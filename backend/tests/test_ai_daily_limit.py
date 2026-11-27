"""D-016 (Gemini free tier only): the daily cap on real requests, counted in PostgreSQL per Google
quota day and model, and reported as AI_DAILY_LIMIT (429) by the API. No real model is called:
the gate is tested on the test database, the API with a provider that reports the cap."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError

from app.ai.providers.fake import FakeProvider
from app.ai.usage import DailyLimitReached, PostgresDailyGate, asyncpg_dsn, quota_day
from app.core.config import Settings
from tests.assistant_helpers import ask
from tests.auth_helpers import fetch_all
from tests.p07_helpers import new_account

NOON_UTC = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


def gate(url: str, limit: int, now: datetime = NOON_UTC) -> PostgresDailyGate:
    return PostgresDailyGate(url, limit, now=lambda: now)


async def take(g: PostgresDailyGate, model: str) -> None:
    # The provider calls the gate from a worker thread (no event loop there).
    await asyncio.to_thread(g.take, model)


@pytest.fixture
async def model_name(migrated_database: str) -> Any:
    name = f"test-model-{datetime.now(UTC).timestamp()}"
    yield name
    import asyncpg

    connection = await asyncpg.connect(asyncpg_dsn(migrated_database))
    try:
        await connection.execute("DELETE FROM ai_daily_requests WHERE model LIKE 'test-model-%'")
    finally:
        await connection.close()


async def test_counts_and_refuses_at_the_limit(migrated_database: str, model_name: str) -> None:
    g = gate(migrated_database, 3)
    for _ in range(3):
        await take(g, model_name)

    with pytest.raises(DailyLimitReached):
        await take(g, model_name)
    with pytest.raises(DailyLimitReached):
        await take(g, model_name)

    # A refused request is not counted.
    assert await asyncio.to_thread(g.used, model_name) == 3


async def test_models_and_days_are_counted_apart(migrated_database: str, model_name: str) -> None:
    g = gate(migrated_database, 1)
    await take(g, model_name)

    await take(g, model_name + "-other")  # another model has its own quota
    tomorrow = gate(migrated_database, 1, datetime(2026, 11, 28, 12, 0, tzinfo=UTC))
    await take(tomorrow, model_name)  # a new quota day

    with pytest.raises(DailyLimitReached):
        await take(g, model_name)


async def test_two_processes_share_the_counter(migrated_database: str, model_name: str) -> None:
    backend, experiments = gate(migrated_database, 2), gate(migrated_database, 2)

    await take(backend, model_name)
    await take(experiments, model_name)

    with pytest.raises(DailyLimitReached):
        await take(backend, model_name)


def test_the_quota_day_is_googles_pacific_day() -> None:
    # 07:00 UTC on 27 Nov is still 26 Nov in California (23:00 PST).
    assert quota_day(datetime(2026, 11, 27, 7, 0, tzinfo=UTC)).isoformat() == "2026-11-26"
    assert quota_day(datetime(2026, 11, 27, 9, 0, tzinfo=UTC)).isoformat() == "2026-11-27"


def test_the_setting_has_a_safe_default_and_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_MAX_REQUESTS_PER_DAY", raising=False)
    assert Settings().ai_max_requests_per_day == 100  # type: ignore[call-arg]
    monkeypatch.setenv("AI_MAX_REQUESTS_PER_DAY", "0")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


# ---- the API ------------------------------------------------------------------------------------


class CappedProvider(FakeProvider):
    """A provider whose daily cap is used up."""

    def extract_receipt(self, masked_text: str, hints: Any) -> Any:
        raise DailyLimitReached("The daily limit of free AI requests is used up.")

    def extract_bank_rows(self, masked_text: str, bank_key: str | None) -> Any:
        raise DailyLimitReached("The daily limit of free AI requests is used up.")


async def test_receipt_extraction_reports_the_cap(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    api_app.state.ai_provider = CappedProvider()
    user = await new_account(api_client, consent=True)

    response = await api_client.post(
        "/api/v1/extract/receipt",
        json={
            "masked_text": "MIGROS\nTOPLAM 10,00",
            "capture_date": "2026-11-27",
            "source": "GALLERY",
        },
        headers=user.headers,
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "AI_DAILY_LIMIT"
    assert await fetch_all(api_app, "SELECT id FROM observations") == []


async def test_the_assistant_reports_the_cap(api_app: FastAPI, api_client: AsyncClient) -> None:
    provider = FakeProvider()
    api_app.state.ai_provider = provider
    provider.script_assistant({"error": "daily_limit"})
    user = await new_account(api_client, consent=True)

    response = await ask(api_client, user, "Bu ay ne harcadım?")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "AI_DAILY_LIMIT"

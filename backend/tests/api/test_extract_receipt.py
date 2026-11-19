"""POST /api/v1/extract/receipt end to end, with FakeProvider (never a real model)."""

import json
import logging
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.ai.providers.fake import FakeProvider
from app.core.config import Settings
from app.main import create_app
from app.services import extraction_service
from tests.auth_helpers import bearer, fetch_all, register_ok
from tests.conftest import make_test_settings

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "receipts"
URL = "/api/v1/extract/receipt"
TODAY = date(2026, 11, 19)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction_service, "business_today", lambda: TODAY)


@pytest.fixture
def provider(api_app: FastAPI) -> FakeProvider:
    fake = FakeProvider.from_directory(FIXTURE_DIR)
    api_app.state.ai_provider = fake
    return fake


def fixture_names() -> list[str]:
    return sorted(path.name.removesuffix(".txt") for path in FIXTURE_DIR.glob("*.txt"))


def text_of(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.txt").read_text(encoding="utf-8")


def body(name: str = "01_migros", **overrides: object) -> dict[str, object]:
    return {
        "masked_text": text_of(name),
        "capture_date": "2026-11-18",
        "source": "GALLERY",
        **overrides,
    }


async def user_with_consent(client: AsyncClient, *, consent: bool = True) -> dict[str, str]:
    tokens = await register_ok(client)
    headers = bearer(tokens["access_token"])
    if consent:
        response = await client.put(
            "/api/v1/me/ai-consent", json={"ai_consent": True}, headers=headers
        )
        assert response.status_code == 200
    return headers


# ---- the fixtures, end to end ----------------------------------------------------------------


@pytest.mark.parametrize("name", fixture_names())
async def test_every_fixture_returns_the_expected_extraction_and_confidence(
    name: str, api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user_with_consent(api_client)
    expected = json.loads((FIXTURE_DIR / f"{name}.expected.json").read_text(encoding="utf-8"))

    response = await api_client.post(URL, json=body(name), headers=headers)

    if expected.get("rejected"):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "EXTRACTION_REJECTED"
        assert await fetch_all(api_app, "SELECT id FROM observations") == []
        return
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["extraction"] == expected["extraction"]
    assert result["confidence"] == expected["confidence"]
    assert set(result) == {"observation_id", "extraction", "confidence", "suggestions"}

    rows = await fetch_all(
        api_app,
        "SELECT source, status, amount_minor, obs_date IS NULL, field_confidence_json "
        "FROM observations WHERE id = :id",
        id=result["observation_id"],
    )
    assert rows[0][:2] == ("RECEIPT", "PENDING_REVIEW")
    assert rows[0][4] == expected["confidence"]


async def test_the_missing_date_receipt_is_null_and_low(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user_with_consent(api_client)

    result = (await api_client.post(URL, json=body("07_tarihsiz"), headers=headers)).json()

    assert result["extraction"]["date"] is None
    assert result["confidence"]["date"] == "LOW"


# ---- who may call it -------------------------------------------------------------------------


async def test_without_a_token_it_is_401(api_client: AsyncClient, provider: FakeProvider) -> None:
    response = await api_client.post(URL, json=body())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_TOKEN"
    assert provider.calls == 0


async def test_without_consent_it_is_403_and_the_provider_is_never_called(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user_with_consent(api_client, consent=False)

    response = await api_client.post(URL, json=body(), headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
    assert provider.calls == 0
    assert await fetch_all(api_app, "SELECT id FROM observations") == []


async def test_revoking_the_consent_blocks_the_next_request(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user_with_consent(api_client)
    assert (await api_client.post(URL, json=body(), headers=headers)).status_code == 200

    await api_client.put("/api/v1/me/ai-consent", json={"ai_consent": False}, headers=headers)

    response = await api_client.post(URL, json=body(), headers=headers)
    assert response.status_code == 403
    assert provider.calls == 1


async def test_consent_belongs_to_one_user_only(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    consenting = await user_with_consent(api_client)
    other = await user_with_consent(api_client, consent=False)

    assert (await api_client.post(URL, json=body(), headers=consenting)).status_code == 200
    assert (await api_client.post(URL, json=body(), headers=other)).status_code == 403


async def test_the_observation_belongs_to_the_caller(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    first = await register_ok(api_client)
    second = await register_ok(api_client)
    me = await api_client.get("/api/v1/me", headers=bearer(first["access_token"]))
    headers = bearer(first["access_token"])
    await api_client.put("/api/v1/me/ai-consent", json={"ai_consent": True}, headers=headers)

    observation_id = (await api_client.post(URL, json=body(), headers=headers)).json()[
        "observation_id"
    ]

    owner = await fetch_all(
        api_app, "SELECT user_id FROM observations WHERE id = :id", id=observation_id
    )
    assert str(owner[0][0]) == me.json()["id"]
    other_me = await api_client.get("/api/v1/me", headers=bearer(second["access_token"]))
    assert str(owner[0][0]) != other_me.json()["id"]


# ---- limits ----------------------------------------------------------------------------------


async def test_21st_request_in_a_minute_is_429(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user_with_consent(api_client)

    for _ in range(20):
        assert (await api_client.post(URL, json=body(), headers=headers)).status_code == 200
    response = await api_client.post(URL, json=body(), headers=headers)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert int(response.headers["retry-after"]) >= 1
    assert provider.calls == 20


async def test_the_limit_is_per_user_and_refused_requests_do_not_use_it_up(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    busy = await user_with_consent(api_client)
    for _ in range(20):
        await api_client.post(URL, json=body(), headers=busy)
    assert (await api_client.post(URL, json=body(), headers=busy)).status_code == 429

    fresh = await user_with_consent(api_client)
    assert (await api_client.post(URL, json=body(), headers=fresh)).status_code == 200

    unconsented = await user_with_consent(api_client, consent=False)
    for _ in range(25):  # all refused with 403: none of them counts against the quota
        assert (await api_client.post(URL, json=body(), headers=unconsented)).status_code == 403
    await api_client.put("/api/v1/me/ai-consent", json={"ai_consent": True}, headers=unconsented)
    assert (await api_client.post(URL, json=body(), headers=unconsented)).status_code == 200


async def test_text_over_20_kb_is_413(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user_with_consent(api_client)

    response = await api_client.post(
        URL, json=body(masked_text="A" * (20 * 1024 + 1)), headers=headers
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "TEXT_TOO_LARGE"
    assert provider.calls == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"masked_text": ""},
        {"masked_text": None},
        {"capture_date": "yesterday"},
        {"source": "FAX"},
        {"source": "RECEIPT"},
    ],
)
async def test_invalid_bodies_are_422_without_echoing_the_input(
    bad: dict[str, object], api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user_with_consent(api_client)

    response = await api_client.post(URL, json=body(**bad), headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "FAX" not in response.text and "yesterday" not in response.text


async def test_a_missing_field_is_422(api_client: AsyncClient, provider: FakeProvider) -> None:
    headers = await user_with_consent(api_client)
    incomplete = {"masked_text": text_of("01_migros")}

    assert (await api_client.post(URL, json=incomplete, headers=headers)).status_code == 422


# ---- failures ---------------------------------------------------------------------------------


async def test_a_text_the_provider_cannot_read_is_502_and_saves_nothing(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user_with_consent(api_client)

    response = await api_client.post(
        URL, json=body(masked_text="NOT A KNOWN RECEIPT 1,00"), headers=headers
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EXTRACTION_FAILED"
    assert "NOT A KNOWN" not in response.text
    assert await fetch_all(api_app, "SELECT id FROM observations") == []


async def test_gemini_without_a_key_is_a_clean_502_not_a_crash(
    migrated_database: str, storage_root: Path
) -> None:
    from httpx import ASGITransport
    from pydantic import SecretStr

    settings: Settings = make_test_settings(
        storage_root=str(storage_root), ai_provider="gemini", gemini_api_key=SecretStr("")
    )
    app = create_app(settings)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            tokens = await register_ok(client)
            headers = bearer(tokens["access_token"])
            await client.put("/api/v1/me/ai-consent", json={"ai_consent": True}, headers=headers)

            response = await client.post(URL, json=body(), headers=headers)

            assert response.status_code == 502
            assert response.json()["error"]["code"] == "EXTRACTION_FAILED"
    finally:
        async with app.state.session_factory() as session:
            from sqlalchemy import text

            await session.execute(text("DELETE FROM users"))
            await session.commit()
        await app.state.engine.dispose()


# ---- privacy ---------------------------------------------------------------------------------


async def test_logs_never_contain_the_receipt_text_amounts_or_merchants(
    api_client: AsyncClient, provider: FakeProvider, caplog: pytest.LogCaptureFixture
) -> None:
    headers = await user_with_consent(api_client)

    with caplog.at_level(logging.DEBUG):
        ok = await api_client.post(URL, json=body("01_migros"), headers=headers)
        rejected = await api_client.post(URL, json=body("12_absurd_tutar"), headers=headers)
        failed = await api_client.post(
            URL, json=body(masked_text="MIGROS 270,30 UNKNOWN"), headers=headers
        )
    assert (ok.status_code, rejected.status_code, failed.status_code) == (200, 422, 502)

    logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    for secret in ("MIGROS", "270,30", "YILDIZ", "1.245.000", "SUT 1L", "14.11.2026"):
        assert secret not in logged, secret
    ai_calls = [r for r in caplog.records if r.name == "receiptbox.ai"]
    assert len(ai_calls) == 3
    assert {r.provider for r in ai_calls} == {"fake"}
    assert all(hasattr(r, "prompt_version") and hasattr(r, "latency_ms") for r in ai_calls)


async def test_the_json_log_formatter_emits_the_call_metadata_only() -> None:
    from app.core.logging import JsonFormatter

    record = logging.LogRecord("receiptbox.ai", logging.INFO, __file__, 1, "ai_call", None, None)
    record.provider = "gemini"
    record.model = "m"
    record.prompt_version = "receipt_extract.v1"
    record.latency_ms = 812
    record.input_tokens = 100
    record.output_tokens = 40
    record.outcome = "ok"
    record.masked_text = "SECRET RECEIPT"  # not whitelisted: must be dropped

    line = json.loads(JsonFormatter().format(record))

    assert line["latency_ms"] == 812 and line["input_tokens"] == 100
    assert "SECRET" not in json.dumps(line)


async def test_the_masked_text_is_stored_but_only_the_masked_one(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user_with_consent(api_client)

    observation_id = (await api_client.post(URL, json=body(), headers=headers)).json()[
        "observation_id"
    ]

    rows = await fetch_all(
        api_app, "SELECT masked_text FROM observations WHERE id = :id", id=observation_id
    )
    assert rows[0][0] == text_of("01_migros")
    assert "[PHONE]" in rows[0][0]  # the text the phone sent, personal data already replaced


async def test_openapi_documents_the_endpoint_and_its_errors(api_app: FastAPI) -> None:
    operation = api_app.openapi()["paths"][URL]["post"]

    assert set(operation["responses"]) >= {"200", "401", "403", "413", "422", "429", "502"}

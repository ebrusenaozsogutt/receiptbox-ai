"""POST /assistant/chat and DELETE /assistant/history (P14): consent, rate limit, input limits,
provider failures, the stored turns and logs without content."""

import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.models.enums import AssistantOutcome
from tests.assistant_helpers import CHAT, ask, build_world, fake, month_end, month_start
from tests.auth_helpers import fetch_all
from tests.p07_helpers import new_account

QUESTION = "Bu ay Gizli Mağaza'ya ne kadar harcadım?"


def this_month() -> dict[str, str]:
    return {"date_from": month_start().isoformat(), "date_to": month_end().isoformat()}


async def turns(app: FastAPI, user_id: object) -> list[tuple]:
    return await fetch_all(
        app, "SELECT outcome, answer FROM assistant_turns WHERE user_id = :u", u=user_id
    )


async def test_needs_a_token(api_client: AsyncClient) -> None:
    response = await api_client.post(CHAT, json={"message": "x"})
    assert response.status_code == 401


async def test_without_ai_consent_the_ai_is_not_called(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    provider = fake(api_app)
    user = await new_account(api_client, consent=False)

    response = await ask(api_client, user, "Bu ay ne harcadım?")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
    assert provider.assistant_requests == []


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": "x" * 501},
        {"message": "x", "history": [{"question": "q", "answer": "a"}] * 7},
        {"message": "x", "user_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
async def test_input_limits(api_app: FastAPI, api_client: AsyncClient, body: dict) -> None:
    fake(api_app)
    user = await new_account(api_client, consent=True)

    response = await api_client.post(CHAT, json=body, headers=user.headers)

    assert response.status_code == 422


async def test_twenty_questions_per_minute(api_app: FastAPI, api_client: AsyncClient) -> None:
    provider = fake(api_app)
    user = await new_account(api_client, consent=True)
    for _ in range(21):
        provider.script_assistant({"answer": "Tamam."})

    codes = [(await ask(api_client, user, "Merhaba")).status_code for _ in range(21)]

    assert codes[:20] == [200] * 20
    assert codes[20] == 429


async def test_quota_or_timeout_before_any_tool_is_503_and_stored_as_failed(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    provider = fake(api_app)
    user = await new_account(api_client, consent=True)
    provider.script_assistant({"error": "unavailable"})

    response = await ask(api_client, user, "Bu ay ne harcadım?")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ASSISTANT_UNAVAILABLE"
    assert await turns(api_app, user.user_id) == [(AssistantOutcome.FAILED, None)]


async def test_a_failure_after_a_tool_answers_from_its_output(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)
    provider = fake(api_app)
    provider.script_assistant(
        {"tool": "aggregate_spending", "args": {**this_month(), "category": "GROCERY"}},
        {"error": "unavailable"},
    )

    response = await ask(api_client, world.a, "Bu ay markete ne kadar harcadım?")

    assert response.status_code == 200
    assert "1.549,90 TL" in response.json()["answer"]
    assert response.json()["actions"][0]["type"] == "OPEN_TRANSACTIONS"
    assert (await turns(api_app, world.a.user_id))[0][0] == AssistantOutcome.TEMPLATE


async def test_clearing_the_history_deletes_only_own_turns(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    provider = fake(api_app)
    a = await new_account(api_client, consent=True)
    b = await new_account(api_client, consent=True)
    for user in (a, a, b):
        provider.script_assistant({"answer": "Tamam."})
        assert (await ask(api_client, user, "Merhaba")).status_code == 200

    response = await api_client.delete("/api/v1/assistant/history", headers=a.headers)

    assert response.status_code == 204
    assert await turns(api_app, a.user_id) == []
    assert len(await turns(api_app, b.user_id)) == 1


async def test_clearing_works_without_consent(api_app: FastAPI, api_client: AsyncClient) -> None:
    user = await new_account(api_client, consent=False)

    response = await api_client.delete("/api/v1/assistant/history", headers=user.headers)

    assert response.status_code == 204


async def test_logs_never_contain_the_question_arguments_or_answer(
    api_app: FastAPI, api_client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    world = await build_world(api_client)
    provider = fake(api_app)
    provider.script_assistant(
        {"tool": "aggregate_spending", "args": {**this_month(), "merchant": "Gizli Mağaza"}},
        {"answer": "Bu ay Gizli Mağaza için kayıtlı bir harcaman yok."},
    )

    with caplog.at_level(logging.DEBUG):
        response = await ask(api_client, world.a, QUESTION)

    assert response.status_code == 200
    logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "Gizli" not in logged
    assert "assistant_turn" in logged and "aggregate_spending" in logged

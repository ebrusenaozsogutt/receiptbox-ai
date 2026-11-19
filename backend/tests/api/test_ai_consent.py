"""The server-side AI consent flag (spec 15.3): PUT /me/ai-consent and GET /me."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.auth_helpers import bearer, fetch_all, register_ok

URL = "/api/v1/me/ai-consent"


async def test_new_accounts_have_not_consented(api_client: AsyncClient) -> None:
    tokens = await register_ok(api_client)

    me = await api_client.get("/api/v1/me", headers=bearer(tokens["access_token"]))

    assert me.json()["ai_consent"] is False


async def test_the_consent_can_be_given_and_withdrawn(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    tokens = await register_ok(api_client)
    headers = bearer(tokens["access_token"])

    given = await api_client.put(URL, json={"ai_consent": True}, headers=headers)
    assert given.status_code == 200
    assert given.json()["ai_consent"] is True
    assert (await api_client.get("/api/v1/me", headers=headers)).json()["ai_consent"] is True
    assert (await fetch_all(api_app, "SELECT ai_consent FROM users"))[0][0] is True

    withdrawn = await api_client.put(URL, json={"ai_consent": False}, headers=headers)
    assert withdrawn.json()["ai_consent"] is False
    assert (await fetch_all(api_app, "SELECT ai_consent FROM users"))[0][0] is False


async def test_setting_the_same_value_twice_is_fine(api_client: AsyncClient) -> None:
    headers = bearer((await register_ok(api_client))["access_token"])

    for _ in range(2):
        assert (
            await api_client.put(URL, json={"ai_consent": True}, headers=headers)
        ).status_code == 200


async def test_it_only_changes_the_callers_own_flag(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    first = bearer((await register_ok(api_client))["access_token"])
    second = bearer((await register_ok(api_client))["access_token"])

    await api_client.put(URL, json={"ai_consent": True}, headers=first)

    assert (await api_client.get("/api/v1/me", headers=second)).json()["ai_consent"] is False
    flags = sorted(row[0] for row in await fetch_all(api_app, "SELECT ai_consent FROM users"))
    assert flags == [False, True]


async def test_it_needs_a_token(api_client: AsyncClient) -> None:
    response = await api_client.put(URL, json={"ai_consent": True})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_TOKEN"


@pytest.mark.parametrize("bad", [{}, {"ai_consent": "maybe"}, {"ai_consent": None}, []])
async def test_a_bad_body_is_422(bad: object, api_client: AsyncClient) -> None:
    headers = bearer((await register_ok(api_client))["access_token"])

    assert (await api_client.put(URL, json=bad, headers=headers)).status_code == 422


async def test_manual_work_does_not_need_the_consent(api_client: AsyncClient) -> None:
    """Spec 15.3: without consent only manual entry is possible. Everything outside /extract/*
    (here: the profile) keeps working for a user who said no."""
    headers = bearer((await register_ok(api_client))["access_token"])

    assert (await api_client.get("/api/v1/me", headers=headers)).status_code == 200
    assert (await api_client.get("/api/v1/health")).status_code in (200, 503)

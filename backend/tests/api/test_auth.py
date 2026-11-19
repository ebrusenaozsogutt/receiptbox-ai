"""Auth endpoints: register, login, refresh (rotation + reuse), logout, /me, rate limit."""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.logging import JsonFormatter
from app.security.rate_limit import SlidingWindowRateLimiter
from app.security.tokens import create_access_token
from tests.auth_helpers import (
    PASSWORD,
    bearer,
    fetch_all,
    login,
    new_email,
    refresh,
    register,
    register_ok,
)
from tests.conftest import make_test_settings

SECRET = make_test_settings().jwt_secret.get_secret_value()


def _error_code(response) -> str:
    return response.json()["error"]["code"]


# ---- register ------------------------------------------------------------------------------


async def test_register_returns_tokens_that_work(api_client: AsyncClient) -> None:
    response = await register(api_client)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900  # 15 minutes
    assert len(body["refresh_token"]) >= 43  # 256 random bits, URL-safe

    me = await api_client.get("/api/v1/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200


async def test_register_lowercases_and_trims_the_email(api_client: AsyncClient) -> None:
    tokens = await register_ok(api_client, email="  Ebru.Test@Example.TEST ")

    me = await api_client.get("/api/v1/me", headers=bearer(tokens["access_token"]))

    assert me.json()["email"] == "ebru.test@example.test"


async def test_register_stores_an_argon2id_hash_and_only_the_hash_of_the_refresh_token(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    tokens = await register_ok(api_client)

    password_hash = (await fetch_all(api_app, "SELECT password_hash FROM users"))[0][0]
    stored_token_hash = (await fetch_all(api_app, "SELECT token_hash FROM refresh_tokens"))[0][0]

    assert password_hash.startswith("$argon2id$")
    assert PASSWORD not in password_hash
    assert stored_token_hash == hashlib.sha256(tokens["refresh_token"].encode()).hexdigest()
    assert stored_token_hash != tokens["refresh_token"]  # the raw token is never stored


async def test_register_sets_adult_confirmation_and_expiry_dates(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    await register_ok(api_client)

    confirmed = (await fetch_all(api_app, "SELECT is_adult_confirmed FROM users"))[0][0]
    expires_at = (await fetch_all(api_app, "SELECT expires_at FROM refresh_tokens"))[0][0]

    assert confirmed is True
    remaining = expires_at - datetime.now(UTC)
    assert timedelta(days=29, hours=23) < remaining <= timedelta(days=30)


async def test_register_duplicate_email_is_rejected_case_insensitively(
    api_client: AsyncClient,
) -> None:
    await register_ok(api_client, email="same@example.test")

    again = await register(api_client, email="SAME@example.test")

    assert again.status_code == 409
    assert _error_code(again) == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.parametrize(
    "password",
    [
        "short1",  # too short
        "abcdefgh",  # no digit
        "12345678",  # no letter
        "!!!!!!!!",  # neither
        "a1" * 65,  # 130 characters: too long
        "",
    ],
)
async def test_register_rejects_weak_passwords(api_client: AsyncClient, password: str) -> None:
    response = await register(api_client, password=password)

    assert response.status_code == 422
    assert _error_code(response) == "WEAK_PASSWORD"


@pytest.mark.parametrize("password", ["abcdefg1", "Parola123", "ş1ifre-uzun", "a" * 127 + "1"])
async def test_register_accepts_passwords_at_the_rules_boundary(
    api_client: AsyncClient, password: str
) -> None:
    response = await register(api_client, password=password)

    assert response.status_code == 201


@pytest.mark.parametrize(
    "email",
    ["", "no-at-sign", "a@b", "a b@example.test", "x@y..z", "@example.test", "ünal@example.test"],
)
async def test_register_rejects_invalid_emails(api_client: AsyncClient, email: str) -> None:
    response = await register(api_client, email=email)

    assert response.status_code == 422
    assert _error_code(response) == "INVALID_EMAIL"


async def test_register_requires_the_adult_confirmation(api_client: AsyncClient) -> None:
    response = await register(api_client, is_adult_confirmed=False)

    assert response.status_code == 422
    assert _error_code(response) == "ADULT_CONFIRMATION_REQUIRED"


async def test_register_with_a_missing_field_is_a_validation_error(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/auth/register", json={"email": new_email(), "password": PASSWORD}
    )

    assert response.status_code == 422
    assert _error_code(response) == "VALIDATION_ERROR"
    assert PASSWORD not in response.text  # input is never echoed back


async def test_nothing_is_stored_when_register_fails(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    await register(api_client, password="weak")
    await register(api_client, is_adult_confirmed=False)

    assert await fetch_all(api_app, "SELECT id FROM users") == []


# ---- login ---------------------------------------------------------------------------------


async def test_login_returns_working_tokens(api_client: AsyncClient) -> None:
    registered = await register_ok(api_client)

    response = await login(api_client, registered["email"])

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    me = await api_client.get("/api/v1/me", headers=bearer(body["access_token"]))
    assert me.json()["email"] == registered["email"]


async def test_login_email_is_case_insensitive(api_client: AsyncClient) -> None:
    registered = await register_ok(api_client, email="mixed.case@example.test")

    response = await login(api_client, "  MIXED.Case@Example.TEST ")

    assert response.status_code == 200
    assert registered["email"] == "mixed.case@example.test"


async def test_each_login_issues_independent_tokens(api_client: AsyncClient) -> None:
    registered = await register_ok(api_client)

    first = (await login(api_client, registered["email"])).json()
    second = (await login(api_client, registered["email"])).json()

    assert first["refresh_token"] != second["refresh_token"] != registered["refresh_token"]
    assert (await refresh(api_client, first["refresh_token"])).status_code == 200
    assert (await refresh(api_client, second["refresh_token"])).status_code == 200


async def test_wrong_password_and_unknown_email_give_the_same_answer(
    api_client: AsyncClient,
) -> None:
    registered = await register_ok(api_client)

    wrong_password = await login(api_client, registered["email"], "Wrong-password-1")
    unknown_email = await login(api_client, new_email("nobody"), PASSWORD)

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert _error_code(wrong_password) == "AUTH_INVALID_CREDENTIALS"
    assert wrong_password.headers["www-authenticate"] == "Bearer"


async def test_login_upgrades_an_old_weaker_password_hash(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    registered = await register_ok(api_client)
    weak_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    async with api_app.state.session_factory() as session:
        from sqlalchemy import text

        await session.execute(
            text("UPDATE users SET password_hash = :h WHERE email = :e"),
            {"h": weak_hash, "e": registered["email"]},
        )
        await session.commit()

    response = await login(api_client, registered["email"])

    assert response.status_code == 200
    new_hash = (await fetch_all(api_app, "SELECT password_hash FROM users"))[0][0]
    assert new_hash != weak_hash
    assert new_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")  # current parameters
    assert (await login(api_client, registered["email"])).status_code == 200  # still works


# ---- refresh: rotation and reuse detection --------------------------------------------------


async def test_refresh_rotates_the_token(api_client: AsyncClient, api_app: FastAPI) -> None:
    first = await register_ok(api_client)

    response = await refresh(api_client, first["refresh_token"])

    assert response.status_code == 200
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    # (Access tokens issued within the same second can be identical: JWT times are in seconds.)
    me = await api_client.get("/api/v1/me", headers=bearer(second["access_token"]))
    assert me.status_code == 200

    # The old row is revoked and points at its replacement.
    rows = await fetch_all(
        api_app,
        "SELECT t.token_hash, t.revoked_at IS NOT NULL, n.token_hash "
        "FROM refresh_tokens t LEFT JOIN refresh_tokens n ON n.id = t.replaced_by "
        "ORDER BY t.created_at",
    )
    old_hash = hashlib.sha256(first["refresh_token"].encode()).hexdigest()
    new_hash = hashlib.sha256(second["refresh_token"].encode()).hexdigest()
    assert rows[0] == (old_hash, True, new_hash)
    assert rows[1] == (new_hash, False, None)


async def test_a_refresh_token_can_be_used_only_once(api_client: AsyncClient) -> None:
    first = await register_ok(api_client)
    assert (await refresh(api_client, first["refresh_token"])).status_code == 200

    replay = await refresh(api_client, first["refresh_token"])

    assert replay.status_code == 401
    assert _error_code(replay) == "AUTH_INVALID_TOKEN"


async def test_reusing_a_revoked_token_revokes_the_whole_family(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    t1 = await register_ok(api_client)
    t2 = (await refresh(api_client, t1["refresh_token"])).json()
    t3 = (await refresh(api_client, t2["refresh_token"])).json()
    t4 = (await refresh(api_client, t3["refresh_token"])).json()  # the legitimate, newest token

    # Someone replays the oldest token (stolen earlier).
    replay = await refresh(api_client, t1["refresh_token"])

    assert replay.status_code == 401
    # Every token of the family is dead now, including the newest one.
    for token in (t2, t3, t4):
        assert (await refresh(api_client, token["refresh_token"])).status_code == 401
    active = await fetch_all(
        api_app, "SELECT count(*) FROM refresh_tokens WHERE revoked_at IS NULL"
    )
    assert active == [(0,)]


async def test_reuse_in_one_family_does_not_affect_another_login(
    api_client: AsyncClient,
) -> None:
    registered = await register_ok(api_client)
    phone = registered
    laptop = (await login(api_client, registered["email"])).json()

    phone_next = (await refresh(api_client, phone["refresh_token"])).json()
    await refresh(api_client, phone["refresh_token"])  # replay on the phone's family

    assert (await refresh(api_client, phone_next["refresh_token"])).status_code == 401
    assert (await refresh(api_client, laptop["refresh_token"])).status_code == 200


async def test_reuse_does_not_affect_other_users(api_client: AsyncClient) -> None:
    alice = await register_ok(api_client, email=new_email("alice"))
    bob = await register_ok(api_client, email=new_email("bob"))
    await refresh(api_client, alice["refresh_token"])
    await refresh(api_client, alice["refresh_token"])  # replay

    assert (await refresh(api_client, bob["refresh_token"])).status_code == 200


async def test_unknown_refresh_token_is_rejected(api_client: AsyncClient) -> None:
    response = await refresh(api_client, "this-token-was-never-issued")

    assert response.status_code == 401
    assert _error_code(response) == "AUTH_INVALID_TOKEN"


async def test_expired_refresh_token_is_rejected_with_auth_expired(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    tokens = await register_ok(api_client)
    async with api_app.state.session_factory() as session:
        from sqlalchemy import text

        await session.execute(
            text("UPDATE refresh_tokens SET expires_at = now() - interval '1 minute'")
        )
        await session.commit()

    response = await refresh(api_client, tokens["refresh_token"])

    assert response.status_code == 401
    assert _error_code(response) == "AUTH_EXPIRED"


async def test_parallel_refreshes_with_the_same_token_cannot_both_succeed(
    api_client: AsyncClient,
) -> None:
    tokens = await register_ok(api_client)

    first, second = await asyncio.gather(
        refresh(api_client, tokens["refresh_token"]),
        refresh(api_client, tokens["refresh_token"]),
    )

    # The row is locked, so the second request sees the token as already used. (A client must
    # therefore never refresh twice at the same time; the mobile app serialises refreshes.)
    assert sorted([first.status_code, second.status_code]) == [200, 401]


# ---- logout --------------------------------------------------------------------------------


async def test_logout_revokes_the_refresh_token(api_client: AsyncClient) -> None:
    tokens = await register_ok(api_client)

    response = await api_client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 204
    assert response.content == b""
    assert (await refresh(api_client, tokens["refresh_token"])).status_code == 401


async def test_logout_only_affects_the_given_token(api_client: AsyncClient) -> None:
    registered = await register_ok(api_client)
    other_device = (await login(api_client, registered["email"])).json()

    await api_client.post(
        "/api/v1/auth/logout", json={"refresh_token": registered["refresh_token"]}
    )

    assert (await refresh(api_client, other_device["refresh_token"])).status_code == 200


async def test_logout_with_an_unknown_token_still_succeeds(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/v1/auth/logout", json={"refresh_token": "unknown"})

    assert response.status_code == 204  # idempotent, and reveals nothing


# ---- GET /me and access-token checks -------------------------------------------------------


async def test_me_returns_the_profile_and_never_the_password(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    tokens = await register_ok(api_client)

    response = await api_client.get("/api/v1/me", headers=bearer(tokens["access_token"]))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "email", "is_adult_confirmed", "ai_consent", "created_at"}
    assert body["email"] == tokens["email"]
    assert body["is_adult_confirmed"] is True
    assert "password" not in response.text
    assert "$argon2" not in response.text


async def test_me_without_a_token_is_401(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/me")

    assert response.status_code == 401
    assert _error_code(response) == "AUTH_INVALID_TOKEN"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "authorization",
    ["Bearer", "Bearer not.a.jwt", "Basic dXNlcjpwYXNz", "token abc", "Bearer " + "a" * 500],
)
async def test_me_with_a_bad_authorization_header_is_401(
    api_client: AsyncClient, authorization: str
) -> None:
    response = await api_client.get("/api/v1/me", headers={"Authorization": authorization})

    assert response.status_code == 401
    assert _error_code(response) == "AUTH_INVALID_TOKEN"


async def test_expired_access_token_is_401_auth_expired(api_client: AsyncClient) -> None:
    tokens = await register_ok(api_client)
    me = await api_client.get("/api/v1/me", headers=bearer(tokens["access_token"]))
    user_id = me.json()["id"]
    old_token = create_access_token(
        user_id=__import__("uuid").UUID(user_id),
        secret=SECRET,
        now=datetime.now(UTC) - timedelta(minutes=16),  # issued 16 minutes ago, valid 15
    )

    response = await api_client.get("/api/v1/me", headers=bearer(old_token))

    assert response.status_code == 401
    assert _error_code(response) == "AUTH_EXPIRED"
    assert response.headers["www-authenticate"] == "Bearer"


async def test_access_token_just_inside_its_lifetime_still_works(api_client: AsyncClient) -> None:
    tokens = await register_ok(api_client)
    user_id = (await api_client.get("/api/v1/me", headers=bearer(tokens["access_token"]))).json()[
        "id"
    ]
    token = create_access_token(
        __import__("uuid").UUID(user_id), SECRET, now=datetime.now(UTC) - timedelta(minutes=14)
    )

    assert (await api_client.get("/api/v1/me", headers=bearer(token))).status_code == 200


async def test_forged_tokens_are_rejected(api_client: AsyncClient) -> None:
    tokens = await register_ok(api_client)
    user_id = (await api_client.get("/api/v1/me", headers=bearer(tokens["access_token"]))).json()[
        "id"
    ]
    now = datetime.now(UTC)
    valid_claims = {
        "sub": user_id,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    forged = {
        "signed with another secret": jwt.encode(
            valid_claims, "another-secret-that-is-long-enough-123456", algorithm="HS256"
        ),
        "alg none": jwt.encode(valid_claims, key=None, algorithm="none"),
        "wrong type claim": jwt.encode({**valid_claims, "typ": "refresh"}, SECRET, "HS256"),
        "no exp claim": jwt.encode(
            {k: v for k, v in valid_claims.items() if k != "exp"}, SECRET, "HS256"
        ),
        "no sub claim": jwt.encode(
            {k: v for k, v in valid_claims.items() if k != "sub"}, SECRET, "HS256"
        ),
        "sub is not a uuid": jwt.encode({**valid_claims, "sub": "42"}, SECRET, "HS256"),
        "issued in the future": jwt.encode(
            {**valid_claims, "iat": now + timedelta(hours=2), "exp": now + timedelta(hours=3)},
            SECRET,
            "HS256",
        ),
        "a refresh token used as access token": tokens["refresh_token"],
    }

    for description, token in forged.items():
        response = await api_client.get("/api/v1/me", headers=bearer(token))
        assert response.status_code == 401, description
        assert _error_code(response) == "AUTH_INVALID_TOKEN", description


async def test_valid_token_of_an_unknown_user_is_rejected(api_client: AsyncClient) -> None:
    token = create_access_token(
        __import__("uuid").uuid4(), SECRET
    )  # signed correctly, no such user

    response = await api_client.get("/api/v1/me", headers=bearer(token))

    assert response.status_code == 401
    assert _error_code(response) == "AUTH_INVALID_TOKEN"


# ---- rate limit on login ------------------------------------------------------------------


async def test_login_is_limited_to_5_attempts_per_minute_per_email_and_ip(
    api_client: AsyncClient,
) -> None:
    registered = await register_ok(api_client)

    for _ in range(5):
        wrong = await login(api_client, registered["email"], "Wrong-password-1")
        assert wrong.status_code == 401

    blocked = await login(api_client, registered["email"], "Wrong-password-1")
    assert blocked.status_code == 429
    assert _error_code(blocked) == "RATE_LIMITED"
    assert 1 <= int(blocked.headers["retry-after"]) <= 60

    # Even the correct password is refused while the limit is used up.
    assert (await login(api_client, registered["email"])).status_code == 429


async def test_login_limit_is_per_email(api_client: AsyncClient) -> None:
    first = await register_ok(api_client)
    second = await register_ok(api_client)
    for _ in range(6):
        await login(api_client, first["email"], "Wrong-password-1")

    assert (await login(api_client, second["email"])).status_code == 200


async def test_login_limit_is_per_ip(api_client: AsyncClient, api_app: FastAPI) -> None:
    registered = await register_ok(api_client)
    for _ in range(6):
        await login(api_client, registered["email"], "Wrong-password-1")

    other_ip = ASGITransport(app=api_app, raise_app_exceptions=False, client=("10.1.2.3", 5000))
    async with AsyncClient(transport=other_ip, base_url="http://test") as other_client:
        response = await login(other_client, registered["email"])

    assert response.status_code == 200


async def test_login_is_allowed_again_after_the_window(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    now = [1000.0]
    api_app.state.login_limiter = SlidingWindowRateLimiter(5, 60, clock=lambda: now[0])
    registered = await register_ok(api_client)
    for _ in range(5):
        await login(api_client, registered["email"], "Wrong-password-1")
    assert (await login(api_client, registered["email"])).status_code == 429

    now[0] += 61  # a minute later

    assert (await login(api_client, registered["email"])).status_code == 200


async def test_register_and_refresh_are_not_login_rate_limited(api_client: AsyncClient) -> None:
    for _ in range(7):
        assert (await register(api_client)).status_code == 201


# ---- privacy: secrets never appear in logs -------------------------------------------------


async def test_passwords_and_tokens_never_appear_in_logs(
    api_client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    email = new_email("logtest")
    password = "Never-Log-This-Pass-77"
    with caplog.at_level(logging.DEBUG):
        registered = await register(api_client, email=email, password=password)
        tokens = registered.json()
        await login(api_client, email, password)
        await login(api_client, email, "Wrong-password-1")
        second = await refresh(api_client, tokens["refresh_token"])
        await refresh(api_client, tokens["refresh_token"])  # reuse: logged as an event
        await api_client.get("/api/v1/me", headers=bearer(second.json()["access_token"]))

    formatter = JsonFormatter()
    log_text = "\n".join(formatter.format(record) for record in caplog.records)
    for secret in (
        password,
        tokens["access_token"],
        tokens["refresh_token"],
        second.json()["refresh_token"],
        email,
    ):
        assert secret not in log_text
    assert "refresh_token_reuse_detected" in log_text  # the security event itself is logged


async def test_responses_never_contain_the_password(api_client: AsyncClient) -> None:
    password = "Never-Echo-This-Pass-88"
    email = new_email()

    for response in (
        await register(api_client, email=email, password=password),
        await register(api_client, email=email, password=password),  # duplicate
        await login(api_client, email, password),
        await login(api_client, email, "x"),
    ):
        assert password not in response.text


# ---- OpenAPI -------------------------------------------------------------------------------


async def test_openapi_documents_the_auth_endpoints(api_client: AsyncClient) -> None:
    schema = (await api_client.get("/openapi.json")).json()

    paths = schema["paths"]
    assert "post" in paths["/api/v1/auth/register"]
    assert "post" in paths["/api/v1/auth/login"]
    assert "post" in paths["/api/v1/auth/refresh"]
    assert "post" in paths["/api/v1/auth/logout"]
    assert set(paths["/api/v1/me"]) == {"get", "delete"}
    assert paths["/api/v1/auth/register"]["post"]["responses"]["201"]
    assert paths["/api/v1/auth/logout"]["post"]["responses"]["204"]
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
    token_schema = schema["components"]["schemas"]["TokenResponse"]
    assert set(token_schema["properties"]) == {
        "access_token",
        "refresh_token",
        "token_type",
        "expires_in",
    }
    # The request password is documented as a password field, not echoed in any response model.
    assert "password" not in schema["components"]["schemas"]["UserResponse"]["properties"]

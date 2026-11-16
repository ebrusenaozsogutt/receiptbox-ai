"""Unit tests for passwords, tokens, the rate limiter, the settings check and storage cleanup."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from argon2 import PasswordHasher
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ExpiredTokenError, InvalidTokenError, RateLimitedError
from app.security.passwords import (
    hash_password,
    password_needs_rehash,
    spend_time_like_a_password_check,
    verify_password,
)
from app.security.rate_limit import SlidingWindowRateLimiter
from app.security.tokens import (
    ACCESS_TOKEN_TTL,
    REFRESH_TOKEN_TTL,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from app.storage.files import delete_user_storage, user_storage_dir

SECRET = "unit-test-secret-that-is-at-least-32-chars"


# ---- passwords -------------------------------------------------------------------------------


def test_hash_is_argon2id_with_a_random_salt() -> None:
    first = hash_password("Correct-horse-9")
    second = hash_password("Correct-horse-9")

    assert first.startswith("$argon2id$")
    assert first != second  # different salts
    assert "Correct-horse-9" not in first


def test_verify_password() -> None:
    password_hash = hash_password("Correct-horse-9")

    assert verify_password(password_hash, "Correct-horse-9") is True
    assert verify_password(password_hash, "correct-horse-9") is False
    assert verify_password(password_hash, "") is False


@pytest.mark.parametrize("broken", ["", "not-a-hash", "$argon2id$garbage", "$2b$12$abc"])
def test_verify_never_raises_for_a_malformed_hash(broken: str) -> None:
    assert verify_password(broken, "anything") is False


def test_needs_rehash_only_for_weaker_parameters() -> None:
    current = hash_password("Correct-horse-9")
    weaker = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("Correct-horse-9")

    assert password_needs_rehash(current) is False
    assert password_needs_rehash(weaker) is True


def test_dummy_check_runs_without_error() -> None:
    spend_time_like_a_password_check("whatever")  # used when the e-mail is unknown


# ---- tokens ----------------------------------------------------------------------------------


def test_access_token_round_trip_and_lifetime() -> None:
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    token = create_access_token(user_id, SECRET, now=now)
    claims = jwt.decode(token, SECRET, algorithms=["HS256"])

    assert decode_access_token(token, SECRET) == user_id
    assert claims["sub"] == str(user_id)
    assert claims["exp"] - claims["iat"] == 15 * 60
    assert ACCESS_TOKEN_TTL == timedelta(minutes=15)
    assert REFRESH_TOKEN_TTL == timedelta(days=30)


def test_expired_access_token_raises_expired() -> None:
    token = create_access_token(uuid.uuid4(), SECRET, now=datetime.now(UTC) - timedelta(hours=1))

    with pytest.raises(ExpiredTokenError) as error:
        decode_access_token(token, SECRET)

    assert error.value.code == "AUTH_EXPIRED"
    assert error.value.status_code == 401


def test_wrong_secret_and_garbage_raise_invalid() -> None:
    token = create_access_token(uuid.uuid4(), SECRET)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, "another-secret-that-is-also-long-enough-1")
    with pytest.raises(InvalidTokenError):
        decode_access_token("garbage", SECRET)
    with pytest.raises(InvalidTokenError):
        decode_access_token("", SECRET)


def test_unsigned_alg_none_token_is_rejected() -> None:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    unsigned = jwt.encode(claims, key=None, algorithm="none")

    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned, SECRET)


def test_refresh_tokens_are_256_random_bits_and_hashed_with_sha256() -> None:
    tokens = {new_refresh_token() for _ in range(200)}

    assert len(tokens) == 200  # no collisions
    token = next(iter(tokens))
    assert len(token) == 43  # 32 bytes, base64url without padding
    digest = hash_refresh_token(token)
    assert len(digest) == 64 and digest == hash_refresh_token(token)
    assert digest != token


# ---- settings --------------------------------------------------------------------------------


def test_short_jwt_secret_is_rejected_without_echoing_it() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(jwt_secret="too-short-secret")  # type: ignore[arg-type]

    assert "at least 32" in str(error.value)
    assert "too-short-secret" not in str(error.value)


def test_32_character_jwt_secret_is_accepted() -> None:
    settings = Settings(jwt_secret="x" * 32)  # type: ignore[arg-type]

    assert settings.jwt_secret.get_secret_value() == "x" * 32
    assert "xxxxxxxx" not in repr(settings)  # SecretStr hides it


# ---- rate limiter ----------------------------------------------------------------------------


def test_limiter_allows_the_limit_then_blocks_with_retry_after() -> None:
    clock = [0.0]
    limiter = SlidingWindowRateLimiter(5, 60, clock=lambda: clock[0])

    for _ in range(5):
        limiter.check("a@example.test", "1.1.1.1")
        clock[0] += 1  # attempts at t = 0, 1, 2, 3, 4

    with pytest.raises(RateLimitedError) as error:
        limiter.check("a@example.test", "1.1.1.1")  # t = 5
    assert error.value.status_code == 429
    assert error.value.retry_after_seconds == 55  # the first attempt (t=0) leaves at t=60
    assert error.value.headers == {"Retry-After": "55"}


def test_limiter_keys_are_independent() -> None:
    limiter = SlidingWindowRateLimiter(1, 60, clock=lambda: 0.0)
    limiter.check("a@example.test", "1.1.1.1")

    limiter.check("b@example.test", "1.1.1.1")  # other e-mail
    limiter.check("a@example.test", "2.2.2.2")  # other IP
    with pytest.raises(RateLimitedError):
        limiter.check("a@example.test", "1.1.1.1")


def test_limiter_window_slides() -> None:
    clock = [0.0]
    limiter = SlidingWindowRateLimiter(2, 10, clock=lambda: clock[0])
    limiter.check("k")
    clock[0] = 6
    limiter.check("k")
    clock[0] = 9
    with pytest.raises(RateLimitedError):
        limiter.check("k")

    clock[0] = 10.5  # the first attempt (t=0) has left the window, the second (t=6) has not
    limiter.check("k")
    with pytest.raises(RateLimitedError):
        limiter.check("k")


def test_limiter_forgets_idle_keys() -> None:
    clock = [0.0]
    limiter = SlidingWindowRateLimiter(5, 60, clock=lambda: clock[0])
    for index in range(100):
        limiter.check(f"user{index}@example.test", "1.1.1.1")

    clock[0] = 500  # long after the window
    limiter.check("someone-new", "1.1.1.1")

    assert len(limiter._hits) == 1  # the 100 idle keys were swept


def test_limiter_does_not_keep_the_email_in_memory_in_readable_form() -> None:
    limiter = SlidingWindowRateLimiter(5, 60)
    limiter.check("secret.person@example.test", "1.1.1.1")

    assert all("secret.person" not in key for key in limiter._hits)


# ---- storage cleanup -------------------------------------------------------------------------


def test_delete_user_storage_removes_only_that_users_folder(storage_root: Path) -> None:
    alice, bob = uuid.uuid4(), uuid.uuid4()
    for user_id in (alice, bob):
        folder = user_storage_dir(storage_root, user_id) / "receipts"
        folder.mkdir(parents=True)
        (folder / "photo.jpg").write_bytes(b"data")

    delete_user_storage(storage_root, alice)

    assert not user_storage_dir(storage_root, alice).exists()
    assert (user_storage_dir(storage_root, bob) / "receipts" / "photo.jpg").exists()


def test_delete_user_storage_is_fine_when_the_folder_does_not_exist(storage_root: Path) -> None:
    delete_user_storage(storage_root, uuid.uuid4())  # no error


def test_user_storage_path_follows_the_spec(storage_root: Path) -> None:
    user_id = uuid.uuid4()

    assert user_storage_dir(storage_root, user_id) == storage_root.resolve() / "users" / str(
        user_id
    )

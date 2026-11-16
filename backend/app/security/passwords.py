"""Password hashing with Argon2id (argon2-cffi).

`PasswordHasher()` defaults to Argon2id with the RFC 9106 "low memory" profile
(time cost 3, 64 MiB, 4 lanes). Verification is constant-time inside the library.
"""

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """An encoded Argon2id hash ("$argon2id$..."), including a random salt."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """True if the password matches. Never raises for a wrong password or a malformed hash."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when the stored hash uses weaker parameters than the current ones."""
    return _hasher.check_needs_rehash(password_hash)


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash("not-a-real-password-used-for-timing-only")


def spend_time_like_a_password_check(password: str) -> None:
    """Burn the same time as a real verification.

    Used when the e-mail is unknown, so that the response time does not reveal whether an
    account exists.
    """
    verify_password(_dummy_hash(), password)

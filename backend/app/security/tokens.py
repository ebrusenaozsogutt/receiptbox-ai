"""Access tokens (JWT) and refresh tokens (opaque random strings).

- Access token: JWT, HS256, 15 minutes, `sub` = user id. Verified on every request.
- Refresh token: 256 random bits, handed to the client once. Only its SHA-256 hash is stored,
  so a database leak does not leak usable tokens. 30 days, rotated on every use.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.errors import ExpiredTokenError, InvalidTokenError

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"  # noqa: S105 (a label, not a secret)


def create_access_token(user_id: uuid.UUID, secret: str, *, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "typ": ACCESS_TOKEN_TYPE,
        "iat": issued_at,
        "exp": issued_at + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> uuid.UUID:
    """The user id inside a valid access token.

    Raises ExpiredTokenError (AUTH_EXPIRED) or InvalidTokenError (AUTH_INVALID_TOKEN).
    The algorithm is pinned, so "alg: none" and algorithm-confusion tokens are rejected.
    """
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as error:
        raise ExpiredTokenError() from error
    except jwt.InvalidTokenError as error:
        raise InvalidTokenError() from error

    if claims.get("typ") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError()
    try:
        return uuid.UUID(claims["sub"])
    except (ValueError, TypeError, AttributeError) as error:
        raise InvalidTokenError() from error


def new_refresh_token() -> str:
    """256 random bits, URL-safe (43 characters)."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hex digest. Safe without a salt because the input is already 256 random bits."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

"""Signed, short-lived tokens for downloading ONE document (spec 15.2).

A token says: user U may read document D until it expires (5 minutes). It is a JWT signed with
the server secret, with its own `typ`, so it cannot be used as an access token and an access
token cannot be used as a document token. The app puts it in the URL of an image view, which has
no way to send an Authorization header; the access log never records query strings.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.errors import ExpiredTokenError, InvalidTokenError

DOCUMENT_TOKEN_TTL = timedelta(minutes=5)
DOCUMENT_TOKEN_TYPE = "document"  # noqa: S105 (a label, not a secret)
_ALGORITHM = "HS256"


def create_document_token(
    user_id: uuid.UUID, document_id: uuid.UUID, secret: str, *, now: datetime | None = None
) -> str:
    issued_at = now or datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "doc": str(document_id),
        "typ": DOCUMENT_TOKEN_TYPE,
        "iat": issued_at,
        "exp": issued_at + DOCUMENT_TOKEN_TTL,
    }
    return jwt.encode(claims, secret, algorithm=_ALGORITHM)


def decode_document_token(token: str, secret: str) -> tuple[uuid.UUID, uuid.UUID]:
    """(user id, document id). Raises ExpiredTokenError or InvalidTokenError."""
    try:
        claims = jwt.decode(
            token, secret, algorithms=[_ALGORITHM], options={"require": ["exp", "iat", "sub"]}
        )
    except jwt.ExpiredSignatureError as error:
        raise ExpiredTokenError() from error
    except jwt.InvalidTokenError as error:
        raise InvalidTokenError() from error
    if claims.get("typ") != DOCUMENT_TOKEN_TYPE:
        raise InvalidTokenError()
    try:
        return uuid.UUID(claims["sub"]), uuid.UUID(claims["doc"])
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise InvalidTokenError() from error

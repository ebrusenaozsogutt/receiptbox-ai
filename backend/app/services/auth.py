"""Authentication logic: register, login, refresh (with rotation), logout, delete account.

The service owns the transaction: it commits at the end of each operation. Repositories only
flush. A session that is closed without commit() discards its changes, so anything that must
survive an error (for example revoking a token family) is committed *before* raising.
"""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    AdultConfirmationRequiredError,
    EmailAlreadyRegisteredError,
    ExpiredTokenError,
    InvalidCredentialsError,
    InvalidEmailError,
    InvalidTokenError,
    WeakPasswordError,
)
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository
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
    hash_refresh_token,
    new_refresh_token,
)
from app.storage.files import delete_user_storage

logger = logging.getLogger("receiptbox.auth")

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128  # also stops absurdly long inputs from burning hashing time
EMAIL_MAX_LENGTH = 254

# ASCII-only on purpose: Python's and PostgreSQL's lower() can disagree on some non-ASCII
# letters, which would trip the "email = lower(email)" CHECK constraint.
_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int  # seconds


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> None:
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL_PATTERN.match(email):
        raise InvalidEmailError()


def validate_password(password: str) -> None:
    """At least 8 characters (at most 128), with at least one letter and one digit."""
    if not (PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH):
        raise WeakPasswordError()
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        raise WeakPasswordError()


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        login_limiter: SlidingWindowRateLimiter,
    ) -> None:
        self._session = session
        self._settings = settings
        self._login_limiter = login_limiter
        self._users = UserRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)

    # ---- register / login --------------------------------------------------------------

    async def register(self, *, email: str, password: str, is_adult_confirmed: bool) -> TokenPair:
        email = normalize_email(email)
        validate_email(email)
        validate_password(password)
        if not is_adult_confirmed:
            raise AdultConfirmationRequiredError()

        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError()
        try:
            user = await self._users.add(
                email=email,
                password_hash=await asyncio.to_thread(hash_password, password),
                is_adult_confirmed=True,
            )
        except IntegrityError as error:  # two registrations for the same e-mail raced
            await self._session.rollback()
            raise EmailAlreadyRegisteredError() from error

        tokens = await self._issue_tokens(user.id)
        await self._session.commit()
        return tokens

    async def login(self, *, email: str, password: str, client_ip: str) -> TokenPair:
        email = normalize_email(email)
        # Counted per e-mail + IP, before any work is done (5 attempts per minute).
        self._login_limiter.check(email, client_ip)

        # Argon2 takes ~50 ms of CPU. It runs in a worker thread (the library releases the GIL)
        # so that one login does not freeze every other request of this single-process server.
        user = await self._users.get_by_email(email)
        if user is None:
            await asyncio.to_thread(spend_time_like_a_password_check, password)
            raise InvalidCredentialsError()
        if not await asyncio.to_thread(verify_password, user.password_hash, password):
            raise InvalidCredentialsError()

        if password_needs_rehash(user.password_hash):
            new_hash = await asyncio.to_thread(hash_password, password)
            await self._users.set_password_hash(user.id, new_hash)

        tokens = await self._issue_tokens(user.id)
        await self._session.commit()
        return tokens

    # ---- refresh / logout --------------------------------------------------------------

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a refresh token for a new pair. The presented token is single-use."""
        now = datetime.now(UTC)
        token = await self._refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
        if token is None:
            raise InvalidTokenError()

        if token.revoked_at is not None:
            # A token that was already used (or logged out) is being presented again: either
            # it was stolen or a client replayed it. Revoke the whole family, then fail.
            await self._refresh_tokens.revoke_family(token.user_id, token.id, now=now)
            await self._session.commit()
            logger.warning("refresh_token_reuse_detected")
            raise InvalidTokenError()

        if token.expires_at <= now:
            raise ExpiredTokenError()

        user_id = token.user_id
        tokens, new_token_id = await self._issue_tokens_with_id(user_id)
        await self._refresh_tokens.revoke(user_id, token.id, now=now, replaced_by=new_token_id)
        await self._session.commit()
        return tokens

    async def logout(self, refresh_token: str) -> None:
        """Revoke the given refresh token. Always succeeds, so it reveals nothing."""
        token = await self._refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
        if token is not None and token.revoked_at is None:
            await self._refresh_tokens.revoke(token.user_id, token.id, now=datetime.now(UTC))
            await self._session.commit()

    # ---- account -----------------------------------------------------------------------

    async def set_ai_consent(self, user_id: uuid.UUID, value: bool) -> None:
        await self._users.set_ai_consent(user_id, value)
        await self._session.commit()

    async def delete_account(self, user_id: uuid.UUID) -> None:
        """Delete the user (cascades remove every row they own), then their files."""
        await self._users.delete(user_id)
        await self._session.commit()
        try:
            delete_user_storage(self._settings.storage_root, user_id)
        except OSError as error:
            # The account is already gone; do not fail the request, but leave a trace.
            logger.error("storage_cleanup_failed", extra={"error_type": type(error).__name__})

    # ---- helpers -----------------------------------------------------------------------

    async def _issue_tokens(self, user_id: uuid.UUID) -> TokenPair:
        tokens, _ = await self._issue_tokens_with_id(user_id)
        return tokens

    async def _issue_tokens_with_id(self, user_id: uuid.UUID) -> tuple[TokenPair, uuid.UUID]:
        now = datetime.now(UTC)
        refresh_token = new_refresh_token()
        row = await self._refresh_tokens.add(
            user_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=now + REFRESH_TOKEN_TTL,
        )
        access_token = create_access_token(
            user_id, self._settings.jwt_secret.get_secret_value(), now=now
        )
        pair = TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
        )
        return pair, row.id

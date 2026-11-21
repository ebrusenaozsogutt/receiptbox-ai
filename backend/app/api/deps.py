"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import AIProvider, ProviderConfigError, get_provider
from app.core.config import Settings
from app.core.database import get_session
from app.core.errors import (
    AiConsentRequiredError,
    ExtractionFailedError,
    InvalidTokenError,
)
from app.models import User
from app.repositories.users import UserRepository
from app.security.rate_limit import SlidingWindowRateLimiter
from app.security.tokens import decode_access_token
from app.services.auth import AuthService
from app.services.bank_service import BankService
from app.services.document_service import DocumentService
from app.services.extraction_service import ExtractionService
from app.services.transaction_service import TransactionService
from app.storage.backend import StorageBackend

# auto_error=False: a missing header is reported by us (401 + our error shape), not by FastAPI
# (which would answer 403). The scheme also gives Swagger UI its "Authorize" button.
bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access token.")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_settings_from_app(request: Request) -> Settings:
    return request.app.state.settings


def get_login_limiter(request: Request) -> SlidingWindowRateLimiter:
    return request.app.state.login_limiter


def get_auth_service(
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    login_limiter: Annotated[SlidingWindowRateLimiter, Depends(get_login_limiter)],
) -> AuthService:
    return AuthService(session, settings, login_limiter)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> User:
    """The authenticated user, or 401 AUTH_INVALID_TOKEN / AUTH_EXPIRED."""
    if credentials is None:
        raise InvalidTokenError()
    user_id = decode_access_token(credentials.credentials, settings.jwt_secret.get_secret_value())
    user = await UserRepository(session).get(user_id)
    if user is None:  # a valid token for an account that has since been deleted
        raise InvalidTokenError()
    return user


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ---- AI extraction (P05) ----------------------------------------------------------------------


def get_ai_provider(request: Request) -> AIProvider:
    """The provider is built on first use and kept, so the app starts without an API key."""
    provider = request.app.state.ai_provider
    if provider is None:
        try:
            provider = get_provider(request.app.state.settings)
        except ProviderConfigError:
            raise ExtractionFailedError() from None
        request.app.state.ai_provider = provider
    return provider


async def get_extraction_user(user: CurrentUser, request: Request) -> User:
    """Signed in + consented + inside the rate limit. Consent comes first so that a refused
    request does not use up the user's quota. Manual entry never goes through this."""
    if not user.ai_consent:
        raise AiConsentRequiredError()
    request.app.state.extract_limiter.check(str(user.id))
    return user


ExtractionUser = Annotated[User, Depends(get_extraction_user)]


async def get_extraction_caller(user: CurrentUser, request: Request) -> User:
    """Signed in + inside the rate limit, but NO consent required: the e-invoice QR path reads
    the QR without any AI. (It uses the AI only for users who consented.)"""
    request.app.state.extract_limiter.check(str(user.id))
    return user


ExtractionCaller = Annotated[User, Depends(get_extraction_caller)]


def get_extraction_service(
    session: SessionDep, provider: Annotated[AIProvider, Depends(get_ai_provider)]
) -> ExtractionService:
    return ExtractionService(session, provider)


ExtractionServiceDep = Annotated[ExtractionService, Depends(get_extraction_service)]


def get_bank_service(
    session: SessionDep, provider: Annotated[AIProvider, Depends(get_ai_provider)]
) -> BankService:
    return BankService(session, provider)


BankServiceDep = Annotated[BankService, Depends(get_bank_service)]


# ---- documents (P07) --------------------------------------------------------------------------


def get_storage(request: Request) -> StorageBackend:
    return request.app.state.storage


def get_document_service(
    session: SessionDep,
    storage: Annotated[StorageBackend, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> DocumentService:
    return DocumentService(session, storage, settings)


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]


# ---- review and transactions (P07) ------------------------------------------------------------


def get_transaction_service(
    session: SessionDep, storage: Annotated[StorageBackend, Depends(get_storage)]
) -> TransactionService:
    return TransactionService(session, storage)


TransactionServiceDep = Annotated[TransactionService, Depends(get_transaction_service)]

"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import get_session
from app.core.errors import InvalidTokenError
from app.models import User
from app.repositories.users import UserRepository
from app.security.rate_limit import SlidingWindowRateLimiter
from app.security.tokens import decode_access_token
from app.services.auth import AuthService

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

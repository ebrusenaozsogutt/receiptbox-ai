"""Auth endpoints (spec 16): register, login, refresh, logout, GET /me, DELETE /me."""

from fastapi import APIRouter, Request, Response, status

from app.api.deps import AuthServiceDep, CurrentUser
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.errors import ErrorResponse
from app.services.auth import TokenPair

router = APIRouter(tags=["auth"])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"}}


def _token_response(tokens: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse, "description": "EMAIL_ALREADY_REGISTERED"},
        422: {
            "model": ErrorResponse,
            "description": "INVALID_EMAIL, WEAK_PASSWORD or ADULT_CONFIRMATION_REQUIRED",
        },
    },
)
async def register(body: RegisterRequest, service: AuthServiceDep) -> TokenResponse:
    tokens = await service.register(
        email=body.email,
        password=body.password.get_secret_value(),
        is_adult_confirmed=body.is_adult_confirmed,
    )
    return _token_response(tokens)


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "AUTH_INVALID_CREDENTIALS"},
        429: {"model": ErrorResponse, "description": "RATE_LIMITED (5 attempts per minute)"},
    },
)
async def login(body: LoginRequest, request: Request, service: AuthServiceDep) -> TokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    tokens = await service.login(
        email=body.email, password=body.password.get_secret_value(), client_ip=client_ip
    )
    return _token_response(tokens)


@router.post("/auth/refresh", response_model=TokenResponse, responses=_UNAUTHORIZED)
async def refresh(body: RefreshRequest, service: AuthServiceDep) -> TokenResponse:
    """Rotates the refresh token: the old one stops working. Re-using it revokes the family."""
    return _token_response(await service.refresh(body.refresh_token))


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, service: AuthServiceDep) -> Response:
    await service.logout(body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse, responses=_UNAUTHORIZED)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, responses=_UNAUTHORIZED)
async def delete_me(current_user: CurrentUser, service: AuthServiceDep) -> Response:
    """Deletes the account, every row the user owns, and the user's stored files."""
    await service.delete_account(current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

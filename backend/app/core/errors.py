"""Domain exceptions and the single handler that maps them to the API error shape.

Every error response looks like: {"error": {"code": "STRING_CODE", "message": "..."}}.
Messages never echo request input, because input may contain personal data.
"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("receiptbox.errors")


class AppError(Exception):
    """Base class for domain errors. Subclasses set status_code and code."""

    status_code = 400
    code = "BAD_REQUEST"
    default_message = "The request could not be processed."

    def __init__(
        self, message: str | None = None, *, headers: dict[str, str] | None = None
    ) -> None:
        self.message = message or self.default_message
        self.headers = headers
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    default_message = "The request conflicts with the current state."


class ValidationFailedError(AppError):
    """A business-rule validation failure (the request was well-formed JSON)."""

    status_code = 422
    code = "VALIDATION_ERROR"
    default_message = "The request is invalid."


# ---- authentication (P02) ----------------------------------------------------------------


class AuthError(AppError):
    """401. The WWW-Authenticate header is required by RFC 6750 for bearer authentication."""

    status_code = 401
    code = "AUTH_INVALID_TOKEN"
    default_message = "Authentication is required."

    def __init__(
        self, message: str | None = None, *, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message, headers=headers or {"WWW-Authenticate": "Bearer"})


class InvalidTokenError(AuthError):
    code = "AUTH_INVALID_TOKEN"
    default_message = "The token is missing, malformed, revoked or unknown."


class ExpiredTokenError(AuthError):
    code = "AUTH_EXPIRED"
    default_message = "The token has expired."


class InvalidCredentialsError(AuthError):
    # Same answer for "no such e-mail" and "wrong password", so it cannot be used to find
    # out which e-mail addresses are registered.
    code = "AUTH_INVALID_CREDENTIALS"
    default_message = "E-mail or password is incorrect."


class InvalidEmailError(ValidationFailedError):
    code = "INVALID_EMAIL"
    default_message = "The e-mail address is not valid."


class WeakPasswordError(ValidationFailedError):
    code = "WEAK_PASSWORD"
    default_message = (
        "The password must be 8-128 characters with at least one letter and one digit."
    )


class AdultConfirmationRequiredError(ValidationFailedError):
    code = "ADULT_CONFIRMATION_REQUIRED"
    default_message = "You must confirm that you are 18 or older."


class EmailAlreadyRegisteredError(ConflictError):
    code = "EMAIL_ALREADY_REGISTERED"
    default_message = "An account with this e-mail address already exists."


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    default_message = "Too many attempts. Try again later."

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(headers={"Retry-After": str(retry_after_seconds)})
        self.retry_after_seconds = retry_after_seconds


# ---- AI extraction (P05) -----------------------------------------------------------------


class AiConsentRequiredError(AppError):
    """The user has not agreed that masked text goes to an external AI provider (spec 15.3).
    Manual entry does not need the consent."""

    status_code = 403
    code = "AI_CONSENT_REQUIRED"
    default_message = "AI extraction needs your consent. You can still add purchases manually."


class TextTooLargeError(AppError):
    status_code = 413
    code = "TEXT_TOO_LARGE"
    default_message = "The text is too large (at most 20 KB)."


class InvalidQrError(AppError):
    """The QR content is not a usable GİB e-invoice QR."""

    status_code = 422
    code = "QR_INVALID"
    default_message = "The QR code is not a readable e-Archive / e-Invoice QR."


class ExtractionRejectedError(AppError):
    """The extraction was not credible (for example an absurd amount). Nothing was saved."""

    status_code = 422
    code = "EXTRACTION_REJECTED"
    default_message = "The receipt could not be read reliably. You can enter it manually."


class ExtractionFailedError(AppError):
    """The AI provider failed (timeout, quota, bad answer). Nothing was saved."""

    status_code = 502
    code = "EXTRACTION_FAILED"
    default_message = "The receipt could not be read right now. You can enter it manually."


# ---- documents (P07) ---------------------------------------------------------------------


class FileTooLargeError(AppError):
    status_code = 413
    code = "FILE_TOO_LARGE"
    default_message = "The file is too large (at most 10 MB)."


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "UNSUPPORTED_FILE_TYPE"
    default_message = "Only jpeg, png and pdf files are accepted."


def error_response(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


def _http_status_code_name(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).name  # e.g. 404 -> "NOT_FOUND"
    except ValueError:
        return "HTTP_ERROR"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Covers unknown routes (404), wrong methods (405), etc.
        return error_response(
            exc.status_code,
            _http_status_code_name(exc.status_code),
            HTTPStatus(exc.status_code).phrase if exc.status_code in HTTPStatus else "HTTP error",
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        # Deliberately generic: pydantic's default body would echo the invalid input back.
        return error_response(
            422, "VALIDATION_ERROR", "The request body or parameters are invalid."
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Log the exception type and path only. Exception messages and tracebacks can contain
        # SQL parameters or request data, which must never reach the logs.
        logger.error(
            "unhandled_error",
            extra={"path": request.url.path, "error_type": type(exc).__name__},
        )
        return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")

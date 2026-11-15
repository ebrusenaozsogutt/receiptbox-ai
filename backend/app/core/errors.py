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

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    default_message = "The request conflicts with the current state."


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _http_status_code_name(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).name  # e.g. 404 -> "NOT_FOUND"
    except ValueError:
        return "HTTP_ERROR"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

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

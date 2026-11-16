from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Every error response of the API (see app/core/errors.py)."""

    error: ErrorBody

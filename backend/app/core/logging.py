"""Structured (JSON) logging that never records request bodies, headers or query strings.

Privacy rule (CLAUDE.md): never log OCR text, tokens, e-mails, or amounts together with
merchant names. To make that hard to violate by accident, the formatter only emits a fixed
whitelist of extra fields.
"""

import json
import logging
import time
from datetime import UTC, datetime

from fastapi import FastAPI, Request

LOGGER_NAME = "receiptbox"

# The only extra fields a log call may attach. Anything else is silently dropped.
ALLOWED_EXTRA_FIELDS = (
    "method",
    "path",
    "status",
    "duration_ms",
    "error_type",
    # AI provider calls (spec 14): never the content, only these.
    "provider",
    "model",
    "prompt_version",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "outcome",
    # P14 assistant: the tool's name and the number of tool calls (never arguments or answers).
    "tool",
    "tool_calls",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in ALLOWED_EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        # exc_info / stack traces are intentionally never included (they can contain data).
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Idempotent: safe to call once per created app (tests create many)."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    if not any(getattr(h, "_receiptbox", False) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._receiptbox = True  # type: ignore[attr-defined]
        logger.addHandler(handler)

    # uvicorn's access log prints the full URL including the query string (which will later
    # carry document access tokens). We log requests ourselves, without the query string.
    logging.getLogger("uvicorn.access").disabled = True


def install_access_log(app: FastAPI) -> None:
    access_logger = logging.getLogger(f"{LOGGER_NAME}.access")

    @app.middleware("http")
    async def access_log(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        access_logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,  # path only: no query string, no body, no headers
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

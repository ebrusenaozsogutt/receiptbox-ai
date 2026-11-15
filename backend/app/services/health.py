import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.health import HealthResponse

logger = logging.getLogger("receiptbox.health")

DB_CHECK_TIMEOUT_SECONDS = 3


async def check_health(session: AsyncSession) -> HealthResponse:
    """Run `SELECT 1`. This touches no user data, so it takes no user_id."""
    try:
        async with asyncio.timeout(DB_CHECK_TIMEOUT_SECONDS):
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # health must report any failure, never raise
        logger.warning("db_check_failed", extra={"error_type": type(exc).__name__})
        return HealthResponse(status="degraded", db="error")
    return HealthResponse(status="ok", db="ok")

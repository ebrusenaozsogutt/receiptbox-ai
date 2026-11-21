"""Data retention (spec 5.5, 15.3): the masked screenshot text is kept for 30 days for debugging
and is then set to NULL. Run at startup (`app.main`); the extracted fields stay."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Observation

logger = logging.getLogger("receiptbox.retention")

MASKED_TEXT_RETENTION = timedelta(days=30)


async def null_old_masked_text(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Set `masked_text` to NULL on every observation older than 30 days. Returns how many."""
    cutoff = (now or datetime.now(UTC)) - MASKED_TEXT_RETENTION
    result = await session.execute(
        update(Observation)
        .where(Observation.masked_text.is_not(None), Observation.created_at < cutoff)
        .values(masked_text=None)
    )
    await session.commit()
    return result.rowcount or 0

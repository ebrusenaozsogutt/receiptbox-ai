"""Free tier only (D-016): a daily cap on real Gemini requests, and a hook for caching answers.

`PostgresDailyGate.take(model)` counts one request in `ai_daily_requests` (one row per day and
model) and refuses with `DailyLimitReached` once `AI_MAX_REQUESTS_PER_DAY` requests were made
that day. The day is Google's quota day (midnight Pacific time). The counter lives in the
database, so the backend (in Docker) and the experiment scripts (on the host) share it and a
restart does not reset it. Retries count too: each one is a request.

The gate is called from the provider's worker thread (the SDK is blocking), where no event loop
runs, so it opens one short asyncpg connection per request. That costs a few milliseconds next to
a model call of seconds.

`ResponseCache` is what the experiment harness plugs into the provider so that a rerun with the
same input sends nothing (P15). The provider (de)serialises; a cache only stores strings.
"""

import asyncio
from collections.abc import Callable
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

import asyncpg

from app.ai.provider import ProviderError

QUOTA_TIMEZONE = ZoneInfo("America/Los_Angeles")  # Google resets free-tier quotas at its midnight


class DailyLimitReached(ProviderError):
    """The daily cap of real requests for this model is used up. No request was sent."""


class RequestGate(Protocol):
    def take(self, model: str) -> None:
        """Count one real request, or raise DailyLimitReached without counting it."""
        ...


class ResponseCache(Protocol):
    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...


def quota_day(now: datetime | None = None) -> date:
    return (now or datetime.now(QUOTA_TIMEZONE)).astimezone(QUOTA_TIMEZONE).date()


def asyncpg_dsn(database_url: str) -> str:
    """'postgresql+asyncpg://...' (SQLAlchemy) -> 'postgresql://...' (asyncpg)."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


# One statement: insert the first request of the day, or add one while under the limit. When the
# limit is reached the UPDATE matches nothing and no row comes back.
_TAKE = """
INSERT INTO ai_daily_requests (day, model, count) VALUES ($1, $2, 1)
ON CONFLICT (day, model) DO UPDATE SET count = ai_daily_requests.count + 1
WHERE ai_daily_requests.count < $3
RETURNING count
"""


class PostgresDailyGate:
    def __init__(
        self,
        database_url: str,
        limit: int,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(QUOTA_TIMEZONE),
    ) -> None:
        if limit < 1:
            raise ValueError("The daily request limit must be at least 1.")
        self._dsn = asyncpg_dsn(database_url)
        self.limit = limit
        self._now = now

    def take(self, model: str) -> None:
        count = asyncio.run(self._take(quota_day(self._now()), model))
        if count is None:
            raise DailyLimitReached("The daily limit of free AI requests is used up.")

    async def _take(self, day: date, model: str) -> int | None:
        connection = await asyncpg.connect(self._dsn)
        try:
            return await connection.fetchval(_TAKE, day, model, self.limit)
        finally:
            await connection.close()

    def used(self, model: str) -> int:
        """Requests counted today for `model` (for the experiment harness's progress line)."""

        async def read() -> int:
            connection = await asyncpg.connect(self._dsn)
            try:
                value = await connection.fetchval(
                    "SELECT count FROM ai_daily_requests WHERE day = $1 AND model = $2",
                    quota_day(self._now()),
                    model,
                )
                return int(value or 0)
            finally:
                await connection.close()

        return asyncio.run(read())

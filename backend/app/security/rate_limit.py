"""A simple in-process sliding-window rate limiter (spec 15.2: no Redis).

State lives in this process only: it resets on restart and is not shared between several
server processes. That is acceptable for the single-process MVP (spec 4, principle 6).
"""

import hashlib
import math
import time
from collections import deque
from collections.abc import Callable

from app.core.errors import RateLimitedError


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._last_sweep = clock()

    def check(self, *key_parts: str) -> None:
        """Count one attempt, or raise RateLimitedError if the limit is already used up."""
        now = self._clock()
        self._sweep(now)

        # The key is hashed so the e-mail address is not kept in memory in readable form.
        key = hashlib.sha256("\x1f".join(key_parts).encode("utf-8")).hexdigest()
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self._window:
            hits.popleft()

        if len(hits) >= self._limit:
            retry_after = max(1, math.ceil(hits[0] + self._window - now))
            raise RateLimitedError(retry_after)
        hits.append(now)

    def _sweep(self, now: float) -> None:
        """Forget keys that have not been seen for a whole window (bounds memory use)."""
        if now - self._last_sweep < self._window:
            return
        self._last_sweep = now
        stale = [
            key for key, hits in self._hits.items() if not hits or hits[-1] <= now - self._window
        ]
        for key in stale:
            del self._hits[key]

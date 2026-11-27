"""The real model for the experiments: Gemini (free tier only, D-016) with the daily cap, a file
cache per (system, input) and pacing. Built through the backend's provider, so the SDK stays in
backend/app/ai/providers/ (CLAUDE.md)."""

import hashlib
from pathlib import Path

from rbx_eval import EXPERIMENTS_DIR

from app.ai.providers.gemini import GeminiProvider  # noqa: E402
from app.ai.usage import PostgresDailyGate  # noqa: E402
from app.core.config import Settings  # noqa: E402

CACHE = EXPERIMENTS_DIR / "cache"


class FileCache:
    """One JSON file per request key: <root>/<key[:2]>/<key>.json. Keys are hashes of the whole
    request (model, system prompt, input, tools), computed by the provider."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.hits = 0
        self.misses = 0

    def _path(self, key: str) -> Path:
        if not key.isalnum():
            raise ValueError("cache keys are hex digests")
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> str | None:
        path = self._path(key)
        if path.is_file():
            self.hits += 1
            return path.read_text(encoding="utf-8")
        self.misses += 1
        return None

    def put(self, key: str, value: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")


def gemini(
    *,
    model: str,
    cache_dir: Path,
    pace_seconds: float,
    settings: Settings | None = None,
    timeout_seconds: float | None = None,
) -> tuple[GeminiProvider, FileCache, PostgresDailyGate]:
    """A Gemini provider for `model` whose answers are cached in `cache_dir`. Every real request
    passes the shared daily cap (the same counter as the app)."""
    settings = settings or Settings()  # type: ignore[call-arg]
    api_key = settings.gemini_api_key.get_secret_value()
    cache = FileCache(cache_dir)
    gate = PostgresDailyGate(settings.database_url, settings.ai_max_requests_per_day)
    provider = GeminiProvider(
        api_key=api_key or "missing-key",  # a full cache needs no key
        model=model,
        assistant_model=model,
        timeout_seconds=timeout_seconds or settings.ai_timeout_seconds,
        gate=gate,
        response_cache=cache,
        pace_seconds=pace_seconds,
    )
    return provider, cache, gate


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

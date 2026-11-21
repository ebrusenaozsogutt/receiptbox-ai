"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, documents, extract, health, observations, transactions
from app.core.config import Settings, get_settings
from app.core.database import create_engine, create_session_factory
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, install_access_log
from app.security.rate_limit import SlidingWindowRateLimiter
from app.services.retention import null_old_masked_text
from app.storage.backend import LocalStorage

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    engine = create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Spec 5.5: masked screenshot text older than 30 days is removed. A failure here must
        # never stop the server from starting.
        try:
            async with app.state.session_factory() as session:
                await null_old_masked_text(session)
        except Exception:  # noqa: BLE001
            logging.getLogger("receiptbox.retention").warning("retention_cleanup_failed")
        yield
        await engine.dispose()

    app = FastAPI(title="ReceiptBox AI", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    # 5 login attempts per minute per e-mail + IP (spec P02). In-process, reset on restart.
    app.state.login_limiter = SlidingWindowRateLimiter(limit=5, window_seconds=60)

    # Spec 15.2 / P05: 20 extractions per minute per user. The provider is created lazily.
    app.state.extract_limiter = SlidingWindowRateLimiter(limit=20, window_seconds=60)
    app.state.ai_provider = None
    app.state.storage = LocalStorage(settings.storage_root)

    register_error_handlers(app)
    install_access_log(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(extract.router, prefix=API_PREFIX)
    app.include_router(documents.router, prefix=API_PREFIX)
    app.include_router(observations.router, prefix=API_PREFIX)
    app.include_router(transactions.router, prefix=API_PREFIX)
    return app


app = create_app()

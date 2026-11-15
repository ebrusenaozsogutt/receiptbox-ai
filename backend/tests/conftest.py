import os
from collections.abc import AsyncIterator

# Must be set before app.main is imported: it builds the default app at import time.
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")

import pytest_asyncio  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def make_test_settings(**overrides: object) -> Settings:
    base = Settings()  # type: ignore[call-arg]
    return base.model_copy(update={"database_url": base.test_database_url, **overrides})


@pytest_asyncio.fixture
async def app() -> AsyncIterator[FastAPI]:
    test_app = create_app(make_test_settings())
    yield test_app
    await test_app.state.engine.dispose()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # raise_app_exceptions=False: let our 500 handler answer instead of re-raising in tests.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client

import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

# Must be set before app.main is imported: it builds the default app at import time.
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-not-for-production-use")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.database import create_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import User  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def make_test_settings(**overrides: object) -> Settings:
    base = Settings()  # type: ignore[call-arg]
    return base.model_copy(update={"database_url": base.test_database_url, **overrides})


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    # Do not let Alembic reconfigure logging in the middle of a pytest run.
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """The dedicated test database, rebuilt from scratch with `alembic upgrade head`.

    Sync on purpose: Alembic's async env.py calls asyncio.run(), which needs no running loop.
    """
    url = make_test_settings().database_url
    config = alembic_config(url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return url


@pytest_asyncio.fixture
async def db_session(migrated_database: str) -> AsyncIterator[AsyncSession]:
    """A session whose changes are rolled back after each test (savepoint-based)."""
    engine = create_engine(migrated_database)
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await outer_transaction.rollback()
    await engine.dispose()


async def create_user(session: AsyncSession, label: str = "user") -> User:
    """Insert a user with a unique, lowercase e-mail (a placeholder password hash)."""
    user = User(email=f"{label}-{uuid.uuid4().hex[:8]}@example.test", password_hash="not-a-hash")
    session.add(user)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def app() -> AsyncIterator[FastAPI]:
    test_app = create_app(make_test_settings())
    yield test_app
    await test_app.state.engine.dispose()


@pytest.fixture
def storage_root() -> Iterator[Path]:
    """A throw-away STORAGE_ROOT. (pytest's tmp_path fails on this PC: the Windows user name
    contains non-ASCII letters and pytest's own temp folder is not accessible.)"""
    with tempfile.TemporaryDirectory(prefix="receiptbox-test-") as directory:
        yield Path(directory)


@pytest_asyncio.fixture
async def api_app(migrated_database: str, storage_root: Path) -> AsyncIterator[FastAPI]:
    """An app on the migrated test database whose requests really commit.

    Unlike db_session (rolled back), API requests commit, so every user is deleted afterwards
    (DELETE, not TRUNCATE ... CASCADE: that would also wipe the seeded global aliases).
    Files go to a temporary STORAGE_ROOT.
    """
    test_app = create_app(make_test_settings(storage_root=str(storage_root)))
    yield test_app
    async with test_app.state.session_factory() as session:
        await session.execute(text("DELETE FROM users"))
        await session.commit()
    await test_app.state.engine.dispose()


@pytest_asyncio.fixture
async def api_client(api_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=api_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # raise_app_exceptions=False: let our 500 handler answer instead of re-raising in tests.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client

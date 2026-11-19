"""`alembic upgrade head` and `alembic downgrade base` both work on the test database."""

import asyncio

from alembic import command
from sqlalchemy import text

from app.core.database import create_engine
from tests.conftest import alembic_config

EXPECTED_TABLE_COUNT = 19  # the spec 6.1 tables, not counting alembic_version


def _fetch(url: str, sql: str) -> list[tuple]:
    async def run() -> list[tuple]:
        engine = create_engine(url)
        try:
            async with engine.connect() as connection:
                return [tuple(row) for row in await connection.execute(text(sql))]
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _tables(url: str) -> set[str]:
    rows = _fetch(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return {row[0] for row in rows}


def test_downgrade_to_base_then_upgrade_to_head(migrated_database: str) -> None:
    config = alembic_config(migrated_database)

    command.downgrade(config, "base")
    assert _tables(migrated_database) == {"alembic_version"}  # nothing else is left behind

    command.upgrade(config, "head")
    tables = _tables(migrated_database)
    assert len(tables - {"alembic_version"}) == EXPECTED_TABLE_COUNT


def test_seed_migration_downgrades_on_its_own(migrated_database: str) -> None:
    config = alembic_config(migrated_database)

    command.downgrade(config, "0001")  # undo only the seed
    assert _fetch(migrated_database, "SELECT count(*) FROM categories") == [(0,)]
    assert _fetch(migrated_database, "SELECT count(*) FROM merchants") == [(0,)]
    assert _fetch(migrated_database, "SELECT count(*) FROM merchant_aliases") == [(0,)]
    assert len(_tables(migrated_database) - {"alembic_version"}) == EXPECTED_TABLE_COUNT

    command.upgrade(config, "head")  # and the seed comes back
    assert _fetch(migrated_database, "SELECT count(*) FROM categories") == [(13,)]


def test_database_is_left_at_head(migrated_database: str) -> None:
    rows = _fetch(migrated_database, "SELECT version_num FROM alembic_version")

    assert rows == [("0003",)]

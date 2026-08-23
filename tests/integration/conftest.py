"""Database fixtures.

Tests run against a real PostgreSQL instance, migrated with alembic - the
same schema production gets, rather than a create_all() approximation that
can silently drift from the migrations.

Every test runs inside a transaction that is rolled back afterwards, so the
suite leaves no residue and tests cannot see each other's rows.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from urllib.parse import quote_plus

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from gym_assistant.config import Settings, get_settings
from gym_assistant.db import create_engine

pytestmark = pytest.mark.integration


def _test_database_name(settings: Settings) -> str:
    """Never the development database - always a sibling ending in _test."""
    name = settings.postgres_db
    return name if name.endswith("_test") else f"{name}_test"


def _async_url(settings: Settings, database: str) -> str:
    password = quote_plus(settings.postgres_password.get_secret_value())
    return (
        f"postgresql+asyncpg://{quote_plus(settings.postgres_user)}:{password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{database}"
    )


async def _prepare(settings: Settings, database: str) -> None:
    admin = await asyncpg.connect(
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database="postgres",
    )
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{database}"')
    finally:
        await admin.close()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Creates the test database once and migrates it to head.

    Deliberately a plain (sync) fixture driving asyncio.run: it sidesteps
    pytest-asyncio's event-loop scoping rules for session fixtures.
    """
    settings = get_settings()
    database = _test_database_name(settings)

    try:
        asyncio.run(_prepare(settings, database))
    except OSError as exc:  # no server reachable
        pytest.skip(f"PostgreSQL is not available: {exc}")

    url = _async_url(settings, database)

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    yield url


@pytest_asyncio.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    created = create_engine(database_url)
    yield created
    await created.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    connection = await engine.connect()
    transaction = await connection.begin()

    factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        # Turns the service layer's commits into savepoint releases, so the
        # outer transaction below can still roll everything back.
        join_transaction_mode="create_savepoint",
    )

    async with factory() as opened:
        yield opened

    await transaction.rollback()
    await connection.close()

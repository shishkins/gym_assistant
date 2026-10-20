"""The migrations build exactly the schema the ORM models describe.

Without this a model and its migration can drift apart and nothing notices
until a query fails in production. Checked once by hand for body_estimates
on 2026-10-20; this makes it permanent.
"""

from __future__ import annotations

from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import AsyncEngine

from gym_assistant.domain.models import Base


async def test_migrated_schema_matches_the_models(engine: AsyncEngine) -> None:
    def diff(connection: Any) -> list[Any]:
        return list(compare_metadata(MigrationContext.configure(connection), Base.metadata))

    async with engine.connect() as connection:
        differences = await connection.run_sync(diff)

    assert differences == [], f"models and migrations disagree: {differences}"

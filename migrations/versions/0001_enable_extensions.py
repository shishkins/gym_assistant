"""Enable PostgreSQL extensions the project relies on.

pg_trgm powers typo-tolerant exercise search (iteration 2). It is created
here, in the very first migration, so every environment - local, CI and
production - is identical from the start.

Revision ID: 0001
Revises:
Create Date: 2026-08-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    # Deliberately not dropped: other objects may depend on it.
    pass

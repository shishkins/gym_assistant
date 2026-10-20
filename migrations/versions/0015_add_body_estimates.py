"""Оценки состава тела по фото прогресса: таблица body_estimates.

Отдельная таблица, а не колонка body_fat_pct в body_measurements: там число,
которое человек ввёл сам (калипер, весы), а здесь чтение модели, и смысл у
него есть только вместе с вилкой, моделью и версией промпта.

Ревизия: 0015
Предыдущая: 0014
Дата: 2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "body_estimates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("measurement_id", sa.BigInteger(), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("photo_file_id", sa.Text(), nullable=False),
        sa.Column("bf_low", sa.Numeric(4, 1), nullable=False),
        sa.Column("bf_likely", sa.Numeric(4, 1), nullable=False),
        sa.Column("bf_high", sa.Numeric(4, 1), nullable=False),
        sa.Column("weight_kg", sa.Numeric(5, 2), nullable=True),
        sa.Column("height_cm", sa.SmallInteger(), nullable=True),
        sa.Column(
            "observations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("limits", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["measurement_id"], ["body_measurements.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "bf_low BETWEEN 3 AND 60 AND bf_high BETWEEN 3 AND 60 "
            "AND bf_low <= bf_likely AND bf_likely <= bf_high",
            name="ck_body_estimates_band",
        ),
    )
    op.create_index("ix_body_estimates_user_measured", "body_estimates", ["user_id", "measured_at"])
    op.create_index("ix_body_estimates_measurement", "body_estimates", ["measurement_id"])


def downgrade() -> None:
    op.drop_table("body_estimates")

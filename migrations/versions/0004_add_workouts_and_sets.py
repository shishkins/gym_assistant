"""Add workouts and sets

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-02 14:43:26.748709
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "workouts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="in_progress", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("perceived_effort", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IS NULL OR status IN ('in_progress', 'completed', 'cancelled')",
            name="ck_workouts_status",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_workouts_finished_after_started",
        ),
        sa.CheckConstraint(
            "perceived_effort IS NULL OR (perceived_effort BETWEEN 1 AND 10)",
            name="ck_workouts_perceived_effort",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workouts_user_started", "workouts", ["user_id", "started_at"], unique=False)
    op.create_index(
        "uq_workouts_one_in_progress",
        "workouts",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )
    op.create_table(
        "workout_sets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workout_id", sa.BigInteger(), nullable=False),
        sa.Column("exercise_id", sa.BigInteger(), nullable=False),
        sa.Column("order_index", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("set_index", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("reps", sa.SmallInteger(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.Column("rpe", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("is_warmup", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "distance_m IS NULL OR distance_m BETWEEN 1 AND 100000", name="ck_sets_distance"
        ),
        sa.CheckConstraint(
            "duration_sec IS NULL OR duration_sec BETWEEN 1 AND 86400", name="ck_sets_duration"
        ),
        sa.CheckConstraint(
            "reps IS NOT NULL OR duration_sec IS NOT NULL OR distance_m IS NOT NULL",
            name="ck_sets_not_empty",
        ),
        sa.CheckConstraint("reps IS NULL OR reps BETWEEN 1 AND 1000", name="ck_sets_reps"),
        sa.CheckConstraint("rpe IS NULL OR rpe BETWEEN 1 AND 10", name="ck_sets_rpe"),
        sa.CheckConstraint(
            "weight_kg IS NULL OR weight_kg BETWEEN 0 AND 1000", name="ck_sets_weight"
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workout_id"], ["workouts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workout_sets_exercise_time",
        "workout_sets",
        ["exercise_id", "performed_at"],
        unique=False,
    )
    op.create_index(
        "ix_workout_sets_workout",
        "workout_sets",
        ["workout_id", "order_index", "set_index"],
        unique=False,
    )


def downgrade() -> None:

    op.drop_index("ix_workout_sets_workout", table_name="workout_sets")
    op.drop_index("ix_workout_sets_exercise_time", table_name="workout_sets")
    op.drop_table("workout_sets")
    op.drop_index(
        "uq_workouts_one_in_progress",
        table_name="workouts",
        postgresql_where=sa.text("status = 'in_progress'"),
    )
    op.drop_index("ix_workouts_user_started", table_name="workouts")
    op.drop_table("workouts")

"""Add users, profiles and body measurements

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23 17:52:26.369708
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("locale", sa.String(length=8), server_default="ru", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)
    op.create_table(
        "body_measurements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("body_fat_pct", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("chest_cm", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("waist_cm", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("hip_cm", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("biceps_cm", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("thigh_cm", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("photo_file_id", sa.Text(), nullable=True),
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
            "body_fat_pct IS NULL OR (body_fat_pct BETWEEN 3 AND 70)",
            name="ck_body_measurements_body_fat_pct",
        ),
        sa.CheckConstraint(
            "weight_kg IS NOT NULL OR body_fat_pct IS NOT NULL OR chest_cm IS NOT NULL OR waist_cm IS NOT NULL OR hip_cm IS NOT NULL OR biceps_cm IS NOT NULL OR thigh_cm IS NOT NULL OR photo_file_id IS NOT NULL",
            name="ck_body_measurements_not_empty",
        ),
        sa.CheckConstraint(
            "weight_kg IS NULL OR (weight_kg BETWEEN 20 AND 400)",
            name="ck_body_measurements_weight_kg",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_body_measurements_user_measured",
        "body_measurements",
        ["user_id", "measured_at"],
        unique=False,
    )
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("sex", sa.String(length=16), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("height_cm", sa.SmallInteger(), nullable=True),
        sa.Column("goal", sa.String(length=16), nullable=True),
        sa.Column("experience_level", sa.String(length=16), nullable=True),
        sa.Column("weekly_target", sa.SmallInteger(), nullable=True),
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
            "experience_level IS NULL OR experience_level IN ('beginner', 'intermediate', 'advanced')",
            name="ck_user_profiles_experience_level",
        ),
        sa.CheckConstraint(
            "goal IS NULL OR goal IN ('mass', 'strength', 'cut', 'health')",
            name="ck_user_profiles_goal",
        ),
        sa.CheckConstraint("sex IS NULL OR sex IN ('male', 'female')", name="ck_user_profiles_sex"),
        sa.CheckConstraint(
            "height_cm IS NULL OR (height_cm BETWEEN 100 AND 250)",
            name="ck_user_profiles_height_cm",
        ),
        sa.CheckConstraint(
            "weekly_target IS NULL OR (weekly_target BETWEEN 1 AND 14)",
            name="ck_user_profiles_weekly_target",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:

    op.drop_table("user_profiles")
    op.drop_index("ix_body_measurements_user_measured", table_name="body_measurements")
    op.drop_table("body_measurements")
    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")

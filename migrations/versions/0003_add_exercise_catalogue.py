"""Add exercise catalogue and seed it from seeds/exercises.yaml

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-02 12:44:46.908844
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence

import sqlalchemy as sa
import yaml
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "muscle_groups",
        sa.Column("id", sa.SmallInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name_ru", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "exercises",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name_ru", sa.Text(), nullable=False),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("primary_muscle_group_id", sa.SmallInteger(), nullable=False),
        sa.Column("equipment", sa.String(length=16), nullable=False),
        sa.Column("exercise_type", sa.String(length=20), nullable=False),
        sa.Column("is_compound", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("technique_tips", sa.Text(), nullable=True),
        sa.Column("common_mistakes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "equipment IS NULL OR equipment IN ('barbell', 'dumbbell', 'machine', 'cable', 'bodyweight', 'kettlebell', 'other')",
            name="ck_exercises_equipment",
        ),
        sa.CheckConstraint(
            "exercise_type IS NULL OR exercise_type IN ('weight_reps', 'bodyweight_reps', 'time', 'distance')",
            name="ck_exercises_exercise_type",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["primary_muscle_group_id"], ["muscle_groups.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exercises_owner", "exercises", ["owner_user_id"], unique=False)
    op.create_index(
        "ix_exercises_aliases", "exercises", ["aliases"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_exercises_name_trgm",
        "exercises",
        ["name_ru"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_ru": "gin_trgm_ops"},
    )
    op.create_index(
        "uq_exercises_owner_slug",
        "exercises",
        [sa.literal_column("COALESCE(owner_user_id, 0)"), "slug"],
        unique=True,
    )
    op.create_table(
        "exercise_secondary_muscles",
        sa.Column("exercise_id", sa.BigInteger(), nullable=False),
        sa.Column("muscle_group_id", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["muscle_group_id"], ["muscle_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("exercise_id", "muscle_group_id"),
    )
    op.create_table(
        "user_exercise_prefs",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("exercise_id", sa.BigInteger(), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_favourite", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "exercise_id"),
    )

    _seed(op.get_bind())


def downgrade() -> None:

    op.drop_table("user_exercise_prefs")
    op.drop_table("exercise_secondary_muscles")
    op.drop_index("uq_exercises_owner_slug", table_name="exercises")
    op.drop_index("ix_exercises_name_trgm", table_name="exercises")
    op.drop_index("ix_exercises_aliases", table_name="exercises")
    op.drop_index("ix_exercises_owner", table_name="exercises")
    op.drop_table("exercises")
    op.drop_table("muscle_groups")


SEED_FILE = pathlib.Path(__file__).resolve().parents[2] / "seeds" / "exercises.yaml"


def _seed(bind: sa.engine.Connection) -> None:
    """Loads the shipped catalogue.

    Idempotent by design: it inserts only what is missing and never updates
    an existing row, so a re-run cannot undo edits made in the database.
    Later catalogue changes get their own migration rather than mutating
    this one.
    """
    data = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8"))

    for group in data["muscle_groups"]:
        bind.execute(
            sa.text(
                "INSERT INTO muscle_groups (code, name_ru, sort_order)"
                " VALUES (:code, :name_ru, :sort_order)"
                " ON CONFLICT (code) DO NOTHING"
            ),
            group,
        )

    group_ids = dict(bind.execute(sa.text("SELECT code, id FROM muscle_groups")).all())

    for item in data["exercises"]:
        exercise_id = bind.execute(
            sa.text("SELECT id FROM exercises WHERE owner_user_id IS NULL AND slug = :slug"),
            {"slug": item["slug"]},
        ).scalar()

        if exercise_id is None:
            exercise_id = bind.execute(
                sa.text(
                    "INSERT INTO exercises ("
                    " slug, name_ru, aliases, primary_muscle_group_id, equipment,"
                    " exercise_type, is_compound, video_url, technique_tips, common_mistakes"
                    ") VALUES ("
                    " :slug, :name_ru, :aliases, :primary_id, :equipment,"
                    " :exercise_type, :is_compound, :video_url, :tips, :mistakes"
                    ") RETURNING id"
                ),
                {
                    "slug": item["slug"],
                    "name_ru": item["name_ru"],
                    "aliases": item["aliases"],
                    "primary_id": group_ids[item["primary"]],
                    "equipment": item["equipment"],
                    "exercise_type": item["type"],
                    "is_compound": item["compound"],
                    "video_url": item.get("video_url") or None,
                    "tips": (item.get("tips") or "").strip() or None,
                    "mistakes": (item.get("mistakes") or "").strip() or None,
                },
            ).scalar_one()

        for code in item.get("secondary") or []:
            bind.execute(
                sa.text(
                    "INSERT INTO exercise_secondary_muscles (exercise_id, muscle_group_id)"
                    " VALUES (:exercise_id, :muscle_group_id)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"exercise_id": exercise_id, "muscle_group_id": group_ids[code]},
            )

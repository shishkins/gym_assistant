"""Add cardio and more triceps work to the catalogue.

Data only: no schema change. The loader is a copy of the one in 0003 rather
than an import of application code - a migration is a snapshot, and code it
imports will keep evolving underneath it.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-02
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence

import sqlalchemy as sa
import yaml
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_FILE = pathlib.Path(__file__).resolve().parents[2] / "seeds" / "exercises.yaml"

# Everything this revision introduces. Named explicitly so the downgrade can
# remove exactly what was added and nothing a user has since logged against.
ADDED_SLUGS = (
    "rope_pushdown",
    "overhead_triceps_extension",
    "bench_dips",
    "treadmill_run",
    "stationary_bike",
    "rowing_machine",
    "elliptical",
    "jump_rope",
)
ADDED_GROUPS = ("cardio",)


def upgrade() -> None:
    _seed(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    # Only the system copies: a personal exercise with the same slug belongs
    # to its owner and is none of this migration's business.
    bind.execute(
        sa.text("DELETE FROM exercises WHERE owner_user_id IS NULL AND slug = ANY(:slugs)"),
        {"slugs": list(ADDED_SLUGS)},
    )
    bind.execute(
        sa.text("DELETE FROM muscle_groups WHERE code = ANY(:codes)"),
        {"codes": list(ADDED_GROUPS)},
    )


def _seed(bind: sa.engine.Connection) -> None:
    """Inserts what is missing and never updates what is already there."""
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

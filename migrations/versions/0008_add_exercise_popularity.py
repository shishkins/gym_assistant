"""Насколько упражнение ходовое.

Расширение до 167 позиций вскрыло то, чего каталог из 49 не показывал:
когда совпадений много, порядок решался длиной названия. Запрос
"приседанья" переставал находить приседания со штангой - "Гакк-приседания"
короче и выигрывал тай-брейк. "планко" выдавало плавание раньше планки.

Нужен признак "это базовое движение, а это его вариация". Он берётся не с
потолка: первые 49 упражнений отбирались вручную как тот минимум, вокруг
которого строится тренировка. Они и есть ядро.

Меньше значит выше. Свои упражнения пользователя получают 50 - наравне с
вариациями, но ниже базы, потому что в поиске по группе мышц человек чаще
ищет базовое движение, а своё знает по имени.

Ревизия: 0008
Предыдущая: 0007
Дата: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Ядро: то, что было в справочнике до расширения.
CORE_SLUGS = (
    "barbell_curl",
    "barbell_row",
    "bench_dips",
    "bench_press",
    "bent_over_lateral_raise",
    "bulgarian_split_squat",
    "cable_crossover",
    "calf_raise",
    "close_grip_bench_press",
    "crunch",
    "deadlift",
    "dips",
    "dumbbell_bench_press",
    "dumbbell_curl",
    "dumbbell_fly",
    "dumbbell_row",
    "dumbbell_shoulder_press",
    "elliptical",
    "farmers_walk",
    "front_squat",
    "hammer_curl",
    "hanging_leg_raise",
    "hip_thrust",
    "hyperextension",
    "incline_bench_press",
    "jump_rope",
    "lat_pulldown",
    "lateral_raise",
    "leg_curl",
    "leg_extension",
    "leg_press",
    "lunges",
    "overhead_press",
    "overhead_triceps_extension",
    "plank",
    "pull_up",
    "push_up",
    "romanian_deadlift",
    "rope_pushdown",
    "rowing_machine",
    "russian_twist",
    "seated_cable_row",
    "shrug",
    "skull_crusher",
    "squat",
    "stationary_bike",
    "treadmill_run",
    "triceps_pushdown",
    "upright_row",
)


def upgrade() -> None:
    op.add_column(
        "exercises",
        sa.Column("popularity", sa.SmallInteger(), nullable=False, server_default="50"),
    )
    op.get_bind().execute(
        sa.text(
            "UPDATE exercises SET popularity = 10"
            " WHERE owner_user_id IS NULL AND slug = ANY(:slugs)"
        ),
        {"slugs": list(CORE_SLUGS)},
    )
    # Индекс под сортировку: она участвует в каждом поиске.
    op.create_index("ix_exercises_popularity", "exercises", ["popularity"])


def downgrade() -> None:
    op.drop_index("ix_exercises_popularity", table_name="exercises")
    op.drop_column("exercises", "popularity")

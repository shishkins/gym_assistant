"""Расширение справочника со 49 до 167 упражнений.

Данные, без изменения схемы. Загрузчик - копия того, что в 0003 и 0005:
миграция это снимок, а код приложения под ней продолжит меняться.

Зачем: на 49 упражнениях в самой большой группе было восемь позиций, в
группе "Грудь" - семь. Пагинация в справочнике при этом работала и была
покрыта тестами, но увидеть её было невозможно - страница вмещает восемь.
Пользователь решил, что пагинации нет, и оказался прав по сути: списка,
который стоило бы листать, действительно не существовало.

Ревизия: 0007
Предыдущая: 0006
Дата: 2026-09-03
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence

import sqlalchemy as sa
import yaml
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_FILE = pathlib.Path(__file__).resolve().parents[2] / "seeds" / "exercises.yaml"

# Всё, что добавляет эта ревизия. Перечислено явно, чтобы downgrade удалил
# ровно это и не тронул то, что пользователь успел записать.
ADDED_SLUGS = (
    "decline_bench_press",
    "incline_dumbbell_press",
    "incline_dumbbell_fly",
    "machine_chest_press",
    "pec_deck",
    "cable_fly_low",
    "cable_fly_high",
    "dumbbell_pullover",
    "floor_press",
    "svend_press",
    "incline_push_up",
    "decline_push_up",
    "t_bar_row",
    "chest_supported_row",
    "pendlay_row",
    "chin_up",
    "wide_grip_pull_up",
    "neutral_grip_pulldown",
    "straight_arm_pulldown",
    "one_arm_cable_row",
    "machine_row",
    "rack_pull",
    "sumo_deadlift",
    "good_morning",
    "face_pull",
    "inverted_row",
    "single_arm_dumbbell_row_bench",
    "hyperextension_reverse",
    "kettlebell_swing",
    "arnold_press",
    "machine_shoulder_press",
    "cable_lateral_raise",
    "front_raise",
    "reverse_pec_deck",
    "cable_rear_delt_fly",
    "landmine_press",
    "push_press",
    "behind_neck_press",
    "dumbbell_shrug",
    "cuban_rotation",
    "pike_push_up",
    "preacher_curl",
    "incline_dumbbell_curl",
    "concentration_curl",
    "cable_curl",
    "reverse_curl",
    "spider_curl",
    "cable_hammer_curl",
    "machine_curl",
    "zottman_curl",
    "chin_up_weighted",
    "dumbbell_kickback",
    "cable_overhead_extension",
    "reverse_grip_pushdown",
    "jm_press",
    "diamond_push_up",
    "machine_triceps_extension",
    "dumbbell_skull_crusher",
    "ring_dips",
    "bench_press_board",
    "wrist_curl",
    "reverse_wrist_curl",
    "plate_pinch",
    "dead_hang",
    "wrist_roller",
    "hack_squat",
    "goblet_squat",
    "box_squat",
    "pause_squat",
    "sissy_squat",
    "step_up",
    "walking_lunges",
    "reverse_lunge",
    "leg_press_narrow",
    "front_rack_lunge",
    "wall_sit",
    "belt_squat",
    "seated_leg_curl",
    "standing_leg_curl",
    "nordic_curl",
    "stiff_leg_deadlift",
    "single_leg_rdl",
    "glute_ham_raise",
    "cable_pull_through",
    "kettlebell_deadlift",
    "glute_bridge",
    "cable_kickback",
    "abduction_machine",
    "adduction_machine",
    "frog_pump",
    "single_leg_hip_thrust",
    "banded_lateral_walk",
    "sumo_squat",
    "step_down",
    "seated_calf_raise",
    "standing_calf_raise_machine",
    "leg_press_calf_raise",
    "donkey_calf_raise",
    "single_leg_calf_raise",
    "side_plank",
    "ab_wheel",
    "cable_crunch",
    "leg_raise_lying",
    "bicycle_crunch",
    "dead_bug",
    "pallof_press",
    "hollow_hold",
    "woodchopper",
    "sit_up",
    "suitcase_carry",
    "hanging_knee_raise",
    "incline_walk",
    "stair_climber",
    "assault_bike",
    "sled_push",
    "burpee",
    "swimming",
    "walking",
)

# Загрузчик никогда не трогает уже существующие строки - это защита от
# затирания правок, сделанных руками. Но этой записи нужны новые синонимы:
# "жим сидя гантели" и "жим гантелей над головой сидя" переехали сюда из
# дубля, который я по невнимательности завёл отдельным упражнением.
ALIAS_TOPUP = {
    "dumbbell_shoulder_press": [
        "жим гантелей сидя",
        "жим на плечи",
        "дб жим плечи",
        "жим сидя гантели",
        "жим гантелей над головой сидя",
    ],
}


def upgrade() -> None:
    bind = op.get_bind()
    _seed(bind)
    for slug, aliases in ALIAS_TOPUP.items():
        bind.execute(
            sa.text(
                "UPDATE exercises SET aliases = :aliases"
                " WHERE owner_user_id IS NULL AND slug = :slug"
            ),
            {"slug": slug, "aliases": aliases},
        )


def downgrade() -> None:
    bind = op.get_bind()
    # Только системные копии: личное упражнение с тем же slug принадлежит
    # своему владельцу и этой миграции не касается.
    bind.execute(
        sa.text("DELETE FROM exercises WHERE owner_user_id IS NULL AND slug = ANY(:slugs)"),
        {"slugs": list(ADDED_SLUGS)},
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

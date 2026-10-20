"""Убрать дневник питания: таблицы meals и meal_items.

Подсчёт калорий по фото убран целиком по решению пользователя: на его
собственной еде модель ошибалась слишком сильно, чтобы цифрам можно было
доверять. Единственное настоящее измерение точности за всё время — боул из
доставки с калорийностью на экране — показало завышение на 69% по одной
фотографии. Скриншот доставки это исправлял, но дневник, которому нужна
подсказка на каждом приёме пищи, перестаёт быть быстрее, чем вбить цифры
руками.

Данных здесь нет: база на новом сервере поднята 2026-10-20 с нуля, и в эти
таблицы никто не успел записать ни строки. Поэтому миграция просто удаляет
их, без выгрузки.

Откат восстанавливает таблицы в том виде, в каком их оставили 0012 и 0013, —
скопированным DDL, а не импортом тех миграций: миграция должна описывать
схему на свой момент и не зависеть от того, что потом станет с соседними
файлами.

Ревизия: 0014
Предыдущая: 0013
Дата: 2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Children first; dropping the table takes its indexes with it.
    op.drop_table("meal_items")
    op.drop_table("meals")


def downgrade() -> None:
    op.create_table(
        "meals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("eaten_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("photo_file_id", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("kcal", sa.Numeric(7, 1), nullable=False, server_default="0"),
        sa.Column("protein_g", sa.Numeric(6, 1), nullable=False, server_default="0"),
        sa.Column("fat_g", sa.Numeric(6, 1), nullable=False, server_default="0"),
        sa.Column("carb_g", sa.Numeric(6, 1), nullable=False, server_default="0"),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("first_pass", postgresql.JSONB(), nullable=True),
        sa.Column("hints", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kcal >= 0 AND kcal <= 20000", name="ck_meals_kcal"),
    )
    op.create_index("ix_meals_user_eaten", "meals", ["user_id", "eaten_at"])

    op.create_table(
        "meal_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("meal_id", sa.BigInteger(), nullable=False),
        sa.Column("order_index", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("grams", sa.Numeric(7, 1), nullable=False),
        sa.Column("grams_low", sa.Numeric(7, 1), nullable=True),
        sa.Column("grams_high", sa.Numeric(7, 1), nullable=True),
        sa.Column("kcal_100g", sa.Numeric(6, 1), nullable=False),
        sa.Column("protein_100g", sa.Numeric(5, 1), nullable=False),
        sa.Column("fat_100g", sa.Numeric(5, 1), nullable=False),
        sa.Column("carb_100g", sa.Numeric(5, 1), nullable=False),
        sa.Column("grams_source", sa.Text(), nullable=False, server_default="model"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["meal_id"], ["meals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("grams > 0 AND grams <= 5000", name="ck_meal_items_grams"),
        sa.CheckConstraint("kcal_100g >= 0 AND kcal_100g <= 900", name="ck_meal_items_kcal"),
        sa.CheckConstraint("grams_source IN ('model', 'user')", name="ck_meal_items_grams_source"),
    )
    op.create_index("ix_meal_items_meal", "meal_items", ["meal_id", "order_index"])
    op.execute(
        "CREATE INDEX ix_meal_items_name_trgm ON meal_items USING gin (lower(name) gin_trgm_ops)"
    )

"""Дневник питания по фото: приёмы пищи и позиции в них.

Отдельного справочника еды здесь нет, и это сознательно. В спеке он был, но
замер показал, что модель каждый раз называет одно и то же блюдо по-новому
(«круассан с ветчиной и сыром», «круассан с начинкой», «сэндвич с ветчиной
и сыром»), а закрытый список не годится: еда — открытое множество, в отличие
от упражнений. Роль справочника играет собственная история человека: что он
уже ел, то и подсказывается модели, и она называет это так же. Позиции и есть
история, поэтому отдельная таблица пока не нужна.

Состав на 100 г лежит СНИМКОМ в позиции, а не ссылкой. Приём пищи, записанный
месяц назад, обязан читаться тем, чем был записан.

Итоги денормализованы в meals: их суммирует каждый отчёт, и считать их
джойном на каждом графике незачем.

Вилка граммов хранится целиком. Модель отдаёт low/likely/high, и ширина этой
вилки — единственный честный признак её неуверенности: замер показал, что
ширину она оценивает верно (32–46% при реальном разбросе 7–30%), хотя центр
держит плохо. Показываем одно число, но храним все три — по ним потом видно,
где спрашивать подтверждение, а где не тревожить.

Ревизия: 0012
Предыдущая: 0011
Дата: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("eaten_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("photo_file_id", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        # Totals, summed from the items at write time.
        sa.Column("kcal", sa.Numeric(7, 1), nullable=False, server_default="0"),
        sa.Column("protein_g", sa.Numeric(6, 1), nullable=False, server_default="0"),
        sa.Column("fat_g", sa.Numeric(6, 1), nullable=False, server_default="0"),
        sa.Column("carb_g", sa.Numeric(6, 1), nullable=False, server_default="0"),
        # Which model and which prompt produced this. Without both, a shift in
        # either silently rewrites the meaning of the whole history.
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
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
        # The band, not just the point. grams is what counts; the bounds are
        # what say how much to trust it.
        sa.Column("grams", sa.Numeric(7, 1), nullable=False),
        sa.Column("grams_low", sa.Numeric(7, 1), nullable=True),
        sa.Column("grams_high", sa.Numeric(7, 1), nullable=True),
        # Snapshot per 100 g, never a reference.
        sa.Column("kcal_100g", sa.Numeric(6, 1), nullable=False),
        sa.Column("protein_100g", sa.Numeric(5, 1), nullable=False),
        sa.Column("fat_100g", sa.Numeric(5, 1), nullable=False),
        sa.Column("carb_100g", sa.Numeric(5, 1), nullable=False),
        # model | user. A meal the person corrected by hand is a calibration
        # point: over time these are what show how far the model drifts.
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
    # What the person has eaten before, for the prompt to anchor names to.
    # Trigram, like the exercise search: "круассан с начинкой" has to find
    # "круассан с ветчиной и сыром".
    op.execute(
        "CREATE INDEX ix_meal_items_name_trgm ON meal_items USING gin (lower(name) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_table("meal_items")
    op.drop_table("meals")

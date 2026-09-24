"""Килограммы или фунты — только для показа.

В базе вес остаётся в килограммах при любом значении этого поля. Настройка
меняет две вещи: как разбирается введённое число и как показывается
хранимое. Если писать в базу то, что человек набрал в своей системе,
история превратится в смесь двух единиц, и смысл каждой строки будет
зависеть от настройки, действовавшей на момент записи, — а это
необратимо.

Поле живёт в users рядом с locale, а не в профиле: это предпочтение показа,
а не свойство тела.

Ревизия: 0010
Предыдущая: 0009
Дата: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "units",
            sa.String(length=16),
            nullable=False,
            server_default="metric",
        ),
    )
    op.create_check_constraint("ck_users_units", "users", "units IN ('metric', 'imperial')")


def downgrade() -> None:
    op.drop_constraint("ck_users_units", "users", type_="check")
    op.drop_column("users", "units")

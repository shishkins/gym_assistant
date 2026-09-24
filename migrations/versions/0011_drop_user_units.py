"""Убрать users.units — показ везде в килограммах.

Колонка прожила один день. 0010 завела её под настройку «показывать в
фунтах», но после проверки в зале требование изменилось: килограммы
показываются всегда, а фунты нужны только как способ набрать число во время
упражнения. Такой режим живёт в состоянии диалога и не переживает смену
упражнения — хранить его в базе незачем.

Потери данных нет: у всех пользователей там стоит 'metric', другого значения
никто выставить не успел. Откат возвращает колонку с тем же умолчанием.

Ревизия: 0011
Предыдущая: 0010
Дата: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_users_units", "users", type_="check")
    op.drop_column("users", "units")


def downgrade() -> None:
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

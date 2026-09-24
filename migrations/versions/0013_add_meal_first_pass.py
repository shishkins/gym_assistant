"""Сохранять первую оценку модели отдельно от исправленной.

Пользователь взялся измерять порции и прикладывать скриншоты доставки, чтобы
по ним потом посчитать ошибку модели. Без этой миграции его работа пропала
бы: в meals лежит только ИТОГОВЫЙ разбор, уже исправленный подсказкой, а
измеряемая величина — это то, что модель сказала по одной фотографии, до
всякой помощи.

first_pass — снимок первого прочтения: позиции, граммы, состав на 100 г.
hints — чем уточняли: второе фото, текст, ответ на вопрос модели.

Отсюда считается то, чего не даёт никакой повторный прогон одного и того же
фото: прогоны меряют, согласна ли модель сама с собой, а разница между
first_pass и подтверждённым итогом меряет, была ли она права.

JSONB, а не отдельная таблица: это журнал для анализа, а не то, по чему
строятся отчёты. Запрашивать его будут раз в месяц одной выборкой.

Ревизия: 0013
Предыдущая: 0012
Дата: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("meals", sa.Column("first_pass", postgresql.JSONB(), nullable=True))
    op.add_column("meals", sa.Column("hints", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("meals", "hints")
    op.drop_column("meals", "first_pass")

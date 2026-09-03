"""Roles: who may use the paid parts of the bot.

One row per user, and only for users who are anything other than an ordinary
one - the absence of a row means ``regular_user``. That keeps the table small
enough to read by eye and means opening the bot to a new person costs no
write at all.

``expires_at`` is checked when the role is read rather than by a scheduled
job. A subscription that has run out stops working because the clock moved,
not because a cron fired.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_access",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("granted_by_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
            "role IS NULL OR role IN ('regular_user', 'subscription_user', 'admin')",
            name="ck_user_access_role",
        ),
        # The grant outlives the admin who made it: losing the audit trail is
        # worse than a dangling name.
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    # Answers "whose subscription is about to run out" without a scan.
    op.create_index("ix_user_access_expires_at", "user_access", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_user_access_expires_at", table_name="user_access")
    op.drop_table("user_access")

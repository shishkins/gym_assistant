"""Where the conversation lives between messages.

The Messages API is stateless: each request carries the whole exchange. This
keeps that exchange in Postgres rather than Redis, because a discussion about
someone's training is worth surviving a deploy - and deploys happen on every
push.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import AiMessage, AiSession

log = structlog.get_logger(__name__)

# A conversation nobody has touched for this long is over; the next question
# starts fresh instead of dragging yesterday's context - and its cost - along.
IDLE_HOURS = 6

# Turns kept when replaying history. Each one is resent in full on every
# request, so this is a direct multiplier on the bill.
MAX_TURNS = 12


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active(self, user_id: int, *, now: datetime | None = None) -> AiSession:
        """The live conversation, starting one if there is none or it is stale."""
        now = now or datetime.now(UTC)
        found = await self._session.scalar(
            select(AiSession).where(AiSession.user_id == user_id, AiSession.is_active)
        )

        if found is not None:
            if found.last_used_at >= now - timedelta(hours=IDLE_HOURS):
                found.last_used_at = now
                return found
            found.is_active = False
            await self._session.flush()

        started = AiSession(user_id=user_id, last_used_at=now)
        self._session.add(started)
        await self._session.flush()
        return started

    async def history(self, session_id: int) -> list[dict[str, Any]]:
        """Prior turns in API shape, oldest first, trimmed to MAX_TURNS.

        Trimmed from the front, and never leaving a tool_use without its
        result: a dangling tool_use is rejected by the API, so the cut lands
        on a user turn that starts a clean exchange.
        """
        rows = list(
            await self._session.scalars(
                select(AiMessage).where(AiMessage.session_id == session_id).order_by(AiMessage.id)
            )
        )
        turns = [{"role": row.role, "content": row.content} for row in rows]
        if len(turns) <= MAX_TURNS:
            return turns

        cut = len(turns) - MAX_TURNS
        while cut < len(turns) and not _is_plain_user_turn(turns[cut]):
            cut += 1
        return turns[cut:]

    async def append(self, session_id: int, turns: list[dict[str, Any]]) -> None:
        for turn in turns:
            self._session.add(
                AiMessage(
                    session_id=session_id,
                    role=str(turn["role"]),
                    content=turn["content"],
                )
            )
        await self._session.flush()

    async def reset(self, user_id: int) -> bool:
        """Ends the live conversation. Returns whether there was one."""
        result = await self._session.execute(
            update(AiSession)
            .where(AiSession.user_id == user_id, AiSession.is_active)
            .values(is_active=False)
            .returning(AiSession.id)
        )
        await self._session.flush()
        return result.first() is not None


def _is_plain_user_turn(turn: dict[str, Any]) -> bool:
    """A user turn that is a question, not a batch of tool results."""
    if turn.get("role") != "user":
        return False
    content = turn.get("content")
    if isinstance(content, str):
        return True
    return not any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content or []
    )

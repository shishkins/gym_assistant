"""The hard gate: may this person talk to the bot at all.

Distinct from roles. Roles decide which *features* a user gets and live in
the database; this decides whether the bot answers at all, and lives in the
environment so that closing the bot never depends on a working database.

**An empty ``ALLOWED_TELEGRAM_IDS`` means the bot is open to everyone**, who
then arrive as ordinary users. Set it to close the bot down again - during a
rollout, or if it ever gets abused.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from gym_assistant.bot.texts import ru

log = structlog.get_logger(__name__)


class WhitelistMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: frozenset[int]) -> None:
        self._allowed_ids = allowed_ids
        if not allowed_ids:
            log.info("whitelist_open", hint="ALLOWED_TELEGRAM_IDS is empty - the bot is public")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None:
            # Service updates without an author (e.g. channel posts) are ignored.
            return None

        if not self._allowed_ids or user.id in self._allowed_ids:
            return await handler(event, data)

        log.info("access_denied", user_id=user.id, username=user.username)
        await self._reject(event, user.id)
        return None

    @staticmethod
    async def _reject(event: TelegramObject, user_id: int) -> None:
        if isinstance(event, Message):
            await event.answer(ru.ACCESS_DENIED.format(user_id=user_id))
        elif isinstance(event, CallbackQuery):
            await event.answer(
                ru.ACCESS_DENIED_SHORT.format(user_id=user_id),
                show_alert=True,
            )

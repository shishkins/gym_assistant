"""Access control.

The bot is private during the MVP: only Telegram IDs listed in
``ALLOWED_TELEGRAM_IDS`` get through. Everyone else is told their own ID,
which removes the need to hunt for it with a third-party bot.
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
            log.warning(
                "whitelist_empty",
                hint="ALLOWED_TELEGRAM_IDS is not set - every user will be rejected",
            )

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

        if user.id in self._allowed_ids:
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

"""Guarantees a User row exists before any handler runs.

Without this, every handler would need its own "is this user registered
yet" branch. Registration is idempotent and costs one indexed SELECT.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.services import ProfileService


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user: TelegramUser | None = data.get("event_from_user")
        session: AsyncSession | None = data.get("session")

        if telegram_user is not None and session is not None:
            data["user"] = await ProfileService(session).get_or_create_user(
                telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
            )

        return await handler(event, data)

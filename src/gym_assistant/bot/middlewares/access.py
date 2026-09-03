"""Resolves what the current user is allowed to do.

Runs after ``UserMiddleware``, so the row exists and its grant is already
loaded. Puts an ``Access`` into the handler context; nothing here refuses
anything - refusing is the job of the ``RequireRole`` filter, on the routers
that need it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from gym_assistant.domain.models import Role, User
from gym_assistant.domain.services import AccessService

log = structlog.get_logger(__name__)


class AccessMiddleware(BaseMiddleware):
    def __init__(self, admin_telegram_ids: frozenset[int]) -> None:
        self._admin_ids = admin_telegram_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("user")
        session = data.get("session")
        if user is None or session is None:
            return await handler(event, data)

        service = AccessService(session)

        # Self-healing: the owner's admin rights come back the moment they
        # touch the bot. This project wipes its database routinely while
        # testing, and an owner locked out of their own admin commands after
        # every reset would be a footgun with a very long fuse.
        if user.telegram_id in self._admin_ids:
            stored = await service.get(user.id)
            if stored is None or Role(stored.role) is not Role.ADMIN:
                await service.grant(user.id, Role.ADMIN, note="владелец из ADMIN_TELEGRAM_IDS")
                log.info("admin_restored", telegram_id=user.telegram_id)

        data["access"] = await service.for_user(user)
        return await handler(event, data)

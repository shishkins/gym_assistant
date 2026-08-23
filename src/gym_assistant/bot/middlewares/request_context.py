"""Binds request context to structlog and times every update."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from gym_assistant.bot.texts import ru

log = structlog.get_logger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=uuid.uuid4().hex[:12],
            user_id=user.id if user else None,
            update_type=type(event).__name__,
        )

        started = time.perf_counter()
        try:
            return await handler(event, data)
        except Exception:
            log.exception("handler_failed")
            await self._notify_user(event)
            return None
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            log.debug("update_handled", duration_ms=duration_ms)

    @staticmethod
    async def _notify_user(event: TelegramObject) -> None:
        """Never leave a user staring at silence after a crash."""
        answer = getattr(event, "answer", None)
        if answer is None:
            return
        try:
            await answer(ru.UNEXPECTED_ERROR)
        except Exception:
            # Swallowed on purpose: the original failure is the one that matters.
            log.warning("error_notification_failed")

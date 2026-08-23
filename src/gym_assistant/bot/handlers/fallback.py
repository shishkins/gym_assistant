"""Catch-all, registered last.

From iteration 3 the set parser hooks in here, and from iteration 5 the AI
assistant takes over whatever the parser declines.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from gym_assistant.bot.texts import ru

router = Router(name="fallback")


@router.callback_query(F.data)
async def stale_callback(callback: CallbackQuery) -> None:
    """Buttons on old messages should feel inert rather than broken."""
    await callback.answer()


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer(ru.NOT_IMPLEMENTED_YET)

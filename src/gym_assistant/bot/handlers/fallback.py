"""Catch-all for anything not yet handled.

From iteration 3 this is where the set parser hooks in, and from
iteration 5 the AI assistant takes over whatever the parser declines.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from gym_assistant.bot.texts import ru

router = Router(name="fallback")


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer(ru.NOT_IMPLEMENTED_YET)

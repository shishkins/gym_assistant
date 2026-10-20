"""Redrawing a message in place, shared by every inline-keyboard screen."""

from __future__ import annotations

import structlog
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

log = structlog.get_logger(__name__)


async def edit_or_send(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Edits the pressed message; sends a fresh one only if it cannot be edited.

    "Not modified" is the one refusal that means nothing is wrong: the screen
    already shows this. Answering it with a new message is what posted
    another copy of the workout panel on every press of "−" at zero. Any
    other refusal - a message too old to edit, say - still gets a fresh one.
    Network errors are not caught: a second copy is the wrong answer to a
    line that may have delivered the first.
    """
    message = callback.message
    if not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        log.debug("edit_failed", reason=str(exc))
        await message.answer(text, reply_markup=markup)

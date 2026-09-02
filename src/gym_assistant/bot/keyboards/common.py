"""Controls shared by every wizard."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gym_assistant.bot.texts import ru


class CancelCB(CallbackData, prefix="cx"):
    """Leave whatever multi-step action is in progress."""

    scope: str = "any"


def cancel_button(scope: str = "any") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=ru.BTN_CANCEL_ACTION, callback_data=CancelCB(scope=scope).pack()
    )


def with_cancel(builder: InlineKeyboardBuilder, scope: str = "any") -> InlineKeyboardBuilder:
    """Appends a full-width cancel row.

    Every step that waits for input gets one: typing /cancel is a command the
    user has to remember, and a button is the same thing without the recall.
    """
    builder.row(cancel_button(scope))
    return builder


def cancel_keyboard(scope: str = "any") -> InlineKeyboardBuilder:
    return with_cancel(InlineKeyboardBuilder(), scope)

"""The one button that asks for a body-composition estimate."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gym_assistant.bot.texts import ru


class BodyCB(CallbackData, prefix="bd"):
    """Read this photo. The id is checked against the presser on arrival."""

    measurement_id: int


def body_keyboard(measurement_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text=ru.BTN_BODY_ESTIMATE, callback_data=BodyCB(measurement_id=measurement_id))
    return builder

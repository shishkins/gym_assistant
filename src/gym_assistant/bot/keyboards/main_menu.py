"""The one keyboard that reaches every feature.

Telegram's native command list is discoverable but flat and easy to miss;
a single /menu keeps everything one tap away without memorising commands.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gym_assistant.bot.texts import ru


class MainMenuCB(CallbackData, prefix="main"):
    action: str  # exercises | profile | weight | photos | help


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Ordered by how often it gets used, not by when it was built.
    builder.button(text=ru.BTN_MENU_EXERCISES, callback_data=MainMenuCB(action="exercises"))
    builder.button(text=ru.BTN_MENU_WEIGHT, callback_data=MainMenuCB(action="weight"))
    builder.button(text=ru.BTN_MENU_PHOTOS, callback_data=MainMenuCB(action="photos"))
    builder.button(text=ru.BTN_MENU_PROFILE, callback_data=MainMenuCB(action="profile"))
    builder.button(text=ru.BTN_MENU_HELP, callback_data=MainMenuCB(action="help"))
    builder.adjust(1, 2, 2)
    return builder.as_markup()

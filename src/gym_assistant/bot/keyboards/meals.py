"""Buttons under a meal that has not been written down yet.

The card is a proposal, not a record. Everything here is arranged so that
agreeing costs one tap and disagreeing costs one tap - because the portion is
wrong often enough that correcting it has to be as cheap as accepting it.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gym_assistant.bot.texts import ru


class MealCB(CallbackData, prefix="meal"):
    """An action on the breakdown currently on screen."""

    action: str  # save | clarify | discard


class MealScaleCB(CallbackData, prefix="mealx"):
    """Multiply every portion. ``factor`` is a decimal string."""

    factor: str


class MealUndoCB(CallbackData, prefix="mealu"):
    """Remove a meal that was already written."""

    meal_id: int


def meal_card_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Portion first, because that is where the error is. Measured: the model
    # judges what is on the plate far better than how much of it there is.
    builder.row(
        InlineKeyboardButton(text=ru.BTN_MEAL_HALF, callback_data=MealScaleCB(factor="0.5").pack()),
        InlineKeyboardButton(
            text=ru.BTN_MEAL_ONE_AND_HALF, callback_data=MealScaleCB(factor="1.5").pack()
        ),
        InlineKeyboardButton(text=ru.BTN_MEAL_DOUBLE, callback_data=MealScaleCB(factor="2").pack()),
    )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_MEAL_CLARIFY, callback_data=MealCB(action="clarify").pack()
        ),
        InlineKeyboardButton(
            text=ru.BTN_MEAL_DISCARD, callback_data=MealCB(action="discard").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(text=ru.BTN_MEAL_SAVE, callback_data=MealCB(action="save").pack())
    )
    return builder.as_markup()


def meal_saved_keyboard(meal_id: int) -> InlineKeyboardMarkup:
    """One way back out of a tap that was made without looking."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_MEAL_UNDO, callback_data=MealUndoCB(meal_id=meal_id).pack()
        )
    )
    return builder.as_markup()

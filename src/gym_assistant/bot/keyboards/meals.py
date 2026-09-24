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


class MealDayCB(CallbackData, prefix="mday"):
    """A day in the diary. ``offset`` is days back from today, 0 is today."""

    offset: int


class MealWeekCB(CallbackData, prefix="mweek"):
    """The last seven days at a glance."""


class MealPickDeleteCB(CallbackData, prefix="mdel"):
    """Show which meals of ``offset`` can be removed."""

    offset: int


def day_keyboard(offset: int, *, has_meals: bool) -> InlineKeyboardMarkup:
    """Walking backwards is the common direction, so it sits on the left.

    "Позже" appears only when there is a later day to go to: a button that
    does nothing is worse than a missing one, because it has to be tried
    before that is known.
    """
    builder = InlineKeyboardBuilder()
    row = [
        InlineKeyboardButton(
            text=ru.BTN_MEAL_PREV_DAY, callback_data=MealDayCB(offset=offset + 1).pack()
        )
    ]
    if offset > 0:
        row.append(
            InlineKeyboardButton(
                text=ru.BTN_MEAL_NEXT_DAY, callback_data=MealDayCB(offset=offset - 1).pack()
            )
        )
    builder.row(*row)

    builder.row(InlineKeyboardButton(text=ru.BTN_MEAL_WEEK, callback_data=MealWeekCB().pack()))
    if has_meals:
        builder.row(
            InlineKeyboardButton(
                text=ru.BTN_MEAL_DELETE_ONE,
                callback_data=MealPickDeleteCB(offset=offset).pack(),
            )
        )
    return builder.as_markup()


def week_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=ru.BTN_MEAL_TODAY, callback_data=MealDayCB(offset=0).pack())
    )
    return builder.as_markup()


def delete_picker(meals: list[tuple[int, str]], offset: int) -> InlineKeyboardMarkup:
    """One button per meal, and a way back that does not delete anything."""
    builder = InlineKeyboardBuilder()
    for meal_id, label in meals:
        builder.row(
            InlineKeyboardButton(text=label, callback_data=MealUndoCB(meal_id=meal_id).pack())
        )
    builder.row(
        InlineKeyboardButton(text=ru.BTN_CANCEL, callback_data=MealDayCB(offset=offset).pack())
    )
    return builder.as_markup()

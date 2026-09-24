"""Inline keyboards for profile and onboarding."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gym_assistant.bot.texts import ru
from gym_assistant.domain.models import ExperienceLevel, Goal, Sex
from gym_assistant.domain.units import Units
from gym_assistant.domain.units import label as unit_label


class ChoiceCB(CallbackData, prefix="ch"):
    """One option picked for ``field``."""

    field: str
    value: str


class SkipCB(CallbackData, prefix="skip"):
    """Skip the step for ``field``."""

    field: str


class EditCB(CallbackData, prefix="edit"):
    """Edit ``field`` from the profile card."""

    field: str


def _with_skip(builder: InlineKeyboardBuilder, field: str, *, skip: bool) -> InlineKeyboardMarkup:
    """Appends a full-width Skip row. Every onboarding step must be skippable."""
    if skip:
        builder.row(
            InlineKeyboardButton(text=ru.BTN_SKIP, callback_data=SkipCB(field=field).pack())
        )
    return builder.as_markup()


def sex_keyboard(*, skip: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for member, label in ru.SEX_LABELS.items():
        builder.button(text=label, callback_data=ChoiceCB(field="sex", value=member.value))
    builder.adjust(2)
    return _with_skip(builder, "sex", skip=skip)


def goal_keyboard(*, skip: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for member, label in ru.GOAL_LABELS.items():
        builder.button(text=label, callback_data=ChoiceCB(field="goal", value=member.value))
    builder.adjust(2)
    return _with_skip(builder, "goal", skip=skip)


def experience_keyboard(*, skip: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for member, label in ru.EXPERIENCE_LABELS.items():
        builder.button(
            text=label,
            callback_data=ChoiceCB(field="experience_level", value=member.value),
        )
    builder.adjust(3)
    return _with_skip(builder, "experience_level", skip=skip)


def skip_keyboard(field: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=ru.BTN_SKIP, callback_data=SkipCB(field=field))
    return builder.as_markup()


def profile_keyboard(units: Units = Units.METRIC) -> InlineKeyboardMarkup:
    """Every field on the card is a button that edits it."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Пол", callback_data=EditCB(field="sex"))
    builder.button(text="Дата рождения", callback_data=EditCB(field="birth_date"))
    builder.button(text="Рост", callback_data=EditCB(field="height_cm"))
    builder.button(text="Цель", callback_data=EditCB(field="goal"))
    builder.button(text="Опыт", callback_data=EditCB(field="experience_level"))
    builder.button(text="Записать вес", callback_data=EditCB(field="weight"))
    # One button rather than a two-option picker: with exactly two systems the
    # picker would always show one live option and one no-op.
    builder.button(
        text=ru.BTN_UNITS_SWITCH.format(unit=unit_label(other_units(units))),
        callback_data=EditCB(field="units"),
    )
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def other_units(units: Units) -> Units:
    """The system the switch leads to."""
    return Units.METRIC if units is Units.IMPERIAL else Units.IMPERIAL


CHOICE_ENUMS: dict[str, type[Sex] | type[Goal] | type[ExperienceLevel]] = {
    "sex": Sex,
    "goal": Goal,
    "experience_level": ExperienceLevel,
}

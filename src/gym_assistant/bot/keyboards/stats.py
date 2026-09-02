"""Keyboards for the reports."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gym_assistant.bot.texts import ru
from gym_assistant.domain.models import Exercise

# Ordered shortest first, because that is the order a period gets widened in
# when a report says there is not enough data.
PERIODS = ("1m", "3m", "6m", "1y", "all")


class StatsCB(CallbackData, prefix="st"):
    """One report over one period."""

    report: str  # menu | progress | tonnage | volume | weight | records | frequency | summary
    period: str = "3m"


class StatsPeriodCB(CallbackData, prefix="stp"):
    """Period picker, remembering which report to return to."""

    report: str
    period: str


class StatsExerciseCB(CallbackData, prefix="ste"):
    exercise_id: int
    period: str


def menu_keyboard(period: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=ru.BTN_STATS_SUMMARY, callback_data=StatsCB(report="summary", period=period)
    )
    builder.button(
        text=ru.BTN_STATS_PROGRESS, callback_data=StatsCB(report="progress", period=period)
    )
    builder.button(
        text=ru.BTN_STATS_TONNAGE, callback_data=StatsCB(report="tonnage", period=period)
    )
    builder.button(text=ru.BTN_STATS_VOLUME, callback_data=StatsCB(report="volume", period=period))
    builder.button(text=ru.BTN_STATS_WEIGHT, callback_data=StatsCB(report="weight", period=period))
    builder.button(
        text=ru.BTN_STATS_FREQUENCY, callback_data=StatsCB(report="frequency", period=period)
    )
    builder.button(
        text=ru.BTN_STATS_RECORDS, callback_data=StatsCB(report="records", period=period)
    )
    builder.button(text=ru.BTN_STATS_EXPORT, callback_data=StatsCB(report="export", period=period))
    builder.adjust(1, 2, 2, 2, 1)

    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_STATS_PERIOD.format(period=ru.STATS_PERIOD_LABELS[period]),
            callback_data=StatsPeriodCB(report="menu", period=period).pack(),
        )
    )
    return builder.as_markup()


def period_keyboard(report: str, current: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for period in PERIODS:
        label = ru.STATS_PERIOD_LABELS[period]
        builder.button(
            # A tick beats a disabled-looking button: it says which one is on
            # without removing the option to press it again.
            text=f"✓ {label}" if period == current else label,
            callback_data=StatsCB(report=report, period=period),
        )
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def report_keyboard(report: str, period: str) -> InlineKeyboardMarkup:
    """Under a chart: change the period without going back to the menu first."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_STATS_PERIOD.format(period=ru.STATS_PERIOD_LABELS[period]),
            callback_data=StatsPeriodCB(report=report, period=period).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_BACK, callback_data=StatsCB(report="menu", period=period).pack()
        )
    )
    return builder.as_markup()


def exercise_picker(exercises: list[Exercise], period: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for exercise in exercises:
        builder.button(
            text=exercise.name_ru,
            callback_data=StatsExerciseCB(exercise_id=exercise.id, period=period),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_BACK, callback_data=StatsCB(report="menu", period=period).pack()
        )
    )
    return builder.as_markup()

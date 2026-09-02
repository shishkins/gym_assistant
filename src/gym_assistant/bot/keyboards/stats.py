"""Keyboards for the reports."""

from __future__ import annotations

from collections.abc import Callable

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
    page: int = 0


class StatsPeriodCB(CallbackData, prefix="stp"):
    """Period picker, remembering what to return to.

    ``exercise_id`` is what makes the picker return to *this* chart rather
    than to the exercise list: changing the period is a question about the
    same exercise, and asking which one again was the first thing the review
    complained about.
    """

    report: str
    period: str
    exercise_id: int = 0


class StatsExerciseCB(CallbackData, prefix="ste"):
    exercise_id: int
    period: str


class StatsPickCB(CallbackData, prefix="stpick"):
    """A page of the exercise picker."""

    period: str
    page: int = 0


class StatsLastCB(CallbackData, prefix="stl"):
    """The last completed session that included this exercise."""

    exercise_id: int
    period: str


def _noop() -> str:
    return StatsCB(report="noop").pack()


def _pager(
    builder: InlineKeyboardBuilder,
    *,
    page: int,
    total_pages: int,
    callback: Callable[[int], str],
) -> None:
    """The ‹ 2/5 › row, built the same way as the exercise lists build it."""
    if total_pages <= 1:
        return

    def step(delta: int) -> InlineKeyboardButton:
        target = page + delta
        if 0 <= target < total_pages:
            return InlineKeyboardButton(
                text=ru.BTN_PREV_PAGE if delta < 0 else ru.BTN_NEXT_PAGE,
                callback_data=callback(target),
            )
        # A spacer keeps the row width steady as you page.
        return InlineKeyboardButton(text=" ", callback_data=_noop())

    builder.row(
        step(-1),
        InlineKeyboardButton(
            text=ru.PAGE_INDICATOR.format(page=page + 1, total=total_pages),
            callback_data=_noop(),
        ),
        step(1),
    )


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


def period_keyboard(report: str, current: str, exercise_id: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for period in PERIODS:
        label = ru.STATS_PERIOD_LABELS[period]
        # A tick beats a disabled-looking button: it says which one is on
        # without removing the option to press it again.
        text = f"✓ {label}" if period == current else label
        if exercise_id:
            builder.button(
                text=text,
                callback_data=StatsExerciseCB(exercise_id=exercise_id, period=period),
            )
        else:
            builder.button(text=text, callback_data=StatsCB(report=report, period=period))
    builder.adjust(2, 2, 1)

    if exercise_id:
        builder.row(
            InlineKeyboardButton(
                text=ru.BTN_STATS_PICK_OTHER,
                callback_data=StatsPickCB(period=current).pack(),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=ru.BTN_BACK, callback_data=StatsCB(report="menu", period=current).pack()
            )
        )
    return builder.as_markup()


def report_keyboard(report: str, period: str, exercise_id: int = 0) -> InlineKeyboardMarkup:
    """Under a chart: change the period without going back to the menu first."""
    builder = InlineKeyboardBuilder()
    if exercise_id:
        builder.row(
            InlineKeyboardButton(
                text=ru.BTN_STATS_LAST_WITH,
                callback_data=StatsLastCB(exercise_id=exercise_id, period=period).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_STATS_PERIOD.format(period=ru.STATS_PERIOD_LABELS[period]),
            callback_data=StatsPeriodCB(
                report=report, period=period, exercise_id=exercise_id
            ).pack(),
        )
    )
    if exercise_id:
        builder.row(
            InlineKeyboardButton(
                text=ru.BTN_STATS_PICK_OTHER,
                callback_data=StatsPickCB(period=period).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_BACK, callback_data=StatsCB(report="menu", period=period).pack()
        )
    )
    return builder.as_markup()


def records_keyboard(period: str, *, page: int = 0, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Records page by page: the list grows with every exercise ever done."""
    builder = InlineKeyboardBuilder()
    _pager(
        builder,
        page=page,
        total_pages=total_pages,
        callback=lambda target: StatsCB(report="records", period=period, page=target).pack(),
    )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_STATS_PERIOD.format(period=ru.STATS_PERIOD_LABELS[period]),
            callback_data=StatsPeriodCB(report="records", period=period).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_BACK, callback_data=StatsCB(report="menu", period=period).pack()
        )
    )
    return builder.as_markup()


def exercise_picker(
    exercises: list[Exercise],
    period: str,
    *,
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for exercise in exercises:
        builder.button(
            text=exercise.name_ru,
            callback_data=StatsExerciseCB(exercise_id=exercise.id, period=period),
        )
    builder.adjust(1)
    _pager(
        builder,
        page=page,
        total_pages=total_pages,
        callback=lambda target: StatsPickCB(period=period, page=target).pack(),
    )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_BACK, callback_data=StatsCB(report="menu", period=period).pack()
        )
    )
    return builder.as_markup()

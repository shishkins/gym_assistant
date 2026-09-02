"""Reports: charts, records and the CSV export."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.analytics import charts, export
from gym_assistant.analytics.metrics import (
    moving_average,
    personal_records,
    total_tonnage,
    weekly_volume_by_group,
    working_sets,
)
from gym_assistant.bot.keyboards.stats import (
    StatsCB,
    StatsExerciseCB,
    StatsLastCB,
    StatsPeriodCB,
    StatsPickCB,
    exercise_picker,
    menu_keyboard,
    period_keyboard,
    records_keyboard,
    report_keyboard,
)
from gym_assistant.bot.texts import render, ru
from gym_assistant.domain.models import User
from gym_assistant.domain.repositories import MeasurementRepository, StatsRepository
from gym_assistant.domain.services import ExerciseService, WorkoutService

log = structlog.get_logger(__name__)
router = Router(name="stats")

DEFAULT_PERIOD = "3m"
PERIOD_DAYS = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "all": None}
# A picker longer than this stops being a picker - but truncating it silently,
# as this did, hides every exercise past the twelfth. Both lists page instead.
PICKER_PAGE_SIZE = 8
RECORDS_PAGE_SIZE = 8


def _since(period: str) -> datetime | None:
    days = PERIOD_DAYS.get(period)
    return None if days is None else datetime.now(UTC) - timedelta(days=days)


async def _menu(session: AsyncSession, user: User, period: str) -> tuple[str, InlineKeyboardMarkup]:
    stats = StatsRepository(session)
    since = _since(period)
    sets = await stats.sets_with_exercises(user.id, since=since)
    days = await stats.workout_days(user.id, since=since)

    text = ru.STATS_MENU.format(
        period=ru.STATS_PERIOD_LABELS[period], workouts=len(days), sets=len(sets)
    )
    return text, menu_keyboard(period)


async def _send(
    message: Message,
    image: bytes | None,
    report: str,
    period: str,
    *,
    empty: str,
    exercise_id: int = 0,
    thin: bool = False,
) -> None:
    """Sends a chart, or says plainly why there is none.

    ``thin`` marks a picture built from a single point: it is drawn, because a
    dot beats a refusal, but the caption says not to read a trend into it.
    """
    keyboard = report_keyboard(report, period, exercise_id)
    if image is None:
        await message.answer(empty, reply_markup=keyboard)
        return
    await message.answer_photo(
        BufferedInputFile(image, filename=f"{report}.png"),
        caption=ru.STATS_THIN if thin else None,
        reply_markup=keyboard,
    )


# --- entry points ---------------------------------------------------------


@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.clear()
    text, markup = await _menu(session, user, DEFAULT_PERIOD)
    await message.answer(text, reply_markup=markup)


@router.message(Command("export"))
async def cmd_export(message: Message, session: AsyncSession, user: User) -> None:
    await _export(message, session, user)


async def open_stats_menu(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await state.clear()
    text, markup = await _menu(session, user, DEFAULT_PERIOD)
    await message.answer(text, reply_markup=markup)


# --- navigation -----------------------------------------------------------


@router.callback_query(StatsPeriodCB.filter())
async def choose_period(callback: CallbackQuery, callback_data: StatsPeriodCB) -> None:
    await callback.answer()
    message = callback.message
    if isinstance(message, Message):
        await message.answer(
            ru.BTN_STATS_PERIOD.format(period=ru.STATS_PERIOD_LABELS[callback_data.period]),
            reply_markup=period_keyboard(
                callback_data.report, callback_data.period, callback_data.exercise_id
            ),
        )


async def _picker(
    message: Message, session: AsyncSession, user: User, period: str, page: int
) -> None:
    used = await StatsRepository(session).exercises_used(user.id)
    if not used:
        await message.answer(ru.STATS_NO_EXERCISES)
        return

    total_pages = max(1, -(-len(used) // PICKER_PAGE_SIZE))
    page = min(max(page, 0), total_pages - 1)
    offset = page * PICKER_PAGE_SIZE
    await message.answer(
        ru.STATS_PICK_EXERCISE,
        reply_markup=exercise_picker(
            used[offset : offset + PICKER_PAGE_SIZE],
            period,
            page=page,
            total_pages=total_pages,
        ),
    )


@router.callback_query(StatsPickCB.filter())
async def pick_exercise(
    callback: CallbackQuery,
    callback_data: StatsPickCB,
    session: AsyncSession,
    user: User,
) -> None:
    await callback.answer()
    message = callback.message
    if isinstance(message, Message):
        await _picker(message, session, user, callback_data.period, callback_data.page)


@router.callback_query(StatsCB.filter())
async def report(
    callback: CallbackQuery,
    callback_data: StatsCB,
    session: AsyncSession,
    user: User,
) -> None:
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return

    period = callback_data.period
    label = ru.STATS_PERIOD_LABELS[period]
    stats = StatsRepository(session)
    since = _since(period)

    match callback_data.report:
        case "menu":
            text, markup = await _menu(session, user, period)
            await message.answer(text, reply_markup=markup)

        case "progress":
            await _picker(message, session, user, period, callback_data.page)

        case "tonnage":
            weeks = await stats.weekly_tonnage(user.id, since=since)
            await _send(
                message,
                charts.weekly_tonnage_chart(weeks),
                "tonnage",
                period,
                empty=ru.STATS_NOT_ENOUGH.format(period=label),
                thin=len(weeks) == 1,
            )

        case "volume":
            sets = await stats.sets_with_exercises(user.id, since=since)
            volume = weekly_volume_by_group(sets)
            await _send(
                message,
                charts.muscle_volume_chart(volume),
                "volume",
                period,
                empty=ru.STATS_NOT_ENOUGH.format(period=label),
                thin=len(volume) == 1,
            )

        case "weight":
            measurements = await MeasurementRepository(session).history(
                user.id, since=since, limit=1000
            )
            points = [
                (item.measured_at.date(), item.weight_kg)
                for item in reversed(measurements)
                if item.weight_kg is not None
            ]
            await _send(
                message,
                charts.body_weight_chart(points, moving_average(points)),
                "weight",
                period,
                empty=ru.STATS_NOT_ENOUGH.format(period=label),
                thin=len(points) == 1,
            )

        case "frequency":
            days = await stats.workout_days(user.id, since=since)
            await _send(
                message,
                charts.frequency_chart(days),
                "frequency",
                period,
                empty=ru.STATS_NOT_ENOUGH.format(period=label),
                thin=len(days) == 1,
            )

        case "records":
            await _records(message, session, user, period, callback_data.page)

        case "summary":
            await _summary(message, session, user, period)

        case "export":
            await _export(message, session, user)


@router.callback_query(StatsExerciseCB.filter())
async def exercise_progress(
    callback: CallbackQuery,
    callback_data: StatsExerciseCB,
    session: AsyncSession,
    user: User,
) -> None:
    from gym_assistant.analytics.metrics import exercise_progress as compute_progress

    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return

    exercise = await ExerciseService(session).get(callback_data.exercise_id, user_id=user.id)
    if exercise is None:
        return

    period = callback_data.period
    sets = await StatsRepository(session).sets_of_exercise(
        user.id, exercise.id, since=_since(period)
    )
    points = compute_progress(sets)
    await _send(
        message,
        charts.exercise_progress_chart(exercise.name_ru, points),
        "progress",
        period,
        empty=ru.STATS_NOT_ENOUGH.format(period=ru.STATS_PERIOD_LABELS[period]),
        exercise_id=exercise.id,
        thin=len(points) == 1,
    )


@router.callback_query(StatsLastCB.filter())
async def last_with_exercise(
    callback: CallbackQuery,
    callback_data: StatsLastCB,
    session: AsyncSession,
    user: User,
) -> None:
    """The sets behind the last point on the chart.

    Asked for during the iteration 4 review: a curve says the weight went up,
    but not how the session that produced it actually went.
    """
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return

    summary = await WorkoutService(session).last_completed_with(user.id, callback_data.exercise_id)
    keyboard = report_keyboard("progress", callback_data.period, callback_data.exercise_id)
    if summary is None:
        await message.answer(ru.STATS_LAST_WITH_NONE, reply_markup=keyboard)
        return

    header = ru.WORKOUT_LAST_HEADER.format(when=render.format_when(summary.workout.started_at))
    await message.answer(header + render.render_workout_summary(summary), reply_markup=keyboard)


# --- text reports ---------------------------------------------------------


async def _records(
    message: Message, session: AsyncSession, user: User, period: str, page: int = 0
) -> None:
    sets = await StatsRepository(session).sets_with_exercises(user.id)
    records = personal_records(sets)
    if not records:
        await message.answer(ru.STATS_RECORDS_EMPTY, reply_markup=records_keyboard(period))
        return

    # Everything ever lifted goes in this list, and Telegram refuses a message
    # over 4096 characters - so it pages rather than silently losing the tail.
    total_pages = max(1, -(-len(records) // RECORDS_PAGE_SIZE))
    page = min(max(page, 0), total_pages - 1)
    offset = page * RECORDS_PAGE_SIZE

    lines = []
    for record in records[offset : offset + RECORDS_PAGE_SIZE]:
        line = ru.STATS_RECORDS_LINE.format(
            name=record.exercise_name,
            weight=render.format_decimal(record.best_weight) if record.best_weight else "—",
            reps=record.best_weight_reps or "—",
            when=render.format_when(record.best_weight_at) if record.best_weight_at else "",
        )
        if record.best_estimate is not None:
            line += ru.STATS_RECORDS_ESTIMATE.format(
                estimate=render.format_decimal(record.best_estimate)
            )
        lines.append(line)

    counter = f" · {page + 1}/{total_pages}" if total_pages > 1 else ""
    await message.answer(
        ru.STATS_RECORDS_HEADER.format(page=counter) + "\n\n".join(lines),
        reply_markup=records_keyboard(period, page=page, total_pages=total_pages),
    )


async def _summary(message: Message, session: AsyncSession, user: User, period: str) -> None:
    stats = StatsRepository(session)
    since = _since(period)
    sets = await stats.sets_with_exercises(user.id, since=since)
    days = await stats.workout_days(user.id, since=since)

    if not sets:
        await message.answer(
            ru.STATS_EMPTY.format(period=ru.STATS_PERIOD_LABELS[period]),
            reply_markup=report_keyboard("summary", period),
        )
        return

    tonnage = total_tonnage(sets)
    per_workout = tonnage / Decimal(len(days)) if days else Decimal(0)
    await message.answer(
        ru.STATS_SUMMARY.format(
            period=ru.STATS_PERIOD_LABELS[period],
            workouts=len(days),
            sets=len(sets),
            working=len(working_sets(sets)),
            tonnage=render.format_decimal(tonnage.quantize(Decimal("1"))),
            per_workout=render.format_decimal(per_workout.quantize(Decimal("1"))),
        ),
        reply_markup=report_keyboard("summary", period),
    )


async def _export(message: Message, session: AsyncSession, user: User) -> None:
    stats = StatsRepository(session)
    sets = await stats.sets_with_exercises(user.id)
    measurements = await MeasurementRepository(session).history(user.id, limit=10000)

    if not sets and not measurements:
        await message.answer(ru.EXPORT_EMPTY)
        return

    await message.answer(ru.EXPORT_READY.format(sets=len(sets), measurements=len(measurements)))
    stamp = datetime.now(UTC).date().isoformat()
    if sets:
        await message.answer_document(
            BufferedInputFile(export.sets_to_csv(sets), filename=f"подходы_{stamp}.csv")
        )
    if measurements:
        await message.answer_document(
            BufferedInputFile(
                export.measurements_to_csv(list(reversed(measurements))),
                filename=f"замеры_{stamp}.csv",
            )
        )

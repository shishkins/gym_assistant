"""Logging a workout.

The measure of this module is taps per set. Everything is arranged so the
common path - same exercise, same weight, one more set - costs one.
"""

from __future__ import annotations

from decimal import Decimal

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.keyboards import (
    SetAdjustCB,
    SetCommitCB,
    WorkoutCB,
    WorkoutExerciseCB,
    cancel_keyboard,
    panel_keyboard,
    set_entry_keyboard,
    start_keyboard,
)
from gym_assistant.bot.states import WorkoutFlow
from gym_assistant.bot.texts import render, ru
from gym_assistant.domain.models import Exercise, User, WorkoutSet
from gym_assistant.domain.parsing import ParsedSet, ValueParseError, parse_set_entry
from gym_assistant.domain.services import (
    EmptySetError,
    ExerciseService,
    NoOpenWorkoutError,
    WorkoutService,
)

log = structlog.get_logger(__name__)
router = Router(name="workouts")

DEFAULT_REPS = 8
SEARCH_LIMIT = 8


# --- shared rendering -----------------------------------------------------


async def _panel(service: WorkoutService, user: User) -> tuple[str, InlineKeyboardMarkup]:
    workout = await service.open_workout(user.id)
    if workout is None:
        return ru.WORKOUT_NONE_OPEN, start_keyboard(is_open=False)

    summary = await service.summary(workout)
    frequent = await service.frequent_exercises(user.id)
    text = render.render_workout_panel(
        duration_min=summary.duration_min,
        sets=[item for _, items in summary.by_exercise for item in items],
        tonnage=summary.tonnage,
        by_exercise=summary.by_exercise,
    )
    return text, panel_keyboard(frequent)


async def _exercise_panel(
    service: WorkoutService,
    user: User,
    exercise: Exercise,
    state: FSMContext,
) -> tuple[str, InlineKeyboardMarkup]:
    history = await service.history_for(user.id, exercise)
    today = [
        item for item in await service.current_sets(user.id) if item.exercise_id == exercise.id
    ]

    data = await state.get_data()
    if data.get("exercise_id") == exercise.id and "reps" in data:
        weight = Decimal(data["weight"]) if data.get("weight") is not None else None
        reps = int(data["reps"])
    else:
        # Prefill from the last working set: the next set is usually the
        # same one again, so the default should already be right.
        weight = history.suggested_weight
        reps = history.suggested_reps or DEFAULT_REPS

    await state.set_state(WorkoutFlow.active)
    await state.update_data(
        exercise_id=exercise.id,
        weight=str(weight) if weight is not None else None,
        reps=reps,
    )

    text = render.render_exercise_panel(history, today, weight=weight, reps=reps)
    return text, set_entry_keyboard(weight=weight, reps=reps, can_repeat=bool(today))


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    message = callback.message
    if not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=markup)
    except Exception:
        log.debug("workout_edit_failed")
        await message.answer(text, reply_markup=markup)


# --- entry points ---------------------------------------------------------


@router.message(Command("workout"))
async def cmd_workout(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await open_workout_panel(message, state, session, user)


async def open_workout_panel(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    """Starts a session if none is running, then shows the panel."""
    service = WorkoutService(session)
    if await service.open_workout(user.id) is None:
        await service.start(user.id)
        await message.answer(ru.WORKOUT_STARTED)

    await state.set_state(WorkoutFlow.active)
    text, markup = await _panel(service, user)
    await message.answer(text, reply_markup=markup)


@router.message(Command("last"))
async def cmd_last(message: Message, session: AsyncSession, user: User) -> None:
    summary = await WorkoutService(session).last_completed(user.id)
    if summary is None:
        await message.answer(ru.WORKOUT_LAST_NONE)
        return
    header = ru.WORKOUT_LAST_HEADER.format(when=render.format_when(summary.workout.started_at))
    await message.answer(header + render.render_workout_summary(summary))


# --- session actions ------------------------------------------------------


@router.callback_query(WorkoutCB.filter())
async def workout_action(
    callback: CallbackQuery,
    callback_data: WorkoutCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    service = WorkoutService(session)
    await callback.answer()

    match callback_data.action:
        case "start":
            await service.start(user.id)
            await state.set_state(WorkoutFlow.active)
            text, markup = await _panel(service, user)
            await _edit(callback, text, markup)

        case "panel":
            await state.set_state(WorkoutFlow.active)
            # Forget the pending set: the panel is a fresh choice of exercise.
            await state.update_data(exercise_id=None, weight=None, reps=None)
            text, markup = await _panel(service, user)
            await _edit(callback, text, markup)

        case "find":
            await state.set_state(WorkoutFlow.search)
            message = callback.message
            if isinstance(message, Message):
                await message.answer(
                    ru.WORKOUT_PICK_EXERCISE,
                    reply_markup=cancel_keyboard("workout_search").as_markup(),
                )

        case "undo":
            await _undo(callback, service, state, user)

        case "finish":
            await _finish(callback, service, state, user)


async def _undo(
    callback: CallbackQuery, service: WorkoutService, state: FSMContext, user: User
) -> None:
    removed = await service.undo_last(user.id)
    message = callback.message
    if not isinstance(message, Message):
        return

    if removed is None:
        await message.answer(ru.WORKOUT_NOTHING_TO_UNDO)
        return

    await message.answer(ru.WORKOUT_SET_UNDONE.format(value=render.render_set_value(removed)))
    text, markup = await _panel(service, user)
    await message.answer(text, reply_markup=markup)


async def _finish(
    callback: CallbackQuery, service: WorkoutService, state: FSMContext, user: User
) -> None:
    summary = await service.finish(user.id)
    await state.clear()
    if summary is None:
        await _edit(callback, ru.WORKOUT_NONE_OPEN, start_keyboard(is_open=False))
        return
    await _edit(callback, render.render_workout_summary(summary), start_keyboard(is_open=False))


# --- choosing an exercise -------------------------------------------------


@router.callback_query(WorkoutExerciseCB.filter())
async def pick_exercise(
    callback: CallbackQuery,
    callback_data: WorkoutExerciseCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await callback.answer()
    exercise = await ExerciseService(session).get(callback_data.exercise_id, user_id=user.id)
    if exercise is None:
        return
    # Choosing an exercise resets the pending values to that exercise's own.
    await state.update_data(exercise_id=None, weight=None, reps=None)
    text, markup = await _exercise_panel(WorkoutService(session), user, exercise, state)
    await _edit(callback, text, markup)


@router.message(WorkoutFlow.search)
async def search_exercise(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    if not message.text:
        await message.answer(ru.WORKOUT_PICK_EXERCISE)
        return

    found = await ExerciseService(session).search(message.text, user_id=user.id, limit=SEARCH_LIMIT)
    if not found:
        await message.answer(ru.WORKOUT_EXERCISE_NOT_FOUND.format(query=message.text))
        return

    await state.set_state(WorkoutFlow.active)
    await message.answer(
        ru.WORKOUT_PICK_EXERCISE,
        reply_markup=_picker(found),
    )


def _picker(exercises: list[Exercise]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for exercise in exercises:
        builder.button(
            text=exercise.name_ru, callback_data=WorkoutExerciseCB(exercise_id=exercise.id)
        )
    builder.adjust(1)
    return builder.as_markup()


# --- adjusting and committing a set --------------------------------------


@router.callback_query(SetAdjustCB.filter())
async def adjust_set(
    callback: CallbackQuery,
    callback_data: SetAdjustCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    data = await state.get_data()
    exercise_id = data.get("exercise_id")
    if exercise_id is None:
        await callback.answer()
        return

    if callback_data.field == "weight":
        current = Decimal(data["weight"]) if data.get("weight") is not None else Decimal(0)
        updated = max(Decimal(0), current + Decimal(callback_data.delta))
        await state.update_data(weight=str(updated))
    else:
        reps = max(1, int(data.get("reps") or DEFAULT_REPS) + int(callback_data.delta))
        await state.update_data(reps=reps)

    await callback.answer()
    exercise = await ExerciseService(session).get(int(exercise_id), user_id=user.id)
    if exercise is None:
        return
    text, markup = await _exercise_panel(WorkoutService(session), user, exercise, state)
    await _edit(callback, text, markup)


@router.callback_query(SetCommitCB.filter())
async def commit_set(
    callback: CallbackQuery,
    callback_data: SetCommitCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    data = await state.get_data()
    exercise_id = data.get("exercise_id")
    if exercise_id is None:
        await callback.answer()
        return

    service = ExerciseService(session)
    exercise = await service.get(int(exercise_id), user_id=user.id)
    if exercise is None:
        await callback.answer()
        return

    parsed = ParsedSet(
        weight_kg=Decimal(data["weight"]) if data.get("weight") is not None else None,
        reps=int(data.get("reps") or DEFAULT_REPS),
        is_warmup=callback_data.warmup,
    )
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return
    await _store(message, WorkoutService(session), user, exercise, parsed, state)


# --- typed sets -----------------------------------------------------------


@router.message(WorkoutFlow.active, F.text)
async def typed_set(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    """Free text during a session is a set - the fastest path there is."""
    assert message.text is not None
    try:
        parsed = parse_set_entry(message.text)
    except ValueParseError as exc:
        await message.answer(
            ru.WORKOUT_SET_FORMAT_ERROR if exc.reason == "format" else ru.WORKOUT_SET_RANGE_ERROR
        )
        return

    exercises = ExerciseService(session)
    workouts = WorkoutService(session)
    data = await state.get_data()

    exercise: Exercise | None = None
    if parsed.exercise_query:
        found = await exercises.search(parsed.exercise_query, user_id=user.id, limit=1)
        if not found:
            await message.answer(ru.WORKOUT_EXERCISE_NOT_FOUND.format(query=parsed.exercise_query))
            return
        exercise = found[0]
    elif data.get("exercise_id"):
        exercise = await exercises.get(int(data["exercise_id"]), user_id=user.id)

    if exercise is None:
        await message.answer(ru.WORKOUT_NEED_EXERCISE)
        return

    if not parsed.has_payload:
        # Just a name: switch to that exercise rather than refusing.
        await state.update_data(exercise_id=None, weight=None, reps=None)
        text, markup = await _exercise_panel(workouts, user, exercise, state)
        await message.answer(text, reply_markup=markup)
        return

    await _store(message, workouts, user, exercise, parsed, state)


async def _store(
    message: Message,
    service: WorkoutService,
    user: User,
    exercise: Exercise,
    parsed: ParsedSet,
    state: FSMContext,
) -> None:
    try:
        logged = await service.log(user.id, exercise, parsed)
    except NoOpenWorkoutError:
        await message.answer(ru.WORKOUT_NONE_OPEN, reply_markup=start_keyboard(is_open=False))
        return
    except EmptySetError:
        await message.answer(ru.WORKOUT_SET_FORMAT_ERROR)
        return

    await message.answer(_confirmation(logged.sets))
    if logged.is_record and logged.new_best is not None:
        await message.answer(
            ru.WORKOUT_RECORD.format(best=render.format_decimal(logged.new_best))
            if logged.previous_best is None
            else ru.WORKOUT_RECORD_BEATEN.format(
                previous=render.format_decimal(logged.previous_best),
                best=render.format_decimal(logged.new_best),
            )
        )

    # Keep the pending values so the next identical set is one tap away.
    await state.update_data(
        exercise_id=exercise.id,
        weight=str(parsed.weight_kg) if parsed.weight_kg is not None else None,
        reps=parsed.reps or DEFAULT_REPS,
    )
    text, markup = await _exercise_panel(service, user, exercise, state)
    await message.answer(text, reply_markup=markup)


def _confirmation(stored: list[WorkoutSet]) -> str:
    value = render.render_set_value(stored[0])
    if len(stored) == 1:
        return ru.WORKOUT_SET_SAVED.format(value=value)
    return ru.WORKOUT_SETS_SAVED.format(count=len(stored), value=value)

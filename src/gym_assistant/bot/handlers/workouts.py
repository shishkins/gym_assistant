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
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.keyboards import (
    SetAdjustCB,
    SetCommitCB,
    WorkoutCB,
    WorkoutExerciseCB,
    WorkoutFavCB,
    WorkoutSearchPageCB,
    cancel_keyboard,
    panel_keyboard,
    search_results_keyboard,
    set_entry_keyboard,
    start_keyboard,
    technique_keyboard,
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
from gym_assistant.domain.units import Units, from_kg, to_kg

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
    same_exercise = data.get("exercise_id") == exercise.id
    if same_exercise and "reps" in data:
        weight = Decimal(data["weight"]) if data.get("weight") is not None else None
        reps = int(data["reps"])
    else:
        # Prefill from the last working set: the next set is usually the
        # same one again, so the default should already be right.
        weight = history.suggested_weight
        reps = history.suggested_reps or DEFAULT_REPS

    # The pounds mode belongs to the exercise being done, and this is the one
    # place that knows whether we are still on it. Carrying it further would
    # mean the next exercise silently reads a bare number as pounds.
    lbs_input = same_exercise and bool(data.get("lbs_input"))

    await state.set_state(WorkoutFlow.active)
    await state.update_data(
        exercise_id=exercise.id,
        weight=str(weight) if weight is not None else None,
        reps=reps,
        lbs_input=lbs_input,
    )

    text = render.render_exercise_panel(
        history, today, weight=weight, reps=reps, lbs_input=lbs_input
    )
    is_favourite = await ExerciseService(service.session).is_favourite(user.id, exercise.id)
    return text, set_entry_keyboard(
        weight=weight,
        reps=reps,
        can_repeat=bool(today),
        is_favourite=is_favourite,
        lbs_input=lbs_input,
    )


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
            await state.update_data(exercise_id=None, weight=None, reps=None, lbs_input=False)
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

        case "help":
            # Discoverability: the text formats are the fast path, and until
            # now nothing in the interface mentioned they existed.
            message = callback.message
            if isinstance(message, Message):
                await message.answer(ru.WORKOUT_INPUT_HELP)

        case "technique":
            await _technique(callback, session, state, user)

        case "lbs":
            await _toggle_lbs(callback, session, state, user)

        case "catalogue":
            # The session stays open; the catalogue offers a way back.
            await show_catalogue(callback, session, state, user)

        case "undo":
            await _undo(callback, service, state, user)

        case "finish":
            await _finish(callback, service, state, user)


async def _technique(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, user: User
) -> None:
    """The technique card for the exercise being done right now.

    Asked for after a real session: the catalogue was reachable, but it
    opened on a browse list and getting back cost several taps. Between reps
    nobody wants to navigate - they want this exercise, then back.
    """
    exercise_id = (await state.get_data()).get("exercise_id")
    message = callback.message
    if exercise_id is None or not isinstance(message, Message):
        if isinstance(message, Message):
            await message.answer(ru.WORKOUT_TECHNIQUE_NO_EXERCISE)
        return

    service = ExerciseService(session)
    exercise = await service.get(int(exercise_id), user_id=user.id)
    if exercise is None:
        return

    await message.answer(
        render.render_exercise_card(exercise),
        reply_markup=technique_keyboard(
            exercise.id,
            is_favourite=await service.is_favourite(user.id, exercise.id),
        ),
    )


async def _toggle_lbs(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, user: User
) -> None:
    """Switches what a typed number means, for this exercise only.

    Asked for after a session in a gym stacked in pounds: the diary stays in
    kilograms, but reading a plate and converting it in your head between reps
    is how wrong numbers get written down.
    """
    data = await state.get_data()
    exercise_id = data.get("exercise_id")
    if exercise_id is None:
        await callback.answer(ru.WORKOUT_TECHNIQUE_NO_EXERCISE, show_alert=True)
        return

    enabled = not data.get("lbs_input")
    await state.update_data(lbs_input=enabled)
    await callback.answer(ru.WORKOUT_LBS_ENABLED if enabled else ru.WORKOUT_LBS_DISABLED)

    exercise = await ExerciseService(session).get(int(exercise_id), user_id=user.id)
    if exercise is None:
        return
    text, markup = await _exercise_panel(WorkoutService(session), user, exercise, state)
    await _edit(callback, text, markup)


@router.callback_query(WorkoutFavCB.filter())
async def toggle_favourite(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """Stars the current exercise and stays put.

    Deliberately not the catalogue's own toggle: that one re-renders the
    exercise card, which would throw someone out of the set they are in the
    middle of.
    """
    exercise_id = (await state.get_data()).get("exercise_id")
    if exercise_id is None:
        await callback.answer(ru.WORKOUT_TECHNIQUE_NO_EXERCISE, show_alert=True)
        return

    service = ExerciseService(session)
    added = await service.toggle_favourite(user.id, int(exercise_id))
    await callback.answer(ru.EXERCISE_FAV_ADDED if added else ru.EXERCISE_FAV_REMOVED)

    exercise = await service.get(int(exercise_id), user_id=user.id)
    message = callback.message
    if exercise is None or not isinstance(message, Message):
        return

    text, markup = await _exercise_panel(WorkoutService(session), user, exercise, state)
    await _edit(callback, text, markup)


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
    await state.update_data(exercise_id=None, weight=None, reps=None, lbs_input=False)
    text, markup = await _exercise_panel(WorkoutService(session), user, exercise, state)
    await _edit(callback, text, markup)


@router.message(WorkoutFlow.search)
async def search_exercise(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    if not message.text:
        await message.answer(ru.WORKOUT_PICK_EXERCISE)
        return

    service = ExerciseService(session)
    total = await service.count_search(message.text, user_id=user.id)
    if total == 0:
        await message.answer(ru.WORKOUT_EXERCISE_NOT_FOUND.format(query=message.text))
        return

    # Remembered so the pager has something to page through.
    await state.set_state(WorkoutFlow.active)
    await state.update_data(search_query=message.text)
    text, markup = await _search_page(service, user, message.text, page=0)
    await message.answer(text, reply_markup=markup)


@router.callback_query(WorkoutSearchPageCB.filter())
async def search_page(
    callback: CallbackQuery,
    callback_data: WorkoutSearchPageCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await callback.answer()
    query = (await state.get_data()).get("search_query")
    message = callback.message
    if not query or not isinstance(message, Message):
        return

    text, markup = await _search_page(
        ExerciseService(session), user, query, page=callback_data.page
    )
    await _edit(callback, text, markup)


async def _search_page(
    service: ExerciseService, user: User, query: str, *, page: int
) -> tuple[str, InlineKeyboardMarkup]:
    total = await service.count_search(query, user_id=user.id)
    total_pages = max(1, -(-total // SEARCH_LIMIT))
    page = min(max(page, 0), total_pages - 1)

    found = await service.search(
        query, user_id=user.id, limit=SEARCH_LIMIT, offset=page * SEARCH_LIMIT
    )
    text = ru.WORKOUT_PICK_EXERCISE
    if total_pages > 1:
        first = page * SEARCH_LIMIT + 1
        text += "\n\n" + ru.LIST_COUNTER.format(
            shown=f"{first}–{first + len(found) - 1}", total=total
        )
    return text, search_results_keyboard(found, page=page, total_pages=total_pages)


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
        # Out of storage, add, back into storage. Adding a converted step to
        # kilograms instead would drift: +5 lbs is 2.2679685 kg, stored as
        # 2.27, and twenty taps of that is a weight nobody typed.
        units = _input_units(data)
        current = Decimal(data["weight"]) if data.get("weight") is not None else Decimal(0)
        shown = max(Decimal(0), from_kg(current, units) + Decimal(callback_data.delta))
        await state.update_data(weight=str(to_kg(shown, units)))
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
    data = await state.get_data()
    try:
        parsed = parse_set_entry(message.text, _input_units(data))
    except ValueParseError as exc:
        await message.answer(
            ru.WORKOUT_SET_FORMAT_ERROR if exc.reason == "format" else ru.WORKOUT_SET_RANGE_ERROR
        )
        return

    exercises = ExerciseService(session)
    workouts = WorkoutService(session)

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

    # The mode belongs to the exercise it was switched on for, and a line
    # naming a different one has already left it. The unit can only be checked
    # once the name is parsed, so this re-reads rather than guesses - unless
    # the line stated its own unit, which outranks any mode.
    if (
        parsed.marked_units is None
        and data.get("exercise_id") != exercise.id
        and _input_units(data) is Units.IMPERIAL
    ):
        parsed = parse_set_entry(message.text, Units.METRIC)

    if not parsed.has_payload:
        # Just a name: switch to that exercise rather than refusing.
        await state.update_data(exercise_id=None, weight=None, reps=None, lbs_input=False)
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
    if logged.is_record:
        value = render.render_set_value(logged.sets[0])
        text = (
            ru.WORKOUT_RECORD.format(value=value)
            if logged.previous_best is None
            else ru.WORKOUT_RECORD_BEATEN.format(
                value=value, previous=render.format_weight(logged.previous_best)
            )
        )
        if logged.estimate is not None:
            text += ru.WORKOUT_RECORD_ESTIMATE.format(
                estimate=render.format_weight(logged.estimate)
            )
        await message.answer(text)

    # Keep the pending values so the next identical set is one tap away. The
    # pounds mode is dropped when the line named a different exercise: writing
    # exercise_id here would otherwise make _exercise_panel believe we never
    # left, and the mode would follow along uninvited.
    stayed = (await state.get_data()).get("exercise_id") == exercise.id
    await state.update_data(
        exercise_id=exercise.id,
        weight=str(parsed.weight_kg) if parsed.weight_kg is not None else None,
        reps=parsed.reps or DEFAULT_REPS,
        lbs_input=stayed and bool((await state.get_data()).get("lbs_input")),
    )
    text, markup = await _exercise_panel(service, user, exercise, state)
    await message.answer(text, reply_markup=markup)


def _input_units(data: dict[str, object]) -> Units:
    """What a bare number in this panel means right now."""
    return Units.IMPERIAL if data.get("lbs_input") else Units.METRIC


def _confirmation(stored: list[WorkoutSet]) -> str:
    value = render.render_set_value(stored[0])
    if len(stored) == 1:
        return ru.WORKOUT_SET_SAVED.format(value=value)
    return ru.WORKOUT_SETS_SAVED.format(count=len(stored), value=value)


async def show_catalogue(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, user: User
) -> None:
    """Opens the catalogue without ending the session."""
    from gym_assistant.bot.handlers.exercises import show_menu as show_catalogue_menu

    message = callback.message
    if not isinstance(message, Message):
        return
    # The state stays WorkoutFlow.active on purpose: inside a session typed
    # text is a set, and the catalogue is browsed with buttons. Arming a
    # catalogue search here is what made browsing feel like leaving.
    await show_catalogue_menu(message, state, ExerciseService(session), user, workout_open=True)

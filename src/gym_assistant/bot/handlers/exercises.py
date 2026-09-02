"""Exercise catalogue: browsing, search, favourites and personal entries."""

from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.keyboards import (
    EQUIPMENT_BY_VALUE,
    TYPE_BY_VALUE,
    ExCardCB,
    ExFavCB,
    ExHideCB,
    ExListCB,
    ExMenuCB,
    ExNewCB,
    ExUnhideCB,
    cancel_keyboard,
    exercise_card_keyboard,
    exercise_list_keyboard,
    groups_keyboard,
    menu_keyboard,
    new_equipment_keyboard,
    new_group_keyboard,
    new_type_keyboard,
    undo_hide_keyboard,
)
from gym_assistant.bot.states import ExerciseCreate, ExerciseSearch
from gym_assistant.bot.texts import render, ru
from gym_assistant.domain.models import Exercise, User
from gym_assistant.domain.services import DuplicateExerciseError, ExerciseService

log = structlog.get_logger(__name__)
router = Router(name="exercises")

NAME_MIN_LENGTH = 3
NAME_MAX_LENGTH = 80
# Telegram renders a taller keyboard, but a list you scroll past the message
# box stops being scannable - and an unbounded one is eventually refused.
PAGE_SIZE = 8


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Navigates in place instead of stacking new messages in the chat."""
    message = callback.message
    if not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=markup)
    except Exception:
        # Telegram rejects an edit that changes nothing, and a message may be
        # too old to edit. Neither is worth failing the interaction over.
        log.debug("catalogue_edit_failed")
        await message.answer(text, reply_markup=markup)


async def _menu_text(service: ExerciseService, user: User) -> str:
    stats = await service.stats(user.id)
    return ru.EXERCISES_MENU.format(total=stats.total, own=stats.own, favourites=stats.favourites)


async def show_menu(
    message: Message, state: FSMContext, service: ExerciseService, user: User
) -> None:
    """Opens the catalogue and leaves search armed.

    Search being armed is the point: the catalogue is something you dip into
    repeatedly during a session, and retyping the command each time is friction.
    """
    await state.set_state(ExerciseSearch.query)
    await message.answer(await _menu_text(service, user), reply_markup=menu_keyboard())


# --- Paged lists ----------------------------------------------------------


async def _count(service: ExerciseService, user: User, *, kind: str, ref: int, query: str) -> int:
    if kind == "group":
        return await service.count_by_muscle_group(ref, user_id=user.id)
    if kind == "favourites":
        return await service.count_favourites(user.id)
    if kind == "own":
        return await service.count_own(user.id)
    return await service.count_search(query, user_id=user.id)


async def _fetch(
    service: ExerciseService, user: User, *, kind: str, ref: int, query: str, offset: int
) -> list[Exercise]:
    if kind == "group":
        return await service.by_muscle_group(ref, user_id=user.id, limit=PAGE_SIZE, offset=offset)
    if kind == "favourites":
        return await service.favourites(user.id, limit=PAGE_SIZE, offset=offset)
    if kind == "own":
        return await service.own(user.id, limit=PAGE_SIZE, offset=offset)
    return await service.search(query, user_id=user.id, limit=PAGE_SIZE, offset=offset)


async def _list_view(
    service: ExerciseService,
    user: User,
    *,
    kind: str,
    ref: int = 0,
    page: int = 0,
    query: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    """Renders any exercise list.

    Every list goes through one function so that paging cannot be added to
    one of them and forgotten on the next - which is exactly what happened
    when only muscle groups were paged.
    """
    total = await _count(service, user, kind=kind, ref=ref, query=query)
    total_pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(page, 0), total_pages - 1)

    if total == 0:
        if kind == "favourites":
            return ru.EXERCISES_FAVOURITES_EMPTY, menu_keyboard()
        if kind == "own":
            return ru.EXERCISES_OWN_EMPTY, menu_keyboard()
        if kind == "search":
            return ru.EXERCISES_SEARCH_EMPTY.format(query=query), menu_keyboard()
        return ru.EXERCISES_GROUP_EMPTY, groups_keyboard(await service.muscle_groups())

    items = await _fetch(service, user, kind=kind, ref=ref, query=query, offset=page * PAGE_SIZE)

    if kind == "group":
        groups = {group.id: group for group in await service.muscle_groups()}
        header = ru.EXERCISES_GROUP_RESULTS.format(group=groups[ref].name_ru)
        back_action, back_label = "groups", None
    elif kind == "favourites":
        header, back_action, back_label = ru.EXERCISES_FAVOURITES, "menu", None
    elif kind == "own":
        header, back_action, back_label = ru.EXERCISES_OWN, "menu", None
    else:
        header = ru.EXERCISES_SEARCH_RESULTS.format(query=query)
        back_action, back_label = "menu", ru.BTN_EXIT_SEARCH

    if total_pages > 1:
        first = page * PAGE_SIZE + 1
        header += "\n\n" + ru.LIST_COUNTER.format(
            shown=f"{first}–{first + len(items) - 1}", total=total
        )

    return header, exercise_list_keyboard(
        items,
        kind=kind,
        ref=ref,
        page=page,
        total_pages=total_pages,
        back_action=back_action,
        back_label=back_label,
    )


async def _show_card(
    callback: CallbackQuery, service: ExerciseService, user: User, exercise_id: int
) -> None:
    exercise = await service.get(exercise_id, user_id=user.id)
    if exercise is None:
        await callback.answer(ru.EXERCISES_GROUP_EMPTY, show_alert=True)
        return
    is_favourite = await service.is_favourite(user.id, exercise.id)
    await _edit(
        callback,
        render.render_exercise_card(exercise),
        exercise_card_keyboard(exercise, is_favourite=is_favourite),
    )


# --- Entry point ----------------------------------------------------------


@router.message(Command("exercises"))
async def cmd_exercises(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """``/exercises`` opens the menu, ``/exercises жим`` searches straight away."""
    service = ExerciseService(session)

    if command.args:
        await state.set_state(ExerciseSearch.query)
        await state.update_data(search_query=command.args)
        text, markup = await _list_view(service, user, kind="search", query=command.args)
        await message.answer(text, reply_markup=markup)
        return

    await show_menu(message, state, service, user)


# --- Menu navigation ------------------------------------------------------


@router.callback_query(ExMenuCB.filter())
async def menu_action(
    callback: CallbackQuery,
    callback_data: ExMenuCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    service = ExerciseService(session)
    await callback.answer()

    match callback_data.action:
        case "noop":
            # The page counter is a label, not a control.
            return

        case "menu":
            await state.set_state(ExerciseSearch.query)
            await _edit(callback, await _menu_text(service, user), menu_keyboard())

        case "groups":
            await _edit(
                callback, ru.EXERCISES_GROUPS, groups_keyboard(await service.muscle_groups())
            )

        case "favourites":
            text, markup = await _list_view(service, user, kind="favourites")
            await _edit(callback, text, markup)

        case "own":
            text, markup = await _list_view(service, user, kind="own")
            await _edit(callback, text, markup)

        case "search":
            await state.set_state(ExerciseSearch.query)
            message = callback.message
            if isinstance(message, Message):
                await message.answer(ru.SEARCH_MODE_ON)

        case "new":
            await state.set_state(ExerciseCreate.name)
            message = callback.message
            if isinstance(message, Message):
                await message.answer(
                    ru.EXERCISE_NEW_NAME,
                    reply_markup=cancel_keyboard("exercise_new").as_markup(),
                )


@router.callback_query(ExListCB.filter())
async def list_page(
    callback: CallbackQuery,
    callback_data: ExListCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """One handler for every paged list."""
    await callback.answer()
    # The search term lives in FSM data: a Cyrillic query does not reliably
    # fit in the 64 bytes Telegram allows for callback data.
    data = await state.get_data()
    text, markup = await _list_view(
        ExerciseService(session),
        user,
        kind=callback_data.kind,
        ref=callback_data.ref,
        page=callback_data.page,
        query=data.get("search_query", ""),
    )
    await _edit(callback, text, markup)


@router.callback_query(ExCardCB.filter())
async def open_card(
    callback: CallbackQuery, callback_data: ExCardCB, session: AsyncSession, user: User
) -> None:
    await callback.answer()
    await _show_card(callback, ExerciseService(session), user, callback_data.exercise_id)


# --- Per-user preferences -------------------------------------------------


@router.callback_query(ExFavCB.filter())
async def toggle_favourite(
    callback: CallbackQuery, callback_data: ExFavCB, session: AsyncSession, user: User
) -> None:
    service = ExerciseService(session)
    added = await service.toggle_favourite(user.id, callback_data.exercise_id)
    await callback.answer(ru.EXERCISE_FAV_ADDED if added else ru.EXERCISE_FAV_REMOVED)
    await _show_card(callback, service, user, callback_data.exercise_id)


@router.callback_query(ExHideCB.filter())
async def hide_exercise(
    callback: CallbackQuery, callback_data: ExHideCB, session: AsyncSession, user: User
) -> None:
    service = ExerciseService(session)
    exercise = await service.get(callback_data.exercise_id, user_id=user.id)
    if exercise is None:
        await callback.answer()
        return

    name = exercise.name_ru
    await service.set_hidden(user.id, exercise.id, hidden=True)
    await callback.answer()
    await _edit(callback, ru.EXERCISE_HIDDEN.format(name=name), undo_hide_keyboard(exercise.id))


@router.callback_query(ExUnhideCB.filter())
async def unhide_exercise(
    callback: CallbackQuery, callback_data: ExUnhideCB, session: AsyncSession, user: User
) -> None:
    service = ExerciseService(session)
    await service.set_hidden(user.id, callback_data.exercise_id, hidden=False)
    exercise = await service.get(callback_data.exercise_id, user_id=user.id)
    await callback.answer()
    if exercise is None:
        return
    await _edit(callback, ru.EXERCISE_RESTORED.format(name=exercise.name_ru), menu_keyboard())


# --- Search ---------------------------------------------------------------


@router.message(ExerciseSearch.query)
async def search_entered(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    if not message.text:
        await message.answer(ru.EXERCISES_SEARCH_PROMPT)
        return

    # State is deliberately kept: the next message searches again.
    await state.update_data(search_query=message.text)
    text, markup = await _list_view(
        ExerciseService(session), user, kind="search", query=message.text
    )
    await message.answer(text, reply_markup=markup)


# --- Creating a personal exercise ----------------------------------------


@router.message(ExerciseCreate.name)
async def new_name_entered(message: Message, state: FSMContext, session: AsyncSession) -> None:
    name = " ".join((message.text or "").split())
    keyboard = cancel_keyboard("exercise_new").as_markup()

    if len(name) < NAME_MIN_LENGTH:
        await message.answer(ru.EXERCISE_NAME_TOO_SHORT, reply_markup=keyboard)
        return
    if len(name) > NAME_MAX_LENGTH:
        await message.answer(ru.EXERCISE_NAME_TOO_LONG, reply_markup=keyboard)
        return

    await state.update_data(name=name)
    await state.set_state(ExerciseCreate.muscle_group)
    groups = await ExerciseService(session).muscle_groups()
    await message.answer(ru.EXERCISE_NEW_GROUP, reply_markup=new_group_keyboard(groups))


@router.callback_query(ExerciseCreate.muscle_group, ExNewCB.filter())
async def new_group_chosen(
    callback: CallbackQuery, callback_data: ExNewCB, state: FSMContext
) -> None:
    await state.update_data(muscle_group_id=int(callback_data.value))
    await state.set_state(ExerciseCreate.equipment)
    await callback.answer()
    await _edit(callback, ru.EXERCISE_NEW_EQUIPMENT, new_equipment_keyboard())


@router.callback_query(ExerciseCreate.equipment, ExNewCB.filter())
async def new_equipment_chosen(
    callback: CallbackQuery, callback_data: ExNewCB, state: FSMContext
) -> None:
    await state.update_data(equipment=callback_data.value)
    await state.set_state(ExerciseCreate.exercise_type)
    await callback.answer()
    await _edit(callback, ru.EXERCISE_NEW_TYPE, new_type_keyboard())


@router.callback_query(ExerciseCreate.exercise_type, ExNewCB.filter())
async def new_type_chosen(
    callback: CallbackQuery,
    callback_data: ExNewCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer()

    service = ExerciseService(session)
    try:
        exercise = await service.create_own(
            user.id,
            name=data["name"],
            primary_muscle_group_id=data["muscle_group_id"],
            equipment=EQUIPMENT_BY_VALUE[data["equipment"]],
            exercise_type=TYPE_BY_VALUE[callback_data.value],
        )
    except DuplicateExerciseError:
        await _edit(callback, ru.EXERCISE_NEW_DUPLICATE, menu_keyboard())
        return

    message = callback.message
    if isinstance(message, Message):
        await message.edit_text(ru.EXERCISE_NEW_DONE.format(name=exercise.name_ru))
        await message.answer(
            render.render_exercise_card(exercise),
            reply_markup=exercise_card_keyboard(exercise, is_favourite=False),
        )

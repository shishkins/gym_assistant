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
    ExGroupCB,
    ExHideCB,
    ExMenuCB,
    ExNewCB,
    ExUnhideCB,
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
from gym_assistant.domain.models import User
from gym_assistant.domain.services import DuplicateExerciseError, ExerciseService

log = structlog.get_logger(__name__)
router = Router(name="exercises")

NAME_MIN_LENGTH = 3
NAME_MAX_LENGTH = 80
SEARCH_LIMIT = 8


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Navigates in place instead of stacking new messages in the chat."""
    message = callback.message
    if not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=markup)
    except Exception:
        # Telegram rejects an edit that changes nothing, and the message may
        # be too old to edit. Neither is worth failing the interaction over.
        log.debug("catalogue_edit_failed")
        await message.answer(text, reply_markup=markup)


async def _menu_text(service: ExerciseService, user: User) -> str:
    stats = await service.stats(user.id)
    return ru.EXERCISES_MENU.format(total=stats.total, own=stats.own, favourites=stats.favourites)


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
        await _answer_search(message, service, user, command.args)
        return

    await state.clear()
    await message.answer(await _menu_text(service, user), reply_markup=menu_keyboard())


async def _answer_search(
    message: Message, service: ExerciseService, user: User, query: str
) -> None:
    found = await service.search(query, user_id=user.id, limit=SEARCH_LIMIT)
    if not found:
        await message.answer(
            ru.EXERCISES_SEARCH_EMPTY.format(query=query), reply_markup=menu_keyboard()
        )
        return
    await message.answer(
        ru.EXERCISES_SEARCH_RESULTS.format(query=query),
        reply_markup=exercise_list_keyboard(found),
    )


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
        case "menu":
            await state.clear()
            await _edit(callback, await _menu_text(service, user), menu_keyboard())

        case "groups":
            await _edit(
                callback, ru.EXERCISES_GROUPS, groups_keyboard(await service.muscle_groups())
            )

        case "favourites":
            favourites = await service.favourites(user.id)
            if not favourites:
                await _edit(callback, ru.EXERCISES_FAVOURITES_EMPTY, menu_keyboard())
            else:
                await _edit(callback, ru.EXERCISES_FAVOURITES, exercise_list_keyboard(favourites))

        case "own":
            own = await service.own(user.id)
            if not own:
                await _edit(callback, ru.EXERCISES_OWN_EMPTY, menu_keyboard())
            else:
                await _edit(callback, ru.EXERCISES_OWN, exercise_list_keyboard(own))

        case "search":
            await state.set_state(ExerciseSearch.query)
            message = callback.message
            if isinstance(message, Message):
                await message.answer(ru.EXERCISES_SEARCH_PROMPT)

        case "new":
            await state.set_state(ExerciseCreate.name)
            message = callback.message
            if isinstance(message, Message):
                await message.answer(ru.EXERCISE_NEW_NAME)


@router.callback_query(ExGroupCB.filter())
async def open_group(
    callback: CallbackQuery, callback_data: ExGroupCB, session: AsyncSession, user: User
) -> None:
    service = ExerciseService(session)
    await callback.answer()

    exercises = await service.by_muscle_group(callback_data.group_id, user_id=user.id)
    if not exercises:
        await _edit(
            callback, ru.EXERCISES_GROUP_EMPTY, groups_keyboard(await service.muscle_groups())
        )
        return

    groups = {group.id: group for group in await service.muscle_groups()}
    await _edit(
        callback,
        ru.EXERCISES_GROUP_RESULTS.format(group=groups[callback_data.group_id].name_ru),
        exercise_list_keyboard(exercises, back_action="groups"),
    )


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
    await _edit(
        callback,
        ru.EXERCISE_HIDDEN.format(name=name),
        undo_hide_keyboard(exercise.id),
    )


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
    await _edit(
        callback,
        ru.EXERCISE_RESTORED.format(name=exercise.name_ru),
        menu_keyboard(),
    )


# --- Search ---------------------------------------------------------------


@router.message(ExerciseSearch.query)
async def search_entered(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    if not message.text:
        await message.answer(ru.EXERCISES_SEARCH_PROMPT)
        return
    await state.clear()
    await _answer_search(message, ExerciseService(session), user, message.text)


# --- Creating a personal exercise ----------------------------------------


@router.message(ExerciseCreate.name)
async def new_name_entered(message: Message, state: FSMContext, session: AsyncSession) -> None:
    name = " ".join((message.text or "").split())

    if len(name) < NAME_MIN_LENGTH:
        await message.answer(ru.EXERCISE_NAME_TOO_SHORT)
        return
    if len(name) > NAME_MAX_LENGTH:
        await message.answer(ru.EXERCISE_NAME_TOO_LONG)
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

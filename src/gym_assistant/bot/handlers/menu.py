"""The single entry point that reaches every feature.

Commands are discoverable but flat: /menu gives one keyboard that leads
everywhere, so nothing has to be memorised.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.handlers.exercises import show_menu
from gym_assistant.bot.handlers.measurements import prompt_weight, send_photos
from gym_assistant.bot.handlers.profile import show_card
from gym_assistant.bot.handlers.stats import open_stats_menu
from gym_assistant.bot.handlers.workouts import open_workout_panel
from gym_assistant.bot.keyboards import CancelCB, MainMenuCB, main_menu_keyboard
from gym_assistant.bot.states import WorkoutFlow
from gym_assistant.bot.texts import ru
from gym_assistant.domain.models import User
from gym_assistant.domain.services import ExerciseService, WorkoutService

router = Router(name="menu")


async def _leave_wizard(state: FSMContext, session: AsyncSession, user: User) -> bool:
    """Drops whatever was half-typed, but not the workout.

    A running session is a row in the database, not a wizard step: leaving
    to the menu must keep free text meaning "a set". Clearing the state
    outright is what made the menu knock people out of their workout.
    Returns whether a session is running.
    """
    await state.clear()
    running = await WorkoutService(session).open_workout(user.id) is not None
    if running:
        await state.set_state(WorkoutFlow.active)
    return running


@router.message(Command("menu"), StateFilter("*"))
async def cmd_menu(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    """Always available, from inside any wizard: it is the way out and back."""
    await _leave_wizard(state, session, user)
    await message.answer(ru.MAIN_MENU, reply_markup=main_menu_keyboard())


@router.callback_query(MainMenuCB.filter())
async def menu_action(
    callback: CallbackQuery,
    callback_data: MainMenuCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return

    match callback_data.action:
        case "workout":
            await open_workout_panel(message, state, session, user)
        case "stats":
            await open_stats_menu(message, state, session, user)
        case "exercises":
            running = await _leave_wizard(state, session, user)
            await show_menu(message, state, ExerciseService(session), user, workout_open=running)
        case "weight":
            await prompt_weight(message, state, session, user)
        case "photos":
            await _leave_wizard(state, session, user)
            await send_photos(message, session, user)
        case "profile":
            await _leave_wizard(state, session, user)
            await show_card(message, session, user)
        case "help":
            await _leave_wizard(state, session, user)
            await message.answer(ru.HELP, reply_markup=main_menu_keyboard())


@router.callback_query(CancelCB.filter())
async def cancel_action(callback: CallbackQuery, state: FSMContext) -> None:
    """The button form of /cancel.

    Typing a command to back out is a thing the user has to remember; every
    step that waits for input carries this button instead.
    """
    await state.clear()
    await callback.answer(ru.ACTION_CANCELLED)
    message = callback.message
    if isinstance(message, Message):
        await message.edit_text(ru.ACTION_CANCELLED, reply_markup=main_menu_keyboard())

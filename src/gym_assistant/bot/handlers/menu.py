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
from gym_assistant.bot.keyboards import MainMenuCB, main_menu_keyboard
from gym_assistant.bot.texts import ru
from gym_assistant.domain.models import User
from gym_assistant.domain.services import ExerciseService

router = Router(name="menu")


@router.message(Command("menu"), StateFilter("*"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    """Always available, from inside any wizard: it is the way out and back."""
    await state.clear()
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
        case "exercises":
            await show_menu(message, state, ExerciseService(session), user)
        case "weight":
            await prompt_weight(message, state, session, user)
        case "photos":
            await state.clear()
            await send_photos(message, session, user)
        case "profile":
            await state.clear()
            await show_card(message, session, user)
        case "help":
            await state.clear()
            await message.answer(ru.HELP, reply_markup=main_menu_keyboard())

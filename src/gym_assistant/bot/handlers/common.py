"""Entry commands and conversation escape hatches."""

from __future__ import annotations

import html
from datetime import date

from aiogram import Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant import __version__
from gym_assistant.bot.handlers import onboarding
from gym_assistant.bot.texts import render, ru
from gym_assistant.config import Settings
from gym_assistant.domain.models import User
from gym_assistant.domain.services import ProfileService

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.clear()
    name = html.escape(user.first_name or "друг")
    summary = await ProfileService(session).get_summary(user.id, today=date.today())

    if summary.is_empty:
        await message.answer(ru.START_GREETING.format(name=name))
        await onboarding.start(message, state)
        return

    await message.answer(
        ru.START_RETURNING.format(name=name, summary=render.render_profile_summary_short(summary))
    )


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Registered first so it works from inside any wizard."""
    if await state.get_state() is None:
        await message.answer(ru.NOTHING_TO_CANCEL)
        return
    await state.clear()
    await message.answer(ru.CANCELLED)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(ru.HELP)


@router.message(Command("ping"))
async def cmd_ping(message: Message, settings: Settings) -> None:
    await message.answer(ru.PING_OK.format(version=__version__, environment=settings.environment))

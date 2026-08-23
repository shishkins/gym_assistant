"""Basic commands available from day one."""

from __future__ import annotations

import html

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from gym_assistant import __version__
from gym_assistant.bot.texts import ru
from gym_assistant.config import Settings

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    name = message.from_user.first_name if message.from_user else "друг"
    await message.answer(ru.START_GREETING.format(name=html.escape(name)))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(ru.HELP)


@router.message(Command("ping"))
async def cmd_ping(message: Message, settings: Settings) -> None:
    await message.answer(ru.PING_OK.format(version=__version__, environment=settings.environment))

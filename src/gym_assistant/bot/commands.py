"""The command list Telegram shows in its native menu.

Registered on startup so BotFather's /setcommands never has to be kept in
sync by hand.
"""

from __future__ import annotations

from aiogram.types import BotCommand

BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="menu", description="Главное меню"),
    BotCommand(command="workout", description="Тренировка"),
    BotCommand(command="last", description="Последняя тренировка"),
    BotCommand(command="stats", description="Статистика и графики"),
    BotCommand(command="export", description="Выгрузить данные"),
    BotCommand(command="exercises", description="Справочник упражнений"),
    BotCommand(command="profile", description="Профиль"),
    BotCommand(command="weight", description="Записать вес"),
    BotCommand(command="photos", description="Фото прогресса"),
    BotCommand(command="help", description="Что я умею"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
)

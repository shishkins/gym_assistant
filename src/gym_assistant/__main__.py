"""Entry point: wires configuration, storage, middlewares and routers."""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from gym_assistant import __version__
from gym_assistant.bot.handlers import get_routers
from gym_assistant.bot.middlewares import (
    DbSessionMiddleware,
    LoggingMiddleware,
    WhitelistMiddleware,
)
from gym_assistant.config import get_settings
from gym_assistant.db import create_engine, create_session_factory
from gym_assistant.logging_setup import setup_logging


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, json_logs=settings.is_production)
    log = structlog.get_logger("gym_assistant")

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    storage = RedisStorage.from_url(settings.redis_url)

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=storage)
    dispatcher["settings"] = settings

    # Order matters: log context first, then access control, then the session.
    dispatcher.update.outer_middleware(LoggingMiddleware())
    dispatcher.update.outer_middleware(WhitelistMiddleware(settings.allowed_ids))
    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))

    dispatcher.include_routers(*get_routers())

    me = await bot.get_me()
    log.info(
        "bot_started",
        username=me.username,
        version=__version__,
        environment=settings.environment,
        whitelisted_users=len(settings.allowed_ids),
    )

    try:
        # Drop updates queued while the bot was down: on restart they are stale.
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await storage.close()
        await bot.session.close()
        await engine.dispose()
        log.info("bot_stopped")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(main())

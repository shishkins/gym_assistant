"""Handler routers, in registration order."""

from aiogram import Router

from gym_assistant.bot.handlers import common, fallback


def get_routers() -> tuple[Router, ...]:
    """Routers are matched in order, so ``fallback`` must stay last."""
    return (
        common.router,
        fallback.router,
    )


__all__ = ["get_routers"]

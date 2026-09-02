"""Handler routers, in registration order.

Order is behaviour, not style:
* ``common`` first, so /cancel escapes any wizard;
* ``onboarding`` before ``profile``, because both answer the same callback
  payloads and onboarding claims them only while its states are set;
* ``fallback`` last, since it matches everything.
"""

from aiogram import Router

from gym_assistant.bot.handlers import (
    common,
    exercises,
    fallback,
    measurements,
    onboarding,
    profile,
)


def get_routers() -> tuple[Router, ...]:
    return (
        common.router,
        onboarding.router,
        profile.router,
        measurements.router,
        exercises.router,
        fallback.router,
    )


__all__ = ["get_routers"]

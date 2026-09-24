"""Handler routers, in registration order.

Order is behaviour, not style:
* ``common`` first, so /cancel escapes any wizard;
* ``menu`` next, so /menu is reachable from inside one too;
* ``onboarding`` before ``profile``, because both answer the same callback
  payloads and onboarding claims them only while its states are set;
* ``meals`` before ``measurements``, because both answer a photo: a meal
  being clarified owns the next picture, and anything else is a progress
  shot;
* ``workouts`` before ``exercises``, because a running session owns free
  text: what you type between reps is a set, not a catalogue search;
* ``admin`` early, because its whole router is filtered on the admin
  role: a non-admin falls straight through it as if it were not there;
* ``fallback`` last, since it matches everything.
"""

from aiogram import Router

from gym_assistant.bot.handlers import (
    admin,
    ai,
    common,
    exercises,
    fallback,
    meals,
    measurements,
    menu,
    onboarding,
    profile,
    stats,
    workouts,
)


def get_routers() -> tuple[Router, ...]:
    return (
        common.router,
        admin.router,
        admin.public_router,
        ai.router,
        menu.router,
        onboarding.router,
        profile.router,
        meals.router,
        measurements.router,
        workouts.router,
        stats.router,
        exercises.router,
        fallback.router,
    )


__all__ = ["get_routers"]

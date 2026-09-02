"""FSM states for a running workout."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class WorkoutFlow(StatesGroup):
    """A session in progress.

    ``active`` means free text is read as a set; ``search`` means it is read
    as an exercise name. Keeping them apart is what lets the workout survive
    a detour through the catalogue.
    """

    active = State()
    search = State()

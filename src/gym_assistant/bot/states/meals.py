"""FSM states for the food diary."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MealFlow(StatesGroup):
    """A breakdown on screen that has not been written down yet.

    The breakdown itself lives in the state data rather than in the database:
    until the person agrees, it is the model's opinion, and a diary that
    accumulates unconfirmed opinions is worse than an empty one.
    """

    reviewing = State()
    clarifying = State()

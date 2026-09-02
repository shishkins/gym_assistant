"""FSM states for the exercise catalogue."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ExerciseSearch(StatesGroup):
    """Waiting for a search query."""

    query = State()


class ExerciseCreate(StatesGroup):
    """Adding a personal exercise: a typed name, then three button answers."""

    name = State()
    muscle_group = State()
    equipment = State()
    exercise_type = State()

"""FSM states for profile-related conversations."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    """First-run wizard. Every step is skippable."""

    sex = State()
    birth_date = State()
    height = State()
    goal = State()
    weight = State()


class WeightEntry(StatesGroup):
    """/weight without an argument."""

    value = State()


class ProfileEdit(StatesGroup):
    """Editing one field from the profile card.

    The field being edited is kept in the FSM data under ``field``.
    """

    value = State()

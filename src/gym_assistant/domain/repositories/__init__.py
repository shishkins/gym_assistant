"""Repositories: the only place that talks SQL."""

from gym_assistant.domain.repositories.exercise_repository import ExerciseRepository
from gym_assistant.domain.repositories.measurement_repository import MeasurementRepository
from gym_assistant.domain.repositories.user_repository import UserRepository
from gym_assistant.domain.repositories.workout_repository import WorkoutRepository

__all__ = [
    "ExerciseRepository",
    "MeasurementRepository",
    "UserRepository",
    "WorkoutRepository",
]

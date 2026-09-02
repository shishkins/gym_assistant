"""Use cases. Handlers, AI tools and the future API all go through here."""

from gym_assistant.domain.services.exercise_service import (
    CatalogueStats,
    DuplicateExerciseError,
    ExerciseService,
)
from gym_assistant.domain.services.measurement_service import (
    EmptyMeasurementError,
    MeasurementService,
)
from gym_assistant.domain.services.profile_service import ProfileService, ProfileSummary
from gym_assistant.domain.services.workout_service import (
    EmptySetError,
    ExerciseHistory,
    LoggedSets,
    NoOpenWorkoutError,
    WorkoutService,
    WorkoutSummary,
)

__all__ = [
    "CatalogueStats",
    "DuplicateExerciseError",
    "EmptyMeasurementError",
    "EmptySetError",
    "ExerciseHistory",
    "ExerciseService",
    "LoggedSets",
    "MeasurementService",
    "NoOpenWorkoutError",
    "ProfileService",
    "ProfileSummary",
    "WorkoutService",
    "WorkoutSummary",
]

"""FSM state groups."""

from gym_assistant.bot.states.exercises import ExerciseCreate, ExerciseSearch
from gym_assistant.bot.states.meals import MealFlow
from gym_assistant.bot.states.profile import Onboarding, ProfileEdit, WeightEntry
from gym_assistant.bot.states.workouts import WorkoutFlow

__all__ = [
    "ExerciseCreate",
    "ExerciseSearch",
    "MealFlow",
    "Onboarding",
    "ProfileEdit",
    "WeightEntry",
    "WorkoutFlow",
]

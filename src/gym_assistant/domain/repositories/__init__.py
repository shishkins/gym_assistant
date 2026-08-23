"""Repositories: the only place that talks SQL."""

from gym_assistant.domain.repositories.measurement_repository import MeasurementRepository
from gym_assistant.domain.repositories.user_repository import UserRepository

__all__ = ["MeasurementRepository", "UserRepository"]

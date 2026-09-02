"""Data access for workouts and sets."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import Workout, WorkoutSet, WorkoutStatus


class WorkoutRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- workouts ----------------------------------------------------------

    async def open_workout(self, user_id: int) -> Workout | None:
        stmt = select(Workout).where(
            Workout.user_id == user_id,
            Workout.status == WorkoutStatus.IN_PROGRESS.value,
        )
        workout: Workout | None = await self._session.scalar(stmt)
        return workout

    async def get(self, workout_id: int, *, user_id: int) -> Workout | None:
        stmt = select(Workout).where(Workout.id == workout_id, Workout.user_id == user_id)
        workout: Workout | None = await self._session.scalar(stmt)
        return workout

    async def add(self, workout: Workout) -> Workout:
        self._session.add(workout)
        await self._session.flush()
        return workout

    async def last_completed(self, user_id: int) -> Workout | None:
        stmt = (
            select(Workout)
            .where(
                Workout.user_id == user_id,
                Workout.status == WorkoutStatus.COMPLETED.value,
            )
            .order_by(Workout.started_at.desc())
            .limit(1)
        )
        workout: Workout | None = await self._session.scalar(stmt)
        return workout

    async def stale_open(self, older_than: datetime) -> list[Workout]:
        """Sessions left open long enough that they are certainly over."""
        stmt = select(Workout).where(
            Workout.status == WorkoutStatus.IN_PROGRESS.value,
            Workout.started_at < older_than,
        )
        return list(await self._session.scalars(stmt))

    # -- sets --------------------------------------------------------------

    async def add_set(self, item: WorkoutSet) -> WorkoutSet:
        self._session.add(item)
        await self._session.flush()
        return item

    async def sets_of(self, workout_id: int) -> list[WorkoutSet]:
        stmt = (
            select(WorkoutSet)
            .where(WorkoutSet.workout_id == workout_id)
            .order_by(WorkoutSet.order_index, WorkoutSet.set_index, WorkoutSet.id)
        )
        return list(await self._session.scalars(stmt))

    async def last_set(self, workout_id: int) -> WorkoutSet | None:
        stmt = (
            select(WorkoutSet)
            .where(WorkoutSet.workout_id == workout_id)
            .order_by(WorkoutSet.performed_at.desc(), WorkoutSet.id.desc())
            .limit(1)
        )
        item: WorkoutSet | None = await self._session.scalar(stmt)
        return item

    async def delete_set(self, item: WorkoutSet) -> None:
        await self._session.delete(item)
        await self._session.flush()

    async def next_indexes(self, workout_id: int, exercise_id: int) -> tuple[int, int]:
        """``(order_index, set_index)`` for the next set of this exercise.

        The exercise keeps the position it was first used at, so re-visiting
        it later in the session does not reshuffle the summary.
        """
        existing = await self._session.scalar(
            select(WorkoutSet.order_index)
            .where(
                WorkoutSet.workout_id == workout_id,
                WorkoutSet.exercise_id == exercise_id,
            )
            .limit(1)
        )
        if existing is None:
            highest = await self._session.scalar(
                select(func.max(WorkoutSet.order_index)).where(WorkoutSet.workout_id == workout_id)
            )
            return (0 if highest is None else int(highest) + 1), 1

        used = await self._session.scalar(
            select(func.max(WorkoutSet.set_index)).where(
                WorkoutSet.workout_id == workout_id,
                WorkoutSet.exercise_id == exercise_id,
            )
        )
        return int(existing), (1 if used is None else int(used) + 1)

    # -- history -----------------------------------------------------------

    async def recent_sets_of_exercise(
        self, user_id: int, exercise_id: int, *, limit: int = 20
    ) -> list[WorkoutSet]:
        stmt = (
            select(WorkoutSet)
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(Workout.user_id == user_id, WorkoutSet.exercise_id == exercise_id)
            .order_by(WorkoutSet.performed_at.desc())
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def all_sets_of_exercise(self, user_id: int, exercise_id: int) -> list[WorkoutSet]:
        stmt = (
            select(WorkoutSet)
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(Workout.user_id == user_id, WorkoutSet.exercise_id == exercise_id)
            .order_by(WorkoutSet.performed_at)
        )
        return list(await self._session.scalars(stmt))

    async def frequent_exercise_ids(self, user_id: int, *, limit: int = 8) -> list[int]:
        """Exercises this user logs most, most-used first.

        This is what makes picking an exercise two taps instead of a search.
        """
        stmt = (
            select(WorkoutSet.exercise_id, func.count().label("uses"))
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(Workout.user_id == user_id)
            .group_by(WorkoutSet.exercise_id)
            .order_by(func.count().desc(), WorkoutSet.exercise_id)
            .limit(limit)
        )
        rows = await self._session.execute(stmt)
        return [row[0] for row in rows]

    async def count_completed(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Workout)
            .where(
                Workout.user_id == user_id,
                Workout.status == WorkoutStatus.COMPLETED.value,
            )
        )
        return await self._session.scalar(stmt) or 0

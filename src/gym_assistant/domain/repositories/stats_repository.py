"""Aggregation queries behind the reports.

Sums and counts are done in SQL. Anything that needs a training formula -
estimated maxima, what counts as volume for a muscle group - is fetched as
rows and computed in ``analytics.metrics``, so a formula never exists in two
places at once.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, Select, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from gym_assistant.domain.models import Exercise, Workout, WorkoutSet, WorkoutStatus


class StatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _own_sets(self, user_id: int, since: datetime | None) -> Select[tuple[WorkoutSet]]:
        stmt = (
            select(WorkoutSet)
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(Workout.user_id == user_id)
        )
        if since is not None:
            stmt = stmt.where(WorkoutSet.performed_at >= since)
        return stmt

    async def sets_with_exercises(
        self, user_id: int, *, since: datetime | None = None
    ) -> list[WorkoutSet]:
        """Sets with their exercise and muscle groups preloaded.

        Read as rows rather than aggregated in SQL because muscle-group volume
        weights a secondary muscle at half a set - a training convention, not
        a database one, and it belongs next to the other formulas.
        """
        stmt = (
            self._own_sets(user_id, since)
            .options(
                selectinload(WorkoutSet.exercise).selectinload(Exercise.primary_muscle_group),
                selectinload(WorkoutSet.exercise).selectinload(Exercise.secondary_muscle_groups),
            )
            .order_by(WorkoutSet.performed_at)
        )
        return list(await self._session.scalars(stmt))

    async def sets_of_exercise(
        self, user_id: int, exercise_id: int, *, since: datetime | None = None
    ) -> list[WorkoutSet]:
        stmt = (
            self._own_sets(user_id, since)
            .where(WorkoutSet.exercise_id == exercise_id)
            .order_by(WorkoutSet.performed_at)
        )
        return list(await self._session.scalars(stmt))

    async def weekly_tonnage(
        self, user_id: int, *, since: datetime | None = None
    ) -> list[tuple[date, Decimal]]:
        """Weight moved per ISO week.

        Weeks are cut in UTC, which shifts a Monday-morning session by a few
        hours for anyone east of London. Not worth a per-user timezone until
        the bot has users in more than one.
        """
        week = func.date_trunc("week", WorkoutSet.performed_at)
        stmt = (
            select(week.label("week"), func.sum(WorkoutSet.weight_kg * WorkoutSet.reps))
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(
                Workout.user_id == user_id,
                WorkoutSet.weight_kg.is_not(None),
                WorkoutSet.reps.is_not(None),
            )
            .group_by(week)
            .order_by(week)
        )
        if since is not None:
            stmt = stmt.where(WorkoutSet.performed_at >= since)

        rows = await self._session.execute(stmt)
        return [(row[0].date(), Decimal(row[1] or 0)) for row in rows]

    async def workout_days(
        self, user_id: int, *, since: datetime | None = None
    ) -> list[tuple[date, int]]:
        """Days that hold a completed session, with how many sets each holds."""
        day = cast(Workout.started_at, Date)
        stmt = (
            select(day.label("day"), func.count(WorkoutSet.id))
            .select_from(Workout)
            .join(WorkoutSet, WorkoutSet.workout_id == Workout.id)
            .where(
                Workout.user_id == user_id,
                Workout.status == WorkoutStatus.COMPLETED.value,
            )
            .group_by(day)
            .order_by(day)
        )
        if since is not None:
            stmt = stmt.where(Workout.started_at >= since)

        rows = await self._session.execute(stmt)
        return [(row[0], int(row[1])) for row in rows]

    async def exercises_used(self, user_id: int) -> list[Exercise]:
        """Every exercise this user has ever logged, most-used first."""
        stmt = (
            select(Exercise)
            .join(WorkoutSet, WorkoutSet.exercise_id == Exercise.id)
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(Workout.user_id == user_id)
            .group_by(Exercise.id)
            .order_by(func.count(WorkoutSet.id).desc(), Exercise.name_ru)
        )
        return list(await self._session.scalars(stmt))

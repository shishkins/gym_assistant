"""Workout use cases: the core of the product.

Logging a set is the action this whole application exists to make fast, so
the shapes here are built around it: what to prefill, what changed, and
whether the set that was just entered beat anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.analytics.metrics import (
    best_estimate,
    estimated_one_rep_max,
    total_tonnage,
    working_sets,
)
from gym_assistant.domain.models import Exercise, Workout, WorkoutSet, WorkoutStatus
from gym_assistant.domain.parsing import ParsedSet
from gym_assistant.domain.repositories.exercise_repository import ExerciseRepository
from gym_assistant.domain.repositories.workout_repository import WorkoutRepository

# A session left open this long is over; the user simply never said so.
STALE_AFTER = timedelta(hours=6)


class NoOpenWorkoutError(RuntimeError):
    """A set was logged with no session running."""


class EmptySetError(ValueError):
    """The parsed line carried no reps, no time and no distance."""


@dataclass(frozen=True, slots=True)
class ExerciseHistory:
    """What to show and prefill the moment an exercise is picked."""

    exercise: Exercise
    last_sets: list[WorkoutSet]
    last_performed_at: datetime | None
    best_estimate: Decimal | None
    suggested_weight: Decimal | None
    suggested_reps: int | None

    @property
    def is_first_time(self) -> bool:
        return not self.last_sets


@dataclass(frozen=True, slots=True)
class LoggedSets:
    """The result of one entry: what was stored and what it beat."""

    exercise: Exercise
    sets: list[WorkoutSet]
    is_record: bool
    previous_best: Decimal | None
    new_best: Decimal | None


@dataclass(frozen=True, slots=True)
class WorkoutSummary:
    workout: Workout
    duration_min: int
    total_sets: int
    working_sets: int
    tonnage: Decimal
    by_exercise: list[tuple[Exercise, list[WorkoutSet]]]
    records: list[tuple[Exercise, Decimal]]

    @property
    def is_empty(self) -> bool:
        return self.total_sets == 0


class WorkoutService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._workouts = WorkoutRepository(session)
        self._exercises = ExerciseRepository(session)

    # -- session lifecycle -------------------------------------------------

    async def open_workout(self, user_id: int) -> Workout | None:
        return await self._workouts.open_workout(user_id)

    async def start(self, user_id: int, *, now: datetime | None = None) -> Workout:
        """Starts a session, or returns the one already running.

        Two quick taps are genuinely concurrent, so the partial unique index
        is the authority: on a collision we re-read rather than insert twice.
        """
        existing = await self._workouts.open_workout(user_id)
        if existing is not None:
            return existing

        try:
            async with self._session.begin_nested():
                return await self._workouts.add(
                    Workout(user_id=user_id, started_at=now or datetime.now(UTC))
                )
        except IntegrityError:
            existing = await self._workouts.open_workout(user_id)
            if existing is None:  # pragma: no cover - only on a real DB fault
                raise
            return existing

    async def finish(
        self, user_id: int, *, effort: int | None = None, now: datetime | None = None
    ) -> WorkoutSummary | None:
        workout = await self._workouts.open_workout(user_id)
        if workout is None:
            return None

        sets = await self._workouts.sets_of(workout.id)
        # A session with nothing in it is a false start, not a workout: it
        # would otherwise pollute the training frequency chart.
        workout.status = WorkoutStatus.COMPLETED.value if sets else WorkoutStatus.CANCELLED.value
        workout.finished_at = now or datetime.now(UTC)
        if effort is not None:
            workout.perceived_effort = effort
        await self._session.flush()

        return await self.summary(workout)

    async def cancel(self, user_id: int, *, now: datetime | None = None) -> bool:
        workout = await self._workouts.open_workout(user_id)
        if workout is None:
            return False
        workout.status = WorkoutStatus.CANCELLED.value
        workout.finished_at = now or datetime.now(UTC)
        await self._session.flush()
        return True

    async def close_stale(self, *, now: datetime | None = None) -> list[Workout]:
        """Closes sessions nobody finished. Called on startup and on demand."""
        moment = now or datetime.now(UTC)
        stale = await self._workouts.stale_open(moment - STALE_AFTER)
        for workout in stale:
            sets = await self._workouts.sets_of(workout.id)
            workout.status = (
                WorkoutStatus.COMPLETED.value if sets else WorkoutStatus.CANCELLED.value
            )
            # Dated by the last set, not by "now": the session ended when the
            # user stopped, not when the bot noticed.
            workout.finished_at = sets[-1].performed_at if sets else workout.started_at
        await self._session.flush()
        return stale

    # -- logging -----------------------------------------------------------

    async def history_for(self, user_id: int, exercise: Exercise) -> ExerciseHistory:
        """Everything shown the moment an exercise is chosen."""
        recent = await self._workouts.recent_sets_of_exercise(user_id, exercise.id, limit=30)
        if not recent:
            return ExerciseHistory(
                exercise=exercise,
                last_sets=[],
                last_performed_at=None,
                best_estimate=None,
                suggested_weight=None,
                suggested_reps=None,
            )

        newest = recent[0]
        # "Last time" means the previous session, not the previous set.
        same_day = [
            item for item in recent if item.performed_at.date() == newest.performed_at.date()
        ]
        same_day.reverse()

        prefill = next(
            (item for item in recent if not item.is_warmup and item.reps is not None), newest
        )
        return ExerciseHistory(
            exercise=exercise,
            last_sets=same_day,
            last_performed_at=newest.performed_at,
            best_estimate=best_estimate(recent),
            suggested_weight=prefill.weight_kg,
            suggested_reps=prefill.reps,
        )

    async def log(
        self,
        user_id: int,
        exercise: Exercise,
        parsed: ParsedSet,
        *,
        now: datetime | None = None,
    ) -> LoggedSets:
        if not parsed.has_payload:
            raise EmptySetError("a set needs reps, time or distance")

        workout = await self._workouts.open_workout(user_id)
        if workout is None:
            raise NoOpenWorkoutError("no session is running")

        moment = now or datetime.now(UTC)
        previous_best = await self._best_before(user_id, exercise.id, moment)

        order_index, first_set_index = await self._workouts.next_indexes(workout.id, exercise.id)

        stored: list[WorkoutSet] = []
        for offset in range(parsed.repeat):
            stored.append(
                await self._workouts.add_set(
                    WorkoutSet(
                        workout_id=workout.id,
                        exercise_id=exercise.id,
                        order_index=order_index,
                        set_index=first_set_index + offset,
                        weight_kg=parsed.weight_kg,
                        reps=parsed.reps,
                        duration_sec=parsed.duration_sec,
                        distance_m=parsed.distance_m,
                        rpe=parsed.rpe,
                        is_warmup=parsed.is_warmup,
                        performed_at=moment,
                    )
                )
            )

        new_best = None
        if parsed.weight_kg is not None and parsed.reps is not None and not parsed.is_warmup:
            new_best = estimated_one_rep_max(parsed.weight_kg, parsed.reps)

        is_record = new_best is not None and (previous_best is None or new_best > previous_best)
        return LoggedSets(
            exercise=exercise,
            sets=stored,
            is_record=is_record,
            previous_best=previous_best,
            new_best=new_best,
        )

    async def undo_last(self, user_id: int) -> WorkoutSet | None:
        workout = await self._workouts.open_workout(user_id)
        if workout is None:
            return None
        item = await self._workouts.last_set(workout.id)
        if item is None:
            return None
        await self._workouts.delete_set(item)
        return item

    # -- reading -----------------------------------------------------------

    async def current_sets(self, user_id: int) -> list[WorkoutSet]:
        workout = await self._workouts.open_workout(user_id)
        return [] if workout is None else await self._workouts.sets_of(workout.id)

    async def last_completed(self, user_id: int) -> WorkoutSummary | None:
        workout = await self._workouts.last_completed(user_id)
        return None if workout is None else await self.summary(workout)

    async def frequent_exercises(self, user_id: int, *, limit: int = 6) -> list[Exercise]:
        ids = await self._workouts.frequent_exercise_ids(user_id, limit=limit)
        found = [await self._exercises.get(item, user_id=user_id) for item in ids]
        # A hidden or deleted exercise drops out rather than breaking the row.
        return [exercise for exercise in found if exercise is not None]

    async def summary(self, workout: Workout) -> WorkoutSummary:
        sets = await self._workouts.sets_of(workout.id)

        grouped: dict[int, list[WorkoutSet]] = {}
        for item in sets:
            grouped.setdefault(item.exercise_id, []).append(item)

        by_exercise: list[tuple[Exercise, list[WorkoutSet]]] = []
        records: list[tuple[Exercise, Decimal]] = []
        for exercise_id, items in grouped.items():
            exercise = await self._exercises.get(exercise_id, user_id=workout.user_id)
            if exercise is None:
                continue
            by_exercise.append((exercise, items))

            achieved = best_estimate(items)
            if achieved is None:
                continue
            before = await self._best_before(workout.user_id, exercise_id, workout.started_at)
            if before is None or achieved > before:
                records.append((exercise, achieved))

        finished = workout.finished_at or datetime.now(UTC)
        duration = max(0, int((finished - workout.started_at).total_seconds() // 60))

        return WorkoutSummary(
            workout=workout,
            duration_min=duration,
            total_sets=len(sets),
            working_sets=len(working_sets(sets)),
            tonnage=total_tonnage(sets),
            by_exercise=by_exercise,
            records=records,
        )

    async def _best_before(
        self, user_id: int, exercise_id: int, moment: datetime
    ) -> Decimal | None:
        """Best estimate from everything logged before ``moment``.

        Reads the exercise's history rather than aggregating in SQL so the
        formula stays in one place. At personal scale that history is a few
        hundred rows; if it ever stops being, this becomes a query.
        """
        history = await self._workouts.all_sets_of_exercise(user_id, exercise_id)
        earlier = [item for item in history if item.performed_at < moment]
        return best_estimate(earlier)

"""Workout use cases against a real database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import Exercise, WorkoutStatus
from gym_assistant.domain.parsing import ParsedSet, parse_set_entry
from gym_assistant.domain.services import (
    EmptySetError,
    ExerciseService,
    NoOpenWorkoutError,
    ProfileService,
    WorkoutService,
)

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


async def _user(session: AsyncSession, telegram_id: int) -> int:
    user = await ProfileService(session).get_or_create_user(telegram_id)
    return user.id


async def _bench(session: AsyncSession, user_id: int) -> Exercise:
    found = await ExerciseService(session).search("бенч", user_id=user_id)
    return found[0]


async def _squat(session: AsyncSession, user_id: int) -> Exercise:
    found = await ExerciseService(session).search("присед", user_id=user_id)
    return found[0]


# --- session lifecycle ----------------------------------------------------


async def test_start_and_finish(session: AsyncSession) -> None:
    user_id = await _user(session, 4001)
    service = WorkoutService(session)
    bench = await _bench(session, user_id)

    workout = await service.start(user_id, now=NOW)
    assert workout.is_open

    await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW)
    summary = await service.finish(user_id, now=NOW + timedelta(minutes=45))

    assert summary is not None
    assert summary.workout.status == WorkoutStatus.COMPLETED.value
    assert summary.duration_min == 45
    assert summary.total_sets == 1
    assert summary.tonnage == Decimal("640.00")


async def test_start_twice_returns_the_same_session(session: AsyncSession) -> None:
    """The partial unique index is the authority; two taps must not open two."""
    user_id = await _user(session, 4002)
    service = WorkoutService(session)

    first = await service.start(user_id, now=NOW)
    second = await service.start(user_id, now=NOW)

    assert first.id == second.id


async def test_finishing_an_empty_session_cancels_it(session: AsyncSession) -> None:
    """A false start must not count as a workout in the frequency chart."""
    user_id = await _user(session, 4003)
    service = WorkoutService(session)
    await service.start(user_id, now=NOW)

    summary = await service.finish(user_id, now=NOW)

    assert summary is not None
    assert summary.workout.status == WorkoutStatus.CANCELLED.value
    assert summary.is_empty


async def test_logging_without_a_session_is_refused(session: AsyncSession) -> None:
    user_id = await _user(session, 4004)
    bench = await _bench(session, user_id)

    with pytest.raises(NoOpenWorkoutError):
        await WorkoutService(session).log(user_id, bench, parse_set_entry("80х8"))


async def test_empty_set_is_refused(session: AsyncSession) -> None:
    user_id = await _user(session, 4005)
    service = WorkoutService(session)
    await service.start(user_id, now=NOW)
    bench = await _bench(session, user_id)

    with pytest.raises(EmptySetError):
        await service.log(user_id, bench, ParsedSet(weight_kg=Decimal("80")))


async def test_stale_session_is_closed_and_dated_by_its_last_set(
    session: AsyncSession,
) -> None:
    """A forgotten session ended when the user stopped, not when we noticed."""
    user_id = await _user(session, 4006)
    service = WorkoutService(session)
    bench = await _bench(session, user_id)

    await service.start(user_id, now=NOW)
    await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW + timedelta(minutes=20))

    closed = await service.close_stale(now=NOW + timedelta(hours=9))

    assert len(closed) == 1
    assert closed[0].status == WorkoutStatus.COMPLETED.value
    assert closed[0].finished_at == NOW + timedelta(minutes=20)


# --- logging --------------------------------------------------------------


async def test_repeat_stores_several_sets(session: AsyncSession) -> None:
    user_id = await _user(session, 4007)
    service = WorkoutService(session)
    await service.start(user_id, now=NOW)
    bench = await _bench(session, user_id)

    logged = await service.log(user_id, bench, parse_set_entry("80х8х3"), now=NOW)

    assert len(logged.sets) == 3
    assert [item.set_index for item in logged.sets] == [1, 2, 3]


async def test_set_numbering_continues_per_exercise(session: AsyncSession) -> None:
    """Coming back to an exercise keeps its position and continues its count."""
    user_id = await _user(session, 4008)
    service = WorkoutService(session)
    await service.start(user_id, now=NOW)
    bench = await _bench(session, user_id)
    squat = await _squat(session, user_id)

    await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW)
    await service.log(user_id, squat, parse_set_entry("100х5"), now=NOW)
    again = await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW)

    assert again.sets[0].set_index == 2
    assert again.sets[0].order_index == 0


async def test_undo_removes_only_the_last_set(session: AsyncSession) -> None:
    user_id = await _user(session, 4009)
    service = WorkoutService(session)
    await service.start(user_id, now=NOW)
    bench = await _bench(session, user_id)

    await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW)
    await service.log(user_id, bench, parse_set_entry("85х6"), now=NOW + timedelta(minutes=3))

    removed = await service.undo_last(user_id)

    assert removed is not None
    assert removed.weight_kg == Decimal("85.00")
    assert len(await service.current_sets(user_id)) == 1


async def test_undo_on_an_empty_session_is_harmless(session: AsyncSession) -> None:
    user_id = await _user(session, 4010)
    service = WorkoutService(session)
    await service.start(user_id, now=NOW)

    assert await service.undo_last(user_id) is None


# --- records --------------------------------------------------------------


async def test_first_ever_set_is_a_record(session: AsyncSession) -> None:
    user_id = await _user(session, 4011)
    service = WorkoutService(session)
    await service.start(user_id, now=NOW)
    bench = await _bench(session, user_id)

    logged = await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW)

    assert logged.is_record
    assert logged.previous_best is None
    assert logged.new_best == Decimal("101.3")


async def test_beating_the_estimate_is_a_record(session: AsyncSession) -> None:
    user_id = await _user(session, 4012)
    service = WorkoutService(session)
    bench = await _bench(session, user_id)

    await service.start(user_id, now=NOW)
    await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW)
    await service.finish(user_id, now=NOW + timedelta(hours=1))

    await service.start(user_id, now=NOW + timedelta(days=3))
    logged = await service.log(user_id, bench, parse_set_entry("85х8"), now=NOW + timedelta(days=3))

    assert logged.is_record
    assert logged.previous_best == Decimal("101.3")


async def test_a_lighter_set_is_not_a_record(session: AsyncSession) -> None:
    user_id = await _user(session, 4013)
    service = WorkoutService(session)
    bench = await _bench(session, user_id)

    await service.start(user_id, now=NOW)
    await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW)
    logged = await service.log(
        user_id, bench, parse_set_entry("60х8"), now=NOW + timedelta(minutes=5)
    )

    assert not logged.is_record


async def test_a_warmup_never_sets_a_record(session: AsyncSession) -> None:
    user_id = await _user(session, 4014)
    service = WorkoutService(session)
    await service.start(user_id, now=NOW)
    bench = await _bench(session, user_id)

    logged = await service.log(user_id, bench, parse_set_entry("р 100х5"), now=NOW)

    assert logged.sets[0].is_warmup
    assert not logged.is_record


# --- history and prefill --------------------------------------------------


async def test_history_prefills_from_the_last_working_set(session: AsyncSession) -> None:
    """Prefill is what makes the next set two taps instead of typing."""
    user_id = await _user(session, 4015)
    service = WorkoutService(session)
    bench = await _bench(session, user_id)

    await service.start(user_id, now=NOW)
    await service.log(user_id, bench, parse_set_entry("р 40х10"), now=NOW)
    await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW + timedelta(minutes=5))
    await service.finish(user_id, now=NOW + timedelta(hours=1))

    history = await service.history_for(user_id, bench)

    assert history.suggested_weight == Decimal("80.00")
    assert history.suggested_reps == 8
    assert len(history.last_sets) == 2
    assert history.best_estimate == Decimal("101.3")


async def test_history_is_empty_for_a_new_exercise(session: AsyncSession) -> None:
    user_id = await _user(session, 4016)
    bench = await _bench(session, user_id)

    history = await WorkoutService(session).history_for(user_id, bench)

    assert history.is_first_time
    assert history.suggested_weight is None


async def test_frequent_exercises_are_ordered_by_use(session: AsyncSession) -> None:
    user_id = await _user(session, 4017)
    service = WorkoutService(session)
    bench = await _bench(session, user_id)
    squat = await _squat(session, user_id)

    await service.start(user_id, now=NOW)
    await service.log(user_id, squat, parse_set_entry("100х5х3"), now=NOW)
    await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW)

    frequent = await service.frequent_exercises(user_id)

    assert [exercise.id for exercise in frequent] == [squat.id, bench.id]


# --- summary --------------------------------------------------------------


async def test_summary_groups_by_exercise_and_reports_records(
    session: AsyncSession,
) -> None:
    user_id = await _user(session, 4018)
    service = WorkoutService(session)
    bench = await _bench(session, user_id)
    squat = await _squat(session, user_id)

    await service.start(user_id, now=NOW)
    await service.log(user_id, bench, parse_set_entry("р 40х10"), now=NOW)
    await service.log(user_id, bench, parse_set_entry("80х8х2"), now=NOW)
    await service.log(user_id, squat, parse_set_entry("100х5"), now=NOW)
    summary = await service.finish(user_id, now=NOW + timedelta(minutes=60))

    assert summary is not None
    assert summary.total_sets == 4
    assert summary.working_sets == 3
    # 40*10 + 80*8*2 + 100*5 = 400 + 1280 + 500
    assert summary.tonnage == Decimal("2180.00")
    assert len(summary.by_exercise) == 2
    assert {exercise.id for exercise, _ in summary.records} == {bench.id, squat.id}


async def test_last_completed_skips_cancelled_sessions(session: AsyncSession) -> None:
    user_id = await _user(session, 4019)
    service = WorkoutService(session)
    bench = await _bench(session, user_id)

    await service.start(user_id, now=NOW)
    await service.log(user_id, bench, parse_set_entry("80х8"), now=NOW)
    await service.finish(user_id, now=NOW + timedelta(minutes=30))

    # An empty session that follows must not become "the last workout".
    await service.start(user_id, now=NOW + timedelta(days=1))
    await service.finish(user_id, now=NOW + timedelta(days=1, minutes=1))

    summary = await service.last_completed(user_id)

    assert summary is not None
    assert summary.total_sets == 1

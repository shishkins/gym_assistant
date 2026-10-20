"""The SQL side of the clock: weeks and days grouped in the database."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant import clock
from gym_assistant.domain.parsing import parse_set_entry
from gym_assistant.domain.repositories import StatsRepository
from gym_assistant.domain.services import ExerciseService, ProfileService, WorkoutService

MONDAY_MORNING_UTC = datetime(2026, 10, 18, 23, 0, tzinfo=UTC)  # 06:00 Mon in Vietnam


@pytest.fixture
def vietnam() -> Iterator[None]:
    clock.configure("Asia/Ho_Chi_Minh")
    yield
    clock.configure("UTC")


async def test_weeks_and_days_in_sql_follow_the_bots_clock(
    session: AsyncSession, vietnam: None
) -> None:
    user = await ProfileService(session).get_or_create_user(5150)
    bench = (await ExerciseService(session).search("бенч", user_id=user.id))[0]
    workouts = WorkoutService(session)
    await workouts.start(user.id, now=MONDAY_MORNING_UTC)
    await workouts.log(user.id, bench, parse_set_entry("80х5"), now=MONDAY_MORNING_UTC)
    await workouts.finish(user.id, now=MONDAY_MORNING_UTC.replace(hour=23, minute=50))

    stats = StatsRepository(session)
    weeks = await stats.weekly_tonnage(user.id)
    days = await stats.workout_days(user.id)

    assert [week for week, _ in weeks] == [date(2026, 10, 19)]
    assert [day for day, _ in days] == [date(2026, 10, 19)]

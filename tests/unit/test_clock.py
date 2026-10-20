"""Days and weeks are cut where the people live, not in UTC.

Before the review fix the TIMEZONE setting existed and nothing read it.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest

from gym_assistant import clock
from gym_assistant.analytics.metrics import week_start
from gym_assistant.bot.texts.render import format_when
from gym_assistant.config import Settings

# Monday 2026-10-19, 06:00 in Ho Chi Minh City - still Sunday in UTC.
MONDAY_MORNING_UTC = datetime(2026, 10, 18, 23, 0, tzinfo=UTC)


@pytest.fixture
def vietnam() -> Iterator[None]:
    clock.configure("Asia/Ho_Chi_Minh")
    yield
    clock.configure("UTC")


def test_a_monday_morning_session_belongs_to_monday(vietnam: None) -> None:
    assert clock.local_date(MONDAY_MORNING_UTC) == date(2026, 10, 19)
    assert week_start(MONDAY_MORNING_UTC) == date(2026, 10, 19)


def test_in_utc_the_same_session_would_land_in_the_previous_week() -> None:
    """The control: without a zone the bug is exactly what the review said."""
    assert week_start(MONDAY_MORNING_UTC) == date(2026, 10, 12)


def test_this_mornings_sets_are_today_not_yesterday(vietnam: None) -> None:
    later_that_morning = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)  # 10:00 local

    assert format_when(MONDAY_MORNING_UTC, now=later_that_morning) == "сегодня"


def test_a_misspelt_zone_fails_at_startup() -> None:
    with pytest.raises(ValueError, match="time zone"):
        Settings(bot_token="42:x", timezone="Asia/Ho_Chi_Mihn")  # type: ignore[call-arg]

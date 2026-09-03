"""What the assistant can and cannot reach.

The first block is the one that matters. Everything else here checks the
tools return sensible numbers; those checks would still pass on a system
that happily served someone else's training log.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.ai.tools import HANDLERS, TOOL_DEFINITIONS, ToolContext, run_tool
from gym_assistant.domain.parsing import parse_set_entry
from gym_assistant.domain.services import (
    ExerciseService,
    MeasurementService,
    ProfileService,
    WorkoutService,
)

MINE = 5001
SOMEONE_ELSE = 5002


async def _seed(session: AsyncSession, telegram_id: int, *, weeks: int = 4) -> ToolContext:
    profile = ProfileService(session)
    user = await profile.get_or_create_user(telegram_id, first_name="Тестер")
    exercises = ExerciseService(session)
    workouts = WorkoutService(session)

    bench = (await exercises.search("бенч", user_id=user.id))[0]
    start = datetime.now(UTC) - timedelta(weeks=weeks)
    for week in range(weeks):
        when = start + timedelta(weeks=week)
        await workouts.start(user.id, now=when)
        await workouts.log(user.id, bench, parse_set_entry(f"{70 + week * 2.5}х8х3"), now=when)
        await workouts.finish(user.id, now=when + timedelta(hours=1))

    await MeasurementService(session).record(user.id, weight_kg=Decimal("84.0"), measured_at=start)
    return ToolContext(session=session, user=user)


# --- whose data is this ---------------------------------------------------


async def test_no_tool_accepts_a_user_id() -> None:
    """The rule, checked at the schema rather than at runtime.

    If a tool ever grows a user_id parameter, this fails before anyone has
    to notice that the model started sending one.
    """
    for definition in TOOL_DEFINITIONS:
        properties = definition["input_schema"].get("properties", {})
        assert "user_id" not in properties, definition["name"]


async def test_a_forged_user_id_is_ignored(session: AsyncSession) -> None:
    """The model asking for someone else's profile gets its own."""
    mine = await _seed(session, MINE)
    other = await _seed(session, SOMEONE_ELSE, weeks=1)
    assert mine.user.id != other.user.id

    result = await run_tool(mine, "get_profile", {"user_id": other.user.id})

    expected = await run_tool(mine, "get_profile", {})
    assert result == expected


async def test_a_forged_user_id_does_not_leak_training_data(
    session: AsyncSession,
) -> None:
    mine = await _seed(session, MINE, weeks=4)
    other = await _seed(session, SOMEONE_ELSE, weeks=1)

    forged = await run_tool(
        mine, "get_training_summary", {"user_id": other.user.id, "period": "all"}
    )
    honest = await run_tool(mine, "get_training_summary", {"period": "all"})

    assert forged["workouts"] == honest["workouts"] == 4


async def test_every_declared_tool_has_a_handler() -> None:
    """A tool the model can see but nobody implements is an error it cannot
    recover from."""
    declared = {definition["name"] for definition in TOOL_DEFINITIONS}

    assert declared == set(HANDLERS)


# --- the numbers ----------------------------------------------------------


async def test_training_summary_counts_what_happened(session: AsyncSession) -> None:
    ctx = await _seed(session, MINE, weeks=4)

    result = await run_tool(ctx, "get_training_summary", {"period": "all"})

    assert result["workouts"] == 4
    assert result["sets_working"] == 12
    assert result["tonnage_kg"] > 0


async def test_exercise_progress_returns_a_point_per_day(session: AsyncSession) -> None:
    ctx = await _seed(session, MINE, weeks=4)

    result = await run_tool(ctx, "get_exercise_progress", {"exercise": "жим"})

    assert result["exercise"] == "Жим штанги лёжа"
    assert len(result["points"]) == 4
    assert result["points"][0]["weight_kg"] < result["points"][-1]["weight_kg"]


async def test_an_unknown_exercise_says_so_rather_than_guessing(
    session: AsyncSession,
) -> None:
    """The model must be able to tell "no data" from "no such exercise".

    Search is deliberately forgiving, so this needs a query with nothing in
    common with anything - "жим ушами" still resolves to a bench press, and
    the tool reports the name it resolved to so the model can notice.
    """
    ctx = await _seed(session, MINE, weeks=1)

    result = await run_tool(ctx, "get_exercise_progress", {"exercise": "квазар"})

    assert result["error"] == "not_found"


async def test_recent_workouts_returns_the_requested_number_of_days(
    session: AsyncSession,
) -> None:
    ctx = await _seed(session, MINE, weeks=4)

    result = await run_tool(ctx, "list_recent_workouts", {"limit": 2})

    assert len(result["workouts"]) == 2


async def test_tools_on_an_empty_history_return_empty_not_an_error(
    session: AsyncSession,
) -> None:
    """A new user is a normal case; the model should be told nothing
    happened, not handed a failure."""
    user = await ProfileService(session).get_or_create_user(5003)
    ctx = ToolContext(session=session, user=user)

    summary = await run_tool(ctx, "get_training_summary", {"period": "all"})
    records = await run_tool(ctx, "get_personal_records", {})
    volume = await run_tool(ctx, "get_weekly_volume", {})

    assert summary["workouts"] == 0
    assert records["records"] == []
    assert volume["groups"] == {}


async def test_find_exercise_reaches_the_catalogue(session: AsyncSession) -> None:
    ctx = await _seed(session, MINE, weeks=1)

    result = await run_tool(ctx, "find_exercise", {"query": "бабочка"})

    assert any("Сведение" in item["name"] for item in result["found"])


async def test_an_unknown_tool_raises(session: AsyncSession) -> None:
    ctx = await _seed(session, MINE, weeks=1)

    with pytest.raises(LookupError):
        await run_tool(ctx, "drop_everything", {})

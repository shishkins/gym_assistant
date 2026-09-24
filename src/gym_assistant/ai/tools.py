"""What the assistant is allowed to look at.

Two rules hold this module together, and both are about the same thing.

**The model never sees SQL.** It picks from a fixed list of questions, each
of which is a Python function over the same services the handlers use. There
is no free-form query, so there is nothing to inject into.

**The model never says whose data to read.** ``user_id`` is not a tool
parameter - it comes from ``ToolContext``, built from the Telegram session on
the way in. A model that hallucinates ``user_id: 12345`` gets its own data
back regardless, because the argument does not exist.

Everything here reads. Nothing writes. Write tools are the next round, and
they will need confirmation from the person before they touch anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.analytics.metrics import (
    exercise_progress,
    personal_records,
    total_tonnage,
    weekly_volume_by_group,
    working_sets,
)
from gym_assistant.domain.models import User
from gym_assistant.domain.repositories import MeasurementRepository, StatsRepository
from gym_assistant.domain.services import ExerciseService, ProfileService, WorkoutService

log = structlog.get_logger(__name__)

PERIOD_DAYS = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "all": None}
DEFAULT_PERIOD = "3m"

# A tool result is context the model pays for on every later turn, so these
# are capped at what actually answers a question rather than at what the
# database could return.
MAX_WORKOUTS = 20
MAX_RECORDS = 25
MAX_POINTS = 60
MAX_SEARCH_HITS = 8


@dataclass(frozen=True)
class ToolContext:
    """Whose data this is. Built on the way in, never from model arguments."""

    session: AsyncSession
    user: User


def _since(period: str) -> datetime | None:
    days = PERIOD_DAYS.get(period, PERIOD_DAYS[DEFAULT_PERIOD])
    return None if days is None else datetime.now(UTC) - timedelta(days=days)


def _money(value: Decimal | float | None) -> float | None:
    return None if value is None else round(float(value), 2)


# --- the tools themselves -------------------------------------------------


async def get_profile(ctx: ToolContext) -> dict[str, Any]:
    """Height, age, goal, experience, current weight."""
    summary = await ProfileService(ctx.session).get_summary(
        ctx.user.id, today=datetime.now(UTC).date()
    )
    return {
        "sex": summary.sex.value if summary.sex else None,
        "age": summary.age,
        "height_cm": summary.height_cm,
        "weight_kg": _money(summary.weight_kg),
        "goal": summary.goal.value if summary.goal else None,
        "experience": summary.experience_level.value if summary.experience_level else None,
        "bmi": _money(summary.bmi),
    }


async def get_training_summary(ctx: ToolContext, period: str = DEFAULT_PERIOD) -> dict[str, Any]:
    """How much training happened: sessions, sets, tonnage."""
    stats = StatsRepository(ctx.session)
    since = _since(period)
    sets = await stats.sets_with_exercises(ctx.user.id, since=since)
    days = await stats.workout_days(ctx.user.id, since=since)

    return {
        "period": period,
        "workouts": len(days),
        "sets_total": len(sets),
        "sets_working": len(working_sets(sets)),
        "tonnage_kg": _money(total_tonnage(sets)),
        "per_workout_kg": _money(total_tonnage(sets) / len(days)) if days else None,
    }


async def list_recent_workouts(ctx: ToolContext, limit: int = 5) -> dict[str, Any]:
    """The last sessions, with what was done in each."""
    limit = max(1, min(limit, MAX_WORKOUTS))
    service = WorkoutService(ctx.session)
    stats = StatsRepository(ctx.session)

    sets = await stats.sets_with_exercises(ctx.user.id, since=None)

    # Pick the days first, then aggregate only those. Filtering while
    # grouping needs the day to be known before it is added, which is the
    # kind of loop that quietly returns one day too many.
    wanted = sorted({item.performed_at.date() for item in sets}, reverse=True)[:limit]

    by_day: dict[str, dict[str, Any]] = {
        day.isoformat(): {"date": day.isoformat(), "exercises": {}} for day in wanted
    }
    for item in sets:
        entry = by_day.get(item.performed_at.date().isoformat())
        if entry is None:
            continue
        name = item.exercise.name_ru if item.exercise else "?"
        block = entry["exercises"].setdefault(name, {"sets": 0, "top_weight_kg": None})
        block["sets"] += 1
        if item.weight_kg is not None:
            best = block["top_weight_kg"]
            block["top_weight_kg"] = _money(
                item.weight_kg if best is None else max(Decimal(str(best)), item.weight_kg)
            )

    last = await service.last_completed(ctx.user.id)
    return {
        "workouts": list(by_day.values()),
        "last_finished_at": last.workout.started_at.isoformat() if last else None,
    }


async def get_exercise_progress(
    ctx: ToolContext, exercise: str, period: str = DEFAULT_PERIOD
) -> dict[str, Any]:
    """Working weight and estimated max over time, for one exercise."""
    found = await ExerciseService(ctx.session).search(exercise, user_id=ctx.user.id, limit=1)
    if not found:
        return {"error": "not_found", "query": exercise}

    target = found[0]
    sets = await StatsRepository(ctx.session).sets_of_exercise(
        ctx.user.id, target.id, since=_since(period)
    )
    points = exercise_progress(sets)[-MAX_POINTS:]

    return {
        "exercise": target.name_ru,
        "period": period,
        "points": [
            {
                "date": point.at.isoformat(),
                "weight_kg": _money(point.best_weight),
                "estimated_1rm_kg": _money(point.best_estimate),
            }
            for point in points
        ],
    }


async def get_personal_records(ctx: ToolContext, limit: int = 10) -> dict[str, Any]:
    """Heaviest working set per exercise, heaviest first."""
    limit = max(1, min(limit, MAX_RECORDS))
    sets = await StatsRepository(ctx.session).sets_with_exercises(ctx.user.id)
    return {
        "records": [
            {
                "exercise": record.exercise_name,
                "weight_kg": _money(record.best_weight),
                "reps": record.best_weight_reps,
                "at": record.best_weight_at.date().isoformat() if record.best_weight_at else None,
                "estimated_1rm_kg": _money(record.best_estimate),
            }
            for record in personal_records(sets)[:limit]
        ]
    }


async def get_weekly_volume(ctx: ToolContext, period: str = DEFAULT_PERIOD) -> dict[str, Any]:
    """Working sets per muscle group per week - what is under- and overworked."""
    sets = await StatsRepository(ctx.session).sets_with_exercises(ctx.user.id, since=_since(period))
    volume = weekly_volume_by_group(sets)
    if not volume:
        return {"period": period, "weeks": 0, "groups": {}}

    totals: dict[str, float] = {}
    for week in volume.values():
        for group, count in week.items():
            totals[group] = totals.get(group, 0.0) + count

    weeks = len(volume)
    return {
        "period": period,
        "weeks": weeks,
        "recommended_per_week": [10, 20],
        "groups": {group: round(total / weeks, 1) for group, total in sorted(totals.items())},
    }


async def get_body_weight(ctx: ToolContext, period: str = DEFAULT_PERIOD) -> dict[str, Any]:
    """Weigh-ins over the period, oldest first."""
    history = await MeasurementRepository(ctx.session).history(
        ctx.user.id, since=_since(period), limit=MAX_POINTS
    )
    return {
        "period": period,
        "measurements": [
            {"date": item.measured_at.date().isoformat(), "weight_kg": _money(item.weight_kg)}
            for item in reversed(history)
            if item.weight_kg is not None
        ],
    }


async def find_exercise(ctx: ToolContext, query: str) -> dict[str, Any]:
    """Look up the catalogue - to check an exercise exists before suggesting it."""
    found = await ExerciseService(ctx.session).search(
        query, user_id=ctx.user.id, limit=MAX_SEARCH_HITS
    )
    return {
        "query": query,
        "found": [
            {
                "name": item.name_ru,
                "muscle_group": item.primary_muscle_group.name_ru
                if item.primary_muscle_group
                else None,
                "equipment": item.equipment,
                "compound": item.is_compound,
            }
            for item in found
        ],
    }


# --- what the model is told it can call -----------------------------------
#
# Descriptions are written for the model, not for us: they say when to reach
# for the tool, because a model that picks the wrong one produces a confident
# answer about the wrong numbers.

PERIOD_SCHEMA = {
    "type": "string",
    "enum": list(PERIOD_DAYS),
    "description": "Период: 1m — месяц, 3m — три месяца, 6m, 1y, all — вся история.",
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_profile",
        "description": (
            "Профиль: пол, возраст, рост, текущий вес, цель, опыт, ИМТ. "
            "Вызывай, когда совет зависит от того, кто перед тобой."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_training_summary",
        "description": (
            "Сколько всего было тренировок, подходов и тоннажа за период. "
            "Первое, что стоит спросить на вопрос вида «как у меня дела»."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"period": PERIOD_SCHEMA},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_recent_workouts",
        "description": (
            "Последние тренировки: дата, упражнения, число подходов и лучший вес. "
            "Для вопросов «что я делал в последний раз» и «что тренировать сегодня»."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": MAX_WORKOUTS}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_exercise_progress",
        "description": (
            "Динамика ОДНОГО упражнения: рабочий вес и расчётный максимум по датам. "
            "Главный инструмент для вопросов «растёт ли жим», «когда я застрял». "
            "Название можно писать как угодно — найдётся по синонимам."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "exercise": {
                    "type": "string",
                    "description": "Название упражнения, можно сокращённо: «жим», «присед».",
                },
                "period": PERIOD_SCHEMA,
            },
            "required": ["exercise"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_personal_records",
        "description": "Личные рекорды: самый тяжёлый рабочий подход в каждом упражнении.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": MAX_RECORDS}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_weekly_volume",
        "description": (
            "Рабочих подходов в неделю по группам мышц, плюс рекомендуемый коридор. "
            "Для вопросов о перекосах в программе и о том, что недорабатывается."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"period": PERIOD_SCHEMA},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_body_weight",
        "description": "Взвешивания за период. Нужны, когда речь о наборе или сушке.",
        "input_schema": {
            "type": "object",
            "properties": {"period": PERIOD_SCHEMA},
            "additionalProperties": False,
        },
    },
    {
        "name": "find_exercise",
        "description": (
            "Поиск по справочнику. Проверь этим, что упражнение существует, "
            "прежде чем советовать его — выдумывать названия нельзя."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]

HANDLERS = {
    "get_profile": get_profile,
    "get_training_summary": get_training_summary,
    "list_recent_workouts": list_recent_workouts,
    "get_exercise_progress": get_exercise_progress,
    "get_personal_records": get_personal_records,
    "get_weekly_volume": get_weekly_volume,
    "get_body_weight": get_body_weight,
    "find_exercise": find_exercise,
}


class UnknownToolError(LookupError):
    """The model asked for a tool that does not exist."""


async def run_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Executes one tool call.

    ``user_id`` is deliberately absent from every signature, so an argument
    naming someone else cannot be honoured even by accident. Anything the
    model sends that a tool does not declare is dropped here rather than
    passed through.
    """
    handler = HANDLERS.get(name)
    if handler is None:
        raise UnknownToolError(name)

    allowed = _allowed_arguments(name)
    clean = {key: value for key, value in arguments.items() if key in allowed}
    if len(clean) != len(arguments):
        log.info("ai_tool_extra_args", tool=name, dropped=sorted(set(arguments) - allowed))

    result: dict[str, Any] = await handler(ctx, **clean)  # type: ignore[operator]
    return result


def _allowed_arguments(name: str) -> set[str]:
    for definition in TOOL_DEFINITIONS:
        if definition["name"] == name:
            schema: dict[str, Any] = definition["input_schema"]
            return set(schema.get("properties", {}))
    return set()

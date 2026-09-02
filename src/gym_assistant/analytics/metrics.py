"""Training metrics.

Pure functions over sets: no database, no I/O. Everything the bot reports
about progress is computed here, so this is the one place a formula can be
wrong - and the one place that is cheap to test exhaustively.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from gym_assistant.domain.models import WorkoutSet

# Epley overestimates badly past a dozen reps: a 20-rep set is a test of
# endurance, not of maximum strength, and treating it as one flatters the
# number. Above this the estimate is simply not reported.
MAX_REPS_FOR_ESTIMATE = 12


def estimated_one_rep_max(weight_kg: Decimal, reps: int) -> Decimal | None:
    """Epley's estimate: ``weight × (1 + reps / 30)``.

    Returns ``None`` when the set says nothing useful about a maximum -
    zero reps, or so many that the formula stops being meaningful.
    """
    if reps < 1 or reps > MAX_REPS_FOR_ESTIMATE or weight_kg <= 0:
        return None
    estimate = weight_kg * (Decimal(1) + Decimal(reps) / Decimal(30))
    return estimate.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def set_tonnage(item: WorkoutSet) -> Decimal:
    """Weight moved by one set. Bodyweight work counts as zero tonnage."""
    if item.weight_kg is None or item.reps is None:
        return Decimal(0)
    return item.weight_kg * Decimal(item.reps)


def total_tonnage(sets: Iterable[WorkoutSet]) -> Decimal:
    total = sum((set_tonnage(item) for item in sets), Decimal(0))
    return total.quantize(Decimal("0.01"))


def is_working_set(item: WorkoutSet) -> bool:
    """Warm-ups are excluded from volume: they are preparation, not work."""
    return not item.is_warmup


def working_sets(sets: Iterable[WorkoutSet]) -> list[WorkoutSet]:
    return [item for item in sets if is_working_set(item)]


def best_estimate(sets: Iterable[WorkoutSet]) -> Decimal | None:
    """Highest e1RM among the working sets, or ``None``."""
    estimates = [
        estimate
        for item in working_sets(sets)
        if item.weight_kg is not None
        and item.reps is not None
        and (estimate := estimated_one_rep_max(item.weight_kg, item.reps)) is not None
    ]
    return max(estimates) if estimates else None


def heaviest_weight(sets: Iterable[WorkoutSet]) -> Decimal | None:
    """Heaviest working weight, regardless of reps."""
    weights = [item.weight_kg for item in working_sets(sets) if item.weight_kg is not None]
    return max(weights) if weights else None


# A movement loads its secondary muscles too, but not as hard. Half a set is
# the convention most volume guidance is written in; it is a rule of thumb,
# not a measurement, and it lives here so it is stated once.
SECONDARY_SET_WEIGHT = 0.5

# The band most hypertrophy guidance settles on, drawn on the volume chart as
# context rather than as a target to hit exactly.
RECOMMENDED_WEEKLY_SETS = (10, 20)


@dataclass(frozen=True, slots=True)
class PersonalRecord:
    """Best of one exercise, by both measures people actually use."""

    exercise_id: int
    exercise_name: str
    best_weight: Decimal | None
    best_weight_reps: int | None
    best_weight_at: datetime | None
    best_estimate: Decimal | None
    best_estimate_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProgressPoint:
    """One training day's best effort in a single exercise."""

    at: date
    best_weight: Decimal | None
    best_estimate: Decimal | None


def week_start(moment: datetime | date) -> date:
    """Monday of the week this moment falls in."""
    day = moment.date() if isinstance(moment, datetime) else moment
    return day - timedelta(days=day.weekday())


def weekly_tonnage_map(sets: Iterable[WorkoutSet]) -> dict[date, Decimal]:
    totals: dict[date, Decimal] = defaultdict(lambda: Decimal(0))
    for item in sets:
        totals[week_start(item.performed_at)] += set_tonnage(item)
    return dict(totals)


def weekly_working_sets(sets: Iterable[WorkoutSet]) -> dict[date, int]:
    counts: dict[date, int] = defaultdict(int)
    for item in working_sets(sets):
        counts[week_start(item.performed_at)] += 1
    return dict(counts)


def weekly_volume_by_group(sets: Iterable[WorkoutSet]) -> dict[date, dict[str, float]]:
    """Working sets per muscle group per week.

    Requires the exercise and its muscle groups to be loaded; a set whose
    exercise is missing is skipped rather than guessed at.
    """
    volume: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for item in working_sets(sets):
        exercise = item.exercise
        if exercise is None:  # pragma: no cover - defensive
            continue
        week = week_start(item.performed_at)
        volume[week][exercise.primary_muscle_group.name_ru] += 1.0
        for group in exercise.secondary_muscle_groups:
            volume[week][group.name_ru] += SECONDARY_SET_WEIGHT
    return {week: dict(groups) for week, groups in volume.items()}


def exercise_progress(sets: Iterable[WorkoutSet]) -> list[ProgressPoint]:
    """One point per training day: the best working set of that day."""
    by_day: dict[date, list[WorkoutSet]] = defaultdict(list)
    for item in working_sets(sets):
        by_day[item.performed_at.date()].append(item)

    points = [
        ProgressPoint(
            at=day,
            best_weight=heaviest_weight(items),
            best_estimate=best_estimate(items),
        )
        for day, items in sorted(by_day.items())
    ]
    # A day of pure bodyweight work carries neither measure and would draw a
    # gap in the line for no reason.
    return [point for point in points if point.best_weight or point.best_estimate]


def personal_records(sets: Iterable[WorkoutSet]) -> list[PersonalRecord]:
    """Best per exercise, heaviest first.

    Reported by both measures: the heaviest bar is what a lifter calls a
    personal best, the estimate is the fairer comparison across rep ranges.
    """
    by_exercise: dict[int, list[WorkoutSet]] = defaultdict(list)
    for item in working_sets(sets):
        if item.weight_kg is not None:
            by_exercise[item.exercise_id].append(item)

    records: list[PersonalRecord] = []
    for exercise_id, items in by_exercise.items():
        exercise = items[0].exercise
        if exercise is None:  # pragma: no cover - defensive
            continue

        heaviest = max(items, key=lambda entry: entry.weight_kg or Decimal(0))
        estimated = [
            (estimate, entry)
            for entry in items
            if entry.reps is not None
            and entry.weight_kg is not None
            and (estimate := estimated_one_rep_max(entry.weight_kg, entry.reps)) is not None
        ]
        best = max(estimated, key=lambda pair: pair[0]) if estimated else None

        records.append(
            PersonalRecord(
                exercise_id=exercise_id,
                exercise_name=exercise.name_ru,
                best_weight=heaviest.weight_kg,
                best_weight_reps=heaviest.reps,
                best_weight_at=heaviest.performed_at,
                best_estimate=best[0] if best else None,
                best_estimate_at=best[1].performed_at if best else None,
            )
        )

    records.sort(key=lambda record: record.best_weight or Decimal(0), reverse=True)
    return records


def moving_average(
    points: Sequence[tuple[date, Decimal]], *, window: int = 7
) -> list[tuple[date, Decimal]]:
    """Trailing average over a window of DAYS, not of points.

    Weigh-ins are irregular; averaging the last N readings would stretch the
    window over months during a gap and hide exactly the trend it is meant
    to show.
    """
    if not points:
        return []

    smoothed: list[tuple[date, Decimal]] = []
    for index, (day, _) in enumerate(points):
        earliest = day - timedelta(days=window - 1)
        recent = [value for other, value in points[: index + 1] if other >= earliest]
        smoothed.append((day, sum(recent, Decimal(0)) / Decimal(len(recent))))
    return smoothed

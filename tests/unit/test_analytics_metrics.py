"""Aggregation formulas behind the reports.

Every number the bot claims about progress comes from here, so a wrong
formula is a lie the user has no way to catch. These are pure functions
over in-memory objects: exhaustive is cheap.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from gym_assistant.analytics.metrics import (
    SECONDARY_SET_WEIGHT,
    estimated_one_rep_max,
    exercise_progress,
    heaviest_weight,
    moving_average,
    personal_records,
    set_tonnage,
    total_tonnage,
    week_start,
    weekly_tonnage_map,
    weekly_volume_by_group,
    weekly_working_sets,
    working_sets,
)

MONDAY = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)


def _group(name: str) -> SimpleNamespace:
    return SimpleNamespace(name_ru=name)


def _exercise(name: str = "Жим", primary: str = "Грудь", secondary: tuple[str, ...] = ()):
    return SimpleNamespace(
        name_ru=name,
        primary_muscle_group=_group(primary),
        secondary_muscle_groups=[_group(item) for item in secondary],
    )


def _set(
    *,
    weight: str | None = "80",
    reps: int | None = 8,
    at: datetime = MONDAY,
    warmup: bool = False,
    exercise_id: int = 1,
    exercise: SimpleNamespace | None = None,
    duration: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        weight_kg=Decimal(weight) if weight is not None else None,
        reps=reps,
        duration_sec=duration,
        distance_m=None,
        is_warmup=warmup,
        performed_at=at,
        exercise_id=exercise_id,
        exercise=exercise if exercise is not None else _exercise(),
    )


# --- estimates ------------------------------------------------------------


@pytest.mark.parametrize(
    ("weight", "reps", "expected"),
    [
        ("100", 1, Decimal("103.3")),
        ("80", 8, Decimal("101.3")),
        ("100", 5, Decimal("116.7")),
        ("60", 12, Decimal("84.0")),
    ],
)
def test_estimated_one_rep_max(weight: str, reps: int, expected: Decimal) -> None:
    assert estimated_one_rep_max(Decimal(weight), reps) == expected


@pytest.mark.parametrize("reps", [13, 20, 100])
def test_estimate_is_refused_past_twelve_reps(reps: int) -> None:
    """Past a dozen reps Epley measures endurance and flatters the number."""
    assert estimated_one_rep_max(Decimal("60"), reps) is None


@pytest.mark.parametrize(("weight", "reps"), [("0", 8), ("-10", 8), ("80", 0)])
def test_estimate_refuses_nonsense(weight: str, reps: int) -> None:
    assert estimated_one_rep_max(Decimal(weight), reps) is None


# --- tonnage --------------------------------------------------------------


def test_set_tonnage() -> None:
    assert set_tonnage(_set(weight="80", reps=8)) == Decimal("640")


def test_bodyweight_set_has_no_tonnage() -> None:
    """Nothing was lifted that we can weigh, so nothing is counted."""
    assert set_tonnage(_set(weight=None, reps=12)) == Decimal(0)


def test_timed_set_has_no_tonnage() -> None:
    assert set_tonnage(_set(weight=None, reps=None, duration=60)) == Decimal(0)


def test_total_tonnage_includes_warmups() -> None:
    """Warm-ups are work: they are excluded from VOLUME, not from tonnage."""
    total = total_tonnage([_set(weight="40", reps=10, warmup=True), _set(weight="80", reps=8)])
    assert total == Decimal("1040.00")


# --- working sets ---------------------------------------------------------


def test_working_sets_excludes_warmups() -> None:
    items = [_set(warmup=True), _set(), _set()]
    assert len(working_sets(items)) == 2


def test_heaviest_weight_ignores_warmups() -> None:
    """A heavy warm-up must not become the number reported as a best."""
    items = [_set(weight="120", warmup=True), _set(weight="90")]
    assert heaviest_weight(items) == Decimal("90")


def test_heaviest_weight_without_weights() -> None:
    assert heaviest_weight([_set(weight=None, reps=10)]) is None


# --- weeks ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (date(2026, 6, 1), date(2026, 6, 1)),  # Monday itself
        (date(2026, 6, 7), date(2026, 6, 1)),  # Sunday belongs to the same week
        (date(2026, 6, 8), date(2026, 6, 8)),  # next Monday
        (datetime(2026, 6, 3, 23, 59, tzinfo=UTC), date(2026, 6, 1)),
    ],
)
def test_week_start(moment: date | datetime, expected: date) -> None:
    assert week_start(moment) == expected


def test_weekly_tonnage_map_buckets_by_week() -> None:
    items = [
        _set(weight="80", reps=8, at=MONDAY),
        _set(weight="80", reps=8, at=MONDAY + timedelta(days=6)),
        _set(weight="100", reps=5, at=MONDAY + timedelta(days=7)),
    ]

    weekly = weekly_tonnage_map(items)

    assert weekly[date(2026, 6, 1)] == Decimal("1280")
    assert weekly[date(2026, 6, 8)] == Decimal("500")


def test_weekly_working_sets_counts_only_working() -> None:
    items = [_set(warmup=True), _set(), _set(at=MONDAY + timedelta(days=8))]

    counts = weekly_working_sets(items)

    assert counts[date(2026, 6, 1)] == 1
    assert counts[date(2026, 6, 8)] == 1


# --- volume by muscle group ----------------------------------------------


def test_secondary_muscles_count_as_half_a_set() -> None:
    """The convention volume guidance is written in, stated once."""
    bench = _exercise("Жим", "Грудь", ("Трицепс", "Плечи"))

    volume = weekly_volume_by_group([_set(exercise=bench)])

    week = volume[date(2026, 6, 1)]
    assert week["Грудь"] == 1.0
    assert week["Трицепс"] == SECONDARY_SET_WEIGHT
    assert week["Плечи"] == SECONDARY_SET_WEIGHT


def test_volume_accumulates_across_exercises() -> None:
    bench = _exercise("Жим", "Грудь", ("Трицепс",))
    dips = _exercise("Брусья", "Грудь", ("Трицепс",))

    volume = weekly_volume_by_group([_set(exercise=bench), _set(exercise=dips)])

    assert volume[date(2026, 6, 1)]["Грудь"] == 2.0
    assert volume[date(2026, 6, 1)]["Трицепс"] == 1.0


def test_volume_excludes_warmups() -> None:
    bench = _exercise("Жим", "Грудь")
    volume = weekly_volume_by_group([_set(exercise=bench, warmup=True)])
    assert volume == {}


# --- progress -------------------------------------------------------------


def test_exercise_progress_is_one_point_per_day() -> None:
    items = [
        _set(weight="80", reps=8, at=MONDAY),
        _set(weight="85", reps=6, at=MONDAY + timedelta(hours=1)),
        _set(weight="90", reps=5, at=MONDAY + timedelta(days=3)),
    ]

    points = exercise_progress(items)

    assert len(points) == 2
    assert points[0].best_weight == Decimal("85")
    assert points[1].best_weight == Decimal("90")


def test_progress_skips_days_with_nothing_to_plot() -> None:
    """A bodyweight-only day carries neither measure and would draw a gap."""
    items = [
        _set(weight=None, reps=12, at=MONDAY),
        _set(weight="80", at=MONDAY + timedelta(days=2)),
    ]

    points = exercise_progress(items)

    assert [point.at for point in points] == [date(2026, 6, 3)]


def test_progress_is_sorted_by_day() -> None:
    items = [_set(at=MONDAY + timedelta(days=5)), _set(at=MONDAY)]
    points = exercise_progress(items)
    assert points[0].at < points[1].at


# --- personal records -----------------------------------------------------


def test_personal_records_report_both_measures() -> None:
    items = [
        _set(weight="80", reps=8, at=MONDAY),
        _set(weight="95", reps=2, at=MONDAY + timedelta(days=3)),
    ]

    records = personal_records(items)

    assert len(records) == 1
    record = records[0]
    # Heaviest bar and best estimate need not be the same set.
    assert record.best_weight == Decimal("95")
    assert record.best_weight_reps == 2
    assert record.best_estimate == Decimal("101.3")
    assert record.best_estimate_at == MONDAY


def test_personal_records_ignore_warmups() -> None:
    items = [_set(weight="150", warmup=True), _set(weight="90")]
    assert personal_records(items)[0].best_weight == Decimal("90")


def test_personal_records_sorted_heaviest_first() -> None:
    squat = _exercise("Присед", "Квадрицепс")
    items = [
        _set(weight="80", exercise_id=1),
        _set(weight="140", exercise_id=2, exercise=squat),
    ]

    records = personal_records(items)

    assert [record.exercise_name for record in records] == ["Присед", "Жим"]


def test_personal_records_skip_bodyweight_only_exercises() -> None:
    """Nothing to compare: a rep count is not a weight."""
    assert personal_records([_set(weight=None, reps=15)]) == []


# --- moving average -------------------------------------------------------


def test_moving_average_uses_a_window_of_days() -> None:
    points = [
        (date(2026, 6, 1), Decimal("84")),
        (date(2026, 6, 2), Decimal("86")),
        (date(2026, 6, 3), Decimal("85")),
    ]

    smoothed = moving_average(points, window=7)

    assert smoothed[0][1] == Decimal("84")
    assert smoothed[1][1] == Decimal("85")
    assert smoothed[2][1] == Decimal("85")


def test_moving_average_drops_readings_outside_the_window() -> None:
    """Averaging the last N readings would stretch over a gap and hide the trend."""
    points = [
        (date(2026, 6, 1), Decimal("90")),
        (date(2026, 7, 1), Decimal("80")),
    ]

    smoothed = moving_average(points, window=7)

    assert smoothed[1][1] == Decimal("80")


def test_moving_average_of_nothing() -> None:
    assert moving_average([]) == []

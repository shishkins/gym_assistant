"""Chart rendering.

A chart cannot be asserted pixel by pixel, so these check the two things
that actually break: that a chart is produced at all for plausible data,
and that it is deliberately NOT produced when the data would say nothing.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from gym_assistant.analytics import charts
from gym_assistant.analytics.metrics import ProgressPoint, moving_average

MONDAY = date(2026, 6, 1)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _progress(count: int) -> list[ProgressPoint]:
    return [
        ProgressPoint(
            at=MONDAY + timedelta(days=index * 7),
            best_weight=Decimal(80 + index),
            best_estimate=Decimal(100 + index),
        )
        for index in range(count)
    ]


def _weeks(count: int) -> list[tuple[date, Decimal]]:
    return [
        (MONDAY + timedelta(days=index * 7), Decimal(9000 + index * 100)) for index in range(count)
    ]


# --- what gets drawn ------------------------------------------------------


def test_progress_chart_is_a_png() -> None:
    image = charts.exercise_progress_chart("Жим штанги лёжа", _progress(6))
    assert image is not None
    assert image.startswith(PNG_MAGIC)


def test_progress_chart_without_a_trend_line() -> None:
    """Two points draw a line but no trend: a trend needs at least three."""
    assert charts.exercise_progress_chart("Жим", _progress(2)) is not None


def test_tonnage_chart_is_a_png() -> None:
    image = charts.weekly_tonnage_chart(_weeks(8))
    assert image is not None and image.startswith(PNG_MAGIC)


def test_volume_chart_is_a_png() -> None:
    volume = {
        MONDAY + timedelta(days=week * 7): {"Грудь": 6.0, "Спина": 8.5, "Трицепс": 3.0}
        for week in range(4)
    }
    image = charts.muscle_volume_chart(volume)
    assert image is not None and image.startswith(PNG_MAGIC)


def test_volume_chart_from_a_single_week() -> None:
    """One week is still an average worth drawing against the band."""
    volume = {MONDAY: {"Грудь": 12.0}}
    assert charts.muscle_volume_chart(volume) is not None


def test_body_weight_chart_is_a_png() -> None:
    points = [
        (MONDAY + timedelta(days=day), Decimal(84) - Decimal(day) / 20) for day in range(0, 30, 3)
    ]
    image = charts.body_weight_chart(points, moving_average(points))
    assert image is not None and image.startswith(PNG_MAGIC)


def test_frequency_chart_is_a_png() -> None:
    days = [(MONDAY + timedelta(days=day), 20) for day in (0, 2, 4, 7, 9, 14)]
    image = charts.frequency_chart(days)
    assert image is not None and image.startswith(PNG_MAGIC)


# --- what deliberately is not drawn --------------------------------------


@pytest.mark.parametrize("count", [0, 1])
def test_progress_chart_refuses_too_few_points(count: int) -> None:
    """One point is a dot, not a trend; a sentence beats an empty chart."""
    assert charts.exercise_progress_chart("Жим", _progress(count)) is None


@pytest.mark.parametrize("count", [0, 1])
def test_tonnage_chart_refuses_too_few_weeks(count: int) -> None:
    assert charts.weekly_tonnage_chart(_weeks(count)) is None


def test_volume_chart_refuses_empty_data() -> None:
    assert charts.muscle_volume_chart({}) is None


def test_body_weight_chart_refuses_a_single_reading() -> None:
    points = [(MONDAY, Decimal("84"))]
    assert charts.body_weight_chart(points, moving_average(points)) is None


def test_frequency_chart_refuses_a_single_day() -> None:
    assert charts.frequency_chart([(MONDAY, 12)]) is None


# --- properties that must hold -------------------------------------------


def test_charts_do_not_leak_figures() -> None:
    """The process runs for weeks; an unclosed figure per report adds up."""
    import matplotlib.pyplot as plt

    before = len(plt.get_fignums())
    for _ in range(5):
        charts.weekly_tonnage_chart(_weeks(6))
    assert len(plt.get_fignums()) == before


def test_progress_chart_survives_gaps_in_the_data() -> None:
    """A day with an estimate but no weight, and the reverse, must not crash."""
    points = [
        ProgressPoint(at=MONDAY, best_weight=Decimal("80"), best_estimate=None),
        ProgressPoint(
            at=MONDAY + timedelta(days=7), best_weight=None, best_estimate=Decimal("101")
        ),
        ProgressPoint(
            at=MONDAY + timedelta(days=14), best_weight=Decimal("85"), best_estimate=None
        ),
    ]
    assert charts.exercise_progress_chart("Жим", points) is not None

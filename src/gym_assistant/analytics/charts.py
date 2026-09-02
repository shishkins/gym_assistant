"""Rendering charts to PNG bytes.

Every function takes already-computed numbers and returns bytes, or ``None``
when there is nothing worth drawing. Deciding that an empty chart is not
worth sending belongs here rather than in a handler: "not enough data yet"
is a property of the data, and a chart with one point is a worse answer than
a sentence saying so.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.dates import DateFormatter, date2num
from matplotlib.figure import Figure

from gym_assistant.analytics.metrics import (
    RECOMMENDED_WEEKLY_SETS,
    ProgressPoint,
    week_start,
)
from gym_assistant.analytics.style import (
    ACCENT,
    GROUP_COLOURS,
    MUTED,
    NEUTRAL,
    POSITIVE,
    new_figure,
)

# Nothing at all is the only case worth refusing. A single point is a poor
# trend but an honest picture, and refusing it means a new user sees the words
# "данных слишком мало" for their first fortnight - which reads as a broken
# bot, not as patience. Raised from two after the iteration 4 review.
MIN_POINTS = 1

# Below this a line says more about the last session than about progress, so
# the trend is left off rather than invented.
MIN_POINTS_FOR_TREND = 3


def _to_png(figure: Figure) -> bytes:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    # Figures are not garbage collected on their own; leaving them open leaks
    # memory in a process that runs for weeks.
    figure.clf()
    plt.close(figure)
    return buffer.getvalue()


def _format_dates(axes: Axes) -> None:
    axes.xaxis.set_major_formatter(DateFormatter("%d.%m"))


def exercise_progress_chart(name: str, points: Sequence[ProgressPoint]) -> bytes | None:
    """Working weight and estimated maximum over time, with a trend line."""
    if len(points) < MIN_POINTS:
        return None

    # date2num rather than raw dates: matplotlib accepts both at runtime, but
    # only the numeric form is typed, and the axis formatter reads it the same.
    days = date2num([point.at for point in points])
    weights = [float(point.best_weight) if point.best_weight else np.nan for point in points]
    estimates = [float(point.best_estimate) if point.best_estimate else np.nan for point in points]

    figure, axes = new_figure(f"Динамика: {name}")
    axes.plot(days, weights, marker="o", color=ACCENT, label="Рабочий вес", linewidth=2)
    axes.plot(
        days,
        estimates,
        marker="o",
        markersize=4,
        color=NEUTRAL,
        label="Расчётный максимум",
        linewidth=1.4,
        alpha=0.9,
    )

    usable = [(index, value) for index, value in enumerate(weights) if not np.isnan(value)]
    if len(usable) >= MIN_POINTS_FOR_TREND:
        xs = np.array([index for index, _ in usable], dtype=float)
        ys = np.array([value for _, value in usable], dtype=float)
        slope, intercept = np.polyfit(xs, ys, 1)
        trend = slope * np.arange(len(days)) + intercept
        axes.plot(days, trend, color=POSITIVE, linestyle="--", linewidth=1.4, label="Тренд")

    axes.set_ylabel("кг")
    axes.legend(loc="upper left")
    _format_dates(axes)
    figure.autofmt_xdate(rotation=0, ha="center")
    return _to_png(figure)


def weekly_tonnage_chart(weeks: Sequence[tuple[date, Decimal]]) -> bytes | None:
    """Total weight moved per week."""
    if len(weeks) < MIN_POINTS:
        return None

    labels = [day.strftime("%d.%m") for day, _ in weeks]
    values = [float(value) for _, value in weeks]

    figure, axes = new_figure("Тоннаж по неделям")
    axes.bar(labels, values, color=ACCENT, width=0.6)
    axes.set_ylabel("кг за неделю")
    axes.tick_params(axis="x", rotation=45)

    # An average drawn through a single bar is the bar again, labelled twice.
    if len(values) > 1:
        average = sum(values) / len(values)
        axes.axhline(average, color=MUTED, linestyle=":", linewidth=1.2)
        axes.text(
            len(labels) - 0.4,
            average,
            f"среднее {average:,.0f}".replace(",", " "),
            color=MUTED,
            fontsize=9,
            va="bottom",
            ha="right",
        )
    return _to_png(figure)


def muscle_volume_chart(volume: dict[date, dict[str, float]]) -> bytes | None:
    """Average working sets per week, one bar per muscle group.

    Deliberately not a stack over time. The 10-20 band is guidance for ONE
    muscle group, and drawn behind a stacked total it silently changes
    meaning - every week clears 20 once six groups are added together, which
    says nothing about whether the chest got enough work. Horizontal bars put
    each group against the band it actually belongs to.
    """
    if not volume:
        return None

    weeks = len(volume)
    totals: dict[str, float] = {}
    for week in volume.values():
        for group, sets in week.items():
            totals[group] = totals.get(group, 0.0) + sets

    averages = sorted(
        ((group, total / weeks) for group, total in totals.items()),
        key=lambda pair: pair[1],
    )
    if not averages:
        return None

    names = [group for group, _ in averages]
    values = [value for _, value in averages]

    figure, axes = new_figure("Объём: рабочих подходов в неделю")
    low, high = RECOMMENDED_WEEKLY_SETS
    axes.axvspan(low, high, color=POSITIVE, alpha=0.12)
    axes.bar_label(
        axes.barh(
            names,
            values,
            color=[GROUP_COLOURS[index % len(GROUP_COLOURS)] for index in range(len(names))],
            height=0.65,
        ),
        fmt="%.1f",
        padding=4,
        color=MUTED,
        fontsize=9,
    )
    axes.set_xlabel(f"в среднем за неделю · зона {low}–{high}")
    axes.grid(axis="y", visible=False)
    axes.margins(x=0.12)
    return _to_png(figure)


def body_weight_chart(
    points: Sequence[tuple[date, Decimal]], smoothed: Sequence[tuple[date, Decimal]]
) -> bytes | None:
    """Weigh-ins with a trailing average over them."""
    if len(points) < MIN_POINTS:
        return None

    figure, axes = new_figure("Вес тела")
    axes.plot(
        date2num([day for day, _ in points]),
        [float(value) for _, value in points],
        marker="o",
        markersize=4,
        linestyle="none",
        color=MUTED,
        label="Взвешивания",
    )
    axes.plot(
        date2num([day for day, _ in smoothed]),
        [float(value) for _, value in smoothed],
        color=ACCENT,
        linewidth=2,
        label="Среднее за 7 дней",
    )
    axes.set_ylabel("кг")
    axes.legend(loc="upper left")
    _format_dates(axes)
    figure.autofmt_xdate(rotation=0, ha="center")
    return _to_png(figure)


def frequency_chart(days: Sequence[tuple[date, int]]) -> bytes | None:
    """Sessions per week."""
    if len(days) < MIN_POINTS:
        return None

    per_week: dict[date, int] = {}
    for day, _ in days:
        per_week[week_start(day)] = per_week.get(week_start(day), 0) + 1

    weeks = sorted(per_week)
    labels = [week.strftime("%d.%m") for week in weeks]
    values = [per_week[week] for week in weeks]

    figure, axes = new_figure("Тренировок в неделю")
    axes.bar(labels, values, color=NEUTRAL, width=0.6)
    axes.set_ylabel("тренировок")
    axes.tick_params(axis="x", rotation=45)
    # Whole sessions only: half a workout is not a thing.
    axes.set_yticks(range(0, max(values) + 1))
    return _to_png(figure)

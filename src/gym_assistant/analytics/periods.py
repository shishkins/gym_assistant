"""Report periods: "last three months" and friends, in one place.

There were two copies - the stats screens and the assistant's tools - and
they disagreed on an unknown period: one fell back to all history, the other
to three months. Now both fall back to the default.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

PERIOD_DAYS: dict[str, int | None] = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "all": None}
DEFAULT_PERIOD = "3m"


def since(period: str, *, now: datetime | None = None) -> datetime | None:
    """Where the period starts, or ``None`` for all history."""
    days = PERIOD_DAYS.get(period, PERIOD_DAYS[DEFAULT_PERIOD])
    return None if days is None else (now or datetime.now(UTC)) - timedelta(days=days)

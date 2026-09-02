"""Training metrics.

Pure functions over sets: no database, no I/O. Everything the bot reports
about progress is computed here, so this is the one place a formula can be
wrong - and the one place that is cheap to test exhaustively.
"""

from __future__ import annotations

from collections.abc import Iterable
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

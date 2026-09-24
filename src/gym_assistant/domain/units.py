"""Kilograms and pounds.

**The database is always kilograms.** Units are a display preference, nothing
more: they change how a number is typed in and how it is shown, never what is
stored. Store what the user typed in their own system and the history becomes
a mix of two units, with each row's meaning depending on a setting that was
true at the time - and that is not reversible.

So there are exactly two borders. ``to_kg`` on the way in, ``from_kg`` on the
way out. Everything between them is metric.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from enum import StrEnum

LB_IN_KG = Decimal("0.45359237")

# Pounds are shown to the half, not to the whole. Storage quantises to 0.01 kg,
# which is 0.022 lb, so rounding pounds to integers silently eats the halves:
# type 2.5 lb, see 2. Verified over every value from 1 to 1000 lb - at the half
# the round trip is exact, at the integer it breaks on 999 of them.
LB_STEP = Decimal("0.5")
KG_STEP = Decimal("0.01")


class Units(StrEnum):
    METRIC = "metric"
    IMPERIAL = "imperial"


# Plate maths, and it does not survive conversion. A kilo gym stacks 1.25 and
# 2.5 kg pairs; a pound gym stacks 2.5, 5, 10, 25 and 45 lb. Converting the
# metric steps would offer "+5.5 lb", which is not a thing you can load.
WEIGHT_STEPS = {
    Units.METRIC: (Decimal("-5"), Decimal("-2.5"), Decimal("2.5"), Decimal("5")),
    Units.IMPERIAL: (Decimal("-10"), Decimal("-5"), Decimal("5"), Decimal("10")),
}

LABELS = {Units.METRIC: "кг", Units.IMPERIAL: "lbs"}

# Body weight, as the column CHECK already enforces it.
MIN_BODY_WEIGHT_KG = Decimal("20")
MAX_BODY_WEIGHT_KG = Decimal("400")


def label(units: Units) -> str:
    return LABELS[units]


def to_kg(value: Decimal, units: Units) -> Decimal:
    """What the user typed, in kilograms."""
    if units is Units.METRIC:
        return value.quantize(KG_STEP, rounding=ROUND_HALF_UP)
    return (value * LB_IN_KG).quantize(KG_STEP, rounding=ROUND_HALF_UP)


def from_kg(kg: Decimal, units: Units) -> Decimal:
    """Stored kilograms, in the user's own system."""
    if units is Units.METRIC:
        return kg
    pounds = kg / LB_IN_KG
    # Quantise to the half: (x / 0.5) rounded, times 0.5.
    return (pounds / LB_STEP).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * LB_STEP


def step(units: Units) -> Decimal:
    """The smallest increment worth showing in this system."""
    return LB_STEP if units is Units.IMPERIAL else Decimal("0.5")


def weight_bounds(units: Units) -> tuple[Decimal, Decimal]:
    """The allowed body weight, expressed in the user's system.

    Rounded INWARD, and that is the whole point of the function. 20 kg is
    44.09 lb, so a bound of "44" would be accepted by the parser, converted
    back to 19.96 kg and then rejected by the CHECK constraint on the column
    - an error message quoting a limit that does not work.
    """
    if units is Units.METRIC:
        return MIN_BODY_WEIGHT_KG, MAX_BODY_WEIGHT_KG
    low = (MIN_BODY_WEIGHT_KG / LB_IN_KG / LB_STEP).to_integral_value(ROUND_CEILING) * LB_STEP
    high = (MAX_BODY_WEIGHT_KG / LB_IN_KG / LB_STEP).to_integral_value(ROUND_FLOOR) * LB_STEP
    return low, high

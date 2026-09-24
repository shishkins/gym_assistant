"""Kilograms, and pounds as a way of typing them.

**Everything in this bot is kilograms** - the rows, the panel, the charts, the
export, the assistant. Pounds are not a second system the diary can be read
in; they are a keyboard shortcut for someone standing in front of a bar
loaded in pounds, and they stop existing the moment the number is parsed.

There is one border, and it is the input side: ``to_kg``. ``from_kg`` survives
for exactly one job - the ``+5 lbs`` nudge buttons, where the label on the
button and the arithmetic behind it have to agree.

The earlier version of this module made units a display preference. That is
the thing to not go back to: the same weight would read 82.5 in one screenshot
and 181.5 in another, and a diary you cannot compare against itself is not a
diary.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

LB_IN_KG = Decimal("0.45359237")

# Pounds come back to the half, not to the whole. Storage quantises to 0.01 kg,
# which is 0.022 lb, so rounding to integers silently eats the halves: nudge to
# 2.5 lb, land on 2. Verified over every value from 1 to 1000 lb - at the half
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


def label(units: Units) -> str:
    return LABELS[units]


def to_kg(value: Decimal, units: Units) -> Decimal:
    """What the user typed, in kilograms."""
    if units is Units.METRIC:
        return value.quantize(KG_STEP, rounding=ROUND_HALF_UP)
    return (value * LB_IN_KG).quantize(KG_STEP, rounding=ROUND_HALF_UP)


def from_kg(kg: Decimal, units: Units) -> Decimal:
    """Kilograms back out - only to work out what a pound-labelled nudge means.

    Nothing user-facing calls this. The panel shows kilograms; this exists so
    that pressing "+5 lbs" adds five pounds rather than five pounds' worth of
    accumulated rounding.
    """
    if units is Units.METRIC:
        return kg
    pounds = kg / LB_IN_KG
    # Quantise to the half: (x / 0.5) rounded, times 0.5.
    return (pounds / LB_STEP).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * LB_STEP

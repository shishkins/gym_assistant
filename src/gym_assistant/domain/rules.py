"""Pure body-composition rules.

No database, no I/O - just arithmetic that is cheap to test and expensive
to get wrong silently.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def calculate_bmi(weight_kg: Decimal, height_cm: int) -> Decimal:
    """Body mass index, rounded to one decimal."""
    height_m = Decimal(height_cm) / Decimal(100)
    bmi = weight_kg / (height_m * height_m)
    return bmi.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def bmi_category(bmi: Decimal) -> str:
    """WHO band for a BMI value.

    Returns a machine-readable code; the bot layer maps it to Russian.
    BMI ignores muscle mass, so for trained lifters this is context, not a
    verdict - the UI must present it that way.
    """
    if bmi < Decimal("18.5"):
        return "underweight"
    if bmi < Decimal("25"):
        return "normal"
    if bmi < Decimal("30"):
        return "overweight"
    return "obese"

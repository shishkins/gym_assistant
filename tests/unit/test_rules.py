"""Body-composition arithmetic."""

from __future__ import annotations

from decimal import Decimal

import pytest

from gym_assistant.domain.rules import bmi_category, calculate_bmi


def test_calculate_bmi() -> None:
    # 80 kg at 180 cm -> 80 / 3.24 = 24.69...
    assert calculate_bmi(Decimal("80"), 180) == Decimal("24.7")


def test_calculate_bmi_rounds_to_one_decimal() -> None:
    assert calculate_bmi(Decimal("82.5"), 178).as_tuple().exponent == -1


@pytest.mark.parametrize(
    ("bmi", "band"),
    [
        (Decimal("17.0"), "underweight"),
        (Decimal("18.5"), "normal"),
        (Decimal("24.9"), "normal"),
        (Decimal("25.0"), "overweight"),
        (Decimal("29.9"), "overweight"),
        (Decimal("30.0"), "obese"),
    ],
)
def test_bmi_category_boundaries(bmi: Decimal, band: str) -> None:
    assert bmi_category(bmi) == band

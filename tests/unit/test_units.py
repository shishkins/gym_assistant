"""Kilograms and pounds, and the round trip between them.

The database is always kilograms; units are a display preference. The test
that matters is the round trip: a lifter who types 225 and later sees 224.5
will conclude the bot lost their record, and they will be right to.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from gym_assistant.domain.units import Units, from_kg, label, to_kg

# What is actually on the bars in a pound gym.
PLATES_LBS = ("45", "95", "135", "185", "225", "275", "315", "365", "405", "495")


def test_metric_is_a_no_op() -> None:
    assert to_kg(Decimal("82.5"), Units.METRIC) == Decimal("82.50")
    assert from_kg(Decimal("82.50"), Units.METRIC) == Decimal("82.50")


def test_a_pound_is_a_pound() -> None:
    assert to_kg(Decimal("100"), Units.IMPERIAL) == Decimal("45.36")


@pytest.mark.parametrize("pounds", PLATES_LBS)
def test_standard_loads_survive_the_round_trip(pounds: str) -> None:
    """225 lb must come back as 225 lb, not 224.5."""
    value = Decimal(pounds)

    assert from_kg(to_kg(value, Units.IMPERIAL), Units.IMPERIAL) == value


def test_every_half_pound_survives_the_round_trip() -> None:
    """Storage quantises to 0.01 kg, which is 0.022 lb - so the half is the
    finest pound step that can come back unchanged. Checked over the whole
    range a barbell ever sees."""
    value = Decimal("1")
    while value <= 1000:
        back = from_kg(to_kg(value, Units.IMPERIAL), Units.IMPERIAL)
        assert back == value, f"{value} lb вернулось как {back}"
        value += Decimal("0.5")


def test_labels_differ() -> None:
    assert label(Units.METRIC) != label(Units.IMPERIAL)


def test_plate_steps_are_not_converted() -> None:
    """A pound gym stacks 2.5, 5, 10, 25, 45. Converting the metric steps
    would offer +5.5 lb, which cannot be loaded."""
    from gym_assistant.domain.units import WEIGHT_STEPS

    for value in WEIGHT_STEPS[Units.IMPERIAL]:
        assert value % Decimal("5") == 0, f"шаг {value} lb не набрать блинами"

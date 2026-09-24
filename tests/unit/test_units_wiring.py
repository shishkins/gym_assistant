"""The units setting where it meets input, arithmetic and the assistant.

``test_units`` covers the conversion itself. These cover the places that
conversion has to reach: the two parsers, the plate buttons, and the tool
results the model reads.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from gym_assistant.ai.prompts import brief
from gym_assistant.ai.tools import _in_user_units
from gym_assistant.domain.parsing import parse_set_entry, parse_weight
from gym_assistant.domain.parsing.values import ValueParseError
from gym_assistant.domain.units import (
    MAX_BODY_WEIGHT_KG,
    MIN_BODY_WEIGHT_KG,
    WEIGHT_STEPS,
    Units,
    from_kg,
    to_kg,
    weight_bounds,
)

# --- the bounds shown to a user have to be bounds the column accepts -------


@pytest.mark.parametrize("units", list(Units))
def test_quoted_bounds_survive_conversion(units: Units) -> None:
    """The error message names a range. Typing either end of it must work.

    20 kg is 44.09 lb, so a bound rounded the natural way would be quoted as
    44, converted back to 19.96 and rejected by the CHECK on the column - a
    limit that fails when you use it.
    """
    low, high = weight_bounds(units)

    assert MIN_BODY_WEIGHT_KG <= to_kg(low, units) <= MAX_BODY_WEIGHT_KG
    assert MIN_BODY_WEIGHT_KG <= to_kg(high, units) <= MAX_BODY_WEIGHT_KG


def test_pounds_bounds_are_not_the_metric_ones() -> None:
    assert weight_bounds(Units.IMPERIAL) == (Decimal("44.5"), Decimal("881.5"))


# --- parsing ---------------------------------------------------------------


def test_body_weight_is_read_in_the_users_system() -> None:
    assert parse_weight("180", Units.IMPERIAL) == Decimal("81.65")
    assert parse_weight("180", Units.METRIC) == Decimal("180.00")


def test_a_weight_outside_the_pound_range_is_a_range_error() -> None:
    # 900 lb is 408 kg, past the column's 400.
    with pytest.raises(ValueParseError) as caught:
        parse_weight("900", Units.IMPERIAL)
    assert caught.value.reason == "range"


def test_a_set_is_read_in_the_users_system() -> None:
    """Same grammar, different meaning: 225x5 is a plate stack either way."""
    assert parse_set_entry("225х5", Units.IMPERIAL).weight_kg == Decimal("102.06")
    assert parse_set_entry("225х5", Units.METRIC).weight_kg == Decimal("225.00")


def test_a_set_without_a_weight_is_untouched_by_units() -> None:
    assert parse_set_entry("12", Units.IMPERIAL).weight_kg is None
    assert parse_set_entry("60с", Units.IMPERIAL).duration_sec == 60


# --- the plate buttons -----------------------------------------------------


def test_pound_steps_are_plates_not_converted_kilos() -> None:
    """A converted metric step would offer +5.5 lb, which is not loadable."""
    assert WEIGHT_STEPS[Units.IMPERIAL] == (
        Decimal("-10"),
        Decimal("-5"),
        Decimal("5"),
        Decimal("10"),
    )


def test_twenty_taps_do_not_drift() -> None:
    """The handler's own expression, run twenty times.

    Adding a converted step to kilograms instead would accumulate rounding:
    +5 lb is 2.2679685 kg, stored as 2.27, and twenty of those is 0.06 kg
    off - enough to show a weight nobody typed.
    """
    units = Units.IMPERIAL
    stored = to_kg(Decimal("135"), units)

    for _ in range(20):
        shown = from_kg(stored, units) + Decimal("5")
        stored = to_kg(shown, units)

    assert from_kg(stored, units) == Decimal("235.0")


# --- what the assistant is handed ------------------------------------------


def test_tool_results_are_converted_wherever_the_key_sits() -> None:
    """Nested, in a list, and under a key that is not simply "weight_kg"."""
    payload = {
        "tonnage_kg": 1000.0,
        "workouts": [{"exercises": {"Жим": {"top_weight_kg": 100.0, "sets": 3}}}],
        "reps": 5,
    }

    converted = _in_user_units(payload, Units.IMPERIAL)

    assert converted["tonnage_lbs"] == pytest.approx(2204.5, abs=0.5)
    assert converted["workouts"][0]["exercises"]["Жим"]["top_weight_lbs"] == pytest.approx(
        220.5, abs=0.5
    )
    # Anything that is not a weight travels untouched.
    assert converted["reps"] == 5
    assert converted["workouts"][0]["exercises"]["Жим"]["sets"] == 3


def test_metric_results_are_left_exactly_as_they_were() -> None:
    payload = {"tonnage_kg": 1000.0, "reps": 5}

    assert _in_user_units(payload, Units.METRIC) is payload


def test_a_missing_weight_still_takes_the_pound_key() -> None:
    """Otherwise one key says _kg beside a dozen saying _lbs, and the model
    has to guess whether that means kilograms or nothing."""
    assert _in_user_units({"weight_kg": None}, Units.IMPERIAL) == {"weight_lbs": None}


def test_the_brief_mentions_pounds_only_for_pounds() -> None:
    assert "фунт" in brief("Тестер", Units.IMPERIAL)
    assert "фунт" not in brief("Тестер", Units.METRIC)

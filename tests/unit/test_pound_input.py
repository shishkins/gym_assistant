"""Pounds as a way of typing a weight, never as a way of reading one.

Everything this bot shows is kilograms. These tests are about the input side:
the marker in a typed line, the per-exercise mode behind the panel button, and
the two of them disagreeing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from gym_assistant.domain.parsing import parse_set_entry
from gym_assistant.domain.parsing.values import ValueParseError
from gym_assistant.domain.units import WEIGHT_STEPS, Units, from_kg, to_kg

# 225 lb is the four-plate bar, and 102.06 kg is what it weighs.
FOUR_PLATES_KG = Decimal("102.06")


# --- the marker, in every shape it gets typed -----------------------------


@pytest.mark.parametrize(
    "text",
    [
        "lbs 225х5",
        "225х5 lbs",
        "225lbs х 5",
        "225lb х 5",
        "225 фунтов х 5",
        "225х5 lbs разминка",
        "lbs р 225х5",
    ],
)
def test_a_marked_line_is_pounds_whatever_the_mode(text: str) -> None:
    """The marker wins over the mode, so it works before the button is found."""
    assert parse_set_entry(text, Units.METRIC).weight_kg == FOUR_PLATES_KG


def test_the_marker_survives_the_exercise_name_and_the_rpe() -> None:
    parsed = parse_set_entry("жим штанги 225х5 lbs @8", Units.METRIC)

    assert parsed.weight_kg == FOUR_PLATES_KG
    assert parsed.exercise_query == "жим штанги"
    assert parsed.rpe == Decimal("8")


def test_both_qualifiers_at_the_same_end() -> None:
    """One pass in a fixed order left the inner marker stuck to the numbers."""
    parsed = parse_set_entry("225х5 lbs разминка", Units.METRIC)

    assert parsed.weight_kg == FOUR_PLATES_KG
    assert parsed.is_warmup


# --- the mode ------------------------------------------------------------


def test_a_bare_number_follows_the_mode() -> None:
    assert parse_set_entry("225х5", Units.IMPERIAL).weight_kg == FOUR_PLATES_KG
    assert parse_set_entry("225х5", Units.METRIC).weight_kg == Decimal("225.00")


@pytest.mark.parametrize("text", ["100кг х 5", "кг 100х5", "100 кг х 5"])
def test_a_kilo_marker_overrides_the_mode(text: str) -> None:
    """The escape hatch: one machine labelled in kilos, mode left alone."""
    assert parse_set_entry(text, Units.IMPERIAL).weight_kg == Decimal("100.00")


@pytest.mark.parametrize("text", ["12", "60с", "100м", "1:30"])
def test_the_mode_touches_nothing_but_weight(text: str) -> None:
    assert parse_set_entry(text, Units.IMPERIAL).weight_kg is None


# --- what must still be refused ------------------------------------------


@pytest.mark.parametrize("text", ["80кг", "225lbs", "225 lbs"])
def test_a_bare_weight_is_not_a_set_in_either_unit(text: str) -> None:
    with pytest.raises(ValueParseError):
        parse_set_entry(text, Units.METRIC)


def test_two_markers_that_disagree_are_a_typo() -> None:
    """Guessing which half was meant writes a wrong number into the history."""
    with pytest.raises(ValueParseError) as caught:
        parse_set_entry("225lbs х 5 кг", Units.METRIC)
    assert caught.value.reason == "format"


# --- the nudge buttons ---------------------------------------------------


def test_pound_steps_are_plates_not_converted_kilos() -> None:
    """A converted metric step would offer +5.5 lb, which is not loadable."""
    assert WEIGHT_STEPS[Units.IMPERIAL] == (
        Decimal("-10"),
        Decimal("-5"),
        Decimal("5"),
        Decimal("10"),
    )


def test_twenty_nudges_do_not_drift() -> None:
    """The handler's own expression, run twenty times.

    Adding a converted step to the stored kilograms instead would accumulate
    rounding: +5 lb is 2.2679685 kg, stored as 2.27, and twenty of those land
    0.06 kg away from any weight that was ever typed.
    """
    stored = to_kg(Decimal("135"), Units.IMPERIAL)

    for _ in range(20):
        shown = from_kg(stored, Units.IMPERIAL) + Decimal("5")
        stored = to_kg(shown, Units.IMPERIAL)

    assert from_kg(stored, Units.IMPERIAL) == Decimal("235.0")

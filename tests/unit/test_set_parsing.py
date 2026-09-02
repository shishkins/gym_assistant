"""The set parser.

This is the busiest input path in the product - 15-30 lines a session - so
the suite is deliberately exhaustive. A parser that is wrong once every
twenty sets is worse than no parser at all.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from gym_assistant.domain.parsing import ValueParseError, parse_set_entry


@pytest.mark.parametrize(
    "raw",
    ["80х8", "80x8", "80*8", "80×8", "80 8", "80 на 8", "80 х 8", "80X8"],
)
def test_weight_by_reps_separators(raw: str) -> None:
    """Every separator a thumb might produce means the same thing."""
    parsed = parse_set_entry(raw)
    assert parsed.weight_kg == Decimal("80.00")
    assert parsed.reps == 8
    assert parsed.repeat == 1


def test_comma_decimal() -> None:
    assert parse_set_entry("82,5х8").weight_kg == Decimal("82.50")


def test_dot_decimal() -> None:
    assert parse_set_entry("82.5х8").weight_kg == Decimal("82.50")


def test_repeated_sets() -> None:
    parsed = parse_set_entry("80х8х3")
    assert (parsed.weight_kg, parsed.reps, parsed.repeat) == (Decimal("80.00"), 8, 3)


def test_reps_only_is_bodyweight() -> None:
    parsed = parse_set_entry("12")
    assert parsed.reps == 12
    assert parsed.weight_kg is None


def test_added_weight() -> None:
    parsed = parse_set_entry("+10х8")
    assert parsed.weight_kg == Decimal("10.00")
    assert parsed.reps == 8


# --- exercise name --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("жим 80х8", "жим"),
        ("жим лёжа 80х8", "жим лёжа"),
        ("Становая 100х5", "становая"),
        ("подтягивания 12", "подтягивания"),
    ],
)
def test_exercise_name_prefix(raw: str, name: str) -> None:
    assert parse_set_entry(raw).exercise_query == name


def test_no_name_when_line_starts_with_a_number() -> None:
    assert parse_set_entry("80х8").exercise_query is None


def test_name_only_line() -> None:
    """Typing just a name is how you switch exercises mid-session."""
    parsed = parse_set_entry("жим лёжа")
    assert parsed.exercise_query == "жим лёжа"
    assert not parsed.has_payload


# --- time and distance ----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "seconds"),
    [("60с", 60), ("60 сек", 60), ("90s", 90), ("1:30", 90), ("2:05", 125), ("5мин", 300)],
)
def test_duration(raw: str, seconds: int) -> None:
    parsed = parse_set_entry(raw)
    assert parsed.duration_sec == seconds
    assert parsed.reps is None


@pytest.mark.parametrize(("raw", "metres"), [("100м", 100), ("100 метров", 100), ("50m", 50)])
def test_distance(raw: str, metres: int) -> None:
    assert parse_set_entry(raw).distance_m == metres


def test_minutes_are_not_metres() -> None:
    """The one genuinely ambiguous suffix in Russian."""
    assert parse_set_entry("5мин").duration_sec == 300
    assert parse_set_entry("5м").distance_m == 5


# --- modifiers ------------------------------------------------------------


@pytest.mark.parametrize("raw", ["80х8 @8", "80х8 rpe 8", "80х8 рпе 8", "80х8@8"])
def test_rpe(raw: str) -> None:
    parsed = parse_set_entry(raw)
    assert parsed.rpe == Decimal("8")
    assert parsed.reps == 8


def test_fractional_rpe() -> None:
    assert parse_set_entry("80х8 @8.5").rpe == Decimal("8.5")


@pytest.mark.parametrize("raw", ["р 80х8", "разминка 80х8", "разм 80х8", "w 80х8"])
def test_warmup_marker(raw: str) -> None:
    parsed = parse_set_entry(raw)
    assert parsed.is_warmup
    assert parsed.weight_kg == Decimal("80.00")


def test_warmup_with_exercise_and_rpe() -> None:
    parsed = parse_set_entry("разминка жим 60х10 @6")
    assert parsed.is_warmup
    assert parsed.exercise_query == "жим"
    assert parsed.weight_kg == Decimal("60.00")
    assert parsed.reps == 10
    assert parsed.rpe == Decimal("6")


# --- rejections -----------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "80х8х3х2", "80х", "80х8х", "abc 1.2.3"])
def test_rejects_format(raw: str) -> None:
    with pytest.raises(ValueParseError) as exc:
        parse_set_entry(raw)
    assert exc.value.reason == "format"


@pytest.mark.parametrize("raw", ["1500х8", "80х0", "80х8х50", "80х8 @11", "80х1500"])
def test_rejects_range(raw: str) -> None:
    with pytest.raises(ValueParseError) as exc:
        parse_set_entry(raw)
    assert exc.value.reason == "range"


@pytest.mark.parametrize(("raw", "reps"), [("80хх8", 8), ("х8", 8)])
def test_forgiving_about_stray_separators(raw: str, reps: int) -> None:
    """A doubled or leading separator has one sensible reading; take it."""
    assert parse_set_entry(raw).reps == reps


def test_interrupted_line_is_rejected() -> None:
    """ "80х" is a line cut short, not 80 repetitions of nothing."""
    with pytest.raises(ValueParseError):
        parse_set_entry("80х")


def test_weight_alone_is_not_a_set() -> None:
    """80 kg of nothing is not a set; without a unit it reads as reps."""
    with pytest.raises(ValueParseError):
        parse_set_entry("80кг")

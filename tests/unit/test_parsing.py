"""Value parsing. Pure functions, so the suite can afford to be exhaustive."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from gym_assistant.domain.parsing import (
    ValueParseError,
    calculate_age,
    parse_birth_date,
    parse_body_fat,
    parse_girth,
    parse_height,
    parse_weight,
)

TODAY = date(2026, 8, 23)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("80", Decimal("80.00")),
        ("82.5", Decimal("82.50")),
        ("82,5", Decimal("82.50")),  # comma is at least as common as a dot
        (" 82.5 ", Decimal("82.50")),
        ("82 . 5", Decimal("82.50")),
        ("100.25", Decimal("100.25")),
    ],
)
def test_parse_weight_accepts(raw: str, expected: Decimal) -> None:
    assert parse_weight(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "abc", "80.5.5", "80kg", "8-0", "--80"])
def test_parse_weight_rejects_format(raw: str) -> None:
    with pytest.raises(ValueParseError) as exc:
        parse_weight(raw)
    assert exc.value.reason == "format"


@pytest.mark.parametrize("raw", ["19", "401", "0", "-80"])
def test_parse_weight_rejects_range(raw: str) -> None:
    with pytest.raises(ValueParseError) as exc:
        parse_weight(raw)
    assert exc.value.reason == "range"


def test_parse_height_returns_whole_centimetres() -> None:
    assert parse_height("178") == 178
    assert isinstance(parse_height("178"), int)


@pytest.mark.parametrize("raw", ["99", "251"])
def test_parse_height_rejects_range(raw: str) -> None:
    with pytest.raises(ValueParseError) as exc:
        parse_height(raw)
    assert exc.value.reason == "range"


def test_parse_body_fat_and_girth() -> None:
    assert parse_body_fat("14,5") == Decimal("14.5")
    assert parse_girth("102") == Decimal("102.0")


@pytest.mark.parametrize(
    "raw",
    ["31.12.1990", "31/12/1990", "31-12-1990", "1990-12-31", " 31.12.1990 "],
)
def test_parse_birth_date_accepts_common_formats(raw: str) -> None:
    assert parse_birth_date(raw, today=TODAY) == date(1990, 12, 31)


def test_parse_birth_date_distinguishes_iso_by_leading_year() -> None:
    assert parse_birth_date("1990-01-02", today=TODAY) == date(1990, 1, 2)
    assert parse_birth_date("01.02.1990", today=TODAY) == date(1990, 2, 1)


@pytest.mark.parametrize("raw", ["31.13.1990", "32.12.1990", "29.02.1991", "hello", "1990"])
def test_parse_birth_date_rejects_format(raw: str) -> None:
    with pytest.raises(ValueParseError) as exc:
        parse_birth_date(raw, today=TODAY)
    assert exc.value.reason == "format"


@pytest.mark.parametrize("raw", ["01.01.2020", "01.01.1900", "01.01.2030"])
def test_parse_birth_date_rejects_implausible_ages(raw: str) -> None:
    with pytest.raises(ValueParseError) as exc:
        parse_birth_date(raw, today=TODAY)
    assert exc.value.reason == "range"


@pytest.mark.parametrize(
    ("born", "today", "expected"),
    [
        (date(1990, 1, 1), date(2026, 1, 1), 36),  # birthday today
        (date(1990, 1, 2), date(2026, 1, 1), 35),  # birthday tomorrow
        (date(1990, 12, 31), date(2026, 8, 23), 35),
        (date(2000, 2, 29), date(2026, 2, 28), 25),  # leap-day birthday, before
        (date(2000, 2, 29), date(2026, 3, 1), 26),  # leap-day birthday, after
    ],
)
def test_calculate_age(born: date, today: date, expected: int) -> None:
    assert calculate_age(born, today=today) == expected

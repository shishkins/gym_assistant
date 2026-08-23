"""Turning what a user typed into typed values.

Every parser here is pure and raises :class:`ValueParseError` carrying a
machine-readable ``reason``. The bot layer maps that reason to a message,
which keeps user-facing Russian text out of the domain.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

Reason = Literal["format", "range"]


class ValueParseError(ValueError):
    def __init__(self, reason: Reason) -> None:
        super().__init__(reason)
        self.reason: Reason = reason


# People type "82,5" at least as often as "82.5", and paste stray spaces.
_NUMBER_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")

_DATE_RE = re.compile(r"^(?P<first>\d{1,4})[.\-/](?P<second>\d{1,2})[.\-/](?P<third>\d{1,4})$")

MIN_AGE = 10
MAX_AGE = 100


def parse_decimal(
    raw: str,
    *,
    minimum: Decimal | int,
    maximum: Decimal | int,
    decimals: int = 1,
) -> Decimal:
    cleaned = raw.strip().replace(" ", "").replace(",", ".")
    if not _NUMBER_RE.match(cleaned):
        raise ValueParseError("format")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueParseError("format") from exc

    if not Decimal(minimum) <= value <= Decimal(maximum):
        raise ValueParseError("range")

    # No normalize(): it turns Decimal('80') into Decimal('8E+1').
    return value.quantize(Decimal(1).scaleb(-decimals))


def parse_weight(raw: str) -> Decimal:
    """Body weight in kilograms."""
    return parse_decimal(raw, minimum=20, maximum=400, decimals=2)


def parse_height(raw: str) -> int:
    """Height in whole centimetres."""
    value = parse_decimal(raw, minimum=100, maximum=250, decimals=0)
    return int(value)


def parse_body_fat(raw: str) -> Decimal:
    """Body fat percentage."""
    return parse_decimal(raw, minimum=3, maximum=70, decimals=1)


def parse_girth(raw: str) -> Decimal:
    """A body circumference in centimetres."""
    return parse_decimal(raw, minimum=10, maximum=200, decimals=1)


def parse_birth_date(raw: str, *, today: date) -> date:
    """Accepts ``31.12.1990``, ``31/12/1990``, ``31-12-1990`` and ``1990-12-31``."""
    match = _DATE_RE.match(raw.strip())
    if match is None:
        raise ValueParseError("format")

    first, second, third = (int(match["first"]), int(match["second"]), int(match["third"]))
    # A four-digit leading group can only be an ISO date.
    year, month, day = (first, second, third) if first > 31 else (third, second, first)

    try:
        value = date(year, month, day)
    except ValueError as exc:
        raise ValueParseError("format") from exc

    if value > today:
        raise ValueParseError("range")
    if not MIN_AGE <= calculate_age(value, today=today) <= MAX_AGE:
        raise ValueParseError("range")

    return value


def calculate_age(birth_date: date, *, today: date) -> int:
    """Full years lived.

    Kept next to the date parser because the two must agree on what counts
    as a plausible birth date.
    """
    had_birthday = (today.month, today.day) >= (birth_date.month, birth_date.day)
    return today.year - birth_date.year - (0 if had_birthday else 1)

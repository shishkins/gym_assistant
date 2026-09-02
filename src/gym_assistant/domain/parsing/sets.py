"""Parsing a set the way people actually type it between reps.

This is deliberately a grammar and not a model call. Logging a set happens
15-30 times a session, with one hand, and a round trip to an LLM would add
seconds to every one of them. Everything here is pure and instant; the
assistant only ever sees what this parser could not read.

Accepted, roughly in order of how often they appear:

    80х8            вес × повторы
    80x8  80*8  80×8  80 8  80 на 8
    82,5х8          запятая как разделитель
    80х8х3          три одинаковых подхода
    жим 80х8        с названием упражнения
    12              только повторы (свой вес)
    +10х8           доп. вес к своему
    60с   1:30      время
    100м            дистанция
    80х8 @8         RPE
    р 80х8          разминочный
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from gym_assistant.domain.parsing.values import ValueParseError

MAX_REPEAT = 20

_WARMUP_WORDS = ("разминка", "разминочный", "warmup", "разм")
# A bare "р"/"w" prefix is a marker only when a separate token.
_WARMUP_TOKENS = ("р", "w")

# Whitespace separates too: "80 8" is as common as "80х8".
_SEPARATORS = re.compile(r"\s*(?:[xх×*]|на)\s*|\s+", re.IGNORECASE)
_TRAILING_SEPARATOR = re.compile(r"[xх×*]\s*$", re.IGNORECASE)
_RPE = re.compile(r"(?:@|\brpe\s*|\bрпе\s*)(\d+(?:[.,]\d)?)", re.IGNORECASE)
_CLOCK = re.compile(r"^(\d{1,2}):([0-5]\d)$")
_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

_UNIT_PATTERNS = (
    # Minutes before metres: "5мин" must not read as 5 metres.
    ("minutes", re.compile(r"^(\d+(?:\.\d+)?)\s*(?:мин|min|м\.)$", re.IGNORECASE)),
    ("seconds", re.compile(r"^(\d+(?:\.\d+)?)\s*(?:сек|с|sec|s)$", re.IGNORECASE)),
    ("metres", re.compile(r"^(\d+(?:\.\d+)?)\s*(?:метров|метра|метр|м|m)$", re.IGNORECASE)),
    ("kg", re.compile(r"^(\d+(?:\.\d+)?)\s*(?:кг|kg)$", re.IGNORECASE)),
)


@dataclass(frozen=True, slots=True)
class ParsedSet:
    """What one typed line means. ``repeat`` is how many identical sets."""

    weight_kg: Decimal | None = None
    reps: int | None = None
    duration_sec: int | None = None
    distance_m: int | None = None
    rpe: Decimal | None = None
    is_warmup: bool = False
    repeat: int = 1
    exercise_query: str | None = None

    @property
    def has_payload(self) -> bool:
        return any((self.reps, self.duration_sec, self.distance_m))


def parse_set_entry(raw: str) -> ParsedSet:
    """Reads one line into a set, or raises :class:`ValueParseError`."""
    text = " ".join(raw.strip().lower().replace(",", ".").split())
    if not text:
        raise ValueParseError("format")

    text, rpe = _take_rpe(text)
    text, is_warmup = _take_warmup(text)
    exercise_query, text = _split_exercise(text)

    if not text:
        # A line with no numbers names an exercise and nothing else - which is
        # how you switch exercises mid-session.
        if exercise_query:
            return ParsedSet(is_warmup=is_warmup, rpe=rpe, exercise_query=exercise_query)
        raise ValueParseError("format")

    parsed = _parse_numbers(text)
    return ParsedSet(
        weight_kg=parsed.weight_kg,
        reps=parsed.reps,
        duration_sec=parsed.duration_sec,
        distance_m=parsed.distance_m,
        rpe=rpe,
        is_warmup=is_warmup,
        repeat=parsed.repeat,
        exercise_query=exercise_query,
    )


# --- pieces ---------------------------------------------------------------


def _take_rpe(text: str) -> tuple[str, Decimal | None]:
    match = _RPE.search(text)
    if match is None:
        return text, None
    try:
        value = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise ValueParseError("format") from exc
    if not Decimal(1) <= value <= Decimal(10):
        raise ValueParseError("range")
    return (text[: match.start()] + text[match.end() :]).strip(), value


def _take_warmup(text: str) -> tuple[str, bool]:
    tokens = text.split()
    if not tokens:
        return text, False
    head = tokens[0]
    if head in _WARMUP_TOKENS or any(head.startswith(word) for word in _WARMUP_WORDS):
        return " ".join(tokens[1:]).strip(), True
    return text, False


def _split_exercise(text: str) -> tuple[str | None, str]:
    """Splits a leading exercise name off the numbers."""
    match = re.search(r"[\d]", text)
    if match is None:
        # No digits at all: the whole line names an exercise and nothing else.
        return (text or None), ""
    name = text[: match.start()].strip()
    # Trailing separators belong to the numbers, not to the name ("жим х 80").
    name = re.sub(r"[\s xх×*]+$", "", name).strip()
    return (name or None), text[match.start() :].strip()


@dataclass(frozen=True, slots=True)
class _Numbers:
    weight_kg: Decimal | None = None
    reps: int | None = None
    duration_sec: int | None = None
    distance_m: int | None = None
    repeat: int = 1


def _parse_numbers(text: str) -> _Numbers:
    clock = _CLOCK.match(text)
    if clock is not None:
        return _Numbers(duration_sec=int(clock.group(1)) * 60 + int(clock.group(2)))

    # "80х" is an interrupted line, not 80 repetitions. Reading it as reps
    # would silently record a plausible-looking set that never happened.
    if _TRAILING_SEPARATOR.search(text):
        raise ValueParseError("format")

    # Units are checked against the whole line first, so "60 сек" is not split
    # into two tokens by the whitespace separator.
    united = _with_unit(text)
    if united is not None:
        return united

    parts = [part for part in _SEPARATORS.split(text) if part.strip()]
    if not parts:
        raise ValueParseError("format")

    values = [_number(part) for part in parts]

    if len(values) == 1:
        return _Numbers(reps=_as_reps(values[0]))
    if len(values) == 2:
        return _Numbers(weight_kg=_as_weight(values[0]), reps=_as_reps(values[1]))
    if len(values) == 3:
        return _Numbers(
            weight_kg=_as_weight(values[0]),
            reps=_as_reps(values[1]),
            repeat=_as_repeat(values[2]),
        )
    raise ValueParseError("format")


def _with_unit(part: str) -> _Numbers | None:
    for kind, pattern in _UNIT_PATTERNS:
        match = pattern.match(part.strip())
        if match is None:
            continue
        value = _number(match.group(1))
        if kind == "minutes":
            return _Numbers(duration_sec=_as_duration(value * 60))
        if kind == "seconds":
            return _Numbers(duration_sec=_as_duration(value))
        if kind == "metres":
            return _Numbers(distance_m=_as_distance(value))
        # A bare weight with no reps is not a set on its own.
        raise ValueParseError("format")
    return None


def _number(part: str) -> Decimal:
    # No internal-space stripping: "80 8" must not become 808.
    cleaned = part.strip()
    if not _NUMBER.match(cleaned):
        raise ValueParseError("format")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueParseError("format") from exc


def _as_weight(value: Decimal) -> Decimal:
    if not Decimal(0) <= value <= Decimal(1000):
        raise ValueParseError("range")
    return value.quantize(Decimal("0.01"))


def _as_reps(value: Decimal) -> int:
    if value != value.to_integral_value() or not 1 <= value <= 1000:
        raise ValueParseError("range")
    return int(value)


def _as_repeat(value: Decimal) -> int:
    if value != value.to_integral_value() or not 1 <= value <= MAX_REPEAT:
        raise ValueParseError("range")
    return int(value)


def _as_duration(value: Decimal) -> int:
    seconds = int(value)
    if not 1 <= seconds <= 86400:
        raise ValueParseError("range")
    return seconds


def _as_distance(value: Decimal) -> int:
    metres = int(value)
    if not 1 <= metres <= 100000:
        raise ValueParseError("range")
    return metres

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
    р 80х8          разминочный (в начале)
    80х8 разминка   разминочный (в конце)
    lbs 225х5       вес в фунтах — метка с краю строки
    225х5 lbs       она же с другого края
    225lbs х 5      она же вплотную к числу
    кг 100х5        та же метка наоборот, когда включён режим фунтов
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from gym_assistant.domain.parsing.values import ValueParseError
from gym_assistant.domain.units import Units, to_kg

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

# The weight marker, in the two shapes it actually gets typed: a word of its
# own at either end of the line, or stuck to the number. Both are accepted
# because both were asked for, and because a marker you have to place exactly
# right is a marker you stop using by the third set.
#
# "ф" alone is deliberately not a marker: it is one letter away from too many
# things, and the warmup marker already spends the single-letter budget.
_POUND_WORD = r"lbs|lbf|lb|фунтов|фунта|фунты|фунт"
_KILO_WORD = r"кг|kg"
_NUMBER_PART = r"[+-]?\d+(?:\.\d+)?"

_EITHER_WORD = "(?P<lb>" + _POUND_WORD + ")|(?P<kg>" + _KILO_WORD + ")"

_MARKER_TOKEN = re.compile("^(?:" + _EITHER_WORD + ")$", re.IGNORECASE)
_MARKER_SUFFIX = re.compile(
    "^(?P<number>" + _NUMBER_PART + r")\s*(?:" + _EITHER_WORD + ")$",
    re.IGNORECASE,
)

_UNIT_PATTERNS = (
    # Minutes before metres: "5мин" must not read as 5 metres.
    ("minutes", re.compile(r"^(\d+(?:\.\d+)?)\s*(?:мин|min|м\.)$", re.IGNORECASE)),
    ("seconds", re.compile(r"^(\d+(?:\.\d+)?)\s*(?:сек|с|sec|s)$", re.IGNORECASE)),
    ("metres", re.compile(r"^(\d+(?:\.\d+)?)\s*(?:метров|метра|метр|м|m)$", re.IGNORECASE)),
    # A bare weight is not a set whichever unit it carries.
    (
        "weight",
        re.compile(
            "^(" + _NUMBER_PART + r")\s*(?:" + _POUND_WORD + "|" + _KILO_WORD + ")$",
            re.IGNORECASE,
        ),
    ),
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
    # Whether the line said its own unit, as opposed to inheriting the panel's
    # mode. The caller needs to tell the two apart: a mode belongs to one
    # exercise, a marker belongs to the line it was typed on.
    marked_units: Units | None = None

    @property
    def has_payload(self) -> bool:
        return any((self.reps, self.duration_sec, self.distance_m))


def parse_set_entry(raw: str, default_units: Units = Units.METRIC) -> ParsedSet:
    """Reads one line into a set, or raises :class:`ValueParseError`.

    ``weight_kg`` comes back in kilograms whatever was typed. ``default_units``
    is what a bare number means - the panel's input mode - and a marker in the
    line always wins over it, in either direction. That is what makes the mode
    safe to leave on: the one machine labelled in kilos is "100кг х 5" and
    nothing has to be switched back.
    """
    text = " ".join(raw.strip().lower().replace(",", ".").split())
    if not text:
        raise ValueParseError("format")

    text, rpe = _take_rpe(text)
    text, marked, is_warmup = _take_qualifiers(text)
    exercise_query, text = _split_exercise(text)

    if not text:
        # A line with no numbers names an exercise and nothing else - which is
        # how you switch exercises mid-session.
        if exercise_query:
            return ParsedSet(is_warmup=is_warmup, rpe=rpe, exercise_query=exercise_query)
        raise ValueParseError("format")

    parsed = _parse_numbers(text)
    marked = _agree(marked, parsed.units)
    if marked is not None and parsed.weight is None:
        # A unit marker is a statement about a weight, so a line carrying one
        # and no weight is malformed. Without this "225 lbs" parsed as 225
        # REPETITIONS: the marker was stripped, one number was left, and one
        # number means reps. A plausible-looking set that never happened.
        raise ValueParseError("format")

    units = marked or default_units
    return ParsedSet(
        marked_units=marked,
        weight_kg=None if parsed.weight is None else to_kg(parsed.weight, units),
        reps=parsed.reps,
        duration_sec=parsed.duration_sec,
        distance_m=parsed.distance_m,
        rpe=rpe,
        is_warmup=is_warmup,
        repeat=parsed.repeat,
        exercise_query=exercise_query,
    )


# --- pieces ---------------------------------------------------------------


def _agree(first: Units | None, second: Units | None) -> Units | None:
    """Two markers on one line have to say the same thing.

    "225lbs х 5 кг" is not a set with a preference, it is a typo, and guessing
    which half was meant writes a wrong number into the history.
    """
    if first is not None and second is not None and first is not second:
        raise ValueParseError("format")
    return first or second


def _marker_units(match: re.Match[str]) -> Units:
    return Units.IMPERIAL if match.group("lb") else Units.METRIC


def _take_marker(text: str) -> tuple[str, Units | None]:
    """Strips a standalone unit word off either end of the line.

    Either end, for the same reason the warmup marker works at either end: the
    numbers come to mind first, so the qualifier lands wherever the thumb was.
    Only the first and last token are considered - the middle of the line is
    the exercise name, and an exercise is not going to be called "lbs".
    """
    tokens = text.split()
    if not tokens:
        return text, None

    units: Units | None = None
    if (match := _MARKER_TOKEN.match(tokens[-1])) is not None and len(tokens) > 1:
        units = _marker_units(match)
        tokens = tokens[:-1]
    if tokens and (match := _MARKER_TOKEN.match(tokens[0])) is not None and len(tokens) > 1:
        units = _agree(units, _marker_units(match))
        tokens = tokens[1:]

    return " ".join(tokens).strip(), units


def _take_qualifiers(text: str) -> tuple[str, Units | None, bool]:
    """Peels the unit marker and the warmup marker off, in any order.

    Both live at the ends of the line and either can be outside the other:
    "225х5 lbs разминка" and "lbs р 135х5" are both things people type. One
    pass in a fixed order always leaves the inner one stuck to the numbers, so
    this keeps going until a pass takes nothing.
    """
    units: Units | None = None
    is_warmup = False
    while True:
        text, found = _take_marker(text)
        text, warmup = _take_warmup(text)
        units = _agree(units, found)
        is_warmup = is_warmup or warmup
        if found is None and not warmup:
            return text, units, is_warmup


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


def _is_warmup_token(token: str) -> bool:
    return token in _WARMUP_TOKENS or any(token.startswith(word) for word in _WARMUP_WORDS)


def _take_warmup(text: str) -> tuple[str, bool]:
    """Accepts the marker at either end.

    "разминка 50х4" reads naturally, but so does "50 на 4 разминка" - and
    the second is what gets typed, because the numbers come to mind first.
    """
    tokens = text.split()
    if not tokens:
        return text, False
    if _is_warmup_token(tokens[0]):
        return " ".join(tokens[1:]).strip(), True
    if len(tokens) > 1 and _is_warmup_token(tokens[-1]):
        return " ".join(tokens[:-1]).strip(), True
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
    """What the digits said. ``weight`` is still in whatever was typed."""

    weight: Decimal | None = None
    reps: int | None = None
    duration_sec: int | None = None
    distance_m: int | None = None
    repeat: int = 1
    units: Units | None = None


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

    parts, units = _take_attached_markers(parts)
    values = [_number(part) for part in parts]

    if len(values) == 1:
        return _Numbers(reps=_as_reps(values[0]), units=units)
    if len(values) == 2:
        return _Numbers(weight=_as_weight(values[0]), reps=_as_reps(values[1]), units=units)
    if len(values) == 3:
        return _Numbers(
            weight=_as_weight(values[0]),
            reps=_as_reps(values[1]),
            repeat=_as_repeat(values[2]),
            units=units,
        )
    raise ValueParseError("format")


def _take_attached_markers(parts: list[str]) -> tuple[list[str], Units | None]:
    """Peels "lbs" off "225lbs", leaving a number the rest of the code can read.

    Run after the whole-line unit check, not before: "80кг" on its own has to
    stay a format error rather than quietly becoming eighty repetitions.
    """
    cleaned: list[str] = []
    units: Units | None = None
    for part in parts:
        stripped = part.strip()
        if (standalone := _MARKER_TOKEN.match(stripped)) is not None:
            # "225 фунтов х 5": a space before the unit is not a decision.
            units = _agree(units, _marker_units(standalone))
            continue
        match = _MARKER_SUFFIX.match(stripped)
        if match is None:
            cleaned.append(part)
            continue
        units = _agree(units, _marker_units(match))
        cleaned.append(match.group("number"))
    return cleaned, units


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
        # A bare weight with no reps is not a set on its own, in either unit.
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

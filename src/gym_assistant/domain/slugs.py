"""Turning a Russian exercise name into a stable ASCII slug."""

from __future__ import annotations

import re

_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str, *, max_length: int = 48) -> str:
    """``Жим штанги лёжа`` -> ``zhim-shtangi-lezha``.

    Slugs are stable identifiers, so they stay ASCII: they end up in logs,
    URLs and AI tool arguments, where Cyrillic is a nuisance.
    """
    transliterated = "".join(_TRANSLIT.get(ch, ch) for ch in name.strip().lower())
    slug = _NON_SLUG.sub("-", transliterated).strip("-")[:max_length].strip("-")
    return slug or "exercise"


def normalise_alias(alias: str) -> str:
    """Aliases are matched by exact array containment, so they are stored lowercase."""
    return " ".join(alias.strip().lower().split())

"""Slug generation for user-created exercises."""

from __future__ import annotations

import pytest

from gym_assistant.domain.slugs import normalise_alias, slugify


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Жим штанги лёжа", "zhim-shtangi-lezha"),
        ("Тяга Т-грифа", "tyaga-t-grifa"),
        ("  Приседания   со  штангой  ", "prisedaniya-so-shtangoy"),
        ("Bench Press", "bench-press"),
        ("Жим 45°", "zhim-45"),
        ("Подъём на бицепс", "podem-na-bitseps"),
    ],
)
def test_slugify(name: str, expected: str) -> None:
    assert slugify(name) == expected


def test_slugify_never_returns_empty() -> None:
    """A name of pure punctuation must still yield a usable identifier."""
    assert slugify("!!! ??? ...") == "exercise"
    assert slugify("") == "exercise"


def test_slugify_respects_max_length() -> None:
    slug = slugify("Очень длинное название упражнения которое никто не осилит", max_length=20)
    assert len(slug) <= 20
    assert not slug.endswith("-")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Жим Лёжа", "жим лёжа"),
        ("  БЕНЧ  ", "бенч"),
        ("тяга    штанги", "тяга штанги"),
    ],
)
def test_normalise_alias(raw: str, expected: str) -> None:
    """Aliases are matched by exact array containment, so they must be canonical."""
    assert normalise_alias(raw) == expected

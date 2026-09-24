"""Reading a photo into numbers - the part that does not need the API.

The call itself is the SDK's problem. What is worth pinning is everything
around it: the arithmetic, the rows that get dropped, and the band that says
how much to trust a portion.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from gym_assistant.ai.vision import (
    PROMPT,
    PROMPT_VERSION,
    SCHEMA,
    SECOND_IMAGE,
    SeenItem,
    _item,
    atwater_gap_pct,
)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "name": "Фо бо",
        "grams_low": 500,
        "grams_likely": 650,
        "grams_high": 800,
        "kcal_100g": 70,
        "protein_100g": 5,
        "fat_100g": 2,
        "carb_100g": 8,
        "basis": "пиала 600-700 мл, палочки",
        "needs_scale": False,
    }
    row.update(overrides)
    return row


# --- the arithmetic -------------------------------------------------------


def test_totals_come_from_grams_and_the_hundred_gram_snapshot() -> None:
    item = _item(_row())
    assert item is not None

    assert item.kcal == Decimal("455.0")
    assert item.protein_g == Decimal("32.5")


def test_the_band_width_is_measured_against_the_portion() -> None:
    """A 300 g band means one thing on a 650 g bowl and another on a 90 g bun."""
    wide = _item(_row(grams_low=500, grams_likely=650, grams_high=800))
    narrow = _item(_row(grams_low=85, grams_likely=90, grams_high=95))
    assert wide is not None and narrow is not None

    assert wide.band_width_pct == pytest.approx(Decimal("46"), abs=1)
    assert narrow.band_width_pct == pytest.approx(Decimal("11"), abs=1)


# --- rows that must not reach the diary -----------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [("grams_likely", 0), ("grams_likely", 9000), ("kcal_100g", 1500), ("kcal_100g", -5)],
)
def test_an_impossible_row_is_dropped_rather_than_repaired(field: str, value: int) -> None:
    """Repairing means inventing. A plate missing its sauce is easier to spot
    and fix than one carrying a number nobody produced."""
    assert _item(_row(**{field: value})) is None


def test_a_row_without_its_numbers_is_dropped() -> None:
    broken = _row()
    del broken["grams_likely"]

    assert _item(broken) is None


def test_a_band_that_does_not_contain_its_own_centre_is_straightened() -> None:
    """Seen from the model in practice, and cheaper to order than to refuse."""
    item = _item(_row(grams_low=700, grams_likely=650, grams_high=600))
    assert item is not None

    assert item.grams_low <= item.grams <= item.grams_high


# --- the consistency check ------------------------------------------------


def test_atwater_agrees_with_itself_on_a_sane_row() -> None:
    item = SeenItem(
        name="Куриная грудка",
        grams=Decimal(150),
        grams_low=Decimal(140),
        grams_high=Decimal(160),
        kcal_100g=Decimal(165),
        protein_100g=Decimal(31),
        fat_100g=Decimal("3.6"),
        carb_100g=Decimal(0),
        basis="тарелка",
        needs_scale=False,
    )

    assert atwater_gap_pct(item) < Decimal(15)


def test_atwater_catches_calories_invented_apart_from_the_macros() -> None:
    item = SeenItem(
        name="Выдумка",
        grams=Decimal(100),
        grams_low=Decimal(100),
        grams_high=Decimal(100),
        kcal_100g=Decimal(400),
        protein_100g=Decimal(20),
        fat_100g=Decimal(5),
        carb_100g=Decimal(10),
        basis="",
        needs_scale=False,
    )

    assert atwater_gap_pct(item) > Decimal(50)


# --- the frozen parts -----------------------------------------------------


def test_the_prompt_version_travels_with_the_prompt() -> None:
    """Changing the wording without changing the version makes every meal
    already recorded incomparable with every meal after it, silently."""
    assert PROMPT_VERSION == "food-v5"
    assert "ВИЛКУ ВЕСА" in PROMPT
    assert "одна еда — одна позиция" in PROMPT.lower()


def test_a_second_image_is_explained_rather_than_shown() -> None:
    """The bug this exists to prevent, seen for real: a delivery screenshot
    was attached with no word about what it was, so the model read the dish
    photographed at the top of it and ignored the "557 Kcal" printed below.

    The instruction is appended only with a second image - describing one that
    is not there would invite the model to imagine it.
    """
    assert "ВТОРОЕ ИЗОБРАЖЕНИЕ" not in PROMPT
    assert "ИСТИНУ" in SECOND_IMAGE
    # Seen for real on the second attempt: the stated 557 kcal was taken for
    # the bowl, and then the dressing that those 557 already covered was added
    # on top as its own row. The total went UP after a clarification.
    assert "двойной счёт" in SECOND_IMAGE
    assert "ЦЕЛИКОМ" in SECOND_IMAGE


def test_the_schema_demands_a_band_rather_than_a_number() -> None:
    item_schema = SCHEMA["properties"]["items"]["items"]  # type: ignore[index]
    required = set(item_schema["required"])  # type: ignore[index]

    assert {"grams_low", "grams_likely", "grams_high"} <= required
    assert "grams" not in required

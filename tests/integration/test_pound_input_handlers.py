"""The pounds button, driven through the real dispatcher.

The unit tests cover the grammar. These cover the mode behind the button: how
far it reaches, what it does to the nudges, and that it dies with the exercise
it was turned on for.
"""

from __future__ import annotations

from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.config import Settings
from gym_assistant.domain.services import ProfileService, WorkoutService
from tests.integration.bot_harness import BotHarness, build_harness

FOUR_PLATES_KG = Decimal("102.06")


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    settings = Settings(bot_token="42:test-token-not-real")  # type: ignore[call-arg]
    return build_harness(session, settings)


async def _sets(session: AsyncSession) -> list:
    user = await ProfileService(session).get_or_create_user(777)
    return await WorkoutService(session).current_sets(user.id)


# --- the marker needs no button ------------------------------------------


async def test_a_marked_line_is_stored_in_kilograms(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")
    await bot.send("жим 225х5 lbs")

    stored = await _sets(session)
    assert len(stored) == 1
    assert stored[0].weight_kg == FOUR_PLATES_KG


async def test_a_marked_line_is_shown_back_in_kilograms(bot: BotHarness) -> None:
    """The whole point: pounds go in, the diary stays readable in kilograms."""
    await bot.send("/workout")
    await bot.send("жим 225х5 lbs")

    assert "102.06 кг" in bot.session.last_text
    assert "lbs" not in bot.session.last_text


# --- the button ----------------------------------------------------------


async def test_the_panel_offers_the_mode(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")

    assert bot.session.button_with("Ввод в lbs")


async def test_the_mode_makes_a_bare_number_pounds(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Ввод в lbs")
    await bot.send("225х5")

    stored = await _sets(session)
    assert stored[-1].weight_kg == FOUR_PLATES_KG


async def test_the_panel_says_which_unit_it_is_reading(bot: BotHarness) -> None:
    """Kilograms stay on screen, so a bare number is ambiguous without this."""
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Ввод в lbs")

    assert "Ввод в фунтах" in bot.session.last_text


async def test_the_mode_turns_off_again(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Ввод в lbs")
    await bot.tap_button("Ввод в lbs")
    await bot.send("100х5")

    stored = await _sets(session)
    assert stored[-1].weight_kg == Decimal("100.00")


# --- the nudges ----------------------------------------------------------


async def test_the_nudges_become_pound_plates(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Ввод в lbs")

    assert bot.session.button_with("+10 lbs")


async def test_a_nudge_moves_by_the_number_on_the_button(
    bot: BotHarness, session: AsyncSession
) -> None:
    """+5 has to mean five pounds, and the panel still reads kilograms."""
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Ввод в lbs")
    await bot.send("225х5")
    await bot.tap_button("+5 lbs")
    await bot.tap_button("Повторить подход")

    stored = await _sets(session)
    assert stored[-1].weight_kg == Decimal("104.33")


# --- the scope -----------------------------------------------------------


async def test_the_mode_does_not_follow_to_the_next_exercise(
    bot: BotHarness, session: AsyncSession
) -> None:
    """It was asked for per exercise. Carrying it further means a bare number
    quietly becomes pounds on a machine loaded in kilos."""
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Ввод в lbs")
    await bot.send("присед 100х5")

    stored = await _sets(session)
    assert stored[-1].weight_kg == Decimal("100.00")


async def test_the_mode_does_not_survive_the_panel(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Ввод в lbs")
    await bot.tap_button("Другое упражнение")
    await bot.send("жим 100х5")

    stored = await _sets(session)
    assert stored[-1].weight_kg == Decimal("100.00")


async def test_the_mode_lasts_across_sets_of_the_same_exercise(
    bot: BotHarness, session: AsyncSession
) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Ввод в lbs")
    await bot.send("225х5")
    await bot.send("225х5")

    stored = await _sets(session)
    assert [item.weight_kg for item in stored[-2:]] == [FOUR_PLATES_KG, FOUR_PLATES_KG]

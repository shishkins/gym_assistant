"""Switching to pounds, driven through the real dispatcher.

The unit tests prove the conversion. These prove it is wired to the screen:
what the panel shows, what the buttons do, and that the rows underneath stay
kilograms whichever way the setting is pointing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.config import Settings
from gym_assistant.domain.services import ProfileService, WorkoutService
from tests.integration.bot_harness import BotHarness, build_harness


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    settings = Settings(bot_token="42:test-token-not-real")  # type: ignore[call-arg]
    return build_harness(session, settings)


async def _sets(session: AsyncSession) -> list:
    user = await ProfileService(session).get_or_create_user(777)
    return await WorkoutService(session).current_sets(user.id)


async def _switch_to_pounds(bot: BotHarness) -> None:
    await bot.send("/profile")
    await bot.tap_button("Перейти на lbs")


# --- the switch itself -----------------------------------------------------


async def test_the_card_offers_the_other_system(bot: BotHarness) -> None:
    await bot.send("/profile")

    assert "Единицы: <b>кг</b>" in bot.session.last_text
    assert bot.session.button_with("Перейти на lbs")


async def test_switching_flips_the_card_and_the_button(bot: BotHarness) -> None:
    await _switch_to_pounds(bot)

    assert "Единицы: <b>lbs</b>" in bot.session.last_text
    # And the way back is offered, or the setting is a one-way door.
    assert bot.session.button_with("Перейти на кг")


async def test_switching_says_the_history_was_not_rewritten(bot: BotHarness) -> None:
    """Every past number changing at once looks like data loss unless the
    message says what actually happened."""
    await _switch_to_pounds(bot)

    assert any("хранится как раньше" in text for text in bot.session.texts)


# --- logging a set in pounds ----------------------------------------------


async def test_a_typed_set_is_stored_in_kilograms(bot: BotHarness, session: AsyncSession) -> None:
    await _switch_to_pounds(bot)
    await bot.send("/workout")
    await bot.send("жим 225х5")

    stored = await _sets(session)
    assert len(stored) == 1
    assert stored[0].weight_kg == Decimal("102.06")


async def test_a_typed_set_is_shown_back_in_pounds(bot: BotHarness) -> None:
    await _switch_to_pounds(bot)
    await bot.send("/workout")
    await bot.send("жим 225х5")

    assert "225 lbs" in bot.session.last_text
    assert "кг" not in bot.session.last_text


async def test_the_same_number_means_kilograms_in_metric(
    bot: BotHarness, session: AsyncSession
) -> None:
    """The grammar does not change - only what the number means."""
    await bot.send("/workout")
    await bot.send("жим 225х5")

    stored = await _sets(session)
    assert stored[0].weight_kg == Decimal("225.00")


# --- the plate buttons -----------------------------------------------------


async def test_the_nudge_buttons_are_pound_plates(bot: BotHarness) -> None:
    await _switch_to_pounds(bot)
    await bot.send("/workout")
    await bot.send("жим 225х5")

    assert bot.session.button_with("+10")


async def test_a_nudge_moves_by_the_number_on_the_button(
    bot: BotHarness, session: AsyncSession
) -> None:
    """+5 has to mean five pounds on the panel and 2.27 kg in the row."""
    await _switch_to_pounds(bot)
    await bot.send("/workout")
    await bot.send("жим 225х5")
    await bot.tap_button("+5")

    assert "230 lbs" in bot.session.last_text

    await bot.tap_button("Повторить подход")
    stored = await _sets(session)
    assert stored[-1].weight_kg == Decimal("104.33")


# --- body weight -----------------------------------------------------------


async def test_body_weight_is_read_and_echoed_in_pounds(
    bot: BotHarness, session: AsyncSession
) -> None:
    await _switch_to_pounds(bot)
    await bot.send("/weight 180")

    assert "180 lbs" in bot.session.last_text

    user = await ProfileService(session).get_or_create_user(777)
    summary = await ProfileService(session).get_summary(user.id, today=date.today())
    assert summary.weight_kg == Decimal("81.65")


async def test_the_range_error_quotes_pounds(bot: BotHarness) -> None:
    """Quoting "от 20 до 400 кг" at someone typing pounds is the bug this
    message exists to avoid."""
    await _switch_to_pounds(bot)
    await bot.send("/weight 4000")

    assert "881.5 lbs" in bot.session.last_text
    assert "400 кг" not in bot.session.last_text

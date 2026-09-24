"""The food diary through the dispatcher, without spending a cent.

``build_vision`` is swapped for a stub, so the whole path - a photo arriving,
the card, the portion buttons, confirming, undoing - is checked for free. The
API call itself is the SDK's problem.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.ai.vision import Seen, SeenItem
from gym_assistant.bot.handlers import meals as meal_handlers
from gym_assistant.config import Settings
from gym_assistant.domain.models import Role
from gym_assistant.domain.services import AccessService, MealService, ProfileService
from tests.integration.bot_harness import BotHarness, build_harness

TELEGRAM_ID = 777


def _settings() -> Settings:
    return Settings(bot_token="42:test-token-not-real")  # type: ignore[call-arg]


def _item(name: str = "Фо бо", grams: str = "650", **extra: Any) -> SeenItem:
    defaults: dict[str, Any] = {
        "grams_low": Decimal("500"),
        "grams_high": Decimal("800"),
        "kcal_100g": Decimal("70"),
        "protein_100g": Decimal("5"),
        "fat_100g": Decimal("2"),
        "carb_100g": Decimal("8"),
        "basis": "пиала 600-700 мл",
        "needs_scale": False,
    }
    defaults.update(extra)
    return SeenItem(name=name, grams=Decimal(grams), **defaults)


class StubVision:
    """Answers without looking at anything."""

    def __init__(self, seen: Seen | None = None) -> None:
        self.seen = seen or Seen(
            kind="food",
            items=(_item(),),
            question=None,
            model="claude-sonnet-5",
            prompt_version="food-v3",
        )
        self.calls: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return True

    async def look(self, image: bytes, **kwargs: Any) -> Seen:
        self.calls.append(kwargs)
        return self.seen


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    return build_harness(session, _settings(), admin=True)


@pytest.fixture
def vision(monkeypatch: pytest.MonkeyPatch) -> StubVision:
    stub = StubVision()
    monkeypatch.setattr(meal_handlers, "build_vision", lambda *_: stub)
    return stub


async def _user_id(session: AsyncSession) -> int:
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)
    return user.id


async def _meals(session: AsyncSession) -> list:
    service = MealService(session)
    return await service.day_totals(await _user_id(session), days=1)


# --- the card -------------------------------------------------------------


async def test_a_food_photo_becomes_a_card(bot: BotHarness, vision: StubVision) -> None:
    await bot.send_photo()

    assert "455 ккал" in bot.session.last_text
    assert "Фо бо" in bot.session.last_text
    assert bot.session.button_with("Записать")


async def test_nothing_is_written_before_the_tap(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    """A diary that fills with guesses nobody agreed to is worse than an empty
    one: the daily total and everything above it is built on those rows."""
    await bot.send_photo()

    assert await _meals(session) == []


async def test_the_card_offers_the_ways_to_help_but_demands_none(
    bot: BotHarness, vision: StubVision
) -> None:
    await bot.send_photo()

    assert bot.session.button_with("Уточнить")
    assert bot.session.button_with("Не то")


async def test_what_the_person_ate_before_is_sent_as_an_anchor(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    """Without it the same croissant comes back under a new name every
    morning and nothing accumulates."""
    await MealService(session).record(
        await _user_id(session),
        items=[
            {
                "name": "Круассан с ветчиной",
                "grams": "90",
                "kcal_100g": "320",
                "protein_100g": "10",
                "fat_100g": "18",
                "carb_100g": "30",
            }
        ],
    )

    await bot.send_photo()

    assert "Круассан с ветчиной" in vision.calls[0]["hint"]


# --- correcting -----------------------------------------------------------


async def test_a_portion_multiplier_rescales_the_whole_plate(
    bot: BotHarness, vision: StubVision
) -> None:
    await bot.send_photo()
    await bot.tap_button("½ порции")

    assert "228 ккал" in bot.session.last_text


async def test_a_corrected_portion_is_marked_as_the_persons_own(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    """These are the only honest readings we ever get: run-to-run variance
    measures whether the model agrees with itself, and only a hand-corrected
    portion measures whether it was right."""
    await bot.send_photo()
    await bot.tap_button("2 порции")
    await bot.tap_button("Записать")

    meal = await MealService(session).last(await _user_id(session))
    assert meal is not None
    assert [item.grams_source for item in meal.items] == ["user"]


# --- confirming and undoing -----------------------------------------------


async def test_confirming_writes_the_meal(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    await bot.send_photo()
    await bot.tap_button("Записать")

    totals = await _meals(session)
    assert len(totals) == 1
    assert totals[0].kcal == Decimal("455.0")


async def test_the_reading_records_which_model_and_prompt_produced_it(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    """A change in either shifts the bias, and a bias that moves is the one
    thing the adaptive TDEE cannot absorb - so the seam has to be findable."""
    await bot.send_photo()
    await bot.tap_button("Записать")

    meal = await MealService(session).last(await _user_id(session))
    assert meal is not None
    assert meal.model == "claude-sonnet-5"
    assert meal.prompt_version == "food-v3"


async def test_undo_removes_it_again(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    await bot.send_photo()
    await bot.tap_button("Записать")
    await bot.tap_button("Отменить")

    assert await _meals(session) == []


async def test_discarding_writes_nothing(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    await bot.send_photo()
    await bot.tap_button("Не то")

    assert await _meals(session) == []


# --- a photo that is not food ---------------------------------------------


async def test_a_body_photo_still_goes_to_the_progress_album(
    bot: BotHarness, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one thing the whole arrangement rests on: the model saying which
    kind of photo this is. Measured on a real progress shot, three runs, all
    three agreed and none invented any food."""
    stub = StubVision(Seen(kind="body", items=(), question=None, model="m", prompt_version="v"))
    monkeypatch.setattr(meal_handlers, "build_vision", lambda *_: stub)

    await bot.send_photo()

    assert "фото прогресса" in bot.session.last_text.lower()
    assert await _meals(session) == []


# --- the gate -------------------------------------------------------------


async def test_a_photo_from_someone_without_a_subscription_costs_nothing(
    session: AsyncSession, vision: StubVision
) -> None:
    """Every photo here is money at the API. Without the gate, anyone who
    finds the bot spends the owner's budget a plate at a time."""
    plain = build_harness(session, _settings())
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)
    await AccessService(session).grant(user.id, Role.REGULAR_USER)

    await plain.send_photo()

    assert vision.calls == []

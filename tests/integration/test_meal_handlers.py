"""The food diary through the dispatcher, without spending a cent.

``build_vision`` is swapped for a stub, so the whole path - a photo arriving,
the card, the portion buttons, confirming, undoing - is checked for free. The
API call itself is the SDK's problem.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

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


def _seen(*items: SeenItem) -> Seen:
    return Seen(
        kind="food",
        items=items or (_item(),),
        question=None,
        model="claude-sonnet-5",
        prompt_version="food-v3",
    )


class StubVision:
    """Answers without looking at anything.

    Takes a sequence, because a clarification is supposed to CHANGE the
    answer - and a stub that says the same thing twice cannot show whether
    the first reading was kept or quietly replaced.
    """

    def __init__(self, *answers: Seen) -> None:
        self.answers = list(answers) or [_seen()]
        self.calls: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return True

    async def look(self, image: bytes, **kwargs: Any) -> Seen:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.answers) - 1)
        return self.answers[index]


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


# --- what makes the measurement possible ----------------------------------


async def test_the_first_reading_survives_a_clarification(
    bot: BotHarness, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guess being measured is what the model said from the photo alone.

    A clarification is meant to replace the answer - that is its job - and the
    first reading has to sit outside what it replaces. Without this the diary
    holds only corrected numbers: all of them right, and useless for working
    out how far off the model was. The person is weighing portions and sending
    delivery screenshots for exactly this measurement, so losing the "before"
    wastes their work rather than ours.
    """
    stub = StubVision(_seen(_item(grams="650")), _seen(_item(grams="400")))
    monkeypatch.setattr(meal_handlers, "build_vision", lambda *_: stub)

    await bot.send_photo()
    await bot.send_photo()  # the delivery screenshot
    await bot.tap_button("Записать")

    meal = await MealService(session).last(await _user_id(session))
    assert meal is not None
    assert meal.first_pass is not None

    guessed = Decimal(meal.first_pass["items"][0]["grams"])
    assert guessed == Decimal("650"), "первая оценка затёрта уточнением"
    assert meal.items[0].grams == Decimal("400.0"), "уточнённое значение не сохранилось"


async def test_a_corrected_portion_does_not_disturb_the_first_reading(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    await bot.send_photo()
    await bot.tap_button("2 порции")
    await bot.tap_button("Записать")

    meal = await MealService(session).last(await _user_id(session))
    assert meal is not None
    assert Decimal(meal.first_pass["items"][0]["grams"]) == Decimal("650")
    assert meal.items[0].grams == Decimal("1300.0")


async def test_a_photo_sent_after_the_card_clarifies_it(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    """Photograph the plate, then send the delivery screenshot - the order the
    person actually described. Requiring a button press between them taxes the
    one habit worth encouraging."""
    await bot.send_photo()
    await bot.send_photo()

    assert len(vision.calls) == 2
    assert vision.calls[1]["extra"] is not None, "второе фото не доехало до модели"
    assert vision.calls[1]["previous"], "модель не получила, что уже разобрала"
    assert await _meals(session) == []


async def test_the_meal_records_which_help_was_used(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    """A portion read off a delivery screenshot is worth more than one judged
    against a plate, so the two have to be tellable apart later."""
    await bot.send_photo()
    await bot.send_photo()
    await bot.tap_button("Записать")

    meal = await MealService(session).last(await _user_id(session))
    assert meal is not None
    assert meal.hints is not None
    assert meal.hints["used"][0]["photo"] is True


async def test_a_written_hint_reaches_the_model_and_is_recorded(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    await bot.send_photo()
    await bot.tap_button("Уточнить")
    await bot.send("тарелка 30 см")
    await bot.tap_button("Записать")

    assert vision.calls[1]["note"] == "тарелка 30 см"

    meal = await MealService(session).last(await _user_id(session))
    assert meal is not None
    assert meal.hints["used"][0]["text"] == "тарелка 30 см"


# --- reading the diary back -----------------------------------------------


def _vietnam() -> Settings:
    """The bot as it actually runs: a clock seven hours ahead of UTC."""
    return Settings(  # type: ignore[call-arg]
        bot_token="42:test-token-not-real", timezone="Asia/Ho_Chi_Minh"
    )


async def test_the_day_lists_what_was_eaten(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    """The total alone was the whole screen until now, which says how much but
    not what - and "what" is the only part worth correcting."""
    await bot.send_photo()
    await bot.tap_button("Записать")

    await bot.send("/food")

    assert "Фо бо" in bot.session.last_text
    assert "455" in bot.session.last_text


async def test_a_day_with_nothing_says_so_and_still_offers_the_week(
    bot: BotHarness, vision: StubVision
) -> None:
    await bot.send("/food")

    assert "Ничего не записано" in bot.session.last_text
    assert bot.session.button_with("Неделя")


async def test_yesterday_is_one_tap_away(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    await bot.send_photo()
    await bot.tap_button("Записать")
    await bot.send("/food")
    await bot.tap_button("Вчера")

    assert "Вчера" in bot.session.last_text
    assert "Фо бо" not in bot.session.last_text, "вчерашний день показал сегодняшнюю еду"


async def test_a_meal_can_be_removed_later_not_only_right_after_saving(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    """Undo covers a mistaken tap; this covers noticing an hour later, which
    is when a wrong entry is usually spotted."""
    await bot.send_photo()
    await bot.tap_button("Записать")
    await bot.send("/food")
    await bot.tap_button("Убрать приём")
    await bot.tap_button("Фо бо")

    assert await _meals(session) == []


async def test_the_week_shows_days_without_records_as_gaps(
    bot: BotHarness, session: AsyncSession, vision: StubVision
) -> None:
    """A gap is information: it keeps a run of untracked days visible instead
    of quietly dragging the average down."""
    await bot.send_photo()
    await bot.tap_button("Записать")
    await bot.send("/food")
    await bot.tap_button("Неделя")

    body = bot.session.last_text
    assert body.count("—") >= 6, "дни без записей не показаны пропусками"
    assert "В среднем за день" in body


# --- the day boundary -----------------------------------------------------


async def test_a_late_dinner_counts_as_that_evening_not_the_day_before(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dinner at one in the morning in Vietnam is seven the previous evening
    UTC. Counting days by UTC files it under yesterday, so the daily total
    comes out wrong on exactly the days someone ate late.
    """
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    service = MealService(session)
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)

    local_night = datetime(2026, 9, 20, 1, 30, tzinfo=tz)
    await service.record(
        user.id,
        items=[
            {
                "name": "Поздний ужин",
                "grams": "300",
                "kcal_100g": "150",
                "protein_100g": "10",
                "fat_100g": "5",
                "carb_100g": "15",
            }
        ],
        eaten_at=local_night,
    )

    same_day = await service.meals_on(user.id, date(2026, 9, 20), tz=tz)
    assert len(same_day) == 1, "поздний ужин уехал в другой день"

    day_before = await service.meals_on(user.id, date(2026, 9, 19), tz=tz)
    assert day_before == []

"""Body composition through the dispatcher, with the model swapped out.

What is checked here is everything around the API call: who sees the
button, whose photo can be read, that a second press does not pay twice,
that the bill is written even when the answer is thrown away. The reader
itself is replaced by a stub everywhere except the last two tests, which
drive the real :class:`BodyVision` against a fake client to prove it goes
through the budget and the usage log.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.ai.body import PROMPT_VERSION, BodyReading, BodyRefusedError, BodyVision
from gym_assistant.ai.client import BudgetExceededError
from gym_assistant.ai.usage import UsageService
from gym_assistant.bot.handlers import body as body_handlers
from gym_assistant.bot.keyboards import BodyCB
from gym_assistant.bot.texts import ru
from gym_assistant.config import Settings
from gym_assistant.domain.body import Band
from gym_assistant.domain.models import AiUsage, BodyEstimate, Role, Sex
from gym_assistant.domain.services import AccessService, MeasurementService, ProfileService
from tests.integration.bot_harness import BotHarness, build_harness

TELEGRAM_ID = 777
MODEL = "claude-sonnet-5"


def _settings(**overrides: Any) -> Settings:
    return Settings(  # type: ignore[call-arg]
        bot_token="42:test-token-not-real", anthropic_api_key="sk-ant-test-not-real", **overrides
    )


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> AsyncIterator[BotHarness]:
    """The harness, with a key configured.

    The dispatcher is built once for the whole suite, with whichever
    settings the first test brought - without a key. The button is only
    drawn when a key is set, so these tests swap it in and put it back.
    """
    harness = build_harness(session, _settings())
    previous = harness.dispatcher["settings"]
    harness.dispatcher["settings"] = _settings()
    yield harness
    harness.dispatcher["settings"] = previous


class StubVision:
    def __init__(self, reading: BodyReading | None = None, error: Exception | None = None) -> None:
        self._reading = reading or _reading()
        self._error = error
        self.looked: list[Sex | None] = []

    available = True
    model = MODEL

    async def look(self, image: bytes, *, user_id: int, sex: Sex | None, **_: Any) -> BodyReading:
        self.looked.append(sex)
        if self._error is not None:
            raise self._error
        return self._reading


def _reading(kind: str = "body", likely: str = "18", usable: bool = True) -> BodyReading:
    value = Decimal(likely)
    return BodyReading(
        kind=kind,  # type: ignore[arg-type]
        usable=usable,
        band=Band(value - 3, value, value + 4) if kind == "body" else None,
        observations=("пресс угадывается",),
        limits=None,
        model=MODEL,
        prompt_version=PROMPT_VERSION,
        cost_usd=Decimal("0.01"),
    )


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> StubVision:
    vision = StubVision()
    monkeypatch.setattr(body_handlers, "build_body_vision", lambda *_: vision)
    return vision


async def _subscribe(session: AsyncSession, *, sex: Sex | None = Sex.MALE) -> int:
    profiles = ProfileService(session)
    user = await profiles.get_or_create_user(TELEGRAM_ID)
    await AccessService(session).grant(user.id, Role.SUBSCRIPTION_USER)
    await profiles.update_profile(user.id, sex=sex, height_cm=180)
    return user.id


async def _estimates(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(BodyEstimate)) or 0


# --- who gets to ask ------------------------------------------------------


async def test_an_ordinary_users_photo_has_no_button_and_body_is_not_theirs(
    bot: BotHarness, stub: StubVision
) -> None:
    await bot.send_photo()
    assert bot.session.last_markup is None, "кнопка оценки показана без подписки"

    await bot.send("/body")
    assert stub.looked == []


async def test_a_subscriber_presses_the_button_and_gets_kilograms(
    bot: BotHarness, session: AsyncSession, stub: StubVision
) -> None:
    await _subscribe(session)

    await bot.send_photo(caption="80")
    await bot.tap_button("Оценить")

    assert stub.looked == [Sex.MALE], "пол из профиля не дошёл до модели"
    reply = bot.session.last_text
    assert "15–22%" in reply
    assert "тощая масса — 62.4–68 кг" in reply
    assert "FFMI" in reply
    assert await _estimates(session) == 1


async def test_a_second_press_shows_the_stored_estimate_without_paying_again(
    bot: BotHarness, session: AsyncSession, stub: StubVision
) -> None:
    await _subscribe(session)
    await bot.send_photo(caption="80")
    data = bot.session.button_with("Оценить")

    await bot.tap(data)
    await bot.tap(data)

    assert len(stub.looked) == 1
    assert await _estimates(session) == 1
    assert "15–22%" in bot.session.last_text


async def test_someone_elses_photo_cannot_be_read_by_forging_the_button(
    bot: BotHarness, session: AsyncSession, stub: StubVision
) -> None:
    await _subscribe(session)
    stranger = await ProfileService(session).get_or_create_user(999_999)
    theirs = await MeasurementService(session).record(stranger.id, photo_file_id="their-photo")

    await bot.tap(BodyCB(measurement_id=theirs.id).pack())

    assert stub.looked == []
    assert bot.session.last_text == ru.BODY_PHOTO_GONE


# --- /body ---------------------------------------------------------------


async def test_body_without_any_photo_says_how_to_get_one(
    bot: BotHarness, session: AsyncSession, stub: StubVision
) -> None:
    await _subscribe(session)

    await bot.send("/body")

    assert bot.session.last_text == ru.BODY_NO_PHOTO
    assert stub.looked == []


async def test_body_reads_the_latest_photo_and_asks_for_a_weight_when_there_is_none(
    bot: BotHarness, session: AsyncSession, stub: StubVision
) -> None:
    await _subscribe(session)
    await bot.send_photo()

    await bot.send("/body")

    assert len(stub.looked) == 1
    assert ru.BODY_NO_WEIGHT in bot.session.last_text


# --- when there is nothing to keep ----------------------------------------


async def test_a_photo_that_is_not_a_body_stores_nothing(
    bot: BotHarness, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    vision = StubVision(reading=_reading(kind="other"))
    monkeypatch.setattr(body_handlers, "build_body_vision", lambda *_: vision)
    await _subscribe(session)
    await bot.send_photo()

    await bot.tap_button("Оценить")

    assert bot.session.last_text == ru.BODY_NOT_A_BODY
    assert await _estimates(session) == 0


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (BudgetExceededError("0"), ru.AI_BUDGET_SPENT),
        (BodyRefusedError("refusal"), ru.BODY_REFUSED),
    ],
)
async def test_failures_get_their_own_message(
    bot: BotHarness,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected: str,
) -> None:
    vision = StubVision(error=error)
    monkeypatch.setattr(body_handlers, "build_body_vision", lambda *_: vision)
    await _subscribe(session)
    await bot.send_photo()

    await bot.tap_button("Оценить")

    assert bot.session.last_text == expected
    assert await _estimates(session) == 0


# --- over time -------------------------------------------------------------


async def test_a_small_change_since_last_time_is_called_noise(
    bot: BotHarness, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _subscribe(session)
    first = StubVision(reading=_reading(likely="18"))
    monkeypatch.setattr(body_handlers, "build_body_vision", lambda *_: first)
    await bot.send_photo(caption="80")
    await bot.tap_button("Оценить")

    second = StubVision(reading=_reading(likely="17"))
    monkeypatch.setattr(body_handlers, "build_body_vision", lambda *_: second)
    await bot.send_photo(caption="79")
    await bot.tap_button("Оценить")

    assert "без заметных перемен" in bot.session.last_text


# --- the real reader, against a fake client --------------------------------


class _FakeMessages:
    def __init__(self, answer: str, stop_reason: str = "end_turn") -> None:
        self.calls = 0
        self._answer = answer
        self._stop = stop_reason

    async def create(self, **_: Any) -> Any:
        self.calls += 1
        return SimpleNamespace(
            model=MODEL,
            stop_reason=self._stop,
            usage=SimpleNamespace(input_tokens=1500, output_tokens=300),
            content=[SimpleNamespace(type="text", text=self._answer)],
        )


async def test_the_reader_checks_the_budget_before_spending(session: AsyncSession) -> None:
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)
    vision = BodyVision(_settings(ai_monthly_limit_usd=0), UsageService(session))
    fake = _FakeMessages("{}")
    vision._client = SimpleNamespace(messages=fake)  # type: ignore[assignment]

    with pytest.raises(BudgetExceededError):
        await vision.look(b"jpeg", user_id=user.id, sex=Sex.MALE)

    assert fake.calls == 0


async def test_the_reader_logs_what_a_refusal_cost(session: AsyncSession) -> None:
    """Refused or not, the call was billed, and the month's limit must know."""
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)
    vision = BodyVision(_settings(), UsageService(session))
    vision._client = SimpleNamespace(  # type: ignore[assignment]
        messages=_FakeMessages("", stop_reason="refusal")
    )

    with pytest.raises(BodyRefusedError):
        await vision.look(b"jpeg", user_id=user.id, sex=None)

    logged = await session.scalar(select(func.count()).select_from(AiUsage))
    assert logged == 1
    assert await UsageService(session).spent_this_month(user.id) > 0

"""A crash in a handler is logged AND told to the person.

Until the review the second half never happened: the error middleware looked
for ``answer`` on the Update, which has none, so every failure was silent and
a pressed button kept spinning.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.keyboards import BodyCB
from gym_assistant.bot.texts import ru
from gym_assistant.config import Settings
from gym_assistant.domain.models import Role
from gym_assistant.domain.services import (
    AccessService,
    BodyService,
    MeasurementService,
    ProfileService,
)
from tests.integration.bot_harness import TELEGRAM_USER_ID, BotHarness, build_harness


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    return build_harness(session, Settings(bot_token="42:test-token-not-real"))  # type: ignore[call-arg]


async def _boom(*_: Any, **__: Any) -> Any:
    raise RuntimeError("simulated failure")


async def test_a_crash_on_a_message_is_reported(
    bot: BotHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(MeasurementService, "record", _boom)

    await bot.send("/weight 80")

    assert bot.session.last_text == ru.UNEXPECTED_ERROR


async def test_a_crash_on_a_button_stops_the_spinner_and_is_reported(
    bot: BotHarness, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await ProfileService(session).get_or_create_user(TELEGRAM_USER_ID)
    await AccessService(session).grant(user.id, Role.SUBSCRIPTION_USER)
    monkeypatch.setattr(BodyService, "photo", _boom)

    await bot.tap(BodyCB(measurement_id=1).pack())

    names = [type(call).__name__ for call in bot.session.calls]
    assert "AnswerCallbackQuery" in names
    assert bot.session.last_text == ru.UNEXPECTED_ERROR

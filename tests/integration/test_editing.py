"""Redrawing in place: "not modified" is not an error to answer.

Found by the review: pressing "−" at weight 0 left the panel unchanged,
Telegram refused the no-op edit, and the bot posted a fresh copy of the
panel on every press.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.keyboards import WorkoutCB
from gym_assistant.config import Settings
from tests.integration.bot_harness import BotHarness, RecordingSession, build_harness


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    return build_harness(session, Settings(bot_token="42:test-token-not-real"))  # type: ignore[call-arg]


def _refuse_edits(monkeypatch: pytest.MonkeyPatch, bot: BotHarness, reason: str) -> None:
    original = RecordingSession.make_request

    async def make_request(
        self: RecordingSession,
        b: Any,
        method: Any,
        timeout: Any = None,  # noqa: ASYNC109 - aiogram's signature
    ) -> Any:
        if type(method).__name__ == "EditMessageText":
            self.calls.append(method)
            raise TelegramBadRequest(method=method, message=f"Bad Request: {reason}")
        return await original(self, b, method, timeout)

    monkeypatch.setattr(RecordingSession, "make_request", make_request)


def _sent(bot: BotHarness) -> int:
    return sum(1 for call in bot.session.calls if type(call).__name__ == "SendMessage")


async def test_an_edit_that_changes_nothing_sends_nothing(
    bot: BotHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await bot.send("/workout")
    _refuse_edits(monkeypatch, bot, "message is not modified")
    before = _sent(bot)

    await bot.tap(WorkoutCB(action="panel").pack())

    assert _sent(bot) == before


async def test_an_edit_refused_for_another_reason_still_gets_a_fresh_message(
    bot: BotHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await bot.send("/workout")
    _refuse_edits(monkeypatch, bot, "message can't be edited")
    before = _sent(bot)

    await bot.tap(WorkoutCB(action="panel").pack())

    assert _sent(bot) == before + 1

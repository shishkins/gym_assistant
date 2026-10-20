"""A profile choice is saved even when the old message cannot be deleted.

The review: the toast "updated" went out, then message.delete() failed on a
message older than 48 hours, and the failure rolled the change back.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.keyboards import ChoiceCB
from gym_assistant.bot.texts import ru
from gym_assistant.config import Settings
from gym_assistant.domain.models import Goal
from gym_assistant.domain.services import ProfileService
from tests.integration.bot_harness import (
    TELEGRAM_USER_ID,
    BotHarness,
    RecordingSession,
    build_harness,
)


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    return build_harness(session, Settings(bot_token="42:test-token-not-real"))  # type: ignore[call-arg]


async def test_an_old_message_that_cannot_be_deleted_does_not_undo_the_choice(
    bot: BotHarness, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = RecordingSession.make_request

    async def make_request(
        self: RecordingSession,
        b: Any,
        method: Any,
        timeout: Any = None,  # noqa: ASYNC109 - aiogram's signature
    ) -> Any:
        if type(method).__name__ == "DeleteMessage":
            raise TelegramBadRequest(method=method, message="Bad Request: message can't be deleted")
        return await original(self, b, method, timeout)

    monkeypatch.setattr(RecordingSession, "make_request", make_request)
    user = await ProfileService(session).get_or_create_user(TELEGRAM_USER_ID)

    await bot.tap(ChoiceCB(field="goal", value=Goal.STRENGTH.value).pack())

    profile = await ProfileService(session).get_profile(user.id)
    assert profile.goal == Goal.STRENGTH.value
    # The harness never rolls back, so the saved row alone proves little;
    # in production the exception rolled the update back. What the person
    # sees is the honest signal: their card, not the crash message.
    assert bot.session.last_text != ru.UNEXPECTED_ERROR
    assert ru.PROFILE_HEADER in bot.session.last_text

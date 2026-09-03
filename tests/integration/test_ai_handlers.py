"""The assistant through the dispatcher, without spending a cent.

``build_assistant`` is swapped for a stub, so everything around the API call
- the role gate, the budget message, storing the exchange - is checked for
free. The API call itself is the SDK's problem.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.ai.client import (
    AiOverloadedError,
    AiUnavailableError,
    Answer,
    BudgetExceededError,
)
from gym_assistant.ai.conversation import ConversationService
from gym_assistant.ai.usage import Tokens, UsageService
from gym_assistant.bot.handlers import ai as ai_handlers
from gym_assistant.config import Settings
from gym_assistant.domain.models import Role
from gym_assistant.domain.services import AccessService, ProfileService
from tests.integration.bot_harness import BotHarness, build_harness

TELEGRAM_ID = 777


def _settings() -> Settings:
    return Settings(bot_token="42:test-token-not-real")  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    """An ordinary user - no subscription."""
    return build_harness(session, _settings())


@pytest_asyncio.fixture
async def admin_bot(session: AsyncSession) -> BotHarness:
    """The owner, who outranks a subscriber."""
    return build_harness(session, _settings(), admin=True)


class StubAssistant:
    """Answers without calling anything."""

    def __init__(self, *, text: str = "Жим вырос с 70 до 80 кг.", fails: bool = False) -> None:
        self._text = text
        self._fails = fails
        self.asked: list[str] = []

    @property
    def available(self) -> bool:
        return True

    async def ask(self, ctx: Any, question: str, **kwargs: Any) -> Answer:
        self.asked.append(question)
        if self._fails:
            raise BudgetExceededError("0")
        return Answer(
            text=self._text,
            tokens=Tokens(input=2000, output=200),
            cost_usd=Decimal("0.015"),
            tool_calls=["get_exercise_progress"],
            turns=[
                {"role": "user", "content": question},
                {"role": "assistant", "content": [{"type": "text", "text": self._text}]},
            ],
        )


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> StubAssistant:
    assistant = StubAssistant()
    monkeypatch.setattr(ai_handlers, "build_assistant", lambda *_: assistant)
    return assistant


async def _subscribe(session: AsyncSession) -> None:
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)
    await AccessService(session).grant(user.id, Role.SUBSCRIPTION_USER)


# --- the gate -------------------------------------------------------------


async def test_an_ordinary_user_cannot_reach_the_assistant(
    bot: BotHarness, stub: StubAssistant
) -> None:
    await bot.send("/ask как растёт жим")

    assert stub.asked == [], "ассистент был вызван без подписки"


async def test_the_command_reads_as_unknown_rather_than_forbidden(
    bot: BotHarness, stub: StubAssistant
) -> None:
    """Neither an answer nor an explanation of what they are missing."""
    await bot.send("/ask как растёт жим")

    reply = bot.session.last_text.lower()
    assert "жим вырос" not in reply, "ответ ассистента ушёл без подписки"
    assert "подписк" not in reply


async def test_a_subscriber_gets_an_answer(
    bot: BotHarness, session: AsyncSession, stub: StubAssistant
) -> None:
    await _subscribe(session)

    await bot.send("/ask как растёт жим")

    assert "Жим вырос" in bot.session.last_text
    assert stub.asked == ["как растёт жим"]


async def test_an_admin_outranks_a_subscriber(admin_bot: BotHarness, stub: StubAssistant) -> None:
    """Roles are ordered, so the owner never needs to grant themselves a
    subscription to use their own bot."""
    await admin_bot.send("/ask как растёт жим")

    assert stub.asked == ["как растёт жим"]


# --- the exchange ---------------------------------------------------------


async def test_ask_without_a_question_explains_itself(
    bot: BotHarness, session: AsyncSession, stub: StubAssistant
) -> None:
    await _subscribe(session)

    await bot.send("/ask")

    assert "/ask" in bot.session.last_text
    assert stub.asked == []


async def test_the_exchange_is_stored(
    bot: BotHarness, session: AsyncSession, stub: StubAssistant
) -> None:
    """It has to survive a restart: the API keeps no state for us."""
    await _subscribe(session)
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)

    await bot.send("/ask как растёт жим")

    talk = await ConversationService(session).active(user.id)
    history = await ConversationService(session).history(talk.id)
    assert len(history) == 2
    assert history[0]["content"] == "как растёт жим"


async def test_a_second_question_continues_the_same_conversation(
    bot: BotHarness, session: AsyncSession, stub: StubAssistant
) -> None:
    await _subscribe(session)
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)

    await bot.send("/ask первый вопрос")
    await bot.send("/ask второй вопрос")

    talk = await ConversationService(session).active(user.id)
    assert len(await ConversationService(session).history(talk.id)) == 4


async def test_reset_starts_a_new_conversation(
    bot: BotHarness, session: AsyncSession, stub: StubAssistant
) -> None:
    await _subscribe(session)
    await bot.send("/ask первый вопрос")

    await bot.send("/ai_reset")

    assert "заново" in bot.session.last_text


# --- when it cannot answer ------------------------------------------------


async def test_a_spent_budget_says_so_plainly(
    bot: BotHarness, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _subscribe(session)
    monkeypatch.setattr(ai_handlers, "build_assistant", lambda *_: StubAssistant(fails=True))

    await bot.send("/ask как растёт жим")

    assert "бюджет" in bot.session.last_text.lower()


async def test_without_an_api_key_it_says_it_is_not_configured(
    bot: BotHarness, session: AsyncSession
) -> None:
    """No stub here: the real assistant with no key must refuse cleanly."""
    await _subscribe(session)

    await bot.send("/ask как растёт жим")

    assert "не настроен" in bot.session.last_text


async def test_usage_report_is_available_to_a_subscriber(
    bot: BotHarness, session: AsyncSession, stub: StubAssistant
) -> None:
    await _subscribe(session)

    await bot.send("/ai_usage")

    assert "$" in bot.session.last_text


async def test_an_overloaded_api_is_reported_as_temporary(
    bot: BotHarness, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """529 passes by itself, so the message must say "try again", not
    "something is broken" - and must say the attempt was free."""
    await _subscribe(session)

    class Overloaded(StubAssistant):
        async def ask(self, ctx: Any, question: str, **kwargs: Any) -> Answer:
            raise AiOverloadedError("529")

    monkeypatch.setattr(ai_handlers, "build_assistant", lambda *_: Overloaded())

    await bot.send("/ask как растёт жим")

    reply = bot.session.last_text.lower()
    assert "перегружен" in reply
    assert "не стоило" in reply, "человек должен знать, что попытка была бесплатной"


async def test_a_real_failure_is_not_dressed_up_as_overload(
    bot: BotHarness, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AiOverloadedError subclasses AiUnavailableError, so the except order
    matters: swap the two clauses and every failure reads as "try again"."""
    await _subscribe(session)

    class Broken(StubAssistant):
        async def ask(self, ctx: Any, question: str, **kwargs: Any) -> Answer:
            raise AiUnavailableError("400")

    monkeypatch.setattr(ai_handlers, "build_assistant", lambda *_: Broken())

    await bot.send("/ask как растёт жим")

    assert "перегружен" not in bot.session.last_text.lower()


# --- whose spending is whose ----------------------------------------------
#
# Reported by a second pair of eyes: /ai_usage showed the total across
# everyone. How much someone else asks the assistant is not a subscriber's
# business - that view belongs to the owner.


async def test_ai_usage_shows_only_your_own_spending(
    bot: BotHarness, session: AsyncSession, stub: StubAssistant
) -> None:
    await _subscribe(session)
    other = await ProfileService(session).get_or_create_user(4242, username="friend")
    await UsageService(session).record(
        user_id=other.id, session_id=None, model="claude-opus-5",
        tokens=Tokens(input=1_000_000, output=1_000_000),
    )

    await bot.send("/ai_usage")

    reply = bot.session.last_text
    assert "30.00" not in reply, "чужие расходы попали в личный отчёт"
    assert "0.00" in reply


async def test_ai_usage_names_the_current_model(
    bot: BotHarness, session: AsyncSession, stub: StubAssistant
) -> None:
    """Switching the model is an .env edit and a restart, so the bot has to
    say which one is actually running."""
    await _subscribe(session)

    await bot.send("/ai_usage")

    assert "claude-opus-5" in bot.session.last_text


async def test_the_whole_bill_is_admin_only(
    bot: BotHarness, session: AsyncSession, stub: StubAssistant
) -> None:
    await _subscribe(session)

    await bot.send("/ai_costs")

    assert "По людям" not in bot.session.last_text


async def test_an_admin_sees_the_whole_bill(
    admin_bot: BotHarness, session: AsyncSession
) -> None:
    other = await ProfileService(session).get_or_create_user(4242, username="friend")
    await UsageService(session).record(
        user_id=other.id, session_id=None, model="claude-opus-5",
        tokens=Tokens(input=1_000_000),
    )

    admin_bot.session.clear()
    await admin_bot.send("/ai_costs")

    reply = admin_bot.session.last_text
    assert "friend" in reply
    assert "5.00" in reply
    assert "claude-opus-5" in reply

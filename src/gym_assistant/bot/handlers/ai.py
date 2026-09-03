"""The assistant, behind a subscription.

The whole router is filtered on ``RequireRole(SUBSCRIPTION_USER)``: this is
the one part of the bot that costs money per use, so the gate is on the
router rather than inside each handler, where it would eventually be
forgotten on one of them.
"""

from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.ai.client import AiAssistant, AiUnavailableError, BudgetExceededError
from gym_assistant.ai.conversation import ConversationService
from gym_assistant.ai.tools import ToolContext
from gym_assistant.ai.usage import UsageService
from gym_assistant.bot.filters import RequireRole
from gym_assistant.bot.texts import ru
from gym_assistant.config import Settings
from gym_assistant.domain.models import Role, User

log = structlog.get_logger(__name__)


def build_assistant(settings: Settings, usage: UsageService) -> AiAssistant:
    """A seam, so tests can drive the handler without calling the API.

    Everything else here is worth testing - the role gate, the budget
    message, storing the exchange - and none of it should cost money to
    check.
    """
    return AiAssistant(settings, usage)


router = Router(name="ai")
router.message.filter(RequireRole(Role.SUBSCRIPTION_USER))


@router.message(Command("ask"))
async def cmd_ask(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: User,
    settings: Settings,
) -> None:
    question = (command.args or "").strip()
    if not question:
        await message.answer(ru.AI_USAGE)
        return
    await _answer(message, question, session, user, settings)


@router.message(Command("ai_reset"))
async def cmd_reset(message: Message, session: AsyncSession, user: User) -> None:
    ended = await ConversationService(session).reset(user.id)
    await message.answer(ru.AI_RESET if ended else ru.AI_RESET_EMPTY)


@router.message(Command("ai_usage"))
async def cmd_usage(
    message: Message, session: AsyncSession, user: User, settings: Settings
) -> None:
    usage = UsageService(session)
    mine = await usage.spent_this_month(user.id)
    everyone = await usage.spent_this_month_total()
    await message.answer(
        ru.AI_USAGE_REPORT.format(
            mine=f"{mine:.2f}",
            everyone=f"{everyone:.2f}",
            limit=f"{settings.ai_monthly_limit_usd:.2f}",
        )
    )


async def _answer(
    message: Message,
    question: str,
    session: AsyncSession,
    user: User,
    settings: Settings,
) -> None:
    """One question, one answer, with the exchange stored either way."""
    assistant = build_assistant(settings, UsageService(session))
    if not assistant.available:
        await message.answer(ru.AI_NOT_CONFIGURED)
        return

    conversation = ConversationService(session)
    talk = await conversation.active(user.id)
    history = await conversation.history(talk.id)

    # Typing dots: a question with several lookups behind it takes seconds,
    # and silence reads as a bot that died.
    if message.bot is not None:
        await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        answer = await assistant.ask(
            ToolContext(session=session, user=user),
            question,
            history=history,
            session_id=talk.id,
        )
    except BudgetExceededError:
        await message.answer(ru.AI_BUDGET_SPENT)
        return
    except AiUnavailableError as exc:
        log.warning("ai_unavailable", reason=str(exc))
        await message.answer(ru.AI_UNAVAILABLE)
        return

    await conversation.append(talk.id, answer.turns)
    log.info(
        "ai_answered",
        user_id=user.id,
        cost_usd=str(answer.cost_usd),
        tools=answer.tool_calls,
        input_tokens=answer.tokens.input,
        cache_read=answer.tokens.cache_read,
    )

    await message.answer(answer.text or ru.AI_EMPTY_ANSWER)

"""Keeping the conversation, and knowing when to drop it.

Every stored turn is resent on every later request, so this file is as much
about the bill as about correctness.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.ai.conversation import IDLE_HOURS, MAX_TURNS, ConversationService
from gym_assistant.domain.services import ProfileService

TELEGRAM_ID = 6001


async def _user_id(session: AsyncSession) -> int:
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)
    return user.id


def _question(text: str) -> dict[str, object]:
    return {"role": "user", "content": text}


def _tool_call() -> list[dict[str, object]]:
    """An assistant asking for a tool, and the result coming back."""
    return [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "tu_1", "name": "get_profile", "input": {}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "{}"}],
        },
    ]


# --- one live conversation ------------------------------------------------


async def test_the_same_conversation_is_reused(session: AsyncSession) -> None:
    user_id = await _user_id(session)
    service = ConversationService(session)

    first = await service.active(user_id)
    second = await service.active(user_id)

    assert first.id == second.id


async def test_a_stale_conversation_is_replaced(session: AsyncSession) -> None:
    """Yesterday's context should not be dragged along - or paid for."""
    user_id = await _user_id(session)
    service = ConversationService(session)
    now = datetime.now(UTC)

    old = await service.active(user_id, now=now - timedelta(hours=IDLE_HOURS + 1))
    fresh = await service.active(user_id, now=now)

    assert fresh.id != old.id
    assert old.is_active is False


async def test_reset_ends_the_conversation(session: AsyncSession) -> None:
    user_id = await _user_id(session)
    service = ConversationService(session)
    started = await service.active(user_id)

    assert await service.reset(user_id) is True

    assert (await service.active(user_id)).id != started.id


async def test_reset_with_nothing_running_says_so(session: AsyncSession) -> None:
    user_id = await _user_id(session)

    assert await ConversationService(session).reset(user_id) is False


# --- history --------------------------------------------------------------


async def test_turns_come_back_in_order(session: AsyncSession) -> None:
    user_id = await _user_id(session)
    service = ConversationService(session)
    talk = await service.active(user_id)

    await service.append(talk.id, [_question("первый"), _question("второй")])

    history = await service.history(talk.id)
    assert [turn["content"] for turn in history] == ["первый", "второй"]


async def test_content_blocks_survive_the_round_trip(session: AsyncSession) -> None:
    """Tool blocks have to come back byte-identical or the next request is
    rejected."""
    user_id = await _user_id(session)
    service = ConversationService(session)
    talk = await service.active(user_id)

    await service.append(talk.id, _tool_call())

    history = await service.history(talk.id)
    assert history[0]["content"][0]["type"] == "tool_use"
    assert history[1]["content"][0]["tool_use_id"] == "tu_1"


async def test_long_conversations_are_trimmed(session: AsyncSession) -> None:
    user_id = await _user_id(session)
    service = ConversationService(session)
    talk = await service.active(user_id)

    await service.append(talk.id, [_question(f"вопрос {i}") for i in range(MAX_TURNS * 2)])

    assert len(await service.history(talk.id)) <= MAX_TURNS


async def test_trimming_never_leaves_a_tool_use_without_its_result(
    session: AsyncSession,
) -> None:
    """The API rejects a history that opens on a dangling tool_use, so the
    cut has to land on a real question."""
    user_id = await _user_id(session)
    service = ConversationService(session)
    talk = await service.active(user_id)

    for index in range(MAX_TURNS):
        await service.append(talk.id, [_question(f"вопрос {index}"), *_tool_call()])

    history = await service.history(talk.id)

    first = history[0]
    assert first["role"] == "user"
    assert isinstance(first["content"], str), "история начинается с результата инструмента"


async def test_old_tool_results_lose_their_payload(session: AsyncSession) -> None:
    """Raw tool JSON is the bulkiest thing in a conversation and the first
    thing worth dropping: the numbers are already in the answer below it."""
    user_id = await _user_id(session)
    service = ConversationService(session)
    talk = await service.active(user_id)

    for index in range(6):
        await service.append(talk.id, [_question(f"вопрос {index}"), *_tool_call()])

    history = await service.history(talk.id)
    payloads = [
        block["content"]
        for turn in history
        if isinstance(turn["content"], list)
        for block in turn["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]

    assert payloads, "в истории нет результатов инструментов — тест бесполезен"
    assert any("опущены" in text for text in payloads), "старые результаты не урезаны"


async def test_recent_tool_results_are_kept_intact(session: AsyncSession) -> None:
    """The model still needs the numbers it is answering about right now."""
    user_id = await _user_id(session)
    service = ConversationService(session)
    talk = await service.active(user_id)

    await service.append(talk.id, [_question("вопрос"), *_tool_call()])

    history = await service.history(talk.id)
    last = history[-1]["content"][0]
    assert last["content"] == "{}", "свежий результат урезали"


async def test_elision_never_drops_a_tool_result_block(session: AsyncSession) -> None:
    """A tool_use whose result vanished makes the whole request invalid."""
    user_id = await _user_id(session)
    service = ConversationService(session)
    talk = await service.active(user_id)

    for index in range(6):
        await service.append(talk.id, [_question(f"вопрос {index}"), *_tool_call()])

    history = await service.history(talk.id)
    uses = sum(
        1
        for turn in history
        if isinstance(turn["content"], list)
        for block in turn["content"]
        if isinstance(block, dict) and block.get("type") == "tool_use"
    )
    results = sum(
        1
        for turn in history
        if isinstance(turn["content"], list)
        for block in turn["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    )

    assert uses == results, f"{uses} вызовов против {results} результатов"

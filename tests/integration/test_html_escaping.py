"""Text someone typed reaches Telegram escaped.

The bot sends HTML. Before this, a "<" in an exercise name, a search query
or a stranger's display name went out raw: Telegram refused the message
with a 400, the update rolled back, and the user saw nothing at all. The
recording session does not parse HTML, so these tests check the text the
bot would have sent instead.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.config import Settings
from gym_assistant.domain.models import Equipment, ExerciseType, MuscleGroup
from gym_assistant.domain.services import ExerciseService, ProfileService
from tests.integration.bot_harness import TELEGRAM_USER_ID, BotHarness, build_harness

NAME = "Жим <узкий> & хват"


def _settings() -> Settings:
    return Settings(bot_token="42:test-token-not-real")  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    return build_harness(session, _settings())


@pytest_asyncio.fixture
async def admin_bot(session: AsyncSession) -> BotHarness:
    return build_harness(session, _settings(), admin=True)


async def test_a_search_query_with_markup_is_echoed_escaped(bot: BotHarness) -> None:
    await bot.send("/exercises <узкий>")

    reply = bot.session.last_text
    assert "&lt;узкий&gt;" in reply
    assert "<узкий>" not in reply


async def test_an_own_exercise_with_markup_in_its_name_opens_escaped(
    bot: BotHarness, session: AsyncSession
) -> None:
    user = await ProfileService(session).get_or_create_user(TELEGRAM_USER_ID)
    group = await session.scalar(select(MuscleGroup).limit(1))
    assert group is not None
    await ExerciseService(session).create_own(
        user.id,
        name=NAME,
        primary_muscle_group_id=group.id,
        equipment=Equipment.BARBELL,
        exercise_type=ExerciseType.WEIGHT_REPS,
    )

    await bot.send("/exercises узкий")
    await bot.tap_button("узкий")

    card = bot.session.last_text
    assert "Жим &lt;узкий&gt; &amp; хват" in card
    assert "<узкий>" not in card


async def test_a_strangers_display_name_cannot_inject_markup_into_users(
    admin_bot: BotHarness, session: AsyncSession
) -> None:
    await ProfileService(session).get_or_create_user(123_456, first_name='<a href="x">тык</a>')

    await admin_bot.send("/users")

    listing = admin_bot.session.last_text
    assert "<a href" not in listing
    assert "&lt;a href" in listing

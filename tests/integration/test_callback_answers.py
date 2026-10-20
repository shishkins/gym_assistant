"""Every button press is answered once, and only for what is the user's.

Found by the review: the pounds toggle answered its press twice, and so did
"favourite" on an exercise that had gone. Telegram rejects the second answer,
so in production the toast and the redrawn panel never arrived.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.keyboards import ExFavCB, ExUnhideCB
from gym_assistant.config import Settings
from gym_assistant.domain.models import (
    Equipment,
    ExerciseType,
    MuscleGroup,
    UserExercisePref,
)
from gym_assistant.domain.services import ExerciseService, ProfileService
from tests.integration.bot_harness import BotHarness, build_harness


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    return build_harness(session, Settings(bot_token="42:test-token-not-real"))  # type: ignore[call-arg]


async def test_the_pounds_toggle_is_answered_once(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    bot.session.clear()

    await bot.tap_button("Ввод в lbs")

    assert bot.session.callback_answers == 1


async def _strangers_exercise(session: AsyncSession) -> int:
    stranger = await ProfileService(session).get_or_create_user(424_242)
    group = await session.scalar(select(MuscleGroup).limit(1))
    assert group is not None
    created = await ExerciseService(session).create_own(
        stranger.id,
        name="Чужое секретное",
        primary_muscle_group_id=group.id,
        equipment=Equipment.BARBELL,
        exercise_type=ExerciseType.WEIGHT_REPS,
    )
    return created.id


@pytest.mark.parametrize("button", [ExFavCB, ExUnhideCB])
async def test_a_forged_id_of_someone_elses_exercise_writes_nothing(
    bot: BotHarness, session: AsyncSession, button: type[ExFavCB] | type[ExUnhideCB]
) -> None:
    theirs = await _strangers_exercise(session)
    before = await session.scalar(select(func.count()).select_from(UserExercisePref))

    await bot.tap(button(exercise_id=theirs).pack())

    after = await session.scalar(select(func.count()).select_from(UserExercisePref))
    assert after == before
    assert bot.session.callback_answers == 1

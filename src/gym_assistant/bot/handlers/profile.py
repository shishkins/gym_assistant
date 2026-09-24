"""Viewing and editing the profile card."""

from __future__ import annotations

from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.analytics.metrics import personal_records
from gym_assistant.bot.keyboards import (
    CHOICE_ENUMS,
    ChoiceCB,
    EditCB,
    cancel_keyboard,
    experience_keyboard,
    goal_keyboard,
    other_units,
    profile_keyboard,
    sex_keyboard,
)
from gym_assistant.bot.states import ProfileEdit, WeightEntry
from gym_assistant.bot.texts import render, ru
from gym_assistant.domain.models import ExperienceLevel, Goal, Sex, User
from gym_assistant.domain.parsing import (
    ValueParseError,
    parse_birth_date,
    parse_height,
)
from gym_assistant.domain.repositories import StatsRepository
from gym_assistant.domain.services import ProfileService
from gym_assistant.domain.units import label as unit_label

router = Router(name="profile")

# Fields answered by tapping a button rather than typing.
CHOICE_KEYBOARDS = {
    "sex": sex_keyboard,
    "goal": goal_keyboard,
    "experience_level": experience_keyboard,
}


# Enough to answer "am I getting stronger" at a glance; the rest is /stats.
PROFILE_RECORD_COUNT = 3


async def show_card(message: Message, session: AsyncSession, user: User) -> None:
    units = user.unit_system
    summary = await ProfileService(session).get_summary(user.id, today=date.today())
    text = render.render_profile(summary, units)

    # Requested during the iteration 3 review: the maxima belong on the card,
    # not only behind a report.
    sets = await StatsRepository(session).sets_with_exercises(user.id)
    records = personal_records(sets)[:PROFILE_RECORD_COUNT]
    if records:
        text += ru.PROFILE_RECORDS.format(
            records="\n".join(
                ru.PROFILE_RECORD_LINE.format(
                    name=record.exercise_name,
                    weight=(
                        render.format_weight(record.best_weight, units)
                        if record.best_weight
                        else "—"
                    ),
                    reps=record.best_weight_reps or "—",
                )
                for record in records
            )
        )

    await message.answer(text, reply_markup=profile_keyboard(units))


@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession, user: User) -> None:
    await show_card(message, session, user)


@router.callback_query(EditCB.filter())
async def edit_requested(
    callback: CallbackQuery,
    callback_data: EditCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    field = callback_data.field
    message = callback.message
    await callback.answer()
    if not isinstance(message, Message):
        return

    if field == "units":
        await _switch_units(message, session, user)
        return

    if field == "weight":
        await state.set_state(WeightEntry.value)
        await message.answer(
            render.weight_prompt(user.unit_system),
            reply_markup=cancel_keyboard("weight").as_markup(),
        )
        return

    if field in CHOICE_KEYBOARDS:
        # No skip button here: the user opened this on purpose, and /cancel
        # is always available if they change their mind.
        await message.answer(
            ru.PROFILE_FIELD_PROMPTS[field],
            reply_markup=CHOICE_KEYBOARDS[field](skip=False),
        )
        return

    await state.set_state(ProfileEdit.value)
    await state.update_data(field=field)
    await message.answer(
        ru.PROFILE_FIELD_PROMPTS[field],
        reply_markup=cancel_keyboard("profile_edit").as_markup(),
    )


async def _switch_units(message: Message, session: AsyncSession, user: User) -> None:
    """Flips the display system and redraws the card in it.

    Nothing in the history is touched - the rows were kilograms before the tap
    and are kilograms after it. What changes is the two borders: what a typed
    number means, and what a stored one looks like. Saying so in the
    confirmation is the point, because "переключил" next to every past number
    suddenly reading 181 instead of 82 looks like data loss.
    """
    target = other_units(user.unit_system)
    await ProfileService(session).set_units(user.id, target)
    await message.answer(ru.UNITS_SWITCHED.format(unit=unit_label(target)))
    await show_card(message, session, user)


@router.callback_query(ChoiceCB.filter())
async def choice_applied(
    callback: CallbackQuery,
    callback_data: ChoiceCB,
    session: AsyncSession,
    user: User,
) -> None:
    """Handles button answers outside onboarding.

    The onboarding router is registered first and matches only while an
    Onboarding state is set, so anything reaching here is a profile edit.
    """
    field = callback_data.field
    value = CHOICE_ENUMS[field](callback_data.value)
    service = ProfileService(session)

    if isinstance(value, Sex):
        await service.update_profile(user.id, sex=value)
    elif isinstance(value, Goal):
        await service.update_profile(user.id, goal=value)
    else:
        assert isinstance(value, ExperienceLevel)
        await service.update_profile(user.id, experience_level=value)

    await callback.answer(ru.PROFILE_UPDATED)
    message = callback.message
    if isinstance(message, Message):
        await message.delete()
        await show_card(message, session, user)


@router.message(ProfileEdit.value)
async def value_entered(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    data = await state.get_data()
    field = data.get("field")

    if not message.text or field is None:
        await message.answer(ru.UNEXPECTED_ERROR)
        await state.clear()
        return

    service = ProfileService(session)

    if field == "birth_date":
        try:
            await service.update_profile(
                user.id, birth_date=parse_birth_date(message.text, today=date.today())
            )
        except ValueParseError as exc:
            await message.answer(
                ru.ERROR_DATE_FORMAT if exc.reason == "format" else ru.ERROR_DATE_RANGE
            )
            return
    elif field == "height_cm":
        try:
            await service.update_profile(user.id, height_cm=parse_height(message.text))
        except ValueParseError as exc:
            await message.answer(
                ru.ERROR_HEIGHT_FORMAT if exc.reason == "format" else ru.ERROR_HEIGHT_RANGE
            )
            return
    else:
        await message.answer(ru.UNEXPECTED_ERROR)
        await state.clear()
        return

    await state.clear()
    await message.answer(ru.PROFILE_UPDATED)
    await show_card(message, session, user)

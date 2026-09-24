"""First-run wizard.

The steps are a table rather than five near-identical handler pairs, so
reordering or adding a question is a one-line change and the "skip" path
cannot drift out of sync with the "answer" path.
"""

from __future__ import annotations

from datetime import date

import structlog
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.keyboards import (
    CHOICE_ENUMS,
    ChoiceCB,
    SkipCB,
    goal_keyboard,
    sex_keyboard,
    skip_keyboard,
)
from gym_assistant.bot.states import Onboarding
from gym_assistant.bot.texts import render, ru
from gym_assistant.domain.models import Goal, Sex, User
from gym_assistant.domain.parsing import (
    ValueParseError,
    parse_birth_date,
    parse_height,
    parse_weight,
)
from gym_assistant.domain.services import MeasurementService, ProfileService

log = structlog.get_logger(__name__)
router = Router(name="onboarding")

STEPS: tuple[str, ...] = ("sex", "birth_date", "height", "goal", "weight")


def _next_step(current: str) -> str | None:
    index = STEPS.index(current) + 1
    return STEPS[index] if index < len(STEPS) else None


async def ask(step: str, message: Message, state: FSMContext) -> None:
    """Poses the question for ``step`` and parks the FSM there."""
    await state.set_state(getattr(Onboarding, step))

    match step:
        case "sex":
            await message.answer(ru.ONBOARDING_SEX, reply_markup=sex_keyboard())
        case "birth_date":
            await message.answer(ru.ONBOARDING_BIRTH_DATE, reply_markup=skip_keyboard("birth_date"))
        case "height":
            await message.answer(ru.ONBOARDING_HEIGHT, reply_markup=skip_keyboard("height"))
        case "goal":
            await message.answer(ru.ONBOARDING_GOAL, reply_markup=goal_keyboard())
        case "weight":
            await message.answer(ru.ONBOARDING_WEIGHT, reply_markup=skip_keyboard("weight"))


async def start(message: Message, state: FSMContext) -> None:
    await message.answer(ru.ONBOARDING_INTRO)
    await ask(STEPS[0], message, state)


async def _advance(
    current: str, message: Message, state: FSMContext, *, session: AsyncSession, user: User
) -> None:
    following = _next_step(current)
    if following is not None:
        await ask(following, message, state)
        return

    await state.clear()
    summary = await ProfileService(session).get_summary(user.id, today=date.today())
    if summary.is_empty:
        await message.answer(ru.ONBOARDING_DONE_EMPTY)
    else:
        await message.answer(ru.ONBOARDING_DONE.format(summary=render.render_profile(summary)))


async def _strip_keyboard(callback: CallbackQuery, chosen: str | None) -> Message | None:
    """Replaces the prompt with the answer, so the chat reads as a transcript."""
    message = callback.message
    if not isinstance(message, Message):
        return None
    try:
        text = message.html_text if message.text else ""
        suffix = f"\n\n<b>{chosen}</b>" if chosen else f"\n\n<i>{ru.BTN_SKIP.lower()}</i>"
        await message.edit_text(text + suffix, reply_markup=None)
    except Exception:
        # Editing is cosmetic: a stale message must not break the wizard.
        log.debug("prompt_edit_failed")
    return message


# --- Choice steps (sex, goal) --------------------------------------------


@router.callback_query(Onboarding.sex, ChoiceCB.filter(F.field == "sex"))
@router.callback_query(Onboarding.goal, ChoiceCB.filter(F.field == "goal"))
async def choice_selected(
    callback: CallbackQuery,
    callback_data: ChoiceCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    field = callback_data.field
    enum = CHOICE_ENUMS[field]
    value = enum(callback_data.value)

    if isinstance(value, Sex):
        await ProfileService(session).update_profile(user.id, sex=value)
        label = ru.SEX_LABELS[value]
    else:
        assert isinstance(value, Goal)
        await ProfileService(session).update_profile(user.id, goal=value)
        label = ru.GOAL_LABELS[value]

    await callback.answer()
    message = await _strip_keyboard(callback, label)
    if message is not None:
        await _advance(field, message, state, session=session, user=user)


# --- Skipping -------------------------------------------------------------


@router.callback_query(Onboarding.sex, SkipCB.filter())
@router.callback_query(Onboarding.birth_date, SkipCB.filter())
@router.callback_query(Onboarding.height, SkipCB.filter())
@router.callback_query(Onboarding.goal, SkipCB.filter())
@router.callback_query(Onboarding.weight, SkipCB.filter())
async def step_skipped(
    callback: CallbackQuery,
    callback_data: SkipCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    step = callback_data.field
    await callback.answer()
    message = await _strip_keyboard(callback, None)
    if message is not None:
        await _advance(step, message, state, session=session, user=user)


# --- Typed steps ----------------------------------------------------------


@router.message(StateFilter(Onboarding), F.text.startswith("/"))
async def command_during_onboarding(message: Message) -> None:
    """A command mid-wizard would otherwise be parsed as an answer.

    Registered before the typed steps, so "/profile" never ends up being
    validated as a date. /cancel still works: the common router sees it first.
    """
    await message.answer(ru.ONBOARDING_BUSY)


@router.message(Onboarding.birth_date)
async def birth_date_entered(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    if not message.text:
        await message.answer(ru.ERROR_DATE_FORMAT)
        return
    try:
        value = parse_birth_date(message.text, today=date.today())
    except ValueParseError as exc:
        await message.answer(
            ru.ERROR_DATE_FORMAT if exc.reason == "format" else ru.ERROR_DATE_RANGE
        )
        return

    await ProfileService(session).update_profile(user.id, birth_date=value)
    await _advance("birth_date", message, state, session=session, user=user)


@router.message(Onboarding.height)
async def height_entered(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    if not message.text:
        await message.answer(ru.ERROR_HEIGHT_FORMAT)
        return
    try:
        value = parse_height(message.text)
    except ValueParseError as exc:
        await message.answer(
            ru.ERROR_HEIGHT_FORMAT if exc.reason == "format" else ru.ERROR_HEIGHT_RANGE
        )
        return

    await ProfileService(session).update_profile(user.id, height_cm=value)
    await _advance("height", message, state, session=session, user=user)


@router.message(Onboarding.weight)
async def weight_entered(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    if not message.text:
        await message.answer(ru.ERROR_WEIGHT_FORMAT)
        return
    try:
        value = parse_weight(message.text)
    except ValueParseError as exc:
        await message.answer(
            ru.ERROR_WEIGHT_FORMAT if exc.reason == "format" else ru.ERROR_WEIGHT_RANGE
        )
        return

    await MeasurementService(session).record(user.id, weight_kg=value)
    await _advance("weight", message, state, session=session, user=user)

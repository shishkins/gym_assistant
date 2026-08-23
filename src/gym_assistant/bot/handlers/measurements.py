"""Body weight and progress photos."""

from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.media_group import MediaGroupBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.states import WeightEntry
from gym_assistant.bot.texts import render, ru
from gym_assistant.domain.models import User
from gym_assistant.domain.parsing import ValueParseError, parse_weight
from gym_assistant.domain.services import MeasurementService

router = Router(name="measurements")

PHOTO_PAGE_SIZE = 10


async def _save_weight(message: Message, session: AsyncSession, user: User, value: Decimal) -> None:
    service = MeasurementService(session)
    await service.record(user.id, weight_kg=value)

    delta = await service.weight_change(user.id, days=30)
    shown = render.format_decimal(value)

    if delta is None:
        await message.answer(ru.WEIGHT_SAVED.format(weight=shown))
        return

    if delta > 0:
        wording = ru.WEIGHT_DELTA_UP.format(value=render.format_decimal(delta))
    elif delta < 0:
        wording = ru.WEIGHT_DELTA_DOWN.format(value=render.format_decimal(-delta))
    else:
        wording = ru.WEIGHT_DELTA_SAME

    await message.answer(ru.WEIGHT_SAVED_WITH_DELTA.format(weight=shown, delta=wording))


@router.message(Command("weight"))
async def cmd_weight(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """``/weight 82.5`` records straight away; bare ``/weight`` asks."""
    if command.args:
        try:
            value = parse_weight(command.args)
        except ValueParseError as exc:
            await message.answer(
                ru.ERROR_WEIGHT_FORMAT if exc.reason == "format" else ru.ERROR_WEIGHT_RANGE
            )
            return
        await _save_weight(message, session, user, value)
        return

    service = MeasurementService(session)
    last = await service.latest_weigh_in(user.id)
    await state.set_state(WeightEntry.value)

    if last is not None and last.weight_kg is not None:
        await message.answer(
            ru.WEIGHT_PROMPT_WITH_LAST.format(
                last=render.format_decimal(last.weight_kg),
                when=render.format_when(last.measured_at),
            )
        )
    else:
        await message.answer(ru.WEIGHT_PROMPT)


@router.message(WeightEntry.value)
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

    await state.clear()
    await _save_weight(message, session, user, value)


@router.message(F.photo)
async def photo_received(message: Message, session: AsyncSession, user: User) -> None:
    """Any photo becomes a progress shot.

    We store Telegram's file_id rather than the bytes: Telegram keeps the
    file, and we keep a handle to it.
    """
    assert message.photo is not None
    file_id = message.photo[-1].file_id  # last entry is the largest rendition

    weight: Decimal | None = None
    if message.caption:
        try:
            weight = parse_weight(message.caption)
        except ValueParseError:
            weight = None  # a caption is free-form; a non-number is fine

    await MeasurementService(session).record(
        user.id,
        photo_file_id=file_id,
        weight_kg=weight,
        note=message.caption if weight is None else None,
    )

    if weight is not None:
        await message.answer(
            ru.PHOTO_SAVED_WITH_WEIGHT.format(weight=render.format_decimal(weight))
        )
    else:
        await message.answer(ru.PHOTO_SAVED)


@router.message(Command("photos"))
async def cmd_photos(message: Message, session: AsyncSession, user: User) -> None:
    service = MeasurementService(session)
    photos = await service.photos(user.id, limit=PHOTO_PAGE_SIZE)

    if not photos:
        await message.answer(ru.PHOTOS_EMPTY)
        return

    total = await service.count_photos(user.id)
    await message.answer(ru.PHOTOS_HEADER.format(shown=len(photos), total=total))

    # Oldest first: a progress album only reads as progress in that order.
    album = MediaGroupBuilder()
    for measurement in reversed(photos):
        assert measurement.photo_file_id is not None
        when = render.format_when(measurement.measured_at)
        caption = (
            ru.PHOTO_CAPTION_WITH_WEIGHT.format(
                date=when, weight=render.format_decimal(measurement.weight_kg)
            )
            if measurement.weight_kg is not None
            else ru.PHOTO_CAPTION.format(date=when)
        )
        album.add_photo(media=measurement.photo_file_id, caption=caption)

    # aiogram gap: MediaGroupBuilder.build() returns a narrower union than
    # answer_media_group accepts, and list is invariant. warn_unused_ignores
    # will flag this the moment upstream aligns the two.
    await message.answer_media_group(album.build())  # type: ignore[arg-type]

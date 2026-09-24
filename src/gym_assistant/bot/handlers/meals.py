"""The food diary: a photo becomes a meal, once the person agrees.

Three things shape this module, and all three came out of measuring the model
on nine photos of what this user actually eats rather than from the spec.

**Nothing is written until the tap.** The breakdown lives in the dialogue
state. The model is right about what is on the plate far more often than it is
right about how much of it there is, so a card that writes itself would fill
the diary with portions nobody agreed to - and every later number, the daily
total and the TDEE above it, is built on those.

**Correcting has to be as cheap as agreeing.** All the error is in the grams,
so the portion multipliers sit on the first row, above everything else.

**Clarifying is the person's choice, not the bot's demand.** The model reports
where it had no reference to judge size by, and the card can say so, but it
never blocks. A diary that argues before it records is a diary nobody fills in
for a second week.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.ai.vision import FoodVision, Seen, SeenItem, VisionUnavailableError
from gym_assistant.bot.filters import RequireRole
from gym_assistant.bot.keyboards import (
    MealCB,
    MealScaleCB,
    MealUndoCB,
    meal_card_keyboard,
    meal_saved_keyboard,
)
from gym_assistant.bot.states import MealFlow
from gym_assistant.bot.texts import render, ru
from gym_assistant.config import Settings
from gym_assistant.domain.models import GramsSource, Role, User
from gym_assistant.domain.services import Access, MealService

log = structlog.get_logger(__name__)
router = Router(name="meals")
# Behind the same gate as the assistant, and for the same reason: every photo
# sent here costs money at the API. Without this, anyone who finds the bot can
# spend the owner's budget a plate at a time.
router.message.filter(RequireRole(Role.SUBSCRIPTION_USER))

# Above this the portion is a guess dressed as a measurement. Measured at
# 32-46% on real photos, so the line sits above the normal band and marks only
# the rows where the model itself had nothing to judge size by.
UNSURE_BAND_PCT = Decimal(60)

# A photo Telegram has already compressed. Larger costs more tokens for detail
# the model does not use.
MAX_PHOTO_BYTES = 5 * 1024 * 1024


def build_vision(settings: Settings) -> FoodVision:
    """A seam, so tests drive the whole flow without calling the API."""
    return FoodVision(settings)


# --- from photo to card ---------------------------------------------------


async def handle_food_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    settings: Settings,
    image: bytes,
    file_id: str,
    access: Access | None = None,
) -> bool:
    """Reads the photo. Returns False if it was not food after all.

    The caller decides what to do with a photo that is not food - this module
    does not reach into the progress album.

    The subscription check lives here rather than on the router, and a test
    is why: the entry point for a photo is the measurements handler, which
    calls straight into this function and never passes the router's filter.
    A gate on the router looked right and guarded nothing.
    """
    if access is None or not access.allows(Role.SUBSCRIPTION_USER):
        return False

    vision = build_vision(settings)
    if not vision.available:
        return False

    hint = await _recent_hint(session, user)
    notice = await message.answer(ru.MEAL_LOOKING)
    try:
        seen = await vision.look(image, hint=hint)
    except VisionUnavailableError as exc:
        log.warning("meal_vision_failed", reason=str(exc))
        await notice.edit_text(ru.MEAL_FAILED)
        return True

    if seen.kind != "food":
        await notice.delete()
        return False

    if not seen.items:
        await notice.edit_text(ru.MEAL_EMPTY)
        return True

    await notice.delete()
    await _show(message, state, seen, file_id)
    return True


async def _recent_hint(session: AsyncSession, user: User) -> list[str]:
    """What this person has eaten lately.

    Fed to the model so that the same food keeps the same name. Without it the
    croissant is a different row every morning and nothing ever accumulates.
    """
    return await MealService(session).recent_names(user.id)


async def _show(
    message: Message, state: FSMContext, seen: Seen, file_id: str, edit: Message | None = None
) -> None:
    await state.set_state(MealFlow.reviewing)
    await state.update_data(
        items=[_as_data(item) for item in seen.items],
        photo_file_id=file_id,
        model=seen.model,
        prompt_version=seen.prompt_version,
        question=seen.question,
    )

    text = _card(seen.items, seen.question)
    if edit is not None:
        await edit.edit_text(text, reply_markup=meal_card_keyboard())
        return
    await message.answer(text, reply_markup=meal_card_keyboard())


def _card(items: Sequence[SeenItem], question: str | None) -> str:
    lines = []
    for item in items:
        template = (
            ru.MEAL_ITEM_UNSURE
            if item.needs_scale or item.band_width_pct > UNSURE_BAND_PCT
            else ru.MEAL_ITEM_LINE
        )
        lines.append(
            template.format(
                name=item.name,
                grams=render.format_decimal(item.grams.quantize(Decimal(1))),
                kcal=render.format_decimal(item.kcal.quantize(Decimal(1))),
            )
        )

    text = ru.MEAL_CARD.format(
        total=render.format_decimal(_total(items, "kcal").quantize(Decimal(1))),
        protein=render.format_decimal(_total(items, "protein_g").quantize(Decimal(1))),
        fat=render.format_decimal(_total(items, "fat_g").quantize(Decimal(1))),
        carb=render.format_decimal(_total(items, "carb_g").quantize(Decimal(1))),
        items="\n".join(lines),
    )
    if question:
        text += ru.MEAL_QUESTION.format(question=question)
    return text


def _total(items: Sequence[SeenItem], field: str) -> Decimal:
    return sum((getattr(item, field) for item in items), Decimal(0))


# --- the card's buttons ---------------------------------------------------


@router.callback_query(MealScaleCB.filter())
async def scale_portions(
    callback: CallbackQuery, callback_data: MealScaleCB, state: FSMContext
) -> None:
    """Multiplies every portion at once.

    One factor for the whole plate rather than a row at a time: when a portion
    is misjudged it is usually the whole serving, and per-item editing is a
    screen nobody opens between bites.
    """
    data = await state.get_data()
    items = data.get("items")
    message = callback.message
    if not items or not isinstance(message, Message):
        await callback.answer(ru.MEAL_EXPIRED, show_alert=True)
        return

    factor = Decimal(callback_data.factor)
    scaled = [
        {**entry, "grams": str(Decimal(str(entry["grams"])) * factor), "grams_source": "user"}
        for entry in items
    ]
    await state.update_data(items=scaled)
    await callback.answer()

    rebuilt = [_from_data(entry) for entry in scaled]
    await message.edit_text(_card(rebuilt, data.get("question")), reply_markup=meal_card_keyboard())


@router.callback_query(MealCB.filter(F.action == "save"))
async def save_meal(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    data = await state.get_data()
    items = data.get("items")
    message = callback.message
    if not items or not isinstance(message, Message):
        await callback.answer(ru.MEAL_EXPIRED, show_alert=True)
        return

    service = MealService(session)
    meal = await service.record(
        user.id,
        items=items,
        photo_file_id=data.get("photo_file_id"),
        model=data.get("model"),
        prompt_version=data.get("prompt_version"),
    )
    await state.clear()
    await callback.answer()

    today = await service.day_totals(user.id, days=1)
    eaten = today[0].kcal if today else meal.kcal
    await message.edit_text(
        ru.MEAL_SAVED.format(
            total=render.format_decimal(meal.kcal.quantize(Decimal(1))),
            today=render.format_decimal(eaten.quantize(Decimal(1))),
        ),
        reply_markup=meal_saved_keyboard(meal.id),
    )
    log.info("meal_saved", user_id=user.id, kcal=str(meal.kcal), items=len(items))


@router.callback_query(MealCB.filter(F.action == "discard"))
async def discard_meal(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    message = callback.message
    if isinstance(message, Message):
        await message.edit_text(ru.MEAL_DISCARDED)


@router.callback_query(MealCB.filter(F.action == "clarify"))
async def ask_for_clarification(callback: CallbackQuery, state: FSMContext) -> None:
    """Offers the ways to help, and waits. None of them is required."""
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return
    await state.set_state(MealFlow.clarifying)
    await message.answer(ru.MEAL_CLARIFY)


@router.callback_query(MealUndoCB.filter())
async def undo_meal(
    callback: CallbackQuery, callback_data: MealUndoCB, session: AsyncSession, user: User
) -> None:
    removed = await MealService(session).delete(user.id, callback_data.meal_id)
    await callback.answer(ru.MEAL_UNDONE if removed else ru.MEAL_NOTHING_TO_UNDO)
    message = callback.message
    if removed and isinstance(message, Message):
        await message.edit_text(ru.MEAL_UNDONE)


# --- the clarification itself ---------------------------------------------


@router.message(MealFlow.clarifying, F.text)
async def clarify_with_text(
    message: Message, state: FSMContext, session: AsyncSession, user: User, settings: Settings
) -> None:
    """A written hint: "тарелка 30 см", "порция была большая", "это бургер"."""
    assert message.text is not None
    await _rethink(message, state, session, user, settings, hint_text=message.text)


@router.message(MealFlow.clarifying, F.photo)
async def clarify_with_photo(
    message: Message, state: FSMContext, session: AsyncSession, user: User, settings: Settings
) -> None:
    """A second photo: a menu, a delivery app, or the plate next to a fork."""
    assert message.photo is not None
    extra = await _download(message, message.photo[-1].file_id)
    await _rethink(
        message, state, session, user, settings, hint_text=message.caption, extra_image=extra
    )


async def _rethink(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    hint_text: str | None = None,
    extra_image: bytes | None = None,
) -> None:
    data = await state.get_data()
    file_id = data.get("photo_file_id")
    if not file_id:
        await state.clear()
        await message.answer(ru.MEAL_EXPIRED)
        return

    vision = build_vision(settings)
    notice = await message.answer(ru.MEAL_RETHINKING)
    try:
        image = await _download(message, file_id)
        seen = await vision.look(
            image,
            hint=await _recent_hint(session, user),
            note=hint_text,
            extra=extra_image,
            previous=[_from_data(entry) for entry in data.get("items", [])],
        )
    except VisionUnavailableError as exc:
        log.warning("meal_rethink_failed", reason=str(exc))
        await notice.edit_text(ru.MEAL_FAILED)
        return

    if not seen.items:
        await notice.edit_text(ru.MEAL_EMPTY)
        return

    await notice.delete()
    await _show(message, state, seen, str(file_id))


async def _download(message: Message, file_id: str) -> bytes:
    """Telegram keeps the file; we borrow the bytes and do not store them."""
    bot = message.bot
    assert bot is not None
    buffer = await bot.download(file_id)
    assert buffer is not None
    return buffer.read()


# --- reading the day back -------------------------------------------------


@router.message(Command("food"))
async def cmd_food(message: Message, session: AsyncSession, user: User) -> None:
    service = MealService(session)
    totals = await service.day_totals(user.id, days=1)
    if not totals:
        await message.answer(ru.MEAL_DAY_EMPTY)
        return

    day = totals[0]
    await message.answer(
        ru.MEAL_DAY.format(
            total=render.format_decimal(day.kcal.quantize(Decimal(1))),
            meals=_meals_word(day.meals),
            protein=render.format_decimal(day.protein_g.quantize(Decimal(1))),
            fat=render.format_decimal(day.fat_g.quantize(Decimal(1))),
            carb=render.format_decimal(day.carb_g.quantize(Decimal(1))),
            lines="",
        )
    )


def _meals_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} приём"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return f"{count} приёма"
    return f"{count} приёмов"


# --- the breakdown as it travels through the dialogue state ---------------


def _as_data(item: SeenItem) -> dict[str, Any]:
    """Only what a stored row needs. The state is JSON in Redis, so Decimals
    travel as strings rather than as something json cannot carry."""
    return {
        "name": item.name,
        "grams": str(item.grams),
        "grams_low": str(item.grams_low),
        "grams_high": str(item.grams_high),
        "kcal_100g": str(item.kcal_100g),
        "protein_100g": str(item.protein_100g),
        "fat_100g": str(item.fat_100g),
        "carb_100g": str(item.carb_100g),
        "basis": item.basis,
        "needs_scale": item.needs_scale,
        "grams_source": GramsSource.MODEL.value,
    }


def _from_data(entry: dict[str, Any]) -> SeenItem:
    return SeenItem(
        name=entry["name"],
        grams=Decimal(entry["grams"]),
        grams_low=Decimal(entry["grams_low"]),
        grams_high=Decimal(entry["grams_high"]),
        kcal_100g=Decimal(entry["kcal_100g"]),
        protein_100g=Decimal(entry["protein_100g"]),
        fat_100g=Decimal(entry["fat_100g"]),
        carb_100g=Decimal(entry["carb_100g"]),
        basis=entry.get("basis", ""),
        needs_scale=bool(entry.get("needs_scale")),
    )

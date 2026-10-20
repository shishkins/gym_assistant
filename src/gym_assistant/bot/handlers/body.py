"""Body composition from a progress photo, on request only.

Never automatic. A photo is saved as a progress shot and nothing more; the
estimate happens when the person presses the button under it or sends
``/body``. A body-fat number is not something to hand out unasked.

Gated like the assistant, by a filter on the router: it costs money per
use. The button under a photo is only drawn for someone who passes the same
check, and pressing a forged one falls through to the fallback router as an
inert button.
"""

from __future__ import annotations

import structlog
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.ai.body import PROMPT_VERSION, BodyRefusedError, BodyVision
from gym_assistant.ai.client import AiOverloadedError, AiUnavailableError, BudgetExceededError
from gym_assistant.ai.usage import UsageService
from gym_assistant.bot.filters import RequireRole
from gym_assistant.bot.keyboards import BodyCB
from gym_assistant.bot.texts import render, ru
from gym_assistant.config import Settings
from gym_assistant.domain.models import BodyMeasurement, Role, Sex, User
from gym_assistant.domain.services import BodyService, ProfileService

log = structlog.get_logger(__name__)

router = Router(name="body")
router.message.filter(RequireRole(Role.SUBSCRIPTION_USER))
router.callback_query.filter(RequireRole(Role.SUBSCRIPTION_USER))


def build_body_vision(settings: Settings, usage: UsageService) -> BodyVision:
    """A seam, so tests drive the handler without calling the API."""
    return BodyVision(settings, usage)


@router.message(Command("body"))
async def cmd_body(message: Message, session: AsyncSession, user: User, settings: Settings) -> None:
    photo = await BodyService(session).latest_photo(user.id)
    if photo is None:
        await message.answer(ru.BODY_NO_PHOTO)
        return
    await _estimate(message, session, user, settings, photo)


@router.callback_query(BodyCB.filter())
async def on_estimate(
    callback: CallbackQuery,
    callback_data: BodyCB,
    session: AsyncSession,
    user: User,
    settings: Settings,
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    photo = await BodyService(session).photo(user.id, callback_data.measurement_id)
    if photo is None:
        await callback.message.answer(ru.BODY_PHOTO_GONE)
        return
    await _estimate(callback.message, session, user, settings, photo)


async def _estimate(
    message: Message,
    session: AsyncSession,
    user: User,
    settings: Settings,
    photo: BodyMeasurement,
) -> None:
    service = BodyService(session)
    vision = build_body_vision(settings, UsageService(session))

    profile = await ProfileService(session).get_profile(user.id)
    sex = Sex(profile.sex) if profile.sex else None
    weigh_in = await service.weigh_in_for(user.id, photo)

    estimate = await service.existing(
        user.id, photo, model=vision.model, prompt_version=PROMPT_VERSION
    )
    unusable = False
    if estimate is None:
        if not vision.available:
            await message.answer(ru.AI_NOT_CONFIGURED)
            return
        if message.bot is None:  # pragma: no cover - a live update always has one
            return

        await message.answer(ru.BODY_LOOKING)
        image = await _download(message.bot, photo)
        try:
            reading = await vision.look(image, user_id=user.id, sex=sex)
        except BudgetExceededError:
            await message.answer(ru.AI_BUDGET_SPENT)
            return
        except BodyRefusedError:
            # Billed all the same; the usage row must outlive this update.
            await session.commit()
            await message.answer(ru.BODY_REFUSED)
            return
        except AiOverloadedError:
            await message.answer(ru.AI_OVERLOADED)
            return
        except AiUnavailableError as exc:
            log.warning("body_unavailable", reason=str(exc))
            await message.answer(ru.AI_UNAVAILABLE)
            return

        if not reading.is_estimate or reading.band is None:
            await session.commit()
            await message.answer(ru.BODY_NOT_A_BODY)
            return

        estimate = await service.record(
            user.id,
            photo,
            band=reading.band,
            weight_kg=weigh_in.weight_kg if weigh_in and weigh_in.fresh else None,
            height_cm=profile.height_cm,
            observations=reading.observations,
            limits=reading.limits,
            model=reading.model,
            prompt_version=reading.prompt_version,
        )
        unusable = not reading.usable
        log.info(
            "body_estimated",
            user_id=user.id,
            bf_likely=str(reading.band.likely),
            width=str(reading.band.width),
            cost_usd=str(reading.cost_usd),
        )
        # Paid for; the estimate must not depend on Telegram accepting the
        # reply, the same rule as the assistant's answers.
        await session.commit()

    previous = await service.previous(
        user.id,
        before=photo.measured_at,
        model=estimate.model,
        prompt_version=estimate.prompt_version,
    )
    await message.answer(
        render.render_body_estimate(
            estimate,
            weigh_in=weigh_in,
            height_cm=profile.height_cm,
            sex=sex,
            previous=previous,
            unusable=unusable,
        )
    )


async def _download(bot: Bot, photo: BodyMeasurement) -> bytes:
    assert photo.photo_file_id is not None
    buffer = await bot.download(photo.photo_file_id)
    assert buffer is not None  # without a destination aiogram returns the buffer
    return buffer.read()

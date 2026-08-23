"""Profile use cases against a real database."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import Goal, Sex
from gym_assistant.domain.services import MeasurementService, ProfileService

TODAY = date(2026, 8, 23)


async def test_get_or_create_user_is_idempotent(session: AsyncSession) -> None:
    service = ProfileService(session)

    first = await service.get_or_create_user(1001, username="anton", first_name="Антон")
    second = await service.get_or_create_user(1001, username="anton", first_name="Антон")

    assert first.id == second.id


async def test_new_user_gets_an_empty_profile_row(session: AsyncSession) -> None:
    """Creating the profile up front means later edits are plain updates."""
    service = ProfileService(session)
    user = await service.get_or_create_user(1002)

    profile = await service.get_profile(user.id)

    assert profile.user_id == user.id
    assert profile.sex is None


async def test_telegram_metadata_is_refreshed(session: AsyncSession) -> None:
    service = ProfileService(session)
    await service.get_or_create_user(1003, username="old", first_name="Старое")

    user = await service.get_or_create_user(1003, username="new", first_name="Новое")

    assert user.username == "new"
    assert user.first_name == "Новое"


async def test_update_profile_leaves_unpassed_fields_alone(session: AsyncSession) -> None:
    """Guards the regression where a later edit silently wipes earlier data."""
    service = ProfileService(session)
    user = await service.get_or_create_user(1004)

    await service.update_profile(user.id, sex=Sex.MALE, height_cm=178)
    await service.update_profile(user.id, goal=Goal.MASS)

    profile = await service.get_profile(user.id)
    assert profile.sex == Sex.MALE.value
    assert profile.height_cm == 178
    assert profile.goal == Goal.MASS.value


async def test_clear_profile_field(session: AsyncSession) -> None:
    service = ProfileService(session)
    user = await service.get_or_create_user(1005)
    await service.update_profile(user.id, height_cm=178)

    await service.clear_profile_field(user.id, "height_cm")

    assert (await service.get_profile(user.id)).height_cm is None


async def test_clear_profile_field_rejects_unknown_name(session: AsyncSession) -> None:
    service = ProfileService(session)
    user = await service.get_or_create_user(1006)

    with pytest.raises(ValueError, match="unknown profile field"):
        await service.clear_profile_field(user.id, "telegram_id")


async def test_summary_is_empty_for_a_fresh_user(session: AsyncSession) -> None:
    service = ProfileService(session)
    user = await service.get_or_create_user(1007)

    summary = await service.get_summary(user.id, today=TODAY)

    assert summary.is_empty
    assert summary.age is None
    assert summary.bmi is None


async def test_summary_computes_age_and_bmi(session: AsyncSession) -> None:
    service = ProfileService(session)
    user = await service.get_or_create_user(1008, first_name="Антон")
    await service.update_profile(
        user.id,
        sex=Sex.MALE,
        birth_date=date(1990, 12, 31),
        height_cm=180,
        goal=Goal.MASS,
    )
    await MeasurementService(session).record(user.id, weight_kg=Decimal("80"))

    summary = await service.get_summary(user.id, today=TODAY)

    assert not summary.is_empty
    assert summary.age == 35
    assert summary.height_cm == 180
    assert summary.weight_kg == Decimal("80.00")
    assert summary.bmi == Decimal("24.7")
    assert summary.bmi_band == "normal"
    assert summary.measurements_count == 1

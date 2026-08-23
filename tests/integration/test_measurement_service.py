"""Body-measurement use cases against a real database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import BodyMeasurement
from gym_assistant.domain.services import (
    EmptyMeasurementError,
    MeasurementService,
    ProfileService,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


async def _user(session: AsyncSession, telegram_id: int) -> int:
    user = await ProfileService(session).get_or_create_user(telegram_id)
    return user.id


async def test_record_weight(session: AsyncSession) -> None:
    user_id = await _user(session, 2001)

    measurement = await MeasurementService(session).record(user_id, weight_kg=Decimal("82.5"))

    assert measurement.id is not None
    assert measurement.weight_kg == Decimal("82.50")


async def test_record_rejects_an_empty_measurement(session: AsyncSession) -> None:
    """Caught in the domain, so callers see a domain error, not an IntegrityError."""
    user_id = await _user(session, 2002)

    with pytest.raises(EmptyMeasurementError):
        await MeasurementService(session).record(user_id, note="просто заметка")


async def test_database_rejects_an_empty_measurement_too(session: AsyncSession) -> None:
    """Belt and braces: the CHECK constraint is the actual guarantee."""
    user_id = await _user(session, 2003)
    session.add(BodyMeasurement(user_id=user_id, measured_at=NOW))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_database_rejects_an_implausible_weight(session: AsyncSession) -> None:
    user_id = await _user(session, 2004)
    session.add(BodyMeasurement(user_id=user_id, measured_at=NOW, weight_kg=Decimal("500")))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_photo_only_entry_does_not_hide_the_last_weigh_in(
    session: AsyncSession,
) -> None:
    """The reason latest_with_weight exists as a separate query."""
    user_id = await _user(session, 2005)
    service = MeasurementService(session)

    await service.record(user_id, weight_kg=Decimal("80"), measured_at=NOW - timedelta(days=2))
    await service.record(user_id, photo_file_id="photo-1", measured_at=NOW)

    assert await service.latest_weight(user_id) == Decimal("80.00")
    latest = await service.latest(user_id)
    assert latest is not None
    assert latest.photo_file_id == "photo-1"


async def test_weight_change_needs_two_points(session: AsyncSession) -> None:
    user_id = await _user(session, 2006)
    service = MeasurementService(session)
    await service.record(user_id, weight_kg=Decimal("80"))

    assert await service.weight_change(user_id) is None


async def test_weight_change_over_the_window(session: AsyncSession) -> None:
    user_id = await _user(session, 2007)
    service = MeasurementService(session)

    await service.record(user_id, weight_kg=Decimal("80"), measured_at=NOW - timedelta(days=20))
    await service.record(user_id, weight_kg=Decimal("82.5"), measured_at=NOW)

    assert await service.weight_change(user_id, days=30) == Decimal("2.50")


async def test_weight_change_falls_back_to_the_oldest_point(session: AsyncSession) -> None:
    """Outside the window we still answer rather than reporting nothing."""
    user_id = await _user(session, 2008)
    service = MeasurementService(session)

    await service.record(user_id, weight_kg=Decimal("90"), measured_at=NOW - timedelta(days=400))
    await service.record(user_id, weight_kg=Decimal("82"), measured_at=NOW)

    assert await service.weight_change(user_id, days=30) == Decimal("-8.00")


async def test_photos_are_newest_first_and_counted(session: AsyncSession) -> None:
    user_id = await _user(session, 2009)
    service = MeasurementService(session)

    await service.record(user_id, photo_file_id="old", measured_at=NOW - timedelta(days=5))
    await service.record(user_id, photo_file_id="new", measured_at=NOW)
    await service.record(user_id, weight_kg=Decimal("80"), measured_at=NOW)

    photos = await service.photos(user_id)

    assert [p.photo_file_id for p in photos] == ["new", "old"]
    assert await service.count_photos(user_id) == 2


async def test_history_is_scoped_to_one_user(session: AsyncSession) -> None:
    """Multi-user isolation is worth asserting, not assuming."""
    mine = await _user(session, 2010)
    theirs = await _user(session, 2011)
    service = MeasurementService(session)

    await service.record(mine, weight_kg=Decimal("80"))
    await service.record(theirs, weight_kg=Decimal("60"))

    assert [m.weight_kg for m in await service.history(mine)] == [Decimal("80.00")]

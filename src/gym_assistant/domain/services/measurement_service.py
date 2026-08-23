"""Body-measurement use cases."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import BodyMeasurement
from gym_assistant.domain.repositories import MeasurementRepository


class EmptyMeasurementError(ValueError):
    """Raised when a measurement would carry no data at all."""


class MeasurementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._measurements = MeasurementRepository(session)

    async def record(
        self,
        user_id: int,
        *,
        weight_kg: Decimal | None = None,
        body_fat_pct: Decimal | None = None,
        chest_cm: Decimal | None = None,
        waist_cm: Decimal | None = None,
        hip_cm: Decimal | None = None,
        biceps_cm: Decimal | None = None,
        thigh_cm: Decimal | None = None,
        photo_file_id: str | None = None,
        note: str | None = None,
        measured_at: datetime | None = None,
    ) -> BodyMeasurement:
        payload = (
            weight_kg,
            body_fat_pct,
            chest_cm,
            waist_cm,
            hip_cm,
            biceps_cm,
            thigh_cm,
            photo_file_id,
        )
        if all(value is None for value in payload):
            # The database rejects this too; failing here gives the caller a
            # domain error instead of an IntegrityError from three layers down.
            raise EmptyMeasurementError("a measurement needs at least one value")

        measurement = BodyMeasurement(
            user_id=user_id,
            measured_at=measured_at or datetime.now(UTC),
            weight_kg=weight_kg,
            body_fat_pct=body_fat_pct,
            chest_cm=chest_cm,
            waist_cm=waist_cm,
            hip_cm=hip_cm,
            biceps_cm=biceps_cm,
            thigh_cm=thigh_cm,
            photo_file_id=photo_file_id,
            note=note,
        )
        return await self._measurements.add(measurement)

    async def attach_photo(self, measurement_id: int, photo_file_id: str) -> BodyMeasurement:
        measurement = await self._measurements.get(measurement_id)
        if measurement is None:
            raise LookupError(f"measurement {measurement_id} does not exist")
        measurement.photo_file_id = photo_file_id
        await self._session.flush()
        return measurement

    async def latest(self, user_id: int) -> BodyMeasurement | None:
        return await self._measurements.latest(user_id)

    async def latest_weigh_in(self, user_id: int) -> BodyMeasurement | None:
        """Last entry that carries a weight, with its timestamp."""
        return await self._measurements.latest_with_weight(user_id)

    async def count_photos(self, user_id: int) -> int:
        return await self._measurements.count_photos(user_id)

    async def latest_weight(self, user_id: int) -> Decimal | None:
        measurement = await self._measurements.latest_with_weight(user_id)
        return measurement.weight_kg if measurement else None

    async def history(
        self,
        user_id: int,
        *,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[BodyMeasurement]:
        return await self._measurements.history(user_id, since=since, limit=limit)

    async def photos(self, user_id: int, *, limit: int = 10) -> list[BodyMeasurement]:
        return await self._measurements.photos(user_id, limit=limit)

    async def weight_change(self, user_id: int, *, days: int = 30) -> Decimal | None:
        """Weight delta over the window, or ``None`` without two data points."""
        history = await self._measurements.history(user_id, limit=500)
        weighed = [m for m in history if m.weight_kg is not None]
        if len(weighed) < 2:
            return None

        newest = weighed[0]
        cutoff = newest.measured_at.timestamp() - days * 86400
        older = [m for m in weighed[1:] if m.measured_at.timestamp() >= cutoff]
        # Fall back to the oldest point we have rather than reporting nothing.
        baseline = older[-1] if older else weighed[-1]

        assert newest.weight_kg is not None and baseline.weight_kg is not None
        return newest.weight_kg - baseline.weight_kg

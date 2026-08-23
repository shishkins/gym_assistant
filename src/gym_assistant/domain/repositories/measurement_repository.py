"""Data access for the body-metrics time series."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import BodyMeasurement


class MeasurementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, measurement: BodyMeasurement) -> BodyMeasurement:
        self._session.add(measurement)
        await self._session.flush()
        return measurement

    async def get(self, measurement_id: int) -> BodyMeasurement | None:
        return await self._session.get(BodyMeasurement, measurement_id)

    async def latest(self, user_id: int) -> BodyMeasurement | None:
        stmt = (
            select(BodyMeasurement)
            .where(BodyMeasurement.user_id == user_id)
            .order_by(BodyMeasurement.measured_at.desc())
            .limit(1)
        )
        # Annotated because AsyncSession.scalar is typed as returning Any.
        measurement: BodyMeasurement | None = await self._session.scalar(stmt)
        return measurement

    async def latest_with_weight(self, user_id: int) -> BodyMeasurement | None:
        """Most recent row that actually carries a weight.

        A photo-only entry must not hide the last real weigh-in.
        """
        stmt = (
            select(BodyMeasurement)
            .where(
                BodyMeasurement.user_id == user_id,
                BodyMeasurement.weight_kg.is_not(None),
            )
            .order_by(BodyMeasurement.measured_at.desc())
            .limit(1)
        )
        # Annotated because AsyncSession.scalar is typed as returning Any.
        measurement: BodyMeasurement | None = await self._session.scalar(stmt)
        return measurement

    async def history(
        self,
        user_id: int,
        *,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[BodyMeasurement]:
        stmt = select(BodyMeasurement).where(BodyMeasurement.user_id == user_id)
        if since is not None:
            stmt = stmt.where(BodyMeasurement.measured_at >= since)
        stmt = stmt.order_by(BodyMeasurement.measured_at.desc()).limit(limit)
        return list(await self._session.scalars(stmt))

    async def photos(self, user_id: int, *, limit: int = 10) -> list[BodyMeasurement]:
        stmt = (
            select(BodyMeasurement)
            .where(
                BodyMeasurement.user_id == user_id,
                BodyMeasurement.photo_file_id.is_not(None),
            )
            .order_by(BodyMeasurement.measured_at.desc())
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def count_photos(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(BodyMeasurement)
            .where(
                BodyMeasurement.user_id == user_id,
                BodyMeasurement.photo_file_id.is_not(None),
            )
        )
        return await self._session.scalar(stmt) or 0

    async def count(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(BodyMeasurement)
            .where(BodyMeasurement.user_id == user_id)
        )
        return await self._session.scalar(stmt) or 0

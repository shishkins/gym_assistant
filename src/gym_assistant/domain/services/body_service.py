"""Body-composition use cases: finding the photo, the weight, the history.

Knows nothing about the model that reads the photo - it stores what it is
handed. The reader lives in :mod:`ai.body`, and the domain does not import
the AI layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.body import Band, weight_is_fresh
from gym_assistant.domain.models import BodyEstimate, BodyMeasurement
from gym_assistant.domain.repositories import BodyEstimateRepository, MeasurementRepository


@dataclass(frozen=True, slots=True)
class WeighIn:
    weight_kg: Decimal
    measured_at: datetime
    fresh: bool


class BodyService:
    def __init__(self, session: AsyncSession) -> None:
        self._measurements = MeasurementRepository(session)
        self._estimates = BodyEstimateRepository(session)

    async def photo(self, user_id: int, measurement_id: int) -> BodyMeasurement | None:
        return await self._measurements.photo_of(user_id, measurement_id)

    async def latest_photo(self, user_id: int) -> BodyMeasurement | None:
        photos = await self._measurements.photos(user_id, limit=1)
        return photos[0] if photos else None

    async def weigh_in_for(self, user_id: int, photo: BodyMeasurement) -> WeighIn | None:
        """The weight that best describes the body in ``photo``.

        A weight sent as the photo's caption is the photo's own and always
        fresh. Otherwise the nearest weigh-in, flagged stale if it is too far
        from the photo to stand for it.
        """
        if photo.weight_kg is not None:
            return WeighIn(photo.weight_kg, photo.measured_at, fresh=True)
        nearest = await self._measurements.nearest_weigh_in(user_id, photo.measured_at)
        if nearest is None or nearest.weight_kg is None:
            return None
        return WeighIn(
            nearest.weight_kg,
            nearest.measured_at,
            fresh=weight_is_fresh(nearest.measured_at, photo.measured_at),
        )

    async def existing(
        self, user_id: int, photo: BodyMeasurement, *, model: str, prompt_version: str
    ) -> BodyEstimate | None:
        return await self._estimates.for_photo(
            user_id, photo.id, model=model, prompt_version=prompt_version
        )

    async def previous(
        self, user_id: int, *, before: datetime, model: str, prompt_version: str
    ) -> BodyEstimate | None:
        return await self._estimates.previous(
            user_id, before=before, model=model, prompt_version=prompt_version
        )

    async def record(
        self,
        user_id: int,
        photo: BodyMeasurement,
        *,
        band: Band,
        weight_kg: Decimal | None,
        height_cm: int | None,
        observations: Sequence[str],
        limits: str | None,
        model: str,
        prompt_version: str,
    ) -> BodyEstimate:
        assert photo.photo_file_id is not None
        return await self._estimates.add(
            BodyEstimate(
                user_id=user_id,
                measurement_id=photo.id,
                measured_at=photo.measured_at,
                photo_file_id=photo.photo_file_id,
                bf_low=band.low,
                bf_likely=band.likely,
                bf_high=band.high,
                weight_kg=weight_kg,
                height_cm=height_cm,
                observations=list(observations),
                limits=limits,
                model=model,
                prompt_version=prompt_version,
            )
        )

"""Data access for body-composition estimates."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import BodyEstimate


class BodyEstimateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, estimate: BodyEstimate) -> BodyEstimate:
        self._session.add(estimate)
        await self._session.flush()
        return estimate

    async def for_photo(
        self, user_id: int, measurement_id: int, *, model: str, prompt_version: str
    ) -> BodyEstimate | None:
        """An earlier reading of this very photo by the same reader, if any."""
        stmt = (
            select(BodyEstimate)
            .where(
                BodyEstimate.user_id == user_id,
                BodyEstimate.measurement_id == measurement_id,
                BodyEstimate.model == model,
                BodyEstimate.prompt_version == prompt_version,
            )
            .order_by(BodyEstimate.id.desc())
            .limit(1)
        )
        estimate: BodyEstimate | None = await self._session.scalar(stmt)
        return estimate

    async def previous(
        self, user_id: int, *, before: datetime, model: str, prompt_version: str
    ) -> BodyEstimate | None:
        """The last estimate of an earlier photo, read by the same reader.

        Strictly earlier photo time, so re-reading an old photo compares it
        with what came before it, not with today.
        """
        stmt = (
            select(BodyEstimate)
            .where(
                BodyEstimate.user_id == user_id,
                BodyEstimate.measured_at < before,
                BodyEstimate.model == model,
                BodyEstimate.prompt_version == prompt_version,
            )
            .order_by(BodyEstimate.measured_at.desc(), BodyEstimate.id.desc())
            .limit(1)
        )
        estimate: BodyEstimate | None = await self._session.scalar(stmt)
        return estimate

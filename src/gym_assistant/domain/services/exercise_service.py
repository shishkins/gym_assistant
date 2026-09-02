"""Exercise catalogue use cases."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import Equipment, Exercise, ExerciseType, MuscleGroup
from gym_assistant.domain.repositories.exercise_repository import ExerciseRepository
from gym_assistant.domain.slugs import normalise_alias, slugify


class DuplicateExerciseError(ValueError):
    """The user already has an exercise under this name."""


@dataclass(frozen=True, slots=True)
class CatalogueStats:
    total: int
    own: int
    favourites: int


class ExerciseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._exercises = ExerciseRepository(session)

    # -- browsing ----------------------------------------------------------

    async def muscle_groups(self) -> list[MuscleGroup]:
        return await self._exercises.muscle_groups()

    async def by_muscle_group(
        self, muscle_group_id: int, *, user_id: int, limit: int = 50, offset: int = 0
    ) -> list[Exercise]:
        return await self._exercises.by_muscle_group(
            muscle_group_id, user_id=user_id, limit=limit, offset=offset
        )

    async def count_by_muscle_group(self, muscle_group_id: int, *, user_id: int) -> int:
        return await self._exercises.count_by_muscle_group(muscle_group_id, user_id=user_id)

    async def search(self, query: str, *, user_id: int, limit: int = 10) -> list[Exercise]:
        return await self._exercises.search(query, user_id=user_id, limit=limit)

    async def get(self, exercise_id: int, *, user_id: int) -> Exercise | None:
        return await self._exercises.get(exercise_id, user_id=user_id)

    async def is_favourite(self, user_id: int, exercise_id: int) -> bool:
        return await self._exercises.is_favourite(user_id, exercise_id)

    async def favourites(self, user_id: int) -> list[Exercise]:
        return await self._exercises.favourites(user_id)

    async def own(self, user_id: int) -> list[Exercise]:
        return await self._exercises.own(user_id)

    async def stats(self, user_id: int) -> CatalogueStats:
        return CatalogueStats(
            total=await self._exercises.count_visible(user_id),
            own=len(await self._exercises.own(user_id)),
            favourites=len(await self._exercises.favourites(user_id, limit=1000)),
        )

    # -- authoring ---------------------------------------------------------

    async def create_own(
        self,
        user_id: int,
        *,
        name: str,
        primary_muscle_group_id: int,
        equipment: Equipment,
        exercise_type: ExerciseType,
        secondary_muscle_group_ids: list[int] | None = None,
        is_compound: bool = False,
        video_url: str | None = None,
        technique_tips: str | None = None,
    ) -> Exercise:
        clean_name = " ".join(name.strip().split())
        slug = slugify(clean_name)

        if await self._exercises.slug_exists(slug, owner_user_id=user_id):
            # Better a clear refusal than a silent "squat-2" the user never
            # asked for and will not recognise later.
            raise DuplicateExerciseError(clean_name)

        exercise = Exercise(
            owner_user_id=user_id,
            slug=slug,
            name_ru=clean_name,
            # The name itself is the alias, so search finds it immediately.
            aliases=[normalise_alias(clean_name)],
            primary_muscle_group_id=primary_muscle_group_id,
            equipment=equipment.value,
            exercise_type=exercise_type.value,
            is_compound=is_compound,
            video_url=video_url,
            technique_tips=technique_tips,
        )
        created = await self._exercises.add(
            exercise, secondary_ids=secondary_muscle_group_ids or []
        )

        # Re-read through a query so the relationship loaders actually run.
        # A freshly constructed object has its relationships unloaded, and
        # under asyncio touching one raises MissingGreenlet rather than
        # quietly emitting a SELECT - which is exactly what a renderer does.
        stored = await self._exercises.get(created.id, user_id=user_id)
        if stored is None:  # pragma: no cover - the row was just written
            raise RuntimeError(f"exercise {created.id} vanished right after insert")
        return stored

    # -- per-user preferences ---------------------------------------------

    async def toggle_favourite(self, user_id: int, exercise_id: int) -> bool:
        preference = await self._exercises.preference(user_id, exercise_id)
        preference.is_favourite = not preference.is_favourite
        await self._session.flush()
        return preference.is_favourite

    async def set_hidden(self, user_id: int, exercise_id: int, *, hidden: bool) -> None:
        """Hides a catalogue entry for one user.

        Deliberately not a copy of the exercise: a copy would drift from the
        original and duplicate every future catalogue update.
        """
        preference = await self._exercises.preference(user_id, exercise_id)
        preference.is_hidden = hidden
        await self._session.flush()

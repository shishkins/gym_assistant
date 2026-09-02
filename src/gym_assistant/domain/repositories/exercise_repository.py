"""Data access for the exercise catalogue."""

from __future__ import annotations

from sqlalchemy import ColumnElement, Text, and_, case, cast, func, or_, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import (
    Exercise,
    ExerciseSecondaryMuscle,
    MuscleGroup,
    UserExercisePref,
)

# Measured against the shipped catalogue: real typos of a reasonable length
# score 0.43-0.86, while nonsense ("телефон", "квакозябра") stays at 0.09-0.25.
# 0.4 separates the two cleanly.
#
# word_similarity, not similarity: the latter divides shared trigrams by the
# trigrams of the whole string, so a short query against a long exercise name
# always scores low ("приседанья" vs "Приседания со штангой" -> 0.3). This one
# compares the query against the best-matching fragment of the name instead.
#
# Known limit: a three-letter word with a middle typo ("жым" for "жим") shares
# almost no trigrams and sits at the noise floor. It is unreachable at any
# threshold that does not also admit unrelated words - exact aliases cover it.
WORD_SIMILARITY_THRESHOLD = 0.4


class ExerciseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- visibility --------------------------------------------------------

    @staticmethod
    def _visible_to(user_id: int) -> ColumnElement[bool]:
        """System exercises plus the user's own, minus the ones they hid."""
        hidden = select(UserExercisePref.exercise_id).where(
            UserExercisePref.user_id == user_id,
            UserExercisePref.is_hidden.is_(True),
        )
        return and_(
            Exercise.is_active.is_(True),
            or_(Exercise.owner_user_id.is_(None), Exercise.owner_user_id == user_id),
            Exercise.id.not_in(hidden),
        )

    # -- reads -------------------------------------------------------------

    async def muscle_groups(self) -> list[MuscleGroup]:
        stmt = select(MuscleGroup).order_by(MuscleGroup.sort_order)
        return list(await self._session.scalars(stmt))

    async def get(self, exercise_id: int, *, user_id: int) -> Exercise | None:
        stmt = select(Exercise).where(Exercise.id == exercise_id, self._visible_to(user_id))
        exercise: Exercise | None = await self._session.scalar(stmt)
        return exercise

    async def by_slug(self, slug: str, *, user_id: int) -> Exercise | None:
        stmt = (
            select(Exercise)
            .where(Exercise.slug == slug, self._visible_to(user_id))
            # A personal exercise wins over a system one with the same slug.
            .order_by(Exercise.owner_user_id.is_(None))
            .limit(1)
        )
        exercise: Exercise | None = await self._session.scalar(stmt)
        return exercise

    async def search(self, query: str, *, user_id: int, limit: int = 10) -> list[Exercise]:
        """Ranked search: exact alias, then prefix, then substring, then fuzzy."""
        needle = " ".join(query.strip().lower().split())
        if not needle:
            return []

        # Array containment rather than `= ANY(...)`: only @> uses the GIN index.
        alias_hit = Exercise.aliases.bool_op("@>")(cast([needle], ARRAY(Text)))
        name_prefix = Exercise.name_ru.ilike(f"{needle}%")
        name_contains = Exercise.name_ru.ilike(f"%{needle}%")
        closeness = func.word_similarity(needle, Exercise.name_ru)

        rank = case(
            (alias_hit, 0),
            (name_prefix, 1),
            (name_contains, 2),
            else_=3,
        )

        stmt = (
            select(Exercise)
            .where(self._visible_to(user_id))
            .where(or_(alias_hit, name_contains, closeness > WORD_SIMILARITY_THRESHOLD))
            # On a tie the shorter name wins: it is usually the base movement
            # ("Выпады" before "Болгарские выпады").
            .order_by(rank, closeness.desc(), func.length(Exercise.name_ru), Exercise.name_ru)
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def by_muscle_group(
        self, muscle_group_id: int, *, user_id: int, limit: int = 50
    ) -> list[Exercise]:
        stmt = (
            select(Exercise)
            .where(
                self._visible_to(user_id),
                Exercise.primary_muscle_group_id == muscle_group_id,
            )
            # Compound movements first: they are what a session is built around.
            .order_by(Exercise.is_compound.desc(), Exercise.name_ru)
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def favourites(self, user_id: int, *, limit: int = 10) -> list[Exercise]:
        stmt = (
            select(Exercise)
            .join(UserExercisePref, UserExercisePref.exercise_id == Exercise.id)
            .where(
                UserExercisePref.user_id == user_id,
                UserExercisePref.is_favourite.is_(True),
                self._visible_to(user_id),
            )
            .order_by(Exercise.name_ru)
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def own(self, user_id: int) -> list[Exercise]:
        stmt = (
            select(Exercise)
            .where(Exercise.owner_user_id == user_id, Exercise.is_active.is_(True))
            .order_by(Exercise.name_ru)
        )
        return list(await self._session.scalars(stmt))

    async def count_visible(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(Exercise).where(self._visible_to(user_id))
        return await self._session.scalar(stmt) or 0

    async def is_favourite(self, user_id: int, exercise_id: int) -> bool:
        """Read-only check: preference() would insert a row as a side effect."""
        stmt = select(UserExercisePref.is_favourite).where(
            UserExercisePref.user_id == user_id,
            UserExercisePref.exercise_id == exercise_id,
        )
        return bool(await self._session.scalar(stmt))

    async def slug_exists(self, slug: str, *, owner_user_id: int | None) -> bool:
        stmt = select(Exercise.id).where(
            Exercise.slug == slug,
            Exercise.owner_user_id.is_(None)
            if owner_user_id is None
            else Exercise.owner_user_id == owner_user_id,
        )
        return await self._session.scalar(stmt) is not None

    # -- writes ------------------------------------------------------------

    async def add(self, exercise: Exercise, *, secondary_ids: list[int]) -> Exercise:
        self._session.add(exercise)
        await self._session.flush()
        for muscle_group_id in secondary_ids:
            self._session.add(
                ExerciseSecondaryMuscle(exercise_id=exercise.id, muscle_group_id=muscle_group_id)
            )
        await self._session.flush()
        return exercise

    async def preference(self, user_id: int, exercise_id: int) -> UserExercisePref:
        existing = await self._session.get(UserExercisePref, (user_id, exercise_id))
        if existing is not None:
            return existing
        created = UserExercisePref(user_id=user_id, exercise_id=exercise_id)
        self._session.add(created)
        await self._session.flush()
        return created

"""Data access for the exercise catalogue."""

from __future__ import annotations

from typing import Any

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

    @staticmethod
    def _normalise(query: str) -> str:
        return " ".join(query.strip().lower().split())

    def _search_terms(
        self, needle: str
    ) -> tuple[ColumnElement[bool], ColumnElement[bool], Any, Any]:
        """Precise and fuzzy predicates, plus rank and closeness.

        They are built once because counting and paging must use the identical
        predicate: if they drift, the page counter lies about a list the user
        can see.
        """
        # Array containment rather than `= ANY(...)`: only @> uses the GIN index.
        alias_hit = Exercise.aliases.bool_op("@>")(cast([needle], ARRAY(Text)))
        # Muscle group names are the first thing people type. Without this,
        # "трицепс" matches nothing by name and the trigram search happily
        # returns biceps work, which differs by a single letter.
        group_hit = func.lower(MuscleGroup.name_ru) == needle
        name_prefix = Exercise.name_ru.ilike(f"{needle}%")
        name_contains = Exercise.name_ru.ilike(f"%{needle}%")
        closeness = func.word_similarity(needle, Exercise.name_ru)

        precise = or_(alias_hit, group_hit, name_contains)
        fuzzy = closeness > WORD_SIMILARITY_THRESHOLD
        rank = case(
            (alias_hit, 0),
            (group_hit, 1),
            (name_prefix, 2),
            (name_contains, 3),
            else_=4,
        )
        return precise, fuzzy, rank, closeness

    def _matching(self, needle: str, user_id: int, *, condition: ColumnElement[bool]) -> Any:
        return (
            select(Exercise.id)
            .join(MuscleGroup, MuscleGroup.id == Exercise.primary_muscle_group_id)
            .where(self._visible_to(user_id), condition)
        )

    async def search(
        self, query: str, *, user_id: int, limit: int = 10, offset: int = 0
    ) -> list[Exercise]:
        """Ranked search: exact alias, muscle group, prefix, substring, then fuzzy.

        Fuzzy is a FALLBACK, not an addition. Trigrams are generous - "бенч"
        is close enough to "Бег на дорожке" to clear any threshold that still
        catches real typos - so mixing fuzzy hits into a query that already
        matched exactly only adds noise to a correct answer.
        """
        needle = self._normalise(query)
        if not needle:
            return []

        precise, fuzzy, rank, closeness = self._search_terms(needle)

        # Two different questions, so two different orders.
        #
        # A precise hit means the query is understood: then the useful order
        # is the one a lifter thinks in - base movements first, staples above
        # their variations. Popularity replaced name length here, which on a
        # large catalogue decided this silently and wrongly: "Гакк-приседания"
        # is shorter than "Приседания со штангой" and used to win.
        #
        # A fuzzy hit means we are guessing at a typo. There the closest text
        # is the whole point, and compound-first actively hurts: "планко"
        # matched "Плавание" (compound) above "Планка" (isolation).
        orders = {
            "precise": (
                rank,
                Exercise.is_compound.desc(),
                Exercise.popularity,
                closeness.desc(),
                Exercise.name_ru,
            ),
            "fuzzy": (
                closeness.desc(),
                Exercise.popularity,
                Exercise.is_compound.desc(),
                Exercise.name_ru,
            ),
        }

        for kind, condition in (("precise", precise), ("fuzzy", fuzzy)):
            stmt = (
                select(Exercise)
                .join(MuscleGroup, MuscleGroup.id == Exercise.primary_muscle_group_id)
                .where(self._visible_to(user_id), condition)
                .order_by(*orders[kind])
                .offset(offset)
                .limit(limit)
            )
            found = list(await self._session.scalars(stmt))
            if found:
                return found
        return []

    async def count_search(self, query: str, *, user_id: int) -> int:
        needle = self._normalise(query)
        if not needle:
            return 0

        precise, fuzzy, _, _ = self._search_terms(needle)
        for condition in (precise, fuzzy):
            # Counted over a subquery, not select_from(...).where(...): the
            # predicate references muscle_groups, and without an explicit join
            # that table joined the FROM unconstrained - a cartesian product
            # that inflated the page count eightfold while failing nothing.
            matching = self._matching(needle, user_id, condition=condition).subquery()
            total = await self._session.scalar(select(func.count()).select_from(matching))
            if total:
                return int(total)
        return 0

    async def by_muscle_group(
        self, muscle_group_id: int, *, user_id: int, limit: int = 50, offset: int = 0
    ) -> list[Exercise]:
        stmt = (
            select(Exercise)
            .where(
                self._visible_to(user_id),
                Exercise.primary_muscle_group_id == muscle_group_id,
            )
            # Compound movements first: they are what a session is built around.
            # name_ru is the tiebreaker so paging stays stable between calls.
            .order_by(Exercise.is_compound.desc(), Exercise.popularity, Exercise.name_ru)
            .offset(offset)
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def count_by_muscle_group(self, muscle_group_id: int, *, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Exercise)
            .where(
                self._visible_to(user_id),
                Exercise.primary_muscle_group_id == muscle_group_id,
            )
        )
        return await self._session.scalar(stmt) or 0

    async def favourites(self, user_id: int, *, limit: int = 50, offset: int = 0) -> list[Exercise]:
        stmt = (
            select(Exercise)
            .join(UserExercisePref, UserExercisePref.exercise_id == Exercise.id)
            .where(
                UserExercisePref.user_id == user_id,
                UserExercisePref.is_favourite.is_(True),
                self._visible_to(user_id),
            )
            .order_by(Exercise.name_ru)
            .offset(offset)
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def count_favourites(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Exercise)
            .join(UserExercisePref, UserExercisePref.exercise_id == Exercise.id)
            .where(
                UserExercisePref.user_id == user_id,
                UserExercisePref.is_favourite.is_(True),
                self._visible_to(user_id),
            )
        )
        return await self._session.scalar(stmt) or 0

    async def own(self, user_id: int, *, limit: int = 50, offset: int = 0) -> list[Exercise]:
        """Bounded on purpose: an unbounded list becomes a keyboard Telegram refuses."""
        stmt = (
            select(Exercise)
            .where(Exercise.owner_user_id == user_id, Exercise.is_active.is_(True))
            .order_by(Exercise.name_ru)
            .offset(offset)
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def count_own(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Exercise)
            .where(Exercise.owner_user_id == user_id, Exercise.is_active.is_(True))
        )
        return await self._session.scalar(stmt) or 0

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

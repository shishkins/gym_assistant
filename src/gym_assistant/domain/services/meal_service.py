"""Food-diary use cases.

Two things live here that are not obvious from the tables.

**Nothing is stored until the person agrees.** A breakdown the model produced
sits in the dialogue state; only :meth:`MealService.record` writes. A diary
that fills with guesses nobody confirmed is worse than an empty one, because
every later number is built on top of them.

**What the person has eaten before is the closest thing to a reference we
have.** Measured: the same croissant came back from the model under three
different names, which breaks any accumulation. A closed catalogue is the
wrong fix - food is an open set, unlike exercises - so the anchor is the
person's own history, fed back into the prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import GramsSource, Meal, MealItem

# Long enough to cover a habit, short enough that last spring's holiday food
# does not crowd out what is eaten now.
RECENT_DAYS = 45
RECENT_NAMES = 40


@dataclass(frozen=True, slots=True)
class DayTotals:
    """One day on the plate."""

    day: datetime
    kcal: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carb_g: Decimal
    meals: int


class MealService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        user_id: int,
        *,
        items: list[dict[str, object]],
        photo_file_id: str | None = None,
        note: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        first_pass: dict[str, object] | None = None,
        hints: dict[str, object] | None = None,
        eaten_at: datetime | None = None,
    ) -> Meal:
        """Writes a confirmed meal and its items in one go.

        Totals are summed here rather than by a trigger or a later query:
        every report adds them up, and a stored sum cannot disagree with the
        items it came from if it is written beside them.
        """
        meal = Meal(
            user_id=user_id,
            eaten_at=eaten_at or datetime.now(UTC),
            photo_file_id=photo_file_id,
            note=note,
            model=model,
            prompt_version=prompt_version,
            first_pass=first_pass,
            hints=hints,
        )

        for index, entry in enumerate(items):
            meal.items.append(
                MealItem(
                    order_index=index,
                    name=str(entry["name"]),
                    grams=_money(entry["grams"]),
                    grams_low=_optional(entry.get("grams_low")),
                    grams_high=_optional(entry.get("grams_high")),
                    kcal_100g=_money(entry["kcal_100g"]),
                    protein_100g=_money(entry["protein_100g"]),
                    fat_100g=_money(entry["fat_100g"]),
                    carb_100g=_money(entry["carb_100g"]),
                    grams_source=str(entry.get("grams_source") or GramsSource.MODEL.value),
                )
            )

        meal.kcal = _sum(meal.items, "kcal_100g")
        meal.protein_g = _sum(meal.items, "protein_100g")
        meal.fat_g = _sum(meal.items, "fat_100g")
        meal.carb_g = _sum(meal.items, "carb_100g")

        self._session.add(meal)
        await self._session.flush()
        return meal

    async def delete(self, user_id: int, meal_id: int) -> bool:
        """Removes a meal, if it belongs to this person.

        ``user_id`` is part of the condition rather than checked beforehand:
        a mistyped id then deletes nothing instead of someone else's lunch.
        """
        meal = await self._session.get(Meal, meal_id)
        if meal is None or meal.user_id != user_id:
            return False
        await self._session.delete(meal)
        await self._session.flush()
        return True

    async def last(self, user_id: int) -> Meal | None:
        result = await self._session.execute(
            select(Meal).where(Meal.user_id == user_id).order_by(Meal.eaten_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def recent_names(self, user_id: int, limit: int = RECENT_NAMES) -> list[str]:
        """What this person has eaten lately, most often first.

        Goes into the prompt as an anchor. Without it the model renames the
        same food every time and nothing accumulates; with it, a croissant
        eaten on Monday is the same row as the one eaten on Friday.
        """
        since = datetime.now(UTC).timestamp() - RECENT_DAYS * 86400
        result = await self._session.execute(
            select(MealItem.name, func.count().label("times"))
            .join(Meal, Meal.id == MealItem.meal_id)
            .where(
                Meal.user_id == user_id,
                Meal.eaten_at >= datetime.fromtimestamp(since, tz=UTC),
            )
            .group_by(MealItem.name)
            .order_by(func.count().desc(), MealItem.name)
            .limit(limit)
        )
        return [name for name, _ in result.all()]

    async def day_totals(self, user_id: int, *, days: int = 7) -> list[DayTotals]:
        """Calories per day, newest first. The spine of everything above it."""
        since = datetime.now(UTC).timestamp() - days * 86400
        day = func.date_trunc("day", Meal.eaten_at).label("day")
        result = await self._session.execute(
            select(
                day,
                func.sum(Meal.kcal),
                func.sum(Meal.protein_g),
                func.sum(Meal.fat_g),
                func.sum(Meal.carb_g),
                func.count(),
            )
            .where(
                Meal.user_id == user_id,
                Meal.eaten_at >= datetime.fromtimestamp(since, tz=UTC),
            )
            .group_by(day)
            .order_by(day.desc())
        )
        return [
            DayTotals(
                day=row[0],
                kcal=row[1] or Decimal(0),
                protein_g=row[2] or Decimal(0),
                fat_g=row[3] or Decimal(0),
                carb_g=row[4] or Decimal(0),
                meals=row[5],
            )
            for row in result.all()
        ]


def _sum(items: list[MealItem], per_100g: str) -> Decimal:
    total = sum(
        (item.grams * getattr(item, per_100g) / 100 for item in items),
        Decimal(0),
    )
    return Decimal(total).quantize(Decimal("0.1"))


def _money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.1"))


def _optional(value: object) -> Decimal | None:
    return None if value is None else _money(value)

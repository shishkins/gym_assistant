"""Profile use cases: registration, editing and the profile card."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import ExperienceLevel, Goal, Sex, User, UserProfile
from gym_assistant.domain.parsing import calculate_age
from gym_assistant.domain.repositories import MeasurementRepository, UserRepository
from gym_assistant.domain.rules import bmi_category, calculate_bmi


@dataclass(frozen=True, slots=True)
class ProfileSummary:
    """Everything needed to render a profile card or to brief the assistant."""

    first_name: str | None
    sex: Sex | None
    birth_date: date | None
    age: int | None
    height_cm: int | None
    goal: Goal | None
    experience_level: ExperienceLevel | None
    weekly_target: int | None
    weight_kg: Decimal | None
    weight_measured_at: datetime | None
    bmi: Decimal | None
    bmi_band: str | None
    measurements_count: int

    @property
    def is_empty(self) -> bool:
        return not any((self.sex, self.birth_date, self.height_cm, self.goal, self.weight_kg))


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._measurements = MeasurementRepository(session)

    async def get_or_create_user(
        self,
        telegram_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
    ) -> User:
        user = await self._users.get_by_telegram_id(telegram_id)

        if user is None:
            try:
                # aiogram handles updates concurrently, so two messages
                # arriving together can both find no user and both insert.
                # The unique index settles it; the loser just re-reads.
                async with self._session.begin_nested():
                    user = await self._users.add(telegram_id, username, first_name)
            except IntegrityError:
                user = await self._users.get_by_telegram_id(telegram_id)
                if user is None:  # pragma: no cover - only on a real DB fault
                    raise
            else:
                return user

        # Telegram display data changes over time; keep our copy current.
        if username != user.username:
            user.username = username
        if first_name and first_name != user.first_name:
            user.first_name = first_name

        return user

    async def get_profile(self, user_id: int) -> UserProfile:
        user = await self._users.get(user_id)
        if user is None:
            raise LookupError(f"user {user_id} does not exist")
        if user.profile is None:
            user.profile = UserProfile()
            await self._session.flush()
        return user.profile

    async def update_profile(
        self,
        user_id: int,
        *,
        sex: Sex | None = None,
        birth_date: date | None = None,
        height_cm: int | None = None,
        goal: Goal | None = None,
        experience_level: ExperienceLevel | None = None,
        weekly_target: int | None = None,
    ) -> UserProfile:
        """Applies only the fields that were passed.

        ``None`` means "leave alone", not "clear" - clearing is done with
        :meth:`clear_profile_field`, so a forgotten argument can never wipe
        data the user entered earlier.
        """
        profile = await self.get_profile(user_id)

        if sex is not None:
            profile.sex = sex.value
        if birth_date is not None:
            profile.birth_date = birth_date
        if height_cm is not None:
            profile.height_cm = height_cm
        if goal is not None:
            profile.goal = goal.value
        if experience_level is not None:
            profile.experience_level = experience_level.value
        if weekly_target is not None:
            profile.weekly_target = weekly_target

        await self._session.flush()
        return profile

    async def clear_profile_field(self, user_id: int, field: str) -> UserProfile:
        allowed = {"sex", "birth_date", "height_cm", "goal", "experience_level", "weekly_target"}
        if field not in allowed:
            raise ValueError(f"unknown profile field: {field}")

        profile = await self.get_profile(user_id)
        setattr(profile, field, None)
        await self._session.flush()
        return profile

    async def get_summary(self, user_id: int, *, today: date) -> ProfileSummary:
        user = await self._users.get(user_id)
        if user is None:
            raise LookupError(f"user {user_id} does not exist")

        profile = user.profile or UserProfile()
        weigh_in = await self._measurements.latest_with_weight(user_id)
        count = await self._measurements.count(user_id)

        weight = weigh_in.weight_kg if weigh_in else None
        bmi = (
            calculate_bmi(weight, profile.height_cm)
            if weight is not None and profile.height_cm
            else None
        )

        return ProfileSummary(
            first_name=user.first_name,
            sex=Sex(profile.sex) if profile.sex else None,
            birth_date=profile.birth_date,
            age=calculate_age(profile.birth_date, today=today) if profile.birth_date else None,
            height_cm=profile.height_cm,
            goal=Goal(profile.goal) if profile.goal else None,
            experience_level=(
                ExperienceLevel(profile.experience_level) if profile.experience_level else None
            ),
            weekly_target=profile.weekly_target,
            weight_kg=weight,
            weight_measured_at=weigh_in.measured_at if weigh_in else None,
            bmi=bmi,
            bmi_band=bmi_category(bmi) if bmi is not None else None,
            measurements_count=count,
        )

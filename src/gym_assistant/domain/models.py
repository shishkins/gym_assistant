"""SQLAlchemy ORM models.

Two conventions worth knowing before adding tables here:

* Every user-owned table carries ``user_id``. The bot runs on a whitelist
  today, but the schema is multi-user from day one so going public later
  is a policy change rather than a migration of every query.
* Relationships default to ``lazy="raise"``. Under asyncio an accidental
  lazy load raises ``MissingGreenlet`` deep inside a handler; making it a
  loud, explicit error at development time is far cheaper.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


class TimestampMixin:
    """``created_at`` / ``updated_at``, maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Enumerations
#
# Stored as short strings with a CHECK constraint rather than a native
# PostgreSQL ENUM: adding a value to a native enum needs its own migration
# and locks, while a CHECK constraint is a cheap swap.
# ---------------------------------------------------------------------------


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class Goal(StrEnum):
    MASS = "mass"
    STRENGTH = "strength"
    CUT = "cut"
    HEALTH = "health"


class ExperienceLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


def _enum_check(column: str, enum: type[StrEnum]) -> str:
    allowed = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IS NULL OR {column} IN ({allowed})"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, server_default="ru")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    profile: Mapped[UserProfile | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    measurements: Mapped[list[BodyMeasurement]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_id={self.telegram_id}>"


class UserProfile(Base, TimestampMixin):
    """Slow-moving characteristics. Body weight lives in BodyMeasurement."""

    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint(_enum_check("sex", Sex), name="ck_user_profiles_sex"),
        CheckConstraint(_enum_check("goal", Goal), name="ck_user_profiles_goal"),
        CheckConstraint(
            _enum_check("experience_level", ExperienceLevel),
            name="ck_user_profiles_experience_level",
        ),
        CheckConstraint(
            "height_cm IS NULL OR (height_cm BETWEEN 100 AND 250)",
            name="ck_user_profiles_height_cm",
        ),
        CheckConstraint(
            "weekly_target IS NULL OR (weekly_target BETWEEN 1 AND 14)",
            name="ck_user_profiles_weekly_target",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sex: Mapped[str | None] = mapped_column(String(16))
    # Stored as a date, never as a number: age recomputed is always correct,
    # age stored goes stale the moment it is written.
    birth_date: Mapped[date | None] = mapped_column(Date)
    height_cm: Mapped[int | None] = mapped_column(SmallInteger)
    goal: Mapped[str | None] = mapped_column(String(16))
    experience_level: Mapped[str | None] = mapped_column(String(16))
    weekly_target: Mapped[int | None] = mapped_column(SmallInteger)

    user: Mapped[User] = relationship(back_populates="profile", lazy="raise")

    def __repr__(self) -> str:
        return f"<UserProfile user_id={self.user_id}>"


class BodyMeasurement(Base, TimestampMixin):
    """One point in the body-metrics time series."""

    __tablename__ = "body_measurements"
    __table_args__ = (
        Index("ix_body_measurements_user_measured", "user_id", "measured_at"),
        CheckConstraint(
            "weight_kg IS NULL OR (weight_kg BETWEEN 20 AND 400)",
            name="ck_body_measurements_weight_kg",
        ),
        CheckConstraint(
            "body_fat_pct IS NULL OR (body_fat_pct BETWEEN 3 AND 70)",
            name="ck_body_measurements_body_fat_pct",
        ),
        # A row with nothing in it is a bug, not a measurement.
        CheckConstraint(
            "weight_kg IS NOT NULL OR body_fat_pct IS NOT NULL "
            "OR chest_cm IS NOT NULL OR waist_cm IS NOT NULL OR hip_cm IS NOT NULL "
            "OR biceps_cm IS NOT NULL OR thigh_cm IS NOT NULL "
            "OR photo_file_id IS NOT NULL",
            name="ck_body_measurements_not_empty",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    body_fat_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    chest_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    waist_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    hip_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    biceps_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    thigh_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))

    # Telegram keeps uploaded files indefinitely, so we store the handle
    # rather than the bytes. Caveat: file_id is bound to this bot token and
    # would not survive a bot change - accepted for the MVP.
    photo_file_id: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="measurements", lazy="raise")

    def __repr__(self) -> str:
        return f"<BodyMeasurement id={self.id} user_id={self.user_id} at={self.measured_at}>"

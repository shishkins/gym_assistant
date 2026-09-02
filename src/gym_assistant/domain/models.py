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
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
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


class WorkoutStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Equipment(StrEnum):
    BARBELL = "barbell"
    DUMBBELL = "dumbbell"
    MACHINE = "machine"
    CABLE = "cable"
    BODYWEIGHT = "bodyweight"
    KETTLEBELL = "kettlebell"
    OTHER = "other"


class ExerciseType(StrEnum):
    """Decides which fields a set of this exercise asks for."""

    WEIGHT_REPS = "weight_reps"  # bench press: weight x reps
    BODYWEIGHT_REPS = "bodyweight_reps"  # pull-ups: reps, optional added weight
    TIME = "time"  # plank: seconds
    DISTANCE = "distance"  # farmer's walk: metres


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


class MuscleGroup(Base):
    """Reference list. Seeded once and rarely touched."""

    __tablename__ = "muscle_groups"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))

    def __repr__(self) -> str:
        return f"<MuscleGroup {self.code}>"


class Exercise(Base, TimestampMixin):
    """A movement, either shipped with the bot or added by one user.

    ``owner_user_id IS NULL`` marks a system exercise, visible to everyone.
    A non-null owner makes it private to that user.
    """

    __tablename__ = "exercises"
    __table_args__ = (
        # COALESCE, because a plain UNIQUE(owner_user_id, slug) would let the
        # same system slug be inserted twice: NULLs never collide in SQL.
        Index(
            "uq_exercises_owner_slug",
            text("COALESCE(owner_user_id, 0)"),
            "slug",
            unique=True,
        ),
        Index("ix_exercises_owner", "owner_user_id"),
        # Alias lookup is an array-containment test.
        Index("ix_exercises_aliases", "aliases", postgresql_using="gin"),
        # Trigram index: powers typo-tolerant search on the display name.
        Index(
            "ix_exercises_name_trgm",
            "name_ru",
            postgresql_using="gin",
            postgresql_ops={"name_ru": "gin_trgm_ops"},
        ),
        CheckConstraint(_enum_check("equipment", Equipment), name="ck_exercises_equipment"),
        CheckConstraint(
            _enum_check("exercise_type", ExerciseType),
            name="ck_exercises_exercise_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name_ru: Mapped[str] = mapped_column(Text, nullable=False)
    # Search terms people actually type: "бенч", "жим", "жим лёжа".
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )

    primary_muscle_group_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("muscle_groups.id", ondelete="RESTRICT"),
        nullable=False,
    )
    equipment: Mapped[str] = mapped_column(String(16), nullable=False)
    exercise_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_compound: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    video_url: Mapped[str | None] = mapped_column(Text)
    technique_tips: Mapped[str | None] = mapped_column(Text)
    common_mistakes: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    primary_muscle_group: Mapped[MuscleGroup] = relationship(lazy="selectin")
    secondary_muscle_groups: Mapped[list[MuscleGroup]] = relationship(
        secondary="exercise_secondary_muscles",
        lazy="selectin",
        order_by="MuscleGroup.sort_order",
    )

    @property
    def is_system(self) -> bool:
        return self.owner_user_id is None

    def __repr__(self) -> str:
        return f"<Exercise {self.slug} owner={self.owner_user_id}>"


class ExerciseSecondaryMuscle(Base):
    """Muscles a movement also loads, used for weekly volume in iteration 4."""

    __tablename__ = "exercise_secondary_muscles"

    exercise_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exercises.id", ondelete="CASCADE"),
        primary_key=True,
    )
    muscle_group_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("muscle_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )


class UserExercisePref(Base, TimestampMixin):
    """Per-user view of the shared catalogue.

    Hiding writes a row here rather than copying the exercise: a copy would
    drift from the original and double every future catalogue update.
    """

    __tablename__ = "user_exercise_prefs"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    exercise_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exercises.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_favourite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class Workout(Base, TimestampMixin):
    """One training session."""

    __tablename__ = "workouts"
    __table_args__ = (
        Index("ix_workouts_user_started", "user_id", "started_at"),
        # One session at a time. Enforced by the database rather than by a
        # check in the handler: two quick taps are genuinely concurrent.
        Index(
            "uq_workouts_one_in_progress",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
        ),
        CheckConstraint(_enum_check("status", WorkoutStatus), name="ck_workouts_status"),
        CheckConstraint(
            "perceived_effort IS NULL OR (perceived_effort BETWEEN 1 AND 10)",
            name="ck_workouts_perceived_effort",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_workouts_finished_after_started",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=WorkoutStatus.IN_PROGRESS.value
    )
    note: Mapped[str | None] = mapped_column(Text)
    perceived_effort: Mapped[int | None] = mapped_column(SmallInteger)

    sets: Mapped[list[WorkoutSet]] = relationship(
        back_populates="workout",
        cascade="all, delete-orphan",
        order_by="WorkoutSet.performed_at",
        lazy="selectin",
    )

    @property
    def is_open(self) -> bool:
        return self.status == WorkoutStatus.IN_PROGRESS.value

    def __repr__(self) -> str:
        return f"<Workout id={self.id} user_id={self.user_id} status={self.status}>"


class WorkoutSet(Base, TimestampMixin):
    """One set. The hottest table in the schema: written 15-30 times a session."""

    __tablename__ = "workout_sets"
    __table_args__ = (
        Index("ix_workout_sets_workout", "workout_id", "order_index", "set_index"),
        # Progress charts and personal records read one exercise across time.
        Index("ix_workout_sets_exercise_time", "exercise_id", "performed_at"),
        CheckConstraint("weight_kg IS NULL OR weight_kg BETWEEN 0 AND 1000", name="ck_sets_weight"),
        CheckConstraint("reps IS NULL OR reps BETWEEN 1 AND 1000", name="ck_sets_reps"),
        CheckConstraint("rpe IS NULL OR rpe BETWEEN 1 AND 10", name="ck_sets_rpe"),
        CheckConstraint(
            "duration_sec IS NULL OR duration_sec BETWEEN 1 AND 86400", name="ck_sets_duration"
        ),
        CheckConstraint(
            "distance_m IS NULL OR distance_m BETWEEN 1 AND 100000", name="ck_sets_distance"
        ),
        # A set that records nothing is a bug, not a set.
        CheckConstraint(
            "reps IS NOT NULL OR duration_sec IS NOT NULL OR distance_m IS NOT NULL",
            name="ck_sets_not_empty",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workout_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False
    )

    order_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    set_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))

    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    reps: Mapped[int | None] = mapped_column(SmallInteger)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[int | None] = mapped_column(Integer)
    rpe: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    is_warmup: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    workout: Mapped[Workout] = relationship(back_populates="sets", lazy="raise")
    exercise: Mapped[Exercise] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<WorkoutSet id={self.id} exercise_id={self.exercise_id}>"

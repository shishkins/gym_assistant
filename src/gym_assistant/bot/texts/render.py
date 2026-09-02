"""Turning domain objects into the text a user actually reads."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import quote_plus

from gym_assistant.bot.texts import ru
from gym_assistant.domain.models import Equipment, Exercise, ExerciseType
from gym_assistant.domain.services import ProfileSummary


def format_decimal(value: Decimal) -> str:
    """``Decimal('82.50')`` -> ``82.5``; ``Decimal('80.00')`` -> ``80``.

    Trailing zeros are noise on a screen, and ``normalize()`` cannot be used
    because it renders whole numbers in scientific notation.
    """
    text = f"{value:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def format_when(moment: datetime, *, now: datetime | None = None) -> str:
    """Coarse, human wording: exact timestamps are noise in a chat."""
    now = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)

    days = (now.date() - moment.date()).days
    if days <= 0:
        return "сегодня"
    if days == 1:
        return "вчера"
    if days < 7:
        return f"{days} дн. назад"
    if days < 30:
        return f"{days // 7} нед. назад"
    return format_date(moment.date())


def render_profile(summary: ProfileSummary) -> str:
    if summary.is_empty:
        return ru.PROFILE_EMPTY

    lines = [ru.PROFILE_HEADER]

    lines.append(f"Пол: <b>{_sex(summary)}</b>")
    lines.append(f"Возраст: <b>{_age(summary)}</b>")
    lines.append(f"Рост: <b>{_height(summary)}</b>")
    lines.append(f"Цель: <b>{_goal(summary)}</b>")
    lines.append(f"Опыт: <b>{_experience(summary)}</b>")

    if summary.weight_kg is not None:
        when = format_when(summary.weight_measured_at) if summary.weight_measured_at else ""
        lines.append(f"\nВес: <b>{format_decimal(summary.weight_kg)}</b> кг ({when})")

    if summary.bmi is not None and summary.bmi_band is not None:
        band = ru.BMI_LABELS[summary.bmi_band]
        lines.append(f"ИМТ: <b>{format_decimal(summary.bmi)}</b> — {band}")
        if summary.bmi_band in ("overweight", "obese"):
            # Saying this matters: for a trained lifter a high BMI is
            # routine, and an unqualified "ожирение" is simply misleading.
            lines.append(
                "<i>ИМТ не отличает мышцы от жира — для силовых это ориентир, не диагноз.</i>"
            )

    if summary.measurements_count:
        lines.append(f"\nЗамеров в истории: {summary.measurements_count}")

    return "\n".join(lines)


def render_profile_summary_short(summary: ProfileSummary) -> str:
    """One-liner for the greeting of a returning user."""
    parts: list[str] = []
    if summary.weight_kg is not None:
        parts.append(f"вес {format_decimal(summary.weight_kg)} кг")
    if summary.goal is not None:
        parts.append(ru.GOAL_LABELS[summary.goal].lower())
    if not parts:
        return "Профиль пока не заполнен — /profile"
    return "Сейчас: " + ", ".join(parts) + "."


def _sex(summary: ProfileSummary) -> str:
    return ru.SEX_LABELS[summary.sex] if summary.sex else ru.PROFILE_NOT_SET


def _age(summary: ProfileSummary) -> str:
    if summary.age is None or summary.birth_date is None:
        return ru.PROFILE_NOT_SET
    return f"{summary.age} ({format_date(summary.birth_date)})"


def _height(summary: ProfileSummary) -> str:
    return f"{summary.height_cm} см" if summary.height_cm else ru.PROFILE_NOT_SET


def _goal(summary: ProfileSummary) -> str:
    return ru.GOAL_LABELS[summary.goal] if summary.goal else ru.PROFILE_NOT_SET


def _experience(summary: ProfileSummary) -> str:
    if summary.experience_level is None:
        return ru.PROFILE_NOT_SET
    return ru.EXPERIENCE_LABELS[summary.experience_level]


def exercise_video_url(exercise: Exercise) -> str:
    """A curated link when we have one, otherwise a YouTube search.

    The seeded catalogue ships without video URLs on purpose: an invented
    video id is worse than no link at all. A search always resolves to
    something relevant, and a real URL replaces it the moment one is added.
    """
    if exercise.video_url:
        return exercise.video_url
    query = quote_plus(f"{exercise.name_ru} техника выполнения")
    return f"https://www.youtube.com/results?search_query={query}"


def render_exercise_card(exercise: Exercise) -> str:
    muscles = exercise.primary_muscle_group.name_ru
    secondary = [group.name_ru for group in exercise.secondary_muscle_groups]
    if secondary:
        muscles += " + " + ", ".join(secondary)

    meta = ru.EXERCISE_META.format(
        muscles=muscles,
        equipment=ru.EQUIPMENT_LABELS[Equipment(exercise.equipment)],
        type=ru.EXERCISE_TYPE_LABELS[ExerciseType(exercise.exercise_type)],
    )
    kind = ru.EXERCISE_COMPOUND if exercise.is_compound else ru.EXERCISE_ISOLATION
    card = ru.EXERCISE_CARD.format(name=exercise.name_ru, meta=f"{meta} · {kind}")

    if exercise.technique_tips:
        card += ru.EXERCISE_TIPS.format(tips=exercise.technique_tips.strip())
    if exercise.common_mistakes:
        card += ru.EXERCISE_MISTAKES.format(mistakes=exercise.common_mistakes.strip())
    if not exercise.is_system:
        card += ru.EXERCISE_OWN_BADGE

    return card

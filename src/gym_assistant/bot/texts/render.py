"""Turning domain objects into the text a user actually reads."""

from __future__ import annotations

import html
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import quote_plus

from gym_assistant.bot.texts import ru
from gym_assistant.domain import body
from gym_assistant.domain.models import (
    BodyEstimate,
    Equipment,
    Exercise,
    ExerciseType,
    Sex,
    WorkoutSet,
)
from gym_assistant.domain.services import (
    ExerciseHistory,
    ProfileSummary,
    WeighIn,
    WorkoutSummary,
)


def escape(text: str) -> str:
    """Text a person or a model wrote, made safe for an HTML message.

    The bot speaks HTML, so a "<" in an exercise name or a search query is a
    tag to Telegram, and a broken tag makes it refuse the whole message.
    Everything that did not come from this codebase goes through here.
    """
    return html.escape(text, quote=False)


def format_decimal(value: Decimal) -> str:
    """``Decimal('82.50')`` -> ``82.5``; ``Decimal('80.00')`` -> ``80``.

    Trailing zeros are noise on a screen, and ``normalize()`` cannot be used
    because it renders whole numbers in scientific notation.
    """
    text = f"{value:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_weight(kg: Decimal) -> str:
    """A stored weight, with its unit.

    The bot shows kilograms and only kilograms; pounds exist as a way to type
    a number, never as a way to read one. The unit rides along with the number
    from here rather than being spelled out in twenty templates - twenty
    places to keep in step, one of which drifts.
    """
    return f"{format_decimal(kg)} кг"


def weight_error(reason: str) -> str:
    """The parser's ``reason`` as a sentence."""
    return ru.ERROR_WEIGHT_FORMAT if reason == "format" else ru.ERROR_WEIGHT_RANGE


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
        lines.append(f"\nВес: <b>{format_weight(summary.weight_kg)}</b> ({when})")

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
        parts.append(f"вес {format_weight(summary.weight_kg)}")
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
    card = ru.EXERCISE_CARD.format(name=escape(exercise.name_ru), meta=f"{meta} · {kind}")

    if exercise.technique_tips:
        card += ru.EXERCISE_TIPS.format(tips=escape(exercise.technique_tips.strip()))
    if exercise.common_mistakes:
        card += ru.EXERCISE_MISTAKES.format(mistakes=escape(exercise.common_mistakes.strip()))
    if not exercise.is_system:
        card += ru.EXERCISE_OWN_BADGE

    return card


def format_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} мин"
    hours, rest = divmod(minutes, 60)
    return f"{hours} ч {rest} мин" if rest else f"{hours} ч"


def format_seconds(seconds: int) -> str:
    minutes, rest = divmod(seconds, 60)
    return f"{minutes}:{rest:02d}" if minutes else f"{rest} с"


def render_set_value(item: WorkoutSet) -> str:
    """One set as a person reads it, not as the schema stores it."""
    if item.weight_kg is not None and item.reps is not None:
        value = f"{format_weight(item.weight_kg)} × {item.reps}"
    elif item.reps is not None:
        value = f"{item.reps} повт."
    elif item.duration_sec is not None:
        value = format_seconds(item.duration_sec)
    elif item.distance_m is not None:
        value = f"{item.distance_m} м"
    else:  # pragma: no cover - the database forbids this row
        value = "—"

    if item.rpe is not None:
        value += f" @{format_decimal(item.rpe)}"
    return value


def render_set_lines(sets: Sequence[WorkoutSet]) -> str:
    lines = []
    for index, item in enumerate(sets, start=1):
        template = ru.WORKOUT_SET_LINE_WARMUP if item.is_warmup else ru.WORKOUT_SET_LINE
        lines.append(template.format(index=index, value=render_set_value(item)))
    return "\n".join(lines)


def render_workout_panel(
    *,
    duration_min: int,
    sets: Sequence[WorkoutSet],
    tonnage: Decimal,
    by_exercise: Sequence[tuple[Exercise, list[WorkoutSet]]],
) -> str:
    if not sets:
        body = ru.WORKOUT_PANEL_EMPTY
    else:
        body = "\n".join(
            ru.WORKOUT_PANEL_LINE.format(
                name=escape(exercise.name_ru),
                sets=", ".join(render_set_value(item) for item in items),
            )
            for exercise, items in by_exercise
        )
    return ru.WORKOUT_PANEL.format(
        duration=format_duration(duration_min),
        sets=len(sets),
        tonnage=format_weight(tonnage),
        exercises=body,
    )


def render_exercise_panel(
    history: ExerciseHistory,
    today: Sequence[WorkoutSet],
    *,
    weight: Decimal | None,
    reps: int,
    lbs_input: bool = False,
) -> str:
    if history.is_first_time:
        text = ru.WORKOUT_EXERCISE_FIRST_TIME.format(name=escape(history.exercise.name_ru))
    else:
        text = ru.WORKOUT_EXERCISE_HISTORY.format(
            name=escape(history.exercise.name_ru),
            when=format_when(history.last_performed_at) if history.last_performed_at else "",
            sets=render_set_lines(history.last_sets),
        )
        if history.best_estimate is not None:
            text += ru.WORKOUT_EXERCISE_BEST.format(best=format_weight(history.best_estimate))

    if today:
        text += ru.WORKOUT_EXERCISE_TODAY.format(sets=render_set_lines(today))

    if weight is not None:
        text += ru.WORKOUT_ENTRY.format(weight=format_weight(weight), reps=reps)
    else:
        text += ru.WORKOUT_ENTRY_BODYWEIGHT.format(reps=reps)
    if lbs_input:
        text += ru.WORKOUT_LBS_HINT
    return text


def render_workout_summary(summary: WorkoutSummary) -> str:
    if summary.is_empty:
        return ru.WORKOUT_FINISHED_EMPTY

    body = "\n".join(
        ru.WORKOUT_PANEL_LINE.format(
            name=escape(exercise.name_ru),
            sets=", ".join(render_set_value(item) for item in items),
        )
        for exercise, items in summary.by_exercise
    )
    text = ru.WORKOUT_FINISHED.format(
        duration=format_duration(summary.duration_min),
        sets=summary.total_sets,
        working=summary.working_sets,
        tonnage=format_weight(summary.tonnage),
        exercises=body,
    )
    if summary.records:
        text += ru.WORKOUT_FINISHED_RECORDS.format(
            records="\n".join(
                ru.WORKOUT_RECORD_LINE.format(
                    name=escape(exercise.name_ru), best=format_weight(best)
                )
                for exercise, best in summary.records
            )
        )
    return text


def render_body_estimate(
    estimate: BodyEstimate,
    *,
    weigh_in: WeighIn | None,
    height_cm: int | None,
    sex: Sex | None,
    previous: BodyEstimate | None,
    unusable: bool = False,
) -> str:
    """One estimate as a message: the band, the kilograms, and how far to trust them.

    The observations and limits are the model's words and go out escaped:
    they land in an HTML message, and a stray "<" from the model would make
    Telegram refuse the whole reply.
    """
    band = body.Band(estimate.bf_low, estimate.bf_likely, estimate.bf_high)
    parts = [
        ru.BODY_HEADER.format(date=format_date(estimate.measured_at.date())),
        ru.BODY_FAT.format(
            low=format_decimal(band.low),
            likely=format_decimal(band.likely),
            high=format_decimal(band.high),
        ),
    ]
    if unusable:
        parts.append(ru.BODY_UNUSABLE)

    if weigh_in is None:
        parts.append(ru.BODY_NO_WEIGHT)
    elif not weigh_in.fresh:
        parts.append(
            ru.BODY_STALE_WEIGHT.format(
                weight=format_weight(weigh_in.weight_kg),
                when=format_when(weigh_in.measured_at),
            )
        )
    else:
        mass = body.composition(band, weigh_in.weight_kg, height_cm)
        parts.append(
            ru.BODY_MASSES.format(
                weight=format_weight(weigh_in.weight_kg),
                when=format_when(weigh_in.measured_at),
                fat_low=format_decimal(mass.fat_kg.low),
                fat_high=format_decimal(mass.fat_kg.high),
                lean_low=format_decimal(mass.lean_kg.low),
                lean_high=format_decimal(mass.lean_kg.high),
            )
        )
        if mass.ffmi is not None and mass.ffmi_normalized is not None:
            parts.append(
                ru.BODY_FFMI.format(
                    ffmi=format_decimal(mass.ffmi),
                    normalized=format_decimal(mass.ffmi_normalized),
                )
            )
        else:
            parts.append(ru.BODY_NO_HEIGHT)

    if estimate.observations:
        parts.append(
            ru.BODY_SEEN.format(
                observations=escape("; ".join(str(line) for line in estimate.observations))
            )
        )
    if estimate.limits:
        parts.append(ru.BODY_LIMITS.format(limits=escape(estimate.limits)))

    if previous is not None:
        before = body.Band(previous.bf_low, previous.bf_likely, previous.bf_high)
        template = {
            body.Trend.SAME: ru.BODY_TREND_SAME,
            body.Trend.DOWN: ru.BODY_TREND_DOWN,
            body.Trend.UP: ru.BODY_TREND_UP,
        }[body.trend(before, band)]
        parts.append(
            template.format(
                date=format_date(previous.measured_at.date()),
                previous=format_decimal(previous.bf_likely),
                noise=format_decimal(body.NOISE_PP),
            )
        )

    if body.is_low(band, sex):
        parts.append(ru.BODY_LOW_FAT)

    parts.append(ru.BODY_ACCURACY)
    return "\n\n".join(parts)

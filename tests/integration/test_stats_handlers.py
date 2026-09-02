"""The reports, driven through the real dispatcher.

Charts cannot be checked pixel by pixel from here, so these assert what a
user would notice: that a picture arrives at all, that the "not enough data"
path says so instead of sending a blank one, and that the period actually
changes what is counted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.texts import ru
from gym_assistant.config import Settings
from gym_assistant.domain.models import Exercise
from gym_assistant.domain.parsing import parse_set_entry
from gym_assistant.domain.services import (
    ExerciseService,
    MeasurementService,
    ProfileService,
    WorkoutService,
)
from tests.integration.bot_harness import BotHarness, build_harness

TELEGRAM_ID = 777


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    settings = Settings(bot_token="42:test-token-not-real")  # type: ignore[call-arg]
    return build_harness(session, settings)


async def _seed_history(session: AsyncSession, *, weeks: int = 6) -> None:
    """A plausible training history: two sessions a week, slow progression."""
    profile = ProfileService(session)
    exercises = ExerciseService(session)
    workouts = WorkoutService(session)

    user = await profile.get_or_create_user(TELEGRAM_ID)
    bench = (await exercises.search("бенч", user_id=user.id))[0]
    squat = (await exercises.search("присед", user_id=user.id))[0]

    start = datetime.now(UTC) - timedelta(weeks=weeks)
    for week in range(weeks):
        for day, (exercise, base) in enumerate(((bench, 70), (squat, 100))):
            when = start + timedelta(weeks=week, days=day * 3)
            await workouts.start(user.id, now=when)
            await workouts.log(user.id, exercise, parse_set_entry("40х10 разминка"), now=when)
            await workouts.log(
                user.id,
                exercise,
                parse_set_entry(f"{base + week * 2.5}х8х3"),
                now=when + timedelta(minutes=10),
            )
            await workouts.finish(user.id, now=when + timedelta(hours=1))


async def _seed_weight(session: AsyncSession, *, points: int = 10) -> None:
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)
    service = MeasurementService(session)
    start = datetime.now(UTC) - timedelta(days=points * 3)
    for index in range(points):
        await service.record(
            user.id,
            weight_kg=Decimal(84) - Decimal(index) / 10,
            measured_at=start + timedelta(days=index * 3),
        )


async def _seed_many_exercises(session: AsyncSession, *, count: int = 11) -> None:
    """More exercises than fit on one page of the picker or the records list."""
    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)
    picked = list(
        await session.scalars(
            select(Exercise)
            .where(Exercise.owner_user_id.is_(None))
            .order_by(Exercise.id)
            .limit(count)
        )
    )
    workouts = WorkoutService(session)
    when = datetime.now(UTC) - timedelta(days=2)
    await workouts.start(user.id, now=when)
    for index, exercise in enumerate(picked):
        await workouts.log(user.id, exercise, parse_set_entry(f"{50 + index}х5"), now=when)
    await workouts.finish(user.id, now=when + timedelta(hours=1))


def _exercise_labels(bot: BotHarness) -> set[str]:
    """Everything on the keyboard that is not navigation."""
    markup = bot.session.last_markup
    assert markup is not None
    chrome = {ru.BTN_BACK, ru.BTN_PREV_PAGE, ru.BTN_NEXT_PAGE, " "}
    return {
        button.text
        for row in markup.inline_keyboard
        for button in row
        if button.text not in chrome and "/" not in button.text
    }


def _photos_sent(bot: BotHarness) -> int:
    return sum(1 for call in bot.session.calls if type(call).__name__ == "SendPhoto")


def _documents_sent(bot: BotHarness) -> int:
    return sum(1 for call in bot.session.calls if type(call).__name__ == "SendDocument")


# --- the menu -------------------------------------------------------------


async def test_stats_menu_opens(bot: BotHarness) -> None:
    await bot.send("/stats")

    assert "Статистика" in bot.session.last_text
    assert bot.session.button_with("Итоги")
    assert bot.session.button_with("Период")


async def test_menu_counts_the_period(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session, weeks=4)

    await bot.send("/stats")

    # Eight sessions over four weeks, both inside the default three months.
    assert "8" in bot.session.last_text


async def test_menu_on_an_empty_history(bot: BotHarness) -> None:
    await bot.send("/stats")

    assert "Тренировок за период: <b>0</b>" in bot.session.last_text


# --- charts ---------------------------------------------------------------


async def test_tonnage_chart_is_sent(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session)
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Тоннаж")

    assert _photos_sent(bot) == 1


async def test_volume_chart_is_sent(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session)
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Объём")

    assert _photos_sent(bot) == 1


async def test_frequency_chart_is_sent(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session)
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Частота")

    assert _photos_sent(bot) == 1


async def test_body_weight_chart_is_sent(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_weight(session)
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Вес тела")

    assert _photos_sent(bot) == 1


async def test_exercise_progress_chart(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session)
    await bot.send("/stats")

    await bot.tap_button("Динамика упражнения")
    assert bot.session.button_with("Жим штанги лёжа")

    bot.session.clear()
    await bot.tap_button("Жим штанги лёжа")
    assert _photos_sent(bot) == 1


# --- not enough data ------------------------------------------------------


@pytest.mark.parametrize("button", ["Тоннаж", "Объём", "Частота", "Вес тела"])
async def test_reports_say_so_instead_of_sending_a_blank_chart(
    bot: BotHarness, button: str
) -> None:
    """A blank chart is a worse answer than a sentence."""
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button(button)

    assert _photos_sent(bot) == 0
    assert "мало" in bot.session.last_text or "нет" in bot.session.last_text


async def test_progress_without_any_history(bot: BotHarness) -> None:
    await bot.send("/stats")

    await bot.tap_button("Динамика упражнения")

    assert "нечего показывать" in bot.session.last_text


async def test_a_single_session_still_draws_something(
    bot: BotHarness, session: AsyncSession
) -> None:
    """The complaint from iteration 4: one session must not be a blank refusal."""
    await _seed_history(session, weeks=1)
    await bot.send("/stats")
    await bot.tap_button("Динамика упражнения")

    bot.session.clear()
    await bot.tap_button("Жим штанги лёжа")

    assert _photos_sent(bot) == 1


async def test_a_single_point_is_labelled_as_one(bot: BotHarness, session: AsyncSession) -> None:
    """Drawn, but captioned so a dot is not mistaken for a trend."""
    await _seed_history(session, weeks=1)
    await bot.send("/stats")
    await bot.tap_button("Динамика упражнения")

    bot.session.clear()
    await bot.tap_button("Жим штанги лёжа")

    photo = next(call for call in bot.session.calls if type(call).__name__ == "SendPhoto")
    assert "одна точка" in (photo.caption or "")


# --- periods --------------------------------------------------------------


async def test_period_can_be_changed(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session, weeks=4)
    await bot.send("/stats")

    await bot.tap_button("Период")
    assert bot.session.button_with("месяц")

    await bot.tap_button("✓")  # the current one, marked with a tick
    assert "Статистика" in bot.session.last_text


async def test_a_short_period_excludes_older_sessions(
    bot: BotHarness, session: AsyncSession
) -> None:
    """The period must actually filter, not just relabel the header."""
    await _seed_history(session, weeks=10)

    await bot.send("/stats")
    await bot.tap_button("Период")
    bot.session.clear()
    await bot.tap_button("месяц")

    # Ten weeks of history, but only the last month may be counted.
    assert "20" not in bot.session.last_text


# --- records and summary --------------------------------------------------


async def test_records_report(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session)
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Личные рекорды")

    text = bot.session.last_text
    assert "Личные рекорды" in text
    assert "Приседания со штангой" in text


async def test_records_without_history(bot: BotHarness) -> None:
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Личные рекорды")

    assert "Рекордов пока нет" in bot.session.last_text


async def test_summary_report(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session, weeks=2)
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Итоги")

    text = bot.session.last_text
    assert "Итоги" in text
    assert "Тоннаж" in text


async def test_summary_counts_warmups_apart_from_working_sets(
    bot: BotHarness, session: AsyncSession
) -> None:
    await _seed_history(session, weeks=1)
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Итоги")

    # Two sessions, each one warm-up plus three working sets.
    assert "8" in bot.session.last_text
    assert "6" in bot.session.last_text


# --- export ---------------------------------------------------------------


async def test_export_sends_both_files(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session, weeks=2)
    await _seed_weight(session, points=3)

    bot.session.clear()
    await bot.send("/export")

    assert _documents_sent(bot) == 2


async def test_export_with_nothing_to_export(bot: BotHarness) -> None:
    await bot.send("/export")

    assert "нечего" in bot.session.last_text
    assert _documents_sent(bot) == 0


async def test_export_is_reachable_from_the_menu(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session, weeks=1)
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Выгрузить")

    assert _documents_sent(bot) >= 1


# --- profile records ------------------------------------------------------


async def test_profile_shows_maxima(bot: BotHarness, session: AsyncSession) -> None:
    """Asked for during the iteration 3 review."""
    await _seed_history(session, weeks=2)

    bot.session.clear()
    await bot.send("/profile")

    assert "Максимумы" in bot.session.last_text


async def test_profile_without_history_has_no_maxima_block(bot: BotHarness) -> None:
    await bot.send("/profile")

    assert "Максимумы" not in bot.session.last_text


# --- pagination -----------------------------------------------------------
#
# Reported in the iteration 4 review: both of these lists grow with every
# exercise ever trained, and neither of them paged.


async def test_exercise_picker_pages(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_many_exercises(session)
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Динамика упражнения")

    assert bot.session.button_with("1/2")
    assert bot.session.button_with("›")


async def test_exercise_picker_second_page_has_other_exercises(
    bot: BotHarness, session: AsyncSession
) -> None:
    """The eleventh exercise used to be unreachable, silently."""
    await _seed_many_exercises(session)
    await bot.send("/stats")
    await bot.tap_button("Динамика упражнения")
    first = _exercise_labels(bot)

    await bot.tap_button("›")
    second = _exercise_labels(bot)

    assert bot.session.button_with("2/2")
    assert second and not (first & second)


async def test_records_page(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_many_exercises(session)
    await bot.send("/stats")

    bot.session.clear()
    await bot.tap_button("Личные рекорды")

    assert "1/2" in bot.session.last_text
    await bot.tap_button("›")
    assert "2/2" in bot.session.last_text


async def test_records_fit_within_telegram_limit(bot: BotHarness, session: AsyncSession) -> None:
    """A message over 4096 characters is refused outright, not truncated."""
    await _seed_many_exercises(session, count=30)
    await bot.send("/stats")
    await bot.tap_button("Личные рекорды")

    assert len(bot.session.last_text) < 4096


# --- the period keeps the exercise ----------------------------------------


async def test_changing_the_period_keeps_the_exercise(
    bot: BotHarness, session: AsyncSession
) -> None:
    """Reported in the review: it asked which exercise all over again."""
    await _seed_history(session, weeks=6)
    await bot.send("/stats")
    await bot.tap_button("Динамика упражнения")
    await bot.tap_button("Жим штанги лёжа")

    await bot.tap_button("Период")
    bot.session.clear()
    await bot.tap_button("месяц")

    assert _photos_sent(bot) == 1


async def test_the_picker_is_still_one_tap_away(bot: BotHarness, session: AsyncSession) -> None:
    await _seed_history(session, weeks=6)
    await bot.send("/stats")
    await bot.tap_button("Динамика упражнения")

    bot.session.clear()
    await bot.tap_button("Жим штанги лёжа")
    await bot.tap_button("Другое упражнение")

    assert "По какому упражнению" in bot.session.last_text


# --- the session behind the chart -----------------------------------------


async def test_last_session_with_the_exercise(bot: BotHarness, session: AsyncSession) -> None:
    """Asked for in the review: show the sets behind the last point."""
    await _seed_history(session, weeks=2)
    await bot.send("/stats")
    await bot.tap_button("Динамика упражнения")
    await bot.tap_button("Жим штанги лёжа")

    bot.session.clear()
    await bot.tap_button("Последняя тренировка")

    text = bot.session.last_text
    assert "Жим штанги лёжа" in text
    assert "Приседания со штангой" not in text

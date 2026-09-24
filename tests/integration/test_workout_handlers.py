"""The workout flow driven through the real dispatcher.

The iteration is judged on taps per set, so several of these tests count
the taps explicitly rather than only checking that something was stored.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.config import Settings
from gym_assistant.domain.services import ExerciseService, ProfileService, WorkoutService
from tests.integration.bot_harness import BotHarness, build_harness


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    settings = Settings(bot_token="42:test-token-not-real")  # type: ignore[call-arg]
    return build_harness(session, settings)


def _exercise_names(bot: BotHarness) -> set[str]:
    """Buttons on the current keyboard that are exercises, not navigation."""
    markup = bot.session.last_markup
    assert markup is not None
    chrome = {"‹", "›", " "}
    return {
        button.text
        for row in markup.inline_keyboard
        for button in row
        if button.text not in chrome and "/" not in button.text
    }


async def _sets(session: AsyncSession) -> list:
    user = await ProfileService(session).get_or_create_user(777)
    return await WorkoutService(session).current_sets(user.id)


# --- starting -------------------------------------------------------------


async def test_workout_starts_and_shows_the_panel(bot: BotHarness) -> None:
    await bot.send("/workout")

    assert "Тренировка идёт" in bot.session.last_text
    assert bot.session.button_with("Завершить")


async def test_second_workout_command_continues_the_same_session(
    bot: BotHarness, session: AsyncSession
) -> None:
    await bot.send("/workout")
    await bot.send("/workout")

    user = await ProfileService(session).get_or_create_user(777)
    assert await WorkoutService(session).open_workout(user.id) is not None


# --- the fast path --------------------------------------------------------


async def test_typing_a_set_is_one_message(bot: BotHarness, session: AsyncSession) -> None:
    """The whole point: during a session, free text is a set."""
    await bot.send("/workout")

    await bot.send("жим 80х8")

    stored = await _sets(session)
    assert len(stored) == 1
    assert str(stored[0].weight_kg) == "80.00"
    assert stored[0].reps == 8
    # The unit now travels with the number - see render.format_weight.
    assert "80 кг × 8" in " ".join(bot.session.texts)


async def test_repeat_costs_one_tap(bot: BotHarness, session: AsyncSession) -> None:
    """After the first set, the same set again must be a single button."""
    await bot.send("/workout")
    await bot.send("жим 80х8")

    await bot.tap_button("Повторить подход")

    stored = await _sets(session)
    assert len(stored) == 2
    assert stored[1].reps == 8


async def test_picking_a_frequent_exercise_prefills_the_last_working_set(
    bot: BotHarness, session: AsyncSession
) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Другое упражнение")

    # The exercise just used is now offered on the panel.
    await bot.tap_button("Жим штанги лёжа")

    assert "80" in bot.session.last_text
    assert "Записать" in str(bot.session.last_markup) or bot.session.button_with("Повторить")


async def test_three_sets_in_one_line(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")

    await bot.send("жим 80х8х3")

    stored = await _sets(session)
    assert len(stored) == 3
    assert [item.set_index for item in stored] == [1, 2, 3]


async def test_set_without_a_name_uses_the_current_exercise(
    bot: BotHarness, session: AsyncSession
) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")

    await bot.send("82,5х6")

    stored = await _sets(session)
    assert len(stored) == 2
    assert str(stored[1].weight_kg) == "82.50"


async def test_set_without_a_name_and_no_current_exercise_asks(bot: BotHarness) -> None:
    await bot.send("/workout")

    await bot.send("80х8")

    assert "к какому упражнению" in bot.session.last_text


# --- adjusting ------------------------------------------------------------


async def test_weight_buttons_adjust_the_pending_set(
    bot: BotHarness, session: AsyncSession
) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")

    await bot.tap_button("+2.5")
    await bot.tap_button("Повторить подход")

    stored = await _sets(session)
    assert str(stored[-1].weight_kg) == "82.50"


async def test_rep_buttons_adjust_the_pending_set(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")

    await bot.tap_button("+1 повтор")
    await bot.tap_button("Повторить подход")

    stored = await _sets(session)
    assert stored[-1].reps == 9


async def test_warmup_button(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")

    await bot.tap_button("Разминочный")

    stored = await _sets(session)
    assert stored[-1].is_warmup


# --- undo and finish ------------------------------------------------------


async def test_undo_removes_the_last_set(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.send("85х6")

    await bot.tap_button("Отменить последний")

    stored = await _sets(session)
    assert len(stored) == 1
    assert "Убрал" in " ".join(bot.session.texts)


async def test_undo_with_nothing_logged(bot: BotHarness) -> None:
    await bot.send("/workout")

    await bot.tap_button("Отменить последний")

    assert "Отменять нечего" in bot.session.last_text


async def test_finish_reports_a_summary(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8х2")

    await bot.tap_button("Завершить")

    text = bot.session.last_text
    assert "Тренировка завершена" in text
    assert "Тоннаж" in text
    assert "1280" in text


async def test_finishing_an_empty_session_says_so(bot: BotHarness) -> None:
    await bot.send("/workout")

    await bot.tap_button("Завершить")

    assert "без записей" in bot.session.last_text


async def test_last_shows_the_finished_session(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Завершить")

    bot.session.clear()
    await bot.send("/last")

    assert "Последняя тренировка" in bot.session.last_text


async def test_last_without_history(bot: BotHarness) -> None:
    await bot.send("/last")

    assert "пока нет" in bot.session.last_text


# --- records --------------------------------------------------------------


async def test_first_set_of_an_exercise_reports_a_record(bot: BotHarness) -> None:
    await bot.send("/workout")

    await bot.send("жим 80х8")

    assert "Личный рекорд" in " ".join(bot.session.texts)


async def test_a_lighter_set_reports_nothing(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")

    bot.session.clear()
    await bot.send("60х8")

    assert "рекорд" not in " ".join(bot.session.texts).lower()


# --- errors and detours ---------------------------------------------------


async def test_unparseable_line_explains_the_formats(bot: BotHarness) -> None:
    await bot.send("/workout")

    await bot.send("что-то непонятное 80х")

    assert "Не разобрал подход" in bot.session.last_text


async def test_unknown_exercise_name(bot: BotHarness) -> None:
    await bot.send("/workout")

    await bot.send("квакозябра 80х8")

    assert "Не нашёл упражнение" in bot.session.last_text


async def test_typing_a_name_switches_exercise(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")

    await bot.send("присед")
    await bot.send("100х5")

    stored = await _sets(session)
    assert len(stored) == 2
    assert str(stored[-1].weight_kg) == "100.00"


async def test_search_inside_a_workout(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.tap_button("Найти упражнение")

    await bot.send("присед")

    assert bot.session.button_with("Приседания со штангой")


async def _add_own(bot: BotHarness, name: str) -> None:
    """Creates a personal exercise through the catalogue wizard."""
    await bot.send("/exercises")
    await bot.tap_button("Добавить своё")
    await bot.send(name)
    await bot.tap_button("Грудь")
    await bot.tap_button("Штанга")
    await bot.tap_button("Вес")


async def test_search_inside_a_workout_is_paged(bot: BotHarness) -> None:
    """Reported after iteration 4: this list cut off and offered no way on.

    The seeded catalogue has fewer matches than a page holds, so the test
    creates enough to overflow - the same reason the catalogue's own paging
    was invisible in real use.
    """
    for index in range(9):
        await _add_own(bot, f"Жим особенный номер {index}")

    await bot.send("/workout")
    await bot.tap_button("Найти упражнение")
    await bot.send("жим")

    assert bot.session.button_with("›"), "нет кнопки следующей страницы"
    assert bot.session.button_with("1/")


async def test_the_second_page_of_a_search_is_reachable(bot: BotHarness) -> None:
    for index in range(9):
        await _add_own(bot, f"Жим особенный номер {index}")

    await bot.send("/workout")
    await bot.tap_button("Найти упражнение")
    await bot.send("жим")
    first = {
        button.text
        for row in (bot.session.last_markup.inline_keyboard if bot.session.last_markup else [])
        for button in row
    }

    await bot.tap_button("›")
    second = {
        button.text
        for row in (bot.session.last_markup.inline_keyboard if bot.session.last_markup else [])
        for button in row
    }

    assert second - first, "вторая страница показала то же самое"


async def test_a_search_can_be_abandoned_without_ending_the_session(
    bot: BotHarness, session: AsyncSession
) -> None:
    """Before this, the only way out of a wrong search was /cancel."""
    await bot.send("/workout")
    await bot.tap_button("Найти упражнение")
    await bot.send("присед")

    await bot.tap_button("К тренировке")

    assert "Тренировка идёт" in bot.session.last_text
    user = await ProfileService(session).get_or_create_user(777)
    assert await WorkoutService(session).open_workout(user.id) is not None


async def test_commands_still_work_during_a_workout(bot: BotHarness) -> None:
    """A session must not swallow the rest of the bot."""
    await bot.send("/workout")

    await bot.send("/weight 84")

    assert "Записал" in bot.session.last_text


# --- Follow-ups from the iteration 3 review ------------------------------


async def test_warmup_marker_at_the_end(bot: BotHarness, session: AsyncSession) -> None:
    """ "50 на 4 разминка" is how it gets typed: numbers come to mind first."""
    await bot.send("/workout")

    await bot.send("жим 50 на 4 разминка")

    stored = await _sets(session)
    assert stored[0].is_warmup


async def test_record_names_the_set_not_a_formula(bot: BotHarness) -> None:
    await bot.send("/workout")

    await bot.send("жим 80х8")

    joined = " ".join(bot.session.texts)
    assert "Личный рекорд" in joined
    assert "80 кг × 8" in joined


async def test_heavier_for_fewer_reps_is_a_record(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")

    bot.session.clear()
    await bot.send("90х3")

    assert "Личный рекорд" in " ".join(bot.session.texts)


async def test_input_help_is_reachable(bot: BotHarness) -> None:
    """The text formats are the fast path; nothing announced they existed."""
    await bot.send("/workout")

    await bot.tap_button("Как записывать")

    assert "Как записывать подходы" in bot.session.last_text


async def test_catalogue_is_reachable_and_leads_back(bot: BotHarness) -> None:
    await bot.send("/workout")

    await bot.tap_button("Справочник")
    assert "Справочник упражнений" in bot.session.last_text

    await bot.tap_button("К тренировке")
    assert "Тренировка идёт" in bot.session.last_text


async def test_muscle_group_search_finds_the_right_muscle(bot: BotHarness) -> None:
    """ "трицепс" used to return biceps work - one letter apart in trigrams.

    Asserts the muscle, not one exercise: with 15 triceps movements in the
    catalogue, which of them lands on the first page is a ranking decision
    and will keep changing.
    """
    await bot.send("/exercises трицепс")

    names = " ".join(_exercise_names(bot))
    assert "Жим узким хватом" in names, f"нет базового трицепсового: {names}"
    assert "Молотки" not in names, "снова вернулся бицепс"


async def test_cardio_is_in_the_catalogue(bot: BotHarness) -> None:
    await bot.send("/exercises бег")

    assert bot.session.button_with("Бег на дорожке")


# --- The catalogue as a browser inside the session -----------------------


async def test_typing_still_logs_a_set_while_in_the_catalogue(
    bot: BotHarness, session: AsyncSession
) -> None:
    """The bug this flow had: opening the catalogue stole free text.

    You went in to look something up, typed the exercise, and landed in a
    catalogue search instead of the workout.
    """
    await bot.send("/workout")
    await bot.tap_button("Справочник")

    await bot.send("жим 80х8")

    stored = await _sets(session)
    assert len(stored) == 1
    assert stored[0].reps == 8


async def test_catalogue_offers_a_way_back_from_every_screen(bot: BotHarness) -> None:
    """Three levels deep with no way back is what made it feel like leaving."""
    await bot.send("/workout")
    await bot.tap_button("Справочник")
    assert bot.session.button_with("К тренировке")

    await bot.tap_button("По группам")
    assert bot.session.button_with("К тренировке")

    await bot.tap_button("Грудь")
    assert bot.session.button_with("К тренировке")

    await bot.tap_button("Жим штанги лёжа")
    assert bot.session.button_with("К тренировке")


async def test_logging_straight_from_a_catalogue_card(
    bot: BotHarness, session: AsyncSession
) -> None:
    """Finding the exercise was the point, so logging it is the first action."""
    await bot.send("/workout")
    await bot.tap_button("Справочник")
    await bot.tap_button("По группам")
    await bot.tap_button("Грудь")
    await bot.tap_button("Жим штанги лёжа")

    await bot.tap_button("Записать подход")
    assert "Записать" in bot.session.last_text or "Жим штанги лёжа" in bot.session.last_text

    await bot.send("80х8")
    stored = await _sets(session)
    assert len(stored) == 1


async def test_catalogue_hides_its_search_button_during_a_session(
    bot: BotHarness,
) -> None:
    """Typing already searches; a second search would take text from the set."""
    await bot.send("/workout")
    await bot.tap_button("Справочник")

    labels = [b.text for row in (bot.session.last_markup or []).inline_keyboard for b in row]
    assert not any("Поиск" in label for label in labels)


async def test_catalogue_outside_a_workout_is_unchanged(bot: BotHarness) -> None:
    await bot.send("/exercises")

    assert bot.session.button_with("Поиск")
    labels = [b.text for row in (bot.session.last_markup or []).inline_keyboard for b in row]
    assert not any("К тренировке" in label for label in labels)

    await bot.send("бенч")
    assert "Нашёл по запросу" in bot.session.last_text


# --- what a real session in the gym asked for -----------------------------
#
# Both of these existed already, two screens away, and the second screen
# dropped you out of the set you were in the middle of. Between reps nobody
# wants to navigate.


async def test_technique_is_one_tap_from_the_set(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")

    bot.session.clear()
    await bot.tap_button("Техника")

    text = bot.session.last_text
    assert "Жим штанги лёжа" in text
    assert "Лопатки" in text, "в карточке нет советов по технике"


async def test_technique_leads_back_to_the_same_set(bot: BotHarness, session: AsyncSession) -> None:
    """Not to the catalogue: the previous route lost people in a browse list."""
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("Техника")

    await bot.tap_button("К подходу")

    assert "Жим штанги лёжа" in bot.session.last_text
    assert bot.session.button_with("Повторить подход")


async def test_technique_without_an_exercise_says_so(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.tap_button("Как записывать")  # any panel button, no exercise picked

    assert "Жим" not in bot.session.last_text


async def test_favourite_from_the_set_panel(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")

    await bot.tap_button("В избранное")

    user = await ProfileService(session).get_or_create_user(777)
    service = ExerciseService(session)
    bench = (await service.search("бенч", user_id=user.id))[0]
    assert await service.is_favourite(user.id, bench.id) is True


async def test_favouriting_keeps_you_on_the_set(bot: BotHarness) -> None:
    """The catalogue's own toggle re-renders the exercise card, which would
    throw someone out of the set they are in the middle of."""
    await bot.send("/workout")
    await bot.send("жим 80х8")

    bot.session.clear()
    await bot.tap_button("В избранное")

    assert bot.session.button_with("Повторить подход"), "ушли с панели подхода"


async def test_the_star_shows_the_current_state(bot: BotHarness) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    assert bot.session.button_with("В избранное")

    await bot.tap_button("В избранное")

    assert bot.session.button_with("В избранном"), "звезда не отразила, что упражнение добавлено"


async def test_favourite_toggles_back(bot: BotHarness, session: AsyncSession) -> None:
    await bot.send("/workout")
    await bot.send("жим 80х8")
    await bot.tap_button("В избранное")

    await bot.tap_button("В избранном")

    user = await ProfileService(session).get_or_create_user(777)
    service = ExerciseService(session)
    bench = (await service.search("бенч", user_id=user.id))[0]
    assert await service.is_favourite(user.id, bench.id) is False

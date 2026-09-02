"""End-to-end handler tests for the exercise catalogue.

These drive real updates through the real dispatcher, so they catch wiring
faults that service-level tests cannot see.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.config import Settings
from tests.integration.bot_harness import BotHarness, build_harness


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    settings = Settings(bot_token="42:test-token-not-real")  # type: ignore[call-arg]
    return build_harness(session, settings)


async def test_menu_opens(bot: BotHarness) -> None:
    await bot.send("/exercises")

    assert "Справочник упражнений" in bot.session.last_text
    assert "41" in bot.session.last_text


async def test_inline_search(bot: BotHarness) -> None:
    await bot.send("/exercises бенч")

    assert "Нашёл по запросу" in bot.session.last_text
    assert bot.session.button_with("Жим штанги лёжа")


async def test_search_through_the_menu(bot: BotHarness) -> None:
    await bot.send("/exercises")
    await bot.tap_button("Поиск")
    bot.session.clear()

    await bot.send("приседанья")

    assert "Нашёл по запросу" in bot.session.last_text
    assert bot.session.button_with("Приседания")


async def test_browse_by_muscle_group(bot: BotHarness) -> None:
    await bot.send("/exercises")
    await bot.tap_button("По группам")
    await bot.tap_button("Грудь")

    assert "Грудь" in bot.session.last_text
    assert bot.session.button_with("Жим штанги лёжа")


async def test_open_card_and_toggle_favourite(bot: BotHarness) -> None:
    await bot.send("/exercises бенч")
    await bot.tap_button("Жим штанги лёжа")

    assert "Как делать" in bot.session.last_text
    assert "Частые ошибки" in bot.session.last_text

    await bot.tap_button("В избранное")
    assert bot.session.button_with("Убрать из избранного")


async def test_hide_and_restore(bot: BotHarness) -> None:
    await bot.send("/exercises бенч")
    await bot.tap_button("Жим штанги лёжа")
    await bot.tap_button("Скрыть")

    assert "Скрыл" in bot.session.last_text

    await bot.tap_button("Вернуть")
    assert "Вернул" in bot.session.last_text


# --- Section 07 of the QA card: creating a personal exercise --------------


async def test_create_own_exercise_end_to_end(bot: BotHarness) -> None:
    """The whole wizard: name, muscle group, equipment, type."""
    await bot.send("/exercises")
    await bot.tap_button("Добавить своё")
    assert "Как называется" in bot.session.last_text

    await bot.send("Тяга Т-грифа")
    assert "группа мышц" in bot.session.last_text

    await bot.tap_button("Спина")
    assert "На чём выполняется" in bot.session.last_text

    await bot.tap_button("Штанга")
    assert "записываем в подходе" in bot.session.last_text

    await bot.tap_button("Вес")
    assert "Добавил" in " ".join(bot.session.texts)
    assert "Ваше упражнение" in bot.session.last_text


async def test_created_exercise_is_searchable(bot: BotHarness) -> None:
    await bot.send("/exercises")
    await bot.tap_button("Добавить своё")
    await bot.send("Тяга Т-грифа")
    await bot.tap_button("Спина")
    await bot.tap_button("Штанга")
    await bot.tap_button("Вес")

    bot.session.clear()
    await bot.send("/exercises Т-грифа")

    assert bot.session.button_with("Тяга Т-грифа")


async def test_own_exercise_appears_in_my_exercises(bot: BotHarness) -> None:
    await bot.send("/exercises")
    await bot.tap_button("Добавить своё")
    await bot.send("Тяга Т-грифа")
    await bot.tap_button("Спина")
    await bot.tap_button("Штанга")
    await bot.tap_button("Вес")

    await bot.send("/exercises")
    await bot.tap_button("Мои упражнения")

    assert "Мои упражнения" in bot.session.last_text
    assert bot.session.button_with("Тяга Т-грифа")


async def test_duplicate_name_is_refused(bot: BotHarness) -> None:
    for _ in range(2):
        await bot.send("/exercises")
        await bot.tap_button("Добавить своё")
        await bot.send("Тяга Т-грифа")
        await bot.tap_button("Спина")
        await bot.tap_button("Штанга")
        await bot.tap_button("Вес")

    assert "уже есть" in bot.session.last_text


@pytest.mark.parametrize(
    ("name", "expected"),
    [("ок", "Слишком коротко"), ("я" * 100, "Слишком длинно")],
)
async def test_name_validation(bot: BotHarness, name: str, expected: str) -> None:
    await bot.send("/exercises")
    await bot.tap_button("Добавить своё")

    await bot.send(name)

    assert expected in bot.session.last_text


async def test_cancel_leaves_the_wizard(bot: BotHarness) -> None:
    await bot.send("/exercises")
    await bot.tap_button("Добавить своё")

    await bot.send("/cancel")
    assert "Отменил" in bot.session.last_text

    # The next message must be treated as an ordinary one, not as a name.
    bot.session.clear()
    await bot.send("привет")
    assert "не умею" in bot.session.last_text


# --- Behaviour added after the iteration 2 review -------------------------


async def test_search_stays_armed_between_queries(bot: BotHarness) -> None:
    """Opening the catalogue should not mean retyping the command each time."""
    await bot.send("/exercises")

    await bot.send("бенч")
    assert bot.session.button_with("Жим штанги лёжа")

    bot.session.clear()
    await bot.send("присед")
    assert bot.session.button_with("Приседания со штангой")


async def test_cancel_leaves_search_mode(bot: BotHarness) -> None:
    await bot.send("/exercises")
    await bot.send("/cancel")

    assert "Вышел из поиска" in bot.session.last_text

    bot.session.clear()
    await bot.send("бенч")
    assert "не умею" in bot.session.last_text


async def test_exit_search_button_returns_to_the_menu(bot: BotHarness) -> None:
    await bot.send("/exercises")
    await bot.send("бенч")

    await bot.tap_button("Выйти из поиска")

    assert "Справочник упражнений" in bot.session.last_text


async def test_group_listing_is_paged(bot: BotHarness) -> None:
    """Seeded groups fit one page, so the test creates enough to overflow."""
    for index in range(3):
        await bot.send("/exercises")
        await bot.tap_button("Добавить своё")
        await bot.send(f"Своя тяга номер {index}")
        await bot.tap_button("Спина")
        await bot.tap_button("Штанга")
        await bot.tap_button("Вес")

    await bot.send("/exercises")
    await bot.tap_button("По группам")
    await bot.tap_button("Спина")

    assert bot.session.button_with("1/2"), "page indicator missing"
    await bot.tap_button("›")
    assert bot.session.button_with("2/2")


async def test_main_menu_reaches_every_feature(bot: BotHarness) -> None:
    await bot.send("/menu")
    assert "Что делаем" in bot.session.last_text

    await bot.tap_button("Упражнения")
    assert "Справочник упражнений" in bot.session.last_text

    await bot.send("/menu")
    await bot.tap_button("Профиль")
    assert "Профиль" in bot.session.last_text

    await bot.send("/menu")
    await bot.tap_button("Записать вес")
    assert "вес" in bot.session.last_text.lower()


async def test_menu_works_from_inside_a_wizard(bot: BotHarness) -> None:
    """/menu is the escape hatch, so it must not be swallowed by a state."""
    await bot.send("/exercises")
    await bot.tap_button("Добавить своё")

    await bot.send("/menu")

    assert "Что делаем" in bot.session.last_text

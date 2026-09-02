"""Inline keyboards for the exercise catalogue."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gym_assistant.bot.texts import render, ru
from gym_assistant.domain.models import Equipment, Exercise, ExerciseType, MuscleGroup


class ExMenuCB(CallbackData, prefix="exm"):
    action: str  # search | groups | favourites | own | new | menu


class ExGroupCB(CallbackData, prefix="exg"):
    group_id: int
    page: int = 0


class ExCardCB(CallbackData, prefix="exc"):
    exercise_id: int


class ExFavCB(CallbackData, prefix="exf"):
    exercise_id: int


class ExHideCB(CallbackData, prefix="exh"):
    exercise_id: int


class ExUnhideCB(CallbackData, prefix="exu"):
    exercise_id: int


class ExNewCB(CallbackData, prefix="exn"):
    """One answer in the create-an-exercise wizard."""

    field: str  # muscle_group | equipment | type
    value: str


def menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=ru.BTN_SEARCH, callback_data=ExMenuCB(action="search"))
    builder.button(text=ru.BTN_GROUPS, callback_data=ExMenuCB(action="groups"))
    builder.button(text=ru.BTN_FAVOURITES, callback_data=ExMenuCB(action="favourites"))
    builder.button(text=ru.BTN_OWN, callback_data=ExMenuCB(action="own"))
    builder.button(text=ru.BTN_NEW, callback_data=ExMenuCB(action="new"))
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def groups_keyboard(groups: list[MuscleGroup]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(text=group.name_ru, callback_data=ExGroupCB(group_id=group.id))
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text=ru.BTN_BACK, callback_data=ExMenuCB(action="menu").pack())
    )
    return builder.as_markup()


def exercise_list_keyboard(
    exercises: list[Exercise],
    *,
    back_action: str = "menu",
    pager: tuple[int, int, int] | None = None,
) -> InlineKeyboardMarkup:
    """``pager`` is ``(group_id, page, total_pages)`` when the list is paged."""
    builder = InlineKeyboardBuilder()
    for exercise in exercises:
        label = exercise.name_ru if exercise.is_system else f"🛠 {exercise.name_ru}"
        builder.button(text=label, callback_data=ExCardCB(exercise_id=exercise.id))
    builder.adjust(1)

    if pager is not None:
        group_id, page, total_pages = pager
        if total_pages > 1:
            controls = [
                InlineKeyboardButton(
                    text=ru.BTN_PREV_PAGE,
                    callback_data=ExGroupCB(group_id=group_id, page=page - 1).pack(),
                )
                if page > 0
                # A disabled-looking spacer keeps the row width steady, so the
                # buttons do not jump sideways as you page through.
                else InlineKeyboardButton(text=" ", callback_data=ExMenuCB(action="noop").pack()),
                InlineKeyboardButton(
                    text=ru.PAGE_INDICATOR.format(page=page + 1, total=total_pages),
                    callback_data=ExMenuCB(action="noop").pack(),
                ),
                InlineKeyboardButton(
                    text=ru.BTN_NEXT_PAGE,
                    callback_data=ExGroupCB(group_id=group_id, page=page + 1).pack(),
                )
                if page + 1 < total_pages
                else InlineKeyboardButton(text=" ", callback_data=ExMenuCB(action="noop").pack()),
            ]
            builder.row(*controls)

    builder.row(
        InlineKeyboardButton(text=ru.BTN_BACK, callback_data=ExMenuCB(action=back_action).pack())
    )
    return builder.as_markup()


def search_results_keyboard(exercises: list[Exercise]) -> InlineKeyboardMarkup:
    """Search stays active, so the list offers a way out rather than "back"."""
    builder = InlineKeyboardBuilder()
    for exercise in exercises:
        label = exercise.name_ru if exercise.is_system else f"🛠 {exercise.name_ru}"
        builder.button(text=label, callback_data=ExCardCB(exercise_id=exercise.id))
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text=ru.BTN_EXIT_SEARCH, callback_data=ExMenuCB(action="menu").pack())
    )
    return builder.as_markup()


def exercise_card_keyboard(exercise: Exercise, *, is_favourite: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # A URL button: the video opens directly, the bot proxies nothing.
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_VIDEO if exercise.video_url else ru.BTN_VIDEO_SEARCH,
            url=render.exercise_video_url(exercise),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_FAV_REMOVE if is_favourite else ru.BTN_FAV_ADD,
            callback_data=ExFavCB(exercise_id=exercise.id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_HIDE, callback_data=ExHideCB(exercise_id=exercise.id).pack()
        )
    )
    builder.row(
        InlineKeyboardButton(text=ru.BTN_BACK, callback_data=ExMenuCB(action="menu").pack())
    )
    return builder.as_markup()


def undo_hide_keyboard(exercise_id: int) -> InlineKeyboardMarkup:
    """Hiding takes one tap, so undoing it must take one tap too."""
    builder = InlineKeyboardBuilder()
    builder.button(text=ru.BTN_UNHIDE, callback_data=ExUnhideCB(exercise_id=exercise_id))
    builder.button(text=ru.BTN_TO_CATALOGUE, callback_data=ExMenuCB(action="menu"))
    builder.adjust(1)
    return builder.as_markup()


def new_group_keyboard(groups: list[MuscleGroup]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(
            text=group.name_ru,
            callback_data=ExNewCB(field="muscle_group", value=str(group.id)),
        )
    builder.adjust(2)
    return builder.as_markup()


def new_equipment_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for member, label in ru.EQUIPMENT_LABELS.items():
        builder.button(
            text=label.capitalize(),
            callback_data=ExNewCB(field="equipment", value=member.value),
        )
    builder.adjust(2)
    return builder.as_markup()


def new_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for member, label in ru.EXERCISE_TYPE_LABELS.items():
        builder.button(
            text=label.capitalize(),
            callback_data=ExNewCB(field="type", value=member.value),
        )
    builder.adjust(2)
    return builder.as_markup()


EQUIPMENT_BY_VALUE = {member.value: member for member in Equipment}
TYPE_BY_VALUE = {member.value: member for member in ExerciseType}

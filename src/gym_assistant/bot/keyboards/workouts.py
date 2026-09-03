"""Keyboards for a running workout.

The whole iteration is judged on one number: how many taps a set costs.
Everything here exists to keep that at two or three.
"""

from __future__ import annotations

from decimal import Decimal

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gym_assistant.bot.texts import ru
from gym_assistant.domain.models import Exercise

# Plate maths, not round numbers: 2.5 kg is the smallest pair of plates in
# most gyms, 5 kg the next step up.
WEIGHT_STEPS = (Decimal("-5"), Decimal("-2.5"), Decimal("2.5"), Decimal("5"))


class WorkoutCB(CallbackData, prefix="wo"):
    """Session-level action."""

    action: str  # start | panel | finish | undo | find | help | catalogue


class WorkoutExerciseCB(CallbackData, prefix="woe"):
    exercise_id: int


class SetAdjustCB(CallbackData, prefix="wos"):
    """Nudge the pending set. ``delta`` is a decimal string."""

    field: str  # weight | reps
    delta: str


class SetCommitCB(CallbackData, prefix="woc"):
    warmup: bool = False


class WorkoutSearchPageCB(CallbackData, prefix="wosp"):
    """A page of search results inside a running session."""

    page: int = 0


def search_results_keyboard(
    exercises: list[Exercise], *, page: int = 0, total_pages: int = 1
) -> InlineKeyboardMarkup:
    """Search results inside a session, paged like every other list.

    This one was missed when the catalogue lists were unified: it cut the
    results off at a page and offered no way to the rest, so an exercise that
    ranked ninth simply did not exist as far as the session was concerned.
    """
    builder = InlineKeyboardBuilder()
    for exercise in exercises:
        builder.button(
            text=exercise.name_ru, callback_data=WorkoutExerciseCB(exercise_id=exercise.id)
        )
    builder.adjust(1)

    if total_pages > 1:

        def step(delta: int) -> InlineKeyboardButton:
            target = page + delta
            if 0 <= target < total_pages:
                return InlineKeyboardButton(
                    text=ru.BTN_PREV_PAGE if delta < 0 else ru.BTN_NEXT_PAGE,
                    callback_data=WorkoutSearchPageCB(page=target).pack(),
                )
            return InlineKeyboardButton(text=" ", callback_data=WorkoutCB(action="noop").pack())

        builder.row(
            step(-1),
            InlineKeyboardButton(
                text=ru.PAGE_INDICATOR.format(page=page + 1, total=total_pages),
                callback_data=WorkoutCB(action="noop").pack(),
            ),
            step(1),
        )

    # Without this the only way out of a wrong search was /cancel, which
    # also ends the session.
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_PANEL, callback_data=WorkoutCB(action="panel").pack()
        )
    )
    return builder.as_markup()


def start_keyboard(*, is_open: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=ru.BTN_WORKOUT_CONTINUE if is_open else ru.BTN_WORKOUT_START,
        callback_data=WorkoutCB(action="panel" if is_open else "start"),
    )
    return builder.as_markup()


def panel_keyboard(frequent: list[Exercise]) -> InlineKeyboardMarkup:
    """The session panel: the exercises you actually use, then everything else."""
    builder = InlineKeyboardBuilder()
    for exercise in frequent:
        builder.button(
            text=exercise.name_ru, callback_data=WorkoutExerciseCB(exercise_id=exercise.id)
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_FIND, callback_data=WorkoutCB(action="find").pack()
        ),
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_CATALOGUE, callback_data=WorkoutCB(action="catalogue").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_HELP, callback_data=WorkoutCB(action="help").pack()
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_UNDO, callback_data=WorkoutCB(action="undo").pack()
        ),
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_FINISH, callback_data=WorkoutCB(action="finish").pack()
        ),
    )
    return builder.as_markup()


def set_entry_keyboard(
    *, weight: Decimal | None, reps: int, can_repeat: bool
) -> InlineKeyboardMarkup:
    """Prefilled set with nudges. Committing it is one tap from here."""
    builder = InlineKeyboardBuilder()

    if weight is not None:
        builder.row(
            *[
                InlineKeyboardButton(
                    text=f"{step:+g}",
                    callback_data=SetAdjustCB(field="weight", delta=str(step)).pack(),
                )
                for step in WEIGHT_STEPS
            ]
        )

    builder.row(
        InlineKeyboardButton(
            text="−1 повтор", callback_data=SetAdjustCB(field="reps", delta="-1").pack()
        ),
        InlineKeyboardButton(
            text="+1 повтор", callback_data=SetAdjustCB(field="reps", delta="1").pack()
        ),
    )

    # Once a set of this exercise is on the board, committing the same values
    # again IS "repeat", so the label changes rather than a second button
    # appearing that does exactly the same thing.
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_REPEAT if can_repeat else ru.BTN_WORKOUT_ADD_SET,
            callback_data=SetCommitCB().pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(text=ru.BTN_WARMUP, callback_data=SetCommitCB(warmup=True).pack())
    )
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_OTHER, callback_data=WorkoutCB(action="panel").pack()
        ),
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_UNDO, callback_data=WorkoutCB(action="undo").pack()
        ),
    )
    # This panel is where the user spends the session, so ending it has to be
    # reachable from here - not two taps away via the session panel.
    builder.row(
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_HELP, callback_data=WorkoutCB(action="help").pack()
        ),
        InlineKeyboardButton(
            text=ru.BTN_WORKOUT_FINISH, callback_data=WorkoutCB(action="finish").pack()
        ),
    )
    return builder.as_markup()


def back_to_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=ru.BTN_WORKOUT_PANEL, callback_data=WorkoutCB(action="panel"))
    return builder.as_markup()

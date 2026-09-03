"""Exercise catalogue against a real database, seeded by migration 0003."""

from __future__ import annotations

import pathlib

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import Equipment, ExerciseType
from gym_assistant.domain.services import (
    DuplicateExerciseError,
    ExerciseService,
    ProfileService,
)

# Read from the seed rather than hard-coded: the catalogue is meant to grow.
_SEED = yaml.safe_load(pathlib.Path("seeds/exercises.yaml").read_text(encoding="utf-8"))
SEEDED_GROUPS = len(_SEED["muscle_groups"])
SEEDED_EXERCISES = len(_SEED["exercises"])


async def _user(session: AsyncSession, telegram_id: int) -> int:
    user = await ProfileService(session).get_or_create_user(telegram_id)
    return user.id


async def test_catalogue_is_seeded(session: AsyncSession) -> None:
    user_id = await _user(session, 3001)
    service = ExerciseService(session)

    groups = await service.muscle_groups()
    stats = await service.stats(user_id)

    assert len(groups) == SEEDED_GROUPS
    assert stats.total == SEEDED_EXERCISES
    assert stats.own == 0


async def test_search_by_alias(session: AsyncSession) -> None:
    user_id = await _user(session, 3002)

    found = await ExerciseService(session).search("бенч", user_id=user_id)

    assert [e.slug for e in found] == ["bench_press"]


async def test_exact_alias_outranks_a_substring_match(session: AsyncSession) -> None:
    """Typing "жим" must surface the bench press, not "Жим ногами"."""
    user_id = await _user(session, 3003)

    found = await ExerciseService(session).search("жим", user_id=user_id, limit=5)

    assert found[0].slug == "bench_press"


@pytest.mark.parametrize(
    ("query", "expected_slug"),
    [
        ("приседанья", "squat"),
        ("станавая", "deadlift"),
        ("подтягивния", "pull_up"),
        ("планко", "plank"),
    ],
)
async def test_search_tolerates_typos(
    session: AsyncSession, query: str, expected_slug: str
) -> None:
    user_id = await _user(session, 3004)

    found = await ExerciseService(session).search(query, user_id=user_id, limit=3)

    assert expected_slug in {e.slug for e in found}


@pytest.mark.parametrize("query", ["телефон", "квакозябра", "zzzzz", "   "])
async def test_search_rejects_noise(session: AsyncSession, query: str) -> None:
    """The fuzzy threshold has to hold the line, or search becomes useless."""
    user_id = await _user(session, 3005)

    assert await ExerciseService(session).search(query, user_id=user_id) == []


async def test_group_listing_puts_compound_movements_first(session: AsyncSession) -> None:
    user_id = await _user(session, 3006)
    service = ExerciseService(session)
    chest = next(g for g in await service.muscle_groups() if g.code == "chest")

    exercises = await service.by_muscle_group(chest.id, user_id=user_id)

    compound_flags = [e.is_compound for e in exercises]
    assert compound_flags == sorted(compound_flags, reverse=True)


async def test_secondary_muscles_are_loaded(session: AsyncSession) -> None:
    user_id = await _user(session, 3007)

    found = await ExerciseService(session).search("бенч", user_id=user_id)

    codes = {g.code for g in found[0].secondary_muscle_groups}
    assert codes == {"triceps", "shoulders"}


# --- Personal exercises ---------------------------------------------------


async def test_create_own_exercise(session: AsyncSession) -> None:
    user_id = await _user(session, 3008)
    service = ExerciseService(session)

    created = await service.create_own(
        user_id,
        name="Тяга Т-грифа",
        primary_muscle_group_id=next(
            g.id for g in await service.muscle_groups() if g.code == "back"
        ),
        equipment=Equipment.BARBELL,
        exercise_type=ExerciseType.WEIGHT_REPS,
    )

    assert created.slug == "tyaga-t-grifa"
    assert created.owner_user_id == user_id
    assert not created.is_system
    # The name is registered as an alias, so search finds it straight away.
    found = await service.search("Тяга Т-грифа", user_id=user_id)
    assert created.id in {e.id for e in found}


async def test_own_exercise_is_invisible_to_other_users(session: AsyncSession) -> None:
    """The whole point of owner_user_id: one user's entry stays theirs."""
    mine = await _user(session, 3009)
    theirs = await _user(session, 3010)
    service = ExerciseService(session)
    back = next(g.id for g in await service.muscle_groups() if g.code == "back")

    created = await service.create_own(
        mine,
        name="Секретная тяга",
        primary_muscle_group_id=back,
        equipment=Equipment.BARBELL,
        exercise_type=ExerciseType.WEIGHT_REPS,
    )

    # Asserting on ids rather than on an empty list: "тяга" fuzzy-matches the
    # system deadlift and rows, so the other user's results are not empty -
    # they simply must not contain this exercise.
    assert created.id in {e.id for e in await service.search("Секретная тяга", user_id=mine)}
    assert created.id not in {e.id for e in await service.search("Секретная тяга", user_id=theirs)}
    assert await service.get(created.id, user_id=theirs) is None
    assert (await service.stats(theirs)).own == 0


async def test_duplicate_name_is_refused(session: AsyncSession) -> None:
    user_id = await _user(session, 3011)
    service = ExerciseService(session)
    back = next(g.id for g in await service.muscle_groups() if g.code == "back")

    await service.create_own(
        user_id,
        name="Тяга Т-грифа",
        primary_muscle_group_id=back,
        equipment=Equipment.BARBELL,
        exercise_type=ExerciseType.WEIGHT_REPS,
    )

    with pytest.raises(DuplicateExerciseError):
        await service.create_own(
            user_id,
            name="тяга  т-грифа",  # same slug after normalisation
            primary_muscle_group_id=back,
            equipment=Equipment.DUMBBELL,
            exercise_type=ExerciseType.WEIGHT_REPS,
        )


async def test_a_user_slug_may_match_a_system_one(session: AsyncSession) -> None:
    """COALESCE in the unique index exists precisely for this case."""
    user_id = await _user(session, 3012)
    service = ExerciseService(session)
    chest = next(g.id for g in await service.muscle_groups() if g.code == "chest")

    created = await service.create_own(
        user_id,
        name="Жим штанги лёжа",
        primary_muscle_group_id=chest,
        equipment=Equipment.BARBELL,
        exercise_type=ExerciseType.WEIGHT_REPS,
    )

    assert created.slug == "zhim-shtangi-lezha"
    assert created.owner_user_id == user_id


# --- Preferences ----------------------------------------------------------


async def test_hiding_removes_an_exercise_from_view(session: AsyncSession) -> None:
    user_id = await _user(session, 3013)
    other_id = await _user(session, 3014)
    service = ExerciseService(session)
    bench = (await service.search("бенч", user_id=user_id))[0]

    await service.set_hidden(user_id, bench.id, hidden=True)

    # Asserting absence, not emptiness: with the exact match hidden, the fuzzy
    # fallback offers the nearest thing it can find, which is the point of it.
    assert bench.id not in {e.id for e in await service.search("бенч", user_id=user_id)}
    assert await service.get(bench.id, user_id=user_id) is None
    # Hiding is per user: it must not touch the shared catalogue.
    assert bench.id in {e.id for e in await service.search("бенч", user_id=other_id)}


async def test_hiding_is_reversible(session: AsyncSession) -> None:
    user_id = await _user(session, 3015)
    service = ExerciseService(session)
    bench = (await service.search("бенч", user_id=user_id))[0]

    await service.set_hidden(user_id, bench.id, hidden=True)
    await service.set_hidden(user_id, bench.id, hidden=False)

    assert await service.get(bench.id, user_id=user_id) is not None


async def test_toggle_favourite(session: AsyncSession) -> None:
    user_id = await _user(session, 3016)
    service = ExerciseService(session)
    squat = (await service.search("присед", user_id=user_id))[0]

    assert await service.toggle_favourite(user_id, squat.id) is True
    assert await service.is_favourite(user_id, squat.id) is True
    assert [e.id for e in await service.favourites(user_id)] == [squat.id]

    assert await service.toggle_favourite(user_id, squat.id) is False
    assert await service.favourites(user_id) == []


async def test_is_favourite_does_not_create_a_row(session: AsyncSession) -> None:
    """A read must stay a read: the card renders this on every open."""
    user_id = await _user(session, 3017)
    service = ExerciseService(session)
    plank = (await service.search("планка", user_id=user_id))[0]

    assert await service.is_favourite(user_id, plank.id) is False
    assert await service.favourites(user_id) == []


# --- ranking on a large catalogue ----------------------------------------
#
# All four broke when the catalogue grew from 49 to 167 and none of them
# failed loudly: the search still returned exercises, just not the ones
# anyone wanted. The tie-breaker used to be the length of the name.


async def test_a_staple_outranks_its_variations(session: AsyncSession) -> None:
    """ "Приседания со штангой" must beat "Гакк-приседания"."""
    user_id = await _user(session, 3018)

    found = await ExerciseService(session).search("приседания", user_id=user_id, limit=5)

    assert found[0].slug == "squat"


async def test_a_staple_wins_through_a_typo_too(session: AsyncSession) -> None:
    """The fuzzy path dropped the barbell squat out of the top six entirely."""
    user_id = await _user(session, 3019)

    found = await ExerciseService(session).search("приседанья", user_id=user_id, limit=5)

    assert found[0].slug == "squat"


async def test_a_typo_prefers_the_closest_word_over_a_compound(
    session: AsyncSession,
) -> None:
    """ "планко" used to return "Плавание" first - it is compound, планка is not.

    When the query is already understood, compound-first is the order a
    lifter thinks in. When we are guessing at a typo, the closest text is
    the whole point.
    """
    user_id = await _user(session, 3020)

    found = await ExerciseService(session).search("планко", user_id=user_id, limit=5)

    assert found[0].slug == "plank"


async def test_searching_a_muscle_leads_with_a_staple(session: AsyncSession) -> None:
    """ "трицепс" led with the JM press - an accessory almost nobody does."""
    user_id = await _user(session, 3021)

    found = await ExerciseService(session).search("трицепс", user_id=user_id, limit=3)

    assert found[0].slug == "close_grip_bench_press"


async def test_the_catalogue_overflows_a_page_on_its_own(session: AsyncSession) -> None:
    """The reason paging was invisible: no group ever filled a page."""
    user_id = await _user(session, 3022)
    service = ExerciseService(session)

    groups = {g.name_ru: g.id for g in await service.muscle_groups()}
    for name in ("Спина", "Грудь", "Квадрицепс"):
        total = await service.count_by_muscle_group(groups[name], user_id=user_id)
        assert total > 8, f"{name}: {total} — снова одна страница"

"""Admin commands through the real dispatcher.

The point of most of these is the negative case: an ordinary user must not
be able to hand themselves a subscription, and must not even learn that the
commands exist.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.config import Settings
from gym_assistant.domain.models import Role
from gym_assistant.domain.services import AccessService, ProfileService
from tests.integration.bot_harness import BotHarness, build_harness

TELEGRAM_ID = 777
OTHER_ID = 999


def _settings() -> Settings:
    return Settings(bot_token="42:test-token-not-real")  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def bot(session: AsyncSession) -> BotHarness:
    """An ordinary user."""
    return build_harness(session, _settings())


@pytest_asyncio.fixture
async def admin_bot(session: AsyncSession) -> BotHarness:
    """The owner, as listed in ADMIN_TELEGRAM_IDS."""
    return build_harness(session, _settings(), admin=True)


async def _other_user(session: AsyncSession) -> int:
    user = await ProfileService(session).get_or_create_user(OTHER_ID, username="friend")
    return user.id


async def _role_of(session: AsyncSession, user_id: int) -> Role:
    access = await AccessService(session).get(user_id)
    return Role(access.role) if access else Role.REGULAR_USER


# --- the owner becomes an admin by themselves -----------------------------


async def test_an_owner_is_made_admin_on_first_contact(
    admin_bot: BotHarness, session: AsyncSession
) -> None:
    """The database gets wiped often here; admin rights must come back."""
    await admin_bot.send("/whoami")

    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)
    assert await _role_of(session, user.id) is Role.ADMIN


async def test_an_ordinary_user_stays_ordinary(bot: BotHarness) -> None:
    await bot.send("/whoami")

    assert "обычный пользователь" in bot.session.last_text


# --- the commands are invisible to everyone else --------------------------


async def test_a_normal_user_cannot_grant_themselves_anything(
    bot: BotHarness, session: AsyncSession
) -> None:
    await bot.send(f"/grant {TELEGRAM_ID} admin")

    user = await ProfileService(session).get_or_create_user(TELEGRAM_ID)
    assert await _role_of(session, user.id) is Role.REGULAR_USER


async def test_the_grant_command_does_not_exist_for_a_normal_user(bot: BotHarness) -> None:
    """It must read as an unknown command, not as "you are not allowed"."""
    await bot.send(f"/grant {TELEGRAM_ID} admin")

    assert "администратор" not in bot.session.last_text
    assert "→" not in bot.session.last_text


# --- granting -------------------------------------------------------------


async def test_admin_grants_a_subscription(admin_bot: BotHarness, session: AsyncSession) -> None:
    friend_id = await _other_user(session)

    await admin_bot.send(f"/grant {OTHER_ID} sub 30")

    assert await _role_of(session, friend_id) is Role.SUBSCRIPTION_USER


async def test_a_granted_subscription_carries_the_end_date(
    admin_bot: BotHarness, session: AsyncSession
) -> None:
    friend_id = await _other_user(session)

    await admin_bot.send(f"/grant {OTHER_ID} sub 30")

    access = await AccessService(session).get(friend_id)
    assert access is not None and access.expires_at is not None


async def test_a_grant_without_days_has_no_end_date(
    admin_bot: BotHarness, session: AsyncSession
) -> None:
    friend_id = await _other_user(session)

    await admin_bot.send(f"/grant {OTHER_ID} sub")

    access = await AccessService(session).get(friend_id)
    assert access is not None and access.expires_at is None


async def test_granting_to_an_unknown_person_explains_what_to_do(
    admin_bot: BotHarness,
) -> None:
    """Writing a row for a user that does not exist is a class of bug."""
    await admin_bot.send("/grant 4242424242 sub")

    assert "/start" in admin_bot.session.last_text


async def test_a_bad_role_is_reported(admin_bot: BotHarness) -> None:
    await admin_bot.send(f"/grant {OTHER_ID} superuser")

    assert "superuser" in admin_bot.session.last_text


async def test_a_bad_id_is_reported(admin_bot: BotHarness) -> None:
    await admin_bot.send("/grant вася sub")

    assert "вася" in admin_bot.session.last_text


async def test_negative_days_are_refused(admin_bot: BotHarness, session: AsyncSession) -> None:
    """A subscription granted for -5 days would be expired on arrival."""
    friend_id = await _other_user(session)

    await admin_bot.send(f"/grant {OTHER_ID} sub -5")

    assert await _role_of(session, friend_id) is Role.REGULAR_USER


async def test_grant_without_arguments_shows_how_to_use_it(admin_bot: BotHarness) -> None:
    await admin_bot.send("/grant")

    assert "/grant" in admin_bot.session.last_text


# --- revoking -------------------------------------------------------------


async def test_admin_revokes_a_subscription(admin_bot: BotHarness, session: AsyncSession) -> None:
    friend_id = await _other_user(session)
    await admin_bot.send(f"/grant {OTHER_ID} sub 30")

    await admin_bot.send(f"/revoke {OTHER_ID}")

    assert await _role_of(session, friend_id) is Role.REGULAR_USER


async def test_granting_the_ordinary_role_is_the_same_as_revoking(
    admin_bot: BotHarness, session: AsyncSession
) -> None:
    friend_id = await _other_user(session)
    await admin_bot.send(f"/grant {OTHER_ID} sub 30")

    await admin_bot.send(f"/grant {OTHER_ID} user")

    assert await _role_of(session, friend_id) is Role.REGULAR_USER


# --- listing --------------------------------------------------------------


async def test_users_lists_only_the_people_with_a_grant(
    admin_bot: BotHarness, session: AsyncSession
) -> None:
    await _other_user(session)
    await admin_bot.send(f"/grant {OTHER_ID} sub 30")

    admin_bot.session.clear()
    await admin_bot.send("/users")

    assert "friend" in admin_bot.session.last_text


async def test_users_on_a_fresh_database(admin_bot: BotHarness) -> None:
    """The owner themselves is a grant, so this is never truly empty."""
    await admin_bot.send("/users")

    assert "Выданные доступы" in admin_bot.session.last_text

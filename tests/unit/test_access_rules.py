"""The role rules, without a database.

These are the sentences the whole feature rests on, so they are tested as
pure functions: a subscription that has run out is an ordinary user, an
admin never runs out, and an admin can do everything a subscriber can.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gym_assistant.domain.models import Role, UserAccess, role_at_least
from gym_assistant.domain.services import resolve

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _grant(role: Role, expires_at: datetime | None = None) -> UserAccess:
    return UserAccess(user_id=1, role=role.value, expires_at=expires_at)


# --- ordering -------------------------------------------------------------


def test_roles_are_ordered() -> None:
    assert role_at_least(Role.ADMIN, Role.SUBSCRIPTION_USER)
    assert role_at_least(Role.SUBSCRIPTION_USER, Role.REGULAR_USER)
    assert not role_at_least(Role.REGULAR_USER, Role.SUBSCRIPTION_USER)


def test_an_admin_can_do_everything_a_subscriber_can() -> None:
    """Otherwise every check would have to list both roles, and one day one
    of them would list only the subscriber."""
    assert resolve(_grant(Role.ADMIN)).allows(Role.SUBSCRIPTION_USER)


@pytest.mark.parametrize("role", list(Role))
def test_every_role_satisfies_itself(role: Role) -> None:
    assert role_at_least(role, role)


# --- no row means ordinary ------------------------------------------------


def test_no_row_is_an_ordinary_user() -> None:
    """Opening the bot must not require writing a row."""
    assert resolve(None).role is Role.REGULAR_USER


# --- expiry ---------------------------------------------------------------


def test_a_live_subscription_works() -> None:
    access = resolve(_grant(Role.SUBSCRIPTION_USER, NOW + timedelta(days=1)), now=NOW)
    assert access.role is Role.SUBSCRIPTION_USER


def test_a_lapsed_subscription_is_an_ordinary_user() -> None:
    access = resolve(_grant(Role.SUBSCRIPTION_USER, NOW - timedelta(seconds=1)), now=NOW)
    assert access.role is Role.REGULAR_USER


def test_expiry_is_inclusive_of_the_moment_itself() -> None:
    """A subscription "until noon" is over at noon, not a second later."""
    access = resolve(_grant(Role.SUBSCRIPTION_USER, NOW), now=NOW)
    assert access.role is Role.REGULAR_USER


def test_a_subscription_without_an_end_date_never_lapses() -> None:
    access = resolve(_grant(Role.SUBSCRIPTION_USER, None), now=NOW)
    assert access.role is Role.SUBSCRIPTION_USER


def test_an_admin_never_expires() -> None:
    """Locking the owner out of their own bot because a date passed is
    never what anyone wanted."""
    access = resolve(_grant(Role.ADMIN, NOW - timedelta(days=365)), now=NOW)
    assert access.role is Role.ADMIN
    assert access.expires_at is None

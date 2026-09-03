"""Who may do what.

The whole point of this module is one function: given a user and the clock,
what can they do right now. Everything else - granting, revoking, listing -
exists to feed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import Role, User, UserAccess, role_at_least


@dataclass(frozen=True)
class Access:
    """A user's standing, already resolved against the clock."""

    role: Role
    expires_at: datetime | None
    note: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN

    def allows(self, required: Role) -> bool:
        return role_at_least(self.role, required)


REGULAR = Access(role=Role.REGULAR_USER, expires_at=None)


def resolve(access: UserAccess | None, *, now: datetime | None = None) -> Access:
    """Turns a stored grant into what the user may actually do.

    Expiry is applied here rather than by a scheduled job. A subscription
    that has run out has to stop working because the clock moved - a job
    that expires rows can fail to run, and then a lapsed subscription keeps
    working for as long as nobody notices.
    """
    if access is None:
        return REGULAR

    role = Role(access.role)
    # An admin does not expire. Locking the owner out of their own bot
    # because a date passed is never the behaviour anyone wanted.
    if role is Role.ADMIN:
        return Access(role=role, expires_at=None, note=access.note)

    now = now or datetime.now(UTC)
    if access.expires_at is not None and access.expires_at <= now:
        return REGULAR

    return Access(role=role, expires_at=access.expires_at, note=access.note)


class AccessService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_user(self, user: User, *, now: datetime | None = None) -> Access:
        """The user's standing.

        Reads the row by primary key rather than through ``user.access``.
        The relationship is there for convenience elsewhere, but relying on
        it here means depending on how the user happened to be loaded - and
        when that assumption broke, it broke as a MissingGreenlet in the
        middleware, on every single update. A primary-key lookup on a table
        that holds only the exceptions costs nothing and cannot surprise.
        """
        return resolve(await self._session.get(UserAccess, user.id), now=now)

    async def get(self, user_id: int) -> UserAccess | None:
        return await self._session.get(UserAccess, user_id)

    async def grant(
        self,
        user_id: int,
        role: Role,
        *,
        granted_by_id: int | None = None,
        days: int | None = None,
        note: str | None = None,
        now: datetime | None = None,
    ) -> UserAccess:
        """Sets a role, replacing whatever was there.

        ``days=None`` means no end date. Admins never carry one: see
        ``resolve``.
        """
        now = now or datetime.now(UTC)
        expires_at = None if days is None or role is Role.ADMIN else now + timedelta(days=days)

        access = await self._session.get(UserAccess, user_id)
        if access is None:
            access = UserAccess(user_id=user_id)
            self._session.add(access)

        access.role = role.value
        access.granted_by_id = granted_by_id
        access.granted_at = now
        access.expires_at = expires_at
        access.note = note

        await self._session.flush()
        return access

    async def revoke(self, user_id: int) -> bool:
        """Back to an ordinary user. Returns whether anything changed."""
        access = await self._session.get(UserAccess, user_id)
        if access is None:
            return False
        await self._session.delete(access)
        await self._session.flush()
        return True

    async def by_telegram_id(self, telegram_id: int) -> User | None:
        user: User | None = await self._session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        return user

    async def everyone(self, *, limit: int = 50) -> list[tuple[User, UserAccess | None]]:
        """Every person who has ever opened the bot, newest first.

        Used to list only those with a grant, on the reasoning that ordinary
        users have no row and so are not interesting. That was wrong twice
        over: an admin wants to know WHO is using the bot before deciding
        anything about them, and with the whitelist empty anyone can walk in.
        A list that omits exactly the people you have not looked at yet is
        the wrong list.
        """
        rows = await self._session.execute(
            select(User, UserAccess)
            .outerjoin(UserAccess, UserAccess.user_id == User.id)
            .order_by(User.created_at.desc())
            .limit(limit)
        )
        return [(user, access) for user, access in rows]

    async def ensure_admins(self, telegram_ids: frozenset[int]) -> int:
        """Makes sure the owners listed in the environment are admins.

        Called on startup and whenever one of them touches the bot, so that
        wiping the database - which this project does routinely while
        testing - cannot lock the owner out of their own admin commands.
        """
        if not telegram_ids:
            return 0

        users = list(
            await self._session.scalars(select(User).where(User.telegram_id.in_(telegram_ids)))
        )
        repaired = 0
        for user in users:
            stored = await self._session.get(UserAccess, user.id)
            if stored is not None and Role(stored.role) is Role.ADMIN:
                continue
            await self.grant(user.id, Role.ADMIN, note="владелец из ADMIN_TELEGRAM_IDS")
            repaired += 1
        return repaired

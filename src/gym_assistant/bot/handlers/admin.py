"""Admin commands: handing out and taking away access.

The whole router is filtered on ``IsAdmin``, so these commands do not exist
for anyone else - an ordinary user typing /grant gets the same "unknown
command" they would get for /qwerty, which is the right amount of
information to give them.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.filters import IsAdmin
from gym_assistant.bot.texts import render, ru
from gym_assistant.domain.models import Role, User
from gym_assistant.domain.services import Access, AccessService, resolve

log = structlog.get_logger(__name__)

router = Router(name="admin")
router.message.filter(IsAdmin())

ROLE_LABELS = {
    Role.REGULAR_USER: "обычный пользователь",
    Role.SUBSCRIPTION_USER: "подписчик",
    Role.ADMIN: "администратор",
}


def _parse_role(raw: str) -> Role | None:
    needle = raw.strip().lower()
    for role in Role:
        if needle in (role.value, ROLE_LABELS[role]):
            return role
    # Short forms, because typing "subscription_user" on a phone is a chore.
    return {"admin": Role.ADMIN, "sub": Role.SUBSCRIPTION_USER, "user": Role.REGULAR_USER}.get(
        needle
    )


@router.message(Command("grant"))
async def cmd_grant(
    message: Message, command: CommandObject, session: AsyncSession, user: User
) -> None:
    parts = (command.args or "").split()
    if len(parts) < 2:
        await message.answer(ru.ADMIN_GRANT_USAGE)
        return

    raw_id, raw_role, *rest = parts
    try:
        telegram_id = int(raw_id)
    except ValueError:
        await message.answer(ru.ADMIN_BAD_ID.format(value=raw_id))
        return

    role = _parse_role(raw_role)
    if role is None:
        await message.answer(ru.ADMIN_BAD_ROLE.format(value=raw_role))
        return

    days: int | None = None
    if rest:
        try:
            days = int(rest[0])
        except ValueError:
            await message.answer(ru.ADMIN_BAD_DAYS.format(value=rest[0]))
            return
        if days <= 0:
            await message.answer(ru.ADMIN_BAD_DAYS.format(value=rest[0]))
            return

    service = AccessService(session)
    target = await service.by_telegram_id(telegram_id)
    if target is None:
        # Granting to someone who has never opened the bot would write a row
        # keyed on a user that does not exist. Asking them to press /start is
        # one message; inventing half a user is a class of bug.
        await message.answer(ru.ADMIN_USER_UNKNOWN.format(telegram_id=telegram_id))
        return

    if role is Role.REGULAR_USER:
        await service.revoke(target.id)
    else:
        await service.grant(target.id, role, granted_by_id=user.id, days=days)

    log.info(
        "access_granted",
        by=user.telegram_id,
        target=telegram_id,
        role=role.value,
        days=days,
    )
    await message.answer(
        ru.ADMIN_GRANTED.format(
            who=_who(target),
            role=ROLE_LABELS[role],
            until=ru.ADMIN_UNTIL.format(days=days) if days else ru.ADMIN_FOREVER,
        )
    )


@router.message(Command("revoke"))
async def cmd_revoke(message: Message, command: CommandObject, session: AsyncSession) -> None:
    try:
        telegram_id = int((command.args or "").strip())
    except ValueError:
        await message.answer(ru.ADMIN_REVOKE_USAGE)
        return

    service = AccessService(session)
    target = await service.by_telegram_id(telegram_id)
    if target is None:
        await message.answer(ru.ADMIN_USER_UNKNOWN.format(telegram_id=telegram_id))
        return

    changed = await service.revoke(target.id)
    await message.answer(
        ru.ADMIN_REVOKED.format(who=_who(target)) if changed else ru.ADMIN_NOTHING_TO_REVOKE
    )


@router.message(Command("users"))
async def cmd_users(message: Message, session: AsyncSession) -> None:
    """Everyone who is not an ordinary user.

    Ordinary users have no row at all, so this is exactly the list of people
    somebody has decided something about - which is the list worth reading.
    """
    rows = await AccessService(session).privileged()
    if not rows:
        await message.answer(ru.ADMIN_USERS_EMPTY)
        return

    now = datetime.now(UTC)
    lines = []
    for target, stored in rows:
        current = resolve(stored, now=now)
        lapsed = current.role is not Role(stored.role)
        lines.append(
            ru.ADMIN_USER_LINE.format(
                who=_who(target),
                telegram_id=target.telegram_id,
                role=ROLE_LABELS[Role(stored.role)],
                until=_until(stored.expires_at, lapsed=lapsed),
            )
        )
    await message.answer(ru.ADMIN_USERS_HEADER + "\n".join(lines))


def _who(target: User) -> str:
    if target.username:
        return f"@{target.username}"
    return target.first_name or str(target.telegram_id)


def _until(expires_at: datetime | None, *, lapsed: bool) -> str:
    if expires_at is None:
        return ru.ADMIN_FOREVER
    when = render.format_date(expires_at.date())
    return ru.ADMIN_LAPSED.format(when=when) if lapsed else ru.ADMIN_UNTIL_DATE.format(when=when)


# --- available to everyone ------------------------------------------------
#
# Its own router, because the one above refuses non-admins by design.

public_router = Router(name="access")


@public_router.message(Command("whoami"))
async def cmd_whoami(message: Message, user: User, access: Access) -> None:
    """Lets a user read their own standing without asking an admin."""
    await message.answer(
        ru.WHOAMI.format(
            telegram_id=user.telegram_id,
            role=ROLE_LABELS[access.role],
            until=_until(access.expires_at, lapsed=False),
        )
    )

"""Roles from the server's shell, for when the bot cannot help.

    docker compose run --rm bot python -m gym_assistant.admin list
    docker compose run --rm bot python -m gym_assistant.admin grant 402666721 admin
    docker compose run --rm bot python -m gym_assistant.admin grant 12345 sub --days 30
    docker compose run --rm bot python -m gym_assistant.admin revoke 12345

The bot has the same commands, but they need an admin to run them - and the
first admin has to come from somewhere. ADMIN_TELEGRAM_IDS in .env covers the
usual case; this covers the rest, including "I locked myself out".
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from gym_assistant.config import get_settings
from gym_assistant.db import create_engine, create_session_factory
from gym_assistant.domain.models import Role
from gym_assistant.domain.services import AccessService, resolve

ROLE_ALIASES = {
    "admin": Role.ADMIN,
    "sub": Role.SUBSCRIPTION_USER,
    "subscription_user": Role.SUBSCRIPTION_USER,
    "user": Role.REGULAR_USER,
    "regular_user": Role.REGULAR_USER,
}


async def _grant(telegram_id: int, role: Role, days: int | None) -> None:
    engine = create_engine(get_settings().database_url)
    async with create_session_factory(engine)() as session:
        service = AccessService(session)
        user = await service.by_telegram_id(telegram_id)
        if user is None:
            print(f"Пользователя {telegram_id} нет в базе — пусть напишет боту /start.")
            await engine.dispose()
            raise SystemExit(1)

        if role is Role.REGULAR_USER:
            await service.revoke(user.id)
        else:
            await service.grant(user.id, role, days=days, note="выдано из консоли")
        await session.commit()

        until = "бессрочно" if days is None or role is Role.ADMIN else f"на {days} дн."
        print(f"{telegram_id} → {role.value}, {until}")
    await engine.dispose()


async def _revoke(telegram_id: int) -> None:
    await _grant(telegram_id, Role.REGULAR_USER, None)


async def _list() -> None:
    engine = create_engine(get_settings().database_url)
    async with create_session_factory(engine)() as session:
        rows = await AccessService(session).privileged()
        if not rows:
            print("Выданных доступов нет — все пользователи обычные.")
        now = datetime.now(UTC)
        for user, stored in rows:
            current = resolve(stored, now=now)
            lapsed = " (истёк)" if current.role is not Role(stored.role) else ""
            until = stored.expires_at.date().isoformat() if stored.expires_at else "бессрочно"
            name = f"@{user.username}" if user.username else (user.first_name or "—")
            print(f"{user.telegram_id:<14} {Role(stored.role).value:<18} {until}{lapsed}  {name}")
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    grant = sub.add_parser("grant", help="выдать роль")
    grant.add_argument("telegram_id", type=int)
    grant.add_argument("role", choices=sorted(ROLE_ALIASES))
    grant.add_argument("--days", type=int, default=None, help="срок; без него — бессрочно")

    revoke = sub.add_parser("revoke", help="вернуть обычный доступ")
    revoke.add_argument("telegram_id", type=int)

    sub.add_parser("list", help="показать выданные доступы")

    args = parser.parse_args()

    if args.command == "grant":
        asyncio.run(_grant(args.telegram_id, ROLE_ALIASES[args.role], args.days))
    elif args.command == "revoke":
        asyncio.run(_revoke(args.telegram_id))
    else:
        asyncio.run(_list())


if __name__ == "__main__":
    main()

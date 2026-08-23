"""Data access for users and their profiles."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import User, UserProfile


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        # Annotated because AsyncSession.scalar is typed as returning Any.
        user: User | None = await self._session.scalar(stmt)
        return user

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def add(self, telegram_id: int, username: str | None, first_name: str | None) -> User:
        # The profile row is created alongside the user so that later edits
        # are plain updates and never have to branch on "does it exist yet".
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            profile=UserProfile(),
        )
        self._session.add(user)
        await self._session.flush()
        return user

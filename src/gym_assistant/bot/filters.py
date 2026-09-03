"""Filters that gate handlers on what the user is allowed to do.

A filter rather than a check inside each handler: a forgotten check is a
silent hole, while a router without a filter is visible in one place. Attach
it to the router, not to individual handlers.
"""

from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from gym_assistant.domain.models import Role
from gym_assistant.domain.services import Access


class RequireRole(BaseFilter):
    """Passes when the user is at least ``required``.

    Roles are ordered, so an admin satisfies every check a subscriber does
    without anyone having to list both.
    """

    def __init__(self, required: Role) -> None:
        self.required = required

    async def __call__(self, event: TelegramObject, **data: Any) -> bool:
        access: Access | None = data.get("access")
        if access is None:
            # No access in context means the middleware did not run - refuse
            # rather than assume, so a wiring mistake fails closed.
            return False
        return access.allows(self.required)


class IsAdmin(RequireRole):
    """Reads better on the admin router than ``RequireRole(Role.ADMIN)``."""

    def __init__(self) -> None:
        super().__init__(Role.ADMIN)

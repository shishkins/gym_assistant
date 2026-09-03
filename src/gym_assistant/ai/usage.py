"""What each call cost, and the limit it is checked against.

The limit is enforced against a sum over ``ai_usage_log``, not a counter in
the process. A counter resets when the bot restarts, which makes it a
suggestion rather than a limit - and restarts are exactly what happens on
every deploy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.domain.models import AiUsage, User

log = structlog.get_logger(__name__)

MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Price:
    """Dollars per million tokens."""

    input: Decimal
    output: Decimal

    @property
    def cache_read(self) -> Decimal:
        """Reading a cached prefix costs a tenth of fresh input."""
        return self.input / 10

    @property
    def cache_write(self) -> Decimal:
        """Writing one costs a quarter more than fresh input."""
        return self.input * Decimal("1.25")


# Checked against the published rates on 2026-09-03. If a call comes back
# with a model that is not here, it is billed at the most expensive rate we
# know rather than at zero: an unknown model must not look free.
PRICES = {
    "claude-opus-5": Price(input=Decimal(5), output=Decimal(25)),
    "claude-sonnet-5": Price(input=Decimal(2), output=Decimal(10)),
    "claude-haiku-4-5": Price(input=Decimal(1), output=Decimal(5)),
}
FALLBACK_PRICE = Price(input=Decimal(5), output=Decimal(25))


@dataclass(frozen=True)
class Tokens:
    """The four counters the API reports."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write


def price_for(model: str) -> Price:
    price = PRICES.get(model)
    if price is None:
        log.warning("ai_unknown_model_price", model=model)
        return FALLBACK_PRICE
    return price


def cost_of(model: str, tokens: Tokens) -> Decimal:
    """Dollars for one call, to six decimal places.

    Six because a cheap call costs fractions of a cent, and rounding those
    to two would record every one of them as free - and a log of free calls
    sums to a limit that never trips.
    """
    price = price_for(model)
    total = (
        Decimal(tokens.input) * price.input
        + Decimal(tokens.output) * price.output
        + Decimal(tokens.cache_read) * price.cache_read
        + Decimal(tokens.cache_write) * price.cache_write
    ) / MILLION
    return total.quantize(Decimal("0.000001"))


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class UsageService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        user_id: int,
        session_id: int | None,
        model: str,
        tokens: Tokens,
    ) -> Decimal:
        """Writes one call to the log and returns what it cost."""
        cost = cost_of(model, tokens)
        self._session.add(
            AiUsage(
                user_id=user_id,
                session_id=session_id,
                model=model,
                input_tokens=tokens.input,
                output_tokens=tokens.output,
                cache_read_tokens=tokens.cache_read,
                cache_write_tokens=tokens.cache_write,
                cost_usd=cost,
            )
        )
        await self._session.flush()
        return cost

    async def spent_this_month(self, user_id: int, *, now: datetime | None = None) -> Decimal:
        total = await self._session.scalar(
            select(func.coalesce(func.sum(AiUsage.cost_usd), 0)).where(
                AiUsage.user_id == user_id,
                AiUsage.created_at >= month_start(now),
            )
        )
        return Decimal(total or 0)

    async def spent_this_month_total(self, *, now: datetime | None = None) -> Decimal:
        """Across everyone - what actually lands on the card."""
        total = await self._session.scalar(
            select(func.coalesce(func.sum(AiUsage.cost_usd), 0)).where(
                AiUsage.created_at >= month_start(now)
            )
        )
        return Decimal(total or 0)

    async def by_user_this_month(
        self, *, now: datetime | None = None
    ) -> list[tuple[User, Decimal, int]]:
        """Who spent what, dearest first. Admin-only: one person's spending
        is not another's business."""
        rows = await self._session.execute(
            select(User, func.sum(AiUsage.cost_usd), func.count())
            .join(AiUsage, AiUsage.user_id == User.id)
            .where(AiUsage.created_at >= month_start(now))
            .group_by(User.id)
            .order_by(func.sum(AiUsage.cost_usd).desc())
        )
        return [(user, Decimal(cost or 0), calls) for user, cost, calls in rows]

    async def budget_left(self, limit_usd: float, *, now: datetime | None = None) -> Decimal:
        """How much of this month's budget is unspent, across all users.

        Deliberately global rather than per-user: the bill is one bill, and
        a per-user limit lets N users spend N times the cap between them.
        """
        return Decimal(str(limit_usd)) - await self.spent_this_month_total(now=now)

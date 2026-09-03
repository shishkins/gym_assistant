"""Cost arithmetic.

The spending limit is only as good as these numbers. A rounding choice that
records cheap calls as free produces a log that sums to zero and a limit
that never trips.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from gym_assistant.ai.usage import PRICES, Tokens, cost_of, month_start, price_for


def test_a_million_input_tokens_costs_the_headline_price() -> None:
    assert cost_of("claude-opus-5", Tokens(input=1_000_000)) == Decimal("5.000000")


def test_a_million_output_tokens_costs_the_headline_price() -> None:
    assert cost_of("claude-opus-5", Tokens(output=1_000_000)) == Decimal("25.000000")


def test_reading_the_cache_costs_a_tenth_of_input() -> None:
    """The whole point of caching the prompt prefix."""
    assert cost_of("claude-opus-5", Tokens(cache_read=1_000_000)) == Decimal("0.500000")


def test_writing_the_cache_costs_a_quarter_more() -> None:
    assert cost_of("claude-opus-5", Tokens(cache_write=1_000_000)) == Decimal("6.250000")


def test_a_realistic_question_costs_a_few_cents() -> None:
    """~5000 in, ~470 out - the shape measured when planning the iteration."""
    cost = cost_of("claude-opus-5", Tokens(input=5000, output=470))

    assert Decimal("0.03") < cost < Decimal("0.05")


def test_a_cheap_call_is_not_recorded_as_free() -> None:
    """Two decimal places would round this to 0.00, and a log of zeroes
    never reaches any limit."""
    assert cost_of("claude-haiku-4-5", Tokens(input=200, output=50)) > 0


@pytest.mark.parametrize("model", sorted(PRICES))
def test_every_priced_model_costs_something(model: str) -> None:
    assert cost_of(model, Tokens(input=1000, output=100)) > 0


def test_an_unknown_model_is_billed_at_the_dearest_rate() -> None:
    """Not at zero: a model we do not know must not look free."""
    unknown = price_for("claude-something-new")

    assert unknown.input == max(price.input for price in PRICES.values())


def test_cheaper_models_are_cheaper() -> None:
    tokens = Tokens(input=10_000, output=1000)

    assert (
        cost_of("claude-haiku-4-5", tokens)
        < cost_of("claude-sonnet-5", tokens)
        < cost_of("claude-opus-5", tokens)
    )


# --- the month boundary ---------------------------------------------------


def test_the_month_starts_at_midnight_on_the_first() -> None:
    start = month_start(datetime(2026, 9, 17, 13, 45, tzinfo=UTC))

    assert start == datetime(2026, 9, 1, tzinfo=UTC)


def test_the_first_of_the_month_is_already_the_new_month() -> None:
    """A question asked at 00:30 on the 1st must not count against the
    previous month's budget."""
    moment = datetime(2026, 9, 1, 0, 30, tzinfo=UTC)

    assert month_start(moment) <= moment
    assert month_start(moment).month == 9

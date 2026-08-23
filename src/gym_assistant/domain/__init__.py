"""Domain layer: business logic, models and repositories.

Hard rule for this package: it must not import ``aiogram`` or ``anthropic``.
Bot handlers, AI tools and (later) the Mini App API all call the same
services from here. Breaking that rule is the most expensive mistake
available in this codebase.
"""

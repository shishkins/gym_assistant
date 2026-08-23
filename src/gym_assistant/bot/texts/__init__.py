"""User-facing strings and rendering.

Every string shown to a user lives in ``ru``, never inline in a handler.
That keeps tone consistent and makes a second locale a new module rather
than a hunt through the codebase.
"""

from gym_assistant.bot.texts import render, ru

__all__ = ["render", "ru"]

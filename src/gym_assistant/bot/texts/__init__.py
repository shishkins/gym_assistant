"""User-facing strings.

Every string shown to a user lives here, never inline in a handler.
That keeps tone consistent and makes adding a second locale a matter of
adding a module rather than combing through the codebase.
"""

from gym_assistant.bot.texts import ru

__all__ = ["ru"]

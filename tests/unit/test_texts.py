"""UI strings must stay formattable - a typo here breaks a live handler."""

from __future__ import annotations

from gym_assistant.bot.texts import ru


def test_access_denied_includes_user_id() -> None:
    rendered = ru.ACCESS_DENIED.format(user_id=42)
    assert "42" in rendered


def test_greeting_accepts_a_name() -> None:
    assert "Вася" in ru.START_GREETING.format(name="Вася")


def test_ping_reports_version_and_environment() -> None:
    rendered = ru.PING_OK.format(version="0.1.0", environment="local")
    assert "0.1.0" in rendered
    assert "local" in rendered

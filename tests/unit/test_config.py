"""Settings parsing - the whitelist and the DSN are easy to get subtly wrong."""

from __future__ import annotations

import pytest

from gym_assistant.config import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"bot_token": "123:abc"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", frozenset()),
        ("123", frozenset({123})),
        ("123,456", frozenset({123, 456})),
        (" 123 , 456 ", frozenset({123, 456})),
        ("123;456", frozenset({123, 456})),
        ("123,,456,", frozenset({123, 456})),
    ],
)
def test_allowed_ids_parsing(raw: str, expected: frozenset[int]) -> None:
    assert _settings(allowed_telegram_ids=raw).allowed_ids == expected


def test_database_url_is_async_and_escapes_password() -> None:
    settings = _settings(
        postgres_user="gym",
        postgres_password="p@ss w/ord",
        postgres_host="db",
        postgres_port=5433,
        postgres_db="gym_assistant",
    )
    url = settings.database_url

    assert url.startswith("postgresql+asyncpg://")
    assert "p%40ss+w%2Ford" in url
    assert url.endswith("@db:5433/gym_assistant")


def test_password_is_not_leaked_by_repr() -> None:
    settings = _settings(postgres_password="super-secret")
    assert "super-secret" not in repr(settings)


def test_is_production_flag() -> None:
    assert _settings(environment="prod").is_production is True
    assert _settings(environment="local").is_production is False

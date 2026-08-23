"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest

# Settings are validated at import time in some modules, so make sure the
# required variables always exist during tests.
os.environ.setdefault("BOT_TOKEN", "000000:test-token-not-real")
os.environ.setdefault("ALLOWED_TELEGRAM_IDS", "1")


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    from gym_assistant.config import get_settings

    get_settings.cache_clear()

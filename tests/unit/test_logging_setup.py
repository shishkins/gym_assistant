"""Regression tests for logging.

A misconfigured logger only explodes on the first real call, which is far
too late - it took down the bot at startup once already. These tests make
the very first log line part of the test suite.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
import structlog

from gym_assistant.logging_setup import setup_logging


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    yield
    logging.getLogger().handlers.clear()
    structlog.reset_defaults()


@pytest.mark.parametrize("json_logs", [True, False])
def test_named_logger_emits(json_logs: bool, capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging("DEBUG", json_logs=json_logs)

    structlog.get_logger("gym_assistant.some.module").warning("whitelist_empty", hint="none set")

    out = capsys.readouterr().out
    assert "whitelist_empty" in out
    assert "gym_assistant.some.module" in out
    assert "none set" in out


def test_stdlib_logger_goes_through_the_same_renderer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dependencies log through stdlib; their records must render too."""
    setup_logging("INFO", json_logs=True)

    logging.getLogger("aiogram.dispatcher").info("polling started")

    out = capsys.readouterr().out
    assert "polling started" in out
    assert "aiogram.dispatcher" in out


def test_contextvars_are_merged_into_the_event(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging("INFO", json_logs=True)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(user_id=777, request_id="abc123")

    structlog.get_logger("gym_assistant.test").info("update_handled")

    out = capsys.readouterr().out
    assert "777" in out
    assert "abc123" in out

    structlog.contextvars.clear_contextvars()


def test_exception_is_rendered(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging("INFO", json_logs=True)

    try:
        raise ValueError("boom")
    except ValueError:
        structlog.get_logger("gym_assistant.test").exception("handler_failed")

    out = capsys.readouterr().out
    assert "handler_failed" in out
    assert "boom" in out

"""structlog configuration.

structlog is wired on top of the stdlib ``logging`` module rather than
replacing it, so that log records emitted by dependencies (aiogram,
SQLAlchemy, alembic) are rendered exactly like our own.

Local runs get colourful human-readable output; production emits JSON lines
so ``docker compose logs`` stays greppable and machine-parseable.
"""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(level: str = "INFO", *, json_logs: bool = False) -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Applied both to structlog calls and to records coming from stdlib
    # loggers, which is what keeps the two sources looking identical.
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    render_processors: list[structlog.typing.Processor] = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
    ]
    if json_logs:
        # ConsoleRenderer formats exceptions itself; the JSON one needs help.
        render_processors.append(structlog.processors.format_exc_info)
        render_processors.append(structlog.processors.JSONRenderer(ensure_ascii=False))
    else:
        render_processors.append(structlog.dev.ConsoleRenderer(colors=True))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=render_processors,
        )
    )

    root = logging.getLogger()
    root.handlers.clear()  # idempotent: no duplicate lines if called twice
    root.addHandler(handler)
    root.setLevel(log_level)

    # aiogram's polling loop is chatty at INFO; keep it at WARNING.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

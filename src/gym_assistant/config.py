"""Application settings.

Everything is read from environment variables (or a local ``.env``).
No secret is ever hard-coded or committed - see ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["local", "prod"] = "local"
    log_level: str = "INFO"

    # --- Telegram ---
    bot_token: SecretStr
    # Empty means the bot answers everyone; set it to close the bot down.
    allowed_telegram_ids: str = ""
    # Owners. Their admin rights are restored whenever they touch the bot,
    # so wiping the database cannot lock them out of their own commands.
    admin_telegram_ids: str = ""

    # --- PostgreSQL ---
    postgres_user: str = "gym"
    postgres_password: SecretStr = SecretStr("gym")
    postgres_db: str = "gym_assistant"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"

    # --- Anthropic ---
    anthropic_api_key: SecretStr | None = None
    # The default is what production actually runs. It used to be Opus, five
    # times the price, so a .env that lost this one line would have quietly
    # multiplied the bill rather than failed.
    ai_model_main: str = "claude-sonnet-5"
    # Reading a body photo. Pinned rather than merely defaulted: estimates are
    # compared with each other over months, and a different model reads the
    # same photo with a different bias - so changing this mid-history moves
    # every trend line, not just the next number. Sonnet over the cheaper
    # Haiku on measurement, not taste: on real photos Haiku swung 25% between
    # identical runs against Sonnet's 9%.
    ai_model_vision: str = "claude-sonnet-5"
    ai_monthly_limit_usd: float = 10.0

    # --- Clock ---
    # Which clock a day and a week are counted by. Rows stay UTC; this only
    # decides where one day ends and the next begins when they are grouped.
    # A session at six on a Monday morning in Vietnam is eleven on Sunday
    # night UTC, so counting by UTC files it under the previous week. One
    # setting for the whole bot rather than one per person: everyone using it
    # lives in the same place, and a per-user field earns its keep on the day
    # that stops being true.
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        """A typo here would otherwise surface as wrong weeks, silently."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone: {value!r}") from exc
        return value

    @staticmethod
    def _ids(raw: str) -> frozenset[int]:
        """Parses ``123,456``.

        Parsed by hand instead of being declared as ``set[int]`` because
        pydantic-settings JSON-decodes complex types from env vars, which
        would reject a plain ``123,456`` string.
        """
        return frozenset(int(part) for part in raw.replace(";", ",").split(",") if part.strip())

    @property
    def allowed_ids(self) -> frozenset[int]:
        """Who may talk to the bot. Empty means everyone."""
        return self._ids(self.allowed_telegram_ids)

    @property
    def admin_ids(self) -> frozenset[int]:
        """Owners, kept as admins no matter what the database says."""
        return self._ids(self.admin_telegram_ids)

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy DSN. The password is URL-escaped."""
        password = quote_plus(self.postgres_password.get_secret_value())
        return (
            f"postgresql+asyncpg://{quote_plus(self.postgres_user)}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

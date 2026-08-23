"""Application settings.

Everything is read from environment variables (or a local ``.env``).
No secret is ever hard-coded or committed - see ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import SecretStr
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
    allowed_telegram_ids: str = ""

    # --- PostgreSQL ---
    postgres_user: str = "gym"
    postgres_password: SecretStr = SecretStr("gym")
    postgres_db: str = "gym_assistant"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"

    # --- Anthropic (iteration 5+; may stay unset until then) ---
    anthropic_api_key: SecretStr | None = None
    ai_model_main: str = "claude-opus-5"
    ai_model_fast: str = "claude-haiku-4-5"
    ai_monthly_limit_usd: float = 10.0

    # --- Speech to text (iteration 6+) ---
    stt_url: str = "http://stt:8000"
    stt_model: str = "small"

    @property
    def allowed_ids(self) -> frozenset[int]:
        """Telegram user IDs allowed to use the bot.

        Parsed by hand instead of being declared as ``set[int]`` because
        pydantic-settings JSON-decodes complex types from env vars, which
        would reject a plain ``123,456`` string.
        """
        raw = self.allowed_telegram_ids.replace(";", ",")
        return frozenset(int(part) for part in raw.split(",") if part.strip())

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

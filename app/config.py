from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        enable_decoding=False,
        extra="ignore",
        case_sensitive=False,
    )

    telegram_bot_token: SecretStr = SecretStr("")
    admin_telegram_id: int | None = None
    allowed_telegram_ids: list[int] = Field(default_factory=list)

    database_url: str = "sqlite+aiosqlite:///data/fitness_bot.sqlite3"
    timezone: str = "Asia/Yekaterinburg"
    monthly_workout_target: int = 10
    reminder_scan_seconds: int = 30
    log_level: str = "INFO"
    show_reset_button: bool = True

    llm_provider: Literal["template", "groq", "openrouter", "ollama", "openai"] = "template"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "openai/gpt-oss-20b"
    llm_base_url: str = ""
    llm_timeout_seconds: float = 8.0
    llm_max_output_tokens: int = 180

    @field_validator("allowed_telegram_ids", mode="before")
    @classmethod
    def parse_id_list(cls, value: object) -> object:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def database_path(self) -> Path | None:
        prefix = "sqlite+aiosqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        return Path(self.database_url.removeprefix(prefix)).expanduser()

    def ensure_local_directories(self) -> None:
        path = self.database_path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def is_telegram_user_allowed(self, telegram_id: int) -> bool:
        if self.admin_telegram_id == telegram_id:
            return True
        return not self.allowed_telegram_ids or telegram_id in self.allowed_telegram_ids

    def require_runtime_secrets(self) -> None:
        if not self.telegram_bot_token.get_secret_value():
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start polling")


def load_settings() -> Settings:
    return Settings()

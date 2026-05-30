"""Загрузка настроек из .env с проверками безопасности."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    telegram_manager_chat_id: str = Field(default="", alias="TELEGRAM_MANAGER_CHAT_ID")
    telegram_manager_username: str = Field(default="", alias="TELEGRAM_MANAGER_USERNAME")
    admin_user_ids: str = Field(default="", alias="ADMIN_USER_IDS")

    # OpenAI-совместимый API
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", alias="OPENAI_BASE_URL"
    )
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-3-5-haiku-20241022", alias="ANTHROPIC_MODEL"
    )

    # Безопасность
    bot_whitelist_enabled: bool = Field(default=False, alias="BOT_WHITELIST_ENABLED")
    allowed_user_ids: str = Field(default="", alias="ALLOWED_USER_IDS")
    rate_limit_per_minute: int = Field(default=15, ge=1, le=120, alias="RATE_LIMIT_PER_MINUTE")
    max_message_length: int = Field(default=2000, ge=100, le=8000, alias="MAX_MESSAGE_LENGTH")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")
    bot_mode: Literal["polling", "webhook"] = Field(default="polling", alias="BOT_MODE")
    webhook_port: int = Field(default=8443, ge=1, le=65535, alias="WEBHOOK_PORT")
    webhook_path: str = Field(default="/webhook", alias="WEBHOOK_PATH")

    # Бизнес
    business_phone: str = Field(default="+79308001479", alias="BUSINESS_PHONE")
    brief_file_path: str = Field(default="brif.md", alias="BRIEF_FILE_PATH")
    tz: str = Field(default="Europe/Moscow", alias="TZ")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("telegram_bot_token")
    @classmethod
    def token_not_placeholder(cls, v: str) -> str:
        placeholder = "ВСТАВЬТЕ_ТОКЕН_ОТ_BOTFATHER"
        if not v or v.strip() == placeholder:
            raise ValueError(
                "Укажите реальный TELEGRAM_BOT_TOKEN в .env (получить у @BotFather)"
            )
        if ":" not in v:
            raise ValueError("TELEGRAM_BOT_TOKEN выглядит неверно (ожидается формат id:hash)")
        return v.strip()

    @field_validator("webhook_secret")
    @classmethod
    def webhook_secret_if_needed(cls, v: str, info) -> str:
        # Проверка mode выполняется после; для webhook нужен секрет ≥ 16 символов
        return v

    def model_post_init(self, __context) -> None:
        if self.bot_mode == "webhook" and len(self.webhook_secret) < 16:
            raise ValueError(
                "При BOT_MODE=webhook задайте WEBHOOK_SECRET (минимум 16 символов)"
            )
        if not self.openai_api_key and not self.anthropic_api_key:
            raise ValueError(
                "Укажите OPENAI_API_KEY или ANTHROPIC_API_KEY в .env"
            )

    @property
    def admin_user_id_set(self) -> frozenset[int]:
        raw = self.admin_user_ids.strip() or self.telegram_manager_chat_id.strip()
        if not raw:
            return frozenset()
        ids: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if part:
                ids.add(int(part))
        return frozenset(ids)

    @property
    def phone_tel_uri(self) -> str:
        digits = "".join(c for c in self.business_phone if c.isdigit())
        if digits.startswith("8") and len(digits) == 11:
            digits = "7" + digits[1:]
        if not digits.startswith("7") and len(digits) == 10:
            digits = "7" + digits
        return f"+{digits}"

    @property
    def allowed_user_id_set(self) -> frozenset[int]:
        if not self.allowed_user_ids.strip():
            return frozenset()
        ids: set[int] = set()
        for part in self.allowed_user_ids.split(","):
            part = part.strip()
            if part:
                ids.add(int(part))
        return frozenset(ids)

    @property
    def brief_path(self) -> Path:
        p = Path(self.brief_file_path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()

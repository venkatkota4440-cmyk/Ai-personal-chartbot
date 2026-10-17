"""Application configuration loaded from environment variables.

All secrets come from the environment (or a secret manager in production).
Nothing in this module is ever sent to the frontend.
"""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# The project-root .env (personal-ai-agent/.env) is read even when commands run from apps/api.
# A .env in the current directory, if any, takes precedence; real environment variables win over both.
_ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"

# Values copied from .env.example that must never be used in production.
_PLACEHOLDER_SECRETS = {"", "replace_with_long_random_secret", "changeme"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(_ROOT_ENV_FILE, ".env"), env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./app.db"
    redis_url: str = "redis://localhost:6379/0"

    session_secret: str = ""
    session_ttl_hours: int = Field(default=24 * 7, ge=1, le=24 * 90)
    # None means "secure when production"; explicit values allow local HTTPS testing.
    cookie_secure: bool | None = None

    # Comma-separated list of origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:3000"

    allow_registration: bool = True
    password_min_length: int = Field(default=12, ge=8, le=128)

    max_request_bytes: int = Field(default=1_000_000, ge=1_024)

    rate_limit_backend: Literal["memory", "redis"] = "memory"
    login_rate_limit_per_minute: int = Field(default=5, ge=1)
    login_ip_rate_limit_per_minute: int = Field(default=20, ge=1)
    register_rate_limit_per_hour: int = Field(default=10, ge=1)

    # "mock" = deterministic offline provider only; "anthropic" additionally enables Claude models.
    ai_provider: Literal["mock", "anthropic"] = "mock"
    ai_api_key: str = ""
    # Models the user may pick in Settings. The provider registry validates the choice again.
    allowed_models: str = "mock-deterministic"
    ai_timeout_seconds: float = Field(default=60.0, ge=1, le=600)
    ai_max_output_tokens: int = Field(default=4000, ge=256, le=32000)
    chat_rate_limit_per_minute: int = Field(default=20, ge=1)
    run_rate_limit_per_minute: int = Field(default=30, ge=1)

    # "inline" runs automations in the API process (local demos, tests); "redis" hands them to an RQ worker.
    worker_mode: Literal["inline", "redis"] = "inline"
    # How many earlier messages are sent to the model as context.
    chat_history_messages: int = Field(default=20, ge=0, le=200)

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _check_secrets(self) -> Settings:
        if self.session_secret in _PLACEHOLDER_SECRETS or len(self.session_secret) < 32:
            if self.app_env == "production":
                raise ValueError("SESSION_SECRET must be set to a random value of at least 32 characters")
            # Dev/test convenience: an ephemeral secret means sessions reset on restart, which is safe.
            self.session_secret = secrets.token_urlsafe(48)
            logger.warning("SESSION_SECRET not set; using an ephemeral development secret")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_model_list(self) -> list[str]:
        return [m.strip() for m in self.allowed_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

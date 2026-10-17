from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import StrictModel, validate_timezone


class SettingsOut(BaseModel):
    timezone: str
    default_model: str
    available_models: list[str]
    notify_run_succeeded: bool
    notify_run_failed: bool
    notify_approval_needed: bool
    message_retention_days: int | None


class SettingsUpdate(StrictModel):
    """Partial update: only fields present in the request body are changed."""

    timezone: str | None = Field(default=None, max_length=64)
    default_model: str | None = Field(default=None, max_length=100)
    notify_run_succeeded: bool | None = None
    notify_run_failed: bool | None = None
    notify_approval_needed: bool | None = None
    # null in the request body means "keep forever"; omit the field to leave it unchanged.
    message_retention_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        return None if value is None else validate_timezone(value)

"""Per-user preferences: timezone, default model, notifications, data retention."""

from __future__ import annotations

from sqlalchemy.orm import Session as DbSession

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import User, UserSettings
from app.schemas.settings import SettingsOut, SettingsUpdate
from app.services import audit


def _ensure(db: DbSession, user: User, settings: Settings) -> UserSettings:
    if user.settings is None:
        user.settings = UserSettings(default_model=settings.allowed_model_list[0])
        db.flush()
    return user.settings


def to_out(user: User, prefs: UserSettings, settings: Settings) -> SettingsOut:
    return SettingsOut(
        timezone=user.timezone,
        default_model=prefs.default_model,
        available_models=settings.allowed_model_list,
        notify_run_succeeded=prefs.notify_run_succeeded,
        notify_run_failed=prefs.notify_run_failed,
        notify_approval_needed=prefs.notify_approval_needed,
        message_retention_days=prefs.message_retention_days,
    )


def get(db: DbSession, user: User, settings: Settings) -> SettingsOut:
    prefs = _ensure(db, user, settings)
    db.commit()
    return to_out(user, prefs, settings)


def update(db: DbSession, user: User, settings: Settings, change: SettingsUpdate) -> SettingsOut:
    prefs = _ensure(db, user, settings)
    fields = change.model_fields_set

    if "default_model" in fields:
        if change.default_model not in settings.allowed_model_list:
            raise AppError(
                ErrorCategory.VALIDATION,
                "Model is not available on this server",
                fields=[{"field": "default_model", "message": "Choose one of the available models"}],
            )
        prefs.default_model = change.default_model
    if "timezone" in fields:
        if change.timezone is None:
            raise AppError(
                ErrorCategory.VALIDATION,
                "Timezone cannot be empty",
                fields=[{"field": "timezone", "message": "Timezone is required"}],
            )
        user.timezone = change.timezone
    for flag in ("notify_run_succeeded", "notify_run_failed", "notify_approval_needed"):
        if flag in fields:
            value = getattr(change, flag)
            if value is None:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    f"{flag} must be true or false",
                    fields=[{"field": flag, "message": "Required"}],
                )
            setattr(prefs, flag, value)
    if "message_retention_days" in fields:
        prefs.message_retention_days = change.message_retention_days

    audit.record(db, action="settings.update", result="success", user_id=user.id, metadata={"fields": sorted(fields)})
    db.commit()
    return to_out(user, prefs, settings)

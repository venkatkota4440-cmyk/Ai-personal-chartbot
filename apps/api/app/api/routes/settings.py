from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.schemas.settings import SettingsOut, SettingsUpdate
from app.services import user_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def get_settings(user: CurrentUser, db: DbDep, settings: SettingsDep) -> SettingsOut:
    return user_settings.get(db, user, settings)


@router.patch("", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, user: CurrentUser, db: DbDep, settings: SettingsDep) -> SettingsOut:
    return user_settings.update(db, user, settings, body)

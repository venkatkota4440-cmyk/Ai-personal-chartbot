"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session as DbSession

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.core.security import SESSION_COOKIE
from app.db.models import User
from app.db.session import get_db
from app.services import auth as auth_service

DbDep = Annotated[DbSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_limiter(settings: SettingsDep) -> RateLimiter:
    return get_rate_limiter(settings)


LimiterDep = Annotated[RateLimiter, Depends(get_limiter)]


def get_current_user(request: Request, db: DbDep) -> User:
    user = auth_service.user_for_token(db, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise AppError(ErrorCategory.AUTHENTICATION, "Please sign in to continue")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def client_ip(request: Request) -> str:
    # Behind a proxy, configure uvicorn --proxy-headers with a trusted --forwarded-allow-ips list
    # so request.client reflects the real client instead of trusting X-Forwarded-For blindly.
    return request.client.host if request.client else "unknown"

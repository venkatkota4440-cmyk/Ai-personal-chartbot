"""Registration, login, sessions, and logout.

Routes stay thin; all authentication rules live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.core.redaction import mask_email
from app.core.security import (
    hash_password,
    hash_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)
from app.db.base import utcnow
from app.db.models import Session, User, UserSettings
from app.services import audit, demo_data

_INVALID_LOGIN = "Email or password is incorrect"


@dataclass(frozen=True)
class IssuedSession:
    user: User
    token: str
    max_age_seconds: int


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password_strength(password: str, settings: Settings) -> None:
    problems: list[str] = []
    if len(password) < settings.password_min_length:
        problems.append(f"Password must be at least {settings.password_min_length} characters")
    if password.strip() != password:
        problems.append("Password must not start or end with spaces")
    if problems:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Password does not meet requirements",
            fields=[{"field": "password", "message": p} for p in problems],
        )


def register(db: DbSession, settings: Settings, *, email: str, password: str, timezone: str) -> IssuedSession:
    if not settings.allow_registration:
        raise AppError(ErrorCategory.FORBIDDEN, "Registration is disabled on this server")
    validate_password_strength(password, settings)
    email = normalize_email(email)

    user = User(email=email, password_hash=hash_password(password), timezone=timezone)
    user.settings = UserSettings(default_model=settings.allowed_model_list[0])
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        audit.record(db, action="auth.register", result="conflict", user_id=None, target=mask_email(email))
        db.commit()
        # Personal single-owner app: a clear message is more useful than hiding that the account exists.
        raise AppError(ErrorCategory.CONFLICT, "An account with this email already exists") from None

    # Starter projects, tasks and demo automations, so the app is never an empty shell.
    demo_data.seed_for(db, user)
    issued = _issue_session(db, settings, user)
    audit.record(db, action="auth.register", result="success", user_id=user.id, target=mask_email(email))
    db.commit()
    return issued


def login(db: DbSession, settings: Settings, *, email: str, password: str) -> IssuedSession:
    email = normalize_email(email)
    user = db.scalars(select(User).where(User.email == email)).first()
    # verify_password always runs a full hash check, even for unknown emails, to avoid a timing oracle.
    if not verify_password(user.password_hash if user else None, password) or user is None:
        audit.record(
            db, action="auth.login", result="failure", user_id=user.id if user else None, target=mask_email(email)
        )
        db.commit()
        raise AppError(ErrorCategory.INVALID_CREDENTIALS, _INVALID_LOGIN)

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    issued = _issue_session(db, settings, user)
    audit.record(db, action="auth.login", result="success", user_id=user.id, target=mask_email(email))
    db.commit()
    return issued


def logout(db: DbSession, token: str | None) -> None:
    if not token:
        return
    session = db.scalars(select(Session).where(Session.token_hash == hash_token(token))).first()
    if session is None or session.revoked_at is not None:
        return
    session.revoked_at = utcnow()
    audit.record(db, action="auth.logout", result="success", user_id=session.user_id)
    db.commit()


def user_for_token(db: DbSession, token: str | None) -> User | None:
    if not token:
        return None
    session = db.scalars(
        select(Session).where(
            Session.token_hash == hash_token(token),
            Session.revoked_at.is_(None),
            Session.expires_at > utcnow(),
        )
    ).first()
    if session is None:
        return None
    return db.get(User, session.user_id)


def revoke_all_sessions(db: DbSession, user_id: str) -> None:
    db.execute(
        update(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None)).values(revoked_at=utcnow())
    )


def _issue_session(db: DbSession, settings: Settings, user: User) -> IssuedSession:
    token = new_session_token()
    ttl = timedelta(hours=settings.session_ttl_hours)
    db.add(Session(user_id=user.id, token_hash=hash_token(token), expires_at=utcnow() + ttl))
    return IssuedSession(user=user, token=token, max_age_seconds=int(ttl.total_seconds()))

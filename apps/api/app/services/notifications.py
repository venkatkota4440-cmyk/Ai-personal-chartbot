"""Notification centre."""

from __future__ import annotations

from sqlalchemy.orm import Session as DbSession

from app.core.errors import not_found
from app.db.base import utcnow
from app.db.models import Notification, User, UserSettings
from app.db.repository import get_owned, owned_select

# Which user preference silences which notification type.
_PREFERENCE_BY_TYPE = {
    "run_succeeded": "notify_run_succeeded",
    "run_partial": "notify_run_succeeded",
    "run_failed": "notify_run_failed",
    "approval_needed": "notify_approval_needed",
}


def create(db: DbSession, *, user_id: str, type: str, message: str, link: str | None = None) -> Notification | None:
    """Add a notification unless the user switched that type off. Caller commits."""
    preference = _PREFERENCE_BY_TYPE.get(type)
    if preference is not None:
        prefs = db.get(UserSettings, user_id)
        if prefs is not None and not getattr(prefs, preference):
            return None
    notification = Notification(user_id=user_id, type=type, message=message[:2000], link=link)
    db.add(notification)
    db.flush()
    return notification


def list_for_user(db: DbSession, user: User, *, unread_only: bool = False, limit: int = 50) -> list[Notification]:
    query = owned_select(Notification, user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    return list(db.scalars(query.order_by(Notification.created_at.desc()).limit(limit)))


def mark_read(db: DbSession, user: User, notification_id: str) -> Notification:
    notification = get_owned(db, Notification, notification_id, user.id)
    if notification is None:
        raise not_found("Notification")
    if notification.read_at is None:
        notification.read_at = utcnow()
        db.commit()
    return notification


def mark_all_read(db: DbSession, user: User) -> int:
    rows = db.scalars(owned_select(Notification, user.id).where(Notification.read_at.is_(None))).all()
    for notification in rows:
        notification.read_at = utcnow()
    if rows:
        db.commit()
    return len(rows)

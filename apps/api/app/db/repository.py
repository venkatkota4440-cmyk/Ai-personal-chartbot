"""Owner-scoped data access helpers.

Every read or write of user-owned data goes through these helpers so the
user_id filter cannot be forgotten. Records owned by someone else are treated
exactly like records that do not exist (the API returns 404 for both).
"""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import InstrumentedAttribute, Session

T = TypeVar("T")


def owned_select(model: type[T], user_id: str) -> Select[tuple[T]]:
    owner_column: InstrumentedAttribute[str] = model.user_id  # type: ignore[attr-defined]
    return select(model).where(owner_column == user_id)


def get_owned(db: Session, model: type[T], record_id: str, user_id: str) -> T | None:
    id_column: InstrumentedAttribute[str] = model.id  # type: ignore[attr-defined]
    return db.scalars(owned_select(model, user_id).where(id_column == record_id)).first()


def list_owned(db: Session, model: type[T], user_id: str, *, limit: int = 100, offset: int = 0) -> list[T]:
    return list(db.scalars(owned_select(model, user_id).limit(limit).offset(offset)))

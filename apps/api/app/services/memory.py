"""User-controlled memory.

Rules (PRD FR-02, technical doc §9):
- Only APPROVED memories ever reach a prompt.
- Model suggestions start as PROPOSED and wait for the user.
- Deleting a memory erases its text; only an empty tombstone remains for the audit trail.
- Retrieval is keyword relevance only, and every reply records which memories it used.
"""

from __future__ import annotations

import re

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import AppError, ErrorCategory, not_found
from app.db.base import utcnow
from app.db.models import Memory, MemoryStatus, User
from app.db.repository import get_owned, owned_select
from app.schemas.memory import MemoryUpdate
from app.services import audit

MAX_MEMORIES_IN_PROMPT = 5
MAX_ACTIVE_MEMORIES = 1000

_WORD = re.compile(r"[a-z0-9][a-z0-9'+#.-]*")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "like",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "please",
        "should",
        "so",
        "tell",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "user",
        "said",
    ]
)


def _terms(text: str) -> set[str]:
    return {w.strip(".'") for w in _WORD.findall(text.lower()) if len(w) >= 3 and w not in _STOPWORDS}


def _active(user_id: str) -> Select[tuple[Memory]]:
    return owned_select(Memory, user_id).where(Memory.deleted_at.is_(None))


def list_memories(db: DbSession, user: User, status: MemoryStatus | None = None) -> list[Memory]:
    query = _active(user.id)
    if status is not None:
        query = query.where(Memory.status == status)
    return list(db.scalars(query.order_by(Memory.updated_at.desc())))


def get_memory(db: DbSession, user: User, memory_id: str) -> Memory:
    memory = get_owned(db, Memory, memory_id, user.id)
    if memory is None or memory.deleted_at is not None:
        raise not_found("Memory")
    return memory


def _ensure_capacity(db: DbSession, user: User) -> None:
    count = db.scalar(select(func.count()).select_from(_active(user.id).subquery())) or 0
    if count >= MAX_ACTIVE_MEMORIES:
        raise AppError(ErrorCategory.CONFLICT, "Memory limit reached. Delete some memories first.")


def create_by_user(db: DbSession, user: User, content: str) -> Memory:
    """A memory the user typed in themselves is approved by definition."""
    _ensure_capacity(db, user)
    memory = Memory(
        user_id=user.id, content=content.strip(), source="user", status=MemoryStatus.APPROVED, approved=True
    )
    db.add(memory)
    db.flush()
    audit.record(db, action="memory.create", result="success", user_id=user.id, target=memory.id)
    db.commit()
    return memory


def propose(db: DbSession, user: User, contents: list[str], *, conversation_id: str) -> list[Memory]:
    """Store model suggestions as PROPOSED. Duplicates of existing memories are skipped."""
    existing = {m.content.strip().lower() for m in list_memories(db, user)}
    created: list[Memory] = []
    for content in contents:
        normalized = content.strip()
        if not normalized or normalized.lower() in existing:
            continue
        memory = Memory(
            user_id=user.id,
            content=normalized,
            source="chat",
            status=MemoryStatus.PROPOSED,
            approved=False,
            conversation_id=conversation_id,
        )
        db.add(memory)
        existing.add(normalized.lower())
        created.append(memory)
    if created:
        db.flush()
        audit.record(
            db,
            action="memory.propose",
            result="success",
            user_id=user.id,
            actor="assistant",
            metadata={"memory_ids": [m.id for m in created]},
        )
    return created


def update(db: DbSession, user: User, memory_id: str, change: MemoryUpdate) -> Memory:
    memory = get_memory(db, user, memory_id)
    fields = change.model_fields_set
    if "content" in fields:
        if change.content is None:
            raise AppError(ErrorCategory.VALIDATION, "Memory text cannot be empty")
        memory.content = change.content.strip()
    if "status" in fields and change.status is not None:
        memory.status = MemoryStatus(change.status)
    # `approved` mirrors status so both names in the docs mean the same thing.
    memory.approved = memory.status == MemoryStatus.APPROVED
    memory.updated_at = utcnow()
    audit.record(
        db,
        action="memory.update",
        result="success",
        user_id=user.id,
        target=memory.id,
        # Field names and the new status only; memory text is personal data and stays out of the audit log.
        metadata={"fields": sorted(fields), "status": memory.status.value},
    )
    db.commit()
    return memory


def delete(db: DbSession, user: User, memory_id: str) -> None:
    memory = get_memory(db, user, memory_id)
    memory.content = ""
    memory.status = MemoryStatus.REJECTED
    memory.approved = False
    memory.deleted_at = utcnow()
    audit.record(db, action="memory.delete", result="success", user_id=user.id, target=memory.id)
    db.commit()


def relevant_for(db: DbSession, user: User, text: str) -> list[Memory]:
    """Approved memories sharing meaningful words with `text`, best matches first."""
    query_terms = _terms(text)
    if not query_terms:
        return []
    approved = db.scalars(_active(user.id).where(Memory.status == MemoryStatus.APPROVED))
    scored = [(len(query_terms & _terms(m.content)), m) for m in approved]
    ranked = sorted((s for s in scored if s[0] > 0), key=lambda s: (s[0], s[1].updated_at), reverse=True)
    return [m for _, m in ranked[:MAX_MEMORIES_IN_PROMPT]]


def by_ids(db: DbSession, user: User, ids: list[str]) -> dict[str, Memory]:
    if not ids:
        return {}
    return {m.id: m for m in db.scalars(owned_select(Memory, user.id).where(Memory.id.in_(ids)))}

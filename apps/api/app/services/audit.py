"""Audit trail writer.

Audit events record who did what to which target and with what result.
Metadata is always passed through redaction before it is stored.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.core.redaction import redact, redact_text
from app.db.models import AuditEvent


def record(
    db: Session,
    *,
    action: str,
    result: str,
    user_id: str | None,
    actor: str = "user",
    target: str = "",
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Add an audit event to the current transaction; the caller commits it with the change it describes."""
    event = AuditEvent(
        user_id=user_id,
        actor=actor,
        action=action,
        target=redact_text(target)[:500],
        result=result,
        request_id=request_id_var.get(),
        metadata_sanitized=redact(metadata or {}),
    )
    db.add(event)
    return event

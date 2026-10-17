"""Approvals: one action, one approval, bound to an exact payload.

An approval is only usable when all of these hold at execution time:
  1. its status is `approved` (not pending, rejected, expired, or already consumed),
  2. the payload hash still matches the step about to run,
  3. it has not expired,
  4. the permission check still refuses to run the step automatically.
The run engine re-checks all four immediately before executing, then marks the
approval `consumed` in the same transaction, so it can never be used twice.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session as DbSession

from app.core.errors import AppError, ErrorCategory, not_found
from app.db.base import utcnow
from app.db.models import Approval, ApprovalStatus, AutomationRun, RunStep, User
from app.db.repository import get_owned, owned_select
from app.services import audit, notifications, policy

APPROVAL_TTL_MINUTES = 60


def payload_hash(step_type: str, params: dict[str, Any]) -> str:
    """Stable hash of exactly what will run. Any change to type or parameters changes the hash."""
    canonical = json.dumps({"type": step_type, "params": params}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def describe_payload(step_type: str, params: dict[str, Any]) -> str:
    return json.dumps({"type": step_type, "params": params}, indent=2, sort_keys=True)[:4000]


def create_for_step(
    db: DbSession, *, run: AutomationRun, step: RunStep, step_type: str, params: dict[str, Any], automation_name: str
) -> Approval:
    target = str(params.get("target") or params.get("project") or "internal")
    approval = Approval(
        run_id=run.id,
        step_id=step.id,
        user_id=run.user_id,
        action_type=step_type,
        action_summary=f"{automation_name}: step {step.step_index + 1} wants to run '{step_type}'",
        target=target[:500],
        payload_preview=describe_payload(step_type, params),
        payload_hash=payload_hash(step_type, params),
        risk_explanation=policy.risk_explanation(step_type, policy.risk_of(step_type)),
        likely_consequence=policy.consequence_of(step_type),
        expires_at=utcnow() + timedelta(minutes=APPROVAL_TTL_MINUTES),
    )
    db.add(approval)
    db.flush()
    notifications.create(
        db,
        user_id=run.user_id,
        type="approval_needed",
        message=f"'{automation_name}' is waiting for your approval to run '{step_type}'.",
        link=f"/approvals?id={approval.id}",
    )
    audit.record(
        db,
        action="approval.requested",
        result="pending",
        user_id=run.user_id,
        actor="automation",
        target=approval.id,
        metadata={"run_id": run.id, "step_type": step_type, "payload_hash": approval.payload_hash},
    )
    return approval


def expire_due(db: DbSession, user: User) -> int:
    """Mark overdue pending approvals as expired. Run before any read, so the inbox is never stale."""
    rows = db.scalars(
        owned_select(Approval, user.id).where(
            Approval.status == ApprovalStatus.PENDING, Approval.expires_at <= utcnow()
        )
    ).all()
    for approval in rows:
        approval.status = ApprovalStatus.EXPIRED
        approval.decided_at = utcnow()
        audit.record(
            db, action="approval.expired", result="expired", user_id=user.id, actor="system", target=approval.id
        )
    if rows:
        db.commit()
    return len(rows)


def list_for_user(db: DbSession, user: User, status: ApprovalStatus | None = None) -> list[Approval]:
    expire_due(db, user)
    query = owned_select(Approval, user.id)
    if status is not None:
        query = query.where(Approval.status == status)
    return list(db.scalars(query.order_by(Approval.created_at.desc()).limit(100)))


def get(db: DbSession, user: User, approval_id: str) -> Approval:
    approval = get_owned(db, Approval, approval_id, user.id)
    if approval is None:
        raise not_found("Approval")
    return approval


def _require_pending(approval: Approval) -> None:
    if approval.status != ApprovalStatus.PENDING:
        raise AppError(
            ErrorCategory.CONFLICT,
            f"This approval is already {approval.status.value} and cannot be changed.",
        )
    if approval.expires_at <= utcnow():
        raise AppError(
            ErrorCategory.CONFLICT, "This approval has expired. Run the automation again if you still want it."
        )


def approve(db: DbSession, user: User, approval_id: str, reason: str | None = None) -> Approval:
    approval = get(db, user, approval_id)
    expire_due(db, user)
    db.refresh(approval)
    _require_pending(approval)

    approval.status = ApprovalStatus.APPROVED
    approval.decided_at = utcnow()
    approval.decision_reason = reason
    audit.record(
        db,
        action="approval.approved",
        result="success",
        user_id=user.id,
        target=approval.id,
        metadata={"run_id": approval.run_id, "step_type": approval.action_type, "payload_hash": approval.payload_hash},
    )
    db.commit()
    return approval


def reject(db: DbSession, user: User, approval_id: str, reason: str | None = None) -> Approval:
    approval = get(db, user, approval_id)
    expire_due(db, user)
    db.refresh(approval)
    _require_pending(approval)

    approval.status = ApprovalStatus.REJECTED
    approval.decided_at = utcnow()
    approval.decision_reason = reason
    audit.record(
        db,
        action="approval.rejected",
        result="success",
        user_id=user.id,
        target=approval.id,
        metadata={"run_id": approval.run_id, "step_type": approval.action_type},
    )
    db.commit()
    return approval


def consume(db: DbSession, approval: Approval, *, step_type: str, params: dict[str, Any]) -> None:
    """Final gate, called inside the run transaction immediately before the step executes."""
    if approval.status != ApprovalStatus.APPROVED:
        raise AppError(ErrorCategory.FORBIDDEN, f"Approval is {approval.status.value}, not approved")
    if approval.expires_at <= utcnow():
        raise AppError(ErrorCategory.FORBIDDEN, "Approval expired before the step could run")
    if approval.payload_hash != payload_hash(step_type, params):
        raise AppError(ErrorCategory.FORBIDDEN, "The action changed after it was approved")
    approval.status = ApprovalStatus.CONSUMED
    approval.consumed_at = utcnow()

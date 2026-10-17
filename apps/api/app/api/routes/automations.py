"""Routes for automations, runs, approvals and notifications."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, LimiterDep, SettingsDep
from app.core.errors import AppError, ErrorCategory
from app.core.rate_limit import enforce
from app.db.base import utcnow
from app.db.models import (
    Approval,
    ApprovalStatus,
    Automation,
    AutomationRun,
    RunStatus,
    RunStep,
    TriggerType,
)
from app.db.repository import owned_select
from app.schemas.automation import (
    ApprovalDecision,
    ApprovalOut,
    ApprovalStatusLiteral,
    AutomationCreate,
    AutomationDetail,
    AutomationOut,
    AutomationUpdate,
    NotificationOut,
    RunDetail,
    RunOut,
    RunStepOut,
)
from app.services import approvals as approval_service
from app.services import audit, automation, notifications, policy
from app.workers import queue

automations_router = APIRouter(prefix="/api/automations", tags=["automations"])
runs_router = APIRouter(prefix="/api/runs", tags=["runs"])
approvals_router = APIRouter(prefix="/api/approvals", tags=["approvals"])
notifications_router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _run_out(run: AutomationRun) -> RunOut:
    return RunOut.model_validate(run)


def _latest_run(db: DbDep, automation_id: str) -> AutomationRun | None:
    return db.scalars(
        select(AutomationRun)
        .where(AutomationRun.automation_id == automation_id)
        .order_by(AutomationRun.created_at.desc())
        .limit(1)
    ).first()


def _detail(db: DbDep, row: Automation) -> AutomationDetail:
    # Risk is computed here so the UI never has to classify a step itself.
    risks: list[dict[str, str]] = []
    for step in row.definition.get("steps", []) if isinstance(row.definition, dict) else []:
        step_type = str(step.get("type", "")) if isinstance(step, dict) else ""
        try:
            decision = policy.decide(step_type, row.permission_policy)
            risks.append(
                {
                    "type": step_type,
                    "risk": decision.risk.value,
                    "automatic": "yes" if decision.allowed_automatically else "no",
                    "reason": decision.reason,
                }
            )
        except policy.UnknownStepError:
            risks.append({"type": step_type, "risk": "prohibited", "automatic": "no", "reason": "Unknown step type."})

    last = _latest_run(db, row.id)
    hint = f"Runs on schedule: {row.cron}" if row.trigger_type == TriggerType.SCHEDULE and row.enabled else None
    if row.trigger_type == TriggerType.SCHEDULE and not row.enabled:
        hint = "Disabled — it will not run on its schedule."
    return AutomationDetail.model_validate(
        {
            **{c.name: getattr(row, c.name) for c in row.__table__.columns},
            "step_risks": risks,
            "last_run": _run_out(last) if last else None,
            "next_run_hint": hint,
        }
    )


@automations_router.get("", response_model=list[AutomationOut])
def list_automations(user: CurrentUser, db: DbDep) -> list[AutomationOut]:
    rows = db.scalars(owned_select(Automation, user.id).order_by(Automation.created_at.desc()))
    return [AutomationOut.model_validate(r) for r in rows]


@automations_router.post("", response_model=AutomationOut, status_code=status.HTTP_201_CREATED)
def create_automation(body: AutomationCreate, user: CurrentUser, db: DbDep) -> AutomationOut:
    automation.validate_definition(body.definition, body.permission_policy)
    row = Automation(
        user_id=user.id,
        name=body.name.strip(),
        trigger_type=TriggerType(body.trigger_type),
        cron=(body.cron or None),
        enabled=body.enabled,
        definition=body.definition,
        permission_policy=body.permission_policy,
    )
    db.add(row)
    db.flush()
    audit.record(db, action="automation.create", result="success", user_id=user.id, target=row.id)
    db.commit()
    return AutomationOut.model_validate(row)


@automations_router.get("/{automation_id}", response_model=AutomationDetail)
def get_automation(automation_id: str, user: CurrentUser, db: DbDep) -> AutomationDetail:
    return _detail(db, automation.get_automation(db, user, automation_id))


@automations_router.patch("/{automation_id}", response_model=AutomationDetail)
def update_automation(automation_id: str, body: AutomationUpdate, user: CurrentUser, db: DbDep) -> AutomationDetail:
    row = automation.get_automation(db, user, automation_id)
    fields = body.model_fields_set
    definition = body.definition if body.definition is not None else row.definition
    permission_policy = body.permission_policy if body.permission_policy is not None else row.permission_policy
    if "definition" in fields or "permission_policy" in fields:
        automation.validate_definition(definition, permission_policy)
        row.definition = definition
        row.permission_policy = permission_policy
        # Each stored definition change is a new version; runs record the version they executed.
        row.version += 1
    if "name" in fields and body.name:
        row.name = body.name.strip()
    if "trigger_type" in fields and body.trigger_type is not None:
        row.trigger_type = TriggerType(body.trigger_type)
    if "cron" in fields:
        row.cron = body.cron or None
    if "enabled" in fields and body.enabled is not None:
        row.enabled = body.enabled
    if row.trigger_type == TriggerType.SCHEDULE and not row.cron:
        raise AppError(
            ErrorCategory.VALIDATION,
            "A scheduled automation needs a cron expression",
            fields=[{"field": "cron", "message": "For example '0 8 * * *' for 8am daily"}],
        )
    row.updated_at = utcnow()
    audit.record(
        db,
        action="automation.update",
        result="success",
        user_id=user.id,
        target=row.id,
        metadata={"fields": sorted(fields), "version": row.version},
    )
    db.commit()
    return _detail(db, row)


@automations_router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation(automation_id: str, user: CurrentUser, db: DbDep) -> Response:
    row = automation.get_automation(db, user, automation_id)
    db.delete(row)
    audit.record(db, action="automation.delete", result="success", user_id=user.id, target=automation_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@automations_router.get("/{automation_id}/runs", response_model=list[RunOut])
def list_runs(automation_id: str, user: CurrentUser, db: DbDep) -> list[RunOut]:
    automation.get_automation(db, user, automation_id)
    rows = db.scalars(
        owned_select(AutomationRun, user.id)
        .where(AutomationRun.automation_id == automation_id)
        .order_by(AutomationRun.created_at.desc())
        .limit(50)
    )
    return [_run_out(r) for r in rows]


@automations_router.post("/{automation_id}/run", response_model=RunOut)
def run_automation(
    automation_id: str,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> RunOut:
    enforce(limiter, f"run:user:{user.id}", settings.run_rate_limit_per_minute, 60)
    row = automation.get_automation(db, user, automation_id)
    # The header is required by the API contract; generate one only when a client omits it.
    client_key = (idempotency_key or f"manual:{uuid.uuid4().hex}").strip()
    run, created = automation.enqueue_run(
        db, settings, user, row, trigger=TriggerType.MANUAL, client_idempotency_key=client_key
    )
    if created:
        queue.run_or_enqueue(db, settings, run.id)
        response.status_code = status.HTTP_202_ACCEPTED
    else:
        # Same key as before: the existing run is the answer, and nothing runs twice.
        response.status_code = status.HTTP_200_OK
    db.refresh(run)
    return _run_out(run)


@runs_router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, user: CurrentUser, db: DbDep) -> RunDetail:
    run = automation.get_run(db, user, run_id)
    approval_service.expire_due(db, user)
    steps = db.scalars(select(RunStep).where(RunStep.run_id == run.id).order_by(RunStep.step_index)).all()
    pending = db.scalars(
        select(Approval).where(Approval.run_id == run.id, Approval.status == ApprovalStatus.PENDING)
    ).first()
    row = db.get(Automation, run.automation_id)
    return RunDetail.model_validate(
        {
            **{c.name: getattr(run, c.name) for c in run.__table__.columns},
            "automation_name": row.name if row else "Deleted automation",
            "steps": [RunStepOut.model_validate(s) for s in steps],
            "pending_approval_id": pending.id if pending else None,
        }
    )


@runs_router.post("/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: str, user: CurrentUser, db: DbDep) -> RunOut:
    return _run_out(automation.request_cancel(db, user, run_id))


@approvals_router.get("", response_model=list[ApprovalOut])
def list_approvals(
    user: CurrentUser,
    db: DbDep,
    status_filter: Annotated[ApprovalStatusLiteral | None, Query(alias="status")] = "pending",
) -> list[ApprovalOut]:
    rows = approval_service.list_for_user(db, user, ApprovalStatus(status_filter) if status_filter else None)
    return [ApprovalOut.model_validate(a) for a in rows]


@approvals_router.post("/{approval_id}/approve", response_model=ApprovalOut)
def approve(
    approval_id: str, body: ApprovalDecision, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> ApprovalOut:
    approval = approval_service.approve(db, user, approval_id, body.reason)
    # Resume the parked run so the approved step executes exactly once.
    queue.run_or_enqueue(db, settings, approval.run_id)
    db.refresh(approval)
    return ApprovalOut.model_validate(approval)


@approvals_router.post("/{approval_id}/reject", response_model=ApprovalOut)
def reject(
    approval_id: str, body: ApprovalDecision, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> ApprovalOut:
    approval = approval_service.reject(db, user, approval_id, body.reason)
    run = db.get(AutomationRun, approval.run_id)
    if run is not None and run.status == RunStatus.AWAITING_APPROVAL:
        queue.run_or_enqueue(db, settings, run.id)
    db.refresh(approval)
    return ApprovalOut.model_validate(approval)


@notifications_router.get("", response_model=list[NotificationOut])
def list_notifications(user: CurrentUser, db: DbDep, unread: bool = False) -> list[NotificationOut]:
    return [NotificationOut.model_validate(n) for n in notifications.list_for_user(db, user, unread_only=unread)]


@notifications_router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: str, user: CurrentUser, db: DbDep) -> NotificationOut:
    return NotificationOut.model_validate(notifications.mark_read(db, user, notification_id))


@notifications_router.post("/read-all", response_model=dict[str, int])
def mark_all_read(user: CurrentUser, db: DbDep) -> dict[str, int]:
    return {"updated": notifications.mark_all_read(db, user)}

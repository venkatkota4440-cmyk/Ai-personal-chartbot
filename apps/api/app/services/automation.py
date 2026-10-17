"""The automation engine.

Lifecycle (technical documentation §7), enforced here and nowhere else:
 1. A trigger creates a run with status `queued` and a unique idempotency key.
    A repeated key returns the existing run instead of creating a second one.
 2. The worker takes a lock on the run and checks the automation is enabled and owned.
 3. The stored definition is validated against a strict schema.
 4. Every step is classified by the policy service.
 5. Low-risk allowlisted steps execute; a step needing approval creates an approval
    record and parks the run in `awaiting_approval`.
 6. On approval the payload hash, expiry, status and permissions are re-checked, then
    the approval is consumed and the step runs exactly once.
 7. Steps run with a timeout, bounded retries and a cancellation check between each.
 8. The run ends in one explicit terminal state and writes a notification and audit events.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory, not_found
from app.db.base import utcnow
from app.db.models import (
    Approval,
    ApprovalStatus,
    Automation,
    AutomationRun,
    RiskLevel,
    RunStatus,
    RunStep,
    StepStatus,
    TriggerType,
    User,
)
from app.db.repository import get_owned, owned_select
from app.services import approvals, audit, notifications, policy, steps

logger = logging.getLogger(__name__)

MAX_STEPS = 25
MAX_ATTEMPTS = 3
STEP_TIMEOUT_SECONDS = 30.0
# A run whose worker died is retaken after this long, so a crash cannot park a run forever.
LOCK_TIMEOUT_SECONDS = 300.0

_TERMINAL = {RunStatus.SUCCEEDED, RunStatus.PARTIALLY_SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}


class StepSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    """Strict schema for a stored workflow. Anything else is rejected before anything runs."""

    model_config = ConfigDict(extra="forbid")

    steps: list[StepSpec] = Field(min_length=1, max_length=MAX_STEPS)


class PermissionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_allowed: list[str] = Field(default_factory=list, max_length=50)
    require_approval: list[str] = Field(default_factory=list, max_length=50)


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    status: RunStatus


def validate_definition(definition: dict[str, Any], permission_policy: dict[str, Any]) -> WorkflowDefinition:
    """Validate shape, then confirm every step type is known. Used on save and before each run."""
    try:
        parsed = WorkflowDefinition.model_validate(definition)
        PermissionPolicy.model_validate(permission_policy)
    except ValidationError as exc:
        raise AppError(
            ErrorCategory.VALIDATION,
            "The workflow definition is not valid",
            fields=[
                {"field": ".".join(str(p) for p in e.get("loc", ())), "message": str(e.get("msg"))}
                for e in exc.errors()[:10]
            ],
        ) from None

    unknown = [s.type for s in parsed.steps if s.type not in policy.RISK_BY_STEP]
    if unknown:
        raise AppError(
            ErrorCategory.VALIDATION,
            f"Unknown step type(s): {', '.join(sorted(set(unknown)))}",
            fields=[{"field": "definition.steps", "message": "Use a step type this server supports"}],
        )
    prohibited = [s.type for s in parsed.steps if policy.risk_of(s.type) == RiskLevel.PROHIBITED]
    if prohibited:
        raise AppError(ErrorCategory.FORBIDDEN, f"These steps are never allowed: {', '.join(sorted(set(prohibited)))}")
    return parsed


def derive_idempotency_key(user_id: str, automation_id: str, client_key: str) -> str:
    """Server-side key, so one user's key can never collide with or probe another's."""
    raw = f"{user_id}:{automation_id}:{client_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_run(db: DbSession, user: User, run_id: str) -> AutomationRun:
    run = get_owned(db, AutomationRun, run_id, user.id)
    if run is None:
        raise not_found("Run")
    return run


def get_automation(db: DbSession, user: User, automation_id: str) -> Automation:
    automation = get_owned(db, Automation, automation_id, user.id)
    if automation is None:
        raise not_found("Automation")
    return automation


def enqueue_run(
    db: DbSession,
    settings: Settings,
    user: User,
    automation: Automation,
    *,
    trigger: TriggerType,
    client_idempotency_key: str,
) -> tuple[AutomationRun, bool]:
    """Create a queued run, or return the existing one for a repeated key. (run, created)."""
    if not automation.enabled and trigger != TriggerType.MANUAL:
        raise AppError(ErrorCategory.FORBIDDEN, "This automation is disabled")
    validate_definition(automation.definition, automation.permission_policy)

    key = derive_idempotency_key(user.id, automation.id, client_idempotency_key)
    existing = db.scalars(select(AutomationRun).where(AutomationRun.idempotency_key == key)).first()
    if existing is not None:
        return existing, False

    run = AutomationRun(
        automation_id=automation.id,
        user_id=user.id,
        automation_version=automation.version,
        trigger=trigger,
        status=RunStatus.QUEUED,
        idempotency_key=key,
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        # Two triggers raced on the same key; the other one won and its run is the answer.
        db.rollback()
        existing = db.scalars(select(AutomationRun).where(AutomationRun.idempotency_key == key)).first()
        if existing is None:
            raise
        return existing, False

    audit.record(
        db,
        action="run.queued",
        result="queued",
        user_id=user.id,
        actor="user" if trigger == TriggerType.MANUAL else "system",
        target=run.id,
        metadata={"automation_id": automation.id, "trigger": trigger.value},
    )
    db.commit()
    return run, True


def request_cancel(db: DbSession, user: User, run_id: str) -> AutomationRun:
    run = get_run(db, user, run_id)
    if run.status in _TERMINAL:
        raise AppError(ErrorCategory.CONFLICT, f"This run already finished as {run.status.value}")

    run.cancel_requested = True
    if run.status in (RunStatus.QUEUED, RunStatus.AWAITING_APPROVAL):
        # Nothing is executing, so it is safe to stop immediately.
        _finish(
            db,
            run,
            RunStatus.CANCELLED,
            "Cancelled before it ran." if run.status == RunStatus.QUEUED else "Cancelled while waiting for approval.",
        )
        for approval in db.scalars(
            owned_select(Approval, user.id).where(Approval.run_id == run.id, Approval.status == ApprovalStatus.PENDING)
        ):
            approval.status = ApprovalStatus.EXPIRED
            approval.decided_at = utcnow()
    audit.record(db, action="run.cancel_requested", result="success", user_id=user.id, target=run.id)
    db.commit()
    return run


def _finish(db: DbSession, run: AutomationRun, status: RunStatus, summary: str) -> None:
    run.status = status
    run.finished_at = utcnow()
    run.output_summary = summary[:4000]
    run.locked_by = None
    run.locked_at = None
    kind = {
        RunStatus.SUCCEEDED: "run_succeeded",
        RunStatus.PARTIALLY_SUCCEEDED: "run_partial",
        RunStatus.FAILED: "run_failed",
        RunStatus.CANCELLED: "run_failed",
    }[status]
    automation = db.get(Automation, run.automation_id)
    name = automation.name if automation else "Automation"
    notifications.create(
        db,
        user_id=run.user_id,
        type=kind,
        message=f"'{name}' finished: {status.value}.",
        link=f"/automations?run={run.id}",
    )
    audit.record(
        db,
        action="run.finished",
        result=status.value,
        user_id=run.user_id,
        actor="automation",
        target=run.id,
        metadata={"status": status.value},
    )


def _acquire_lock(db: DbSession, run: AutomationRun, worker_id: str) -> bool:
    """One worker at a time. A stale lock from a crashed worker is retaken after LOCK_TIMEOUT_SECONDS."""
    now = utcnow()
    if run.locked_by and run.locked_at and (now - run.locked_at).total_seconds() < LOCK_TIMEOUT_SECONDS:
        return False
    run.locked_by = worker_id
    run.locked_at = now
    db.commit()
    return True


def _step_rows(db: DbSession, run: AutomationRun) -> dict[int, RunStep]:
    rows = db.scalars(select(RunStep).where(RunStep.run_id == run.id)).all()
    return {row.step_index: row for row in rows}


def _ensure_step_row(db: DbSession, run: AutomationRun, index: int, step_type: str) -> RunStep:
    existing = _step_rows(db, run).get(index)
    if existing is not None:
        return existing
    row = RunStep(run_id=run.id, user_id=run.user_id, step_index=index, type=step_type, status=StepStatus.PENDING)
    db.add(row)
    db.flush()
    return row


def _approval_for(db: DbSession, run: AutomationRun, step: RunStep) -> Approval | None:
    return db.scalars(
        select(Approval)
        .where(Approval.run_id == run.id, Approval.step_id == step.id)
        .order_by(Approval.created_at.desc())
    ).first()


def execute_run(db: DbSession, run_id: str, *, worker_id: str | None = None) -> RunOutcome:
    """Run or resume one run to its next stopping point. Safe to call again after a crash."""
    worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
    run = db.get(AutomationRun, run_id)
    if run is None:
        raise not_found("Run")
    if run.status in _TERMINAL:
        return RunOutcome(run.id, run.status)

    if not _acquire_lock(db, run, worker_id):
        logger.info("run already locked by another worker", extra={"run_id": run.id})
        return RunOutcome(run.id, run.status)

    user = db.get(User, run.user_id)
    automation = db.get(Automation, run.automation_id)
    if user is None or automation is None:
        _finish(db, run, RunStatus.FAILED, "The automation or account no longer exists.")
        db.commit()
        return RunOutcome(run.id, run.status)

    if run.cancel_requested:
        _finish(db, run, RunStatus.CANCELLED, "Cancelled before execution.")
        db.commit()
        return RunOutcome(run.id, run.status)

    try:
        definition = validate_definition(automation.definition, automation.permission_policy)
    except AppError as exc:
        run.error_category = exc.category.value
        run.error_message_sanitized = exc.message
        _finish(db, run, RunStatus.FAILED, f"The workflow is not valid: {exc.message}")
        db.commit()
        return RunOutcome(run.id, run.status)

    if run.started_at is None:
        run.started_at = utcnow()
    run.status = RunStatus.RUNNING
    db.commit()

    context = steps.StepContext(db=db, user=user, run_id=run.id)
    failures: list[str] = []
    completed = 0

    for index, spec in enumerate(definition.steps):
        db.refresh(run)
        if run.cancel_requested:
            _finish(db, run, RunStatus.CANCELLED, f"Cancelled after {completed} of {len(definition.steps)} step(s).")
            db.commit()
            return RunOutcome(run.id, run.status)

        row = _ensure_step_row(db, run, index, spec.type)
        if row.status in (StepStatus.SUCCEEDED, StepStatus.SKIPPED):
            if row.output_summary:
                context.previous[f"{index}:{spec.type}"] = row.output_summary
            completed += 1
            continue

        decision = policy.decide(spec.type, automation.permission_policy)
        row.risk_level = decision.risk

        if decision.risk == RiskLevel.PROHIBITED:
            row.status = StepStatus.BLOCKED
            row.error_message_sanitized = decision.reason
            row.finished_at = utcnow()
            failures.append(f"Step {index + 1} ({spec.type}) is not allowed.")
            audit.record(
                db, action="step.blocked", result="prohibited", user_id=user.id, actor="automation", target=row.id
            )
            db.commit()
            continue

        if not decision.allowed_automatically:
            approval = _approval_for(db, run, row)
            if approval is None or approval.status in (ApprovalStatus.EXPIRED, ApprovalStatus.REJECTED):
                if approval is not None and approval.status == ApprovalStatus.REJECTED:
                    row.status = StepStatus.SKIPPED
                    row.error_message_sanitized = "You rejected this action."
                    row.finished_at = utcnow()
                    failures.append(f"Step {index + 1} ({spec.type}) was rejected.")
                    db.commit()
                    continue
                if decision.risk == RiskLevel.MEDIUM and spec.type not in set(
                    automation.permission_policy.get("require_approval", [])
                ):
                    # Medium risk that the automation never enabled: refuse rather than ask.
                    row.status = StepStatus.BLOCKED
                    row.error_message_sanitized = decision.reason
                    row.finished_at = utcnow()
                    failures.append(f"Step {index + 1} ({spec.type}) is not enabled for this automation.")
                    db.commit()
                    continue
                approvals.create_for_step(
                    db, run=run, step=row, step_type=spec.type, params=spec.params, automation_name=automation.name
                )
                row.status = StepStatus.AWAITING_APPROVAL
                run.status = RunStatus.AWAITING_APPROVAL
                run.locked_by = None
                run.locked_at = None
                db.commit()
                return RunOutcome(run.id, run.status)

            if approval.status == ApprovalStatus.PENDING:
                run.status = RunStatus.AWAITING_APPROVAL
                row.status = StepStatus.AWAITING_APPROVAL
                run.locked_by = None
                run.locked_at = None
                db.commit()
                return RunOutcome(run.id, run.status)

            if approval.status == ApprovalStatus.CONSUMED:
                row.status = StepStatus.SKIPPED
                row.error_message_sanitized = "This approval was already used."
                row.finished_at = utcnow()
                db.commit()
                continue

            try:
                # Final gate: hash, expiry, status. Consumed in the same transaction as the step below.
                approvals.consume(db, approval, step_type=spec.type, params=spec.params)
            except AppError as exc:
                row.status = StepStatus.BLOCKED
                row.error_message_sanitized = exc.message
                row.finished_at = utcnow()
                failures.append(f"Step {index + 1} ({spec.type}): {exc.message}")
                audit.record(
                    db, action="approval.refused_at_execution", result="blocked", user_id=user.id, target=approval.id
                )
                db.commit()
                continue

        ok, summary = _execute_with_retries(db, context, row, spec)
        db.commit()
        if ok:
            completed += 1
            context.previous[f"{index}:{spec.type}"] = summary
        else:
            failures.append(f"Step {index + 1} ({spec.type}) failed.")

    total = len(definition.steps)
    if not failures:
        _finish(db, run, RunStatus.SUCCEEDED, f"All {total} step(s) completed.")
    elif completed:
        _finish(
            db, run, RunStatus.PARTIALLY_SUCCEEDED, f"{completed} of {total} step(s) completed. " + " ".join(failures)
        )
    else:
        run.error_category = "step_failed"
        _finish(db, run, RunStatus.FAILED, " ".join(failures) or "No steps completed.")
    db.commit()
    return RunOutcome(run.id, run.status)


def _execute_with_retries(db: DbSession, context: steps.StepContext, row: RunStep, spec: StepSpec) -> tuple[bool, str]:
    """Run one step, retrying transient failures up to MAX_ATTEMPTS with exponential backoff."""
    row.status = StepStatus.RUNNING
    row.started_at = row.started_at or utcnow()
    row.input_summary = steps_input_summary(spec)
    db.commit()

    last_error = "Unknown error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        row.attempts = attempt
        started = time.monotonic()
        try:
            result = steps.run_step(context, spec.type, spec.params)
            elapsed = time.monotonic() - started
            if elapsed > STEP_TIMEOUT_SECONDS:
                # Handlers are synchronous and short; this catches one that misbehaves.
                raise TimeoutError(f"Step took {elapsed:.1f}s, over the {STEP_TIMEOUT_SECONDS:.0f}s limit")
            row.status = StepStatus.SUCCEEDED
            row.output_summary = result.summary[:4000]
            row.finished_at = utcnow()
            return True, result.summary
        except steps.StepParamsError as exc:
            # A bad definition will not fix itself; do not waste retries on it.
            last_error = str(exc)
            break
        except TimeoutError as exc:
            last_error = str(exc)
        except Exception:
            logger.exception("step failed", extra={"step_type": spec.type, "attempt": attempt})
            last_error = "The step failed with an internal error."
        if attempt < MAX_ATTEMPTS:
            time.sleep(min(2 ** (attempt - 1) * 0.05, 1.0))  # short backoff; real waits belong in the queue

    row.status = StepStatus.FAILED
    row.error_message_sanitized = last_error[:1000]
    row.finished_at = utcnow()
    return False, last_error


def steps_input_summary(spec: StepSpec) -> str:
    keys = ", ".join(sorted(spec.params)) or "no parameters"
    return f"{spec.type} ({keys})"


def resume_after_approval(db: DbSession, settings: Settings, run_id: str) -> RunOutcome:
    """Continue a parked run. Called when an approval is granted."""
    from app.workers import queue

    return queue.run_or_enqueue(db, settings, run_id)

"""The step registry: the only code an automation can run.

Each step is a small typed Python function with validated parameters. There is
no generic "run code" or "call URL" step, so model output or a stored workflow
definition can never execute arbitrary behaviour.

High-risk steps are **connectors**. In this MVP they are stubs that record what
*would* have been sent and return `delivered: False`. Nothing reaches a real
external service, and a run never claims otherwise.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session as DbSession

from app.db.models import Project, Task, TaskStatus, User
from app.db.repository import owned_select
from app.schemas.work import TaskCreate
from app.services import tasks as task_service

logger = logging.getLogger(__name__)


class StepParamsError(Exception):
    """The step's parameters did not match its schema."""


@dataclass
class StepContext:
    db: DbSession
    user: User
    run_id: str
    # Output summaries of earlier steps, so later steps can build on them.
    previous: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StepResult:
    summary: str
    # False whenever a connector did not really deliver anything, so no run can claim success falsely.
    delivered: bool = True
    data: dict[str, Any] = field(default_factory=dict)


class StepHandler(Protocol):
    def __call__(self, ctx: StepContext, params: dict[str, Any]) -> StepResult: ...


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProjectParams(_Params):
    project: str | None = Field(default=None, max_length=200)


class ReadTasksParams(_Params):
    due: str | None = Field(default=None, pattern="^(overdue|today|week|none)$")
    project: str | None = Field(default=None, max_length=200)


class CreateTaskParams(_Params):
    title: str = Field(min_length=1, max_length=300)
    project: str | None = Field(default=None, max_length=200)
    priority: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")


class TargetParams(_Params):
    """Parameters for the connector stubs: who or what the action would reach."""

    target: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=5000)


class EmptyParams(_Params):
    pass


def _project_by_name(ctx: StepContext, name: str | None) -> Project | None:
    if not name:
        return None
    query = owned_select(Project, ctx.user.id).where(Project.name == name)
    return ctx.db.scalars(query).first()


def _open_tasks(ctx: StepContext, project: Project | None) -> list[Task]:
    query = owned_select(Task, ctx.user.id).where(Task.status != TaskStatus.DONE)
    if project is not None:
        query = query.where(Task.project_id == project.id)
    return list(ctx.db.scalars(query.order_by(Task.due_at.is_(None), Task.due_at)))


def _read_tasks(ctx: StepContext, params: dict[str, Any]) -> StepResult:
    p = ReadTasksParams.model_validate(params)
    project = _project_by_name(ctx, p.project)
    rows = task_service.list_tasks(
        ctx.db,
        ctx.user,
        project_id=project.id if project else None,
        due=p.due,  # type: ignore[arg-type]
    )
    titles = [t.title for t in rows[:20]]
    return StepResult(
        summary=f"Read {len(rows)} task(s)." + (f" First: {titles[0]}" if titles else ""),
        data={"titles": titles, "count": len(rows)},
    )


def _read_project_milestones(ctx: StepContext, params: dict[str, Any]) -> StepResult:
    p = ProjectParams.model_validate(params)
    project = _project_by_name(ctx, p.project)
    if project is None:
        return StepResult(summary=f"No project named '{p.project}' was found.", data={"found": False})
    rows = _open_tasks(ctx, project)
    milestones = [t.title for t in rows if t.title.lower().startswith("milestone")]
    return StepResult(
        summary=f"{project.name}: {len(rows)} open item(s), {len(milestones)} open milestone(s).",
        data={"milestones": milestones, "open": len(rows)},
    )


def _summarize_open_tasks(ctx: StepContext, params: dict[str, Any]) -> StepResult:
    p = ProjectParams.model_validate(params)
    rows = _open_tasks(ctx, _project_by_name(ctx, p.project))
    by_status: dict[str, int] = {}
    for task in rows:
        by_status[task.status.value] = by_status.get(task.status.value, 0) + 1
    parts = ", ".join(f"{count} {status.replace('_', ' ')}" for status, count in sorted(by_status.items()))
    return StepResult(summary=f"Open work: {parts or 'nothing open'}.", data={"by_status": by_status})


def _summarize_priorities(ctx: StepContext, params: dict[str, Any]) -> StepResult:
    EmptyParams.model_validate(params)
    rows = _open_tasks(ctx, None)
    top = [t.title for t in rows if t.priority.value in ("high", "urgent")][:5]
    return StepResult(
        summary=f"{len(top)} high-priority item(s)." + (f" Top: {top[0]}" if top else ""), data={"top": top}
    )


def _identify_blockers(ctx: StepContext, params: dict[str, Any]) -> StepResult:
    p = ProjectParams.model_validate(params)
    rows = _open_tasks(ctx, _project_by_name(ctx, p.project))
    blocked = [t.title for t in rows if t.status == TaskStatus.BLOCKED]
    return StepResult(
        summary=f"{len(blocked)} blocked item(s)." + (f" Including: {blocked[0]}" if blocked else ""),
        data={"blocked": blocked},
    )


def _draft(label: str) -> StepHandler:
    """Drafting steps compose text from what earlier steps found. They never invent facts."""

    def handler(ctx: StepContext, params: dict[str, Any]) -> StepResult:
        EmptyParams.model_validate(params) if not params else ProjectParams.model_validate(params)
        lines = [f"{label} (drafted automatically from your own tasks — not reviewed by a person):"]
        lines.extend(f"- {summary}" for summary in ctx.previous.values())
        if len(lines) == 1:
            lines.append("- Nothing to report.")
        return StepResult(summary="\n".join(lines), data={"draft": True})

    return handler


def _create_internal_task(ctx: StepContext, params: dict[str, Any]) -> StepResult:
    p = CreateTaskParams.model_validate(params)
    project = _project_by_name(ctx, p.project)
    task = task_service.create(
        ctx.db,
        ctx.user,
        TaskCreate(title=p.title, project_id=project.id if project else None, priority=p.priority),
        actor="automation",
    )
    return StepResult(summary=f"Created task '{task.title}'.", data={"task_id": task.id})


def _connector_stub(action: str) -> StepHandler:
    """A high-risk connector that is deliberately not wired to anything real in this MVP."""

    def handler(ctx: StepContext, params: dict[str, Any]) -> StepResult:
        p = TargetParams.model_validate(params)
        logger.info("connector stub invoked", extra={"action": action, "run_id": ctx.run_id})
        return StepResult(
            summary=(
                f"DEMO MODE: {action} to '{p.target}' was prepared but NOT sent. "
                "No external service is connected in this version."
            ),
            delivered=False,
            data={"action": action, "target": p.target, "delivered": False},
        )

    return handler


REGISTRY: dict[str, StepHandler] = {
    "read_tasks": _read_tasks,
    "read_project_milestones": _read_project_milestones,
    "summarize_open_tasks": _summarize_open_tasks,
    "summarize_priorities": _summarize_priorities,
    "identify_blockers": _identify_blockers,
    "draft_briefing": _draft("Daily briefing"),
    "draft_next_week_plan": _draft("Plan for next week"),
    "create_internal_task": _create_internal_task,
    "send_message": _connector_stub("send_message"),
    "publish_report": _connector_stub("publish_report"),
    "publish_social_post": _connector_stub("publish_social_post"),
    "share_file_externally": _connector_stub("share_file"),
    "modify_production_settings": _connector_stub("modify_production_settings"),
}


def run_step(ctx: StepContext, step_type: str, params: dict[str, Any]) -> StepResult:
    handler = REGISTRY.get(step_type)
    if handler is None:
        # Classified but not implemented: refuse rather than silently skip.
        raise StepParamsError(f"Step '{step_type}' is not available in this version")
    try:
        return handler(ctx, params)
    except ValidationError as exc:
        raise StepParamsError(f"Step '{step_type}' has invalid parameters: {exc.error_count()} problem(s)") from None

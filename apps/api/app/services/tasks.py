"""Tasks: owner-scoped CRUD with filters.

Automations also create tasks through `create`, which is why it takes an actor:
a task created by a workflow is marked as such in the audit trail.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import AppError, ErrorCategory, not_found
from app.db.base import utcnow
from app.db.models import Project, Task, TaskPriority, TaskStatus, User
from app.db.repository import get_owned, owned_select
from app.schemas.work import DueFilter, TaskCreate, TaskUpdate
from app.services import audit

MAX_TASKS = 5000


def get(db: DbSession, user: User, task_id: str) -> Task:
    task = get_owned(db, Task, task_id, user.id)
    if task is None:
        raise not_found("Task")
    return task


def _check_project(db: DbSession, user: User, project_id: str | None) -> None:
    """A task may only join a project the same user owns; anything else is "not found"."""
    if project_id is None:
        return
    if get_owned(db, Project, project_id, user.id) is None:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Project not found",
            fields=[{"field": "project_id", "message": "Choose one of your own projects"}],
        )


def _apply_due_filter(query: Select[tuple[Task]], due: DueFilter, timezone: str) -> Select[tuple[Task]]:
    """Due windows are measured in the user's own timezone, then compared in UTC."""
    if due == "none":
        return query.where(Task.due_at.is_(None))
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = ZoneInfo("UTC")
    local_now = datetime.now(zone)
    end_of_today = local_now.replace(hour=23, minute=59, second=59, microsecond=0)
    if due == "overdue":
        return query.where(Task.due_at.is_not(None), Task.due_at < local_now, Task.status != TaskStatus.DONE)
    if due == "today":
        return query.where(Task.due_at.is_not(None), Task.due_at <= end_of_today)
    return query.where(Task.due_at.is_not(None), Task.due_at <= end_of_today + timedelta(days=7))


def list_tasks(
    db: DbSession,
    user: User,
    *,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    project_id: str | None = None,
    due: DueFilter | None = None,
    limit: int = 200,
) -> list[Task]:
    query = owned_select(Task, user.id)
    if status is not None:
        query = query.where(Task.status == status)
    if priority is not None:
        query = query.where(Task.priority == priority)
    if project_id is not None:
        query = query.where(Task.project_id == project_id)
    if due is not None:
        query = _apply_due_filter(query, due, user.timezone)
    # Unfinished first, then by due date (tasks without one last), then newest.
    ordering = (
        (Task.status == TaskStatus.DONE),
        Task.due_at.is_(None),
        Task.due_at,
        Task.created_at.desc(),
    )
    return list(db.scalars(query.order_by(*ordering).limit(limit)))


def create(db: DbSession, user: User, body: TaskCreate, *, actor: str = "user") -> Task:
    _check_project(db, user, body.project_id)
    if db.query(Task).filter(Task.user_id == user.id).count() >= MAX_TASKS:
        raise AppError(ErrorCategory.CONFLICT, "Task limit reached. Delete some tasks first.")
    task = Task(
        user_id=user.id,
        project_id=body.project_id,
        title=body.title.strip(),
        description=body.description.strip(),
        status=TaskStatus(body.status),
        priority=TaskPriority(body.priority),
        due_at=body.due_at,
    )
    db.add(task)
    db.flush()
    audit.record(db, action="task.create", result="success", user_id=user.id, actor=actor, target=task.id)
    db.commit()
    return task


def update(db: DbSession, user: User, task_id: str, body: TaskUpdate) -> Task:
    task = get(db, user, task_id)
    fields = body.model_fields_set
    if "project_id" in fields:
        _check_project(db, user, body.project_id)
        task.project_id = body.project_id
    if "title" in fields and body.title:
        task.title = body.title.strip()
    if "description" in fields and body.description is not None:
        task.description = body.description.strip()
    if "status" in fields and body.status is not None:
        task.status = TaskStatus(body.status)
    if "priority" in fields and body.priority is not None:
        task.priority = TaskPriority(body.priority)
    if "due_at" in fields:
        task.due_at = body.due_at
    task.updated_at = utcnow()
    audit.record(
        db, action="task.update", result="success", user_id=user.id, target=task.id, metadata={"fields": sorted(fields)}
    )
    db.commit()
    return task


def delete(db: DbSession, user: User, task_id: str) -> None:
    task = get(db, user, task_id)
    db.delete(task)
    audit.record(db, action="task.delete", result="success", user_id=user.id, target=task_id)
    db.commit()

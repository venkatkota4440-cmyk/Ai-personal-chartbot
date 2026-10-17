"""Projects: owner-scoped CRUD with task counts."""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import not_found
from app.db.base import utcnow
from app.db.models import Project, ProjectStatus, Task, TaskStatus, User
from app.db.repository import get_owned, owned_select
from app.schemas.work import ProjectCreate, ProjectUpdate, ProjectWithCounts
from app.services import audit


def get(db: DbSession, user: User, project_id: str) -> Project:
    project = get_owned(db, Project, project_id, user.id)
    if project is None:
        raise not_found("Project")
    return project


def _counts(db: DbSession, user: User) -> dict[str, tuple[int, int]]:
    """(total, done) per project id, in one query rather than one per project."""
    rows = db.execute(
        select(
            Task.project_id,
            func.count(Task.id),
            func.sum(case((Task.status == TaskStatus.DONE, 1), else_=0)),
        )
        .where(Task.user_id == user.id, Task.project_id.is_not(None))
        .group_by(Task.project_id)
    ).all()
    return {str(pid): (int(total), int(done or 0)) for pid, total, done in rows}


def with_counts(db: DbSession, user: User, project: Project) -> ProjectWithCounts:
    total, done = _counts(db, user).get(project.id, (0, 0))
    base = ProjectWithCounts.model_validate(
        {**project.__dict__, "task_total": total, "task_done": done, "task_open": total - done}
    )
    return base


def list_projects(db: DbSession, user: User, status: ProjectStatus | None = None) -> list[ProjectWithCounts]:
    query = owned_select(Project, user.id)
    if status is not None:
        query = query.where(Project.status == status)
    projects = list(db.scalars(query.order_by(Project.created_at.desc())))
    counts = _counts(db, user)
    result: list[ProjectWithCounts] = []
    for project in projects:
        total, done = counts.get(project.id, (0, 0))
        result.append(
            ProjectWithCounts.model_validate(
                {**project.__dict__, "task_total": total, "task_done": done, "task_open": total - done}
            )
        )
    return result


def create(db: DbSession, user: User, body: ProjectCreate) -> Project:
    project = Project(
        user_id=user.id,
        name=body.name.strip(),
        description=body.description.strip(),
        status=ProjectStatus(body.status),
    )
    db.add(project)
    db.flush()
    audit.record(db, action="project.create", result="success", user_id=user.id, target=project.id)
    db.commit()
    return project


def update(db: DbSession, user: User, project_id: str, body: ProjectUpdate) -> Project:
    project = get(db, user, project_id)
    fields = body.model_fields_set
    if "name" in fields and body.name:
        project.name = body.name.strip()
    if "description" in fields and body.description is not None:
        project.description = body.description.strip()
    if "status" in fields and body.status is not None:
        project.status = ProjectStatus(body.status)
    project.updated_at = utcnow()
    audit.record(
        db,
        action="project.update",
        result="success",
        user_id=user.id,
        target=project.id,
        metadata={"fields": sorted(fields)},
    )
    db.commit()
    return project


def delete(db: DbSession, user: User, project_id: str) -> None:
    """Deleting a project keeps its tasks; they become unassigned (ON DELETE SET NULL)."""
    project = get(db, user, project_id)
    db.delete(project)
    audit.record(db, action="project.delete", result="success", user_id=user.id, target=project_id)
    db.commit()

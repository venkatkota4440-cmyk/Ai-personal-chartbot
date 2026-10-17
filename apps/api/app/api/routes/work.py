"""Routes for projects and tasks."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbDep
from app.db.models import ProjectStatus, TaskPriority, TaskStatus
from app.schemas.work import (
    DueFilter,
    ProjectCreate,
    ProjectOut,
    ProjectStatusLiteral,
    ProjectUpdate,
    ProjectWithCounts,
    TaskCreate,
    TaskOut,
    TaskPriorityLiteral,
    TaskStatusLiteral,
    TaskUpdate,
)
from app.services import projects, tasks

projects_router = APIRouter(prefix="/api/projects", tags=["projects"])
tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@projects_router.get("", response_model=list[ProjectWithCounts])
def list_projects(
    user: CurrentUser,
    db: DbDep,
    status_filter: Annotated[ProjectStatusLiteral | None, Query(alias="status")] = None,
) -> list[ProjectWithCounts]:
    return projects.list_projects(db, user, ProjectStatus(status_filter) if status_filter else None)


@projects_router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, user: CurrentUser, db: DbDep) -> ProjectOut:
    return ProjectOut.model_validate(projects.create(db, user, body))


@projects_router.get("/{project_id}", response_model=ProjectWithCounts)
def get_project(project_id: str, user: CurrentUser, db: DbDep) -> ProjectWithCounts:
    return projects.with_counts(db, user, projects.get(db, user, project_id))


@projects_router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate, user: CurrentUser, db: DbDep) -> ProjectOut:
    return ProjectOut.model_validate(projects.update(db, user, project_id, body))


@projects_router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, user: CurrentUser, db: DbDep) -> Response:
    projects.delete(db, user, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@tasks_router.get("", response_model=list[TaskOut])
def list_tasks(
    user: CurrentUser,
    db: DbDep,
    status_filter: Annotated[TaskStatusLiteral | None, Query(alias="status")] = None,
    priority: TaskPriorityLiteral | None = None,
    project_id: Annotated[str | None, Query(max_length=36)] = None,
    due: DueFilter | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[TaskOut]:
    rows = tasks.list_tasks(
        db,
        user,
        status=TaskStatus(status_filter) if status_filter else None,
        priority=TaskPriority(priority) if priority else None,
        project_id=project_id,
        due=due,
        limit=limit,
    )
    return [TaskOut.model_validate(t) for t in rows]


@tasks_router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate, user: CurrentUser, db: DbDep) -> TaskOut:
    return TaskOut.model_validate(tasks.create(db, user, body))


@tasks_router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: str, body: TaskUpdate, user: CurrentUser, db: DbDep) -> TaskOut:
    return TaskOut.model_validate(tasks.update(db, user, task_id, body))


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, user: CurrentUser, db: DbDep) -> Response:
    tasks.delete(db, user, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

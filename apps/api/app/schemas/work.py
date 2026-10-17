"""Schemas for projects and tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import StrictModel

ProjectStatusLiteral = Literal["active", "paused", "completed", "archived"]
TaskStatusLiteral = Literal["todo", "in_progress", "blocked", "done"]
TaskPriorityLiteral = Literal["low", "medium", "high", "urgent"]
DueFilter = Literal["overdue", "today", "week", "none"]


def _aware(value: datetime | None) -> datetime | None:
    """Reject naive datetimes: a due date without an offset is ambiguous across timezones."""
    if value is not None and value.tzinfo is None:
        raise ValueError("Use an ISO-8601 timestamp with a timezone, e.g. 2026-10-20T09:00:00Z")
    return value


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    status: ProjectStatusLiteral
    created_at: datetime
    updated_at: datetime


class ProjectWithCounts(ProjectOut):
    task_total: int
    task_done: int
    task_open: int


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    status: ProjectStatusLiteral = "active"


class ProjectUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: ProjectStatusLiteral | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    title: str
    description: str
    status: TaskStatusLiteral
    priority: TaskPriorityLiteral
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskCreate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    project_id: str | None = Field(default=None, max_length=36)
    status: TaskStatusLiteral = "todo"
    priority: TaskPriorityLiteral = "medium"
    due_at: datetime | None = None

    _due = field_validator("due_at")(_aware)


class TaskUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    # Explicit null detaches the task from its project.
    project_id: str | None = Field(default=None, max_length=36)
    status: TaskStatusLiteral | None = None
    priority: TaskPriorityLiteral | None = None
    due_at: datetime | None = None

    _due = field_validator("due_at")(_aware)

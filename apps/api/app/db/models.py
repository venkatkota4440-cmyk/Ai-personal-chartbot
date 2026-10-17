"""Database models for the whole MVP.

Every user-owned table carries user_id so queries can always be scoped to the
authenticated user. All tables are created in M1 so later milestones only add
behaviour, not schema churn; columns added later get their own migrations.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, utcnow


def _enum(enum_cls: type[StrEnum], name: str) -> Enum:
    # VARCHAR + CHECK constraint instead of a native enum type: portable and easy to migrate.
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MemoryStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    EVENT = "event"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROHIBITED = "prohibited"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Stored lower-cased by the auth service so uniqueness is case-insensitive on every database.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    settings: Mapped[UserSettings] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    default_model: Mapped[str] = mapped_column(String(100), default="mock-deterministic", nullable=False)
    notify_run_succeeded: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_run_failed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_approval_needed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # None = keep conversation messages until the user deletes them.
    message_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="settings")


class Session(IdMixin, Base):
    """Server-side session: logout and password changes can revoke it immediately."""

    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="New conversation", nullable=False)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Message(IdMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole, "message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Assistant messages only: which approved memories were in the prompt, so memory use is visible.
    used_memory_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Assistant messages only: confidence, human-review topics, provider/model that produced it.
    flags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Memory(IdMixin, TimestampMixin, Base):
    __tablename__ = "memories"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        _enum(MemoryStatus, "memory_status"), default=MemoryStatus.PROPOSED, nullable=False
    )
    # Kept alongside status because the technical doc names it; the memory service keeps them in sync.
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Where a chat-proposed memory came from, so the user can see the context it was suggested in.
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        _enum(ProjectStatus, "project_status"), default=ProjectStatus.ACTIVE, nullable=False
    )


class Task(IdMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_user_status", "user_id", "status"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        _enum(TaskStatus, "task_status"), default=TaskStatus.TODO, nullable=False
    )
    priority: Mapped[TaskPriority] = mapped_column(
        _enum(TaskPriority, "task_priority"), default=TaskPriority.MEDIUM, nullable=False
    )
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Automation(IdMixin, TimestampMixin, Base):
    __tablename__ = "automations"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_type: Mapped[TriggerType] = mapped_column(_enum(TriggerType, "trigger_type"), nullable=False)
    cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Bumped whenever definition or policy changes; each run records the version it executed.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    permission_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class AutomationRun(IdMixin, Base):
    __tablename__ = "automation_runs"
    __table_args__ = (Index("ix_automation_runs_user_status", "user_id", "status"),)

    automation_id: Mapped[str] = mapped_column(
        ForeignKey("automations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    automation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[TriggerType] = mapped_column(_enum(TriggerType, "run_trigger"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"), default=RunStatus.QUEUED, nullable=False)
    # Globally unique; the automation service derives it from (user, automation, client key) so users cannot collide.
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunStep(IdMixin, Base):
    __tablename__ = "run_steps"
    __table_args__ = (UniqueConstraint("run_id", "step_index", name="uq_run_steps_run_id_step_index"),)

    run_id: Mapped[str] = mapped_column(ForeignKey("automation_runs.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        _enum(StepStatus, "step_status"), default=StepStatus.PENDING, nullable=False
    )
    risk_level: Mapped[RiskLevel | None] = mapped_column(_enum(RiskLevel, "step_risk_level"), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Approval(IdMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_user_status", "user_id", "status"),)

    run_id: Mapped[str] = mapped_column(
        ForeignKey("automation_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    step_id: Mapped[str | None] = mapped_column(ForeignKey("run_steps.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action_summary: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    # What the approval screen shows as "content/data affected"; the hash binds approval to exactly this payload.
    payload_preview: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    likely_consequence: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        _enum(ApprovalStatus, "approval_status"), default=ApprovalStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AuditEvent(IdMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_user_timestamp", "user_id", "timestamp"),)

    # Nullable: failed logins for unknown emails have no user.
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    metadata_sanitized: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Notification(IdMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

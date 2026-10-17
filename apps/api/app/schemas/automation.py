from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auth import StrictModel

TriggerTypeLiteral = Literal["manual", "schedule", "event"]
RunStatusLiteral = Literal[
    "queued", "running", "awaiting_approval", "succeeded", "partially_succeeded", "failed", "cancelled"
]
StepStatusLiteral = Literal[
    "pending", "running", "awaiting_approval", "succeeded", "failed", "skipped", "blocked", "cancelled"
]
RiskLiteral = Literal["low", "medium", "high", "prohibited"]
ApprovalStatusLiteral = Literal["pending", "approved", "rejected", "expired", "consumed"]


class AutomationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    trigger_type: TriggerTypeLiteral
    cron: str | None
    enabled: bool
    version: int
    definition: dict[str, Any]
    permission_policy: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AutomationDetail(AutomationOut):
    # Risk of each step, computed by the backend so the UI never classifies anything itself.
    step_risks: list[dict[str, str]]
    last_run: RunOut | None
    next_run_hint: str | None


class AutomationCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    trigger_type: TriggerTypeLiteral = "manual"
    cron: str | None = Field(default=None, max_length=100)
    enabled: bool = True
    definition: dict[str, Any]
    permission_policy: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _cron_required_for_schedule(self) -> AutomationCreate:
        if self.trigger_type == "schedule" and not (self.cron or "").strip():
            raise ValueError("A scheduled automation needs a cron expression, e.g. '0 8 * * *'")
        return self


class AutomationUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    trigger_type: TriggerTypeLiteral | None = None
    cron: str | None = Field(default=None, max_length=100)
    enabled: bool | None = None
    definition: dict[str, Any] | None = None
    permission_policy: dict[str, Any] | None = None


class RunStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    step_index: int
    type: str
    status: StepStatusLiteral
    risk_level: RiskLiteral | None
    attempts: int
    input_summary: str | None
    output_summary: str | None
    error_message_sanitized: str | None
    started_at: datetime | None
    finished_at: datetime | None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    automation_id: str
    automation_version: int
    trigger: TriggerTypeLiteral
    status: RunStatusLiteral
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    output_summary: str | None
    error_category: str | None
    error_message_sanitized: str | None


class RunDetail(RunOut):
    automation_name: str
    steps: list[RunStepOut]
    pending_approval_id: str | None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    action_type: str
    action_summary: str
    target: str
    payload_preview: str
    payload_hash: str
    risk_explanation: str
    likely_consequence: str
    status: ApprovalStatusLiteral
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    decision_reason: str | None


class ApprovalDecision(StrictModel):
    reason: str | None = Field(default=None, max_length=1000)


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    message: str
    link: str | None
    read_at: datetime | None
    created_at: datetime


AutomationDetail.model_rebuild()

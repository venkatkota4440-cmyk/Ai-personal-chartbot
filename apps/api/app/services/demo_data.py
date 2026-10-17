"""Synthetic starter data, seeded once per new account.

This is **data**, not platform logic: ScamShield AI is just one project row, and
the weekly review is one automation row. Nothing in the engine knows their
names. Everything here is invented for the demo; none of it is real.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session as DbSession

from app.db.base import utcnow
from app.db.models import (
    Automation,
    Project,
    ProjectStatus,
    Task,
    TaskPriority,
    TaskStatus,
    TriggerType,
    User,
)

SCAMSHIELD_NAME = "ScamShield AI"

_PROJECTS: list[dict[str, Any]] = [
    {
        "key": "scamshield",
        "name": SCAMSHIELD_NAME,
        "description": (
            "Detect and report scam websites, apps and messages. Demo workspace with synthetic "
            "milestones; no real threat data is stored here."
        ),
        "status": ProjectStatus.ACTIVE,
        "tasks": [
            ("Milestone 1: define scam signal list", TaskStatus.DONE, TaskPriority.HIGH, 14),
            ("Milestone 2: build lookalike-domain checker", TaskStatus.IN_PROGRESS, TaskPriority.HIGH, 3),
            ("Milestone 3: app-store listing scanner", TaskStatus.TODO, TaskPriority.MEDIUM, 10),
            ("Write takedown request template", TaskStatus.TODO, TaskPriority.MEDIUM, 7),
            ("Decide accuracy target before any public claim", TaskStatus.BLOCKED, TaskPriority.URGENT, 2),
            ("Draft weekly progress report format", TaskStatus.TODO, TaskPriority.LOW, 21),
        ],
    },
    {
        "key": "personal",
        "name": "Personal setup",
        "description": "Getting this assistant set up the way you want it.",
        "status": ProjectStatus.ACTIVE,
        "tasks": [
            ("Add three memories the assistant should know", TaskStatus.TODO, TaskPriority.MEDIUM, 1),
            ("Review the ScamShield weekly review automation", TaskStatus.TODO, TaskPriority.LOW, 5),
        ],
    },
]

# Mirrors §12.3 of the technical documentation. Step types must exist in the step registry.
_SCAMSHIELD_REVIEW: dict[str, Any] = {
    "name": "ScamShield Weekly Review",
    "trigger_type": TriggerType.SCHEDULE,
    "cron": "0 10 * * 1",
    "definition": {
        "steps": [
            {"type": "read_project_milestones", "params": {"project": SCAMSHIELD_NAME}},
            {"type": "summarize_open_tasks", "params": {"project": SCAMSHIELD_NAME}},
            {"type": "identify_blockers", "params": {"project": SCAMSHIELD_NAME}},
            {"type": "draft_next_week_plan", "params": {"project": SCAMSHIELD_NAME}},
            {"type": "publish_report", "params": {"target": "https://example.invalid/scamshield/weekly"}},
        ]
    },
    "permission_policy": {
        "auto_allowed": [
            "read_project_milestones",
            "summarize_open_tasks",
            "identify_blockers",
            "draft_next_week_plan",
        ],
        "require_approval": ["publish_report", "modify_production_settings"],
    },
}

_DAILY_BRIEFING: dict[str, Any] = {
    "name": "Daily Briefing",
    "trigger_type": TriggerType.SCHEDULE,
    "cron": "0 8 * * *",
    "definition": {
        "steps": [
            {"type": "read_tasks", "params": {"due": "today"}},
            {"type": "summarize_priorities", "params": {}},
            {"type": "draft_briefing", "params": {}},
        ]
    },
    "permission_policy": {
        "auto_allowed": ["read_tasks", "summarize_priorities", "draft_briefing"],
        "require_approval": [],
    },
}


def seed_for(db: DbSession, user: User) -> None:
    """Create the starter projects, tasks and automations. Called once, at registration."""
    now = utcnow()
    for spec in _PROJECTS:
        project = Project(user_id=user.id, name=spec["name"], description=spec["description"], status=spec["status"])
        db.add(project)
        db.flush()
        for title, status, priority, due_in_days in spec["tasks"]:
            db.add(
                Task(
                    user_id=user.id,
                    project_id=project.id,
                    title=title,
                    status=status,
                    priority=priority,
                    due_at=now + timedelta(days=due_in_days),
                )
            )

    for spec in (_SCAMSHIELD_REVIEW, _DAILY_BRIEFING):
        db.add(
            Automation(
                user_id=user.id,
                name=spec["name"],
                trigger_type=spec["trigger_type"],
                cron=spec["cron"],
                # Demo automations start disabled: nothing runs on a schedule until the user enables it.
                enabled=False,
                definition=spec["definition"],
                permission_policy=spec["permission_policy"],
            )
        )
    db.flush()

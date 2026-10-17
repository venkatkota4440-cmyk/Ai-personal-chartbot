"""Risk classification and the permission gate.

The backend decides what a step is allowed to do. The model never influences
this: risk is a property of the step *type*, looked up in a fixed table, and an
unknown type is refused rather than assumed safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models import RiskLevel

# Every step type the engine will ever run, with its risk level (PRD §9).
# Nothing outside this table can execute: there is no "run anything" step.
RISK_BY_STEP: dict[str, RiskLevel] = {
    # Low: read internal data, summarise, draft. Safe to run automatically.
    "read_tasks": RiskLevel.LOW,
    "read_project_milestones": RiskLevel.LOW,
    "summarize_priorities": RiskLevel.LOW,
    "summarize_open_tasks": RiskLevel.LOW,
    "identify_blockers": RiskLevel.LOW,
    "draft_briefing": RiskLevel.LOW,
    "draft_next_week_plan": RiskLevel.LOW,
    "classify_text": RiskLevel.LOW,
    "create_internal_task": RiskLevel.LOW,
    # Medium: changes the user's own records. Allowed only if the automation enables it.
    "update_task_status": RiskLevel.MEDIUM,
    "modify_project_record": RiskLevel.MEDIUM,
    # High: leaves the system, spends, deletes, or changes security. Always needs approval.
    "send_message": RiskLevel.HIGH,
    "publish_report": RiskLevel.HIGH,
    "publish_social_post": RiskLevel.HIGH,
    "share_file_externally": RiskLevel.HIGH,
    "delete_data": RiskLevel.HIGH,
    "spend_money": RiskLevel.HIGH,
    "modify_production_settings": RiskLevel.HIGH,
    "change_account_settings": RiskLevel.HIGH,
    # Prohibited: blocked outright, whatever the policy says.
    "harvest_credentials": RiskLevel.PROHIBITED,
    "bypass_access_control": RiskLevel.PROHIBITED,
    "scrape_authenticated_site": RiskLevel.PROHIBITED,
}

# Shown to the user on the approval screen, so the consequence is in plain words.
CONSEQUENCE_BY_STEP: dict[str, str] = {
    "send_message": "The message is sent. It cannot be unsent.",
    "publish_report": "The report becomes visible at the target address.",
    "publish_social_post": "The post goes live on your account and people can see it.",
    "share_file_externally": "People outside this app get access to the file.",
    "delete_data": "The data is removed. This cannot be undone.",
    "spend_money": "Money leaves your account.",
    "modify_production_settings": "Live settings change, which can affect a running service.",
    "change_account_settings": "Your account or security settings change.",
}

_DEFAULT_CONSEQUENCE = "This acts outside the app and cannot be undone automatically."


class UnknownStepError(Exception):
    """Raised for a step type that is not in the table above."""


@dataclass(frozen=True)
class Decision:
    risk: RiskLevel
    allowed_automatically: bool
    reason: str


def risk_of(step_type: str) -> RiskLevel:
    try:
        return RISK_BY_STEP[step_type]
    except KeyError:
        raise UnknownStepError(step_type) from None


def consequence_of(step_type: str) -> str:
    return CONSEQUENCE_BY_STEP.get(step_type, _DEFAULT_CONSEQUENCE)


def risk_explanation(step_type: str, risk: RiskLevel) -> str:
    if risk == RiskLevel.HIGH:
        return (
            f"'{step_type}' is high risk: it acts outside this app or changes something that cannot be "
            "undone from here. It runs only once, with your approval, exactly as shown."
        )
    if risk == RiskLevel.MEDIUM:
        return f"'{step_type}' changes one of your records. It is allowed because this automation enables it."
    return f"'{step_type}' only reads your data or drafts text."


def decide(step_type: str, permission_policy: dict[str, Any]) -> Decision:
    """Classify a step and check it against the automation's own policy."""
    risk = risk_of(step_type)
    auto_allowed = {str(s) for s in permission_policy.get("auto_allowed", [])}
    require_approval = {str(s) for s in permission_policy.get("require_approval", [])}

    if risk == RiskLevel.PROHIBITED:
        return Decision(risk, False, "This action is never allowed, whatever the automation's policy says.")
    if risk == RiskLevel.HIGH:
        # A policy can never downgrade a high-risk step; listing it under auto_allowed has no effect.
        return Decision(risk, False, "High-risk actions always need your approval immediately before they run.")
    if step_type in require_approval:
        return Decision(risk, False, "This automation is configured to ask you before this step.")
    if risk == RiskLevel.MEDIUM:
        allowed = step_type in auto_allowed
        return Decision(
            risk,
            allowed,
            "Enabled for this automation." if allowed else "Medium-risk steps run only if the automation enables them.",
        )
    return Decision(risk, True, "Low-risk step.")

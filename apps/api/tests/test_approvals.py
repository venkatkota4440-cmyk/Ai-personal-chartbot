"""Approval gate: the security properties that stop a high-risk action running twice,
late, or with a different payload than the one shown to the user."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Approval, ApprovalStatus, AuditEvent, Automation, RunStep, StepStatus
from tests.conftest import csrf, register
from tests.test_automation import HIGH_RISK, create_automation, run_now


def start_pending(client: TestClient) -> tuple[str, dict[str, Any]]:
    automation = create_automation(client, HIGH_RISK)
    run_id = run_now(client, automation["id"]).json()["id"]
    approval = client.get("/api/approvals?status=pending").json()[0]
    return run_id, approval


def test_approve_runs_the_step_exactly_once(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    run_id, approval = start_pending(client)

    approved = client.post(f"/api/approvals/{approval['id']}/approve", json={}, headers=csrf(client))
    assert approved.status_code == 200

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "succeeded"
    assert detail["steps"][1]["status"] == "succeeded"
    assert detail["pending_approval_id"] is None

    with session_factory() as db:
        row = db.get(Approval, approval["id"])
        assert row is not None
        assert row.status == ApprovalStatus.CONSUMED  # one-time use
        assert row.consumed_at is not None
        step = db.scalars(select(RunStep).where(RunStep.run_id == run_id, RunStep.step_index == 1)).one()
        assert step.attempts == 1


def test_a_consumed_approval_cannot_be_reused(client: TestClient) -> None:
    register(client)
    _, approval = start_pending(client)
    client.post(f"/api/approvals/{approval['id']}/approve", json={}, headers=csrf(client))

    again = client.post(f"/api/approvals/{approval['id']}/approve", json={}, headers=csrf(client))
    assert again.status_code == 409
    assert "consumed" in again.json()["error"]["message"]


def test_double_approve_before_execution_is_refused(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    """Two approve calls in a row must not execute the action twice."""
    register(client)
    run_id, approval = start_pending(client)
    first = client.post(f"/api/approvals/{approval['id']}/approve", json={}, headers=csrf(client))
    second = client.post(f"/api/approvals/{approval['id']}/approve", json={}, headers=csrf(client))

    assert first.status_code == 200
    assert second.status_code == 409
    with session_factory() as db:
        step = db.scalars(select(RunStep).where(RunStep.run_id == run_id, RunStep.step_index == 1)).one()
        assert step.attempts == 1


def test_expired_approval_cannot_be_approved(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    run_id, approval = start_pending(client)
    with session_factory() as db:
        row = db.get(Approval, approval["id"])
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    response = client.post(f"/api/approvals/{approval['id']}/approve", json={}, headers=csrf(client))
    assert response.status_code == 409
    assert "expired" in response.json()["error"]["message"].lower()
    # The inbox marks it expired rather than leaving it pending for ever.
    assert client.get("/api/approvals?status=pending").json() == []
    assert client.get(f"/api/runs/{run_id}").json()["steps"][1]["status"] == "awaiting_approval"


def test_changed_payload_after_approval_is_refused_at_execution(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """The hash binds the approval to one exact action; editing the workflow invalidates it."""
    register(client)
    automation = create_automation(client, HIGH_RISK)
    run_id = run_now(client, automation["id"]).json()["id"]
    approval = client.get("/api/approvals?status=pending").json()[0]

    with session_factory() as db:
        # The user approves what they were shown...
        row = db.get(Approval, approval["id"])
        assert row is not None
        row.status = ApprovalStatus.APPROVED
        row.decided_at = datetime.now(UTC)
        # ...but the action is swapped for a different target before the worker reaches it.
        automation_row = db.get(Automation, automation["id"])
        assert automation_row is not None
        automation_row.definition = {
            "steps": [
                {"type": "summarize_open_tasks", "params": {}},
                {"type": "publish_report", "params": {"target": "https://attacker.invalid/leak"}},
            ]
        }
        db.commit()

        from app.services.automation import execute_run

        execute_run(db, run_id)
        step = db.scalars(select(RunStep).where(RunStep.run_id == run_id, RunStep.step_index == 1)).one()
        assert step.status == StepStatus.BLOCKED
        assert "changed" in str(step.error_message_sanitized)
        assert db.get(Approval, approval["id"]).status == ApprovalStatus.APPROVED  # never consumed
        blocked = [e for e in db.scalars(select(AuditEvent)) if e.action == "approval.refused_at_execution"]
        assert blocked


def test_reject_stops_the_action(client: TestClient) -> None:
    register(client)
    run_id, approval = start_pending(client)
    rejected = client.post(
        f"/api/approvals/{approval['id']}/reject", json={"reason": "Not ready"}, headers=csrf(client)
    )
    assert rejected.status_code == 200
    assert rejected.json()["decision_reason"] == "Not ready"

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "partially_succeeded"
    assert detail["steps"][1]["status"] == "skipped"
    assert "rejected" in str(detail["steps"][1]["error_message_sanitized"]).lower()


def test_rejected_approval_cannot_then_be_approved(client: TestClient) -> None:
    register(client)
    _, approval = start_pending(client)
    client.post(f"/api/approvals/{approval['id']}/reject", json={}, headers=csrf(client))
    response = client.post(f"/api/approvals/{approval['id']}/approve", json={}, headers=csrf(client))
    assert response.status_code == 409


def test_approvals_are_owner_scoped(app_factory: Callable[[], TestClient]) -> None:
    alice, bob = app_factory(), app_factory()
    register(alice, email="alice@example.com")
    register(bob, email="bob@example.com")
    _, approval = start_pending(alice)

    assert bob.get("/api/approvals?status=pending").json() == []
    assert bob.post(f"/api/approvals/{approval['id']}/approve", json={}, headers=csrf(bob)).status_code == 404
    assert bob.post(f"/api/approvals/{approval['id']}/reject", json={}, headers=csrf(bob)).status_code == 404
    # Alice's approval is untouched by Bob's attempts.
    assert alice.get("/api/approvals?status=pending").json()[0]["id"] == approval["id"]


def test_approval_shows_action_target_and_consequence(client: TestClient) -> None:
    register(client)
    _, approval = start_pending(client)
    assert approval["action_type"] == "publish_report"
    assert approval["target"] == "https://example.invalid/report"
    assert "visible" in approval["likely_consequence"]
    assert "high risk" in approval["risk_explanation"]
    assert approval["status"] == "pending"
    assert approval["expires_at"] > approval["created_at"]


def test_notifications_are_created_and_readable(client: TestClient) -> None:
    register(client)
    start_pending(client)
    unread = client.get("/api/notifications?unread=true").json()
    assert any(n["type"] == "approval_needed" for n in unread)

    first = unread[0]
    marked = client.patch(f"/api/notifications/{first['id']}/read", headers=csrf(client))
    assert marked.json()["read_at"] is not None

    client.post("/api/notifications/read-all", headers=csrf(client))
    assert client.get("/api/notifications?unread=true").json() == []


def test_notification_preferences_are_respected(client: TestClient) -> None:
    register(client)
    client.patch("/api/settings", json={"notify_approval_needed": False}, headers=csrf(client))
    start_pending(client)
    assert not [n for n in client.get("/api/notifications").json() if n["type"] == "approval_needed"]


def test_approval_audit_records_the_decision(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    _, approval = start_pending(client)
    client.post(f"/api/approvals/{approval['id']}/approve", json={}, headers=csrf(client))
    with session_factory() as db:
        actions = [e.action for e in db.scalars(select(AuditEvent))]
    assert "approval.requested" in actions
    assert "approval.approved" in actions

"""Automation engine: lifecycle, idempotency, retries, cancellation, crash recovery."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuditEvent, AutomationRun, RunStatus, RunStep, StepStatus
from app.services import steps
from app.workers.scheduler import cron_matches
from tests.conftest import csrf, register

LOW_RISK: dict[str, Any] = {
    "name": "Daily check",
    "trigger_type": "manual",
    "definition": {"steps": [{"type": "read_tasks", "params": {}}, {"type": "summarize_priorities", "params": {}}]},
    "permission_policy": {"auto_allowed": ["read_tasks", "summarize_priorities"], "require_approval": []},
}

HIGH_RISK: dict[str, Any] = {
    "name": "Publish report",
    "trigger_type": "manual",
    "definition": {
        "steps": [
            {"type": "summarize_open_tasks", "params": {}},
            {"type": "publish_report", "params": {"target": "https://example.invalid/report"}},
        ]
    },
    "permission_policy": {"auto_allowed": ["summarize_open_tasks"], "require_approval": ["publish_report"]},
}


def create_automation(client: TestClient, body: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post("/api/automations", json=body or LOW_RISK, headers=csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


def run_now(client: TestClient, automation_id: str, key: str = "run-1") -> Any:
    return client.post(f"/api/automations/{automation_id}/run", headers=csrf(client) | {"Idempotency-Key": key})


def test_seeded_demo_automations_exist_and_are_disabled(client: TestClient) -> None:
    register(client)
    rows = client.get("/api/automations").json()
    names = {r["name"] for r in rows}
    assert {"ScamShield Weekly Review", "Daily Briefing"} <= names
    # Nothing may run on a schedule until the user turns it on.
    assert all(r["enabled"] is False for r in rows)
    weekly = next(r for r in rows if r["name"] == "ScamShield Weekly Review")
    assert weekly["cron"] == "0 10 * * 1"
    assert "publish_report" in weekly["permission_policy"]["require_approval"]


def test_low_risk_run_succeeds_with_a_step_timeline(client: TestClient) -> None:
    register(client)
    automation = create_automation(client)
    response = run_now(client, automation["id"])
    assert response.status_code == 202
    run_id = response.json()["id"]

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "succeeded"
    assert [s["status"] for s in detail["steps"]] == ["succeeded", "succeeded"]
    assert [s["risk_level"] for s in detail["steps"]] == ["low", "low"]
    assert detail["steps"][0]["output_summary"]
    assert detail["finished_at"] is not None


def test_duplicate_idempotency_key_returns_the_same_run(client: TestClient) -> None:
    register(client)
    automation = create_automation(client)
    first = run_now(client, automation["id"], key="same-key")
    second = run_now(client, automation["id"], key="same-key")

    assert first.status_code == 202
    assert second.status_code == 200  # existing run returned, not a new one
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get(f"/api/automations/{automation['id']}/runs").json()) == 1


def test_different_users_may_use_the_same_client_key(app_factory: Callable[[], TestClient]) -> None:
    alice, bob = app_factory(), app_factory()
    register(alice, email="alice@example.com")
    register(bob, email="bob@example.com")
    a = create_automation(alice)
    b = create_automation(bob)

    first = run_now(alice, a["id"], key="shared")
    second = run_now(bob, b["id"], key="shared")
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["id"] != second.json()["id"]


def test_high_risk_step_pauses_the_run_and_creates_an_approval(client: TestClient) -> None:
    register(client)
    automation = create_automation(client, HIGH_RISK)
    run_id = run_now(client, automation["id"]).json()["id"]

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "awaiting_approval"
    assert detail["steps"][0]["status"] == "succeeded"
    assert detail["steps"][1]["status"] == "awaiting_approval"
    assert detail["pending_approval_id"]

    approval = client.get("/api/approvals?status=pending").json()[0]
    assert approval["action_type"] == "publish_report"
    assert approval["target"] == "https://example.invalid/report"
    assert "publish_report" in approval["risk_explanation"]
    assert approval["likely_consequence"]
    assert len(approval["payload_hash"]) == 64
    # The exact payload is shown to the user before they decide.
    assert "example.invalid" in approval["payload_preview"]


def test_prohibited_steps_cannot_even_be_saved(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/automations",
        json={
            "name": "Bad",
            "definition": {"steps": [{"type": "harvest_credentials", "params": {}}]},
            "permission_policy": {"auto_allowed": ["harvest_credentials"]},
        },
        headers=csrf(client),
    )
    assert response.status_code == 403
    assert "never allowed" in response.json()["error"]["message"]


def test_unknown_step_types_are_refused(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/automations",
        json={"name": "Odd", "definition": {"steps": [{"type": "run_shell_command", "params": {}}]}},
        headers=csrf(client),
    )
    assert response.status_code == 422
    assert "Unknown step type" in response.json()["error"]["message"]


def test_definition_must_match_the_schema(client: TestClient) -> None:
    register(client)
    headers = csrf(client)
    for definition in ({"steps": []}, {"steps": [{"type": "read_tasks", "extra": 1}]}, {"nope": []}):
        response = client.post("/api/automations", json={"name": "x", "definition": definition}, headers=headers)
        assert response.status_code == 422, definition


def test_policy_cannot_downgrade_a_high_risk_step(client: TestClient) -> None:
    """Listing a high-risk step under auto_allowed must not let it run unattended."""
    register(client)
    sneaky = {
        **HIGH_RISK,
        "permission_policy": {"auto_allowed": ["summarize_open_tasks", "publish_report"], "require_approval": []},
    }
    automation = create_automation(client, sneaky)
    run_id = run_now(client, automation["id"]).json()["id"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "awaiting_approval"


def test_medium_risk_needs_the_automation_to_enable_it(client: TestClient) -> None:
    register(client)
    body = {
        "name": "Medium",
        "definition": {"steps": [{"type": "modify_project_record", "params": {}}]},
        "permission_policy": {"auto_allowed": [], "require_approval": []},
    }
    automation = create_automation(client, body)
    run_id = run_now(client, automation["id"]).json()["id"]
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "failed"
    assert detail["steps"][0]["status"] == "blocked"


def test_cancel_before_running(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    automation = create_automation(client)
    # Create the run without executing it, so it stays queued.
    with session_factory() as db:
        from app.core.config import get_settings
        from app.db.models import Automation, TriggerType, User
        from app.services.automation import enqueue_run

        user = db.scalars(select(User)).one()
        row = db.scalars(select(Automation).where(Automation.id == automation["id"])).one()
        run, _ = enqueue_run(
            db, get_settings(), user, row, trigger=TriggerType.MANUAL, client_idempotency_key="pending"
        )
        run_id = run.id

    cancelled = client.post(f"/api/runs/{run_id}/cancel", headers=csrf(client))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    # Cancelling twice is a conflict, not a silent success.
    assert client.post(f"/api/runs/{run_id}/cancel", headers=csrf(client)).status_code == 409


def test_cancel_while_awaiting_approval_expires_the_approval(client: TestClient) -> None:
    register(client)
    automation = create_automation(client, HIGH_RISK)
    run_id = run_now(client, automation["id"]).json()["id"]
    assert client.post(f"/api/runs/{run_id}/cancel", headers=csrf(client)).json()["status"] == "cancelled"
    assert client.get("/api/approvals?status=pending").json() == []
    assert client.get("/api/approvals?status=expired").json()[0]["run_id"] == run_id


def test_step_failure_is_retried_then_recorded(
    client: TestClient, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    register(client)
    automation = create_automation(client)
    attempts = {"count": 0}

    def flaky(ctx: Any, params: dict[str, Any]) -> steps.StepResult:
        attempts["count"] += 1
        raise RuntimeError("transient")

    monkeypatch.setitem(steps.REGISTRY, "read_tasks", flaky)
    run_id = run_now(client, automation["id"]).json()["id"]

    detail = client.get(f"/api/runs/{run_id}").json()
    assert attempts["count"] == 3  # bounded retries, not unlimited
    assert detail["steps"][0]["status"] == "failed"
    assert detail["steps"][0]["attempts"] == 3
    # The second step still ran, so the run is partially successful rather than a flat failure.
    assert detail["status"] == "partially_succeeded"
    assert "transient" not in str(detail["steps"][0]["error_message_sanitized"])


def test_bad_step_parameters_are_not_retried(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    register(client)
    body = {
        "name": "Bad params",
        "definition": {"steps": [{"type": "read_tasks", "params": {"due": "whenever"}}]},
        "permission_policy": {"auto_allowed": ["read_tasks"]},
    }
    automation = create_automation(client, body)
    run_id = run_now(client, automation["id"]).json()["id"]
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "failed"
    assert detail["steps"][0]["attempts"] == 1


def test_worker_crash_recovery_resumes_completed_steps(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """A run left locked and half-finished by a dead worker is retaken and not re-executed."""
    register(client)
    automation = create_automation(client)
    run_id = run_now(client, automation["id"]).json()["id"]

    with session_factory() as db:
        run = db.get(AutomationRun, run_id)
        assert run is not None
        # Simulate a crash: first step done, run still RUNNING, lock held by a worker that died.
        run.status = RunStatus.RUNNING
        run.locked_by = "dead-worker"
        run.locked_at = datetime.now(UTC) - timedelta(hours=1)
        run.finished_at = None
        second = db.scalars(select(RunStep).where(RunStep.run_id == run_id, RunStep.step_index == 1)).one()
        second.status = StepStatus.PENDING
        second.output_summary = None
        db.commit()

        from app.services.automation import execute_run

        outcome = execute_run(db, run_id, worker_id="fresh-worker")
        assert outcome.status == RunStatus.SUCCEEDED
        first = db.scalars(select(RunStep).where(RunStep.run_id == run_id, RunStep.step_index == 0)).one()
        assert first.attempts == 1  # already-finished step was not run a second time


def test_a_second_worker_does_not_take_a_live_lock(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    automation = create_automation(client)
    run_id = run_now(client, automation["id"]).json()["id"]

    with session_factory() as db:
        run = db.get(AutomationRun, run_id)
        assert run is not None
        run.status = RunStatus.RUNNING
        run.locked_by = "busy-worker"
        run.locked_at = datetime.now(UTC)
        db.commit()

        from app.services.automation import execute_run

        outcome = execute_run(db, run_id, worker_id="second-worker")
        assert outcome.status == RunStatus.RUNNING  # left alone
        db.refresh(run)
        assert run.locked_by == "busy-worker"


def test_runs_and_automations_are_owner_scoped(app_factory: Callable[[], TestClient]) -> None:
    alice, bob = app_factory(), app_factory()
    register(alice, email="alice@example.com")
    register(bob, email="bob@example.com")
    automation = create_automation(alice)
    run_id = run_now(alice, automation["id"]).json()["id"]

    assert bob.get(f"/api/automations/{automation['id']}").status_code == 404
    assert bob.get(f"/api/runs/{run_id}").status_code == 404
    assert bob.post(f"/api/runs/{run_id}/cancel", headers=csrf(bob)).status_code == 404
    assert bob.post(f"/api/automations/{automation['id']}/run", headers=csrf(bob)).status_code == 404
    assert bob.delete(f"/api/automations/{automation['id']}", headers=csrf(bob)).status_code == 404


def test_run_endpoint_is_rate_limited(client: TestClient) -> None:
    register(client)
    automation = create_automation(client)
    statuses = [run_now(client, automation["id"], key=f"k{i}").status_code for i in range(31)]
    assert statuses[30] == 429


def test_connector_steps_never_claim_delivery(client: TestClient) -> None:
    """High-risk connectors are stubs in this MVP and must say so."""
    register(client)
    automation = create_automation(client, HIGH_RISK)
    run_id = run_now(client, automation["id"]).json()["id"]
    approval = client.get("/api/approvals?status=pending").json()[0]
    client.post(f"/api/approvals/{approval['id']}/approve", json={}, headers=csrf(client))

    detail = client.get(f"/api/runs/{run_id}").json()
    summary = detail["steps"][1]["output_summary"]
    assert "NOT sent" in summary
    assert detail["status"] == "succeeded"


def test_audit_trail_covers_the_whole_run(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    automation = create_automation(client)
    run_now(client, automation["id"])
    with session_factory() as db:
        actions = [e.action for e in db.scalars(select(AuditEvent))]
    assert "automation.create" in actions
    assert "run.queued" in actions
    assert "run.finished" in actions


def test_schedule_requires_a_cron_expression(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/automations",
        json={**LOW_RISK, "trigger_type": "schedule"},
        headers=csrf(client),
    )
    assert response.status_code == 422


def test_editing_the_definition_bumps_the_version(client: TestClient) -> None:
    register(client)
    automation = create_automation(client)
    assert automation["version"] == 1
    updated = client.patch(
        f"/api/automations/{automation['id']}",
        json={"definition": {"steps": [{"type": "read_tasks", "params": {}}]}},
        headers=csrf(client),
    )
    assert updated.json()["version"] == 2
    # Renaming alone is not a new version of the workflow.
    renamed = client.patch(f"/api/automations/{automation['id']}", json={"name": "New name"}, headers=csrf(client))
    assert renamed.json()["version"] == 2


@pytest.mark.parametrize(
    ("expression", "moment", "expected"),
    [
        ("0 8 * * *", datetime(2026, 10, 19, 8, 0, tzinfo=UTC), True),
        ("0 8 * * *", datetime(2026, 10, 19, 8, 1, tzinfo=UTC), False),
        ("0 10 * * 1", datetime(2026, 10, 19, 10, 0, tzinfo=UTC), True),  # a Monday
        ("0 10 * * 1", datetime(2026, 10, 20, 10, 0, tzinfo=UTC), False),  # Tuesday
        ("*/15 * * * *", datetime(2026, 10, 19, 9, 30, tzinfo=UTC), True),
        ("*/15 * * * *", datetime(2026, 10, 19, 9, 31, tzinfo=UTC), False),
        ("30 9-17 * * *", datetime(2026, 10, 19, 13, 30, tzinfo=UTC), True),
        ("30 9-17 * * *", datetime(2026, 10, 19, 18, 30, tzinfo=UTC), False),
        ("not a cron", datetime(2026, 10, 19, 8, 0, tzinfo=UTC), False),
    ],
)
def test_cron_matching(expression: str, moment: datetime, expected: bool) -> None:
    assert cron_matches(expression, moment) is expected


def test_scheduler_queues_once_per_slot(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    """Two ticks in the same minute must not produce two runs."""
    from app.db.models import Automation
    from app.workers import scheduler

    register(client)
    created = client.post(
        "/api/automations",
        json={**LOW_RISK, "name": "Every minute", "trigger_type": "schedule", "cron": "* * * * *"},
        headers=csrf(client),
    ).json()

    with session_factory() as db:
        assert db.get(Automation, created["id"]) is not None

    import app.db.session as session_module

    original = session_module.get_sessionmaker
    session_module.get_sessionmaker = lambda: session_factory  # type: ignore[assignment]
    scheduler.get_sessionmaker = lambda: session_factory  # type: ignore[attr-defined]
    try:
        first = scheduler.tick()
        second = scheduler.tick()
    finally:
        session_module.get_sessionmaker = original  # type: ignore[assignment]

    assert first == 1
    assert second == 0
    assert len(client.get(f"/api/automations/{created['id']}/runs").json()) == 1

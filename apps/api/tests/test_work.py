from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import csrf, register

FUTURE = (datetime.now(UTC) + timedelta(days=3)).isoformat()
PAST = (datetime.now(UTC) - timedelta(days=3)).isoformat()


def make_project(client: TestClient, name: str = "Website redesign", **extra: Any) -> dict[str, Any]:
    response = client.post("/api/projects", json={"name": name, **extra}, headers=csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


def make_task(client: TestClient, title: str, **extra: Any) -> dict[str, Any]:
    response = client.post("/api/tasks", json={"title": title, **extra}, headers=csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


def test_new_account_is_seeded_with_scamshield_and_demo_automations(client: TestClient) -> None:
    register(client)
    names = [p["name"] for p in client.get("/api/projects").json()]
    assert "ScamShield AI" in names

    scamshield = next(p for p in client.get("/api/projects").json() if p["name"] == "ScamShield AI")
    assert scamshield["task_total"] == 6
    assert scamshield["task_done"] == 1
    assert scamshield["task_open"] == 5

    tasks = client.get(f"/api/tasks?project_id={scamshield['id']}").json()
    assert any(t["status"] == "blocked" and t["priority"] == "urgent" for t in tasks)


def test_project_crud_and_task_counts(client: TestClient) -> None:
    register(client)
    project = make_project(client)
    assert project["status"] == "active"

    make_task(client, "Draft the brief", project_id=project["id"])
    done = make_task(client, "Pick a colour palette", project_id=project["id"])
    client.patch(f"/api/tasks/{done['id']}", json={"status": "done"}, headers=csrf(client))

    fetched = client.get(f"/api/projects/{project['id']}").json()
    assert (fetched["task_total"], fetched["task_done"], fetched["task_open"]) == (2, 1, 1)

    renamed = client.patch(
        f"/api/projects/{project['id']}", json={"name": "Website refresh", "status": "paused"}, headers=csrf(client)
    )
    assert renamed.json()["name"] == "Website refresh"
    assert [p["id"] for p in client.get("/api/projects?status=paused").json()] == [project["id"]]


def test_deleting_a_project_keeps_its_tasks(client: TestClient) -> None:
    register(client)
    project = make_project(client)
    task = make_task(client, "Survives deletion", project_id=project["id"])

    assert client.delete(f"/api/projects/{project['id']}", headers=csrf(client)).status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404
    remaining = [t for t in client.get("/api/tasks").json() if t["id"] == task["id"]]
    assert remaining and remaining[0]["project_id"] is None


def test_task_filters(client: TestClient) -> None:
    register(client)
    project = make_project(client, name="Filters")
    urgent = make_task(client, "Urgent item", priority="urgent", due_at=PAST, project_id=project["id"])
    make_task(client, "Someday item", priority="low")
    later = make_task(client, "Next month", due_at=(datetime.now(UTC) + timedelta(days=30)).isoformat())

    ids = lambda url: {t["id"] for t in client.get(url).json()}  # noqa: E731 - short helper inside one test
    assert urgent["id"] in ids("/api/tasks?priority=urgent")
    assert later["id"] not in ids("/api/tasks?priority=urgent")
    assert urgent["id"] in ids("/api/tasks?due=overdue")
    assert later["id"] not in ids("/api/tasks?due=week")
    assert ids(f"/api/tasks?project_id={project['id']}") == {urgent["id"]}
    assert urgent["id"] in ids("/api/tasks?status=todo")
    assert urgent["id"] not in ids("/api/tasks?status=done")


def test_unfinished_tasks_sort_before_done_and_by_due_date(client: TestClient) -> None:
    register(client)
    client.post("/api/projects", json={"name": "Sorting"}, headers=csrf(client))
    soon = make_task(client, "Due soon", due_at=(datetime.now(UTC) + timedelta(days=1)).isoformat())
    finished = make_task(client, "Already finished")
    client.patch(f"/api/tasks/{finished['id']}", json={"status": "done"}, headers=csrf(client))

    ordered = [t["id"] for t in client.get("/api/tasks").json()]
    assert ordered.index(soon["id"]) < ordered.index(finished["id"])


def test_task_validation(client: TestClient) -> None:
    register(client)
    headers = csrf(client)
    assert client.post("/api/tasks", json={"title": ""}, headers=headers).status_code == 422
    assert client.post("/api/tasks", json={"title": "x", "status": "finished"}, headers=headers).status_code == 422
    assert client.post("/api/tasks", json={"title": "x", "priority": "panic"}, headers=headers).status_code == 422
    assert client.post("/api/tasks", json={"title": "x", "owner_id": "someone"}, headers=headers).status_code == 422
    # A due date without a timezone is ambiguous and is rejected.
    naive = client.post("/api/tasks", json={"title": "x", "due_at": "2026-12-01T09:00:00"}, headers=headers)
    assert naive.status_code == 422


def test_task_cannot_join_another_users_project(app_factory: Callable[[], TestClient]) -> None:
    alice, bob = app_factory(), app_factory()
    register(alice, email="alice@example.com")
    register(bob, email="bob@example.com")
    alice_project = make_project(alice, name="Alice only")

    response = bob.post("/api/tasks", json={"title": "Sneaky", "project_id": alice_project["id"]}, headers=csrf(bob))
    assert response.status_code == 422
    assert response.json()["error"]["fields"][0]["field"] == "project_id"


def test_cross_user_project_and_task_access_returns_404(app_factory: Callable[[], TestClient]) -> None:
    alice, bob = app_factory(), app_factory()
    register(alice, email="alice@example.com")
    register(bob, email="bob@example.com")
    project = make_project(alice, name="Alice private")
    task = make_task(alice, "Alice task", project_id=project["id"])

    for method, url in [("get", f"/api/projects/{project['id']}")]:
        assert getattr(bob, method)(url).status_code == 404
    assert bob.patch(f"/api/projects/{project['id']}", json={"name": "x"}, headers=csrf(bob)).status_code == 404
    assert bob.delete(f"/api/projects/{project['id']}", headers=csrf(bob)).status_code == 404
    assert bob.patch(f"/api/tasks/{task['id']}", json={"title": "x"}, headers=csrf(bob)).status_code == 404
    assert bob.delete(f"/api/tasks/{task['id']}", headers=csrf(bob)).status_code == 404
    assert task["id"] not in {t["id"] for t in bob.get("/api/tasks").json()}


def test_tasks_persist_across_restart(app_factory: Callable[[], TestClient]) -> None:
    first = app_factory()
    register(first)
    task = make_task(first, "Persisted task", priority="high")

    second = app_factory()  # new app instance, same database
    from tests.conftest import STRONG_PASSWORD

    second.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": STRONG_PASSWORD}, headers=csrf(second)
    )
    fetched = [t for t in second.get("/api/tasks").json() if t["id"] == task["id"]]
    assert fetched and fetched[0]["priority"] == "high"


def test_due_filter_uses_the_users_timezone(client: TestClient) -> None:
    """ "Today" must end at midnight where the user lives, not at midnight UTC."""
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Pacific/Kiritimati")  # UTC+14, so its day ends well before UTC's
    register(client)
    client.patch("/api/settings", json={"timezone": "Pacific/Kiritimati"}, headers=csrf(client))

    local_end_of_day = datetime.now(zone).replace(hour=23, minute=59, second=0, microsecond=0)
    inside = make_task(
        client, "Just before local midnight", due_at=(local_end_of_day - timedelta(minutes=5)).isoformat()
    )
    outside = make_task(
        client, "Just after local midnight", due_at=(local_end_of_day + timedelta(minutes=30)).isoformat()
    )

    today = {t["id"] for t in client.get("/api/tasks?due=today").json()}
    assert inside["id"] in today
    assert outside["id"] not in today

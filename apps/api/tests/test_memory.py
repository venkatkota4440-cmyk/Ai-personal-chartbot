from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuditEvent, Memory
from tests.conftest import csrf, register


def create(client: TestClient, content: str) -> dict[str, str]:
    response = client.post("/api/memories", json={"content": content}, headers=csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


def test_user_created_memory_is_approved(client: TestClient) -> None:
    register(client)
    memory = create(client, "Works in IST timezone")
    assert memory["status"] == "approved"
    assert memory["source"] == "user"
    assert [m["content"] for m in client.get("/api/memories").json()] == ["Works in IST timezone"]


def test_edit_memory(client: TestClient) -> None:
    register(client)
    memory = create(client, "Prefers tea")
    edited = client.patch(f"/api/memories/{memory['id']}", json={"content": "Prefers green tea"}, headers=csrf(client))
    assert edited.status_code == 200
    assert edited.json()["content"] == "Prefers green tea"
    assert client.get("/api/memories").json()[0]["content"] == "Prefers green tea"


def test_reject_and_filter_by_status(client: TestClient) -> None:
    register(client)
    memory = create(client, "Likes running")
    client.patch(f"/api/memories/{memory['id']}", json={"status": "rejected"}, headers=csrf(client))
    assert client.get("/api/memories?status=approved").json() == []
    assert [m["id"] for m in client.get("/api/memories?status=rejected").json()] == [memory["id"]]


def test_users_cannot_set_status_back_to_proposed(client: TestClient) -> None:
    register(client)
    memory = create(client, "Likes running")
    response = client.patch(f"/api/memories/{memory['id']}", json={"status": "proposed"}, headers=csrf(client))
    assert response.status_code == 422


def test_delete_erases_memory_text(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    memory = create(client, "Lives at 12 Example Street")
    assert client.delete(f"/api/memories/{memory['id']}", headers=csrf(client)).status_code == 204
    assert client.get("/api/memories").json() == []
    assert client.patch(f"/api/memories/{memory['id']}", json={"content": "x"}, headers=csrf(client)).status_code == 404
    with session_factory() as db:
        row = db.get(Memory, memory["id"])
        assert row is not None and row.content == "" and row.deleted_at is not None


def test_deleted_memory_shows_as_deleted_in_old_replies(client: TestClient) -> None:
    register(client)
    memory = create(client, "Prefers Python examples")
    conversation_id = client.post("/api/chat", json={"message": "Python examples please"}, headers=csrf(client)).json()[
        "conversation"
    ]["id"]
    client.delete(f"/api/memories/{memory['id']}", headers=csrf(client))
    assistant = client.get(f"/api/conversations/{conversation_id}").json()["messages"][1]
    assert assistant["used_memories"] == [{"id": memory["id"], "content": None, "status": "deleted"}]


def test_export_contains_only_own_active_memories(app_factory: Callable[[], TestClient]) -> None:
    alice, bob = app_factory(), app_factory()
    register(alice, email="alice@example.com")
    register(bob, email="bob@example.com")
    create(alice, "Alice fact")
    gone = create(alice, "Deleted fact")
    alice.delete(f"/api/memories/{gone['id']}", headers=csrf(alice))
    create(bob, "Bob fact")

    response = alice.get("/api/memories/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert [m["content"] for m in response.json()["memories"]] == ["Alice fact"]


def test_cross_user_memory_access_returns_404(app_factory: Callable[[], TestClient]) -> None:
    alice, bob = app_factory(), app_factory()
    register(alice, email="alice@example.com")
    register(bob, email="bob@example.com")
    memory = create(alice, "Alice private memory")
    assert bob.patch(f"/api/memories/{memory['id']}", json={"status": "rejected"}, headers=csrf(bob)).status_code == 404
    assert bob.delete(f"/api/memories/{memory['id']}", headers=csrf(bob)).status_code == 404
    assert bob.get("/api/memories").json() == []
    assert alice.get("/api/memories").json()[0]["status"] == "approved"


def test_memory_validation(client: TestClient) -> None:
    register(client)
    headers = csrf(client)
    assert client.post("/api/memories", json={"content": ""}, headers=headers).status_code == 422
    assert client.post("/api/memories", json={"content": "x" * 1001}, headers=headers).status_code == 422
    extra_field = client.post("/api/memories", json={"content": "ok", "status": "approved"}, headers=headers)
    assert extra_field.status_code == 422


def test_duplicate_proposals_are_skipped(client: TestClient) -> None:
    register(client)
    first = client.post("/api/chat", json={"message": "Remember that I like tea"}, headers=csrf(client)).json()
    second = client.post("/api/chat", json={"message": "Remember that I like tea"}, headers=csrf(client)).json()
    assert len(first["proposed_memories"]) == 1
    assert second["proposed_memories"] == []


def test_memory_audit_has_no_memory_text(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    memory = create(client, "Diagnosed with asthma")
    client.patch(f"/api/memories/{memory['id']}", json={"content": "Has asthma"}, headers=csrf(client))
    with session_factory() as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.action.like("memory.%"))).all()
    assert {e.action for e in events} == {"memory.create", "memory.update"}
    assert "asthma" not in " ".join(f"{e.target} {e.metadata_sanitized}" for e in events)

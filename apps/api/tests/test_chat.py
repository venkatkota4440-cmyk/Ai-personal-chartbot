from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuditEvent, Message
from app.db.session import build_engine, get_db
from app.main import create_app
from app.services import chat as chat_service
from app.services.ai import AIErrorKind, AIProviderError, AssistantReply, ChatRequest
from tests.conftest import STRONG_PASSWORD, csrf, register

API_DIR = Path(__file__).resolve().parents[1]


def send(client: TestClient, message: str, **extra: Any) -> Any:
    return client.post("/api/chat", json={"message": message, **extra}, headers=csrf(client))


class FakeProvider:
    """Records what the backend sent and returns a scripted reply or error."""

    name = "fake"

    def __init__(self, reply: AssistantReply | None = None, error: AIProviderError | None = None) -> None:
        self.reply = reply or AssistantReply(reply="ok", proposed_memories=[], confidence="high")
        self.error = error
        self.requests: list[ChatRequest] = []

    def generate(self, request: ChatRequest) -> AssistantReply:
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    provider = FakeProvider()
    monkeypatch.setattr(chat_service, "provider_for", lambda model, settings: provider)
    return provider


def test_chat_creates_conversation_and_persists_both_messages(client: TestClient) -> None:
    register(client)
    response = send(client, "Help me plan my week")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["conversation"]["title"] == "Help me plan my week"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["model"] == "mock-deterministic"
    # The mock never pretends to know facts.
    assert body["assistant_message"]["confidence"] == "low"

    detail = client.get(f"/api/conversations/{body['conversation']['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert [c["id"] for c in client.get("/api/conversations").json()] == [body["conversation"]["id"]]


def test_follow_up_messages_include_history(client: TestClient, fake: FakeProvider) -> None:
    register(client)
    first = send(client, "First question").json()
    send(client, "Second question", conversation_id=first["conversation"]["id"])
    history = fake.requests[1].history
    assert [(t.role, t.content) for t in history] == [("user", "First question"), ("assistant", "ok")]


def test_conversations_persist_after_restart(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'chat.db'}"
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    def start() -> TestClient:
        factory = sessionmaker(bind=build_engine(url), expire_on_commit=False)

        def _db():  # type: ignore[no-untyped-def]
            db = factory()
            try:
                yield db
            finally:
                db.close()

        app = create_app()
        app.dependency_overrides[get_db] = _db
        return TestClient(app)

    first = start()
    register(first)
    conversation_id = send(first, "Remember that I prefer short answers").json()["conversation"]["id"]

    second = start()  # brand-new app and engine: simulates a restart
    second.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": STRONG_PASSWORD}, headers=csrf(second)
    )
    detail = second.get(f"/api/conversations/{conversation_id}").json()
    assert len(detail["messages"]) == 2
    assert [m["status"] for m in second.get("/api/memories").json()] == ["proposed"]


def test_proposed_memory_is_not_used_until_approved(client: TestClient) -> None:
    register(client)
    first = send(client, "Remember that I prefer Python examples").json()
    assert len(first["proposed_memories"]) == 1
    memory_id = first["proposed_memories"][0]["id"]
    assert first["proposed_memories"][0]["status"] == "proposed"

    before = send(client, "Show me Python examples for reading files").json()
    assert before["assistant_message"]["used_memories"] == []

    client.patch(f"/api/memories/{memory_id}", json={"status": "approved"}, headers=csrf(client))
    after = send(client, "Show me Python examples for reading files").json()
    used = after["assistant_message"]["used_memories"]
    assert [u["id"] for u in used] == [memory_id]
    assert after["assistant_message"]["memory_ranking"] == "keyword"


def test_irrelevant_memories_are_not_sent(client: TestClient, fake: FakeProvider) -> None:
    register(client)
    client.post("/api/memories", json={"content": "Allergic to peanuts"}, headers=csrf(client))
    send(client, "Draft an email about the quarterly roadmap")
    assert fake.requests[0].memories == []


def test_memory_off_toggle_blocks_reading_and_proposing(client: TestClient, fake: FakeProvider) -> None:
    register(client)
    client.post("/api/memories", json={"content": "Prefers Python examples"}, headers=csrf(client))
    fake.reply = AssistantReply(reply="ok", proposed_memories=["Likes tea"], confidence="medium")

    body = send(client, "Python examples please", memory_enabled=False).json()
    assert body["conversation"]["memory_enabled"] is False
    assert fake.requests[0].memories == []
    assert fake.requests[0].allow_memory_proposals is False
    # Even though the model suggested a memory, nothing is stored while memory is off.
    assert body["proposed_memories"] == []
    assert body["assistant_message"]["used_memories"] == []

    conversation_id = body["conversation"]["id"]
    toggled = client.patch(f"/api/conversations/{conversation_id}", json={"memory_enabled": True}, headers=csrf(client))
    assert toggled.json()["memory_enabled"] is True
    body = send(client, "Python examples please", conversation_id=conversation_id).json()
    assert len(fake.requests[1].memories) == 1
    assert [m["content"] for m in body["proposed_memories"]] == ["Likes tea"]


def test_sensitive_topics_get_human_review_note(client: TestClient) -> None:
    register(client)
    body = send(client, "Should I invest my savings in crypto?").json()
    note = body["assistant_message"]["human_review_note"]
    assert note and note.startswith("Human review needed") and "financial" in note
    plain = send(client, "Suggest a name for my cat").json()
    assert plain["assistant_message"]["human_review_note"] is None


@pytest.mark.parametrize(
    ("kind", "status", "category"),
    [
        (AIErrorKind.TIMEOUT, 503, "ai_unavailable"),
        (AIErrorKind.UNAVAILABLE, 503, "ai_unavailable"),
        (AIErrorKind.INVALID_OUTPUT, 502, "ai_invalid_output"),
        (AIErrorKind.REFUSED, 422, "ai_refused"),
    ],
)
def test_provider_failure_keeps_user_message_and_invents_no_reply(
    client: TestClient,
    fake: FakeProvider,
    session_factory: sessionmaker[Session],
    kind: AIErrorKind,
    status: int,
    category: str,
) -> None:
    register(client)
    fake.error = AIProviderError(kind, "Provider problem")
    response = send(client, "Hello there")
    assert response.status_code == status
    assert response.json()["error"]["category"] == category

    with session_factory() as db:
        roles = [m.role.value for m in db.scalars(select(Message))]
        results = [e.result for e in db.scalars(select(AuditEvent).where(AuditEvent.action == "chat.reply"))]
    assert roles == ["user"]  # saved, and no fake assistant reply
    assert results == [f"failed:{kind.value}"]


def test_unconfigured_model_is_refused_not_faked(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    from app.db.models import UserSettings

    with session_factory() as db:
        prefs = db.scalars(select(UserSettings)).one()
        prefs.default_model = "claude-opus-5-5"  # not in ALLOWED_MODELS on this server
        db.commit()
    response = send(client, "Hello")
    assert response.status_code == 503
    assert response.json()["error"]["category"] == "ai_unavailable"


def test_other_users_conversations_are_invisible(app_factory: Callable[[], TestClient]) -> None:
    alice, bob = app_factory(), app_factory()
    register(alice, email="alice@example.com")
    register(bob, email="bob@example.com")
    conversation_id = send(alice, "Alice private chat").json()["conversation"]["id"]

    assert bob.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert bob.patch(f"/api/conversations/{conversation_id}", json={"title": "x"}, headers=csrf(bob)).status_code == 404
    assert bob.delete(f"/api/conversations/{conversation_id}", headers=csrf(bob)).status_code == 404
    assert send(bob, "Inject into Alice's chat", conversation_id=conversation_id).status_code == 404
    assert bob.get("/api/conversations").json() == []
    assert len(alice.get(f"/api/conversations/{conversation_id}").json()["messages"]) == 2


def test_delete_conversation_removes_messages(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    conversation_id = send(client, "Temporary chat").json()["conversation"]["id"]
    assert client.delete(f"/api/conversations/{conversation_id}", headers=csrf(client)).status_code == 204
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404
    with session_factory() as db:
        assert db.scalars(select(Message)).all() == []


def test_chat_input_validation(client: TestClient) -> None:
    register(client)
    assert send(client, "").status_code == 422
    assert send(client, "x" * 8001).status_code == 422
    assert send(client, "hi", unexpected=True).status_code == 422


def test_chat_is_rate_limited_per_user(client: TestClient) -> None:
    register(client)
    statuses = [send(client, f"message {i}").status_code for i in range(21)]
    assert statuses[:20] == [200] * 20
    assert statuses[20] == 429


def test_retention_setting_purges_old_messages(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    conversation_id = send(client, "Old message").json()["conversation"]["id"]
    with session_factory() as db:
        for message in db.scalars(select(Message)):
            message.created_at = datetime.now(UTC) - timedelta(days=40)
        db.commit()
    client.patch("/api/settings", json={"message_retention_days": 30}, headers=csrf(client))
    assert client.get(f"/api/conversations/{conversation_id}").json()["messages"] == []


def test_audit_log_never_contains_message_text(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    send(client, "My secret plan is to learn Rust")
    with session_factory() as db:
        dumped = " ".join(f"{e.target} {e.metadata_sanitized}" for e in db.scalars(select(AuditEvent)))
    assert "secret plan" not in dumped

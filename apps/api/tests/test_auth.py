from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import SESSION_COOKIE
from app.db.models import AuditEvent, User
from tests.conftest import STRONG_PASSWORD, csrf, register


def test_register_creates_session_and_returns_user(client: TestClient) -> None:
    user = register(client, email="Owner@Example.com")
    assert user["email"] == "owner@example.com"
    assert "password_hash" not in user
    assert client.get("/api/auth/me").json()["id"] == user["id"]


def test_session_cookie_is_httponly_and_samesite_lax(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": STRONG_PASSWORD},
        headers=csrf(client),
    )
    cookie = next(h for h in response.headers.get_list("set-cookie") if h.startswith(SESSION_COOKIE))
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()


def test_password_is_hashed_with_argon2id(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    with session_factory() as db:
        stored = db.scalars(select(User)).one().password_hash
    assert stored.startswith("$argon2id$")
    assert STRONG_PASSWORD not in stored


def test_short_password_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register", json={"email": "a@example.com", "password": "short"}, headers=csrf(client)
    )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["category"] == "validation_error"
    assert body["fields"][0]["field"] == "password"


def test_duplicate_email_conflict_is_case_insensitive(client: TestClient) -> None:
    register(client, email="dup@example.com")
    response = client.post(
        "/api/auth/register", json={"email": "DUP@example.com", "password": STRONG_PASSWORD}, headers=csrf(client)
    )
    assert response.status_code == 409


def test_unknown_fields_and_invalid_timezone_rejected(client: TestClient) -> None:
    headers = csrf(client)
    extra = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": STRONG_PASSWORD, "is_admin": True},
        headers=headers,
    )
    assert extra.status_code == 422
    bad_tz = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": STRONG_PASSWORD, "timezone": "Mars/Base"},
        headers=headers,
    )
    assert bad_tz.status_code == 422


def test_validation_errors_do_not_echo_submitted_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "hunter2-secret-value"},
        headers=csrf(client),
    )
    assert response.status_code == 422
    assert "hunter2-secret-value" not in response.text


def test_login_logout_flow(app_factory: Callable[[], TestClient]) -> None:
    first = app_factory()
    register(first)

    browser = app_factory()
    assert browser.get("/api/auth/me").status_code == 401
    login = browser.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": STRONG_PASSWORD}, headers=csrf(browser)
    )
    assert login.status_code == 200
    assert browser.get("/api/auth/me").status_code == 200

    stolen_cookie = browser.cookies[SESSION_COOKIE]
    assert browser.post("/api/auth/logout", headers=csrf(browser)).status_code == 204
    assert browser.get("/api/auth/me").status_code == 401

    # The server-side session is revoked, so replaying the old cookie must fail too.
    replay = app_factory()
    replay.cookies.set(SESSION_COOKIE, stolen_cookie)
    assert replay.get("/api/auth/me").status_code == 401


def test_wrong_password_and_unknown_email_get_identical_responses(client: TestClient) -> None:
    register(client)
    other = client.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": "wrong-password-123"}, headers=csrf(client)
    )
    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-123"}, headers=csrf(client)
    )
    assert other.status_code == unknown.status_code == 401
    assert other.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert other.json()["error"]["category"] == "invalid_credentials"


def test_login_is_rate_limited(client: TestClient) -> None:
    register(client)
    headers = csrf(client)
    statuses = [
        client.post(
            "/api/auth/login", json={"email": "owner@example.com", "password": "wrong-password-123"}, headers=headers
        ).status_code
        for _ in range(6)
    ]
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429
    limited = client.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": STRONG_PASSWORD}, headers=headers
    )
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1


def test_auth_events_are_audited_without_secrets(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    register(client)
    client.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": "wrong-password-123"}, headers=csrf(client)
    )
    with session_factory() as db:
        events = db.scalars(select(AuditEvent).order_by(AuditEvent.timestamp)).all()
    actions = [(e.action, e.result) for e in events]
    assert ("auth.register", "success") in actions
    assert ("auth.login", "failure") in actions
    for event in events:
        serialized = f"{event.target} {event.metadata_sanitized}"
        assert "owner@example.com" not in serialized  # emails are masked
        assert "wrong-password-123" not in serialized
        assert STRONG_PASSWORD not in serialized


def test_expired_session_is_rejected(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    from datetime import UTC, datetime, timedelta

    from app.db.models import Session as SessionModel

    register(client)
    with session_factory() as db:
        for s in db.scalars(select(SessionModel)):
            s.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401

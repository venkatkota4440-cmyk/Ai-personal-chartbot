from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.security import CSRF_HEADER
from tests.conftest import STRONG_PASSWORD, csrf, register


def test_state_changing_request_without_csrf_is_rejected(client: TestClient) -> None:
    response = client.post("/api/auth/register", json={"email": "a@example.com", "password": STRONG_PASSWORD})
    assert response.status_code == 403
    assert response.json()["error"]["category"] == "csrf_failed"


def test_csrf_header_must_match_cookie(client: TestClient) -> None:
    csrf(client)
    response = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": STRONG_PASSWORD},
        headers={CSRF_HEADER: "nonce.forged-signature"},
    )
    assert response.status_code == 403


def test_unsigned_csrf_token_rejected_even_when_cookie_matches(client: TestClient) -> None:
    # Simulates an attacker who can plant a cookie (e.g. from a sibling subdomain) but lacks the secret.
    client.cookies.set("paa_csrf", "attacker.planted")
    response = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": STRONG_PASSWORD},
        headers={CSRF_HEADER: "attacker.planted"},
    )
    assert response.status_code == 403


def test_disallowed_origin_rejected(client: TestClient) -> None:
    headers = csrf(client) | {"Origin": "https://evil.example"}
    response = client.post(
        "/api/auth/register", json={"email": "a@example.com", "password": STRONG_PASSWORD}, headers=headers
    )
    assert response.status_code == 403


def test_oversized_body_rejected(client: TestClient) -> None:
    headers = csrf(client) | {"Content-Type": "application/json"}
    big = b'{"email": "a@example.com", "password": "' + b"x" * 1_100_000 + b'"}'
    response = client.post("/api/auth/register", content=big, headers=headers)
    assert response.status_code == 413
    assert response.json()["error"]["category"] == "payload_too_large"


def test_security_headers_and_request_id_present(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]


def test_unknown_route_returns_structured_404(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["category"] == "not_found"


def test_unhandled_errors_do_not_leak_details(client: TestClient) -> None:
    from app.main import create_app

    app = create_app()

    @app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError("database password is hunter2")

    response = TestClient(app, raise_server_exceptions=False).get("/api/boom")
    assert response.status_code == 500
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text
    assert response.json()["error"]["category"] == "internal_error"


def test_health_reports_database_status(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "components": {"database": "ok"}}


def test_settings_update_validates_model_allowlist(client: TestClient) -> None:
    register(client)
    headers = csrf(client)
    bad = client.patch("/api/settings", json={"default_model": "gpt-unlisted"}, headers=headers)
    assert bad.status_code == 422
    ok = client.patch(
        "/api/settings", json={"message_retention_days": 30, "notify_run_succeeded": False}, headers=headers
    )
    assert ok.status_code == 200
    assert ok.json()["message_retention_days"] == 30
    assert ok.json()["notify_run_succeeded"] is False
    cleared = client.patch("/api/settings", json={"message_retention_days": None}, headers=headers)
    assert cleared.json()["message_retention_days"] is None
    assert client.patch("/api/settings", json={"message_retention_days": 0}, headers=headers).status_code == 422

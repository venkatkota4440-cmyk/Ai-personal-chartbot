"""Cross-user isolation: one user can never read or change another user's data.

Projects get API routes in M3, so this exercises the owner-scoped repository
layer that every later route is required to use, plus the settings API.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Project, User
from app.db.repository import get_owned, list_owned
from tests.conftest import csrf, register


def _user_id(db: Session, email: str) -> str:
    return db.scalars(select(User.id).where(User.email == email)).one()


def test_repository_hides_other_users_records(
    app_factory: Callable[[], TestClient], session_factory: sessionmaker[Session]
) -> None:
    register(app_factory(), email="alice@example.com")
    register(app_factory(), email="bob@example.com")

    with session_factory() as db:
        alice, bob = _user_id(db, "alice@example.com"), _user_id(db, "bob@example.com")
        secret = Project(user_id=alice, name="Alice private project")
        db.add(secret)
        db.commit()

        assert get_owned(db, Project, secret.id, alice) is not None
        assert get_owned(db, Project, secret.id, bob) is None
        # Both accounts hold seeded demo projects, so compare by name rather than by count.
        assert "Alice private project" in [p.name for p in list_owned(db, Project, alice)]
        assert "Alice private project" not in [p.name for p in list_owned(db, Project, bob)]


def test_settings_are_isolated_per_user(app_factory: Callable[[], TestClient]) -> None:
    alice = app_factory()
    bob = app_factory()
    register(alice, email="alice@example.com")
    register(bob, email="bob@example.com")

    assert alice.patch("/api/settings", json={"timezone": "Asia/Kolkata"}, headers=csrf(alice)).status_code == 200
    assert alice.get("/api/settings").json()["timezone"] == "Asia/Kolkata"
    assert bob.get("/api/settings").json()["timezone"] == "UTC"
    assert bob.get("/api/auth/me").json()["email"] == "bob@example.com"


def test_protected_routes_require_authentication(client: TestClient) -> None:
    for method, path in [("get", "/api/auth/me"), ("get", "/api/settings")]:
        response = getattr(client, method)(path)
        assert response.status_code == 401
        assert response.json()["error"]["category"] == "authentication_required"
    patch = client.patch("/api/settings", json={"timezone": "UTC"}, headers=csrf(client))
    assert patch.status_code == 401


def test_forged_session_cookie_is_rejected(client: TestClient) -> None:
    client.cookies.set("paa_session", "forged-token-value")
    assert client.get("/api/auth/me").status_code == 401

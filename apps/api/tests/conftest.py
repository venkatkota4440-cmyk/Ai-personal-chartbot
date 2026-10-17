from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

# Configure before importing the app so module-level settings pick these up.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SESSION_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("DATABASE_URL", "sqlite:///./test-unused.db")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.rate_limit import get_rate_limiter
from app.core.security import CSRF_COOKIE, CSRF_HEADER
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app

STRONG_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def session_factory(db_url: str) -> Iterator[sessionmaker[Session]]:
    engine = build_engine(db_url)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def app_factory(session_factory: sessionmaker[Session]) -> Callable[[], TestClient]:
    get_rate_limiter(get_settings()).reset()

    def _override_db() -> Iterator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def build() -> TestClient:
        app = create_app()
        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    return build


@pytest.fixture
def client(app_factory: Callable[[], TestClient]) -> TestClient:
    return app_factory()


def csrf(client: TestClient) -> dict[str, str]:
    """Fetch a CSRF token (sets the cookie) and return the matching header."""
    client.get("/api/auth/csrf")
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def register(client: TestClient, email: str = "owner@example.com", password: str = STRONG_PASSWORD) -> dict[str, str]:
    response = client.post(
        "/api/auth/register", json={"email": email, "password": password, "timezone": "UTC"}, headers=csrf(client)
    )
    assert response.status_code == 201, response.text
    return response.json()

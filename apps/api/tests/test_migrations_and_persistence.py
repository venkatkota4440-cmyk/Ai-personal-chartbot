"""The Alembic migration must build exactly the schema the models describe,
and data must survive an application restart."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from tests.conftest import STRONG_PASSWORD, csrf, register

API_DIR = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "users",
    "user_settings",
    "sessions",
    "conversations",
    "messages",
    "memories",
    "projects",
    "tasks",
    "automations",
    "automation_runs",
    "run_steps",
    "approvals",
    "audit_events",
    "notifications",
}


def _alembic_config(url: str) -> Config:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_migration_matches_models_and_downgrades(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    command.upgrade(_alembic_config(url), "head")
    engine = build_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
        assert diff == [], f"Models and migrations differ: {diff}"

        command.downgrade(_alembic_config(url), "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        engine.dispose()


def test_idempotency_key_is_unique(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    command.upgrade(_alembic_config(url), "head")
    engine = build_engine(url)
    try:
        uniques = inspect(engine).get_unique_constraints("automation_runs")
        assert any(u["column_names"] == ["idempotency_key"] for u in uniques)
    finally:
        engine.dispose()


def test_users_and_settings_persist_across_restart(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'persist.db'}"
    command.upgrade(_alembic_config(url), "head")

    def start_app() -> tuple[TestClient, sessionmaker[Session]]:
        # A brand-new engine and app instance simulates a process restart.
        engine = build_engine(url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        def _db():  # type: ignore[no-untyped-def]
            db = factory()
            try:
                yield db
            finally:
                db.close()

        app = create_app()
        app.dependency_overrides[get_db] = _db
        return TestClient(app), factory

    first, _ = start_app()
    register(first)
    first.patch("/api/settings", json={"timezone": "Asia/Kolkata"}, headers=csrf(first))

    second, _ = start_app()
    login = second.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": STRONG_PASSWORD}, headers=csrf(second)
    )
    assert login.status_code == 200
    assert second.get("/api/settings").json()["timezone"] == "Asia/Kolkata"

"""Shared pytest fixtures.

Provides:
- `tmp_db_path`: a per-test path under tmp_path.
- `db_conn`: a fresh, migrated connection to that path.
- `app`: a Flask test app bound to a per-test DB.
- `client`: a Flask test client (anonymous).
- `auth_client`: a Flask test client already logged in as `tester`.
- `clean_messages`: collects print() output for assertions.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app import create_app
from backend.database import apply_migrations, connect
from backend import models


class _TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret-key-do-not-use-in-prod"
    # Picked up by create_app; overridden per test via env-style attribute.
    DB_PATH: Path = Path("/tmp/_pnav_test_default.db")
    SESSION_DAYS = 1
    PERMANENT_SESSION_LIFETIME = 86400
    FRONTEND_DIR: Path = Path(__file__).resolve().parent.parent / "frontend"


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def db_conn(tmp_db_path: Path):
    """Yield a migrated connection; close it after the test."""
    conn = connect(tmp_db_path)
    apply_migrations(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def app(tmp_db_path: Path, monkeypatch):
    """A Flask test app bound to a per-test DB."""
    # The app reads DB_PATH from the config class. Build a fresh subclass so
    # the per-test path takes effect.
    class Cfg(_TestConfig):
        DB_PATH = tmp_db_path

    flask_app = create_app(Cfg)
    # Apply migrations once before the test client runs.
    conn = connect(tmp_db_path)
    apply_migrations(conn)
    conn.close()

    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """A logged-in test client + the issued CSRF token."""
    resp = client.post("/api/auth/register", json={
        "username": "tester",
        "password": "testpass1",
    })
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    csrf = body["csrf_token"]
    return client, csrf, body["user"]


@pytest.fixture
def clean_messages():
    return []
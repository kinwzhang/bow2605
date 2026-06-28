"""Centralized Flask configuration.

A single Config object lets tests override any field without reaching into
module globals. Set environment variables before `flask run` to override the
defaults in production.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path


class Config:
    """Default configuration.

    SECRET_KEY is generated at process start if not provided via env. This is
    acceptable for the prototype; in production, supply a stable value via the
    PNAV_SECRET_KEY environment variable so sessions survive restarts.
    """

    SECRET_KEY: str = os.environ.get("PNAV_SECRET_KEY") or secrets.token_urlsafe(32)

    # Database path. Default lives under backend/project_navigator.db.
    _DEFAULT_DB = Path(__file__).resolve().parent / "backend" / "project_navigator.db"
    DB_PATH: Path = Path(os.environ.get("PNAV_DB_PATH", str(_DEFAULT_DB)))

    # Session cookie lifetime, in seconds. 30 days matches typical "remember me"
    # UX for a personal tool.
    SESSION_DAYS: int = int(os.environ.get("PNAV_SESSION_DAYS", "30"))
    PERMANENT_SESSION_LIFETIME = SESSION_DAYS * 24 * 60 * 60

    # Where Flask serves the frontend files from.
    FRONTEND_DIR: Path = Path(__file__).resolve().parent / "frontend"

    # Test-mode toggle for in-memory DB and predictable secret.
    TESTING: bool = False


class TestConfig(Config):
    """Configuration used by pytest fixtures."""

    TESTING = True
    SECRET_KEY = "test-secret-key-do-not-use-in-prod"
    DB_PATH: Path = Path("/tmp/_pnav_test.db")  # overridden by conftest fixture
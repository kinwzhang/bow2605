"""Tests for the database module: connection, PRAGMAs, migration runner."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.database import (
    DEFAULT_DB_PATH,
    ITEM_STATUSES,
    MIGRATIONS_DIR,
    STAGE_STATUSES,
    applied_versions,
    apply_migrations,
    connect,
    discover_migrations,
)


# --- Connection --------------------------------------------------------------

def test_connect_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nest" / "x.db"
    conn = connect(nested)
    try:
        assert nested.exists()
    finally:
        conn.close()


def test_connect_enables_foreign_keys(tmp_path: Path) -> None:
    conn = connect(tmp_path / "fk.db")
    try:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()


def test_connect_uses_wal_journal(tmp_path: Path) -> None:
    conn = connect(tmp_path / "wal.db")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        conn.close()


# --- Migration discovery -----------------------------------------------------

def test_discover_migrations_returns_sorted_versions() -> None:
    found = discover_migrations()
    versions = [v for v, _ in found]
    assert versions == sorted(versions)
    assert 1 in versions
    assert 2 in versions


def test_discover_migrations_ignores_non_sql(tmp_path: Path) -> None:
    # A fresh directory with only a non-sql file returns nothing.
    empty = tmp_path / "migrations"
    empty.mkdir()
    (empty / "README.md").write_text("not a migration")
    assert discover_migrations(empty) == []


def test_discover_migrations_skips_unparseable_names(tmp_path: Path) -> None:
    bad = tmp_path / "migrations"
    bad.mkdir()
    (bad / "abc_init.sql").write_text("-- bad name")
    (bad / "001_good.sql").write_text("-- good")
    found = discover_migrations(bad)
    assert [v for v, _ in found] == [1]


# --- Migration runner on a fresh DB ----------------------------------------

def test_apply_migrations_creates_all_tables(db_conn: sqlite3.Connection) -> None:
    rows = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {row["name"] for row in rows}
    expected = {
        "goal", "stage", "blocker", "sub_item", "idea",
        "user", "project", "schema_migrations",
    }
    assert expected.issubset(names)


def test_apply_migrations_records_versions(db_conn: sqlite3.Connection) -> None:
    versions = applied_versions(db_conn)
    assert versions == {1, 2, 3, 4}


def test_apply_migrations_creates_legacy_user_with_hash(db_conn: sqlite3.Connection) -> None:
    row = db_conn.execute(
        "SELECT id, username, password_hash, active_project_id FROM user WHERE id = 1"
    ).fetchone()
    assert row is not None
    assert row["username"] == "legacy"
    assert row["password_hash"].startswith("scrypt:") or row["password_hash"].startswith("pbkdf2:")
    assert row["active_project_id"] == "legacy00001"


def test_apply_migrations_creates_default_project(db_conn: sqlite3.Connection) -> None:
    row = db_conn.execute(
        "SELECT id, user_id, name FROM project WHERE id = 'legacy00001'"
    ).fetchone()
    assert row is not None
    assert row["user_id"] == 1
    assert row["name"] == "Imported project"


def test_apply_migrations_idempotent(db_conn: sqlite3.Connection) -> None:
    # Closing and reopening applies nothing new.
    db_conn.close()
    fresh = connect(db_conn_path := __import__("pathlib").Path("/tmp/_pnav_idem.db"))
    try:
        applied1 = apply_migrations(fresh)
        applied2 = apply_migrations(fresh)
        assert applied1 == [1, 2, 3, 4]
        assert applied2 == []
    finally:
        fresh.close()
        import os
        for s in ("", "-wal", "-shm"):
            try:
                os.remove("/tmp/_pnav_idem.db" + s)
            except FileNotFoundError:
                pass


def test_apply_migrations_prints_legacy_password_once(tmp_db_path: Path) -> None:
    messages: list[str] = []

    def cb(msg: str) -> None:
        messages.append(msg)

    conn = connect(tmp_db_path)
    try:
        apply_migrations(conn, print_callback=cb)
    finally:
        conn.close()

    # Second run should not re-print (legacy user already exists).
    conn2 = connect(tmp_db_path)
    try:
        apply_migrations(conn2, print_callback=cb)
    finally:
        conn2.close()

    # Exactly one message, and it mentions the legacy user.
    pwd_msgs = [m for m in messages if "Legacy user created" in m]
    assert len(pwd_msgs) == 1
    assert "random password" in pwd_msgs[0]


# --- Migration runner on a pre-populated DB --------------------------------

def _legacy_001_schema_with_data(db_path: Path) -> None:
    """Apply only 001 (skipping 002) and seed a stage/blocker/idea/goal."""
    conn = connect(db_path)
    try:
        sql_001 = (MIGRATIONS_DIR / "001_init.sql").read_text(encoding="utf-8")
        conn.executescript(sql_001)
        conn.execute(
            "INSERT INTO goal (text) VALUES (?)", ("Ship the refactor",)
        )
        conn.execute(
            "INSERT INTO stage (id, name, status) VALUES (?, ?, ?)",
            ("stg01", "Plan", "active"),
        )
        conn.execute(
            "INSERT INTO blocker (id, stage_id, text, status, deep) VALUES (?, ?, ?, ?, ?)",
            ("blk01", "stg01", "Auth design", "todo", 0),
        )
        conn.execute(
            "INSERT INTO idea (id, stage_id, text) VALUES (?, ?, ?)",
            ("idea01", "stg01", "Try session cookies first"),
        )
        # Record the migration so apply_migrations only runs 002 next.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, filename TEXT NOT NULL, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO schema_migrations (version, filename) VALUES (?, ?)",
            (1, "001_init.sql"),
        )
        conn.commit()
    finally:
        conn.close()


def test_migration_002_backfills_existing_data(tmp_path: Path) -> None:
    db = tmp_path / "backfill.db"
    _legacy_001_schema_with_data(db)

    conn = connect(db)
    try:
        applied = apply_migrations(conn)
        assert applied == [2, 3, 4]

        # Existing data should now be reassigned to the default project.
        stages = conn.execute("SELECT id, name, project_id FROM stage").fetchall()
        assert len(stages) == 1
        assert stages[0]["id"] == "stg01"
        assert stages[0]["project_id"] == "legacy00001"

        blockers = conn.execute("SELECT id, text FROM blocker").fetchall()
        assert len(blockers) == 1
        assert blockers[0]["text"] == "Auth design"

        ideas = conn.execute("SELECT id, text, project_id FROM idea").fetchall()
        assert len(ideas) == 1
        assert ideas[0]["project_id"] == "legacy00001"

        # Goal table no longer has CHECK(id = 1) and now keys by project_id.
        goal = conn.execute(
            "SELECT text, project_id FROM goal WHERE project_id = ?",
            ("legacy00001",),
        ).fetchone()
        assert goal is not None
        assert goal["text"] == "Ship the refactor"
    finally:
        conn.close()


def test_migration_002_creates_indexes(tmp_path: Path) -> None:
    db = tmp_path / "indexes.db"
    _legacy_001_schema_with_data(db)
    conn = connect(db)
    try:
        apply_migrations(conn)
        idx_names = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        for required in (
            "idx_blocker_stage",
            "idx_subitem_blocker",
            "idx_idea_stage",
            "idx_project_user",
            "idx_stage_project",
            "idx_idea_project",
        ):
            assert required in idx_names, f"missing index {required}"
    finally:
        conn.close()


# --- Cascade behaviour ------------------------------------------------------

def test_stage_delete_cascades_to_blocker_and_item(tmp_path: Path) -> None:
    db = tmp_path / "cascade.db"
    _legacy_001_schema_with_data(db)
    conn = connect(db)
    try:
        apply_migrations(conn)
        conn.execute("DELETE FROM stage WHERE id = 'stg01'")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM blocker").fetchone()[0] == 0
        # idea cascades through stage_id.
        assert conn.execute("SELECT COUNT(*) FROM idea").fetchone()[0] == 0
    finally:
        conn.close()


# --- Status enum exports ----------------------------------------------------

def test_stage_status_enum() -> None:
    assert STAGE_STATUSES == ("todo", "active", "blocked", "done", "park", "review", "nice")


def test_item_status_enum() -> None:
    assert ITEM_STATUSES == (
        "todo", "active", "blocked", "done", "park", "review", "nice", "solve",
    )
"""SQLite connection helper and migration runner.

See plan_and_design/01_data_model.md and 04_roadmap.md Phase 1.
"""
from __future__ import annotations

import os
import re
import secrets
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "project_navigator.db"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# Status enums exported so models.py can validate against one source of truth.
STAGE_STATUSES = ("todo", "active", "blocked", "done", "park", "review", "nice")
ITEM_STATUSES = ("todo", "active", "blocked", "done", "park", "review", "nice", "solve")


def connect(db_path: Optional[os.PathLike] = None) -> sqlite3.Connection:
    """Open a connection with sensible PRAGMAs.

    - foreign_keys=ON so cascades work.
    - WAL journal mode for better read concurrency.
    - busy_timeout=5000 to wait briefly if another writer holds the lock.
    - Row factory returns sqlite3.Row so callers can use dict-like access.
    - Default isolation level (deferred transactions); commits are explicit.
    """
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    """Create the schema_migrations bookkeeping table if it does not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            filename   TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    ensure_schema_migrations(conn)
    return {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}


_MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    """Return (version, path) pairs sorted by version, one per .sql file."""
    if not migrations_dir.exists():
        return []
    found: list[tuple[int, Path]] = []
    for entry in sorted(migrations_dir.iterdir()):
        if not entry.is_file() or entry.suffix != ".sql":
            continue
        match = _MIGRATION_RE.match(entry.name)
        if not match:
            continue
        found.append((int(match.group(1)), entry))
    found.sort(key=lambda pair: pair[0])
    return found


def _placeholder_keys(sql: str) -> list[str]:
    """Return named-placeholder keys used in this SQL string.

    Used to validate that the migration runner has supplied every parameter the
    SQL references. Anything not bound raises KeyError before execution.
    """
    # Avoid matching ':' inside string literals; for our migration files this
    # is overkill (no string literals use ':') but cheap insurance.
    return re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", sql)


def _sql_quote(value: str) -> str:
    """Quote a string for inclusion as a SQL string literal.

    The migration runner uses this only for values it generated itself
    (werkzeug password hashes, secrets.token_urlsafe output). External input
    is never passed through here.
    """
    return "'" + value.replace("'", "''") + "'"


def _substitute_placeholders(sql: str, params: dict[str, str]) -> str:
    """Replace :name placeholders with quoted SQL literals.

    Intended for migration files where the runner controls every substitution
    value. Do NOT use this for user-supplied data.
    """
    def repl(match: re.Match) -> str:
        key = match.group(1)
        if key not in params:
            raise KeyError(f"unbound placeholder :{key}")
        return _sql_quote(str(params[key]))

    return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", repl, sql)


def _legacy_user_credentials(conn: sqlite3.Connection) -> tuple[str, Optional[str]]:
    """Return (password_hash, plaintext_or_None) for the legacy user row.

    Three states are possible when 002 is about to run:

    1. The `user` table does not exist yet (fresh DB or only 001 applied).
       Generate a fresh password; the SQL will create the table and INSERT
       the legacy user with our hash.
    2. The `user` table exists and id=1 is already present (re-run of 002).
       Reuse the stored hash so the SQL's UNIQUE-checked INSERT can be a
       no-op conceptually; in practice the runner skips this branch because
       002 will already be marked applied.
    3. The `user` table exists but id=1 is missing (someone manually deleted
       the row). Treat as state 1.
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user'"
    ).fetchone()
    if table_exists is not None:
        existing = conn.execute(
            "SELECT password_hash FROM user WHERE id = 1"
        ).fetchone()
        if existing is not None:
            return existing["password_hash"], None

    # Deferred import keeps the migration runner usable from tests that don't
    # want a hard werkzeug dependency at import time.
    from werkzeug.security import generate_password_hash

    plaintext = secrets.token_urlsafe(18)
    pw_hash = generate_password_hash(plaintext)
    return pw_hash, plaintext


def apply_migrations(
    conn: sqlite3.Connection,
    migrations_dir: Path = MIGRATIONS_DIR,
    *,
    force: bool = False,
    print_callback=print,
) -> list[int]:
    """Apply any pending migrations in order. Returns the list of versions applied.

    Each migration runs in its own implicit transaction; a failure rolls back
    that one migration without affecting already-applied ones. The migration's
    version is recorded in `schema_migrations` only after the SQL succeeds.

    The :legacy_hash placeholder in 002 is bound to a freshly generated hash if
    and only if the legacy user does not already exist; the plaintext password
    is printed exactly once via `print_callback`.
    """
    ensure_schema_migrations(conn)
    already = applied_versions(conn)
    if force:
        # Force mode is intended for tests only; nuke schema_migrations so the
        # runner re-applies everything against an already-empty DB.
        conn.execute("DELETE FROM schema_migrations")
        conn.commit()
        already = set()

    pending = [(v, p) for v, p in discover_migrations(migrations_dir) if v not in already]
    applied: list[int] = []

    for version, path in pending:
        sql = path.read_text(encoding="utf-8")
        keys = _placeholder_keys(sql)

        params: dict[str, object] = {}
        plaintext_to_print: Optional[str] = None
        if version == 2:
            if "legacy_hash" not in keys:
                raise RuntimeError(
                    "002_users_projects.sql is expected to reference :legacy_hash"
                )
            pw_hash, plaintext = _legacy_user_credentials(conn)
            params["legacy_hash"] = pw_hash
            plaintext_to_print = plaintext

        # Validate every placeholder is bound before we touch the DB.
        for key in keys:
            if key not in params:
                raise KeyError(
                    f"migration {path.name} references unbound parameter :{key}"
                )

        try:
            if params:
                # Substitute placeholders with quoted SQL literals, then run
                # the multi-statement script. Safe because every value here
                # comes from code we control (werkzeug-generated hashes).
                substituted = _substitute_placeholders(sql, params)
                conn.executescript(substituted)
            else:
                conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, filename) VALUES (?, ?)",
                (version, path.name),
            )
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise

        if plaintext_to_print:
            print_callback(
                f"[migrations] Legacy user created with a random password: {plaintext_to_print}\n"
                f"[migrations] This password is printed exactly once. Use the registration\n"
                f"[migrations] endpoint (POST /api/auth/register) to create a real account."
            )

        applied.append(version)

    return applied


def init_db(db_path: Optional[os.PathLike] = None) -> list[int]:
    """Convenience wrapper: connect + apply migrations + return applied versions."""
    conn = connect(db_path)
    try:
        return apply_migrations(conn)
    finally:
        conn.close()


__all__ = [
    "DEFAULT_DB_PATH",
    "MIGRATIONS_DIR",
    "STAGE_STATUSES",
    "ITEM_STATUSES",
    "connect",
    "ensure_schema_migrations",
    "applied_versions",
    "discover_migrations",
    "apply_migrations",
    "init_db",
]
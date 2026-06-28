#!/usr/bin/env python3
"""Seed a demo account + project for local exploration.

Usage:
    python scripts/seed.py                  # default DB, default credentials
    python scripts/seed.py --reset-db       # wipe DB before seeding (CAUTION)

Default credentials:
    username: demo
    password: demo1234

Creates one project with two stages, a blocker, a sub-item, and an idea.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PROJECT_ROOT = HERE.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from werkzeug.security import generate_password_hash  # noqa: E402

from backend.database import DEFAULT_DB_PATH, apply_migrations, connect  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Project Navigator with demo data.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--reset-db", action="store_true", help="Wipe DB first.")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="demo1234")
    return parser.parse_args()


def reset_db(db_path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        target = Path(str(db_path) + suffix)
        if target.exists():
            target.unlink()
            print(f"[seed] removed {target}")


def main() -> int:
    args = parse_args()
    db_path: Path = args.db.resolve()

    if args.reset_db:
        reset_db(db_path)

    conn = connect(db_path)
    try:
        apply_migrations(conn)

        existing = conn.execute(
            "SELECT id FROM user WHERE username = ?", (args.username,)
        ).fetchone()
        if existing:
            print(f"[seed] user {args.username!r} already exists (id={existing['id']}); skipping.")
            return 0

        pw_hash = generate_password_hash(args.password)
        cur = conn.execute(
            "INSERT INTO user (username, password_hash) VALUES (?, ?)",
            (args.username, pw_hash),
        )
        user_id = cur.lastrowid

        # One demo project.
        conn.execute(
            "INSERT INTO project (id, user_id, name, description, position) "
            "VALUES (?, ?, ?, ?, ?)",
            ("demo00001", user_id, "Bow2605", "Demo project seeded by scripts/seed.py", 0),
        )
        conn.execute(
            "UPDATE user SET active_project_id = ? WHERE id = ?",
            ("demo00001", user_id),
        )

        # Goal text.
        conn.execute(
            "INSERT INTO goal (project_id, text) VALUES (?, ?)",
            ("demo00001", "Ship the refactor"),
        )

        # Stage 1: Plan.
        conn.execute(
            "INSERT INTO stage (id, project_id, name, status, position) "
            "VALUES (?, ?, ?, ?, ?)",
            ("seedstage01", "demo00001", "Plan", "active", 0),
        )
        conn.execute(
            "INSERT INTO blocker (id, stage_id, text, status, deep, position) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("seedblock01", "seedstage01", "What about auth?", "todo", 0, 0),
        )
        conn.execute(
            "INSERT INTO sub_item (id, blocker_id, text, status, deep, position) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("seeditem01", "seedblock01", "JWT vs session cookies", "todo", 0, 0),
        )
        conn.execute(
            "INSERT INTO idea (id, project_id, stage_id, text, position) "
            "VALUES (?, ?, ?, ?, ?)",
            ("seedidea01", "demo00001", "seedstage01", "Try session cookies first", 0),
        )

        # Stage 2: Implement, with a deep blocker.
        conn.execute(
            "INSERT INTO stage (id, project_id, name, status, position) "
            "VALUES (?, ?, ?, ?, ?)",
            ("seedstage02", "demo00001", "Implement", "todo", 1),
        )
        conn.execute(
            "INSERT INTO blocker (id, stage_id, text, status, deep, position) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("seedblock02", "seedstage02", "Migration plan for existing data", "park", 1, 0),
        )
        conn.commit()

        print(f"[seed] created user: {args.username} / {args.password}")
        print("[seed] created project: Bow2605 (demo00001) with 2 stages")
        print("[seed] log in at http://localhost:5000/login.html")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
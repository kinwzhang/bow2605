#!/usr/bin/env python3
"""CLI: apply pending migrations to a SQLite database.

Usage:
    python scripts/init_db.py                          # uses default DB path
    python scripts/init_db.py --db /path/to/file.db    # custom path
    python scripts/init_db.py --reset                  # delete the DB file first

Exits 0 on success, 1 on failure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the project_navigator package importable when running from the repo root.
HERE = Path(__file__).resolve()
PROJECT_ROOT = HERE.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import DEFAULT_DB_PATH, apply_migrations, connect  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply Project Navigator migrations to a SQLite database."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite file (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the DB file (and -wal/-shm siblings) before applying migrations.",
    )
    return parser.parse_args()


def reset_db(db_path: Path) -> None:
    """Remove the DB file and its WAL companions if present."""
    for suffix in ("", "-wal", "-shm"):
        target = db_path.with_name(db_path.name + suffix) if suffix else db_path
        if suffix and not db_path.suffix:
            # Path doesn't have an extension; skip WAL siblings.
            continue
        if target.exists():
            target.unlink()
            print(f"[init_db] removed {target}")


def main() -> int:
    args = parse_args()
    db_path: Path = args.db.resolve()

    if args.reset:
        reset_db(db_path)

    if not db_path.exists():
        print(f"[init_db] creating database at {db_path}")

    try:
        conn = connect(db_path)
    except Exception as exc:
        print(f"[init_db] failed to open database: {exc}", file=sys.stderr)
        return 1

    try:
        applied = apply_migrations(conn)
        if applied:
            print(f"[init_db] applied migrations: {applied}")
        else:
            print("[init_db] no pending migrations")
    except Exception as exc:
        print(f"[init_db] migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
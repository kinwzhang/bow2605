"""CRUD helpers for Project Navigator.

Each function takes a sqlite3.Connection (so callers control transactions) and
returns plain dicts / lists — no ORM. Validation lives here so the API layer
can stay thin.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash

from .database import ITEM_STATUSES, STAGE_STATUSES

# Username rules for the prototype: 3–32 chars, letters/digits/underscore/dash/period.
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD_LEN = 6


# ── Errors ────────────────────────────────────────────────────────────────


class ModelError(Exception):
    """Base class for model-layer errors."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ValidationError(ModelError):
    pass


class NotFoundError(ModelError):
    pass


class DuplicateError(ModelError):
    pass


# ── Validation helpers ────────────────────────────────────────────────────


def validate_username(username: object) -> str:
    if not isinstance(username, str) or not USERNAME_RE.match(username):
        raise ValidationError("validation", "username must be 3–32 chars of letters/digits/_-.")
    return username


def validate_password(password: object) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        raise ValidationError("validation", f"password must be at least {MIN_PASSWORD_LEN} characters.")
    return password


def validate_status(status: object, allowed: tuple[str, ...]) -> str:
    if not isinstance(status, str) or status not in allowed:
        raise ValidationError(
            "validation", f"status must be one of {list(allowed)}"
        )
    return status


def validate_nonempty(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("validation", f"{name} must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise ValidationError("validation", f"{name} must not be empty")
    return trimmed


# ── User CRUD ─────────────────────────────────────────────────────────────


def create_user(conn: sqlite3.Connection, username: str, password: str) -> dict:
    """Create a user. Returns the new row as a dict (no password hash)."""
    username = validate_username(username)
    password = validate_password(password)
    pw_hash = generate_password_hash(password)
    try:
        cur = conn.execute(
            "INSERT INTO user (username, password_hash) VALUES (?, ?)",
            (username, pw_hash),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise DuplicateError("duplicate", "username already exists")
    return get_user_by_id(conn, cur.lastrowid)


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, username, active_project_id, created_at FROM user WHERE id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_username(conn: sqlite3.Connection, username: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, username, password_hash, active_project_id, created_at "
        "FROM user WHERE username = ?",
        (username,),
    ).fetchone()
    return dict(row) if row else None


def verify_credentials(conn: sqlite3.Connection, username: str, password: str) -> Optional[dict]:
    """Return the user row (no hash) if credentials match, else None."""
    user = get_user_by_username(conn, username)
    if user is None:
        return None
    if not check_password_hash(user["password_hash"], password):
        return None
    user.pop("password_hash", None)
    return user


def set_active_project(conn: sqlite3.Connection, user_id: int, project_id: Optional[str]) -> None:
    """Update the user's active_project_id. Pass None to clear."""
    conn.execute(
        "UPDATE user SET active_project_id = ? WHERE id = ?",
        (project_id, user_id),
    )
    conn.commit()


# ── Project CRUD ──────────────────────────────────────────────────────────


def create_project(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    project_id: str,
    name: str,
    description: str = "",
    position: Optional[int] = None,
) -> dict:
    """Create a project owned by user_id. Returns the new row as a dict.

    `project_id` is client-generated (uid() format) — collision surfaces as
    DuplicateError so the caller can retry with a fresh id.
    """
    if not isinstance(project_id, str) or not project_id:
        raise ValidationError("validation", "project id is required")
    name = validate_nonempty("name", name)
    if not isinstance(description, str):
        raise ValidationError("validation", "description must be a string")

    if position is None:
        # Append to the end: max(position) + 1, or 0 if no rows yet.
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS m FROM project WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        position = int(row["m"]) + 1
    elif not isinstance(position, int) or position < 0:
        raise ValidationError("validation", "position must be a non-negative integer")

    try:
        conn.execute(
            "INSERT INTO project (id, user_id, name, description, position) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, user_id, name, description, position),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise DuplicateError("collision", "project id already exists")
    return get_project_for_user(conn, project_id, user_id)


def get_project_for_user(
    conn: sqlite3.Connection,
    project_id: str,
    user_id: int,
) -> Optional[dict]:
    """Fetch a project if and only if it is owned by user_id.

    Returning None for both "not yours" and "does not exist" is intentional —
    see plan_and_design/02_api_design.md §6.
    """
    row = conn.execute(
        "SELECT id, user_id, name, description, position, created_at "
        "FROM project WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def list_projects_for_user(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, user_id, name, description, position, created_at "
        "FROM project WHERE user_id = ? ORDER BY position ASC, created_at ASC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_project(
    conn: sqlite3.Connection,
    project_id: str,
    user_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    position: Optional[int] = None,
) -> Optional[dict]:
    """Apply partial updates. Returns the updated row, or None if not found / not owned."""
    sets: list[str] = []
    params: list[object] = []
    if name is not None:
        sets.append("name = ?")
        params.append(validate_nonempty("name", name))
    if description is not None:
        if not isinstance(description, str):
            raise ValidationError("validation", "description must be a string")
        sets.append("description = ?")
        params.append(description)
    if position is not None:
        if not isinstance(position, int) or position < 0:
            raise ValidationError("validation", "position must be a non-negative integer")
        sets.append("position = ?")
        params.append(position)
    if not sets:
        return get_project_for_user(conn, project_id, user_id)

    params.extend([project_id, user_id])
    cur = conn.execute(
        f"UPDATE project SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
        params,
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get_project_for_user(conn, project_id, user_id)


def delete_project(conn: sqlite3.Connection, project_id: str, user_id: int) -> bool:
    """Delete a project (cascades). Returns True if a row was deleted."""
    cur = conn.execute(
        "DELETE FROM project WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def next_project_position(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(position), -1) AS m FROM project WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return int(row["m"]) + 1


# ── Stage / Blocker / SubItem / Idea CRUD ─────────────────────────────────


# Statuses that count as "deep" / "parked" for stage rollup.
DEEP_STATUSES = frozenset({"park", "review", "nice", "solve"})

# Priority order for stage status rollup (top wins):
#
#     todo > active > blocked > review > parked > done > nice
#
# `todo` is the highest priority because if any blocker / sub-item hasn't
# been started, the stage as a whole is still in the planning phase —
# even if other items are deep into active or done.
#
# `solve` is neutral — it does not trigger any priority. If all items are
# `solve` (or any other mix that doesn't trigger), the stage defaults to
# `active` to indicate work is pending.
STAGE_DERIVE_PRIORITY = ("todo", "active", "blocked", "review", "park", "done", "nice")


def derive_stage_status(conn: sqlite3.Connection, stage_id: str) -> Optional[str]:
    """Auto-derive a stage's status from its blockers + sub-items.

    Returns one of the seven stage statuses (``todo``, ``active``,
    ``blocked``, ``done``, ``park``, ``review``, ``nice``) or ``None``
    when the stage has no blockers (caller decides what to do).

    Priority order — first match wins:

      1. ``active``  — any item is ``active``
      2. ``blocked`` — any item is ``blocked``
      3. ``review``  — any item is ``review``
      4. ``park``    — any item is ``park`` (display label: "Parked")
      5. ``done``    — every item is ``done``
      6. ``nice``    — any item is ``nice`` (display label: "Nice to have")
      7. ``active``  — fallback (all ``todo``/``solve``/mixed-neutral)

    The rollup rule lives here so the backend is the single source of truth;
    the frontend mirrors it for optimistic UX.
    """
    rows = conn.execute(
        """
        SELECT status FROM blocker WHERE stage_id = ?
        UNION ALL
        SELECT si.status FROM sub_item si
          JOIN blocker b ON si.blocker_id = b.id
         WHERE b.stage_id = ?
        """,
        (stage_id, stage_id),
    ).fetchall()

    if not rows:
        return None

    statuses = [row["status"] for row in rows]
    for candidate in STAGE_DERIVE_PRIORITY:
        if candidate == "done":
            if all(s == "done" for s in statuses):
                return "done"
        else:
            if candidate in statuses:
                return candidate
    # Fallback: nothing matched (e.g. all items are ``todo``/``solve``).
    return "active"


def reconcile_stage_status(conn: sqlite3.Connection, stage_id: str) -> None:
    """Recompute and persist the stage's auto-derived status.

    No-op when the stage has no blockers (the user-set status stays).
    Persists with a single UPDATE that filters on the current value, so an
    unchanged row produces no write traffic. Commits so the change survives
    the request teardown even if the caller has already committed once.
    """
    derived = derive_stage_status(conn, stage_id)
    if derived is None:
        return
    conn.execute(
        "UPDATE stage SET status = ? WHERE id = ? AND status != ?",
        (derived, stage_id, derived),
    )
    conn.commit()


def _normalize_status_for_deep(status: str, deep: bool) -> str:
    """Apply the deep↔status coupling rules from ANALYSIS.md §6.5.

    - deep=True forces status='park' (assuming status was not already 'park').
    - status='solve' implies deep=False, status='todo' (handled separately
      because it changes deep, not just status).
    """
    if deep and status != "park":
        return "park"
    return status


def _couple_blocker_patch(status: str, deep: bool) -> tuple[str, bool]:
    """Apply the deep↔status coupling for an UPDATE on a blocker/sub-item.

    Returns (final_status, final_deep). Mirrors the frontend's `applyStatus`:
    - status='solve' → ('todo', False) — solving "promotes" the item out of deep.
    - deep=True → ('park', True) — going too deep parks the item.
    - otherwise → unchanged.
    """
    if status == "solve":
        return ("todo", False)
    if deep:
        return ("park", True)
    return (status, deep)


def create_stage(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    stage_id: str,
    name: str,
    status: str = "todo",
    position: Optional[int] = None,
) -> dict:
    """Create a stage within `project_id`. Caller must have verified ownership."""
    if not isinstance(stage_id, str) or not stage_id:
        raise ValidationError("validation", "stage id is required")
    name = validate_nonempty("name", name)
    status = validate_status(status, STAGE_STATUSES)

    if position is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS m FROM stage WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        position = int(row["m"]) + 1
    elif not isinstance(position, int) or position < 0:
        raise ValidationError("validation", "position must be a non-negative integer")

    try:
        conn.execute(
            "INSERT INTO stage (id, project_id, name, status, position) "
            "VALUES (?, ?, ?, ?, ?)",
            (stage_id, project_id, name, status, position),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise DuplicateError("collision", "stage id already exists")
    return get_stage(conn, stage_id)


def get_stage(conn: sqlite3.Connection, stage_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, project_id, name, status, position, created_at "
        "FROM stage WHERE id = ?",
        (stage_id,),
    ).fetchone()
    return dict(row) if row else None


def list_stages_for_project(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, project_id, name, status, position, created_at "
        "FROM stage WHERE project_id = ? ORDER BY position ASC, created_at ASC",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_stage(
    conn: sqlite3.Connection,
    stage_id: str,
    *,
    name: Optional[str] = None,
    status: Optional[str] = None,
    position: Optional[int] = None,
) -> Optional[dict]:
    # Status is auto-derived from items once any exist; reject manual writes
    # in that case so the frontend can't poke a status out of sync.
    if status is not None:
        derived = derive_stage_status(conn, stage_id)
        if derived is not None:
            raise ValidationError(
                "validation",
                "stage status is auto-derived from its blockers/sub-items",
            )

    sets: list[str] = []
    params: list[object] = []
    if name is not None:
        sets.append("name = ?")
        params.append(validate_nonempty("name", name))
    if status is not None:
        sets.append("status = ?")
        params.append(validate_status(status, STAGE_STATUSES))
    if position is not None:
        if not isinstance(position, int) or position < 0:
            raise ValidationError("validation", "position must be a non-negative integer")
        sets.append("position = ?")
        params.append(position)
    if not sets:
        return get_stage(conn, stage_id)
    params.append(stage_id)
    cur = conn.execute(
        f"UPDATE stage SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get_stage(conn, stage_id)


def delete_stage(conn: sqlite3.Connection, stage_id: str) -> bool:
    cur = conn.execute("DELETE FROM stage WHERE id = ?", (stage_id,))
    conn.commit()
    return cur.rowcount > 0


def create_blocker(
    conn: sqlite3.Connection,
    *,
    stage_id: str,
    blocker_id: str,
    text: str,
    status: str = "todo",
    deep: bool = False,
    position: Optional[int] = None,
) -> dict:
    if not isinstance(blocker_id, str) or not blocker_id:
        raise ValidationError("validation", "blocker id is required")
    text = validate_nonempty("text", text)
    status = validate_status(status, ITEM_STATUSES)
    if not isinstance(deep, bool):
        raise ValidationError("validation", "deep must be a boolean")

    status = _normalize_status_for_deep(status, deep)
    deep_int = 1 if deep else 0

    if position is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS m FROM blocker WHERE stage_id = ?",
            (stage_id,),
        ).fetchone()
        position = int(row["m"]) + 1
    elif not isinstance(position, int) or position < 0:
        raise ValidationError("validation", "position must be a non-negative integer")

    try:
        conn.execute(
            "INSERT INTO blocker (id, stage_id, text, status, deep, position) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (blocker_id, stage_id, text, status, deep_int, position),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise DuplicateError("collision", "blocker id already exists")
    reconcile_stage_status(conn, stage_id)
    return get_blocker(conn, blocker_id)


def get_blocker(conn: sqlite3.Connection, blocker_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, stage_id, text, status, deep, position "
        "FROM blocker WHERE id = ?",
        (blocker_id,),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["deep"] = bool(d["deep"])
    return d


def update_blocker(
    conn: sqlite3.Connection,
    blocker_id: str,
    *,
    text: Optional[str] = None,
    status: Optional[str] = None,
    deep: Optional[bool] = None,
    position: Optional[int] = None,
) -> Optional[dict]:
    if text is None and status is None and deep is None and position is None:
        return get_blocker(conn, blocker_id)

    current = get_blocker(conn, blocker_id)
    if current is None:
        return None

    # Resolve the final status/deep with the coupling rules applied.
    incoming_status = validate_status(status, ITEM_STATUSES) if status is not None else current["status"]
    if deep is not None and not isinstance(deep, bool):
        raise ValidationError("validation", "deep must be a boolean")
    incoming_deep = deep if deep is not None else current["deep"]
    final_status, final_deep = _couple_blocker_patch(incoming_status, incoming_deep)

    sets: list[str] = []
    params: list[object] = []
    if text is not None:
        sets.append("text = ?")
        params.append(validate_nonempty("text", text))
    if status is not None or final_status != current["status"]:
        sets.append("status = ?")
        params.append(final_status)
    if deep is not None or final_deep != current["deep"]:
        sets.append("deep = ?")
        params.append(1 if final_deep else 0)
    if position is not None:
        if not isinstance(position, int) or position < 0:
            raise ValidationError("validation", "position must be a non-negative integer")
        sets.append("position = ?")
        params.append(position)

    if not sets:
        return current

    params.append(blocker_id)
    cur = conn.execute(
        f"UPDATE blocker SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    # Recompute parent stage's auto-derived status.
    blocker = get_blocker(conn, blocker_id)
    if blocker is not None:
        reconcile_stage_status(conn, blocker["stage_id"])
    return blocker


def delete_blocker(conn: sqlite3.Connection, blocker_id: str) -> bool:
    # Need the stage_id before we delete, so we can reconcile afterwards.
    row = conn.execute(
        "SELECT stage_id FROM blocker WHERE id = ?", (blocker_id,)
    ).fetchone()
    if row is None:
        return False
    cur = conn.execute("DELETE FROM blocker WHERE id = ?", (blocker_id,))
    conn.commit()
    reconcile_stage_status(conn, row["stage_id"])
    return cur.rowcount > 0


def create_sub_item(
    conn: sqlite3.Connection,
    *,
    blocker_id: str,
    sub_id: str,
    text: str,
    status: str = "todo",
    deep: bool = False,
    position: Optional[int] = None,
) -> dict:
    if not isinstance(sub_id, str) or not sub_id:
        raise ValidationError("validation", "sub-item id is required")
    text = validate_nonempty("text", text)
    status = validate_status(status, ITEM_STATUSES)
    if not isinstance(deep, bool):
        raise ValidationError("validation", "deep must be a boolean")
    status = _normalize_status_for_deep(status, deep)
    deep_int = 1 if deep else 0

    if position is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS m FROM sub_item WHERE blocker_id = ?",
            (blocker_id,),
        ).fetchone()
        position = int(row["m"]) + 1
    elif not isinstance(position, int) or position < 0:
        raise ValidationError("validation", "position must be a non-negative integer")

    try:
        conn.execute(
            "INSERT INTO sub_item (id, blocker_id, text, status, deep, position) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sub_id, blocker_id, text, status, deep_int, position),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise DuplicateError("collision", "sub-item id already exists")
    # Walk up to the stage for status reconciliation.
    row = conn.execute(
        "SELECT stage_id FROM blocker WHERE id = ?", (blocker_id,)
    ).fetchone()
    if row is not None:
        reconcile_stage_status(conn, row["stage_id"])
    return get_sub_item(conn, sub_id)


def get_sub_item(conn: sqlite3.Connection, sub_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, blocker_id, text, status, deep, position "
        "FROM sub_item WHERE id = ?",
        (sub_id,),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["deep"] = bool(d["deep"])
    return d


def update_sub_item(
    conn: sqlite3.Connection,
    sub_id: str,
    *,
    text: Optional[str] = None,
    status: Optional[str] = None,
    deep: Optional[bool] = None,
    position: Optional[int] = None,
) -> Optional[dict]:
    if text is None and status is None and deep is None and position is None:
        return get_sub_item(conn, sub_id)

    current = get_sub_item(conn, sub_id)
    if current is None:
        return None

    incoming_status = validate_status(status, ITEM_STATUSES) if status is not None else current["status"]
    if deep is not None and not isinstance(deep, bool):
        raise ValidationError("validation", "deep must be a boolean")
    incoming_deep = deep if deep is not None else current["deep"]
    final_status, final_deep = _couple_blocker_patch(incoming_status, incoming_deep)

    sets: list[str] = []
    params: list[object] = []
    if text is not None:
        sets.append("text = ?")
        params.append(validate_nonempty("text", text))
    if status is not None or final_status != current["status"]:
        sets.append("status = ?")
        params.append(final_status)
    if deep is not None or final_deep != current["deep"]:
        sets.append("deep = ?")
        params.append(1 if final_deep else 0)
    if position is not None:
        if not isinstance(position, int) or position < 0:
            raise ValidationError("validation", "position must be a non-negative integer")
        sets.append("position = ?")
        params.append(position)

    if not sets:
        return current

    params.append(sub_id)
    cur = conn.execute(
        f"UPDATE sub_item SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    # Walk up to the stage for status reconciliation.
    item = get_sub_item(conn, sub_id)
    if item is not None:
        row = conn.execute(
            "SELECT stage_id FROM blocker WHERE id = ?", (item["blocker_id"],)
        ).fetchone()
        if row is not None:
            reconcile_stage_status(conn, row["stage_id"])
    return item


def delete_sub_item(conn: sqlite3.Connection, sub_id: str) -> bool:
    row = conn.execute(
        "SELECT b.stage_id FROM sub_item si "
        "JOIN blocker b ON si.blocker_id = b.id WHERE si.id = ?",
        (sub_id,),
    ).fetchone()
    if row is None:
        return False
    cur = conn.execute("DELETE FROM sub_item WHERE id = ?", (sub_id,))
    conn.commit()
    reconcile_stage_status(conn, row["stage_id"])
    return cur.rowcount > 0


def create_idea(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    stage_id: str,
    idea_id: str,
    text: str,
    position: Optional[int] = None,
) -> dict:
    if not isinstance(idea_id, str) or not idea_id:
        raise ValidationError("validation", "idea id is required")
    text = validate_nonempty("text", text)

    if position is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS m FROM idea WHERE stage_id = ?",
            (stage_id,),
        ).fetchone()
        position = int(row["m"]) + 1
    elif not isinstance(position, int) or position < 0:
        raise ValidationError("validation", "position must be a non-negative integer")

    try:
        conn.execute(
            "INSERT INTO idea (id, project_id, stage_id, text, position) "
            "VALUES (?, ?, ?, ?, ?)",
            (idea_id, project_id, stage_id, text, position),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise DuplicateError("collision", "idea id already exists")
    return get_idea(conn, idea_id)


def get_idea(conn: sqlite3.Connection, idea_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, project_id, stage_id, text, position "
        "FROM idea WHERE id = ?",
        (idea_id,),
    ).fetchone()
    return dict(row) if row else None


def delete_idea(conn: sqlite3.Connection, idea_id: str) -> bool:
    cur = conn.execute("DELETE FROM idea WHERE id = ?", (idea_id,))
    conn.commit()
    return cur.rowcount > 0


# ── Goal ──────────────────────────────────────────────────────────────────


def get_goal(conn: sqlite3.Connection, project_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT text FROM goal WHERE project_id = ?", (project_id,)
    ).fetchone()
    if row is None:
        return {"text": ""}
    return {"text": row["text"]}


def set_goal(conn: sqlite3.Connection, project_id: str, text: str) -> dict:
    if not isinstance(text, str):
        raise ValidationError("validation", "goal text must be a string")
    text = text.strip()
    # Upsert: delete any existing row for this project, then insert.
    conn.execute("DELETE FROM goal WHERE project_id = ?", (project_id,))
    conn.execute(
        "INSERT INTO goal (project_id, text) VALUES (?, ?)",
        (project_id, text),
    )
    conn.commit()
    return {"text": text}


# ── Snapshot ──────────────────────────────────────────────────────────────


def build_snapshot(conn: sqlite3.Connection, project_id: str) -> Optional[dict]:
    """Return the full tree for one project, or None if the project doesn't exist."""
    project = conn.execute(
        "SELECT id, user_id, name, description FROM project WHERE id = ?",
        (project_id,),
    ).fetchone()
    if project is None:
        return None
    project_d = dict(project)
    project_d.pop("user_id", None)

    goal = get_goal(conn, project_id)
    stages = list_stages_for_project(conn, project_id)

    stage_blocks: list[dict] = []
    for st in stages:
        blockers = conn.execute(
            "SELECT id, text, status, deep, position FROM blocker "
            "WHERE stage_id = ? ORDER BY position ASC",
            (st["id"],),
        ).fetchall()
        blocker_list = []
        for bq in blockers:
            items = conn.execute(
                "SELECT id, text, status, deep, position FROM sub_item "
                "WHERE blocker_id = ? ORDER BY position ASC",
                (bq["id"],),
            ).fetchall()
            blocker_list.append({
                "id": bq["id"],
                "text": bq["text"],
                "status": bq["status"],
                "deep": bool(bq["deep"]),
                "position": bq["position"],
                "items": [
                    {
                        "id": it["id"],
                        "text": it["text"],
                        "status": it["status"],
                        "deep": bool(it["deep"]),
                        "position": it["position"],
                    }
                    for it in items
                ],
            })
        ideas = conn.execute(
            "SELECT id, text, position FROM idea "
            "WHERE stage_id = ? ORDER BY position ASC",
            (st["id"],),
        ).fetchall()
        stage_blocks.append({
            "id": st["id"],
            "name": st["name"],
            "status": st["status"],
            "position": st["position"],
            "blockers": blocker_list,
            "ideas": [dict(i) for i in ideas],
        })

    return {
        "project": project_d,
        "goal": goal,
        "stages": stage_blocks,
    }


__all__ = [
    "ModelError",
    "ValidationError",
    "NotFoundError",
    "DuplicateError",
    "USERNAME_RE",
    "MIN_PASSWORD_LEN",
    "STAGE_STATUSES",
    "ITEM_STATUSES",
    "DEEP_STATUSES",
    "STAGE_DERIVE_PRIORITY",
    "validate_username",
    "validate_password",
    "validate_status",
    "validate_nonempty",
    "create_user",
    "get_user_by_id",
    "get_user_by_username",
    "verify_credentials",
    "set_active_project",
    "create_project",
    "get_project_for_user",
    "list_projects_for_user",
    "update_project",
    "delete_project",
    "next_project_position",
    "create_stage",
    "get_stage",
    "list_stages_for_project",
    "update_stage",
    "delete_stage",
    "create_blocker",
    "get_blocker",
    "update_blocker",
    "delete_blocker",
    "create_sub_item",
    "get_sub_item",
    "update_sub_item",
    "delete_sub_item",
    "create_idea",
    "get_idea",
    "delete_idea",
    "get_goal",
    "set_goal",
    "build_snapshot",
    "derive_stage_status",
    "reconcile_stage_status",
]
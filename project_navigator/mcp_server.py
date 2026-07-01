"""MCP server for Project Navigator.

Lets AI agents interact with Project Navigator's planning hierarchy via the
Model Context Protocol. Connect via stdio or SSE.

Usage:
    pnav-mcp          # stdio (default, for AI agent subprocess)
    pnav-mcp --sse    # SSE server on http://localhost:8000
"""
from __future__ import annotations

import os
import secrets
import sys
import time
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from backend import models
from backend.database import ITEM_STATUSES, STAGE_STATUSES, apply_migrations, connect

# ── Config ────────────────────────────────────────────────────────────────

_env_db = os.environ.get("PNAV_DB_PATH")
DB_PATH = Path(_env_db).resolve() if _env_db else (
    Path(__file__).resolve().parent / "backend" / "project_navigator.db"
)

mcp = FastMCP(
    "Project Navigator",
    instructions="""Interactive planning tool for breaking down goals into stages,
blockers, sub-items, and ideas. The hierarchy is:

  User -> Project -> Stage -> Blocker -> SubItem
                        └──> Idea

Statuses: todo, active, blocked, done, park, review, nice, solve.
Stage status is auto-derived from its blockers. Blocker status is auto-derived
from its sub-items.

When creating entities, provide a `user_id` (integer) to establish ownership.
Project/stage/blocker IDs are auto-generated as base36 strings.""",
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_db():
    conn = connect(DB_PATH)
    apply_migrations(conn)
    return conn


def _uid() -> str:
    """Generate a base36 id matching the frontend's uid() pattern."""
    return f"{int(time.time() * 1000):x}{secrets.token_hex(3)}"


def _format_project(p: dict) -> dict:
    return {k: v for k, v in p.items() if k != "user_id"}


def _user_exists(conn, user_id: int) -> bool:
    return models.get_user_by_id(conn, user_id) is not None


# ── Resources ─────────────────────────────────────────────────────────────

@mcp.resource("pnav://users", title="All users", description="List all registered users")
def list_users_resource() -> str:
    conn = _get_db()
    try:
        users = models.list_users(conn)
        if not users:
            return "No users registered."
        lines = ["# Registered Users\n"]
        for u in users:
            lines.append(f"- **{u['username']}** (id: {u['id']})")
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.resource("pnav://users/{user_id}/projects", title="User projects", description="List projects for a user")
def list_user_projects_resource(user_id: int) -> str:
    conn = _get_db()
    try:
        if not _user_exists(conn, user_id):
            return f"User {user_id} not found."
        projects = models.list_projects_for_user(conn, user_id)
        if not projects:
            return f"User {user_id} has no projects."
        lines = [f"# Projects for user {user_id}\n"]
        for p in projects:
            lines.append(f"- **{p['name']}** (`{p['id']}`) — {p.get('description', '')}")
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.resource("pnav://projects/{project_id}/snapshot", title="Project snapshot",
              description="Full project tree: goal, stages, blockers, sub-items, ideas")
def project_snapshot_resource(project_id: str) -> str:
    conn = _get_db()
    try:
        snap = models.build_snapshot(conn, project_id)
        if snap is None:
            return f"Project `{project_id}` not found."
        return _snapshot_to_markdown(snap)
    finally:
        conn.close()


@mcp.resource("pnav://projects/{project_id}/goal", title="Project goal",
              description="The ultimate goal of a project")
def project_goal_resource(project_id: str) -> str:
    conn = _get_db()
    try:
        goal = models.get_goal(conn, project_id)
        if goal["text"]:
            return f"# Goal\n\n{goal['text']}"
        return "No goal set for this project."
    finally:
        conn.close()


# ── Tool helpers ──────────────────────────────────────────────────────────

def _snapshot_to_markdown(snap: dict) -> str:
    lines = []
    proj = snap["project"]
    lines.append(f"# {proj['name']}\n")
    if proj.get("description"):
        lines.append(f"_{proj['description']}_\n")
    goal = snap.get("goal", {})
    if goal and goal.get("text"):
        lines.append(f"## 🎯 Goal\n{goal['text']}\n")
    for stage in snap.get("stages", []):
        lines.append(f"## 📋 {stage['name']} _({stage['status']})_\n")
        for b in stage.get("blockers", []):
            deep_mark = " 🔍" if b.get("deep") else ""
            lines.append(f"  - **{b['text']}** _({b['status']})_{deep_mark}")
            for item in b.get("items", []):
                d = " 🔍" if item.get("deep") else ""
                lines.append(f"    · {item['text']} _({item['status']})_{d}")
        for idea in stage.get("ideas", []):
            lines.append(f"  💡 {idea['text']}")
        lines.append("")
    return "\n".join(lines)


# ── Tools ─────────────────────────────────────────────────────────────────

# -- Users --

@mcp.tool(description="Register a new user. Returns the user id and username.")
def register_user(username: str, password: str) -> str:
    """Create a new user account.
    - username: 3-32 chars, letters/digits/underscore/dash/period.
    - password: at least 6 characters.
    """
    conn = _get_db()
    try:
        user = models.create_user(conn, username, password)
        return f"User created: **{user['username']}** (id: {user['id']})"
    except models.DuplicateError:
        return f"Error: username '{username}' already exists."
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="List all registered users.")
def list_users() -> str:
    conn = _get_db()
    try:
        users = models.list_users(conn)
        if not users:
            return "No users registered."
        return "\n".join(f"- {u['username']} (id: {u['id']})" for u in users)
    finally:
        conn.close()


# -- Projects --

@mcp.tool(description="Create a new project for a user.")
def create_project(user_id: int, name: str, description: str = "") -> str:
    """Create a project owned by user_id."""
    conn = _get_db()
    try:
        if not _user_exists(conn, user_id):
            return f"Error: user {user_id} not found."
        pid = _uid()
        proj = models.create_project(
            conn, user_id=user_id, project_id=pid, name=name, description=description,
        )
        return f"Project created: **{proj['name']}** (`{proj['id']}`)"
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="Update a project's name or description.")
def update_project(user_id: int, project_id: str, name: Optional[str] = None,
                   description: Optional[str] = None) -> str:
    conn = _get_db()
    try:
        kwargs = {}
        if name is not None:
            kwargs["name"] = name
        if description is not None:
            kwargs["description"] = description
        proj = models.update_project(conn, project_id, user_id, **kwargs)
        if proj is None:
            return "Error: project not found or not owned by this user."
        parts = [f"Project updated: **{proj['name']}**"]
        if name is not None:
            parts.append(f"name → '{name}'")
        if description is not None:
            parts.append(f"description → '{description}'")
        return ", ".join(parts)
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="Delete a project and all its contents (cascading).")
def delete_project(user_id: int, project_id: str) -> str:
    conn = _get_db()
    try:
        ok = models.delete_project(conn, project_id, user_id)
        if ok:
            return f"Project `{project_id}` deleted."
        return f"Error: project `{project_id}` not found or not owned by this user."
    finally:
        conn.close()


@mcp.tool(description="Set the ultimate goal text for a project.")
def set_project_goal(project_id: str, text: str) -> str:
    conn = _get_db()
    try:
        models.set_goal(conn, project_id, text)
        return f"Goal set for project `{project_id}`."
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="Get the full project tree as structured text.")
def get_project_snapshot(project_id: str) -> str:
    conn = _get_db()
    try:
        snap = models.build_snapshot(conn, project_id)
        if snap is None:
            return f"Project `{project_id}` not found."
        return _snapshot_to_markdown(snap)
    finally:
        conn.close()


# -- Stages --

@mcp.tool(description="Add a new stage to a project.")
def create_stage(project_id: str, name: str) -> str:
    conn = _get_db()
    try:
        sid = _uid()
        stage = models.create_stage(conn, project_id=project_id, stage_id=sid, name=name)
        return f"Stage created: **{stage['name']}** (`{stage['id']}`)"
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="Update a stage's name or status.")
def update_stage(stage_id: str, name: Optional[str] = None,
                 status: Optional[str] = None) -> str:
    conn = _get_db()
    try:
        kwargs = {}
        if name is not None:
            kwargs["name"] = name
        if status is not None:
            kwargs["status"] = status
        stage = models.update_stage(conn, stage_id, **kwargs)
        if stage is None:
            return f"Error: stage `{stage_id}` not found."
        return f"Stage updated: **{stage['name']}** ({stage['status']})"
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="Delete a stage and all its blockers/sub-items/ideas.")
def delete_stage(stage_id: str) -> str:
    conn = _get_db()
    try:
        ok = models.delete_stage(conn, stage_id)
        return f"Stage `{stage_id}` deleted." if ok else f"Error: stage `{stage_id}` not found."
    finally:
        conn.close()


# -- Blockers --

@mcp.tool(description="Add a blocker/question to a stage. Things that block progress.")
def create_blocker(stage_id: str, text: str, deep: bool = False) -> str:
    conn = _get_db()
    try:
        bid = _uid()
        blocker = models.create_blocker(
            conn, stage_id=stage_id, blocker_id=bid, text=text, deep=deep,
        )
        return f"Blocker created: **{blocker['text']}** (`{blocker['id']}`)"
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="Update a blocker's text, status, or deep flag.")
def update_blocker(blocker_id: str, text: Optional[str] = None,
                   status: Optional[str] = None, deep: Optional[bool] = None) -> str:
    conn = _get_db()
    try:
        kwargs = {}
        if text is not None:
            kwargs["text"] = text
        if status is not None:
            kwargs["status"] = status
        if deep is not None:
            kwargs["deep"] = deep
        blocker = models.update_blocker(conn, blocker_id, **kwargs)
        if blocker is None:
            return f"Error: blocker `{blocker_id}` not found."
        return f"Blocker updated: **{blocker['text']}** ({blocker['status']})"
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="Delete a blocker and its sub-items.")
def delete_blocker(blocker_id: str) -> str:
    conn = _get_db()
    try:
        ok = models.delete_blocker(conn, blocker_id)
        return f"Blocker `{blocker_id}` deleted." if ok else f"Error: blocker `{blocker_id}` not found."
    finally:
        conn.close()


# -- Sub-items --

@mcp.tool(description="Add a sub-item (action step) to a blocker.")
def create_sub_item(blocker_id: str, text: str, deep: bool = False) -> str:
    conn = _get_db()
    try:
        sid = _uid()
        item = models.create_sub_item(
            conn, blocker_id=blocker_id, sub_id=sid, text=text, deep=deep,
        )
        return f"Sub-item created: **{item['text']}** (`{item['id']}`)"
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="Update a sub-item's text, status, or deep flag.")
def update_sub_item(sub_id: str, text: Optional[str] = None,
                    status: Optional[str] = None, deep: Optional[bool] = None) -> str:
    conn = _get_db()
    try:
        kwargs = {}
        if text is not None:
            kwargs["text"] = text
        if status is not None:
            kwargs["status"] = status
        if deep is not None:
            kwargs["deep"] = deep
        item = models.update_sub_item(conn, sub_id, **kwargs)
        if item is None:
            return f"Error: sub-item `{sub_id}` not found."
        return f"Sub-item updated: **{item['text']}** ({item['status']})"
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="Delete a sub-item.")
def delete_sub_item(sub_id: str) -> str:
    conn = _get_db()
    try:
        ok = models.delete_sub_item(conn, sub_id)
        return f"Sub-item `{sub_id}` deleted." if ok else f"Error: sub-item `{sub_id}` not found."
    finally:
        conn.close()


# -- Ideas --

@mcp.tool(description="Add an idea/note to a stage.")
def create_idea(project_id: str, stage_id: str, text: str) -> str:
    conn = _get_db()
    try:
        iid = _uid()
        idea = models.create_idea(
            conn, project_id=project_id, stage_id=stage_id, idea_id=iid, text=text,
        )
        return f"Idea created: **{idea['text']}** (`{idea['id']}`)"
    except models.ValidationError as e:
        return f"Error: {e.message}"
    finally:
        conn.close()


@mcp.tool(description="Delete an idea.")
def delete_idea(idea_id: str) -> str:
    conn = _get_db()
    try:
        ok = models.delete_idea(conn, idea_id)
        return f"Idea `{idea_id}` deleted." if ok else f"Error: idea `{idea_id}` not found."
    finally:
        conn.close()


# ── Prompt Templates ──────────────────────────────────────────────────────

@mcp.prompt(name="navigate-project", title="Navigate a project",
            description="Guide the AI to explore and update a project")
def navigate_project_prompt(project_id: str) -> str:
    return (
        f"I want to work on project `{project_id}`. "
        f"First, get the project snapshot so we can see the current state. "
        f"Then we can discuss what to do next — add stages, blockers, sub-items, "
        f"or update existing ones."
    )


# ── Entrypoint ────────────────────────────────────────────────────────────

def main():
    if "--sse" in sys.argv:
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

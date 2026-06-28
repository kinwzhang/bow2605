"""Phase 7 acceptance — sidebar / header flows.

These tests exercise the API endpoints that the frontend's sidebar and header
use. The DOM-level rendering is not unit-tested (it requires a browser);
instead we verify the backend contracts the sidebar relies on.
"""
from __future__ import annotations


def _register(client, *, username="alice"):
    resp = client.post("/api/auth/register", json={"username": username, "password": "validpw1"})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["csrf_token"]


def _csrf(client):
    return client.get("/api/auth/me").get_json()["csrf_token"]


# ── Sidebar list rendering ────────────────────────────────────────────────


def test_sidebar_lists_user_projects(client):
    csrf = _register(client)
    # Create two projects.
    for i, name in enumerate(("Project A", "Project B")):
        resp = client.post(
            "/api/projects",
            json={"id": f"p{i+1}", "name": name},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200

    me = client.get("/api/auth/me").get_json()
    names = sorted(p["name"] for p in me["projects"])
    assert names == ["Project A", "Project B"]


def test_sidebar_active_project_highlight(client):
    csrf = _register(client)
    for i in (1, 2):
        client.post(
            "/api/projects",
            json={"id": f"p{i}", "name": f"P{i}"},
            headers={"X-CSRF-Token": csrf},
        )
    client.put("/api/projects/p2/active", headers={"X-CSRF-Token": csrf})

    me = client.get("/api/auth/me").get_json()
    assert me["active_project_id"] == "p2"


# ── Project CRUD from the sidebar ─────────────────────────────────────────


def test_sidebar_create_project(client):
    csrf = _register(client)
    resp = client.post(
        "/api/projects",
        json={"id": "newproj", "name": "New project"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "New project"

    # The new project shows up in /me.
    me = client.get("/api/auth/me").get_json()
    assert any(p["id"] == "newproj" for p in me["projects"])


def test_sidebar_rename_project(client):
    csrf = _register(client)
    client.post("/api/projects",
                json={"id": "p1", "name": "Old name"},
                headers={"X-CSRF-Token": csrf})
    resp = client.patch(
        "/api/projects/p1",
        json={"name": "New name"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "New name"


def test_sidebar_delete_project_cascades_and_clears_active(client):
    csrf = _register(client)
    # Create p1 with a stage, set it active, then delete it.
    client.post("/api/projects",
                json={"id": "p1", "name": "X"},
                headers={"X-CSRF-Token": csrf})
    client.put("/api/projects/p1/active", headers={"X-CSRF-Token": csrf})

    # Add a stage under p1 (need fresh CSRF after /me rotation).
    csrf = _csrf(client)
    resp = client.post(
        "/api/projects/p1/stages",
        json={"id": "s1", "name": "Stage"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200

    # Delete p1.
    csrf = _csrf(client)
    resp = client.delete("/api/projects/p1", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204

    me = client.get("/api/auth/me").get_json()
    assert me["projects"] == []
    assert me["active_project_id"] is None


# ── Active project memory ─────────────────────────────────────────────────


def test_active_project_persists_across_reloads(client):
    csrf = _register(client)
    client.post("/api/projects",
                json={"id": "p1", "name": "X"},
                headers={"X-CSRF-Token": csrf})
    client.put("/api/projects/p1/active", headers={"X-CSRF-Token": csrf})

    # Simulate a reload: re-fetch /me and verify the active id sticks.
    me = client.get("/api/auth/me").get_json()
    assert me["active_project_id"] == "p1"


# ── Switch user (logout + redirect) ───────────────────────────────────────


def test_logout_via_switch_user_returns_to_login_state(client):
    csrf = _register(client)
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

    # /me now requires re-auth.
    assert client.get("/api/auth/me").status_code == 401
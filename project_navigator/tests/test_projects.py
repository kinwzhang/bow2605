"""Tests for /api/projects/* endpoints and project CRUD helpers."""
from __future__ import annotations


# ── Helpers ───────────────────────────────────────────────────────────────


def _csrf(client) -> str:
    me = client.get("/api/auth/me")
    return me.get_json()["csrf_token"]


def _auth(client, *, username="alice", password="validpw1"):
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.get_json()
    # The register response carries the CSRF token directly — no need to call
    # /me (which would rotate the token and break subsequent mutating calls).
    return resp.get_json()["csrf_token"]


# ── /api/auth/me returns active_project_id + projects list ───────────────


def test_me_includes_projects_list(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "validpw1"})
    me = client.get("/api/auth/me")
    body = me.get_json()
    assert "projects" in body
    assert body["active_project_id"] is None  # nothing active yet
    assert body["projects"] == []


# ── List projects ─────────────────────────────────────────────────────────


def test_list_projects_empty(client):
    _auth(client)
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["projects"] == []
    assert body["active_project_id"] is None


def test_list_projects_ordered_by_position(client):
    _auth(client)
    csrf = _csrf(client)
    for i, name in enumerate(("Gamma", "Alpha", "Beta")):
        client.post(
            "/api/projects",
            json={"id": f"p{i}", "name": name},
            headers={"X-CSRF-Token": csrf},
        )
    resp = client.get("/api/projects")
    names = [p["name"] for p in resp.get_json()["projects"]]
    assert names == ["Gamma", "Alpha", "Beta"]  # creation order = position order


def test_list_projects_isolated_between_users(client):
    # Register both users (in any order — the session is shared, so we log out
    # between them).
    csrf_a = _auth(client, username="alice")
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_a})
    _auth(client, username="bob")
    client.post("/api/auth/logout", headers={"X-CSRF-Token": _csrf(client)})

    # Log in as alice and create her projects.
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "validpw1"})
    csrf_a = resp.get_json()["csrf_token"]
    client.post("/api/projects", json={"id": "a1", "name": "Alice 1"},
                headers={"X-CSRF-Token": csrf_a})
    client.post("/api/projects", json={"id": "a2", "name": "Alice 2"},
                headers={"X-CSRF-Token": csrf_a})

    # Switch to bob.
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_a})
    resp = client.post("/api/auth/login", json={"username": "bob", "password": "validpw1"})
    csrf_b = resp.get_json()["csrf_token"]
    client.post("/api/projects", json={"id": "b1", "name": "Bob 1"},
                headers={"X-CSRF-Token": csrf_b})

    # bob must not see alice's projects.
    resp = client.get("/api/projects")
    projects = resp.get_json()["projects"]
    names = [p["name"] for p in projects]
    assert names == ["Bob 1"]

    # alice, after logging back in, sees only her projects.
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_b})
    client.post("/api/auth/login", json={"username": "alice", "password": "validpw1"})
    resp = client.get("/api/projects")
    names = sorted(p["name"] for p in resp.get_json()["projects"])
    assert names == ["Alice 1", "Alice 2"]


# ── Create project ────────────────────────────────────────────────────────


def test_create_project_minimal(client):
    _auth(client)
    csrf = _csrf(client)
    resp = client.post(
        "/api/projects",
        json={"id": "p1", "name": "Bow2605"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["name"] == "Bow2605"
    assert body["description"] == ""
    assert body["position"] == 0


def test_create_project_with_description(client):
    _auth(client)
    csrf = _csrf(client)
    resp = client.post(
        "/api/projects",
        json={"id": "p1", "name": "Bow2605", "description": "v2 spec", "position": 5},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["description"] == "v2 spec"
    assert body["position"] == 5


def test_create_project_appends_position_when_omitted(client):
    _auth(client)
    csrf = _csrf(client)
    for i in range(3):
        client.post(
            "/api/projects",
            json={"id": f"p{i}", "name": f"P{i}"},
            headers={"X-CSRF-Token": csrf},
        )
    resp = client.get("/api/projects")
    positions = [p["position"] for p in resp.get_json()["projects"]]
    assert positions == [0, 1, 2]


def test_create_project_rejects_empty_name(client):
    _auth(client)
    csrf = _csrf(client)
    resp = client.post(
        "/api/projects",
        json={"id": "p1", "name": "   "},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 400


def test_create_project_rejects_collision(client):
    _auth(client)
    csrf = _csrf(client)
    client.post(
        "/api/projects",
        json={"id": "p1", "name": "First"},
        headers={"X-CSRF-Token": csrf},
    )
    resp = client.post(
        "/api/projects",
        json={"id": "p1", "name": "Duplicate"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "collision"


def test_create_project_requires_csrf(client):
    _auth(client)
    resp = client.post("/api/projects", json={"id": "p1", "name": "X"})
    assert resp.status_code == 403


def test_create_project_requires_auth(client):
    resp = client.post("/api/projects", json={"id": "p1", "name": "X"},
                       headers={"X-CSRF-Token": "anything"})
    assert resp.status_code == 401


# ── Patch project ─────────────────────────────────────────────────────────


def test_patch_project_rename(client):
    _auth(client)
    csrf = _csrf(client)
    client.post("/api/projects", json={"id": "p1", "name": "Old"},
                headers={"X-CSRF-Token": csrf})
    resp = client.patch(
        "/api/projects/p1",
        json={"name": "New"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "New"


def test_patch_project_description_only(client):
    _auth(client)
    csrf = _csrf(client)
    client.post("/api/projects", json={"id": "p1", "name": "X"},
                headers={"X-CSRF-Token": csrf})
    resp = client.patch(
        "/api/projects/p1",
        json={"description": "Added"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.get_json()["description"] == "Added"


def test_patch_other_users_project_returns_404(client):
    csrf_a = _auth(client, username="alice")
    client.post("/api/projects", json={"id": "p1", "name": "Alice's"},
                headers={"X-CSRF-Token": csrf_a})
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_a})
    _auth(client, username="bob")

    csrf_b = _csrf(client)
    resp = client.patch(
        "/api/projects/p1",
        json={"name": "Hijacked"},
        headers={"X-CSRF-Token": csrf_b},
    )
    # 404 (not 403) to avoid resource enumeration.
    assert resp.status_code == 404


# ── Delete project + cascade ─────────────────────────────────────────────


def test_delete_project_cascades(client, tmp_db_path):
    csrf = _auth(client)
    client.post("/api/projects", json={"id": "p1", "name": "Bow2605"},
                headers={"X-CSRF-Token": csrf})

    # Look up alice's user_id so we can scope cascade checks to her data only
    # (the DB also has a legacy user with the legacy00001 project).
    me = client.get("/api/auth/me").get_json()
    alice_id = me["user"]["id"]
    # /me rotated the CSRF token — re-fetch for the upcoming mutating call.
    csrf = _csrf(client)

    # Insert a stage directly to verify cascade on delete.
    import sqlite3
    conn = sqlite3.connect(tmp_db_path)
    conn.execute(
        "INSERT INTO stage (id, project_id, name) VALUES (?, ?, ?)",
        ("s1", "p1", "Plan"),
    )
    conn.execute(
        "INSERT INTO blocker (id, stage_id, text) VALUES (?, ?, ?)",
        ("b1", "s1", "Auth?"),
    )
    conn.commit()
    conn.close()

    resp = client.delete("/api/projects/p1", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204

    conn = sqlite3.connect(tmp_db_path)
    n_alice_projects = conn.execute(
        "SELECT COUNT(*) FROM project WHERE user_id = ?", (alice_id,)
    ).fetchone()[0]
    n_alice_stages = conn.execute(
        "SELECT COUNT(*) FROM stage WHERE project_id IN (SELECT id FROM project WHERE user_id = ?)",
        (alice_id,),
    ).fetchone()[0]
    n_alice_blockers = conn.execute(
        "SELECT COUNT(*) FROM blocker WHERE stage_id IN ("
        "  SELECT id FROM stage WHERE project_id IN (SELECT id FROM project WHERE user_id = ?)"
        ")",
        (alice_id,),
    ).fetchone()[0]
    conn.close()
    assert n_alice_projects == 0
    assert n_alice_stages == 0
    assert n_alice_blockers == 0


def test_delete_other_users_project_returns_404(client):
    csrf_a = _auth(client, username="alice")
    client.post("/api/projects", json={"id": "p1", "name": "Alice"},
                headers={"X-CSRF-Token": csrf_a})
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_a})
    _auth(client, username="bob")
    csrf_b = _csrf(client)

    resp = client.delete("/api/projects/p1", headers={"X-CSRF-Token": csrf_b})
    assert resp.status_code == 404


def test_deleting_active_project_clears_active(client):
    _auth(client)
    csrf = _csrf(client)
    client.post("/api/projects", json={"id": "p1", "name": "One"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/projects", json={"id": "p2", "name": "Two"},
                headers={"X-CSRF-Token": csrf})
    client.put("/api/projects/p1/active", headers={"X-CSRF-Token": csrf})

    client.delete("/api/projects/p1", headers={"X-CSRF-Token": csrf})

    me = client.get("/api/auth/me")
    body = me.get_json()
    assert body["active_project_id"] in (None, "p2")  # rolled over or cleared


# ── Active project memory ─────────────────────────────────────────────────


def test_set_active_project(client):
    _auth(client)
    csrf = _csrf(client)
    client.post("/api/projects", json={"id": "p1", "name": "X"},
                headers={"X-CSRF-Token": csrf})
    resp = client.put("/api/projects/p1/active", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204

    me = client.get("/api/auth/me")
    assert me.get_json()["active_project_id"] == "p1"


def test_set_active_project_404_for_other_user(client):
    csrf_a = _auth(client, username="alice")
    client.post("/api/projects", json={"id": "p1", "name": "Alice"},
                headers={"X-CSRF-Token": csrf_a})
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_a})
    _auth(client, username="bob")

    resp = client.put("/api/projects/p1/active", headers={"X-CSRF-Token": _csrf(client)})
    assert resp.status_code == 404


def test_set_active_project_requires_csrf(client):
    _auth(client)
    client.post("/api/projects", json={"id": "p1", "name": "X"},
                headers={"X-CSRF-Token": _csrf(client)})
    resp = client.put("/api/projects/p1/active")
    assert resp.status_code == 403
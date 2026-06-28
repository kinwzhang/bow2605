"""Tests for project-scoped stage/blocker/sub-item/idea routes + snapshot."""
from __future__ import annotations


# ── Helpers ───────────────────────────────────────────────────────────────


def _auth(client, *, username="alice"):
    resp = client.post("/api/auth/register", json={"username": username, "password": "validpw1"})
    return resp.get_json()["csrf_token"]


def _new_project(client, csrf, pid="p1", name="Bow2605"):
    return client.post(
        "/api/projects",
        json={"id": pid, "name": name},
        headers={"X-CSRF-Token": csrf},
    )


def _csrf_after(client) -> str:
    return client.get("/api/auth/me").get_json()["csrf_token"]


# ── Snapshot ──────────────────────────────────────────────────────────────


def test_snapshot_empty_project(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    resp = client.get("/api/projects/p1/snapshot")
    assert resp.status_code == 200
    snap = resp.get_json()
    assert snap["project"]["name"] == "Bow2605"
    assert snap["goal"] == {"text": ""}
    assert snap["stages"] == []


def test_snapshot_full_tree(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.put("/api/projects/p1/goal", json={"text": "Ship the v2"},
               headers={"X-CSRF-Token": csrf})
    csrf = _csrf_after(client)
    client.post("/api/projects/p1/stages", json={"id": "s1", "name": "Plan"},
                 headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/stages/s1/blockers",
                 json={"id": "b1", "text": "Auth?"},
                 headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/blockers/b1/items",
                 json={"id": "i1", "text": "JWT vs session"},
                 headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/stages/s1/ideas",
                 json={"id": "d1", "text": "Try cookie-first"},
                 headers={"X-CSRF-Token": csrf})

    snap = client.get("/api/projects/p1/snapshot").get_json()
    assert snap["goal"]["text"] == "Ship the v2"
    assert len(snap["stages"]) == 1
    st = snap["stages"][0]
    assert st["name"] == "Plan"
    assert st["blockers"][0]["text"] == "Auth?"
    assert st["blockers"][0]["items"][0]["text"] == "JWT vs session"
    assert st["ideas"][0]["text"] == "Try cookie-first"


def test_snapshot_404_for_other_user(client):
    csrf_a = _auth(client, username="alice")
    _new_project(client, csrf_a, pid="p1", name="Alice")
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_a})
    _auth(client, username="bob")

    resp = client.get("/api/projects/p1/snapshot")
    assert resp.status_code == 404


# ── Stages ────────────────────────────────────────────────────────────────


def test_create_stage_minimal(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    resp = client.post("/api/projects/p1/stages",
                       json={"id": "s1", "name": "Plan"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["name"] == "Plan"
    assert body["status"] == "todo"
    assert body["position"] == 0


def test_create_stage_rejects_bad_status(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    resp = client.post("/api/projects/p1/stages",
                       json={"id": "s1", "name": "Plan", "status": "park"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "validation"


def test_create_stage_rejects_empty_name(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    resp = client.post("/api/projects/p1/stages",
                       json={"id": "s1", "name": "   "},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 400


def test_create_stage_collision_returns_409(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    resp = client.post("/api/projects/p1/stages",
                       json={"id": "s1", "name": "Other"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 409


def test_create_stage_requires_csrf(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    resp = client.post("/api/projects/p1/stages", json={"id": "s1", "name": "Plan"})
    assert resp.status_code == 403


def test_create_stage_requires_auth(client):
    resp = client.post("/api/projects/p1/stages",
                       json={"id": "s1", "name": "Plan"},
                       headers={"X-CSRF-Token": "anything"})
    assert resp.status_code == 401


def test_create_stage_404_for_other_project(client):
    csrf = _auth(client)
    _new_project(client, csrf, pid="p1")
    resp = client.post("/api/projects/other/stages",
                       json={"id": "s1", "name": "Plan"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 404


def test_patch_stage_rename(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Old"},
                headers={"X-CSRF-Token": csrf})
    resp = client.patch("/api/projects/p1/stages/s1",
                        json={"name": "New"},
                        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "New"


def test_patch_stage_invalid_status(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    resp = client.patch("/api/projects/p1/stages/s1",
                        json={"status": "park"},
                        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 400


def test_delete_stage_cascades_blockers_and_ideas(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/stages/s1/blockers",
                json={"id": "b1", "text": "Auth?"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/stages/s1/ideas",
                json={"id": "d1", "text": "Note"},
                headers={"X-CSRF-Token": csrf})

    resp = client.delete("/api/projects/p1/stages/s1",
                         headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204

    snap = client.get("/api/projects/p1/snapshot").get_json()
    assert snap["stages"] == []


# ── Blockers ──────────────────────────────────────────────────────────────


def test_create_blocker(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    resp = client.post("/api/projects/p1/stages/s1/blockers",
                       json={"id": "b1", "text": "Auth?"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "todo"
    assert body["deep"] is False


def test_blocker_deep_true_forces_park(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    resp = client.post("/api/projects/p1/stages/s1/blockers",
                       json={"id": "b1", "text": "X", "deep": True, "status": "todo"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["deep"] is True
    assert body["status"] == "park"


def test_blocker_solve_forces_todo_and_unset_deep(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    # Create a deep blocker, then mark it solve.
    client.post("/api/projects/p1/stages/s1/blockers",
                json={"id": "b1", "text": "X", "deep": True},
                headers={"X-CSRF-Token": csrf})
    resp = client.patch("/api/projects/p1/blockers/b1",
                        json={"status": "solve"},
                        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "todo"
    assert body["deep"] is False


def test_blocker_invalid_status_rejected(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    resp = client.post("/api/projects/p1/stages/s1/blockers",
                       json={"id": "b1", "text": "X", "status": "frobnicate"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 400


def test_delete_blocker_cascades_items(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/stages/s1/blockers",
                json={"id": "b1", "text": "X"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/blockers/b1/items",
                json={"id": "i1", "text": "Y"},
                headers={"X-CSRF-Token": csrf})

    resp = client.delete("/api/projects/p1/blockers/b1",
                         headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204

    snap = client.get("/api/projects/p1/snapshot").get_json()
    assert snap["stages"][0]["blockers"] == []


# ── Sub-items ──────────────────────────────────────────────────────────────


def test_create_sub_item(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/stages/s1/blockers",
                json={"id": "b1", "text": "X"},
                headers={"X-CSRF-Token": csrf})
    resp = client.post("/api/projects/p1/blockers/b1/items",
                       json={"id": "i1", "text": "Y"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert resp.get_json()["text"] == "Y"


def test_sub_item_deep_status_coupling(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/stages/s1/blockers",
                json={"id": "b1", "text": "X"},
                headers={"X-CSRF-Token": csrf})
    resp = client.post("/api/projects/p1/blockers/b1/items",
                       json={"id": "i1", "text": "Y", "deep": True},
                       headers={"X-CSRF-Token": csrf})
    assert resp.get_json()["status"] == "park"


def test_delete_sub_item(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/stages/s1/blockers",
                json={"id": "b1", "text": "X"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/blockers/b1/items",
                json={"id": "i1", "text": "Y"},
                headers={"X-CSRF-Token": csrf})
    resp = client.delete("/api/projects/p1/subitems/i1",
                         headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204


# ── Ideas ─────────────────────────────────────────────────────────────────


def test_create_and_delete_idea(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    resp = client.post("/api/projects/p1/stages/s1/ideas",
                       json={"id": "d1", "text": "Note"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200

    resp = client.delete("/api/projects/p1/ideas/d1",
                         headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204


def test_idea_wrong_project_404(client):
    csrf = _auth(client)
    _new_project(client, csrf, pid="p1")
    _new_project(client, csrf, pid="p2", name="Other")
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/projects/p1/stages/s1/ideas",
                json={"id": "d1", "text": "X"},
                headers={"X-CSRF-Token": csrf})
    # d1 belongs to p1 — deleting under p2 must 404.
    resp = client.delete("/api/projects/p2/ideas/d1",
                         headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 404


# ── Stage auto-derivation ────────────────────────────────────────────────


def _setup_with_blocker(client, *, stage_status="active"):
    """Helper: register, create project + stage + blocker. Return CSRF."""
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Plan", "status": stage_status},
                headers={"X-CSRF-Token": csrf})
    csrf = _csrf_after(client)
    client.post("/api/projects/p1/stages/s1/blockers",
                json={"id": "b1", "text": "X"},
                headers={"X-CSRF-Token": csrf})
    return _csrf_after(client)


def test_stage_status_auto_derives_to_done_when_all_items_done(client):
    csrf = _setup_with_blocker(client)
    # Mark blocker done.
    client.patch("/api/projects/p1/blockers/b1",
                 json={"status": "done"},
                 headers={"X-CSRF-Token": csrf})

    snap = client.get("/api/projects/p1/snapshot").get_json()
    assert snap["stages"][0]["status"] == "done"


def test_stage_status_auto_derives_to_blocked_when_any_item_deep(client):
    csrf = _setup_with_blocker(client)
    client.patch("/api/projects/p1/blockers/b1",
                 json={"deep": True},  # deep=true forces status='park'
                 headers={"X-CSRF-Token": csrf})

    snap = client.get("/api/projects/p1/snapshot").get_json()
    assert snap["stages"][0]["status"] == "blocked"


def test_stage_status_auto_derives_to_active_for_mixed_normal(client):
    csrf = _setup_with_blocker(client)
    # b1 stays 'todo' → stage should be 'active'
    snap = client.get("/api/projects/p1/snapshot").get_json()
    assert snap["stages"][0]["status"] == "active"


def test_stage_status_recompute_on_sub_item_change(client):
    csrf = _setup_with_blocker(client)
    csrf = _csrf_after(client)
    # Add a sub-item to the blocker.
    client.post("/api/projects/p1/blockers/b1/items",
                json={"id": "i1", "text": "sub"},
                headers={"X-CSRF-Token": csrf})
    # Mark BOTH items done — only then is the rollup 'done'.
    csrf = _csrf_after(client)
    client.patch("/api/projects/p1/blockers/b1",
                 json={"status": "done"},
                 headers={"X-CSRF-Token": csrf})
    csrf = _csrf_after(client)
    client.patch("/api/projects/p1/subitems/i1",
                 json={"status": "done"},
                 headers={"X-CSRF-Token": csrf})
    snap = client.get("/api/projects/p1/snapshot").get_json()
    assert snap["stages"][0]["status"] == "done"


def test_stage_status_recompute_on_blocker_delete(client):
    csrf = _setup_with_blocker(client, stage_status="active")
    # Delete the only blocker → no items → stage keeps the user-set 'active'.
    csrf = _csrf_after(client)
    client.delete("/api/projects/p1/blockers/b1",
                  headers={"X-CSRF-Token": csrf})
    snap = client.get("/api/projects/p1/snapshot").get_json()
    # No items → derivation returns None → status stays 'active' (set by user).
    assert snap["stages"][0]["status"] == "active"


def test_stage_patch_status_rejected_when_items_exist(client):
    csrf = _setup_with_blocker(client)
    resp = client.patch("/api/projects/p1/stages/s1",
                        json={"status": "done"},
                        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 400
    assert "auto-derived" in resp.get_json()["error"]


def test_stage_patch_name_allowed_when_items_exist(client):
    csrf = _setup_with_blocker(client)
    resp = client.patch("/api/projects/p1/stages/s1",
                        json={"name": "Renamed"},
                        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Renamed"


def test_stage_patch_status_allowed_when_no_items(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    client.post("/api/projects/p1/stages",
                json={"id": "s1", "name": "Empty"},
                headers={"X-CSRF-Token": csrf})
    csrf = _csrf_after(client)
    resp = client.patch("/api/projects/p1/stages/s1",
                        json={"status": "active"},
                        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "active"


# ── Goal ──────────────────────────────────────────────────────────────────


def test_goal_upsert(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    resp = client.put("/api/projects/p1/goal",
                      json={"text": "Ship"},
                      headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert resp.get_json() == {"text": "Ship"}

    # Update replaces, does not append.
    client.put("/api/projects/p1/goal",
               json={"text": "Refine"},
               headers={"X-CSRF-Token": csrf})
    snap = client.get("/api/projects/p1/snapshot").get_json()
    assert snap["goal"] == {"text": "Refine"}


def test_goal_rejects_non_string(client):
    csrf = _auth(client)
    _new_project(client, csrf)
    resp = client.put("/api/projects/p1/goal",
                      json={"text": 12345},
                      headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 400


# ── Cross-user isolation ──────────────────────────────────────────────────


def test_other_user_cannot_touch_my_project(client):
    csrf_a = _auth(client, username="alice")
    _new_project(client, csrf_a, pid="p1", name="Alice's")
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_a})
    csrf_b = _auth(client, username="bob")

    for verb, path, body in [
        ("POST", "/api/projects/p1/stages", {"id": "s1", "name": "X"}),
        ("PATCH", "/api/projects/p1/stages/s1", {"name": "X"}),
        ("DELETE", "/api/projects/p1/stages/s1", None),
        ("POST", "/api/projects/p1/stages/s1/blockers", {"id": "b1", "text": "X"}),
        ("POST", "/api/projects/p1/stages/s1/ideas", {"id": "d1", "text": "X"}),
    ]:
        kwargs = {"headers": {"X-CSRF-Token": csrf_b}, "json": body} if body else \
                 {"headers": {"X-CSRF-Token": csrf_b}}
        if verb == "DELETE":
            resp = client.delete(path, **kwargs)
        else:
            resp = client.post(path, **kwargs) if verb == "POST" else client.patch(path, **kwargs)
        assert resp.status_code == 404, f"{verb} {path} should be 404 for cross-user access"
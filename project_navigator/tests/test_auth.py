"""Tests for the auth endpoints and CSRF flow.

Covers:
- Registration validation and duplicate handling
- Login happy path + wrong-password rejection
- Logout
- /api/auth/me when unauthenticated and authenticated
- CSRF token required on mutating endpoints after auth
"""
from __future__ import annotations


# ── Registration ──────────────────────────────────────────────────────────


def test_register_creates_user(client):
    resp = client.post("/api/auth/register", json={
        "username": "alice",
        "password": "secret123",
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["username"] == "alice"
    assert "password_hash" not in body["user"]
    assert "csrf_token" in body
    # Cookie set
    assert "session" in resp.headers.get("Set-Cookie", "")


def test_register_rejects_duplicate_username(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret123"})
    resp = client.post("/api/auth/register", json={"username": "alice", "password": "different456"})
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "duplicate"


def test_register_rejects_short_password(client):
    resp = client.post("/api/auth/register", json={"username": "alice", "password": "abc"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "validation"


def test_register_rejects_bad_username(client):
    for bad in ("a", "a" * 33, "has space", "weird!char"):
        resp = client.post("/api/auth/register", json={"username": bad, "password": "validpw1"})
        assert resp.status_code == 400, f"username {bad!r} should be rejected"


def test_register_rejects_missing_fields(client):
    resp = client.post("/api/auth/register", json={})
    assert resp.status_code == 400


# ── Login ─────────────────────────────────────────────────────────────────


def test_login_success(auth_client):
    client, csrf, user = auth_client
    # Already logged in via register; verify /me reflects the session.
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["user"]["username"] == "tester"


def test_login_with_wrong_password(auth_client):
    client, _, _ = auth_client
    client.post("/api/auth/logout", headers={"X-CSRF-Token": _extract_csrf(client)})
    resp = client.post("/api/auth/login", json={"username": "tester", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "invalid_credentials"


def test_login_with_unknown_user(auth_client):
    client, _, _ = auth_client
    client.post("/api/auth/logout", headers={"X-CSRF-Token": _extract_csrf(client)})
    resp = client.post("/api/auth/login", json={"username": "ghost", "password": "anything1"})
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "invalid_credentials"


def test_login_same_response_for_unknown_user_and_wrong_password(auth_client):
    """Defends against username enumeration: same status + code for both."""
    client, _, _ = auth_client
    client.post("/api/auth/logout", headers={"X-CSRF-Token": _extract_csrf(client)})

    r1 = client.post("/api/auth/login", json={"username": "ghost", "password": "anything1"})
    r2 = client.post("/api/auth/login", json={"username": "tester", "password": "wrong"})
    assert r1.status_code == r2.status_code == 401
    assert r1.get_json() == r2.get_json()


def test_login_requires_fields(auth_client):
    client, _, _ = auth_client
    client.post("/api/auth/logout", headers={"X-CSRF-Token": _extract_csrf(client)})
    for body in ({}, {"username": "x"}, {"password": "x"}):
        resp = client.post("/api/auth/login", json=body)
        assert resp.status_code == 400


# ── Logout ────────────────────────────────────────────────────────────────


def test_logout_clears_session(auth_client):
    client, csrf, _ = auth_client
    resp = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204
    # /me should now be unauthenticated.
    me = client.get("/api/auth/me")
    assert me.status_code == 401


def test_logout_requires_csrf(auth_client):
    client, _, _ = auth_client
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 403


def test_logout_requires_auth(client):
    resp = client.post("/api/auth/logout", headers={"X-CSRF-Token": "anything"})
    assert resp.status_code == 401


# ── /api/auth/me ─────────────────────────────────────────────────────────


def test_me_unauthenticated(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_returns_csrf_token(auth_client):
    client, _, _ = auth_client
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    body = me.get_json()
    assert body["csrf_token"]
    # /me rotates the CSRF; calling again yields a different token.
    me2 = client.get("/api/auth/me")
    assert me2.get_json()["csrf_token"] != body["csrf_token"]


def test_me_with_stale_session_returns_401(client, app, tmp_db_path):
    """A session cookie pointing at a deleted user must be cleared."""
    import sqlite3
    # Register, capture cookie, then drop the user row directly.
    client.post("/api/auth/register", json={"username": "bob", "password": "validpw1"})
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("DELETE FROM user WHERE username = 'bob'")
    conn.commit()
    conn.close()

    me = client.get("/api/auth/me")
    assert me.status_code == 401


# ── CSRF ─────────────────────────────────────────────────────────────────


def test_csrf_required_for_mutating_endpoints(auth_client):
    client, _, _ = auth_client
    # No CSRF header → 403
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 403


def test_csrf_rejects_wrong_token(auth_client):
    client, _, _ = auth_client
    resp = client.post("/api/auth/logout", headers={"X-CSRF-Token": "not-the-real-one"})
    assert resp.status_code == 403


def test_csrf_header_name_case_insensitive(auth_client):
    """HTTP headers are case-insensitive; both spellings should work."""
    client, csrf, _ = auth_client
    resp = client.post("/api/auth/logout", headers={"x-csrf-token": csrf})
    assert resp.status_code == 204


# ── Cookie round-trip (Phase 6 acceptance) ────────────────────────────────


def test_cookie_round_trip_preserves_session(auth_client):
    """After login, follow-up calls in the same client use the cookie."""
    client, _, user = auth_client
    # Subsequent call works without re-authenticating.
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["user"]["id"] == user["id"]


def test_full_auth_flow_register_then_logout_then_login(client):
    # Register → /me works.
    r1 = client.post("/api/auth/register", json={"username": "user1", "password": "pw1234"})
    assert r1.status_code == 200
    # /me rotates the CSRF; use the value from /me for subsequent mutations.
    csrf = client.get("/api/auth/me").get_json()["csrf_token"]

    # Logout → /me fails.
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401

    # Re-login with same credentials.
    r2 = client.post("/api/auth/login", json={"username": "user1", "password": "pw1234"})
    assert r2.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_login_flow_can_create_and_view_project(client):
    # Register, then create a project via the API.
    r = client.post("/api/auth/register", json={"username": "demo", "password": "pw1234"})
    csrf = r.get_json()["csrf_token"]
    p = client.post("/api/projects",
                    json={"id": "p1", "name": "My project"},
                    headers={"X-CSRF-Token": csrf})
    assert p.status_code == 200

    # /me now includes the project (note: /me rotates the token but the body
    # also lists projects from list_projects_for_user).
    me = client.get("/api/auth/me").get_json()
    assert any(proj["id"] == "p1" for proj in me["projects"])


# ── Helpers ───────────────────────────────────────────────────────────────


def _extract_csrf(client) -> str:
    """Read the most recent CSRF token from /api/auth/me."""
    me = client.get("/api/auth/me")
    if me.status_code != 200:
        return ""
    return me.get_json().get("csrf_token", "")
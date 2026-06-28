"""Flask app factory + auth endpoints.

Phase 2 covers /api/auth/*; later phases add /api/projects/* and project-scoped
routes. The factory pattern lets tests build a fresh app per session.
"""
from __future__ import annotations

from typing import Optional, Type

from flask import Flask, g, jsonify, request

from . import models
from .auth import (
    CSRF_HEADER,
    SESSION_CSRF_KEY,
    SESSION_USER_KEY,
    current_user,
    issue_csrf,
    login_required,
    login_user,
    logout_user,
    require_csrf,
)
from .database import apply_migrations, connect


def create_app(config_class: Optional[Type] = None) -> Flask:
    """Build and return a Flask app.

    - config_class: defaults to config.Config; tests pass TestConfig or a custom
      subclass.
    """
    # Late import to keep config importable without Flask at the top level.
    from config import Config

    app = Flask(__name__, static_folder=str((config_class or Config).FRONTEND_DIR), static_url_path="/static")
    app.config.from_object(config_class or Config)
    app.config["DB_PATH"] = app.config["DB_PATH"]

    # Database lifecycle: one connection per request, stored on flask.g.
    @app.before_request
    def _open_db() -> None:
        g._pnav_db = connect(app.config["DB_PATH"])

    @app.teardown_appcontext
    def _close_db(_exc) -> None:
        db = g.pop("_pnav_db", None)
        if db is not None:
            db.close()

    # Apply pending migrations on first request. In tests, conftest.py applies
    # them directly against a temp DB; the boot-time call here is a safety net
    # for `flask run`.
    _bootstrapped = {"done": False}

    @app.before_request
    def _maybe_apply_migrations() -> None:
        if _bootstrapped["done"] or app.config.get("TESTING"):
            return
        _bootstrapped["done"] = True
        # Use the same connection that subsequent requests will use.
        apply_migrations(g._pnav_db)

    # ── Auth endpoints ──────────────────────────────────────────────────

    @app.post("/api/auth/register")
    def register():
        body = request.get_json(silent=True) or {}
        try:
            user = models.create_user(
                g._pnav_db,
                body.get("username", ""),
                body.get("password", ""),
            )
        except models.DuplicateError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 409
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        # Auto-login on register so the UX matches the API design.
        csrf = login_user(user["id"])
        return jsonify({
            "user": user,
            "csrf_token": csrf,
        }), 200

    @app.post("/api/auth/login")
    def login():
        body = request.get_json(silent=True) or {}
        try:
            username = models.validate_nonempty("username", body.get("username", ""))
            password = body.get("password", "")
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        if not isinstance(password, str) or not password:
            return jsonify({"error": "password required", "code": "validation"}), 400

        user = models.verify_credentials(g._pnav_db, username, password)
        if user is None:
            # Single error code on purpose — do not leak which field was wrong.
            return jsonify({"error": "invalid credentials", "code": "invalid_credentials"}), 401

        csrf = login_user(user["id"])
        return jsonify({
            "user": user,
            "csrf_token": csrf,
        }), 200

    @app.post("/api/auth/logout")
    @login_required
    @require_csrf
    def logout():
        logout_user()
        return ("", 204)

    @app.get("/api/auth/me")
    def me():
        user_id = _session_user_id()
        if user_id is None:
            return jsonify({"error": "unauthenticated", "code": "unauthenticated"}), 401
        user = models.get_user_by_id(g._pnav_db, user_id)
        if user is None:
            return jsonify({"error": "unauthenticated", "code": "unauthenticated"}), 401

        # Refresh CSRF token on every /me call so the frontend always has a
        # current one. Cheap and avoids token-expiry bugs.
        csrf = issue_csrf()
        # Also include the active project + project list so the frontend can
        # hydrate the sidebar without a follow-up call.
        projects = models.list_projects_for_user(g._pnav_db, user["id"])
        return jsonify({
            "user": user,
            "csrf_token": csrf,
            "active_project_id": user.get("active_project_id"),
            "projects": projects,
        }), 200

    # ── Project endpoints ────────────────────────────────────────────────

    @app.get("/api/projects")
    @login_required
    def list_projects():
        user = current_user()
        return jsonify({
            "projects": models.list_projects_for_user(g._pnav_db, user["id"]),
            "active_project_id": user.get("active_project_id"),
        }), 200

    @app.post("/api/projects")
    @login_required
    @require_csrf
    def create_project_route():
        user = current_user()
        body = request.get_json(silent=True) or {}
        try:
            project = models.create_project(
                g._pnav_db,
                user_id=user["id"],
                project_id=body.get("id", ""),
                name=body.get("name", ""),
                description=body.get("description", ""),
                position=body.get("position"),
            )
        except models.DuplicateError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 409
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        return jsonify(project), 200

    @app.patch("/api/projects/<project_id>")
    @login_required
    @require_csrf
    def patch_project(project_id: str):
        user = current_user()
        body = request.get_json(silent=True) or {}
        try:
            project = models.update_project(
                g._pnav_db,
                project_id,
                user["id"],
                name=body.get("name"),
                description=body.get("description"),
                position=body.get("position"),
            )
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        if project is None:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        return jsonify(project), 200

    @app.delete("/api/projects/<project_id>")
    @login_required
    @require_csrf
    def delete_project(project_id: str):
        user = current_user()
        deleted = models.delete_project(g._pnav_db, project_id, user["id"])
        if not deleted:
            return jsonify({"error": "not found", "code": "not_found"}), 404

        # If the deleted project was active, clear or roll over to the next project.
        if user.get("active_project_id") == project_id:
            remaining = models.list_projects_for_user(g._pnav_db, user["id"])
            next_active = remaining[0]["id"] if remaining else None
            models.set_active_project(g._pnav_db, user["id"], next_active)
        return ("", 204)

    @app.put("/api/projects/<project_id>/active")
    @login_required
    @require_csrf
    def set_active_project_route(project_id: str):
        user = current_user()
        # Verify the project is owned by the user before flipping the flag.
        project = models.get_project_for_user(g._pnav_db, project_id, user["id"])
        if project is None:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        models.set_active_project(g._pnav_db, user["id"], project_id)
        return ("", 204)

    # ── Project-scoped endpoints ────────────────────────────────────────
    #
    # Every handler resolves project_id from the URL and confirms ownership
    # via get_project_for_user before touching stages/blockers/etc. The same
    # helper also covers stage_id → project_id and blocker_id → project_id
    # chains by walking the foreign keys.

    def _resolve_project(project_id: str):
        """Return the project dict if owned by the current user, else None."""
        return models.get_project_for_user(g._pnav_db, project_id, current_user()["id"])

    def _resolve_stage(stage_id: str):
        """Return (project, stage) or (None, None) if either link is broken."""
        stage = models.get_stage(g._pnav_db, stage_id)
        if stage is None:
            return None, None
        project = _resolve_project(stage["project_id"])
        if project is None:
            return None, None
        return project, stage

    def _resolve_blocker(blocker_id: str):
        blocker = models.get_blocker(g._pnav_db, blocker_id)
        if blocker is None:
            return None, None
        project, stage = _resolve_stage(blocker["stage_id"])
        if project is None:
            return None, None
        return project, stage, blocker

    def _resolve_sub_item(sub_id: str):
        item = models.get_sub_item(g._pnav_db, sub_id)
        if item is None:
            return None
        project, stage, blocker = _resolve_blocker(item["blocker_id"])
        if project is None:
            return None
        return project, stage, blocker, item

    def _resolve_idea(idea_id: str):
        idea = models.get_idea(g._pnav_db, idea_id)
        if idea is None:
            return None
        project = _resolve_project(idea["project_id"])
        if project is None:
            return None
        return project, idea

    @app.get("/api/projects/<project_id>/snapshot")
    @login_required
    def snapshot(project_id: str):
        project = _resolve_project(project_id)
        if project is None:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        snap = models.build_snapshot(g._pnav_db, project_id)
        return jsonify(snap), 200

    @app.put("/api/projects/<project_id>/goal")
    @login_required
    @require_csrf
    def put_goal(project_id: str):
        if _resolve_project(project_id) is None:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            goal = models.set_goal(g._pnav_db, project_id, body.get("text", ""))
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        return jsonify(goal), 200

    # ── Stages ──────────────────────────────────────────────────────────

    @app.post("/api/projects/<project_id>/stages")
    @login_required
    @require_csrf
    def create_stage_route(project_id: str):
        if _resolve_project(project_id) is None:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            stage = models.create_stage(
                g._pnav_db,
                project_id=project_id,
                stage_id=body.get("id", ""),
                name=body.get("name", ""),
                status=body.get("status", "todo"),
                position=body.get("position"),
            )
        except models.DuplicateError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 409
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        return jsonify(stage), 200

    @app.patch("/api/projects/<project_id>/stages/<stage_id>")
    @login_required
    @require_csrf
    def patch_stage(project_id: str, stage_id: str):
        project, stage = _resolve_stage(stage_id)
        if project is None or project["id"] != project_id:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            stage = models.update_stage(
                g._pnav_db,
                stage_id,
                name=body.get("name"),
                status=body.get("status"),
                position=body.get("position"),
            )
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        if stage is None:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        return jsonify(stage), 200

    @app.delete("/api/projects/<project_id>/stages/<stage_id>")
    @login_required
    @require_csrf
    def delete_stage_route(project_id: str, stage_id: str):
        project, stage = _resolve_stage(stage_id)
        if project is None or project["id"] != project_id:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        models.delete_stage(g._pnav_db, stage_id)
        return ("", 204)

    # ── Blockers ────────────────────────────────────────────────────────

    @app.post("/api/projects/<project_id>/stages/<stage_id>/blockers")
    @login_required
    @require_csrf
    def create_blocker_route(project_id: str, stage_id: str):
        project, stage = _resolve_stage(stage_id)
        if project is None or project["id"] != project_id:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            blocker = models.create_blocker(
                g._pnav_db,
                stage_id=stage_id,
                blocker_id=body.get("id", ""),
                text=body.get("text", ""),
                status=body.get("status", "todo"),
                deep=bool(body.get("deep", False)),
                position=body.get("position"),
            )
        except models.DuplicateError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 409
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        return jsonify(blocker), 200

    @app.patch("/api/projects/<project_id>/blockers/<blocker_id>")
    @login_required
    @require_csrf
    def patch_blocker(project_id: str, blocker_id: str):
        resolved = _resolve_blocker(blocker_id)
        if resolved[0] is None or resolved[0]["id"] != project_id:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            blocker = models.update_blocker(
                g._pnav_db,
                blocker_id,
                text=body.get("text"),
                status=body.get("status"),
                deep=body.get("deep"),
                position=body.get("position"),
            )
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        if blocker is None:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        return jsonify(blocker), 200

    @app.delete("/api/projects/<project_id>/blockers/<blocker_id>")
    @login_required
    @require_csrf
    def delete_blocker_route(project_id: str, blocker_id: str):
        resolved = _resolve_blocker(blocker_id)
        if resolved[0] is None or resolved[0]["id"] != project_id:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        models.delete_blocker(g._pnav_db, blocker_id)
        return ("", 204)

    # ── Sub-items ───────────────────────────────────────────────────────

    @app.post("/api/projects/<project_id>/blockers/<blocker_id>/items")
    @login_required
    @require_csrf
    def create_sub_item_route(project_id: str, blocker_id: str):
        resolved = _resolve_blocker(blocker_id)
        if resolved[0] is None or resolved[0]["id"] != project_id:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            item = models.create_sub_item(
                g._pnav_db,
                blocker_id=blocker_id,
                sub_id=body.get("id", ""),
                text=body.get("text", ""),
                status=body.get("status", "todo"),
                deep=bool(body.get("deep", False)),
                position=body.get("position"),
            )
        except models.DuplicateError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 409
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        return jsonify(item), 200

    @app.patch("/api/projects/<project_id>/subitems/<sub_id>")
    @login_required
    @require_csrf
    def patch_sub_item(project_id: str, sub_id: str):
        resolved = _resolve_sub_item(sub_id)
        if resolved is None or resolved[0]["id"] != project_id:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            item = models.update_sub_item(
                g._pnav_db,
                sub_id,
                text=body.get("text"),
                status=body.get("status"),
                deep=body.get("deep"),
                position=body.get("position"),
            )
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        if item is None:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        return jsonify(item), 200

    @app.delete("/api/projects/<project_id>/subitems/<sub_id>")
    @login_required
    @require_csrf
    def delete_sub_item_route(project_id: str, sub_id: str):
        resolved = _resolve_sub_item(sub_id)
        if resolved is None or resolved[0]["id"] != project_id:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        models.delete_sub_item(g._pnav_db, sub_id)
        return ("", 204)

    # ── Ideas ───────────────────────────────────────────────────────────

    @app.post("/api/projects/<project_id>/stages/<stage_id>/ideas")
    @login_required
    @require_csrf
    def create_idea_route(project_id: str, stage_id: str):
        project, stage = _resolve_stage(stage_id)
        if project is None or project["id"] != project_id:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            idea = models.create_idea(
                g._pnav_db,
                project_id=project_id,
                stage_id=stage_id,
                idea_id=body.get("id", ""),
                text=body.get("text", ""),
                position=body.get("position"),
            )
        except models.DuplicateError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 409
        except models.ValidationError as exc:
            return jsonify({"error": exc.message, "code": exc.code}), 400
        return jsonify(idea), 200

    @app.delete("/api/projects/<project_id>/ideas/<idea_id>")
    @login_required
    @require_csrf
    def delete_idea_route(project_id: str, idea_id: str):
        resolved = _resolve_idea(idea_id)
        if resolved is None or resolved[0]["id"] != project_id:
            return jsonify({"error": "not found", "code": "not_found"}), 404
        models.delete_idea(g._pnav_db, idea_id)
        return ("", 204)

    # ── Error handlers ──────────────────────────────────────────────────

    @app.errorhandler(404)
    def _not_found(_exc):
        return jsonify({"error": "not found", "code": "not_found"}), 404

    @app.errorhandler(405)
    def _bad_method(_exc):
        return jsonify({"error": "method not allowed", "code": "not_found"}), 405

    @app.errorhandler(500)
    def _server_error(_exc):
        # Don't leak tracebacks to the client.
        return jsonify({"error": "internal error", "code": "internal"}), 500

    # ── Frontend static files ───────────────────────────────────────────
    # Phase 5: serve the refactored frontend from /static. Phase 6 will add
    # an auth-gated route at / that redirects to /login.html when the user
    # is unauthenticated.

    frontend_dir = app.config["FRONTEND_DIR"]
    if frontend_dir.exists():
        @app.get("/")
        def index():
            # Phase 6: gate the app shell on an authenticated session.
            # The frontend also calls /api/auth/me which 401-redirects, but
            # gating here avoids a brief flash of the unauthenticated shell.
            if not _session_user_id():
                return app.send_static_file("login.html")
            return app.send_static_file("index.html")

        @app.get("/login.html")
        def login_page():
            # If already logged in, send the user straight to the app.
            if _session_user_id():
                return app.send_static_file("index.html")
            return app.send_static_file("login.html")

    return app


def _session_user_id() -> Optional[int]:
    from flask import session
    value = session.get(SESSION_USER_KEY)
    return int(value) if value is not None else None


__all__ = ["create_app"]
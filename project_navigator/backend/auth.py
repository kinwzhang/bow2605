"""Session-cookie authentication helpers and the @login_required decorator.

Design summary (see plan_and_design/02_api_design.md §7):
- Flask's signed session cookie holds user_id and csrf token.
- On login we rotate the CSRF token; on logout we clear it.
- Every mutating request must include an X-CSRF-Token header matching the
  session-stored value. CSRF checks live in `require_csrf` and are layered on
  top of `login_required` for POST/PATCH/PUT/DELETE routes.
"""
from __future__ import annotations

import secrets
from functools import wraps
from typing import Callable

from flask import current_app, g, jsonify, request, session

from . import models


SESSION_USER_KEY = "_pnav_user_id"
SESSION_CSRF_KEY = "_pnav_csrf"
CSRF_HEADER = "X-CSRF-Token"


# ── Token management ──────────────────────────────────────────────────────


def issue_csrf() -> str:
    """Generate a new CSRF token, store it in the session, and return it."""
    token = secrets.token_urlsafe(24)
    session[SESSION_CSRF_KEY] = token
    return token


def current_csrf() -> str | None:
    return session.get(SESSION_CSRF_KEY)


# ── Decorators ────────────────────────────────────────────────────────────


def login_required(view: Callable) -> Callable:
    """Reject the request unless a valid session is present."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        user_id = session.get(SESSION_USER_KEY)
        if user_id is None:
            return jsonify({"error": "authentication required", "code": "unauthenticated"}), 401
        # Cache the user row on flask.g for the duration of the request.
        user = models.get_user_by_id(_db(), int(user_id))
        if user is None:
            # Stale session pointing at a deleted user — clear it.
            session.clear()
            return jsonify({"error": "authentication required", "code": "unauthenticated"}), 401
        g.current_user = user
        return view(*args, **kwargs)

    return wrapper


def require_csrf(view: Callable) -> Callable:
    """Reject mutating requests without a matching X-CSRF-Token header.

    Must be combined with @login_required (CSRF check happens after auth).
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = session.get(SESSION_CSRF_KEY)
        if not expected:
            # No CSRF token issued — happens if user logged in via a code path
            # that forgot to issue one. Generate one now so the next request works.
            expected = issue_csrf()
        presented = request.headers.get(CSRF_HEADER, "")
        if not presented or presented != expected:
            return jsonify({"error": "CSRF token missing or invalid", "code": "forbidden"}), 403
        return view(*args, **kwargs)

    return wrapper


# ── Helpers used by route handlers ────────────────────────────────────────


def _db():
    """Return the request-scoped database connection.

    The connection is created and stored on flask.g in app.before_request;
    that indirection keeps tests and request handling symmetric.
    """
    return g._pnav_db


def login_user(user_id: int) -> str:
    """Mark the session as logged in for `user_id`. Returns the issued CSRF token."""
    session.clear()
    session[SESSION_USER_KEY] = user_id
    session.permanent = True
    return issue_csrf()


def logout_user() -> None:
    session.clear()


def current_user() -> dict:
    """Return the current user dict (set by @login_required)."""
    return g.current_user


__all__ = [
    "SESSION_USER_KEY",
    "SESSION_CSRF_KEY",
    "CSRF_HEADER",
    "issue_csrf",
    "current_csrf",
    "login_required",
    "require_csrf",
    "login_user",
    "logout_user",
    "current_user",
]
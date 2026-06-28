# 02 — API Design

## 1. Overview

REST/JSON over HTTP. All endpoints live under `/api/`. Mutations require an authenticated session. Project-scoped routes additionally verify that the resolved project belongs to the current user.

## 2. Conventions

### 2.1 Content type

- Request: `application/json` for any body.
- Response: `application/json; charset=utf-8` always.

### 2.2 Authentication

- Session cookie (`session`) issued by Flask on login.
- `Set-Cookie: session=...; HttpOnly; SameSite=Lax; Path=/`. `Secure` flag is added when `FLASK_ENV` is `production`.
- The frontend's `fetch()` calls use `credentials: 'same-origin'` so the cookie is included.

### 2.3 Status codes

| Code | Meaning in this API |
|------|---------------------|
| `200 OK` | Success with a body |
| `204 No Content` | Success, no body (used for logout, delete) |
| `400 Bad Request` | Validation failure (unknown status, missing field) |
| `401 Unauthorized` | No session, or invalid credentials on login |
| `403 Forbidden` | Session valid but resource belongs to a different user |
| `404 Not Found` | Resource ID does not exist (or is scoped out by ownership) |
| `409 Conflict` | Duplicate username, ID collision on insert |
| `500 Internal Server Error` | Unhandled exception (logged with traceback) |

### 2.4 Error body shape

```json
{ "error": "human-readable message", "code": "machine_code" }
```

`code` values used: `invalid_credentials`, `unauthenticated`, `forbidden`, `not_found`, `validation`, `duplicate`, `collision`.

### 2.5 Timestamps

Server returns ISO-8601 UTC strings (`2026-06-28T12:34:56Z`). Clients render them as-is for the prototype.

## 3. Auth Endpoints

### `POST /api/auth/register`

Create a user.

Request:
```json
{ "username": "kin", "password": "hunter2" }
```
Response `200`:
```json
{ "id": 7, "username": "kin" }
```
Errors: `409 duplicate`, `400 validation` (missing field, short password, bad username).

### `POST /api/auth/login`

Request:
```json
{ "username": "kin", "password": "hunter2" }
```
Response `200`:
```json
{ "id": 7, "username": "kin", "active_project_id": "abc123def" }
```
Errors: `401 invalid_credentials`. (Single error code for both unknown user and wrong password — avoids username enumeration.)

The session cookie is set in the response headers.

### `POST /api/auth/logout`

No body. Response `204`. Cookie cleared.

### `GET /api/auth/me`

Response `200`:
```json
{
  "user": { "id": 7, "username": "kin" },
  "active_project_id": "abc123def",
  "projects": [
    { "id": "abc123def", "name": "Bow2605", "description": "", "position": 0 },
    { "id": "ghi789jkl", "name": "Side project", "description": "", "position": 1 }
  ]
}
```
Used on app boot to hydrate the sidebar without a separate `GET /api/projects` round-trip.

Errors: `401 unauthenticated`.

## 4. Project Endpoints

All require an authenticated session.

### `GET /api/projects`

List the current user's projects ordered by `position ASC, created_at ASC`.

Response `200`:
```json
{
  "projects": [
    { "id": "abc123def", "name": "Bow2605", "description": "", "position": 0, "created_at": "..." },
    { "id": "ghi789jkl", "name": "Side project", "description": "", "position": 1, "created_at": "..." }
  ],
  "active_project_id": "abc123def"
}
```

### `POST /api/projects`

Create. Request:
```json
{ "id": "clientuid123", "name": "Bow2605", "description": "Optional", "position": 0 }
```
`id` is client-generated (matches `uid()`). `position` defaults to `max(position) + 1` if omitted.

Response `200`:
```json
{ "id": "clientuid123", "name": "Bow2605", "description": "Optional", "position": 3, "created_at": "..." }
```
Errors: `409 collision` (duplicate id), `400 validation` (empty name).

### `PATCH /api/projects/<id>`

Update name and/or description.

Request:
```json
{ "name": "Bow 2605", "description": "v2 spec" }
```
Response `200`: the updated project. Errors: `403 forbidden`, `404 not_found`, `400 validation`.

### `DELETE /api/projects/<id>`

Cascade-deletes stages, blockers, sub-items, ideas, goal. Response `204`. Errors: `403`, `404`.

If the deleted project was the user's `active_project_id`, the server clears the active flag (or sets it to the next-most-recent project, TBD in Phase 3).

### `PUT /api/projects/<id>/active`

Set the user's active project. Idempotent. Response `204`. Errors: `403`, `404`.

## 5. Project-Scoped Endpoints (Stages / Blockers / Items / Ideas)

All require authentication. Every route resolves `project_id` from the URL and checks `project.user_id == current_user.id` before doing anything.

Snapshot is the primary read; per-entity endpoints are for mutations only.

### `GET /api/projects/<pid>/snapshot`

Full tree for one project, used on project switch and on initial load of `index.html`.

Response `200`:
```json
{
  "project":  { "id": "abc123def", "name": "Bow2605", "description": "" },
  "goal":     { "text": "Ship the refactor" },
  "stages": [
    {
      "id": "stg01", "name": "Plan", "status": "active", "position": 0,
      "blockers": [
        { "id": "blk01", "text": "What about auth?", "status": "todo", "deep": 0, "position": 0,
          "items": [
            { "id": "sub01", "text": "JWT vs session", "status": "todo", "deep": 0, "position": 0 }
          ]
        }
      ],
      "ideas": [
        { "id": "idea01", "text": "Try cookie-first", "position": 0 }
      ]
    }
  ]
}
```
`blockers[].status` and `items[].status` use the full 8-value set; `stages[].status` uses the 4-value set.

### Goal

`PUT /api/projects/<pid>/goal` — body `{ "text": "..." }` → `200 { "text": "..." }`.

### Stages

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST`   | `/api/projects/<pid>/stages` | `{ id, name, status?, position? }` | `200` stage |
| `PATCH`  | `/api/projects/<pid>/stages/<sid>` | `{ name?, status?, position? }` | `200` stage |
| `DELETE` | `/api/projects/<pid>/stages/<sid>` | — | `204` |

### Blockers

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST`   | `/api/projects/<pid>/stages/<sid>/blockers` | `{ id, text, status?, deep?, position? }` | `200` blocker |
| `PATCH`  | `/api/projects/<pid>/blockers/<bid>` | `{ text?, status?, deep?, position? }` | `200` blocker |
| `DELETE` | `/api/projects/<pid>/blockers/<bid>` | — | `204` |

`PATCH` on `deep=true` server-side forces `status='park'`; `deep=false` forces `status='todo'`. Status `'solve'` implies `deep=false, status='todo'` (matches frontend behavior in `applyStatus`).

### Sub-items

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST`   | `/api/projects/<pid>/blockers/<bid>/items` | `{ id, text, status?, deep?, position? }` | `200` sub-item |
| `PATCH`  | `/api/projects/<pid>/subitems/<iid>` | `{ text?, status?, deep?, position? }` | `200` sub-item |
| `DELETE` | `/api/projects/<pid>/subitems/<iid>` | — | `204` |

(Sub-item `iid` is unique enough on its own; the path is short for ergonomics. Authorization still resolves through the parent blocker → stage → project chain.)

### Ideas

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST`   | `/api/projects/<pid>/stages/<sid>/ideas` | `{ id, text, position? }` | `200` idea |
| `DELETE` | `/api/projects/<pid>/ideas/<iid>` | — | `204` |

`PATCH` is not exposed for ideas in the prototype (they are text-only and immutable to keep the API surface small).

## 6. Authorization Helper

Every project-scoped handler goes through one decorator chain:

```python
@bp.route("/api/projects/<pid>/...")
@login_required
def handler(pid, ...):
    project = models.get_project_for_user(pid, current_user.id)
    if not project:
        abort(404)  # do not distinguish "not yours" from "doesn't exist"
    ...
```

Returning `404` for both "not yours" and "doesn't exist" avoids resource enumeration across users.

## 7. CSRF

For the prototype we use a **double-submit token**:

- On `GET /api/auth/me`, the server also issues a `csrf_token` in the JSON body. The frontend stores it in memory (not localStorage).
- Every mutating request (`POST`, `PATCH`, `PUT`, `DELETE`) must include `X-CSRF-Token: <token>`.
- The server compares the header against the value in `flask.session['csrf']`; mismatch → `403`.
- The token rotates on login and on logout.

This is simpler than wiring Flask-WTF for the prototype and meets the "future-scalable" requirement (it can be replaced by SameSite=Strict + Origin checks later).

## 8. Session Lifecycle

```
GET /            →  if no session: redirect to /login.html
                  else: serve /index.html

GET /api/auth/me →  200 with user, active_project, projects list
                  401: redirect to /login.html

POST /api/auth/login  → 200, Set-Cookie session=..., Set-Cookie csrf_hint
POST /api/auth/logout → 204, Clear-Cookie session

Session expires after 30 days of inactivity (configurable).
```

## 9. Sample Walkthrough — Switching Projects

1. User clicks project `ghi789jkl` in the sidebar.
2. Frontend calls `PUT /api/projects/ghi789jkl/active` → `204`.
3. Frontend calls `GET /api/projects/ghi789jkl/snapshot` → full tree.
4. Frontend updates header (`Project Navigator ▸ Side project`), clears `S`, hydrates from snapshot, renders.

No full page reload. Optimistic UI: the sidebar selection updates immediately; the main pane shows a "Loading…" hint until the snapshot arrives.

## 10. Sample Walkthrough — Creating a Stage

1. User types "Spec the v2 API" → Enter.
2. Frontend calls `uid()`, optimistically pushes into `S.stages`, re-renders.
3. Frontend calls `POST /api/projects/<pid>/stages` with `{ id, name }`.
4. On `409 collision`, frontend regenerates `uid()` and retries once. On `400`, frontend rolls back the optimistic insert and shows an error.
5. On any other failure, the next `snapshot` load (or a manual retry button) reconciles.
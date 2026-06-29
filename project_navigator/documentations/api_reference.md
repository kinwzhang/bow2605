# API Reference

REST/JSON API served by the Flask backend. All endpoints under `/api/`. The
session cookie is set on register/login; subsequent calls must include it via
the browser's cookie jar (`credentials: 'same-origin'` in fetch).

## Conventions

- Request body: `application/json`.
- Response body: `application/json` on success; `{"error":"…","code":"…"}` on
  failure.
- Mutating endpoints (`POST`, `PATCH`, `PUT`, `DELETE`) require
  `X-CSRF-Token: <token>` matching the value stored in the session. The token
  is returned by every `/api/auth/me` response (and is rotated on each call).
- `401 unauthenticated` means no session. The frontend redirects to
  `/login.html` automatically.
- `404 not_found` covers both "does not exist" and "exists but owned by a
  different user" — by design, to avoid resource enumeration.

## Auth

### `POST /api/auth/register`

Create a user (and sign them in).

```json
// Request
{ "username": "alice", "password": "validpw1" }

// 200 Response
{ "user": { "id": 2, "username": "alice", "active_project_id": null, "created_at": "..." },
  "csrf_token": "..." }

// 409 duplicate (username already exists)
// 400 validation (missing field, short password, bad username)
```

### `POST /api/auth/login`

Sign in.

```json
// Request
{ "username": "alice", "password": "validpw1" }

// 200 Response
{ "user": { ... }, "csrf_token": "..." }

// 401 invalid_credentials
// 400 validation
```

The session cookie is set in the response headers.

### `POST /api/auth/logout`

Sign out. Requires `X-CSRF-Token`. Returns `204`.

### `GET /api/auth/me`

Return the current session. CSRF token is rotated on every call.

```json
// 200 Response
{ "user": { "id": 2, "username": "alice", "active_project_id": "abc", "created_at": "..." },
  "csrf_token": "...",
  "active_project_id": "abc",
  "projects": [ { "id": "abc", "name": "Bow2605", "description": "", "position": 0, "created_at": "..." } ] }

// 401 unauthenticated
```

## Projects

### `GET /api/projects`

List the current user's projects.

```json
// 200 Response
{ "projects": [ ... ], "active_project_id": "abc" }
```

### `POST /api/projects`

Create a project. `id` is client-generated.

```json
// Request
{ "id": "clientuid", "name": "Bow2605", "description": "Optional", "position": 0 }

// 200 Response — full project row
// 400 validation (empty name)
// 409 collision (id already exists)
```

### `PATCH /api/projects/<id>`

Update name / description / position. Returns the updated project, or `404`.

### `DELETE /api/projects/<id>`

Cascade-delete the project. Returns `204`, or `404`. If the deleted project
was the active one, `active_project_id` rolls over to the next-most-recent
project, or clears if none remain.

### `PUT /api/projects/<id>/active`

Set the active project. Idempotent. Returns `204`, or `404`.

## Project-scoped tree

All endpoints below scope under `/api/projects/<pid>/...` and verify that the
project is owned by the current user.

### `GET /api/projects/<pid>/snapshot`

Return the full tree for one project in one round-trip.

```json
// 200 Response
{
  "project":  { "id": "abc", "name": "Bow2605", "description": "" },
  "goal":     { "text": "Ship the refactor" },
  "stages": [
    {
      "id": "stg01", "name": "Plan", "status": "active", "position": 0,
      "blockers": [
        { "id": "blk01", "text": "Auth?", "status": "todo", "deep": false, "position": 0,
          "items": [
            { "id": "sub01", "text": "JWT vs session", "status": "todo", "deep": false, "position": 0 }
          ]
        }
      ],
      "ideas": [ { "id": "idea01", "text": "Try cookies", "position": 0 } ]
    }
  ]
}
```

### Goal

`PUT /api/projects/<pid>/goal` — body `{ "text": "..." }` → `200 { "text": "..." }` or `400`.

### Stages

| Method   | Path                                                | Body                                          |
|----------|-----------------------------------------------------|-----------------------------------------------|
| `POST`   | `/api/projects/<pid>/stages`                        | `{ id, name, status?, position? }`            |
| `PATCH`  | `/api/projects/<pid>/stages/<sid>`                  | `{ name?, status?, position? }`               |
| `DELETE` | `/api/projects/<pid>/stages/<sid>`                  | —                                             |

#### Stage status is auto-derived

Once a stage has any blockers or sub-items, its `status` field is
**auto-derived** from the rollup of its items, with **priority order**
(first match wins):

`todo` > `active` > `blocked` > `review` > `park` > (all `done`) > `nice`

| Priority | Condition                                       | Stage status |
|---------:|-------------------------------------------------|--------------|
| 1 (top)  | Any item is todo                                  | `todo`       |
| 2        | Any item is active                                | `active`     |
| 3        | Any item is blocked                              | `blocked`    |
| 4        | Any item is review                                | `review`     |
| 5        | Any item is park — display label: Parked         | `park`       |
| 6        | All items are done                                | `done`       |
| 7        | Any item is nice — display label: Nice to have   | `nice`       |
| (fallback) | All items are solve (neutral)                   | `active`     |

`todo` wins because if any blocker or sub-item has not started, the
stage as a whole is still in planning — even if other items are deep
into `active` or `done`.

Items in `solve` are **neutral** — the deep-coupling rule converts them
to `todo` on patch, so an "all solve" state in the DB becomes "all todo"
in practice. The fallback only triggers for synthetic states the
backend cannot currently produce.

The seven stage statuses are `todo`, `active`, `blocked`, `done`, `park`,
`review`, `nice` (see `STAGE_STATUSES` in `backend/database.py`).

`PATCH /api/projects/<pid>/stages/<sid>` with `status: ...` returns
`400 validation` if the stage has any items. `name` and `position` can
still be changed freely.

The frontend mirrors the same rule for optimistic UI: the header badge
and the footer status badge both update instantly after every blocker /
sub-item mutation, without a server round-trip.

### Blockers

| Method   | Path                                                       | Body                                          |
|----------|------------------------------------------------------------|-----------------------------------------------|
| `POST`   | `/api/projects/<pid>/stages/<sid>/blockers`                | `{ id, text, status?, deep?, position? }`     |
| `PATCH`  | `/api/projects/<pid>/blockers/<bid>`                       | `{ text?, status?, deep?, position? }`        |
| `DELETE` | `/api/projects/<pid>/blockers/<bid>`                       | —                                             |

Blocker status values: `todo`, `active`, `blocked`, `done`, `park`, `review`, `nice`, `solve`.
Setting `deep=true` server-side forces `status='park'`; setting `status='solve'` forces `deep=false, status='todo'`.

### Sub-items

| Method   | Path                                                       | Body                                          |
|----------|------------------------------------------------------------|-----------------------------------------------|
| `POST`   | `/api/projects/<pid>/blockers/<bid>/items`                 | `{ id, text, status?, deep?, position? }`     |
| `PATCH`  | `/api/projects/<pid>/subitems/<iid>`                       | `{ text?, status?, deep?, position? }`        |
| `DELETE` | `/api/projects/<pid>/subitems/<iid>`                       | —                                             |

### Ideas

| Method   | Path                                                       | Body                              |
|----------|------------------------------------------------------------|-----------------------------------|
| `POST`   | `/api/projects/<pid>/stages/<sid>/ideas`                   | `{ id, text, position? }`         |
| `DELETE` | `/api/projects/<pid>/ideas/<iid>`                          | —                                 |

Ideas have no status; `PATCH` is not exposed.

## Error codes

| Status | code                  | Meaning                                          |
|-------:|-----------------------|--------------------------------------------------|
| 400    | `validation`          | Invalid input — missing field or bad status     |
| 401    | `unauthenticated`     | No session                                       |
| 401    | `invalid_credentials` | Wrong username or password at login             |
| 403    | `forbidden`           | CSRF token missing or invalid                    |
| 404    | `not_found`           | Resource missing or owned by another user       |
| 409    | `duplicate`           | Username already exists at register             |
| 409    | `collision`           | Client-generated id collision                   |
| 500    | `internal`            | Unhandled exception — server logged a traceback |

# 04 — Roadmap

Nine phases. Each ends in a runnable, testable state — after every phase, `flask run` plus a browser tab demonstrates the new capability. Acceptance criteria are listed for each phase; all are checked before moving to the next.

---

## Phase 1 — Schema & Migrations

**Goal**: Apply `002_users_projects.sql` to both a fresh DB and a DB pre-populated by `001_init.sql`.

**Deliverables**
- `backend/migrations/001_init.sql` — copy from `ANALYSIS.md` §6.2.
- `backend/migrations/002_users_projects.sql` — DDL per `01_data_model.md` §6.4.
- `backend/database.py` — connection helper, `PRAGMA` setup, migration runner.
- `scripts/init_db.py` — CLI: `python scripts/init_db.py [--db PATH]`.

**Acceptance criteria**
- [ ] Running `init_db.py` against a fresh path creates `project_navigator.db` with `schema_migrations` recording versions 1 and 2.
- [ ] Running `init_db.py --db existing.db` (where `existing.db` was populated by `001`) backfills a `legacy` user and a single project, drops the `goal` CHECK constraint, and leaves no orphaned rows.
- [ ] `PRAGMA foreign_keys=ON` is set on every connection.
- [ ] Re-running `init_db.py` is a no-op (migrations are recorded).

**Verification**
```bash
sqlite3 project_navigator.db "SELECT version FROM schema_migrations;"
# 1
# 2
sqlite3 project_navigator.db ".schema project"
```

---

## Phase 2 — Auth Backend

**Goal**: Users can register, log in, log out. Sessions are cookie-based. CSRF token issued.

**Deliverables**
- `backend/app.py` — Flask app factory.
- `backend/auth.py` — `login_required`, `issue_csrf`, helpers.
- `backend/models.py` — `create_user`, `get_user_by_username`, `verify_password`.
- `config.py` — `SECRET_KEY`, `DB_PATH`, `SESSION_DAYS`.
- `pyproject.toml` — Flask + Werkzeug + pytest pinned.

**Endpoints**
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET  /api/auth/me`

**Acceptance criteria**
- [ ] `register` rejects duplicate usernames with `409`.
- [ ] `login` returns `401` for unknown user or wrong password with the same error code.
- [ ] `login` sets a `session` cookie (HttpOnly, SameSite=Lax) and includes `csrf_token` in the JSON body.
- [ ] `me` returns `200` with `user` payload when authenticated, `401` otherwise.
- [ ] `logout` returns `204` and clears the cookie.
- [ ] Mutating endpoints reject requests missing `X-CSRF-Token` with `403`.

**Verification**
- `tests/test_auth.py` covers all five error paths and the happy path.

---

## Phase 3 — Projects CRUD

**Goal**: Users can list, create, rename, delete their projects. Active-project memory works.

**Deliverables**
- `backend/models.py` — add `list_projects`, `create_project`, `update_project`, `delete_project`, `get_project_for_user`, `set_active_project`.
- `backend/app.py` — `/api/projects` endpoints.
- Update `auth.py` — `/api/auth/me` now also returns the active project id and projects list.

**Acceptance criteria**
- [ ] `GET /api/projects` returns only the current user's projects, ordered by `position`.
- [ ] `POST` rejects duplicate `id` with `409`.
- [ ] `PATCH` and `DELETE` return `404` for ids the user does not own (not `403`, to avoid enumeration).
- [ ] `DELETE` cascades: project, stages, blockers, items, ideas, goal all gone afterward (verified via `SELECT COUNT(*)`).
- [ ] `PUT /api/projects/<id>/active` sets `user.active_project_id`; subsequent `me` returns it.
- [ ] Deleting the active project clears `active_project_id`.

**Verification**
- `tests/test_projects.py`: ownership isolation, cascade, active project memory.

---

## Phase 4 — Scoped Stages / Blockers / Items / Ideas API

**Goal**: All existing `ANALYSIS.md` §6.3 endpoints re-scoped under `/api/projects/<pid>/...`.

**Deliverables**
- `backend/models.py` — CRUD for stage, blocker, sub_item, idea, plus `build_snapshot(pid)`.
- `backend/serializers.py` — JSON row converters.
- `backend/app.py` — routes per `02_api_design.md` §5.

**Acceptance criteria**
- [ ] `GET /api/projects/<pid>/snapshot` returns the full tree in one round-trip.
- [ ] Every project-scoped route returns `404` for projects not owned by the caller.
- [ ] `status` is validated against the correct enum (4-value for stage, 8-value for blocker/sub-item); invalid status returns `400 validation`.
- [ ] `deep=true` server-side forces `status='park'`; setting `status='solve'` forces `deep=false, status='todo'`.
- [ ] `goal` is one-per-project; `PUT /api/projects/<pid>/goal` upserts.

**Verification**
- `tests/test_stages.py`: snapshot shape, status validation, deep/solve coupling, ownership.

---

## Phase 5 — Frontend Refactor (single-project, parity)

**Goal**: Move the existing `project_navigator.html` logic into `frontend/` modules. Same UI behavior, still operating on a single hard-coded project for now.

**Deliverables**
- `frontend/index.html` — bare shell: header + main + sidebar placeholder + portal menu.
- `frontend/css/main.css` — extracted from the existing `<style>` block.
- `frontend/js/api.js`, `state.js`, `stages.js`, `app.js` — module split per `03_frontend_architecture.md`.
- `app.js` — temporarily calls a stub `loadSnapshot()` that returns a hard-coded in-memory dataset (matches the current `localStorage` shape).

**Acceptance criteria**
- [ ] Opening `frontend/index.html` directly (file://) shows the same UI as `project_navigator.html` and supports add/edit/delete on the hard-coded dataset.
- [ ] No external network requests are made.
- [ ] No references to `localStorage` remain in `frontend/js/`.
- [ ] All inline `onclick="…"` handlers in the original are replaced with event delegation or per-element listeners in `stages.js`.

**Verification**
- Manual smoke: add stage, add blocker, toggle status, deep toggle, delete stage.

---

## Phase 6 — Login Page & Auth Bootstrap

**Goal**: Real auth in the frontend. `index.html` requires a session; unauthenticated users land on `login.html`.

**Deliverables**
- `frontend/login.html` — register/login form.
- `frontend/css/login.css` (or inline in `login.html`) — minimal styling.
- `frontend/js/auth.js` — per `03_frontend_architecture.md` §4.3.
- Update `app.js` — call `auth.bootstrap()` first.
- `app.py` — route `/` serves `frontend/index.html`; route `/login` serves `login.html`. Static files served from `frontend/` via Flask's static handler.

**Acceptance criteria**
- [ ] `GET /` while unauthenticated returns `login.html` (server-side redirect).
- [ ] After successful login, the user lands on `/` and sees the empty main pane (no project yet → "No stages yet" empty state).
- [ ] Reloading the browser preserves the session.
- [ ] `logout` returns to `login.html`.

**Verification**
- `tests/test_auth.py` extends to cover cookie round-trip via the Flask test client.

---

## Phase 7 — Sidebar, Header, Active-Project Memory

**Goal**: The new feature requirements (1) and (2) from `requirements/20260628_new_feature.md` are visible.

**Deliverables**
- `frontend/css/sidebar.css`, `frontend/css/header.css`.
- `frontend/js/projects.js` — sidebar render + actions.
- `frontend/index.html` — wire `<aside id="sidebar">` and `<header>` structure.
- Update `app.js` — on bootstrap, load sidebar and active project.

**Acceptance criteria**
- [ ] Left sidebar lists all of the current user's projects with the active one highlighted.
- [ ] `+ New project` creates a project, refreshes the sidebar, and loads the new project's snapshot.
- [ ] Rename and delete (with confirm) work and update the sidebar.
- [ ] Sidebar collapse toggle works and persists across reloads via `localStorage`.
- [ ] Header shows `Project Navigator` + `▸ {project name}`; selecting a different project updates the breadcrumb.
- [ ] Header shows the current username with a switcher dropdown; selecting "Switch user" returns to `login.html`.
- [ ] Reloading the browser opens the most recently active project without user intervention.

**Verification**
- Manual: log in as user A, create two projects, switch between them, log out, log in as user B, confirm A's projects are not visible.

---

## Phase 8 — Tests, Docs, Polish

**Goal**: Production-ish polish: full test coverage, populated `documentations/`, demo seed.

**Deliverables**
- `tests/` complete (auth, projects, stages).
- `scripts/seed.py` — creates demo user `demo / demo123` with one sample project.
- `documentations/setup.md` — install, run, default credentials.
- `documentations/user_guide.md` — screenshots-as-text walkthrough.
- `documentations/api_reference.md` — auto-generated-ish from `02_api_design.md`.
- README.md at the project root — overview + quickstart.

**Acceptance criteria**
- [ ] `pytest` passes with ≥80% line coverage on `backend/`.
- [ ] `python scripts/seed.py && flask run` produces a usable demo at `http://localhost:5000`.
- [ ] All three docs exist and link back to this folder.

**Verification**
- `pytest -q` from the repo root.
- `documentations/setup.md` followed verbatim on a clean checkout.

---

## Phase 9 — Legacy Banner & Final Cleanup

**Goal**: Old `project_navigator.html` no longer confuses users.

**Deliverables**
- Edit `project_navigator.html` — add a banner at the top:
  > **This is the legacy single-file version.** The new multi-user app lives at `frontend/index.html` (served by Flask at `/`). See [`README.md`](./README.md).
- Final pass: remove any leftover TODOs, update `README.md` cross-links.

**Acceptance criteria**
- [ ] Opening `project_navigator.html` directly shows the banner and otherwise behaves identically to before.
- [ ] No file references the legacy `localStorage` `pnav5` key except in `project_navigator.html` itself.
- [ ] `git status` shows only the expected new files plus the modified legacy banner.

**Verification**
- Visual: open `project_navigator.html` in a browser, confirm banner is visible and dismissable (small × button is acceptable).

---

## Summary Table

| # | Phase | Demonstrable result |
|---|-------|---------------------|
| 1 | Schema & Migrations | `sqlite3 project_navigator.db ".tables"` lists all 7 tables. |
| 2 | Auth backend | `curl` register → login → me works. |
| 3 | Projects CRUD | Multiple projects per user; ownership enforced. |
| 4 | Scoped Stages API | Snapshot endpoint serves the same shape as `localStorage`. |
| 5 | Frontend refactor | `frontend/index.html` behaves like the legacy file. |
| 6 | Login flow | Unauth users land on `login.html`. |
| 7 | Sidebar & Header | New feature requirements 1 + 2 visible. |
| 8 | Tests & Docs | `pytest` passes; docs complete. |
| 9 | Legacy banner | Old file points to the new app. |
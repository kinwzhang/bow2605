# 00 — Overview

## 1. Purpose

Document the development plan for the **Project Navigator** application as it evolves from a single-file localStorage tool into a multi-user, multi-project web app backed by SQLite.

This document is the entrypoint. Read it first; follow the links to deeper documents.

| # | Document | Covers |
|---|----------|--------|
| 00 | `00_overview.md` (this file) | Context, decisions, stack, structure, principles |
| 01 | `01_data_model.md` | Entities, schema, migrations |
| 02 | `02_api_design.md` | REST endpoints, payloads, errors, sessions |
| 03 | `03_frontend_architecture.md` | Module layout, render flow, sidebar, header |
| 04 | `04_roadmap.md` | Phased delivery, acceptance criteria |

## 2. Context Recap

### 2.1 Current state (as of 2026-06-28)

- `project_navigator/project_navigator.html` — single-file vanilla HTML/CSS/JS app, ~450 lines.
- Persistence: `localStorage` only (key `pnav5`).
- Data model: `goal → stages → blockers → sub_items`, plus `ideas` per stage.
- Behavior: focus-tool, Notion-inspired, full re-render on every mutation.
- `project_navigator/ANALYSIS.md` (existing) already proposes a Flask + SQLite backend and documents the current data model, ID strategy, render flow, and limitations.

### 2.2 New feature requirements

Sourced from `requirements/20260628_new_feature.md`:

1. **Multi-project support**
   - 1.1 Left-hand project list panel for navigation; each project has a unique name and an optional description.
   - 1.2 Create, delete, rename projects; selecting one swaps the main content.
   - 1.3 Panel is collapsible; remembers the last-selected project across reloads.
2. **Branding header** — "Project Navigator" prominently at the top; selected project name appears next to it.
3. **Multi-user support** — users log in and access their own projects; can switch between users. Simplified auth is acceptable for the prototype but the design must scale.

### 2.3 What this plan does

- Adds a Flask + SQLite backend (extending `ANALYSIS.md` §6).
- Adds `user` and `project` tables; scopes all existing entities under `project`.
- Refactors the existing single-file frontend into vanilla JS ES modules.
- Introduces session-cookie auth with a user switcher.
- Adds the left sidebar and branded header.
- Keeps `project_navigator.html` as a legacy reference (banner added, points to the new entrypoint).

## 3. Confirmed Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Frontend architecture | **Vanilla JS ES modules** | Preserves the no-build, no-dependency philosophy of the original. |
| Auth model | **Session cookies + user switcher**; username + password stored in SQLite (Werkzeug hash) | Simplest correct prototype path; session-based design is portable to JWT later without changing route signatures. |
| Legacy `project_navigator.html` | **Keep at root with a banner** pointing to the new entrypoint | Useful as a visual diff reference; old localStorage data is not auto-migrated. |
| Delivery order | **Phases 1 → 9 sequentially**, each ending in a runnable, testable state | Predictable review checkpoints; no half-finished dead-ends. |

## 4. Technical Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Language | Python 3.11+ | Matches the rest of the repo (`main.py`, `pyproject.toml`). |
| Web framework | Flask | Per `ANALYSIS.md` §6.1. Minimal, single-file friendly. |
| Database | SQLite via stdlib `sqlite3` | Single-file, zero-ops. |
| Migrations | Numbered SQL files in `backend/migrations/`, applied at boot | Per `ANALYSIS.md` §6.6. |
| Auth | Flask session cookies + Werkzeug password hashing | `flask.session` + `werkzeug.security`. |
| Frontend | Vanilla HTML/CSS/JS ES modules | `<script type="module">`, no bundler. |
| Server ↔ client | JSON over `fetch()` | Direct continuation of `ANALYSIS.md` §6.5. |
| Testing | `pytest` + Flask test client | Standard. |
| Dev runner | `flask run` on port 5000, single command | No Docker; matches "single-file friendly" spirit. |

## 5. Folder Structure

`project_navigator/` is the project root.

```
project_navigator/
├── project_navigator.html          # legacy — banner added in Phase 9
├── ANALYSIS.md                     # historical, unchanged
├── README.md                       # NEW — entrypoint docs
├── pyproject.toml                  # NEW — deps + scripts
├── config.py                       # NEW — Flask config (SECRET_KEY, DB_PATH)
├── .gitignore                      # NEW — *.db, __pycache__, venv, .env
│
├── requirements/
│   └── 20260628_new_feature.md     # existing
│
├── plan_and_design/                # this folder
│   ├── 00_overview.md
│   ├── 01_data_model.md
│   ├── 02_api_design.md
│   ├── 03_frontend_architecture.md
│   └── 04_roadmap.md
│
├── documentations/                 # populated in Phase 8
│   ├── setup.md
│   ├── user_guide.md
│   └── api_reference.md
│
├── backend/
│   ├── app.py                      # Flask app factory + routes
│   ├── database.py                 # SQLite connection + migration runner
│   ├── auth.py                     # session helpers, login_required decorator
│   ├── models.py                   # CRUD for users/projects/stages/blockers/items/ideas
│   ├── serializers.py              # JSON ↔ DB row conversion; snapshot builder
│   ├── migrations/
│   │   ├── 001_init.sql            # per ANALYSIS.md §6.2 (goal/stage/blocker/sub_item/idea)
│   │   └── 002_users_projects.sql  # adds user + project; project_id FK on stage/idea
│   └── project_navigator.db        # gitignored; created on first run
│
├── frontend/
│   ├── index.html                  # app shell — sidebar + header + main
│   ├── login.html                  # auth page
│   ├── css/
│   │   ├── main.css                # existing palette + stage/blocker/idea styles
│   │   ├── sidebar.css             # left project list panel
│   │   └── header.css              # branded top bar
│   └── js/
│       ├── api.js                  # fetch() wrapper, JSON, error handling
│       ├── state.js                # S cache + openStages/openBQ
│       ├── auth.js                 # login/logout/me, session bootstrap
│       ├── projects.js             # sidebar: list/create/rename/delete
│       ├── stages.js               # extracted stage/blocker/idea render + actions
│       └── app.js                  # bootstrap, routing by selected project
│
├── tests/
│   ├── conftest.py                 # Flask test client + temp-DB fixture
│   ├── test_auth.py
│   ├── test_projects.py
│   └── test_stages.py
│
└── scripts/
    ├── init_db.py                  # apply migrations to a fresh DB
    └── seed.py                     # demo user + sample project
```

## 6. Guiding Principles

1. **Match the existing aesthetic.** No build step, no framework, neutral palette, minimal chrome. The frontend is a tool, not a showcase.
2. **IDs stay client-generated.** `uid()` (base36 `Date.now()` + 3 random chars) preserves offline-first semantics; the DB accepts whatever the client produces.
3. **Optimistic writes with server validation.** Mutations feel instant (current UX); the server validates status values and rejects unknown ones with HTTP 400.
4. **Scope before authorization.** Every project-scoped route resolves `project_id` and verifies `project.user_id == current_user.id` before touching data. No row should leak across users.
5. **Phases end runnable.** After every phase, `flask run` + a browser tab demonstrates the new capability. No silent half-states.
6. **Backward compatibility is one-way.** `localStorage` data from `project_navigator.html` is **not** auto-migrated; the legacy file is preserved as a reference, not a feeder.
7. **Docs live with the code.** `plan_and_design/` captures *why* (this is what we agreed to build). `documentations/` captures *how* (run it, use it, call the API).

## 7. Open Items (to resolve during build)

| Item | Owner | Phase |
|------|-------|-------|
| Exact `SECRET_KEY` source for production (env var vs. config) | Phase 8 | before deploy |
| Whether to serve the frontend via Flask static or a separate dev server | Phase 5 | confirm during refactor |
| Demo data shape for `scripts/seed.py` | Phase 8 | not blocking |
| CSRF protection on mutating endpoints (Flask-WTF vs. manual token) | Phase 2 | lightweight manual token is acceptable for prototype |
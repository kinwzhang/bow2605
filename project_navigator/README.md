# Project Navigator

A multi-user hierarchical planning tool — break an "ultimate goal" into ordered
stages, each with blockers/questions and ideas. Notion-inspired, minimal chrome,
deliberately a focus tool rather than a full project-management suite.

Originally a single-file vanilla HTML/CSS/JS app with `localStorage` persistence.
Now a Flask + SQLite backend with a session-cookie auth frontend in vanilla JS ES
modules.

## Quickstart

```bash
cd project_navigator

# 1. (Optional) seed a demo account + project
python scripts/seed.py --reset-db
# → username: demo, password: demo1234

# 2. Run the dev server
python -m flask --app backend.app:create_app run --port 5000

# 3. Open the app
open http://localhost:5000/
# → redirects to /login.html; sign in with the demo credentials above
```

The first run automatically applies the SQLite migrations in
`backend/migrations/`.

## Tests

```bash
cd project_navigator
python -m pytest tests/ -v
# 92 tests, ~24s
```

## Project layout

```
project_navigator/
├── README.md                       ← you are here
├── pyproject.toml                  ← Python deps + pytest config
├── config.py                       ← Flask config (SECRET_KEY, DB_PATH, FRONTEND_DIR)
├── project_navigator.html          ← legacy single-file app (banner added in Phase 9)
├── ANALYSIS.md                     ← historical analysis of the legacy file
│
├── requirements/                   ← feature specs
├── plan_and_design/                ← design docs (this iteration's plan)
├── documentations/                 ← user-facing docs (setup, user guide, API reference)
│
├── backend/                        ← Flask app + SQLite migrations
│   ├── app.py                      ← routes + app factory
│   ├── database.py                 ← connection + migration runner
│   ├── auth.py                     ← session helpers + CSRF
│   ├── models.py                   ← CRUD for users / projects / stages / blockers / items / ideas
│   ├── migrations/
│   │   ├── 001_init.sql            ← initial schema (ANALYSIS.md §6.2)
│   │   └── 002_users_projects.sql  ← adds user + project tables
│   └── project_navigator.db        ← gitignored; created on first run
│
├── frontend/                       ← vanilla JS ES modules (no build step)
│   ├── index.html                  ← app shell: sidebar + header + main
│   ├── login.html                  ← auth page
│   ├── css/
│   │   ├── main.css                ← palette + stage/blocker/idea styles
│   │   ├── sidebar.css             ← left project list
│   │   ├── header.css              ← branded top bar
│   │   └── login.css               ← auth page styling
│   └── js/
│       ├── api.js                  ← fetch() wrapper with CSRF + 401 redirect
│       ├── state.js                ← in-memory cache + open-state maps + status enums
│       ├── auth.js                 ← login / register / logout / me
│       ├── projects.js             ← sidebar logic
│       └── stages.js               ← render + actions
│
├── tests/                          ← pytest suite
└── scripts/
    ├── init_db.py                  ← apply migrations to a SQLite database
    └── seed.py                     ← demo user + sample project
```

## Phase status

| # | Phase                              | Status |
|---|------------------------------------|--------|
| 1 | Schema & Migrations                | ✅ |
| 2 | Auth Backend                       | ✅ |
| 3 | Projects CRUD                      | ✅ |
| 4 | Scoped Stages API                  | ✅ |
| 5 | Frontend Refactor                  | ✅ |
| 6 | Login Page & Auth Bootstrap        | ✅ |
| 7 | Sidebar, Header, Active-Project Memory | ✅ |
| 8 | Tests, Docs, Polish                | ✅ |
| 9 | Legacy Banner & Final Cleanup      | ✅ |

See `plan_and_design/04_roadmap.md` for the per-phase acceptance criteria.

## Further reading

- `plan_and_design/00_overview.md` — context, decisions, stack, structure
- `plan_and_design/01_data_model.md` — entities, schema, migrations
- `plan_and_design/02_api_design.md` — REST endpoints
- `plan_and_design/03_frontend_architecture.md` — frontend modules
- `plan_and_design/04_roadmap.md` — phased delivery
- `documentations/setup.md` — local setup
- `documentations/user_guide.md` — using the app
- `documentations/api_reference.md` — REST API reference
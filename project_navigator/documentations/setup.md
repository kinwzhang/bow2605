# Setup

How to run the Project Navigator app locally.

## Prerequisites

- Python 3.11+ (developed and tested against 3.14).
- Flask 3.x and pytest (declared in `pyproject.toml`).

```bash
# In a virtualenv:
python3 -m venv .venv
.venv/bin/pip install -e .  # or: pip install flask pytest
```

## First-time setup

```bash
cd project_navigator

# 1. Seed a demo account + project (optional, recommended for exploration)
python scripts/seed.py --reset-db
# → username: demo, password: demo1234

# 2. Run the dev server
python -m flask --app backend.app:create_app run --port 5000

# 3. Open the app
open http://localhost:5000/
# → redirects to /login.html; sign in with the demo credentials
```

The first run automatically applies the SQLite migrations in
`backend/migrations/`. The DB file lives at
`backend/project_navigator.db` and is gitignored.

## Database helpers

```bash
# Apply pending migrations (idempotent)
python scripts/init_db.py

# Wipe and recreate
python scripts/init_db.py --reset

# Custom DB path
python scripts/init_db.py --db /tmp/x.db
```

Inspect with Python (no sqlite3 CLI required):

```bash
python -c "import sqlite3; c=sqlite3.connect('backend/project_navigator.db'); \
  print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")])"
```

## Run the test suite

```bash
cd project_navigator
python -m pytest tests/ -v
# 99 tests pass in ~20s
```

## Phase status

- ✅ Phase 1: Schema & Migrations
- ✅ Phase 2: Auth Backend (register/login/logout/me + CSRF)
- ✅ Phase 3: Projects CRUD (list/create/rename/delete + active memory)
- ✅ Phase 4: Scoped Stages API (stage/blocker/sub_item/idea + snapshot + goal)
- ✅ Phase 5: Frontend Refactor (vanilla ES modules)
- ✅ Phase 6: Login Page & Auth Bootstrap
- ✅ Phase 7: Sidebar, Header, Active-Project Memory
- ✅ Phase 8: Tests, Docs, Polish
- ✅ Phase 9: Legacy Banner & Final Cleanup

All 9 phases complete. 92 tests pass; 82% backend line coverage.

## See also

- `../README.md` — project overview
- `user_guide.md` — how to use the app
- `api_reference.md` — REST API reference
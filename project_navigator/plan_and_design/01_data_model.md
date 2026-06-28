# 01 — Data Model

## 1. Entity-Relationship Diagram

```
user (1) ──< project (N) ──< goal         (1:1, optional)
                       │
                       └──< stage (N) ──< blocker (N) ──< sub_item (N)
                       │
                       └──< idea   (N)
```

- One **user** owns many **projects**.
- Each **project** has at most one **goal** (the "north star") and an ordered list of **stages**.
- Each **stage** has many **blockers** (or questions) and many **ideas**.
- Each **blocker** has many **sub-items**.
- Deletes cascade down the tree; deleting a user removes every project and every descendant.

## 2. Tables

### 2.1 `user`  *(new in 002)*

| Column         | Type         | Constraints                       | Notes |
|----------------|--------------|-----------------------------------|-------|
| `id`           | INTEGER      | PK AUTOINCREMENT                  | |
| `username`     | TEXT         | NOT NULL, UNIQUE                  | Case-sensitive ASCII for the prototype. |
| `password_hash`| TEXT         | NOT NULL                          | `werkzeug.security.generate_password_hash`. |
| `created_at`   | TIMESTAMP    | DEFAULT CURRENT_TIMESTAMP         | |

### 2.2 `project`  *(new in 002)*

| Column        | Type         | Constraints                                  | Notes |
|---------------|--------------|----------------------------------------------|-------|
| `id`          | TEXT         | PK                                           | Client-generated `uid()` (matches `ANALYSIS.md` format). |
| `user_id`     | INTEGER      | NOT NULL → `user(id)` ON DELETE CASCADE      | Scoping key. |
| `name`        | TEXT         | NOT NULL                                     | Display name; uniqueness enforced per-user in the API layer (not DB). |
| `description` | TEXT         | NOT NULL DEFAULT `''`                        | Free-form, optional. |
| `position`    | INTEGER      | NOT NULL DEFAULT 0                           | Sidebar display order; ties broken by `created_at`. |
| `created_at`  | TIMESTAMP    | DEFAULT CURRENT_TIMESTAMP                     | |

Indexes: `idx_project_user ON project(user_id)`.

### 2.3 `goal`  *(per `ANALYSIS.md` §6.2, re-scoped to project)*

| Column        | Type     | Constraints                                                              | Notes |
|---------------|----------|--------------------------------------------------------------------------|-------|
| `id`          | INTEGER  | PK AUTOINCREMENT                                                         | |
| `project_id`  | TEXT     | NOT NULL UNIQUE → `project(id)` ON DELETE CASCADE                        | One goal per project. Replaces the old `CHECK (id = 1)` constraint. |
| `text`        | TEXT     | NOT NULL DEFAULT `''`                                                    | |

### 2.4 `stage`  *(per `ANALYSIS.md` §6.2, + project_id)*

| Column        | Type     | Constraints                                                                                                | Notes |
|---------------|----------|------------------------------------------------------------------------------------------------------------|-------|
| `id`          | TEXT     | PK                                                                                                         | Client `uid()`. |
| `project_id`  | TEXT     | NOT NULL → `project(id)` ON DELETE CASCADE                                                                 | Scoping key. |
| `name`        | TEXT     | NOT NULL                                                                                                   | |
| `status`      | TEXT     | NOT NULL DEFAULT `'todo'` CHECK (status IN ('todo','active','blocked','done'))                             | |
| `position`    | INTEGER  | NOT NULL DEFAULT 0                                                                                         | Display order within a project. |
| `created_at`  | TIMESTAMP| DEFAULT CURRENT_TIMESTAMP                                                                                  | |

Indexes: `idx_stage_project ON stage(project_id)`.

### 2.5 `blocker`  *(unchanged from `ANALYSIS.md` §6.2)*

| Column      | Type     | Constraints                                                                                                            | Notes |
|-------------|----------|------------------------------------------------------------------------------------------------------------------------|-------|
| `id`        | TEXT     | PK                                                                                                                     | |
| `stage_id`  | TEXT     | NOT NULL → `stage(id)` ON DELETE CASCADE                                                                               | Cascade reaches the project via the stage. |
| `text`      | TEXT     | NOT NULL                                                                                                               | |
| `status`    | TEXT     | NOT NULL DEFAULT `'todo'` — full set: `'todo','active','blocked','done','park','review','nice','solve'`                | Wider status set than stages; matches the frontend enum. |
| `deep`      | INTEGER  | NOT NULL DEFAULT 0                                                                                                     | Boolean: 0/1. |
| `position`  | INTEGER  | NOT NULL DEFAULT 0                                                                                                     | |

Indexes: `idx_blocker_stage ON blocker(stage_id)`.

### 2.6 `sub_item`  *(unchanged from `ANALYSIS.md` §6.2)*

| Column      | Type     | Constraints                                                                                            | Notes |
|-------------|----------|--------------------------------------------------------------------------------------------------------|-------|
| `id`        | TEXT     | PK                                                                                                     | |
| `blocker_id`| TEXT     | NOT NULL → `blocker(id)` ON DELETE CASCADE                                                             | |
| `text`      | TEXT     | NOT NULL                                                                                               | |
| `status`    | TEXT     | NOT NULL DEFAULT `'todo'` — full set as `blocker.status`                                               | |
| `deep`      | INTEGER  | NOT NULL DEFAULT 0                                                                                     | |
| `position`  | INTEGER  | NOT NULL DEFAULT 0                                                                                     | |

Indexes: `idx_subitem_blocker ON sub_item(blocker_id)`.

### 2.7 `idea`  *(per `ANALYSIS.md` §6.2, + project_id)*

| Column       | Type     | Constraints                                                  | Notes |
|--------------|----------|--------------------------------------------------------------|-------|
| `id`         | TEXT     | PK                                                           | |
| `project_id` | TEXT     | NOT NULL → `project(id)` ON DELETE CASCADE                   | Scoping key. |
| `stage_id`   | TEXT     | NOT NULL → `stage(id)` ON DELETE CASCADE                     | Lives inside a stage. |
| `text`       | TEXT     | NOT NULL                                                     | |
| `position`   | INTEGER  | NOT NULL DEFAULT 0                                           | |

Indexes: `idx_idea_project ON idea(project_id)`, `idx_idea_stage ON idea(stage_id)`.

## 3. Why not just one big JSON column?

We considered `project.data TEXT` (single JSON blob, like the current `localStorage`). We chose a normalized schema because:

1. The new requirement is **multi-user**. Two users on the same DB must not see each other's projects; row-level scoping makes that impossible to leak.
2. `blocker` and `sub_item` are queried independently (status counts, deep counts in badges). Indexed columns beat scanning JSON.
3. Cascade deletes are a one-liner (`ON DELETE CASCADE`) instead of a recursive walk in application code.

The trade-off (more boilerplate) is acceptable for a personal tool whose write volume is human-scale.

## 4. ID Strategy

- **Client-generated** `uid()`: `Date.now().toString(36) + Math.random().toString(36).slice(2,5)`. 10–12 char base36.
- All entity IDs (`project`, `stage`, `blocker`, `sub_item`, `idea`) use this format. SQL `TEXT PRIMARY KEY` accepts them as-is.
- Collisions on rapid creation (acknowledged limitation in `ANALYSIS.md` §5) are mitigated at the API layer: a 409 response on `UNIQUE` violation triggers a client retry.

## 5. Status Enums

Two distinct enums — the analyzer flagged this in the original; we preserve it:

- **Stage status**: `todo | active | blocked | done`  (4 values)
- **Blocker/sub-item status**: `todo | active | blocked | done | park | review | nice | solve`  (8 values)

Validation lives in `backend/models.py` (single source of truth). Both lists are also exported to the frontend so the renderer cannot drift.

## 6. Migrations

### 6.1 Strategy

- Migrations are plain numbered SQL files in `backend/migrations/`: `001_init.sql`, `002_users_projects.sql`, …
- On boot, `database.py` ensures a `schema_migrations(version INTEGER PRIMARY KEY, applied_at TIMESTAMP)` table exists, then applies any migration whose version is not yet recorded, in order, inside a transaction.
- Migrations are **append-only** — once applied to a DB, a file is never edited. Add a new file to change schema.

### 6.2 Initial state: `001_init.sql`

Implements the schema in `ANALYSIS.md` §6.2 verbatim (`goal` with `CHECK (id = 1)`, `stage`, `blocker`, `sub_item`, `idea` — no `user`/`project`). Kept as-is to honor the existing analysis document and to allow a clean DB from scratch.

### 6.3 `002_users_projects.sql`

1. Create `user` and `project`.
2. Backfill: insert one default user `legacy` with a random password hash (printed to the console once on first boot); for each existing row in `goal` / `stage` / `idea`, insert a corresponding `project` owned by `legacy`, and update the row's `project_id`.
3. Drop the `CHECK (id = 1)` constraint on `goal` (SQLite requires a table rebuild for this).
4. Recreate `goal` with `project_id UNIQUE`.
5. Add `project_id` columns to `stage` and `idea`, populate, and create indexes.
6. Record the migration version.

Concrete DDL is written in `backend/migrations/002_users_projects.sql` during Phase 1 — pseudo-SQL is shown in §6.4 below.

### 6.4 Backfill pseudocode (executed by 002)

```sql
-- 1. Create user table
CREATE TABLE user (...);

-- 2. Create legacy user with a random password (printed once)
INSERT INTO user (id, username, password_hash)
VALUES (1, 'legacy', :random_hash);

-- 3. Create project table
CREATE TABLE project (...);

-- 4. Bootstrap one project per existing top-level dataset
INSERT INTO project (id, user_id, name, description, position)
VALUES ('legacy00001', 1, 'Imported project', 'Auto-created from localStorage migration', 0);

-- 5. Rebuild goal table (drop CHECK, add project_id)
ALTER TABLE goal RENAME TO _goal_old;
CREATE TABLE goal (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL UNIQUE REFERENCES project(id) ON DELETE CASCADE,
    text        TEXT NOT NULL DEFAULT ''
);
INSERT INTO goal (project_id, text)
SELECT 'legacy00001', text FROM _goal_old;
DROP TABLE _goal_old;

-- 6. stage: add project_id
ALTER TABLE stage ADD COLUMN project_id TEXT REFERENCES project(id) ON DELETE CASCADE;
UPDATE stage SET project_id = 'legacy00001';
-- (position is not backfilled from old data — defaults to 0; ordering preserved by created_at on reload)

-- 7. idea: add project_id (also requires a stage_id, which already exists)
ALTER TABLE idea ADD COLUMN project_id TEXT REFERENCES project(id) ON DELETE CASCADE;
UPDATE idea SET project_id = 'legacy00001';

-- 8. Indexes + record migration
CREATE INDEX idx_stage_project ON stage(project_id);
CREATE INDEX idx_idea_project  ON idea(project_id);
INSERT INTO schema_migrations (version) VALUES (2);
```

## 7. Concurrency & Locking

SQLite is single-writer. For the prototype:

- `PRAGMA journal_mode=WAL` — better read concurrency.
- `PRAGMA foreign_keys=ON` — enforce cascades.
- `PRAGMA busy_timeout=5000` — wait briefly if locked.

No connection pooling is required; one connection per request, closed in a `teardown_appcontext` hook.

## 8. Diagram (text)

```
┌──────────┐       ┌─────────────┐        ┌──────┐
│   user   │1────N │   project   │1──1    │ goal │
│──────────│       │─────────────│────────│──────│
│ id (PK)  │       │ id (PK,TXT) │        │ id   │
│ username │       │ user_id (FK)│        │ proj │
│ pw_hash  │       │ name        │        │ text │
│ created  │       │ descr       │        └──────┘
└──────────┘       │ position    │
                   │ created     │
                   └──────┬──────┘
                          │1
                          │
              ┌───────────┴───────────┐
              │N                      │N
         ┌────▼─────┐            ┌────▼────┐
         │  stage   │1────────N  │  idea   │
         │──────────│            │─────────│
         │ id (PK)  │            │ id (PK) │
         │ project  │            │ project │
         │ name     │            │ stage   │
         │ status   │            │ text    │
         │ position │            │ pos     │
         └────┬─────┘            └─────────┘
              │1
              │
              │N
         ┌────▼─────┐
         │ blocker  │1────N┌───────────┐
         │──────────│      │ sub_item  │
         │ id (PK)  │      │───────────│
         │ stage    │      │ id (PK)   │
         │ text     │      │ blocker   │
         │ status   │      │ text      │
         │ deep     │      │ status    │
         │ position │      │ deep      │
         └──────────┘      │ position  │
                           └───────────┘
```

Lines annotated `1` / `N` show cardinality. Cascade direction: user → project → stage → blocker → sub_item; project → idea (via stage).
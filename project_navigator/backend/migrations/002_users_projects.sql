-- 002_users_projects.sql
-- Adds the user and project tables, scopes existing entities under a project, and
-- drops the legacy CHECK(id = 1) constraint on goal.
--
-- This file is safe to run on a fresh DB (one legacy user and one default project
-- are created) and on a DB pre-populated by 001 (existing rows are reassigned to
-- the default project).

-- 1. user table. active_project_id is added as a TEXT column referencing
--    project(id); SQLite cannot express a FOREIGN KEY in ALTER TABLE, so the
--    referential integrity is enforced at the application layer.
CREATE TABLE user (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT NOT NULL UNIQUE,
    password_hash     TEXT NOT NULL,
    active_project_id TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Bootstrap the legacy user with a hash that the migration runner substitutes.
--    The runner generates a random password, hashes it, and binds :legacy_hash.
INSERT INTO user (id, username, password_hash) VALUES (1, 'legacy', :legacy_hash);

-- 3. project table.
CREATE TABLE project (
    id          TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_project_user ON project(user_id);

-- 4. Bootstrap one default project for the legacy user and point the user at it.
INSERT INTO project (id, user_id, name, description, position)
VALUES ('legacy00001', 1, 'Imported project', 'Auto-created from initial schema', 0);
UPDATE user SET active_project_id = 'legacy00001' WHERE id = 1;

-- 5. Rebuild goal: drop CHECK(id = 1), add project_id UNIQUE.
--    SQLite cannot ALTER a CHECK constraint, so the standard rebuild dance is used.
ALTER TABLE goal RENAME TO _goal_old;
CREATE TABLE goal (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL UNIQUE REFERENCES project(id) ON DELETE CASCADE,
    text        TEXT NOT NULL DEFAULT ''
);
INSERT INTO goal (project_id, text)
SELECT 'legacy00001', text FROM _goal_old;
DROP TABLE _goal_old;

-- 6. Add project_id to stage and backfill existing rows.
ALTER TABLE stage ADD COLUMN project_id TEXT REFERENCES project(id) ON DELETE CASCADE;
UPDATE stage SET project_id = 'legacy00001' WHERE project_id IS NULL;

-- 7. Add project_id to idea and backfill existing rows.
ALTER TABLE idea ADD COLUMN project_id TEXT REFERENCES project(id) ON DELETE CASCADE;
UPDATE idea SET project_id = 'legacy00001' WHERE project_id IS NULL;

-- 8. Indexes for the new scoping columns.
CREATE INDEX idx_stage_project ON stage(project_id);
CREATE INDEX idx_idea_project  ON idea(project_id);
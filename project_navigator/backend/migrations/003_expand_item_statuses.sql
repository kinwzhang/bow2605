-- 003_expand_item_statuses.sql
-- Expand the CHECK constraints on stage.status, blocker.status, and
-- sub_item.status from the original 4 statuses (todo/active/blocked/done)
-- to the full 7 used by the stage rollup palette:
--   todo, active, blocked, done, park, review, nice
-- Items additionally accept `solve` (the deep-mode "to solve" status).
--
-- Existing data is unaffected (all current values are subset-valid). The
-- rebuild dance is required because SQLite cannot ALTER a CHECK constraint
-- in place.
--
-- We disable foreign_keys for the duration of the migration. Reason:
-- `ALTER TABLE ... RENAME TO ...` rewrites all FK targets that name the
-- renamed table, so `blocker.stage_id` becomes a FK to `_stage_old` after
-- the rename. Then `DROP TABLE _stage_old` cascades through that FK and
-- wipes every blocker / sub_item / idea row. Disabling FKs lets the
-- rename and drop happen without cascade.

PRAGMA foreign_keys = OFF;

ALTER TABLE stage RENAME TO _stage_old;
CREATE TABLE stage (
    id        TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'todo'
              CHECK (status IN ('todo','active','blocked','done','park','review','nice')),
    position  INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO stage (id, project_id, name, status, position, created_at)
    SELECT id, project_id, name, status, position, created_at FROM _stage_old;
DROP TABLE _stage_old;
CREATE INDEX idx_stage_project ON stage(project_id);

ALTER TABLE blocker RENAME TO _blocker_old;
CREATE TABLE blocker (
    id        TEXT PRIMARY KEY,
    stage_id  TEXT NOT NULL REFERENCES stage(id) ON DELETE CASCADE,
    text      TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'todo'
              CHECK (status IN ('todo','active','blocked','done','park','review','nice','solve')),
    deep      INTEGER NOT NULL DEFAULT 0,
    position  INTEGER NOT NULL DEFAULT 0
);
INSERT INTO blocker (id, stage_id, text, status, deep, position)
    SELECT id, stage_id, text, status, deep, position FROM _blocker_old;
DROP TABLE _blocker_old;
CREATE INDEX idx_blocker_stage ON blocker(stage_id);

ALTER TABLE sub_item RENAME TO _sub_item_old;
CREATE TABLE sub_item (
    id         TEXT PRIMARY KEY,
    blocker_id TEXT NOT NULL REFERENCES blocker(id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'todo'
              CHECK (status IN ('todo','active','blocked','done','park','review','nice','solve')),
    deep       INTEGER NOT NULL DEFAULT 0,
    position   INTEGER NOT NULL DEFAULT 0
);
INSERT INTO sub_item (id, blocker_id, text, status, deep, position)
    SELECT id, blocker_id, text, status, deep, position FROM _sub_item_old;
DROP TABLE _sub_item_old;
CREATE INDEX idx_subitem_blocker ON sub_item(blocker_id);

-- Rebuild idea too: the stage_id FK still points to the renamed "_stage_old".
-- Without this rebuild, INSERT INTO idea fails with "no such table" because
-- SQLite tracks FK targets by name, and the rename updated all references
-- automatically. We must rebuild idea with the new "stage" FK target.
ALTER TABLE idea RENAME TO _idea_old;
CREATE TABLE idea (
    id         TEXT PRIMARY KEY,
    stage_id   TEXT NOT NULL REFERENCES stage(id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    position   INTEGER NOT NULL DEFAULT 0,
    project_id TEXT REFERENCES project(id) ON DELETE CASCADE
);
INSERT INTO idea (id, stage_id, text, position, project_id)
    SELECT id, stage_id, text, position, project_id FROM _idea_old;
DROP TABLE _idea_old;
CREATE INDEX idx_idea_stage   ON idea(stage_id);
CREATE INDEX idx_idea_project ON idea(project_id);

PRAGMA foreign_keys = ON;
-- 001_init.sql
-- Initial schema per ANALYSIS.md §6.2.
-- This migration creates the data model that 002 will extend with users and projects.

-- Single-row goal table (id constrained to 1 in 001; the constraint is dropped in 002
-- so the goal can be keyed by project_id).
CREATE TABLE goal (
    id    INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    text  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE stage (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'todo'
              CHECK (status IN ('todo','active','blocked','done')),
    position  INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE blocker (
    id        TEXT PRIMARY KEY,
    stage_id  TEXT NOT NULL REFERENCES stage(id) ON DELETE CASCADE,
    text      TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'todo',
    deep      INTEGER NOT NULL DEFAULT 0,
    position  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sub_item (
    id         TEXT PRIMARY KEY,
    blocker_id TEXT NOT NULL REFERENCES blocker(id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'todo',
    deep       INTEGER NOT NULL DEFAULT 0,
    position   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE idea (
    id        TEXT PRIMARY KEY,
    stage_id  TEXT NOT NULL REFERENCES stage(id) ON DELETE CASCADE,
    text      TEXT NOT NULL,
    position  INTEGER NOT NULL DEFAULT 0
);

-- Cascade lookup indexes.
CREATE INDEX idx_blocker_stage   ON blocker(stage_id);
CREATE INDEX idx_subitem_blocker ON sub_item(blocker_id);
CREATE INDEX idx_idea_stage      ON idea(stage_id);
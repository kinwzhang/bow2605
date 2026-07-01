-- 005_notes_and_timestamps.sql
-- Adds note, status_changed_at, and updated_at columns to stage, blocker,
-- sub_item, and idea tables for enhancement requirement 20260701.

-- Stage: add note, status_changed_at, updated_at
ALTER TABLE stage ADD COLUMN note TEXT NOT NULL DEFAULT '';
ALTER TABLE stage ADD COLUMN status_changed_at TIMESTAMP;
ALTER TABLE stage ADD COLUMN updated_at TIMESTAMP;

-- Blocker: add note, status_changed_at, updated_at
ALTER TABLE blocker ADD COLUMN note TEXT NOT NULL DEFAULT '';
ALTER TABLE blocker ADD COLUMN status_changed_at TIMESTAMP;
ALTER TABLE blocker ADD COLUMN updated_at TIMESTAMP;

-- Sub-item: add note, status_changed_at, updated_at
ALTER TABLE sub_item ADD COLUMN note TEXT NOT NULL DEFAULT '';
ALTER TABLE sub_item ADD COLUMN status_changed_at TIMESTAMP;
ALTER TABLE sub_item ADD COLUMN updated_at TIMESTAMP;

-- Idea: add note, updated_at
ALTER TABLE idea ADD COLUMN note TEXT NOT NULL DEFAULT '';
ALTER TABLE idea ADD COLUMN updated_at TIMESTAMP;

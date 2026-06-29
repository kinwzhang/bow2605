-- 004_user_preferences.sql
-- Adds theme and mode columns for per-user color theme persistence.

ALTER TABLE user ADD COLUMN theme TEXT NOT NULL DEFAULT 'blue';
ALTER TABLE user ADD COLUMN mode TEXT NOT NULL DEFAULT 'light';

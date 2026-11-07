-- ISE-A4 migration 001 DOWN: removes every table and trigger created by 001_up.sql.
-- DESTRUCTIVE. Always run `python scripts/rollback.py backup` first (ROLLBACK.md, level 4).
DROP TRIGGER IF EXISTS history_no_delete;
DROP TRIGGER IF EXISTS history_no_update;
DROP TRIGGER IF EXISTS candidates_transition_guard;
DROP TRIGGER IF EXISTS assignments_owner_immutable;
DROP TRIGGER IF EXISTS assignments_version_guard;
DROP TABLE IF EXISTS idempotency_keys;
DROP TABLE IF EXISTS history;
DROP TABLE IF EXISTS candidates;
DROP TABLE IF EXISTS sources;
DROP TABLE IF EXISTS assignments;
DROP TABLE IF EXISTS auth_tokens;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS schema_migrations;

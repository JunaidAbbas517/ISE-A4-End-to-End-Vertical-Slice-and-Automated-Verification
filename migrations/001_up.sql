-- ISE-A4 migration 001: persistent store for the deadline-confirmation slice.
-- Rollback: migrations/001_down.sql (take a backup first, see ROLLBACK.md).
PRAGMA foreign_keys = ON;

CREATE TABLE schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE students (
    student_id    TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL
);

-- Only SHA-256 of bearer tokens is stored; plaintext tokens never touch the DB.
CREATE TABLE auth_tokens (
    token_sha256  TEXT PRIMARY KEY CHECK (length(token_sha256) = 64),
    student_id    TEXT NOT NULL REFERENCES students(student_id),
    created_at    TEXT NOT NULL,
    revoked       INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1))
);

-- Personal tracked deadline (A2 aggregate root). Never the official university record.
CREATE TABLE assignments (
    assignment_id       TEXT PRIMARY KEY,
    course_id           TEXT NOT NULL,
    student_id          TEXT NOT NULL REFERENCES students(student_id),
    title               TEXT NOT NULL CHECK (length(trim(title)) > 0),
    deadline_local_iso  TEXT NOT NULL,
    deadline_zone       TEXT NOT NULL,
    version             INTEGER NOT NULL CHECK (version >= 1)
);

CREATE TABLE sources (
    source_id           TEXT PRIMARY KEY,
    assignment_id       TEXT NOT NULL REFERENCES assignments(assignment_id),
    source_kind         TEXT NOT NULL,
    source_ref          TEXT NOT NULL,
    content_sha256      TEXT NOT NULL CHECK (length(content_sha256) = 64),
    authority_verified  INTEGER NOT NULL CHECK (authority_verified IN (0, 1))
);

CREATE TABLE candidates (
    candidate_id        TEXT PRIMARY KEY,
    assignment_id       TEXT NOT NULL REFERENCES assignments(assignment_id),
    source_id           TEXT NOT NULL REFERENCES sources(source_id),
    proposed_local_iso  TEXT NOT NULL,
    proposed_zone       TEXT NOT NULL,
    base_version        INTEGER NOT NULL CHECK (base_version >= 1),
    status              TEXT NOT NULL CHECK (status IN ('PENDING_REVIEW', 'INVALID', 'REJECTED', 'APPLIED')),
    decided_by          TEXT,
    decided_at          TEXT
);

-- Append-only revision history (A2 I3). kind=REVERT is a compensating rollback entry.
CREATE TABLE history (
    history_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id       TEXT NOT NULL REFERENCES assignments(assignment_id),
    kind                TEXT NOT NULL CHECK (kind IN ('APPLY', 'REVERT')),
    old_local_iso       TEXT NOT NULL,
    old_zone            TEXT NOT NULL,
    new_local_iso       TEXT NOT NULL,
    new_zone            TEXT NOT NULL,
    old_version         INTEGER NOT NULL,
    new_version         INTEGER NOT NULL CHECK (new_version = old_version + 1),
    candidate_id        TEXT REFERENCES candidates(candidate_id),
    source_id           TEXT REFERENCES sources(source_id),
    reverts_history_id  INTEGER REFERENCES history(history_id),
    actor_id            TEXT NOT NULL,
    recorded_at         TEXT NOT NULL
);

-- Stored responses for duplicate-request handling, scoped per student.
CREATE TABLE idempotency_keys (
    student_id      TEXT NOT NULL,
    idem_key        TEXT NOT NULL,
    request_sha256  TEXT NOT NULL,
    status_code     INTEGER NOT NULL,
    response_json   TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (student_id, idem_key)
);

-- Storage-level guards. These close the A2 counterexample W6 (direct mutation
-- bypassing domain rules) for any client that writes through SQLite.

CREATE TRIGGER assignments_version_guard
BEFORE UPDATE OF deadline_local_iso, deadline_zone, version ON assignments
WHEN NEW.version <> OLD.version + 1
  OR NOT EXISTS (
      SELECT 1 FROM history h
      WHERE h.assignment_id = NEW.assignment_id
        AND h.old_version = OLD.version
        AND h.new_version = NEW.version
        AND h.new_local_iso = NEW.deadline_local_iso
        AND h.new_zone = NEW.deadline_zone)
BEGIN
    SELECT RAISE(ABORT, 'I3_VERSION_GUARD: deadline change needs version+1 and a matching history row');
END;

CREATE TRIGGER assignments_owner_immutable
BEFORE UPDATE OF student_id, assignment_id ON assignments
BEGIN
    SELECT RAISE(ABORT, 'I1_OWNER_GUARD: assignment identity and owner are immutable');
END;

CREATE TRIGGER candidates_transition_guard
BEFORE UPDATE OF status ON candidates
WHEN NOT (OLD.status = 'PENDING_REVIEW' AND NEW.status IN ('REJECTED', 'APPLIED'))
BEGIN
    SELECT RAISE(ABORT, 'I4_STATE_GUARD: illegal candidate status transition');
END;

CREATE TRIGGER history_no_update BEFORE UPDATE ON history
BEGIN
    SELECT RAISE(ABORT, 'HISTORY_APPEND_ONLY');
END;

CREATE TRIGGER history_no_delete BEFORE DELETE ON history
BEGIN
    SELECT RAISE(ABORT, 'HISTORY_APPEND_ONLY');
END;

INSERT INTO schema_migrations (version, applied_at) VALUES (1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));

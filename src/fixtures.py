"""Load the frozen synthetic fixture set into a migrated database."""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from pathlib import Path

from src.domain import parse_deadline
from src.service import sha256_hex, utc_now

FIXTURES = Path(__file__).resolve().parents[1] / 'data' / 'a4-fixtures.json'


def fixture_sha256(path: Path = FIXTURES) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(conn: sqlite3.Connection, tokens: dict[str, str] | None = None,
         path: Path = FIXTURES) -> dict[str, str]:
    """Insert fixtures; returns {student_id: plaintext_token}. Only token hashes are stored."""
    data = json.loads(path.read_text(encoding='utf-8'))
    tokens = dict(tokens or {})
    conn.execute('BEGIN')
    try:
        for s in data['students']:
            conn.execute('INSERT INTO students VALUES (?, ?)', (s['student_id'], s['display_name']))
            token = tokens.setdefault(s['student_id'], secrets.token_urlsafe(24))
            conn.execute('INSERT INTO auth_tokens (token_sha256, student_id, created_at) VALUES (?, ?, ?)',
                         (sha256_hex(token), s['student_id'], utc_now()))
        for a in data['assignments']:
            parse_deadline(a['deadline_local_iso'], a['deadline_zone'])  # I5 at load time
            conn.execute('INSERT INTO assignments VALUES (?, ?, ?, ?, ?, ?, 1)',
                         (a['assignment_id'], a['course_id'], a['student_id'], a['title'],
                          a['deadline_local_iso'], a['deadline_zone']))
        for s in data['sources']:
            conn.execute('INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?)',
                         (s['source_id'], s['assignment_id'], s['source_kind'], s['source_ref'],
                          sha256_hex(s['content_text']), int(s['authority_verified'])))
        for c in data['candidates']:
            parse_deadline(c['proposed_local_iso'], c['proposed_zone'])
            conn.execute("INSERT INTO candidates (candidate_id, assignment_id, source_id, proposed_local_iso, "
                         "proposed_zone, base_version, status) VALUES (?, ?, ?, ?, ?, ?, 'PENDING_REVIEW')",
                         (c['candidate_id'], c['assignment_id'], c['source_id'], c['proposed_local_iso'],
                          c['proposed_zone'], c['base_version']))
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return tokens

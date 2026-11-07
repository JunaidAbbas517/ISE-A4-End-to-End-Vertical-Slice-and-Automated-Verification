"""Server-side application service for the A4 slice.

Every rule here runs in the backend process, never in the browser:
authentication, ownership, idempotency, stale-version detection, source authority,
temporal validation and the atomic state change. Domain rules come from the
unchanged A2 model (src/domain.py).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain import Decision, DomainError, parse_deadline
from src.ics import assignment_to_ics

AUTHORITATIVE_KINDS = {'OFFICIAL_LMS', 'INSTRUCTOR_EMAIL'}
IDEM_KEY_RE = re.compile(r'^[A-Za-z0-9_-]{8,128}$')
ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


@dataclass(eq=False)
class ServiceError(Exception):
    status: int
    code: str
    message: str
    recovery: str = ''

    def __str__(self) -> str:
        return f'{self.status} {self.code}: {self.message}'

    def body(self) -> dict:
        return {'error': {'code': self.code, 'message': self.message, 'recovery': self.recovery}}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------- authentication
def authenticate(conn: sqlite3.Connection, authorization_header: str | None) -> str:
    if not authorization_header or not authorization_header.startswith('Bearer '):
        raise ServiceError(401, 'UNAUTHENTICATED', 'Sign in with your access token.',
                           'Paste your demo token and press Sign in.')
    token = authorization_header[len('Bearer '):].strip()
    if not token or len(token) > 256:
        raise ServiceError(401, 'UNAUTHENTICATED', 'Sign in with your access token.',
                           'Paste your demo token and press Sign in.')
    row = conn.execute('SELECT student_id FROM auth_tokens WHERE token_sha256 = ? AND revoked = 0',
                       (sha256_hex(token),)).fetchone()
    if row is None:
        raise ServiceError(401, 'UNAUTHENTICATED', 'This token is not valid or has been revoked.',
                           'Check the token and sign in again.')
    return row['student_id']


def student_profile(conn: sqlite3.Connection, student_id: str) -> dict:
    row = conn.execute('SELECT student_id, display_name FROM students WHERE student_id = ?',
                       (student_id,)).fetchone()
    return dict(row)


# ---------------------------------------------------------------- reads
def _candidate_view(row: sqlite3.Row) -> dict:
    return {
        'candidate_id': row['candidate_id'],
        'proposed_local_iso': row['proposed_local_iso'],
        'proposed_zone': row['proposed_zone'],
        'base_version': row['base_version'],
        'status': row['status'],
        'source': {'source_id': row['source_id'], 'kind': row['source_kind'],
                   'ref': row['source_ref'], 'authority_verified': bool(row['authority_verified'])},
    }


def list_assignments(conn: sqlite3.Connection, student_id: str) -> list[dict]:
    assignments = conn.execute(
        'SELECT assignment_id, course_id, title, deadline_local_iso, deadline_zone, version '
        'FROM assignments WHERE student_id = ? ORDER BY assignment_id', (student_id,)).fetchall()
    result = []
    for a in assignments:
        cands = conn.execute(
            'SELECT c.*, s.source_kind, s.source_ref, s.authority_verified FROM candidates c '
            'JOIN sources s ON s.source_id = c.source_id '
            "WHERE c.assignment_id = ? AND c.status = 'PENDING_REVIEW' ORDER BY c.candidate_id",
            (a['assignment_id'],)).fetchall()
        history = conn.execute(
            'SELECT history_id, kind, old_local_iso, new_local_iso, old_version, new_version, '
            'candidate_id, recorded_at FROM history WHERE assignment_id = ? ORDER BY history_id',
            (a['assignment_id'],)).fetchall()
        item = dict(a)
        item['pending_candidates'] = [_candidate_view(c) for c in cands]
        item['history'] = [dict(h) for h in history]
        result.append(item)
    return result


def _owned_assignment(conn: sqlite3.Connection, student_id: str, assignment_id: str) -> dict:
    # Same 404 for "missing" and "someone else's": no existence oracle for other students' data.
    row = conn.execute('SELECT * FROM assignments WHERE assignment_id = ? AND student_id = ?',
                       (assignment_id, student_id)).fetchone()
    if row is None:
        raise ServiceError(404, 'NOT_FOUND', 'Assignment not found.', 'Reload your assignment list.')
    return dict(row)


def export_ics(conn: sqlite3.Connection, student_id: str, assignment_id: str,
               now: datetime | None = None) -> str:
    if not ID_RE.match(assignment_id or ''):
        raise ServiceError(404, 'NOT_FOUND', 'Assignment not found.', 'Reload your assignment list.')
    return assignment_to_ics(_owned_assignment(conn, student_id, assignment_id), now)


# ---------------------------------------------------------------- the write path
def validate_decision_request(candidate_id: str, payload: object, idem_key: str | None) -> tuple[Decision, int]:
    if not ID_RE.match(candidate_id or ''):
        raise ServiceError(404, 'NOT_FOUND', 'Change not found.', 'Reload your assignment list.')
    if not idem_key or not IDEM_KEY_RE.match(idem_key):
        raise ServiceError(400, 'IDEMPOTENCY_KEY_REQUIRED',
                           'Each change request needs an Idempotency-Key header (8-128 letters, digits, - or _).',
                           'Reload the page and try again.')
    if not isinstance(payload, dict) or set(payload) != {'decision', 'expected_version'}:
        raise ServiceError(400, 'INVALID_REQUEST',
                           'Body must be exactly {"decision": ..., "expected_version": ...}.',
                           'Reload the page and try again.')
    try:
        decision = Decision(payload['decision'])
    except ValueError:
        raise ServiceError(400, 'INVALID_DECISION', 'Decision must be CONFIRM or REJECT.',
                           'Use the Confirm or Reject button.') from None
    version = payload['expected_version']
    if isinstance(version, bool) or not isinstance(version, int) or not 1 <= version <= 1_000_000:
        raise ServiceError(400, 'INVALID_VERSION', 'expected_version must be a positive integer.',
                           'Reload the page and try again.')
    return decision, version


def decide(conn: sqlite3.Connection, student_id: str, candidate_id: str, payload: object,
           idem_key: str | None) -> tuple[int, dict, bool]:
    """Confirm or reject one candidate. Returns (http_status, body, replayed)."""
    decision, expected_version = validate_decision_request(candidate_id, payload, idem_key)
    request_hash = sha256_hex(json.dumps(
        {'candidate_id': candidate_id, 'decision': decision.value, 'expected_version': expected_version},
        sort_keys=True))

    conn.execute('BEGIN IMMEDIATE')  # serialises writers: no lost update between check and write
    try:
        stored = conn.execute(
            'SELECT request_sha256, status_code, response_json FROM idempotency_keys '
            'WHERE student_id = ? AND idem_key = ?', (student_id, idem_key)).fetchone()
        if stored is not None:
            conn.execute('ROLLBACK')
            if stored['request_sha256'] != request_hash:
                raise ServiceError(422, 'IDEMPOTENCY_KEY_REUSED',
                                   'This request key was already used for a different action.',
                                   'Reload the page; a fresh key will be used.')
            return stored['status_code'], json.loads(stored['response_json']), True

        try:
            status, body = _apply_decision(conn, student_id, candidate_id, decision, expected_version)
        except ServiceError as err:
            if err.status in (401, 403, 404):
                raise  # never cache auth/visibility outcomes
            status, body = err.status, err.body()

        conn.execute('INSERT INTO idempotency_keys VALUES (?, ?, ?, ?, ?, ?)',
                     (student_id, idem_key, request_hash, status, json.dumps(body), utc_now()))
        conn.execute('COMMIT')
        return status, body, False
    except BaseException:
        if conn.in_transaction:
            conn.execute('ROLLBACK')
        raise


def _apply_decision(conn: sqlite3.Connection, student_id: str, candidate_id: str,
                    decision: Decision, expected_version: int) -> tuple[int, dict]:
    row = conn.execute(
        'SELECT c.*, a.student_id, a.version AS current_version, a.deadline_local_iso, a.deadline_zone, '
        's.source_kind, s.authority_verified FROM candidates c '
        'JOIN assignments a ON a.assignment_id = c.assignment_id '
        'JOIN sources s ON s.source_id = c.source_id WHERE c.candidate_id = ?', (candidate_id,)).fetchone()
    if row is None or row['student_id'] != student_id:  # I1: only the owning student
        raise ServiceError(404, 'NOT_FOUND', 'Change not found.', 'Reload your assignment list.')

    if row['status'] == 'APPLIED' and decision is Decision.CONFIRM:
        return 200, {'status': 'APPLIED', 'already_applied': True,
                     'assignment_id': row['assignment_id'], 'version': row['current_version'],
                     'message': 'This change was already applied. Nothing was changed twice.'}
    if row['status'] != 'PENDING_REVIEW':
        raise ServiceError(409, 'NOT_PENDING', f"This change is already {row['status'].lower()}.",
                           'Reload to see the current state.')
    if expected_version != row['current_version']:
        raise ServiceError(409, 'STALE_VERSION',
                           f"Your page showed version {expected_version}, but the deadline is now "
                           f"version {row['current_version']}.",
                           'Reload to see the latest deadline, then decide again.')
    now = utc_now()
    # REJECT is checked before CANDIDATE_OUTDATED: rejecting never mutates the deadline, so an
    # outdated candidate must stay rejectable (first test run found users could get stuck here).
    if decision is Decision.REJECT:  # I4: rejection never mutates the tracked deadline
        conn.execute("UPDATE candidates SET status = 'REJECTED', decided_by = ?, decided_at = ? "
                     'WHERE candidate_id = ?', (student_id, now, candidate_id))
        return 200, {'status': 'REJECTED', 'assignment_id': row['assignment_id'],
                     'version': row['current_version'], 'message': 'Change rejected. Your deadline is unchanged.'}

    if row['base_version'] != row['current_version']:
        raise ServiceError(409, 'CANDIDATE_OUTDATED',
                           'This proposed change was detected against an older deadline version.',
                           'Reject it, or wait for it to be re-detected against the current deadline.')

    # I2: provenance and authority
    if not row['authority_verified'] or row['source_kind'] not in AUTHORITATIVE_KINDS:
        raise ServiceError(422, 'SOURCE_NOT_AUTHORIZED',
                           'This change comes from an unverified source and cannot be applied.',
                           'Check the official course page; you can Reject this change.')
    # I5: explicit, consistent instants
    try:
        new_utc = parse_deadline(row['proposed_local_iso'], row['proposed_zone'])
        old_utc = parse_deadline(row['deadline_local_iso'], row['deadline_zone'])
    except DomainError as err:
        raise ServiceError(422, err.code, 'The proposed date/time is not a valid deadline.',
                           'Reject this change and check the official notice.') from None
    if new_utc == old_utc:
        raise ServiceError(422, 'NO_CHANGE', 'The proposed deadline equals your current deadline.',
                           'No action is needed; you can Reject it.')

    new_version = row['current_version'] + 1
    conn.execute(
        'INSERT INTO history (assignment_id, kind, old_local_iso, old_zone, new_local_iso, new_zone, '
        'old_version, new_version, candidate_id, source_id, actor_id, recorded_at) '
        "VALUES (?, 'APPLY', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (row['assignment_id'], row['deadline_local_iso'], row['deadline_zone'], row['proposed_local_iso'],
         row['proposed_zone'], row['current_version'], new_version, candidate_id, row['source_id'],
         student_id, now))
    conn.execute('UPDATE assignments SET deadline_local_iso = ?, deadline_zone = ?, version = ? '
                 'WHERE assignment_id = ?',
                 (row['proposed_local_iso'], row['proposed_zone'], new_version, row['assignment_id']))
    conn.execute("UPDATE candidates SET status = 'APPLIED', decided_by = ?, decided_at = ? "
                 'WHERE candidate_id = ?', (student_id, now, candidate_id))
    return 200, {'status': 'APPLIED', 'already_applied': False, 'assignment_id': row['assignment_id'],
                 'version': new_version, 'deadline_local_iso': row['proposed_local_iso'],
                 'deadline_zone': row['proposed_zone'], 'message': 'Deadline updated.'}


# ---------------------------------------------------------------- data rollback
def revert_change(conn: sqlite3.Connection, history_id: int, actor_id: str) -> dict:
    """Compensating rollback: restore the pre-change deadline as a NEW version.

    History stays append-only, so the original change and its reversal are both auditable.
    Refuses if the assignment has moved on since that change (would silently drop later work).
    """
    conn.execute('BEGIN IMMEDIATE')
    try:
        h = conn.execute("SELECT * FROM history WHERE history_id = ? AND kind = 'APPLY'",
                         (history_id,)).fetchone()
        if h is None:
            raise ServiceError(404, 'NOT_FOUND', f'No APPLY history entry {history_id}.')
        if conn.execute('SELECT 1 FROM history WHERE reverts_history_id = ?', (history_id,)).fetchone():
            raise ServiceError(409, 'ALREADY_REVERTED', f'History entry {history_id} was already reverted.')
        a = conn.execute('SELECT * FROM assignments WHERE assignment_id = ?', (h['assignment_id'],)).fetchone()
        if a['version'] != h['new_version']:
            raise ServiceError(409, 'STALE_VERSION',
                               f"Assignment is at v{a['version']}, change produced v{h['new_version']}; "
                               'revert later changes first.')
        new_version = a['version'] + 1
        conn.execute(
            'INSERT INTO history (assignment_id, kind, old_local_iso, old_zone, new_local_iso, new_zone, '
            'old_version, new_version, reverts_history_id, actor_id, recorded_at) '
            "VALUES (?, 'REVERT', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (a['assignment_id'], a['deadline_local_iso'], a['deadline_zone'], h['old_local_iso'],
             h['old_zone'], a['version'], new_version, history_id, actor_id, utc_now()))
        conn.execute('UPDATE assignments SET deadline_local_iso = ?, deadline_zone = ?, version = ? '
                     'WHERE assignment_id = ?',
                     (h['old_local_iso'], h['old_zone'], new_version, a['assignment_id']))
        conn.execute('COMMIT')
        return {'assignment_id': a['assignment_id'], 'version': new_version,
                'deadline_local_iso': h['old_local_iso'], 'reverted_history_id': history_id}
    except BaseException:
        if conn.in_transaction:
            conn.execute('ROLLBACK')
        raise

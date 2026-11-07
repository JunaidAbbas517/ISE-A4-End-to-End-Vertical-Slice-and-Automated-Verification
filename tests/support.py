"""Shared test helpers: fresh temp database per test, fixed synthetic tokens."""
from __future__ import annotations

import tempfile
from pathlib import Path

from src import db, fixtures

TOKENS = {'student-demo-01': 'test-token-student-a-0001', 'student-demo-02': 'test-token-student-b-0002'}
A, B = 'student-demo-01', 'student-demo-02'


class TempDB:
    def __init__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / 'test.db'
        conn = db.connect(self.path)
        db.migrate_up(conn)
        fixtures.load(conn, TOKENS)
        conn.close()

    def connect(self):
        return db.connect(self.path)

    def cleanup(self):
        self._dir.cleanup()


def assignment(conn, assignment_id):
    return dict(conn.execute('SELECT * FROM assignments WHERE assignment_id = ?', (assignment_id,)).fetchone())


def candidate_status(conn, candidate_id):
    return conn.execute('SELECT status FROM candidates WHERE candidate_id = ?', (candidate_id,)).fetchone()[0]


def history_count(conn, assignment_id=None):
    if assignment_id:
        return conn.execute('SELECT COUNT(*) FROM history WHERE assignment_id = ?', (assignment_id,)).fetchone()[0]
    return conn.execute('SELECT COUNT(*) FROM history').fetchone()[0]

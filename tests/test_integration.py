"""Integration checks: service layer against a real SQLite file (fresh per test)."""
import sqlite3
import threading
import unittest
import uuid
from pathlib import Path

from src import db, service
from src.service import ServiceError
from support import A, B, TOKENS, TempDB, assignment, candidate_status, history_count

CONFIRM_V1 = {'decision': 'CONFIRM', 'expected_version': 1}
REJECT_V1 = {'decision': 'REJECT', 'expected_version': 1}


def key():
    return 'k-' + uuid.uuid4().hex


class Base(unittest.TestCase):
    def setUp(self):
        self.tdb = TempDB()
        self.conn = self.tdb.connect()

    def tearDown(self):
        self.conn.close()
        self.tdb.cleanup()

    def decide(self, student, cand, body, idem=None):
        return service.decide(self.conn, student, cand, body, idem or key())


class TestAuthentication(Base):
    def test_valid_token_maps_to_student(self):
        self.assertEqual(service.authenticate(self.conn, f"Bearer {TOKENS[A]}"), A)

    def test_missing_wrong_and_revoked_tokens_are_401(self):
        for header in (None, '', 'Basic abc', 'Bearer ', 'Bearer wrong-token', 'Bearer ' + 'x' * 300):
            with self.subTest(header=header), self.assertRaises(ServiceError) as ctx:
                service.authenticate(self.conn, header)
            self.assertEqual(ctx.exception.status, 401)
        self.conn.execute('UPDATE auth_tokens SET revoked = 1 WHERE student_id = ?', (A,))
        with self.assertRaises(ServiceError):
            service.authenticate(self.conn, f"Bearer {TOKENS[A]}")

    def test_plaintext_tokens_not_stored(self):
        dump = '\n'.join(self.conn.iterdump())
        for token in TOKENS.values():
            self.assertNotIn(token, dump)


class TestNormalPath(Base):
    def test_confirm_applies_new_version_with_history(self):
        status, body, replayed = self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        self.assertEqual((status, body['status'], body['version'], replayed), (200, 'APPLIED', 2, False))
        a = assignment(self.conn, 'assignment-demo-a1')
        self.assertEqual((a['version'], a['deadline_local_iso']), (2, '2026-10-17T16:30:00+08:00'))
        self.assertEqual(candidate_status(self.conn, 'cand-a1-lms'), 'APPLIED')
        h = self.conn.execute('SELECT * FROM history').fetchall()
        self.assertEqual(len(h), 1)
        self.assertEqual((h[0]['old_version'], h[0]['new_version'], h[0]['actor_id'], h[0]['source_id']),
                         (1, 2, A, 'source-demo-lms-01'))

    def test_reject_never_mutates_deadline(self):
        status, body, _ = self.decide(A, 'cand-a1-lms', REJECT_V1)
        self.assertEqual((status, body['status']), (200, 'REJECTED'))
        a = assignment(self.conn, 'assignment-demo-a1')
        self.assertEqual((a['version'], a['deadline_local_iso']), (1, '2026-10-10T16:30:00+08:00'))
        self.assertEqual(history_count(self.conn), 0)

    def test_list_shows_only_own_assignments_and_open_changes(self):
        items = service.list_assignments(self.conn, A)
        self.assertEqual([i['assignment_id'] for i in items], ['assignment-demo-a1', 'assignment-demo-a2'])
        self.assertEqual(len(items[0]['pending_candidates']), 2)
        self.assertNotIn('assignment-demo-b1', str(items))


class TestDuplicates(Base):
    def test_same_key_same_body_is_replayed_once(self):
        k = key()
        first = self.decide(A, 'cand-a1-lms', CONFIRM_V1, k)
        second = self.decide(A, 'cand-a1-lms', CONFIRM_V1, k)
        self.assertEqual(first[:2], second[:2])
        self.assertEqual((first[2], second[2]), (False, True))
        self.assertEqual(history_count(self.conn), 1)
        self.assertEqual(assignment(self.conn, 'assignment-demo-a1')['version'], 2)

    def test_same_key_different_body_is_refused(self):
        k = key()
        self.decide(A, 'cand-a1-lms', REJECT_V1, k)
        with self.assertRaises(ServiceError) as ctx:
            self.decide(A, 'cand-a1-lms', CONFIRM_V1, k)
        self.assertEqual(ctx.exception.code, 'IDEMPOTENCY_KEY_REUSED')

    def test_new_key_after_apply_is_harmless(self):
        self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        status, body, _ = self.decide(A, 'cand-a1-lms', CONFIRM_V1)  # e.g. second browser tab
        self.assertEqual((status, body['already_applied']), (200, True))
        self.assertEqual(history_count(self.conn), 1)

    def test_keys_are_scoped_per_student(self):
        k = key()
        self.decide(A, 'cand-a1-lms', CONFIRM_V1, k)
        status, body, replayed = self.decide(B, 'cand-b1-lms', CONFIRM_V1, k)
        self.assertEqual((status, body['assignment_id'], replayed), (200, 'assignment-demo-b1', False))

    def test_concurrent_double_submit_applies_exactly_once(self):
        results, errors = [], []
        def worker():
            conn = self.tdb.connect()
            try:
                results.append(service.decide(conn, A, 'cand-a1-lms', CONFIRM_V1, key()))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                conn.close()
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(errors, [])
        self.assertEqual(sum(1 for r in results if r[1].get('already_applied') is False), 1)
        self.assertEqual(history_count(self.conn), 1)
        self.assertEqual(assignment(self.conn, 'assignment-demo-a1')['version'], 2)


class TestStaleVersions(Base):
    def test_stale_expected_version_is_409_without_change(self):
        status, body, _ = self.decide(A, 'cand-a1-lms', {'decision': 'CONFIRM', 'expected_version': 7})
        self.assertEqual((status, body['error']['code']), (409, 'STALE_VERSION'))
        self.assertEqual(assignment(self.conn, 'assignment-demo-a1')['version'], 1)
        self.assertEqual(candidate_status(self.conn, 'cand-a1-lms'), 'PENDING_REVIEW')

    def test_candidate_from_older_version_cannot_overwrite(self):
        self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        status, body, _ = self.decide(A, 'cand-a1-conflict', {'decision': 'CONFIRM', 'expected_version': 2})
        self.assertEqual((status, body['error']['code']), (409, 'CANDIDATE_OUTDATED'))
        self.assertEqual(assignment(self.conn, 'assignment-demo-a1')['deadline_local_iso'],
                         '2026-10-17T16:30:00+08:00')

    def test_outdated_candidate_can_still_be_rejected(self):
        # Regression for first-run defect: recovery advice said "Reject it" but REJECT was refused.
        self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        status, body, _ = self.decide(A, 'cand-a1-conflict', {'decision': 'REJECT', 'expected_version': 2})
        self.assertEqual((status, body['status']), (200, 'REJECTED'))
        self.assertEqual(assignment(self.conn, 'assignment-demo-a1')['version'], 2)

    def test_concurrent_conflicting_candidates_one_wins(self):
        out = {}
        def worker(cand):
            conn = self.tdb.connect()
            try:
                out[cand] = service.decide(conn, A, cand, CONFIRM_V1, key())[:2]
            finally:
                conn.close()
        ts = [threading.Thread(target=worker, args=(c,)) for c in ('cand-a1-lms', 'cand-a1-conflict')]
        for t in ts: t.start()
        for t in ts: t.join()
        statuses = sorted(v[0] for v in out.values())
        self.assertEqual(statuses, [200, 409])
        self.assertEqual(history_count(self.conn), 1)


class TestAuthorizationAndAbuse(Base):
    def test_other_students_candidate_is_404_and_untouched(self):
        with self.assertRaises(ServiceError) as ctx:
            self.decide(A, 'cand-b1-lms', CONFIRM_V1)
        self.assertEqual((ctx.exception.status, ctx.exception.code), (404, 'NOT_FOUND'))
        self.assertEqual(candidate_status(self.conn, 'cand-b1-lms'), 'PENDING_REVIEW')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM idempotency_keys').fetchone()[0], 0)

    def test_unknown_candidate_same_404_as_foreign(self):
        with self.assertRaises(ServiceError) as ctx:
            self.decide(A, 'cand-does-not-exist', CONFIRM_V1)
        self.assertEqual(ctx.exception.code, 'NOT_FOUND')

    def test_untrusted_source_cannot_be_applied(self):
        status, body, _ = self.decide(A, 'cand-a2-chat', CONFIRM_V1)
        self.assertEqual((status, body['error']['code']), (422, 'SOURCE_NOT_AUTHORIZED'))
        self.assertEqual(assignment(self.conn, 'assignment-demo-a2')['version'], 1)
        self.assertEqual(candidate_status(self.conn, 'cand-a2-chat'), 'PENDING_REVIEW')
        self.assertEqual(self.decide(A, 'cand-a2-chat', REJECT_V1)[1]['status'], 'REJECTED')

    def test_rejected_cannot_be_confirmed_later(self):
        self.decide(A, 'cand-a1-lms', REJECT_V1)
        status, body, _ = self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        self.assertEqual((status, body['error']['code']), (409, 'NOT_PENDING'))

    def test_offset_mismatch_in_stored_candidate_is_refused(self):
        self.conn.execute("UPDATE candidates SET proposed_local_iso = '2026-10-17T16:30:00+05:00' "
                          "WHERE candidate_id = 'cand-a1-lms'")
        status, body, _ = self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        self.assertEqual((status, body['error']['code']), (422, 'OFFSET_MISMATCH'))
        self.assertEqual(history_count(self.conn), 0)

    def test_export_of_foreign_assignment_is_404(self):
        with self.assertRaises(ServiceError) as ctx:
            service.export_ics(self.conn, B, 'assignment-demo-a1')
        self.assertEqual(ctx.exception.status, 404)


class TestStorageGuards(Base):
    """A2 counterexample W6 (direct mutation bypasses the rules) re-run against SQLite."""

    def test_direct_deadline_update_is_blocked(self):
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'I3_VERSION_GUARD'):
            self.conn.execute("UPDATE assignments SET deadline_local_iso = '2026-12-31T00:00:00+08:00', "
                              "version = 2 WHERE assignment_id = 'assignment-demo-a1'")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'I3_VERSION_GUARD'):
            self.conn.execute("UPDATE assignments SET deadline_local_iso = '2026-12-31T00:00:00+08:00' "
                              "WHERE assignment_id = 'assignment-demo-a1'")

    def test_owner_cannot_be_reassigned(self):
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'I1_OWNER_GUARD'):
            self.conn.execute(f"UPDATE assignments SET student_id = '{B}' WHERE assignment_id = 'assignment-demo-a1'")

    def test_illegal_candidate_transition_blocked(self):
        self.decide(A, 'cand-a1-lms', REJECT_V1)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'I4_STATE_GUARD'):
            self.conn.execute("UPDATE candidates SET status = 'APPLIED' WHERE candidate_id = 'cand-a1-lms'")

    def test_history_is_append_only(self):
        self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'HISTORY_APPEND_ONLY'):
            self.conn.execute('DELETE FROM history')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'HISTORY_APPEND_ONLY'):
            self.conn.execute("UPDATE history SET actor_id = 'someone-else'")

    def test_mid_transaction_fault_rolls_back_everything(self):
        # Fault injection: make the final candidate update fail after history+assignment were written.
        self.conn.execute("CREATE TEMP TRIGGER inject_fault BEFORE UPDATE OF status ON candidates "
                          "WHEN NEW.status = 'APPLIED' BEGIN SELECT RAISE(ABORT, 'INJECTED_FAULT'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'INJECTED_FAULT'):
            self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        self.assertFalse(self.conn.in_transaction)
        self.assertEqual(assignment(self.conn, 'assignment-demo-a1')['version'], 1)
        self.assertEqual(history_count(self.conn), 0)
        self.assertEqual(candidate_status(self.conn, 'cand-a1-lms'), 'PENDING_REVIEW')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM idempotency_keys').fetchone()[0], 0)
        # Recovery: once the fault is gone, the same user action succeeds.
        self.conn.execute('DROP TRIGGER temp.inject_fault')
        self.assertEqual(self.decide(A, 'cand-a1-lms', CONFIRM_V1)[1]['status'], 'APPLIED')


class TestRollback(Base):
    def test_compensating_revert_restores_previous_deadline(self):
        self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        hid = self.conn.execute('SELECT history_id FROM history').fetchone()[0]
        result = service.revert_change(self.conn, hid, 'operator')
        self.assertEqual((result['version'], result['deadline_local_iso']), (3, '2026-10-10T16:30:00+08:00'))
        kinds = [r[0] for r in self.conn.execute('SELECT kind FROM history ORDER BY history_id')]
        self.assertEqual(kinds, ['APPLY', 'REVERT'])
        with self.assertRaises(ServiceError) as ctx:
            service.revert_change(self.conn, hid, 'operator')
        self.assertEqual(ctx.exception.code, 'ALREADY_REVERTED')

    def test_revert_refused_if_later_change_exists(self):
        self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        first = self.conn.execute('SELECT history_id FROM history').fetchone()[0]  # v1 -> v2
        self.conn.execute("INSERT INTO candidates (candidate_id, assignment_id, source_id, proposed_local_iso, "
                          "proposed_zone, base_version, status) VALUES ('cand-x', 'assignment-demo-a1', "
                          "'source-demo-lms-01', '2026-10-24T16:30:00+08:00', 'Asia/Shanghai', 2, 'PENDING_REVIEW')")
        self.decide(A, 'cand-x', {'decision': 'CONFIRM', 'expected_version': 2})  # v2 -> v3
        with self.assertRaises(ServiceError) as ctx:
            service.revert_change(self.conn, first, 'operator')  # would silently drop the v3 change
        self.assertEqual(ctx.exception.code, 'STALE_VERSION')
        self.assertEqual(assignment(self.conn, 'assignment-demo-a1')['version'], 3)
        later = self.conn.execute("SELECT history_id FROM history WHERE candidate_id = 'cand-x'").fetchone()[0]
        reverted = service.revert_change(self.conn, later, 'operator')  # newest first: v3 -> v4
        self.assertEqual((reverted['version'], reverted['deadline_local_iso']), (4, '2026-10-17T16:30:00+08:00'))

    def test_backup_restore_round_trip(self):
        backup = Path(self.tdb.path).with_name('backup.db')
        db.backup(self.conn, backup)
        self.decide(A, 'cand-a1-lms', CONFIRM_V1)
        self.conn.close()
        db.restore(backup, self.tdb.path)
        self.conn = self.tdb.connect()
        self.assertEqual(assignment(self.conn, 'assignment-demo-a1')['version'], 1)
        self.assertEqual(history_count(self.conn), 0)

    def test_schema_down_then_up(self):
        self.assertEqual(db.migrate_down(self.conn), 0)
        tables = self.conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','trigger') "
                                   "AND name NOT LIKE 'sqlite_%'").fetchall()
        self.assertEqual(tables, [])
        self.assertEqual(db.migrate_up(self.conn), 1)


if __name__ == '__main__':
    unittest.main()

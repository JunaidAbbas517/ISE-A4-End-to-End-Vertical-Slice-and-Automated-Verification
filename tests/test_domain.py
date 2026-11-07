"""Independent boundary checks against the executable reference model."""
import hashlib
import json
import unittest
from pathlib import Path
from dataclasses import replace
from src.domain import (Assignment, EvidenceSource, DeadlineValue, ChangeCandidate,
                        Decision, DeadlineStore, DomainError, Status)

F = json.loads((Path(__file__).resolve().parents[1] / 'data/synthetic-fixtures.json').read_text())
H = hashlib.sha256(b'known-synthetic-announcement').hexdigest()


def deadline(which):
    return DeadlineValue(**F[which])


def setup(verified=True, source_kind='OFFICIAL_LMS'):
    store = DeadlineStore()
    store.add_assignment(Assignment(F['assignment_id'], F['course_id'], F['student_id'],
                                    F['assignment_title'], deadline('original_deadline')))
    store.add_source(EvidenceSource('s1', F['assignment_id'], source_kind, 'demo://notice/1', H, verified))
    store.propose(ChangeCandidate('c1', F['assignment_id'], 's1', deadline('candidate_deadline'), 1))
    return store


class TestInvariants(unittest.TestCase):
    def test_I1_requires_explicit_confirmation(self):
        s = setup()
        self.assertEqual(s.assignments[F['assignment_id']].version, 1)
        self.assertEqual(len(s.history), 0)
        self.assertEqual(s.candidates['c1'].status, Status.PENDING_REVIEW)

    def test_I1_nonowner_blocked_and_unchanged(self):
        s = setup()
        with self.assertRaisesRegex(DomainError, 'ACTOR_NOT_OWNER'):
            s.review('c1', 'other-student', Decision.CONFIRM)
        self.assertEqual(s.assignments[F['assignment_id']].version, 1)

    def test_I2_provenance_required(self):
        s = setup()
        with self.assertRaisesRegex(DomainError, 'INVALID_LINK'):
            s.propose(ChangeCandidate('c-bad', F['assignment_id'], 'missing', deadline('candidate_deadline'), 1))
        self.assertEqual(s.assignments[F['assignment_id']].version, 1)

    def test_I2_missing_provenance_identifier_rejected(self):
        s = setup()
        with self.assertRaisesRegex(DomainError, 'MISSING_PROVENANCE'):
            s.add_source(EvidenceSource('s-bad', F['assignment_id'], 'OFFICIAL_LMS', '', H, True))

    def test_I2_unverified_blocked(self):
        s = setup(verified=False)
        with self.assertRaisesRegex(DomainError, 'SOURCE_NOT_AUTHORIZED'):
            s.review('c1', F['student_id'], Decision.CONFIRM)
        self.assertEqual(s.assignments[F['assignment_id']].version, 1)
        self.assertEqual(len(s.history), 0)

    def test_I2_untrusted_kind_even_with_bad_verified_flag_is_blocked(self):
        s = setup(verified=True, source_kind='UNTRUSTED_MESSAGE')
        with self.assertRaisesRegex(DomainError, 'SOURCE_NOT_AUTHORIZED'):
            s.review('c1', F['student_id'], Decision.CONFIRM)

    def test_I3_versioned_history_and_single_current_deadline(self):
        s = setup()
        self.assertEqual(s.review('c1', F['student_id'], Decision.CONFIRM), Status.APPLIED)
        a = s.assignments[F['assignment_id']]
        self.assertEqual(a.version, 2)
        self.assertEqual(a.deadline, deadline('candidate_deadline'))
        self.assertEqual(len(s.history), 1)
        self.assertEqual((s.history[0].old_version, s.history[0].new_version), (1, 2))
        self.assertEqual(s.history[0].old_deadline, deadline('original_deadline'))

    def test_I3_replay_is_idempotent(self):
        s = setup()
        s.review('c1', F['student_id'], Decision.CONFIRM)
        events_before = len(s.events)
        self.assertEqual(s.review('c1', F['student_id'], Decision.CONFIRM), Status.APPLIED)
        self.assertEqual(s.assignments[F['assignment_id']].version, 2)
        self.assertEqual(len(s.history), 1)
        self.assertEqual(len(s.events), events_before)

    def test_I3_stale_candidate_rejected(self):
        s = setup()
        s.add_source(EvidenceSource('s2', F['assignment_id'], 'OFFICIAL_LMS', 'demo://notice/2', H, True))
        s.propose(ChangeCandidate('c2', F['assignment_id'], 's2', deadline('conflicting_deadline'), 1))
        s.review('c1', F['student_id'], Decision.CONFIRM)
        with self.assertRaisesRegex(DomainError, 'VERSION_CONFLICT'):
            s.review('c2', F['student_id'], Decision.CONFIRM)
        self.assertEqual(s.assignments[F['assignment_id']].version, 2)
        self.assertEqual(s.candidates['c2'].status, Status.PENDING_REVIEW)

    def test_I4_rejected_candidate_no_mutation(self):
        s = setup()
        self.assertEqual(s.review('c1', F['student_id'], Decision.REJECT), Status.REJECTED)
        self.assertEqual(s.assignments[F['assignment_id']].deadline, deadline('original_deadline'))
        self.assertEqual(len(s.history), 0)

    def test_I4_rejected_cannot_confirm_later(self):
        s = setup()
        s.review('c1', F['student_id'], Decision.REJECT)
        with self.assertRaisesRegex(DomainError, 'ILLEGAL_STATE'):
            s.review('c1', F['student_id'], Decision.CONFIRM)

    def test_same_deadline_marked_invalid(self):
        s = setup()
        self.assertEqual(s.propose(ChangeCandidate('c-same', F['assignment_id'], 's1', deadline('original_deadline'), 1)), Status.INVALID)
        self.assertEqual(s.candidates['c-same'].status, Status.INVALID)

    def test_naive_datetime_rejected(self):
        s = setup()
        with self.assertRaisesRegex(DomainError, 'NAIVE_DATETIME'):
            s.propose(ChangeCandidate('c-naive', F['assignment_id'], 's1', DeadlineValue('2026-10-19T10:00:00', 'Asia/Shanghai'), 1))

    def test_time_zone_offset_mismatch_rejected(self):
        s = setup()
        with self.assertRaisesRegex(DomainError, 'OFFSET_MISMATCH'):
            s.propose(ChangeCandidate('c-tz', F['assignment_id'], 's1', DeadlineValue('2026-10-19T10:00:00+00:00', 'Asia/Shanghai'), 1))

    def test_missing_assignment_reference_rejected(self):
        s = setup()
        with self.assertRaisesRegex(DomainError, 'INVALID_LINK'):
            s.propose(ChangeCandidate('c-missing', 'unknown', 's1', deadline('candidate_deadline'), 1))

    def test_legal_transition_trail(self):
        s = setup()
        s.review('c1', F['student_id'], Decision.CONFIRM)
        self.assertEqual([x.kind for x in s.events], ['CandidatePendingReview', 'DeadlineChangeApplied'])
        self.assertEqual(s.candidates['c1'].status, Status.APPLIED)

    @unittest.expectedFailure
    def test_documented_limitation_public_store_mutation(self):
        """Expected failure: raw in-memory dict is not an access-control boundary."""
        s = setup()
        original = s.assignments[F['assignment_id']]
        s.assignments[F['assignment_id']] = replace(original, deadline=deadline('candidate_deadline'), version=2)
        # This assertion should fail; unguarded Python dict access bypasses review.
        self.assertEqual(s.assignments[F['assignment_id']].version, 1)

    def test_no_raw_document_content_stored(self):
        s = setup()
        source = s.sources['s1']
        self.assertEqual(set(source.__dataclass_fields__),
                         {'source_id', 'assignment_id', 'source_kind', 'source_ref', 'content_sha256', 'authority_verified'})


if __name__ == '__main__':
    unittest.main()

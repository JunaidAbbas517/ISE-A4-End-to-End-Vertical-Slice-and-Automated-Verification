"""Unit checks: pure functions, no database or network."""
import unittest
from datetime import datetime, timezone

from src.domain import Decision
from src.ics import assignment_to_ics, escape_text
from src.server import flag_enabled
from src.service import ServiceError, sha256_hex, validate_decision_request

KEY = 'unit-test-key-0001'


class TestRequestValidation(unittest.TestCase):
    def assertCode(self, code, *args):
        with self.assertRaises(ServiceError) as ctx:
            validate_decision_request(*args)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    def test_valid_request(self):
        self.assertEqual(validate_decision_request('cand-1', {'decision': 'CONFIRM', 'expected_version': 1}, KEY),
                         (Decision.CONFIRM, 1))

    def test_missing_idempotency_key(self):
        self.assertCode('IDEMPOTENCY_KEY_REQUIRED', 'c1', {'decision': 'CONFIRM', 'expected_version': 1}, None)

    def test_idempotency_key_bounds(self):
        body = {'decision': 'CONFIRM', 'expected_version': 1}
        self.assertCode('IDEMPOTENCY_KEY_REQUIRED', 'c1', body, 'short')          # < 8 chars
        self.assertCode('IDEMPOTENCY_KEY_REQUIRED', 'c1', body, 'k' * 129)        # > 128 chars
        self.assertCode('IDEMPOTENCY_KEY_REQUIRED', 'c1', body, 'bad key; drop')  # illegal chars
        validate_decision_request('c1', body, 'k' * 8)
        validate_decision_request('c1', body, 'k' * 128)

    def test_body_must_be_exact_shape(self):
        self.assertCode('INVALID_REQUEST', 'c1', [], KEY)
        self.assertCode('INVALID_REQUEST', 'c1', {'decision': 'CONFIRM'}, KEY)
        self.assertCode('INVALID_REQUEST', 'c1', {'decision': 'CONFIRM', 'expected_version': 1, 'student_id': 'x'}, KEY)

    def test_decision_enum(self):
        self.assertCode('INVALID_DECISION', 'c1', {'decision': 'confirm', 'expected_version': 1}, KEY)
        self.assertCode('INVALID_DECISION', 'c1', {'decision': 'APPLY', 'expected_version': 1}, KEY)

    def test_version_type_and_range(self):
        for bad in (0, -1, True, '1', 1.0, None, 1_000_001):
            with self.subTest(bad=bad):
                self.assertCode('INVALID_VERSION', 'c1', {'decision': 'REJECT', 'expected_version': bad}, KEY)

    def test_candidate_id_charset(self):
        self.assertCode('NOT_FOUND', '../etc', {'decision': 'REJECT', 'expected_version': 1}, KEY)
        self.assertCode('NOT_FOUND', '', {'decision': 'REJECT', 'expected_version': 1}, KEY)


class TestIcsExport(unittest.TestCase):
    A = {'assignment_id': 'assignment-demo-a1', 'title': 'Assignment 1', 'version': 2,
         'deadline_local_iso': '2026-10-17T16:30:00+08:00', 'deadline_zone': 'Asia/Shanghai'}
    NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)

    def test_due_is_converted_to_utc(self):
        ics = assignment_to_ics(self.A, self.NOW)
        self.assertIn('DUE:20261017T083000Z\r\n', ics)
        self.assertIn('SEQUENCE:1\r\n', ics)
        self.assertIn('DTSTAMP:20261108T120000Z\r\n', ics)
        self.assertTrue(ics.startswith('BEGIN:VCALENDAR\r\n') and ics.endswith('END:VCALENDAR\r\n'))

    def test_text_escaping_prevents_property_injection(self):
        evil = dict(self.A, title='Report; final,\nEND:VTODO\nBEGIN:VEVENT')
        ics = assignment_to_ics(evil, self.NOW)
        # Oracle counts structural LINES; the escaped text may legitimately contain the substring.
        self.assertEqual(ics.split('\r\n').count('END:VTODO'), 1)
        self.assertEqual(ics.split('\r\n').count('BEGIN:VEVENT'), 0)
        self.assertIn('SUMMARY:Report\\; final\\,\\nEND:VTODO\\nBEGIN:VEVENT', ics)

    def test_escape_backslash_first(self):
        self.assertEqual(escape_text('a\\b'), 'a\\\\b')


class TestHelpers(unittest.TestCase):
    def test_flag_parsing(self):
        for on in (None, '1', 'true', 'ON', ' yes '):
            self.assertTrue(flag_enabled(on), on)
        for off in ('0', 'false', 'OFF', 'no'):
            self.assertFalse(flag_enabled(off), off)

    def test_token_hash_is_not_plaintext(self):
        h = sha256_hex('secret-token')
        self.assertEqual(len(h), 64)
        self.assertNotIn('secret', h)


if __name__ == '__main__':
    unittest.main()

"""End-to-end checks: a real HTTP server on 127.0.0.1 (ephemeral port) + real SQLite file.

These drive the same HTTP API the browser UI uses. They do NOT drive a real browser,
so JavaScript rendering is covered by the manual user task test, not by this file.
"""
import http.client
import json
import threading
import unittest
import uuid

from src.server import make_server
from support import A, B, TOKENS, TempDB


class Client:
    def __init__(self, port):
        self.port = port

    def request(self, method, path, token=None, body=None, headers=None, raw=None, conn=None):
        h = dict(headers or {})
        if token:
            h['Authorization'] = f'Bearer {token}'
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            h.setdefault('Content-Type', 'application/json')
        own = conn is None
        conn = conn or http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request(method, path, body=data, headers=h)
            res = conn.getresponse()
            payload = res.read()
            ctype = res.getheader('Content-Type', '')
            parsed = json.loads(payload) if ctype.startswith('application/json') else payload.decode()
            return res.status, parsed, dict(res.getheaders())
        finally:
            if own:
                conn.close()

    def decide(self, token, cand, decision, version, idem=None, **kw):
        return self.request('POST', f'/api/candidates/{cand}/decision', token,
                            {'decision': decision, 'expected_version': version},
                            {'Idempotency-Key': idem or 'e2e-' + uuid.uuid4().hex}, **kw)


class ServerCase(unittest.TestCase):
    decisions_enabled = True

    def setUp(self):
        self.tdb = TempDB()
        self.httpd = make_server(self.tdb.path, port=0, decisions_enabled=self.decisions_enabled, quiet=True)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.c = Client(self.httpd.server_address[1])

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tdb.cleanup()

    def assignments(self, student=A):
        status, body, _ = self.c.request('GET', '/api/assignments', TOKENS[student])
        self.assertEqual(status, 200)
        return {a['assignment_id']: a for a in body['assignments']}


class TestUserJourney(ServerCase):
    def test_ui_assets_served_with_security_headers(self):
        status, html, headers = self.c.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('Deadline Change Check', html)
        self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        for asset in ('/app.js', '/app.css'):
            self.assertEqual(self.c.request('GET', asset)[0], 200)

    def test_full_confirm_reject_export_journey(self):
        # 1. Student A sees the pending official change at version 1.
        a1 = self.assignments()['assignment-demo-a1']
        self.assertEqual(a1['version'], 1)
        self.assertEqual({c['candidate_id'] for c in a1['pending_candidates']}, {'cand-a1-lms', 'cand-a1-conflict'})
        # 2. Confirms it.
        status, body, _ = self.c.decide(TOKENS[A], 'cand-a1-lms', 'CONFIRM', 1)
        self.assertEqual((status, body['status'], body['version']), (200, 'APPLIED', 2))
        # 3. The conflicting candidate (detected against v1) is refused with recovery advice.
        status, body, _ = self.c.decide(TOKENS[A], 'cand-a1-conflict', 'CONFIRM', 2)
        self.assertEqual((status, body['error']['code']), (409, 'CANDIDATE_OUTDATED'))
        self.assertTrue(body['error']['recovery'])
        # 4. Student rejects it instead.
        self.assertEqual(self.c.decide(TOKENS[A], 'cand-a1-conflict', 'REJECT', 2)[1]['status'], 'REJECTED')
        # 5. State and history are visible.
        a1 = self.assignments()['assignment-demo-a1']
        self.assertEqual((a1['version'], a1['deadline_local_iso'], a1['pending_candidates']),
                         (2, '2026-10-17T16:30:00+08:00', []))
        self.assertEqual([h['kind'] for h in a1['history']], ['APPLY'])
        # 6. Export reflects the confirmed deadline in UTC.
        status, ics, headers = self.c.request('GET', '/api/assignments/assignment-demo-a1/calendar.ics', TOKENS[A])
        self.assertEqual(status, 200)
        self.assertTrue(headers['Content-Type'].startswith('text/calendar'))
        self.assertIn('DUE:20261017T083000Z', ics)


class TestDuplicatesAndStale(ServerCase):
    def test_retry_with_same_key_is_replayed(self):
        first = self.c.decide(TOKENS[A], 'cand-a1-lms', 'CONFIRM', 1, idem='retry-key-0001')
        second = self.c.decide(TOKENS[A], 'cand-a1-lms', 'CONFIRM', 1, idem='retry-key-0001')
        self.assertEqual(first[1], second[1])
        self.assertNotIn('Idempotent-Replayed', first[2])
        self.assertEqual(second[2].get('Idempotent-Replayed'), 'true')
        self.assertEqual(len(self.assignments()['assignment-demo-a1']['history']), 1)

    def test_parallel_double_click(self):
        results = []
        def click():
            results.append(self.c.decide(TOKENS[A], 'cand-a1-lms', 'CONFIRM', 1, idem='double-click-0001')[0])
        ts = [threading.Thread(target=click) for _ in range(5)]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertEqual(results, [200] * 5)
        self.assertEqual(len(self.assignments()['assignment-demo-a1']['history']), 1)

    def test_stale_page_gets_409_with_recovery(self):
        self.c.decide(TOKENS[A], 'cand-a1-lms', 'CONFIRM', 1)
        status, body, _ = self.c.decide(TOKENS[A], 'cand-a1-conflict', 'REJECT', 1)  # page still shows v1
        self.assertEqual((status, body['error']['code']), (409, 'STALE_VERSION'))
        self.assertIn('Reload', body['error']['recovery'])


class TestUnauthorized(ServerCase):
    def test_no_or_bad_token_is_401(self):
        for token in (None, 'not-a-real-token'):
            status, body, headers = self.c.request('GET', '/api/assignments', token)
            self.assertEqual((status, body['error']['code']), (401, 'UNAUTHENTICATED'))
            self.assertEqual(headers.get('WWW-Authenticate'), 'Bearer')
        status, _, _ = self.c.decide(None, 'cand-a1-lms', 'CONFIRM', 1)
        self.assertEqual(status, 401)

    def test_cross_student_access_is_404(self):
        status, body, _ = self.c.decide(TOKENS[B], 'cand-a1-lms', 'CONFIRM', 1)
        self.assertEqual((status, body['error']['code']), (404, 'NOT_FOUND'))
        status, _, _ = self.c.request('GET', '/api/assignments/assignment-demo-a1/calendar.ics', TOKENS[B])
        self.assertEqual(status, 404)
        self.assertNotIn('assignment-demo-a1', self.assignments(B))
        self.assertEqual(self.assignments()['assignment-demo-a1']['version'], 1)

    def test_body_cannot_choose_the_actor(self):
        status, body, _ = self.c.request('POST', '/api/candidates/cand-b1-lms/decision', TOKENS[A],
                                         {'decision': 'CONFIRM', 'expected_version': 1, 'student_id': B},
                                         {'Idempotency-Key': 'actor-spoof-0001'})
        self.assertEqual((status, body['error']['code']), (400, 'INVALID_REQUEST'))


class TestBoundaries(ServerCase):
    def test_malformed_requests(self):
        t = TOKENS[A]
        key = {'Idempotency-Key': 'boundary-key-0001'}
        cases = [
            ('oversized body', dict(raw=b'{"x":"' + b'a' * 5000 + b'"}', headers={**key, 'Content-Type': 'application/json'}), 413, 'PAYLOAD_TOO_LARGE'),
            ('wrong content type', dict(raw=b'{}', headers={**key, 'Content-Type': 'text/plain'}), 415, 'UNSUPPORTED_MEDIA_TYPE'),
            ('invalid json', dict(raw=b'{not json', headers={**key, 'Content-Type': 'application/json'}), 400, 'INVALID_JSON'),
            ('missing idempotency key', dict(body={'decision': 'CONFIRM', 'expected_version': 1}), 400, 'IDEMPOTENCY_KEY_REQUIRED'),
            ('bad decision', dict(body={'decision': 'DELETE', 'expected_version': 1}, headers=key), 400, 'INVALID_DECISION'),
        ]
        for name, kw, status, code in cases:
            with self.subTest(name):
                got_status, body, _ = self.c.request('POST', '/api/candidates/cand-a1-lms/decision', t, **kw)
                self.assertEqual((got_status, body['error']['code']), (status, code))
        self.assertEqual(self.assignments()['assignment-demo-a1']['version'], 1)

    def test_unknown_route_and_method(self):
        self.assertEqual(self.c.request('GET', '/api/nope', TOKENS[A])[0], 404)
        self.assertEqual(self.c.request('GET', '/../../etc/passwd')[0], 404)
        self.assertEqual(self.c.request('PUT', '/api/assignments', TOKENS[A])[0], 405)
        self.assertEqual(self.c.request('DELETE', '/api/assignments', TOKENS[A])[0], 405)

    def test_keep_alive_connection_survives_a_rejected_post(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.c.port, timeout=10)
        try:
            status, _, _ = self.c.decide('bad-token', 'cand-a1-lms', 'CONFIRM', 1, conn=conn)
            self.assertEqual(status, 401)
            status, body, _ = self.c.request('GET', '/api/me', TOKENS[A], conn=conn)
            self.assertEqual((status, body['student_id']), (200, A))
        finally:
            conn.close()


class TestFeatureFlagOff(ServerCase):
    decisions_enabled = False

    def test_writes_disabled_reads_still_work(self):
        status, body, _ = self.c.decide(TOKENS[A], 'cand-a1-lms', 'CONFIRM', 1)
        self.assertEqual((status, body['error']['code']), (503, 'FEATURE_DISABLED'))
        status, body, _ = self.c.request('GET', '/api/assignments', TOKENS[A])
        self.assertEqual((status, body['decisions_enabled']), (200, False))
        self.assertEqual(self.c.request('GET', '/api/assignments/assignment-demo-a1/calendar.ics', TOKENS[A])[0], 200)
        self.assertEqual(self.assignments()['assignment-demo-a1']['version'], 1)


if __name__ == '__main__':
    unittest.main()

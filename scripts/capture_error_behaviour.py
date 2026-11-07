"""Record what a user actually sees for each normal/error scenario (real server, real DB).

    python scripts/capture_error_behaviour.py

Writes evidence/error-behaviour.json and evidence/error-behaviour.md. Responses are captured,
not hand-written; tokens are redacted.
"""
from __future__ import annotations

import http.client
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from src.server import make_server  # noqa: E402
from support import TOKENS, A, B, TempDB  # noqa: E402


def call(port, method, path, token=None, body=None, key=None, raw=None, ctype='application/json'):
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if key:
        headers['Idempotency-Key'] = key
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if data is not None:
        headers['Content-Type'] = ctype
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    conn.request(method, path, body=data, headers=headers)
    res = conn.getresponse()
    text = res.read().decode()
    conn.close()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = text[:200]
    return res.status, parsed, res.getheader('Idempotent-Replayed')


def scenarios(port, decisions_enabled):
    ta, tb = TOKENS[A], TOKENS[B]
    d = '/api/candidates/{}/decision'
    if not decisions_enabled:
        return [('S13 Feature flag off (rollback level 1)', 'Student A confirms while slice disabled',
                 call(port, 'POST', d.format('cand-a1-lms'), ta, {'decision': 'CONFIRM', 'expected_version': 1}, 'flag-off-0001'))]
    return [
        ('S1 Normal: confirm official change', 'Student A confirms cand-a1-lms at v1',
         call(port, 'POST', d.format('cand-a1-lms'), ta, {'decision': 'CONFIRM', 'expected_version': 1}, 'cap-key-0001')),
        ('S2 Duplicate: network retry, same key', 'Same request re-sent with the same Idempotency-Key',
         call(port, 'POST', d.format('cand-a1-lms'), ta, {'decision': 'CONFIRM', 'expected_version': 1}, 'cap-key-0001')),
        ('S3 Duplicate: second tab, new key', 'Already-applied change confirmed again with a new key',
         call(port, 'POST', d.format('cand-a1-lms'), ta, {'decision': 'CONFIRM', 'expected_version': 1}, 'cap-key-0002')),
        ('S4 Stale page', 'Page still shows v1 while deadline is v2',
         call(port, 'POST', d.format('cand-a1-conflict'), ta, {'decision': 'CONFIRM', 'expected_version': 1}, 'cap-key-0003')),
        ('S5 Outdated candidate', 'Conflicting candidate (detected at v1) confirmed with fresh v2 page',
         call(port, 'POST', d.format('cand-a1-conflict'), ta, {'decision': 'CONFIRM', 'expected_version': 2}, 'cap-key-0004')),
        ('S6 Recovery: reject outdated candidate', 'Student follows the recovery advice',
         call(port, 'POST', d.format('cand-a1-conflict'), ta, {'decision': 'REJECT', 'expected_version': 2}, 'cap-key-0005')),
        ('S7 Abuse: unverified source', 'Student A confirms a change from an untrusted chat message',
         call(port, 'POST', d.format('cand-a2-chat'), ta, {'decision': 'CONFIRM', 'expected_version': 1}, 'cap-key-0006')),
        ('S8 Unauthorized: no token', 'Request without Authorization header',
         call(port, 'GET', '/api/assignments')),
        ('S9 Unauthorized: other student', "Student B tries to confirm Student A's change",
         call(port, 'POST', d.format('cand-a2-chat'), tb, {'decision': 'CONFIRM', 'expected_version': 1}, 'cap-key-0007')),
        ('S10 Boundary: oversized body', '5 KB body (limit 4 KB)',
         call(port, 'POST', d.format('cand-a2-chat'), ta, key='cap-key-0008', raw=b'{"a":"' + b'x' * 5000 + b'"}')),
        ('S11 Boundary: missing Idempotency-Key', 'Client omits the duplicate-protection header',
         call(port, 'POST', d.format('cand-a2-chat'), ta, {'decision': 'CONFIRM', 'expected_version': 1})),
        ('S12 Boundary: invalid decision', 'decision = "DELETE"',
         call(port, 'POST', d.format('cand-a2-chat'), ta, {'decision': 'DELETE', 'expected_version': 1}, 'cap-key-0009')),
    ]


def run(decisions_enabled):
    tdb = TempDB()
    httpd = make_server(tdb.path, port=0, decisions_enabled=decisions_enabled, quiet=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        return scenarios(httpd.server_address[1], decisions_enabled)
    finally:
        httpd.shutdown()
        httpd.server_close()
        tdb.cleanup()


def main():
    rows = run(True) + run(False)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    records = [{'scenario': s, 'action': a, 'http_status': st, 'replayed': rp, 'response': body}
               for s, a, (st, body, rp) in rows]
    (ROOT / 'evidence').mkdir(exist_ok=True)
    (ROOT / 'evidence' / 'error-behaviour.json').write_text(
        json.dumps({'captured_at': stamp, 'data': 'synthetic fixtures a4-synthetic-fixtures-v1',
                    'records': records}, indent=2), encoding='utf-8')
    md = [f'# Captured error behaviour ({stamp})', '',
          'Generated by `python scripts/capture_error_behaviour.py` against a real local server and SQLite file.',
          'Messages below are exactly what the UI banner shows (message + recovery line).', '',
          '| Scenario | Action | HTTP | Result / message shown | Recovery shown |', '|---|---|---|---|---|']
    for r in records:
        body = r['response'] if isinstance(r['response'], dict) else {}
        err = body.get('error')
        if err:
            result, recovery = f"`{err['code']}` {err['message']}", err['recovery'] or '-'
        else:
            result = f"`{body.get('status')}` {body.get('message', '')}" + (' (replayed)' if r['replayed'] else '')
            recovery = '-'
        md.append(f"| {r['scenario']} | {r['action']} | {r['http_status']} | {result} | {recovery} |")
    (ROOT / 'evidence' / 'error-behaviour.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print('\n'.join(md))


if __name__ == '__main__':
    main()

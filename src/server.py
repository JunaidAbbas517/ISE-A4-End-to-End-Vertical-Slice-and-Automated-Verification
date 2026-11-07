"""Local HTTP server for the A4 slice (Python standard library only).

Binds to 127.0.0.1 by default: nothing is exposed to the network or deployed.
Run:  python -m src.server --db local/deadlines.db
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src import db, service
from src.service import ServiceError

STATIC = Path(__file__).resolve().parent / 'static'
MAX_BODY = 4096
DECISION_PATH = re.compile(r'^/api/candidates/([^/]+)/decision$')
ICS_PATH = re.compile(r'^/api/assignments/([^/]+)/calendar\.ics$')
SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    'Cache-Control': 'no-store',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'",
}


def flag_enabled(value: str | None) -> bool:
    return (value if value is not None else '1').strip().lower() not in {'0', 'false', 'off', 'no'}


class Handler(BaseHTTPRequestHandler):
    server_version = 'ISE-A4'
    sys_version = ''
    protocol_version = 'HTTP/1.1'

    # ------------------------------------------------------------ plumbing
    def log_message(self, fmt, *args):  # replaced by structured log in _finish
        pass

    def _log(self, status: int, code: str = '', student: str = '') -> None:
        if getattr(self.server, 'quiet', False):
            return
        record = {'ts': service.utc_now(), 'method': self.command, 'path': self.path.split('?')[0],
                  'status': status, 'code': code, 'student': student,
                  'ms': round((time.perf_counter() - self._t0) * 1000, 1)}
        sys.stderr.write(json.dumps(record) + '\n')

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None,
              code: str = '', student: str = '') -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        for k, v in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)
        self._log(status, code, student)

    def _json(self, status: int, payload: dict, extra: dict | None = None, student: str = '') -> None:
        code = payload.get('error', {}).get('code', '') if isinstance(payload.get('error'), dict) else ''
        self._send(status, json.dumps(payload).encode('utf-8'), 'application/json; charset=utf-8',
                   extra, code, student)

    def _error(self, err: ServiceError, student: str = '') -> None:
        extra = {'WWW-Authenticate': 'Bearer'} if err.status == 401 else None
        self._json(err.status, err.body(), extra, student)

    def _conn(self):
        return db.connect(self.server.db_path)

    # ------------------------------------------------------------ routing
    def do_GET(self):
        self._t0 = time.perf_counter()
        path = self.path.split('?')[0]
        if path in ('/', '/index.html'):
            return self._static('index.html', 'text/html; charset=utf-8')
        if path == '/app.js':
            return self._static('app.js', 'text/javascript; charset=utf-8')
        if path == '/app.css':
            return self._static('app.css', 'text/css; charset=utf-8')
        if path == '/api/health':
            return self._json(200, {'ok': True, 'decisions_enabled': self.server.decisions_enabled})
        if path.startswith('/api/'):
            return self._authed(path)
        self._error(ServiceError(404, 'NOT_FOUND', 'No such page.'))

    def do_POST(self):
        self._t0 = time.perf_counter()
        path = self.path.split('?')[0]
        match = DECISION_PATH.match(path)
        if not match:
            self._drain()
            return self._error(ServiceError(404, 'NOT_FOUND', 'No such endpoint.'))
        raw, body_error = self._read_body()  # always consume the body first (keep-alive safety)
        conn = self._conn()
        student = ''
        try:
            student = service.authenticate(conn, self.headers.get('Authorization'))
            if not self.server.decisions_enabled:  # rollback level 1: feature flag
                raise ServiceError(503, 'FEATURE_DISABLED',
                                   'Confirming changes is temporarily switched off. Your tracked deadline is unchanged.',
                                   'Try again later; you can still view and export deadlines.')
            if body_error:
                raise body_error
            payload = self._parse_json(raw)
            status, body, replayed = service.decide(conn, student, match.group(1), payload,
                                                    self.headers.get('Idempotency-Key'))
            extra = {'Idempotent-Replayed': 'true'} if replayed else None
            self._json(status, body, extra, student)
        except ServiceError as err:
            self._error(err, student)
        except Exception as exc:  # noqa: BLE001 - never leak internals to the client
            sys.stderr.write(json.dumps({'ts': service.utc_now(), 'internal_error': repr(exc)}) + '\n')
            self._error(ServiceError(500, 'INTERNAL_ERROR', 'Something went wrong. No change was saved.',
                                     'Reload and try again.'), student)
        finally:
            conn.close()

    def do_PUT(self):
        self._method_not_allowed()

    do_DELETE = do_PATCH = do_PUT

    def _method_not_allowed(self):
        self._t0 = time.perf_counter()
        self._drain()
        self._error(ServiceError(405, 'METHOD_NOT_ALLOWED', 'Method not allowed.'))

    def _authed(self, path: str) -> None:
        conn = self._conn()
        student = ''
        try:
            student = service.authenticate(conn, self.headers.get('Authorization'))
            if path == '/api/me':
                return self._json(200, service.student_profile(conn, student), student=student)
            if path == '/api/assignments':
                return self._json(200, {'assignments': service.list_assignments(conn, student),
                                        'decisions_enabled': self.server.decisions_enabled}, student=student)
            match = ICS_PATH.match(path)
            if match:
                body = service.export_ics(conn, student, match.group(1)).encode('utf-8')
                return self._send(200, body, 'text/calendar; charset=utf-8',
                                  {'Content-Disposition': f'attachment; filename="{match.group(1)}.ics"'},
                                  student=student)
            raise ServiceError(404, 'NOT_FOUND', 'No such endpoint.')
        except ServiceError as err:
            self._error(err, student)
        finally:
            conn.close()

    # ------------------------------------------------------------ helpers
    def _static(self, name: str, ctype: str) -> None:
        self._send(200, (STATIC / name).read_bytes(), ctype)

    def _content_length(self) -> int:
        try:
            return max(0, int(self.headers.get('Content-Length', '0')))
        except ValueError:
            return -1

    def _drain(self) -> None:
        length = self._content_length()
        if 0 < length <= MAX_BODY:
            self.rfile.read(length)
        elif length != 0:
            self.close_connection = True

    def _read_body(self) -> tuple[bytes, ServiceError | None]:
        length = self._content_length()
        if length < 0:
            self.close_connection = True
            return b'', ServiceError(400, 'INVALID_REQUEST', 'Bad Content-Length header.')
        if length > MAX_BODY:
            self.close_connection = True  # never read an oversized body into memory
            return b'', ServiceError(413, 'PAYLOAD_TOO_LARGE', f'Request body exceeds {MAX_BODY} bytes.')
        return (self.rfile.read(length) if length else b''), None

    def _parse_json(self, raw: bytes) -> object:
        ctype = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        if ctype != 'application/json':
            raise ServiceError(415, 'UNSUPPORTED_MEDIA_TYPE', 'Content-Type must be application/json.')
        try:
            return json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ServiceError(400, 'INVALID_JSON', 'Request body is not valid JSON.',
                               'Reload the page and try again.') from None


def make_server(db_path: str | Path, host: str = '127.0.0.1', port: int = 8000,
                decisions_enabled: bool = True, quiet: bool = False) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    httpd.db_path = str(db_path)
    httpd.decisions_enabled = decisions_enabled
    httpd.quiet = quiet
    return httpd


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='ISE-A4 local deadline confirmation server')
    parser.add_argument('--db', default=str(db.DEFAULT_DB))
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args(argv)
    if not Path(args.db).exists():
        sys.exit(f'Database {args.db} not found. Run: python scripts/seed.py')
    enabled = flag_enabled(os.environ.get('A4_DECISIONS_ENABLED'))
    httpd = make_server(args.db, args.host, args.port, enabled)
    print(f'Serving on http://{args.host}:{httpd.server_address[1]}/  '
          f'(decisions_enabled={enabled}, db={args.db})  Ctrl+C to stop.', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()

"""Execute every rollback level from ROLLBACK.md on a throwaway database; save the transcript.

    python scripts/rollback_drill.py [--code-target <git-rev>]

Writes evidence/rollback-drill.txt. Uses local/drill/ (git-ignored); never touches local/deadlines.db.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import db, service  # noqa: E402

DRILL = ROOT / 'local' / 'drill'
DB = DRILL / 'drill.db'
log: list[str] = []


def say(text: str = '') -> None:
    print(text)
    log.append(text)


def run(*args: str, env: dict | None = None, cwd: Path = ROOT) -> int:
    say(f'$ {" ".join(args)}')
    p = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, env=env)
    for line in (p.stdout + p.stderr).rstrip().splitlines():
        say(f'  {line}')
    say(f'  [exit {p.returncode}]')
    return p.returncode


def rb(*args: str) -> int:
    return run(sys.executable, 'scripts/rollback.py', '--db', str(DB), *args)


def apply_change() -> int:
    conn = db.connect(DB)
    try:
        status, body, _ = service.decide(conn, 'student-demo-01', 'cand-a1-lms',
                                         {'decision': 'CONFIRM', 'expected_version': 1}, 'drill-key-0001')
        say(f'  user confirms cand-a1-lms -> {status} {body["status"]} v{body["version"]}')
        return conn.execute("SELECT history_id FROM history WHERE candidate_id = 'cand-a1-lms'").fetchone()[0]
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--code-target', default='HEAD~1', help='git revision to roll code back to')
    args = parser.parse_args()
    shutil.rmtree(DRILL, ignore_errors=True)
    DRILL.mkdir(parents=True)
    say(f'# ISE-A4 rollback drill {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}')
    say(f'python {sys.version.split()[0]}; db {DB.relative_to(ROOT)}')
    ok = True

    say('\n## Setup: fresh seeded database, user applies one change')
    run(sys.executable, 'scripts/seed.py', '--db', str(DB))
    rb('backup', '--out', str(DRILL / 'before-change.db'))
    hid = apply_change()

    say('\n## Level 1: feature flag off (A4_DECISIONS_ENABLED=0), server restarted')
    env = dict(os.environ, A4_DECISIONS_ENABLED='0', PYTHONUNBUFFERED='1')
    proc = subprocess.Popen([sys.executable, '-m', 'src.server', '--db', str(DB), '--port', '8765'],
                            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        health = None
        for _ in range(50):
            try:
                health = json.loads(urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=1).read())
                break
            except OSError:
                time.sleep(0.1)
        say(f'  GET /api/health -> {health}')
        ok &= bool(health) and health['decisions_enabled'] is False
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    say('\n## Level 2: compensating revert of the applied change')
    ok &= rb('revert-change', '--history-id', str(hid), '--actor', 'drill-operator') == 0
    ok &= rb('revert-change', '--history-id', str(hid), '--actor', 'drill-operator') == 1  # must refuse twice
    rb('status')

    say('\n## Level 3: restore database from backup taken before the change')
    ok &= rb('restore', '--from', str(DRILL / 'before-change.db')) == 0
    conn = db.connect(DB)
    v = conn.execute("SELECT version FROM assignments WHERE assignment_id='assignment-demo-a1'").fetchone()[0]
    hist = conn.execute('SELECT COUNT(*) FROM history').fetchone()[0]
    conn.close()
    say(f'  after restore: assignment-demo-a1 version={v}, history rows={hist}')
    ok &= (v, hist) == (1, 0)

    say('\n## Level 4: schema down (safety backup is automatic)')
    ok &= rb('schema-down') == 2  # refuses without --yes
    ok &= rb('schema-down', '--yes') == 0
    rb('status')

    say(f'\n## Level 5: code rollback target {args.code_target} builds and passes its own tests')
    rev = subprocess.run(['git', 'rev-parse', '--short', args.code_target], cwd=ROOT,
                         capture_output=True, text=True)
    if rev.returncode != 0:
        say(f'  git revision {args.code_target} not available: {rev.stderr.strip()}')
        ok = False
    else:
        archive = subprocess.run(['git', 'archive', '--format=tar', args.code_target], cwd=ROOT,
                                 capture_output=True, check=True).stdout
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(tmp, filter='data')
            say(f'  extracted {rev.stdout.strip()} to a temporary directory')
            ok &= run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', cwd=Path(tmp)) == 0

    say(f'\n# drill result: {"PASS" if ok else "FAIL"}')
    (ROOT / 'evidence').mkdir(exist_ok=True)
    (ROOT / 'evidence' / 'rollback-drill.txt').write_text('\n'.join(log) + '\n', encoding='utf-8')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

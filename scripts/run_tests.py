"""Run the full suite and keep the raw output, pass or fail, under evidence/test-runs/.

    python scripts/run_tests.py [--label note]

Every run is kept (failed runs are evidence too). Exit code mirrors the test result.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import platform
import sqlite3
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))


def git(*args: str) -> str:
    try:
        return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return 'unavailable'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='run')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out_dir = ROOT / 'evidence' / 'test-runs'
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import tzdata  # noqa: F401
        tz = tzdata.__version__
    except ImportError:
        tz = 'not installed (system tz database)'
    fixture = ROOT / 'data' / 'a4-fixtures.json'
    header = [
        f'# ISE-A4 test run {stamp} label={args.label}',
        f'git_commit: {git("rev-parse", "HEAD")}',
        f'git_dirty: {"yes" if git("status", "--porcelain") else "no"}',
        f'python: {sys.version.split()[0]} ({platform.python_implementation()})',
        f'platform: {platform.platform()}',
        f'sqlite: {sqlite3.sqlite_version}',
        f'tzdata: {tz}',
        f'fixtures: {fixture.name} sha256={hashlib.sha256(fixture.read_bytes()).hexdigest()}',
        'command: python -m unittest discover -s tests -v',
        '',
    ]
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT / 'tests'))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    outcome = 'PASS' if result.wasSuccessful() else 'FAIL'
    summary = (f'\n# summary: {outcome} ran={result.testsRun} failures={len(result.failures)} '
               f'errors={len(result.errors)} skipped={len(result.skipped)} '
               f'expected_failures={len(result.expectedFailures)} '
               f'unexpected_successes={len(result.unexpectedSuccesses)}\n')
    text = '\n'.join(header) + stream.getvalue() + summary
    path = out_dir / f'{stamp}-{args.label}-{outcome}.txt'
    path.write_text(text, encoding='utf-8')
    print(stream.getvalue() + summary)
    print(f'Raw output saved: {path.relative_to(ROOT)}')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())

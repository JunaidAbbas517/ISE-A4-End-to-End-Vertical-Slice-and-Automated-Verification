"""Create a fresh local SQLite database with synthetic fixtures and random demo tokens.

    python scripts/seed.py            # creates local/deadlines.db, refuses to overwrite
    python scripts/seed.py --reset    # deletes and recreates it

Demo tokens are printed and written to local/demo-tokens.json (git-ignored).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import db, fixtures  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=str(db.DEFAULT_DB))
    parser.add_argument('--reset', action='store_true', help='delete an existing database first')
    args = parser.parse_args()
    path = Path(args.db)
    if path.exists():
        if not args.reset:
            sys.exit(f'{path} already exists. Use --reset to recreate it.')
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(path)
    db.migrate_up(conn)
    tokens = fixtures.load(conn)
    conn.close()
    token_file = path.parent / 'demo-tokens.json'
    token_file.write_text(json.dumps(tokens, indent=2), encoding='utf-8')
    print(f'Created {path} (schema v1, fixtures {fixtures.fixture_sha256()[:12]}...)')
    print(f'Demo tokens (also in {token_file}, never commit):')
    for student, token in tokens.items():
        print(f'  {student}: {token}')


if __name__ == '__main__':
    main()

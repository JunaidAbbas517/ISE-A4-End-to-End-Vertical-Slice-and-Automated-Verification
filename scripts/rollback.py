"""Rollback tool for the A4 slice. See ROLLBACK.md for when to use each level.

    python scripts/rollback.py status
    python scripts/rollback.py backup  [--out local/backups/x.db]
    python scripts/rollback.py revert-change --history-id N [--actor operator]
    python scripts/rollback.py restore --from local/backups/x.db      (server stopped)
    python scripts/rollback.py schema-down --yes                      (backup is taken first)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import db, service  # noqa: E402


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=str(db.DEFAULT_DB))
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status')
    b = sub.add_parser('backup'); b.add_argument('--out')
    r = sub.add_parser('revert-change'); r.add_argument('--history-id', type=int, required=True)
    r.add_argument('--actor', default='operator')
    s = sub.add_parser('restore'); s.add_argument('--from', dest='src', required=True)
    d = sub.add_parser('schema-down'); d.add_argument('--yes', action='store_true')
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f'Database {db_path} not found.', file=sys.stderr)
        return 2
    conn = db.connect(db_path)
    try:
        if args.cmd == 'status':
            v = db.schema_version(conn)
            info = {'db': str(db_path), 'schema_version': v}
            if v:
                info['assignments'] = [dict(r) for r in conn.execute(
                    'SELECT assignment_id, version, deadline_local_iso FROM assignments ORDER BY 1')]
                info['history'] = [dict(r) for r in conn.execute(
                    'SELECT history_id, assignment_id, kind, old_version, new_version, reverts_history_id '
                    'FROM history ORDER BY 1')]
            print(json.dumps(info, indent=2))
        elif args.cmd == 'backup':
            out = Path(args.out) if args.out else db_path.parent / 'backups' / f'deadlines-{_stamp()}.db'
            print(f'Backup written: {db.backup(conn, out)}')
        elif args.cmd == 'revert-change':
            print(json.dumps(service.revert_change(conn, args.history_id, args.actor), indent=2))
        elif args.cmd == 'restore':
            conn.close()
            db.restore(args.src, db_path)
            print(f'Restored {db_path} from {args.src}')
        elif args.cmd == 'schema-down':
            if not args.yes:
                print('Refusing: schema-down deletes all slice data. Re-run with --yes.', file=sys.stderr)
                return 2
            out = db.backup(conn, db_path.parent / 'backups' / f'pre-schema-down-{_stamp()}.db')
            print(f'Safety backup written: {out}')
            print(f'Schema version now: {db.migrate_down(conn)}')
    except service.ServiceError as err:
        print(f'Refused: {err}', file=sys.stderr)
        return 1
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())

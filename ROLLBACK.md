# Rollback Guide

Pick the **lowest level that fixes the problem**. Levels 1–3 keep user data; level 4 removes the slice's tables; level 5 rolls back code.
All commands run from the repository root. Each level was executed in `scripts/rollback_drill.py`; the transcript is in `evidence/rollback-drill.txt`.

| Level | Use when | Data loss | Time |
|---|---|---|---|
| 1 Feature flag | Confirm/reject misbehaves; need to stop writes now | None | Restart server |
| 2 Compensating revert | One applied change was wrong | None (audit kept) | One command |
| 3 Restore backup | Data damaged by many bad writes | Writes after the backup | Server stopped |
| 4 Schema down | Remove the slice's storage completely | All slice data (backup taken first) | Server stopped |
| 5 Code rollback | The slice's code must be withdrawn | Depends on 1–4 | `git revert` |

## Before any rollback: take a backup
```bash
python scripts/rollback.py status      # versions and history, for the record
python scripts/rollback.py backup      # -> local/backups/deadlines-<UTC>.db
```

## Level 1: feature flag (writes off, reads and export on)
```bash
# PowerShell
$env:A4_DECISIONS_ENABLED = "0"; python -m src.server
# bash
A4_DECISIONS_ENABLED=0 python -m src.server
```
Check: `GET /api/health` returns `"decisions_enabled": false`. Confirm/Reject return `503 FEATURE_DISABLED` with "Your tracked deadline is unchanged"; the UI disables the buttons and shows a notice. To undo it, restart without the variable (the default is on).

## Level 2: revert one applied change (compensating entry)
```bash
python scripts/rollback.py status                         # find the APPLY history_id
python scripts/rollback.py revert-change --history-id 1 --actor <your-name>
```
This writes the old deadline back as a **new** version with a `REVERT` history row, so history stays append-only and auditable. It is refused (`exit 1`) if the change was already reverted, or if later changes exist (`STALE_VERSION`). In that case revert the newest change first. Silently overwriting later work is never allowed.

## Level 3: restore from backup (server stopped)
```bash
python scripts/rollback.py restore --from local/backups/deadlines-<UTC>.db
python scripts/rollback.py status
```
Every change made after that backup is lost. Write down what `status` showed before restoring.

## Level 4: remove the schema (server stopped)
```bash
python scripts/rollback.py schema-down --yes   # takes local/backups/pre-schema-down-<UTC>.db first
```
Without `--yes` the command refuses. To bring the slice back: `python scripts/seed.py --reset`, or restore the safety backup (level 3).

## Level 5: code rollback
```bash
git log --oneline                       # find the slice commit
git revert <slice-commit>               # new commit that undoes it; history kept
python -m unittest discover -s tests -v # baseline (A2) suite must pass: 18 tests, 1 expected failure
```
Apply level 1 first so no writes happen during the switch. The A2 baseline has no persistence, so run level 4 or archive `local/deadlines.db` as well. The drill checks the rollback target by extracting `HEAD~1` with `git archive` and running its tests.

## Not covered (residual risk)
- Exported `.ics` files already imported into someone's calendar are **not** recalled. Users must re-export after a revert. `SEQUENCE` increases with each version, so calendars that honour it will replace the old copy.
- The drill runs on synthetic data on one machine. Nothing here has been tested with concurrent live users.

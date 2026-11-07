# Peer Review Protocol

This file defines how the A4 slice is peer-reviewed. No peer-review session took place within this submission, so no reviewer findings are reported. The author's AI-assisted self-review is recorded in `AI-USE-AND-VERIFICATION.md` and is not presented as peer review.

## Review scope
The slice diff only. The A2 baseline is commit 1 and was reviewed in A2.
```bash
git diff 6625c5d 8de033c --stat
git diff 6625c5d 8de033c -- migrations/001_up.sql src/service.py src/server.py
```
Reading order: `migrations/001_up.sql` → `src/service.py` → `src/server.py` → `src/static/app.js` → `tests/`.

## Reviewer checklist
1. **Authorization:** can any request change or read another student's data? Is the actor ever taken from the request body?
2. **Duplicates:** can a double-click, retry or second tab apply a change twice?
3. **Stale versions:** can an old page overwrite a newer deadline?
4. **Atomicity:** if something fails halfway through, can the database be left half-updated?
5. **Error feedback:** does every refusal tell the user what happened and what to do next?
6. **Boundaries:** oversized, malformed or wrong-type input; time-zone/offset mismatches.
7. **Tests:** does each acceptance criterion in `TASK-CONTRACT.md` have a test that would fail if the rule were removed?
8. **Rollback:** can `ROLLBACK.md` be followed without asking the author?
9. Anything confusing, over-engineered or missing.

## Record format
Each review records:
- Reviewer (anonymised ID, with consent), role, date and time (Asia/Shanghai), commit reviewed, time spent, and medium (in person, screen share or PR comments).
- For each comment: file and line, the comment, severity (blocker, major, minor or question), the author's response, and the resolution (fixed in commit X, or not fixed with a reason).
- The reviewer's overall verdict, and any disagreement left open.

# Peer Review Record

> **Status: NOT YET CONDUCTED.** Fill this in with a real classmate's review. Do not invent reviewers or comments.
> An AI-assisted self-review is recorded separately in `AI-USE-AND-VERIFICATION.md` and does **not** count as peer review.

## What to review
The slice diff only (the A2 baseline is commit 1 and was reviewed in A2):
```bash
git diff <baseline-commit> <slice-commit> --stat
git diff <baseline-commit> <slice-commit> -- src/service.py src/server.py migrations/001_up.sql
```
Core files, in reading order: `migrations/001_up.sql` → `src/service.py` → `src/server.py` → `src/static/app.js` → `tests/`.

## Reviewer checklist (give the reviewer this list)
1. **Authorization:** can any request change or read another student's data? Is the actor ever taken from the request body?
2. **Duplicates:** can a double-click, retry or second tab apply a change twice?
3. **Stale versions:** can an old page overwrite a newer deadline?
4. **Atomicity:** if something fails halfway through, can the database be left half-updated?
5. **Error feedback:** does every refusal tell the user what happened and what to do next?
6. **Boundaries:** oversized, malformed or wrong-type input; time-zone/offset mismatches.
7. **Tests:** does each acceptance criterion in `TASK-CONTRACT.md` have a test that would fail if the rule were removed?
8. **Rollback:** could you follow `ROLLBACK.md` without asking the author?
9. Anything confusing, over-engineered or missing?

## Record

| Field | Value |
|---|---|
| Reviewer (name or anonymised ID, with consent) | |
| Role (e.g. classmate, ISE course) | |
| Date / time (Asia/Shanghai) | |
| Commit reviewed | |
| Time spent | |
| How (in person / screen share / GitHub PR comments) | |

| # | File:line | Reviewer comment (verbatim or close paraphrase) | Severity (blocker/major/minor/question) | Author response | Resolution (fixed in commit / won't fix + reason) |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

**Reviewer's overall verdict:** (approve / approve with changes / request changes)

**Disagreements kept open:** (list any comment you did not accept, with your reason; this counts as evidence too)

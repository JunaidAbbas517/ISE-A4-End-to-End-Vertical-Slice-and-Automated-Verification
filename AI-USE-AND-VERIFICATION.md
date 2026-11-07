# AI Use and Verification Log

## Tools
| Tool | Used for |
|---|---|
| Claude Code (Anthropic, model Claude Opus 5.5) in VS Code, 2026-11-08 | Proposing the slice from A1–A3 material; writing code, tests, scripts and draft documentation; running the tests and drills on the author's machine |

The author remains responsible for every file. Items marked **author to verify** below must be checked by the author before submission.

## What the AI did, and what was accepted or rejected

| # | AI suggestion / output | Decision | Reason / independent check |
|---|---|---|---|
| 1 | Choose A3 ADR-001's "confirmation endpoint + export adapter" as the slice | Accepted | Traceable to A1 scenarios, A2 invariants I1–I5 and A3 risk R1 (`TASK-CONTRACT.md`) |
| 2 | Use FastAPI/Flask + Playwright for API and browser E2E | **Rejected** | Adds dependencies and a browser download, which hurts reproducibility. Standard library `http.server` + `sqlite3` + `unittest` chosen. Cost: E2E is HTTP-level, not a real browser (limitation below) |
| 3 | Host a server | **Rejected** (author request) | Runs locally only, bound to `127.0.0.1`; nothing deployed |
| 4 | Enforce invariants only in Python | **Rejected** in favour of also adding SQLite triggers | Python-only checks repeat A2's W6 weakness; triggers checked by `TestStorageGuards` |
| 5 | Return 403 for another student's candidate | **Rejected** → 404 | 403 confirms the ID exists; 404 is used for both cases (`test_unknown_candidate_same_404_as_foreign`) |
| 6 | Cache all outcomes under the idempotency key | Partly accepted | Business outcomes (200/409/422) are cached; 401/403/404 are not, so another user's probing cannot fill the cache (`test_other_students_candidate_is_404_and_untouched` checks 0 rows) |
| 7 | First version of `_apply_decision` checked `CANDIDATE_OUTDATED` before the reject path | **AI's own bug, found by E2E test** | First run `evidence/test-runs/*first-run-FAIL.txt`: rejecting an outdated change was refused although the message told the user to reject it. Fixed; regression test `test_outdated_candidate_can_still_be_rejected` added |
| 8 | First `.ics` injection test counted `END:VTODO` substrings | **AI's test-oracle bug** | Escaped text legitimately contains the substring. Oracle changed to count whole lines. The code was correct; the test was wrong |
| 9 | First POST handler authenticated before reading the body | **AI's bug, found during self-review before any test** | An unread body on a keep-alive connection corrupts the next request. Fixed by reading (bounded) first; `test_keep_alive_connection_survives_a_rejected_post` |
| 10 | Draft peer-review and user-test results | **Rejected / not produced** | Would be fabricated. Only templates and protocol were written; results must come from real people |

## Independent verification performed
- Full suite run from the command line: first run **FAIL** (2 of 71), kept. After fixes **72 tests, all pass** (1 inherited A2 expected failure). Repeated 10 times: 10/10 OK, no flaky concurrency tests.
- Error behaviour captured from a real server, not hand-written (`evidence/error-behaviour.*`).
- Rollback levels 1–5 executed by script (`evidence/rollback-drill.txt`).
- A2 baseline reproduced unchanged before any edit (18 tests, 1 expected failure).

## Author to verify before submitting
- [ ] Read `src/service.py` and `migrations/001_up.sql` and be able to explain each check.
- [ ] Run `python scripts/run_tests.py` yourself on a clean clone.
- [ ] Open the UI yourself and go through T1–T6 in `USER-TASK-TEST.md` once.
- [ ] Peer review and user test done by real people and recorded.
- [ ] Add any further AI use (e.g. for the report text) to this table.

## Known limitations
- E2E tests drive the HTTP API, not a real browser. `app.js` is checked only through manual use.
- Demo bearer tokens are not real authentication (no expiry, no login, no TLS). Acceptable only on localhost.
- Change *detection* is not implemented; candidates are seeded fixtures.
- Concurrency was tested with threads on one machine with SQLite's single-writer lock, not under multi-process load.
- Someone who opens the SQLite file with raw SQL and drops the triggers can still bypass every guard. The triggers protect against application bugs and casual edits, not against the file owner.

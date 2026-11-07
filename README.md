# ISE-A4 | End-to-End Vertical Slice and Automated Verification

**Course:** Intelligent Software Engineering | **Due:** 2026-11-09 16:30 (Asia/Shanghai)
**Project:** Assignment Deadline Change Tracking and Verification (continues ISE-A1 → A2 → A3)

**Main report:** [report/ISE-A4-Final-Report.pdf](report/ISE-A4-Final-Report.pdf) (editable: `report/ISE-A4-Final-Report.docx`)

## The slice in one sentence
A student sees a detected deadline change and where it came from, then **confirms** it (their personal tracked deadline moves to a new version with history) or **rejects** it (nothing changes), and can export the result as an `.ics` calendar task. Everything runs **locally**: Python's built-in web server on `127.0.0.1` and a SQLite file. Nothing is deployed.

This is option B of A3's [ADR-001](https://github.com/JunaidAbbas517/ISE-A3-Repository-Investigation): a separate verification boundary plus one controlled export adapter. Full requirement trace: [TASK-CONTRACT.md](TASK-CONTRACT.md).

## Quick start (Windows, macOS or Linux; Python 3.11+)
```bash
python --version                      # recorded run: CPython 3.12.4
pip install -r requirements.txt       # Windows only: tzdata (time zones); nothing else
python scripts/seed.py                # creates local/deadlines.db and prints 2 demo tokens
python -m src.server                  # open http://127.0.0.1:8000/ and paste Student A's token
```
Stop with Ctrl+C. Start again from fresh data with `python scripts/seed.py --reset`.

## Verify (all executable top to bottom)
```bash
python scripts/run_tests.py                 # unit + integration + E2E; raw output -> evidence/test-runs/
python scripts/capture_error_behaviour.py   # real server responses -> evidence/error-behaviour.md
python scripts/rollback_drill.py            # runs rollback levels 1-5 -> evidence/rollback-drill.txt
```

| Frozen item | Value |
|---|---|
| Dependencies | Python standard library only; `tzdata==2023.3` on Windows |
| Recorded environment | CPython 3.12.4, SQLite 3.45.3, Windows 11 (each run header records its own) |
| Data | `data/a4-fixtures.json` = `a4-synthetic-fixtures-v1`, SHA-256 `b39689db3068dd41d0b7d01e9239e58ba9a22dfdd5393586a38e2bd70a5fd8ad` |
| Randomness | Tests use fixed tokens and fixed keys; no random input affects results. Demo tokens from `seed.py` are random by design and never committed |
| Line endings | `.gitattributes` forces LF so hashes match across operating systems |

## How the required work is covered

| A4 requirement | Where |
|---|---|
| Bounded slice from a traceable requirement | [TASK-CONTRACT.md](TASK-CONTRACT.md) |
| UI / API | `src/static/` (HTML+JS, strict CSP, no inline script) and `src/server.py` (JSON API) |
| Server authorization | `service.authenticate` (hashed bearer tokens) and ownership check in `service._apply_decision`. The actor always comes from the token, never from the body |
| State / data change | One `BEGIN IMMEDIATE` transaction: history row → assignment version+1 → candidate `APPLIED` → idempotency record |
| Failure feedback & recovery | Every error is `{code, message, recovery}`, shown in the UI banner with Retry / Reload latest; see `evidence/error-behaviour.md` |
| Duplicates | `Idempotency-Key` header with a stored response; an already-applied change is harmless to re-confirm |
| Stale versions | `expected_version` → `409 STALE_VERSION`; candidate from an old version → `409 CANDIDATE_OUTDATED` |
| Unauthorized access | `401` for no/bad token; `404` for other students' data |
| Boundaries | 4 KB body limit, content-type, strict JSON shape, ID charset, time-zone/offset agreement, `.ics` escaping |
| Unit / integration / E2E checks | `tests/test_unit.py`, `tests/test_integration.py` (real SQLite, threads, fault injection), `tests/test_e2e.py` (real HTTP server); `tests/test_domain.py` = unchanged A2 suite |
| Peer review | [PEER-REVIEW.md](PEER-REVIEW.md): scope, checklist and record format; no review session in this submission |
| Representative-user task test | [USER-TASK-TEST.md](USER-TASK-TEST.md): six-task protocol; not executed with participants (AC10 unverified) |
| Rollback design | [ROLLBACK.md](ROLLBACK.md) + `scripts/rollback.py` + executed drill |
| AI-use log | [AI-USE-AND-VERIFICATION.md](AI-USE-AND-VERIFICATION.md) |

## Commits (small, reviewable diff)
1. `Baseline` – A2 `src/domain.py`, tests and fixtures, byte-for-byte unchanged.
2. `Slice` – the A4 code, migration and tests. `src/domain.py` is untouched; the A4 rules call it.
3. Documentation and evidence.

Review the slice with `git diff HEAD~2 HEAD~1 --stat`.

## Negative results kept
- `evidence/test-runs/*first-run-FAIL.txt`: the first run failed 2 of 71. One was a real defect: an outdated change could not be rejected even though the error message said to reject it. The other was a wrong test oracle. Both fixed; see `AI-USE-AND-VERIFICATION.md` rows 7–8. Those first two runs were made before the slice was committed (`git_dirty: yes` in their headers).
- `tests/test_domain.py::test_documented_limitation_public_store_mutation` is still an **expected failure**. The A2 in-memory model can still be bypassed. The new SQLite triggers (`TestStorageGuards`) close that gap only for the persistent store.

## Limitations
Synthetic data only; demo tokens are not real authentication; change detection is not implemented (candidates are seeded); E2E is HTTP-level, not a real browser; single machine, single SQLite writer; the file owner can bypass triggers with raw SQL; exported `.ics` copies cannot be recalled.

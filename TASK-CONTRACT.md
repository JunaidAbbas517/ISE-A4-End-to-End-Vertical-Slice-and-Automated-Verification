# Task Contract: Confirm or Reject a Detected Deadline Change

**ID:** A4-SLICE-01 | **Owner:** the repository author | **Status:** implemented, awaiting peer review and user task test

## Requirement link (traceability)

| Source | Item | What this slice takes from it |
|---|---|---|
| ISE-A1 | Normal scenario: a deadline changes and the student must update their own record; abuse scenario: an untrusted message claims a new date | The user value: the student's own tracked deadline is updated **only** after the student confirms, with its source kept |
| ISE-A1 | Non-goals | Does not replace the LMS, edit official deadlines or submit coursework |
| ISE-A2 | Invariants I1 owner-only review, I2 verified provenance, I3 versioned history / no lost update, I4 rejection never mutates, I5 explicit time zones | Enforced server-side in `src/service.py` and, for I1/I3/I4, also as SQLite triggers in `migrations/001_up.sql` |
| ISE-A2 | Decision-table rows: apply / reject / block / safe repeat | `service._apply_decision` (order of checks documented in code) |
| ISE-A2 | Counterexample W6: direct mutation of the in-memory store bypasses the rules (kept as an expected failure) | Re-tested against SQLite: `TestStorageGuards` now blocks it at the storage layer |
| ISE-A3 | Risk R1 (no verification/stale-version boundary on direct writes); ADR-001 option "separate verification service + controlled export adapter" | This slice *is* that boundary: a confirmation endpoint plus one `.ics` VTODO export adapter |

## User story

As a student who tracks my own deadlines, when a possible deadline change has been detected, I want to see where it came from and confirm or reject it, so that my record changes only when I agree and I can export the result to my calendar.

## In scope
- Sign in with a (local, demo) bearer token.
- See my assignments, current deadline and version, pending changes with their source and whether that source is verified.
- **Confirm** → new version, history row, export updates. **Reject** → nothing changes.
- Export one assignment as an iCalendar VTODO (`.ics`).
- Clear error message and a recovery action for every refusal.

## Out of scope (non-goals)
Detecting changes from real LMS/email (candidates are seeded fixtures); real university authentication; deployment or network exposure (server binds to `127.0.0.1`); reading calendar edits back; multi-device sync; deletion workflow (retention rules stay A2 design requirements).

## Acceptance criteria → automated checks

| # | Criterion | Check(s) |
|---|---|---|
| AC1 | Owner confirms a verified pending change at the current version → `200 APPLIED`, version +1, exactly one history row with actor and source | `test_integration.TestNormalPath.test_confirm_applies_new_version_with_history`, `test_e2e.TestUserJourney.test_full_confirm_reject_export_journey` |
| AC2 | Reject → `200 REJECTED`, deadline/version/history unchanged | `test_reject_never_mutates_deadline`, `test_outdated_candidate_can_still_be_rejected` |
| AC3 | **Duplicate**: same Idempotency-Key + same body → identical stored response, no second change; same key + different body → `422`; new key on applied change → `200 already_applied`; concurrent clicks apply once | `TestDuplicates.*` (integration, 8 threads), `test_e2e.TestDuplicatesAndStale.test_parallel_double_click` |
| AC4 | **Stale version**: `expected_version` ≠ current → `409 STALE_VERSION`; candidate based on older version → `409 CANDIDATE_OUTDATED`; two conflicting confirms race → exactly one wins | `TestStaleVersions.*`, `test_stale_page_gets_409_with_recovery` |
| AC5 | **Unauthorized**: no/invalid/revoked token → `401`; another student's candidate or export → `404` (same as non-existent, no existence leak); body cannot name the actor | `TestAuthentication.*`, `TestAuthorizationAndAbuse.*`, `test_e2e.TestUnauthorized.*` |
| AC6 | **Abuse**: change from an unverified source cannot be applied (`422`) but can be rejected | `test_untrusted_source_cannot_be_applied` |
| AC7 | **Boundaries**: body > 4096 B → `413`; non-JSON content type → `415`; bad JSON / missing key / bad decision / bad version → `400`; wrong offset for zone → `422`; unknown route `404`, wrong method `405`; `.ics` text injection escaped | `test_unit.*`, `test_e2e.TestBoundaries.*`, `test_offset_mismatch_in_stored_candidate_is_refused` |
| AC8 | **Failure & recovery**: a fault mid-transaction leaves no partial state; the same action succeeds after the fault is removed; every error carries a recovery hint | `test_mid_transaction_fault_rolls_back_everything`, `evidence/error-behaviour.md` |
| AC9 | **Rollback**: feature flag disables writes but keeps reads/export; compensating revert; backup/restore; schema down/up; previous commit passes its own tests | `TestFeatureFlagOff`, `TestRollback.*`, `evidence/rollback-drill.txt` |
| AC10 | Representative users can complete the confirm and the stale-recovery tasks | **Manual**: `USER-TASK-TEST.md` (results must come from real participants) |

## Definition of done
All automated checks pass from a clean checkout (`python scripts/run_tests.py`); raw output kept in `evidence/test-runs/`; peer review recorded in `PEER-REVIEW.md` with each comment resolved or explained; user task test recorded in `USER-TASK-TEST.md`; rollback drill executed; tag `ise-a4-v1.0` pushed.

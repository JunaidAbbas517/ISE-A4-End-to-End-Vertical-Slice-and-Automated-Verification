# ISE-A4 Platform Result Summary

> DRAFT. Replace the bracketed sentence with your real peer-review and user-test results, then recheck the word count (150–300).

This assignment delivers one small, reversible slice of the deadline-change workflow from ISE-A1. It follows the boundary that the ISE-A3 ADR recommended: a student confirms or rejects a detected change to their personal tracked deadline, and can export the confirmed result as an iCalendar task. The slice runs locally on a standard-library Python server bound to 127.0.0.1, with a SQLite store. It reuses the unchanged A2 domain model.

The server authenticates hashed bearer tokens, takes the actor only from the token, and returns 404 for other students' data. Each write runs in one transaction that adds a history row, increments the version and closes the candidate. Idempotency keys make retries and double-clicks safe. An expected-version check refuses stale pages, and unverified sources cannot be applied. SQLite triggers now block the direct-mutation counterexample that A2 left open. Every refusal returns a code, a message and a recovery action.

Seventy-two unit, integration and HTTP end-to-end checks cover concurrency, fault injection, boundaries and rollback. The first run failed two checks. One was a real defect: an outdated change could not be rejected even though the error message said to reject it. The other was a faulty test oracle. Both are documented and fixed. A scripted drill executed five rollback levels, from a feature flag to a code revert.

[Peer review by N classmate(s) produced X comments, Y resolved; N participants completed tasks T1–T6 with results ….]

Limits: synthetic data, demo tokens rather than institutional authentication, seeded rather than detected candidates, and API-level rather than browser-level E2E testing.

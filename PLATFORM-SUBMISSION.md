# ISE-A4 Platform Result Summary

This assignment delivers one small, reversible slice of the deadline-change workflow from ISE-A1. It follows the boundary that the ISE-A3 ADR recommended: a student confirms or rejects a detected change to their personal tracked deadline, and can export the confirmed result as an iCalendar task. The slice runs locally on a standard-library Python server bound to 127.0.0.1, with a SQLite store. It reuses the unchanged A2 domain model.

The server authenticates hashed bearer tokens, takes the actor only from the token, and returns 404 for other students' data. Each write runs in one transaction that adds a history row, increments the version and closes the candidate. Idempotency keys make retries and double-clicks safe. An expected-version check refuses stale pages, and unverified sources cannot be applied. SQLite triggers now block the direct-mutation counterexample that A2 left open. Every refusal returns a code, a message and a recovery action.

Seventy-two unit, integration and HTTP end-to-end checks cover concurrency, fault injection, boundaries and rollback. The first run failed two checks. One was a real defect: an outdated change could not be rejected even though the error message said to reject it. The other was a faulty test oracle. Both are documented and fixed. A scripted drill executed five rollback levels, from a feature flag to a code revert.

Peer-review and representative-user task-test protocols are documented, but neither was conducted within this submission, so usability with real students remains unverified. Other limits: synthetic data, demo tokens rather than institutional authentication, seeded rather than detected candidates, and API-level rather than browser-level end-to-end testing.

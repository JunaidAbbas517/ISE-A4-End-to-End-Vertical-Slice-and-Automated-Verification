# Representative-User Task Test Protocol

This file defines the formative task test for the A4 slice. The protocol was not executed with participants within this submission, so no task times, success rates or quotes are reported, and acceptance criterion AC10 is unverified. The usability evidence available is the captured error behaviour in `evidence/error-behaviour.md`.

## Participants and ethics
- 2–3 students who track their own coursework deadlines (representative of the A1 users), excluding the author.
- Consent script, read aloud: *"This is a test of the software, not of you. It uses made-up data. I'll note the time, any errors and your comments, with no names. You can stop at any time."* A verbal yes is recorded.
- Recorded: participant code (P1, P2, …), task times, success, errors and anonymised quotes. Not recorded: names, student IDs, faces or any personal data.

## Setup per participant
```bash
python scripts/seed.py --reset          # fresh synthetic data; prints two demo tokens
python -m src.server                    # open http://127.0.0.1:8000/
```
The participant receives Student A's token and thinks aloud. The facilitator does not help unless the participant is stuck for more than 2 minutes, and records any help as an assist.

## Tasks

| Task | Instruction read to participant | Success criterion |
|---|---|---|
| T1 | "Sign in and tell me the current deadline for Assignment 1." | Says 2026-10-10 16:30 (Asia/Shanghai) |
| T2 | "The course page announced a new deadline for Assignment 1. Accept the official change." | `cand-a1-lms` confirmed; version 2 shown |
| T3 | "There's another proposed date for Assignment 1. Deal with it." | Notices it is outdated (409 message) and rejects it |
| T4 | "Assignment 2 has a proposed change from a chat message. What do you do?" | Does not apply it; notices the *UNVERIFIED* badge or refusal; rejects |
| T5 | "Put Assignment 1's deadline into your calendar." | Downloads the `.ics` |
| T6 (error recovery) | The facilitator confirms in a second tab first; the participant then acts in the old tab | Understands the stale-version message and uses *Reload latest* |

## Debrief questions
1. What was confusing?
2. Did you trust that nothing changed when you rejected?
3. Was any error message unclear?
4. Ease of use, rated 1–5 (optional).

## Stop rule and analysis
A task stops after 5 minutes or when the participant asks. Results are reported per task (success, time, assists), with observed problems ranked by severity and number of participants affected, and any code change linked to its commit. The protocol's known limits: a small convenience sample, synthetic data, and the author as facilitator (bias).

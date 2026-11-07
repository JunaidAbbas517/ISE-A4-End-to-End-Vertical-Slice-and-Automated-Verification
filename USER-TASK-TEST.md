# Representative-User Task Test

> **Status: NOT YET CONDUCTED.** Results must come from real participants (2–3 fellow students is enough for a formative test).
> Do not fill in invented participants, times or quotes. If fewer people take part than planned, report the actual number.

## Protocol (frozen before testing)

**Participants:** 2–3 students who track their own coursework deadlines (representative of A1 users). Do not use the author.
**Consent:** read aloud: *"This is a test of the software, not of you. It uses made-up data. I'll note the time, any errors and your comments, with no names. You can stop at any time."* Write down a verbal yes.
**Data recorded:** participant code (P1, P2, …), task times, success, errors, quotes. **No** names, student IDs, screenshots of faces or personal data.

**Setup per participant** (fresh data each time):
```bash
python scripts/seed.py --reset          # prints two demo tokens
python -m src.server                    # open http://127.0.0.1:8000/
```
Give them Student A's token. Think-aloud: ask them to say what they are thinking. **Do not help** unless they are stuck for more than 2 minutes (record that as an assist).

| Task | Instruction read to participant | Success criterion |
|---|---|---|
| T1 | "Sign in and tell me the current deadline for Assignment 1." | Says 2026-10-10 16:30 (Asia/Shanghai) |
| T2 | "The course page announced a new deadline for Assignment 1. Accept the official change." | `cand-a1-lms` confirmed; version 2 shown |
| T3 | "There's another proposed date for Assignment 1. Deal with it." | Notices it's outdated (409 message) and rejects it |
| T4 | "Assignment 2 has a proposed change from a chat message. What do you do?" | Does not apply it; notices the *UNVERIFIED* badge / refusal; rejects |
| T5 | "Put Assignment 1's deadline into your calendar." | Downloads the `.ics` |
| T6 (error recovery) | Facilitator opens a 2nd tab, confirms there first; participant then acts in the old tab | Understands the stale-version message and uses *Reload latest* |

**After the tasks:** ask (1) What was confusing? (2) Did you trust that nothing changed when you rejected? (3) Was any error message unclear? Optionally ask them to rate ease of use from 1 to 5.

**Stop rule:** stop a task after 5 minutes or if the participant asks to.

## Results

| Participant | T1 | T2 | T3 | T4 | T5 | T6 | Assists | Ease 1–5 |
|---|---|---|---|---|---|---|---|---|
| P1 | ✓/✗ (time) | | | | | | | |
| P2 | | | | | | | | |
| P3 | | | | | | | | |

**Observed problems** (what happened, task, how many participants, severity):
1.
2.

**Quotes** (anonymised):
-

**Changes made because of this test** (commit hash) / **problems not fixed** (and why):
-

**Limits:** small convenience sample of classmates; synthetic data; facilitator is the author (bias); local machine only.

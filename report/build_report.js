// Builds report/ISE-A4-Final-Report.docx. Run from report/:  node build_report.js
// Figures: python make_figures.py. PDF: scripts in README (Word export) or File > Save As PDF.
'use strict';
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, HeadingLevel, Footer, PageNumber, ImageRun, PageBreak, LevelFormat,
} = require('docx');

const NAVY = '1B3A57', ROW = 'F1F4F8', GRID = 'D3DAE2';
const CONTENT = 9638; // A4 width 11906 - 2 x 1134 margins (DXA)
const FONT = 'Arial';

// ---- inline markup: **bold**, `code`, [[highlight]] --------------------------------------
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[\[[^\]]+\]\])/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith('`')) out.push(new TextRun({ text: t.slice(1, -1), font: 'Consolas', size: (base.size || 20) - 1, ...base, }));
    else out.push(new TextRun({ text: t.slice(2, -2), highlight: 'yellow', ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

const p = (text, opts = {}) => new Paragraph({ children: runs(text, opts.run), spacing: { after: 120, line: 264 }, ...opts.para });
const h1 = (text, pageBreak = true) => new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: pageBreak, children: [new TextRun(text)] });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
const caption = (text) => new Paragraph({ children: runs(text, { size: 19 }), spacing: { before: 60, after: 160 } });
const bullet = (text) => new Paragraph({ numbering: { reference: 'bullets', level: 0 }, children: runs(text), spacing: { after: 60, line: 264 } });
const code = (lines) => lines.map((l, i) => new Paragraph({
  children: [new TextRun({ text: l, font: 'Consolas', size: 17 })],
  spacing: { after: i === lines.length - 1 ? 140 : 0 },
}));

function image(file, widthPx) {
  const buf = fs.readFileSync(path.join(__dirname, 'figures', file));
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20); // PNG IHDR
  return new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 },
    children: [new ImageRun({ type: 'png', data: buf, transformation: { width: widthPx, height: Math.round(widthPx * h / w) } })],
  });
}

function table(widths, header, rows) {
  const total = widths.reduce((a, b) => a + b, 0);
  if (total !== CONTENT) throw new Error(`column widths ${total} != ${CONTENT}`);
  const border = { style: BorderStyle.SINGLE, size: 4, color: GRID };
  const borders = { top: border, bottom: border, left: border, right: border };
  const cell = (text, w, isHead, shade) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders,
    shading: isHead ? { type: ShadingType.CLEAR, fill: NAVY, color: 'auto' }
      : shade ? { type: ShadingType.CLEAR, fill: ROW, color: 'auto' } : undefined,
    margins: { top: 70, bottom: 70, left: 100, right: 100 },
    children: [new Paragraph({ children: runs(text, { size: 18, color: isHead ? 'FFFFFF' : '1D2330', bold: isHead || undefined }) })],
  });
  return new Table({
    width: { size: CONTENT, type: WidthType.DXA }, columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: header.map((t, i) => cell(t, widths[i], true)) }),
      ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((t, i) => cell(t, widths[i], false, ri % 2 === 0)) })),
    ],
  });
}
const gap = () => new Paragraph({ spacing: { after: 80 }, children: [] });

// ---- content ------------------------------------------------------------------------------
const body = [
  new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun('End-to-End Vertical Slice and Automated Verification')] }),
  new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: 'ISE A4  |  Intelligent Software Engineering  |  8 November 2026', italics: true, font: 'Calibri', size: 22 })] }),
  p('Project context: Assignment Deadline Change Tracking and Verification System (continues A1, A2 and A3)'),

  h1('Purpose and principal result', false),
  p('This assignment delivers one small, complete and reversible slice of user value for the deadline-change workflow. A student sees a detected change to a tracked assignment deadline, sees where it came from, and **confirms** it (the personal tracked deadline moves to a new version with history) or **rejects** it (nothing changes). The confirmed result can be exported as an iCalendar task. This is option B of the A3 ADR-001: a separate verification boundary plus one controlled export adapter.'),
  p('The slice runs entirely on the author\'s machine: a Python standard-library HTTP server bound to 127.0.0.1 and a SQLite file. Nothing is deployed. The unchanged A2 domain model is reused. The A2 invariants are enforced in the server and, for ownership, versioning and state transitions, again as SQLite triggers. Every refusal returns a code, a message and a recovery action. Negative results are retained, including a failed first test run that exposed a real defect.'),
  h2('Slice identity and environment'),
  table([2300, 7338], ['Item', 'Recorded identity'], [
    ['Repository', 'ISE-A4 study repository; submitted at tag `ise-a4-v1.0`'],
    ['Commits', '`6625c5d` A2 baseline (byte-identical); `8de033c` A4 slice; documentation and evidence commits follow'],
    ['Runtime', 'CPython 3.12.4; SQLite 3.45.3; Windows 11 (10.0.22631); tzdata 2023.3'],
    ['Dependencies', 'Python standard library only (`sqlite3`, `http.server`, `unittest`, `zoneinfo`); `tzdata` on Windows'],
    ['Data', '`a4-synthetic-fixtures-v1`, SHA-256 b39689db3068…d8ad; derived from the A2 fixture IDs and dates'],
    ['Determinism', 'Fixed test tokens and idempotency keys; no random inputs; LF line endings enforced by .gitattributes'],
  ]),
  h2('Recorded outcomes'),
  table([2300, 2300, 5038], ['Evidence', 'Outcome', 'Interpretation'], [
    ['Automated checks', '72 checks, all pass', '12 unit, 30 integration, 12 end-to-end, 18 inherited A2 checks (1 expected failure kept)'],
    ['First test run', '2 of 71 failed', 'One product defect, one faulty test oracle; both retained and fixed'],
    ['Repeat runs', '10 of 10 OK', 'No flaky results from the threaded concurrency tests in this environment'],
    ['Error behaviour', '13 scenarios captured', 'Responses recorded from a real local server, not hand-written'],
    ['Rollback drill', 'Levels 1–5 PASS', 'Feature flag, compensating revert, restore, schema down, code rollback'],
    ['Peer review', '[[PENDING]]', '[[Protocol in PEER-REVIEW.md; insert result before submission]]'],
    ['User task test', '[[PENDING]]', '[[Protocol in USER-TASK-TEST.md; insert result before submission]]'],
  ]),
  p('All records are synthetic. No real student data, university credentials, live LMS or network deployment was used. A1 simulated pilot data remain simulated.', { para: { spacing: { before: 120, after: 120 } } }),

  // ---------------------------------------------------------------------------------------
  h1('Task contract and requirement link'),
  p('The slice was selected because it is the smallest change that delivers the A1 user value end to end and closes the A3 risk R1. The full contract, with every acceptance criterion mapped to named tests, is in TASK-CONTRACT.md.'),
  table([1300, 4000, 4338], ['Source', 'Requirement', 'Taken into the slice'], [
    ['A1', 'Normal scenario: a deadline changes and the student must update their own record', 'Tracked deadline changes only after the owner confirms; source is kept'],
    ['A1', 'Abuse scenario: an untrusted message claims a new date', 'Unverified sources cannot be applied (422) but can be rejected'],
    ['A2', 'I1 owner-only review; I2 verified provenance; I3 versioned history, no lost update; I4 rejection never mutates; I5 explicit zones', 'Enforced in `service.py`; I1, I3 and I4 also as SQLite triggers'],
    ['A2', 'Counterexample W6: direct mutation bypasses the in-memory rules', 'Re-tested on SQLite; blocked by triggers (TestStorageGuards)'],
    ['A3', 'R1: direct writes lack verification and stale-version protection; ADR-001 option B', 'Confirmation endpoint and one VTODO `.ics` export adapter'],
  ]),
  h2('User story and scope'),
  p('As a student who tracks my own deadlines, when a possible deadline change has been detected, I want to see where it came from and confirm or reject it, so that my record changes only when I agree and I can export the result to my calendar.'),
  p('**Non-goals:** detecting changes from a real LMS or email (candidates are seeded fixtures), institutional authentication, deployment, reading calendar edits back, multi-device sync, and the deletion workflow (A2 retention rules stay design requirements).'),
  h2('Acceptance criteria'),
  table([700, 5038, 3900], ['AC', 'Criterion', 'Evidence'], [
    ['1', 'Owner confirms a verified pending change: 200, version +1, one history row with actor and source', 'Integration normal path; E2E journey'],
    ['2', 'Reject: 200, deadline, version and history unchanged', 'Integration; regression test for outdated reject'],
    ['3', 'Duplicates: same key replays; same key with a different body 422; concurrent clicks apply once', 'TestDuplicates (8 threads); E2E double-click'],
    ['4', 'Stale: wrong expected_version 409; outdated candidate 409; conflicting race has one winner', 'TestStaleVersions; E2E stale page'],
    ['5', 'Unauthorized: 401 without valid token; 404 for other students\' data; actor never from body', 'TestAuthentication; E2E TestUnauthorized'],
    ['6', 'Abuse: unverified source cannot be applied', 'Integration abuse tests'],
    ['7', 'Boundaries: 413, 415, 400, 422 offset mismatch, 404/405 routes, `.ics` escaping', 'Unit tests; E2E TestBoundaries'],
    ['8', 'A mid-transaction fault leaves no partial state and the action succeeds afterwards', 'Fault-injection test; error-behaviour capture'],
    ['9', 'Rollback works at every level', 'TestRollback; TestFeatureFlagOff; rollback drill'],
    ['10', 'Representative users complete confirm and stale-recovery tasks', '[[Manual: USER-TASK-TEST.md, pending]]'],
  ]),

  // ---------------------------------------------------------------------------------------
  h1('Implementation and change boundary'),
  image('fig1-architecture.png', 560),
  caption('Figure 1. Slice components. Every rule runs in the server process; the browser only displays state and messages. The official LMS deadline stays outside this system.'),
  table([2900, 900, 5838], ['File', 'Lines', 'Role'], [
    ['migrations/001_up.sql / _down.sql', '124 / 15', '8 tables, 5 guard triggers; reversible schema'],
    ['src/service.py', '289', 'Authentication, ownership, idempotency, version checks, decision transaction, compensating revert'],
    ['src/server.py', '228', 'Local JSON API, body limit, content-type checks, security headers, feature flag, structured log'],
    ['src/static/ (html, js, css)', '249', 'Sign-in, assignment list, confirm/reject, error banner with Retry and Reload latest, export'],
    ['src/db.py, ics.py, fixtures.py', '155', 'Migrations, backup/restore, RFC 5545 export, fixture loading with hashed tokens'],
    ['src/domain.py (A2)', '0 changed', 'Reused unchanged: `parse_deadline`, `Decision`'],
  ]),
  p('The slice commit adds 2,180 lines: about 1,060 product lines (code, SQL and UI), 623 test lines and 455 lines of reproduction scripts. No existing line is changed, so a reviewer can read the slice against the baseline with `git diff 6625c5d 8de033c`. A reviewer may still find the commit large for a "small diff". Most of it is tests and SQL guards, which were judged proportional to the write-path risk.', { para: { spacing: { before: 120, after: 120 } } }),

  // ---------------------------------------------------------------------------------------
  h1('Write path: authorization, duplicates and stale versions'),
  image('fig2-write-path.png', 520),
  caption('Figure 2. Order of server-side checks for one decision request. REJECT is evaluated before the outdated-candidate check so an outdated change can always be rejected (the first test run found this ordering wrong).'),
  table([1900, 4300, 3438], ['Concern', 'Mechanism', 'Evidence'], [
    ['Server authorization', 'Bearer token hashed (SHA-256) and looked up; student taken only from the token; body shape is exact, so it cannot name an actor', '401 tests; actor-spoof E2E test; no plaintext tokens in DB dump'],
    ['Other students\' data', 'Ownership check returns 404 for both "not yours" and "does not exist"; 401/404 outcomes are never cached under an idempotency key', 'Cross-student tests: no state change, zero idempotency rows'],
    ['Duplicate requests', '`Idempotency-Key` per student; stored response replayed with header `Idempotent-Replayed`; different body with the same key gives 422', '8-thread and 5-click tests: exactly one history row'],
    ['Stale versions', '`expected_version` from the page compared inside `BEGIN IMMEDIATE`; candidate `base_version` must equal the current version', 'Concurrent conflicting confirms: one 200, one 409'],
    ['Atomic state change', 'History row, then version +1 (trigger requires the matching history row), then candidate APPLIED, then idempotency row, then COMMIT', 'Injected fault: version, history, candidate and key all unchanged'],
    ['Boundaries', '4 KB body cap read before authentication (keeps the connection usable), JSON content type, ID charset, offset must match the named zone', 'Boundary and keep-alive E2E tests'],
  ]),

  // ---------------------------------------------------------------------------------------
  h1('Automated verification'),
  p('Checks are proportional to risk: the write path and storage guards carry the most integration tests; the HTTP layer is exercised end to end; pure functions have unit tests. One command runs everything and keeps the raw output with an environment header:'),
  ...code(['python scripts/run_tests.py', 'python scripts/capture_error_behaviour.py', 'python scripts/rollback_drill.py']),
  table([1500, 2300, 900, 4938], ['Level', 'File', 'Checks', 'What it exercises'], [
    ['Unit', 'tests/test_unit.py', '12', 'Request validation bounds, `.ics` UTC conversion and injection escaping, flag parsing'],
    ['Integration', 'tests/test_integration.py', '30', 'Service on a real SQLite file: auth, duplicates, threads, stale versions, abuse, triggers, fault injection, rollback'],
    ['End to end', 'tests/test_e2e.py', '12', 'Real HTTP server on an ephemeral port: user journey, 401/404, 413/415/400/405, keep-alive, feature flag off'],
    ['Regression', 'tests/test_domain.py', '18', 'Unchanged A2 suite, including its retained expected failure'],
  ]),
  h2('Run history (all retained in evidence/test-runs)'),
  table([2800, 1500, 1500, 3838], ['Run', 'Code state', 'Result', 'Note'], [
    ['first-run', 'uncommitted', 'FAIL 2 / 71', 'Defects below'],
    ['after-fix', 'uncommitted', 'PASS 72', 'One regression test added'],
    ['clean-commit', '`8de033c`', 'PASS 72', 'Header shows git_dirty=yes because documentation was not yet committed'],
    ['10 repeated runs', '`8de033c`', '10 / 10 OK', 'Concurrency tests stable on this machine'],
  ]),
  h2('Defects found by the checks'),
  p('**Product defect (found by the E2E journey).** When a change was outdated, the error message advised "Reject it", but the server checked the outdated condition before the reject path and refused the rejection, so a user could get stuck. Rejection never mutates the deadline, so the check now applies to confirmation only. A regression test was added.'),
  p('**Test-oracle defect.** The `.ics` injection test counted the substring `END:VTODO`. The escaped title legitimately contains it on the same line. The oracle now counts whole lines. The code was correct.'),
  p('**Found in self-review before testing.** The first POST handler authenticated before reading the body. On a keep-alive connection the unread body would corrupt the next request. The body is now read (bounded) first, and a dedicated E2E test covers it.'),
  h2('What the tests do not show'),
  p('The E2E tests drive the same HTTP API the page uses, but not a real browser, so `app.js` rendering and the banner flow are verified only by manual use and the user task test. Concurrency was tested with threads against one SQLite file, not with several processes or machines. No coverage percentage is claimed.'),

  // ---------------------------------------------------------------------------------------
  h1('Usability and error-behaviour evidence'),
  p('The table is an excerpt of evidence/error-behaviour.md, generated by running each scenario against a real local server. The message and recovery columns are exactly what the UI banner shows.'),
  table([2500, 800, 3500, 2838], ['Scenario', 'HTTP', 'Message shown', 'Recovery offered'], [
    ['Confirm official change', '200', 'Deadline updated.', 'Now version 2'],
    ['Retry with the same key', '200', 'Same response, marked replayed', 'None needed'],
    ['Second tab, new key', '200', 'Already applied. Nothing was changed twice.', 'None needed'],
    ['Stale page (v1 shown, v2 current)', '409', 'Your page showed version 1, but the deadline is now version 2.', 'Reload latest, then decide again'],
    ['Outdated candidate', '409', 'Detected against an older deadline version.', 'Reject it (works since the fix)'],
    ['Unverified chat source', '422', 'Unverified source; cannot be applied.', 'Check the official course page; Reject'],
    ['No token', '401', 'Sign in with your access token.', 'Paste token and sign in'],
    ['Other student\'s change', '404', 'Change not found.', 'Reload your list'],
    ['Body over 4 KB', '413', 'Request body exceeds 4096 bytes.', '-'],
    ['Feature flag off', '503', 'Temporarily switched off. Deadline unchanged.', 'View and export still work'],
  ]),
  h2('Peer review'),
  p('[[PENDING. Protocol and checklist are fixed in PEER-REVIEW.md: reviewer, date, commit reviewed, each comment with severity, author response and resolution. Replace this paragraph with the real outcome (number of comments, what changed, any disagreement kept open).]]'),
  h2('Representative-user task test'),
  p('Protocol frozen in USER-TASK-TEST.md: 2–3 students who track their own deadlines, consent read aloud, no personal data, six tasks (T1 read deadline, T2 confirm official change, T3 handle outdated change, T4 handle unverified change, T5 export, T6 recover from a stale page), think-aloud, 5-minute stop rule.'),
  p('[[PENDING. Replace with the real results: participants, success per task, times, assists, observed problems, quotes, and any change made in response. Report the actual number of participants, even if lower than planned.]]'),

  // ---------------------------------------------------------------------------------------
  h1('Rollback design and drill'),
  p('Rollback is layered so the least destructive action is tried first. Each level was executed by `scripts/rollback_drill.py` on a throwaway database; the transcript (tokens redacted) is evidence/rollback-drill.txt.'),
  table([1800, 3700, 1700, 2438], ['Level', 'Mechanism', 'Data loss', 'Drill result'], [
    ['1 Feature flag', '`A4_DECISIONS_ENABLED=0`: writes return 503, reads and export continue, UI disables buttons', 'None', 'Health shows decisions_enabled false'],
    ['2 Compensating revert', '`rollback.py revert-change`: old deadline written back as a new version with a REVERT history row', 'None; audit kept', 'v2 to v3 restored; second revert refused (409)'],
    ['3 Restore backup', 'SQLite backup API copy taken before the change, restored with the server stopped', 'Writes after backup', 'Version 1, 0 history rows'],
    ['4 Schema down', '`001_down.sql`; refuses without `--yes`; automatic safety backup', 'All slice data (backed up)', 'Refusal exit 2; schema version 0'],
    ['5 Code rollback', '`git revert` of the slice commit; target checked by extracting HEAD~1 and running its tests', 'Per levels 1–4', 'Baseline 6625c5d: OK, 1 expected failure'],
  ]),
  p('A revert is refused if later changes exist, because rolling back an earlier change would silently discard newer work; the newest change must be reverted first. Exported `.ics` copies cannot be recalled. SEQUENCE increases with every version, so calendars that honour it replace older copies after re-export.', { para: { spacing: { before: 120, after: 120 } } }),

  // ---------------------------------------------------------------------------------------
  h1('Limits, residual risk and AI use'),
  h2('What the evidence supports'),
  p('On the recorded Windows environment, the slice confirms, rejects and exports a tracked deadline. It enforces ownership, idempotency, stale-version, provenance and time-zone rules on the server and in storage, and gives an actionable message for every refusal tested. Every rollback level was executed. This establishes a reviewable local slice, not production readiness.'),
  h2('Limits and residual risk'),
  bullet('Synthetic data only. Change detection is not implemented; candidates are seeded fixtures. The `authority_verified` flag is a fixture assumption, as in A2.'),
  bullet('Demo bearer tokens have no expiry, login flow or TLS. They are acceptable only on 127.0.0.1.'),
  bullet('E2E tests are HTTP-level, not browser-level. Usability depends on the pending user task test.'),
  bullet('Concurrency was tested with threads and SQLite\'s single-writer lock on one machine. Multi-process load was not tested.'),
  bullet('Anyone with direct access to the SQLite file can drop the triggers. The triggers protect against application bugs, not against the file owner.'),
  bullet('Linux and macOS were not executed. The code uses only portable standard-library modules, but this is untested.'),
  h2('Provenance and AI use'),
  p('Claude Code (Anthropic, Claude Opus 5.5) assisted with slice selection, code, tests, scripts, figures and drafting; all commands were executed on the author\'s machine. AI-USE-AND-VERIFICATION.md records accepted and rejected advice. Rejected: hosted deployment, extra frameworks (Flask, FastAPI, Playwright), Python-only invariant enforcement, and 403 for other students\' data. Three AI-introduced defects were caught by the tests or self-review and are retained above. No peer review or user-test result was generated by AI.'),
];

const doc = new Document({
  creator: 'ISE A4', title: 'ISE-A4 End-to-End Vertical Slice and Automated Verification',
  styles: {
    default: { document: { run: { font: FONT, size: 20 } } },
    paragraphStyles: [
      { id: 'Title', name: 'Title', basedOn: 'Normal', next: 'Normal', run: { font: 'Calibri Light', size: 44, color: '1D2330' }, paragraph: { spacing: { before: 0, after: 80 }, keepNext: true } },
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: 'Calibri', size: 28, bold: true, color: '1D2330' }, paragraph: { spacing: { before: 240, after: 120 }, keepNext: true, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: 'Calibri', size: 22, bold: true, color: '1D2330' }, paragraph: { spacing: { before: 200, after: 100 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 260 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
      new TextRun({ text: 'ISE A4  |  ', size: 16, color: '6B7F95' }), new TextRun({ children: [PageNumber.CURRENT], size: 18 })] })] }) },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, 'ISE-A4-Final-Report.docx');
  fs.writeFileSync(out, buf);
  console.log('wrote', out);
});

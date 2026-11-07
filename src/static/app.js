// ISE-A4 UI. All authorization and validation is enforced by the server;
// the browser only displays state and the server's error/recovery messages.
'use strict';

const state = { token: null, pending: null, decisionsEnabled: true };
const $ = (id) => document.getElementById(id);

function showBanner(message, recovery, { kind = 'error', retry = false, reload = false } = {}) {
  const b = $('banner');
  b.className = kind === 'success' ? 'success' : '';
  $('banner-msg').textContent = message;
  $('banner-recovery').textContent = recovery || '';
  $('banner-retry').hidden = !retry;
  $('banner-reload').hidden = !reload;
  b.hidden = false;
  b.focus?.();
}
function hideBanner() { $('banner').hidden = true; }

async function api(path, options = {}) {
  const headers = Object.assign({ Authorization: 'Bearer ' + state.token }, options.headers || {});
  const res = await fetch(path, Object.assign({}, options, { headers }));
  const isJson = (res.headers.get('Content-Type') || '').startsWith('application/json');
  const body = isJson ? await res.json() : await res.text();
  return { status: res.status, body, headers: res.headers };
}

function newKey() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');
}

async function loadAssignments() {
  let res;
  try {
    res = await api('/api/assignments');
  } catch (e) {
    return showBanner('Cannot reach the local server.', 'Check that the server is running, then press Reload latest.', { reload: true });
  }
  if (res.status === 401) { signOut(); return showBanner(res.body.error.message, res.body.error.recovery); }
  if (res.status !== 200) return showBanner(res.body.error?.message || 'Could not load.', res.body.error?.recovery, { reload: true });
  state.decisionsEnabled = res.body.decisions_enabled;
  $('flag-off').hidden = state.decisionsEnabled;
  render(res.body.assignments);
}

function render(assignments) {
  const root = $('assignments');
  root.replaceChildren();
  if (!assignments.length) { root.textContent = 'No tracked assignments.'; return; }
  for (const a of assignments) {
    const node = $('assignment-tpl').content.cloneNode(true);
    node.querySelector('.title').textContent = a.title;
    node.querySelector('.deadline').textContent = `${a.deadline_local_iso} (${a.deadline_zone})`;
    node.querySelector('.version').textContent = `version ${a.version}`;
    node.querySelector('.export').addEventListener('click', () => exportIcs(a.assignment_id));
    const list = node.querySelector('.candidates');
    if (!a.pending_candidates.length) {
      const p = document.createElement('p'); p.textContent = 'No pending changes.'; list.append(p);
    }
    for (const c of a.pending_candidates) {
      const cn = $('candidate-tpl').content.cloneNode(true);
      cn.querySelector('.proposed').textContent = `${c.proposed_local_iso} (${c.proposed_zone})`;
      cn.querySelector('.source').textContent = `${c.source.kind} - ${c.source.ref}`;
      const badge = cn.querySelector('.badge');
      badge.textContent = c.source.authority_verified ? 'verified official source' : 'UNVERIFIED source';
      badge.classList.add(c.source.authority_verified ? 'ok' : 'bad');
      const buttons = cn.querySelectorAll('button');
      buttons.forEach((btn) => { btn.disabled = !state.decisionsEnabled; });
      cn.querySelector('.confirm').addEventListener('click', (ev) => decide(c.candidate_id, 'CONFIRM', a.version, ev.target));
      cn.querySelector('.reject').addEventListener('click', (ev) => decide(c.candidate_id, 'REJECT', a.version, ev.target));
      list.append(cn);
    }
    const hist = node.querySelector('.history');
    for (const h of a.history) {
      const li = document.createElement('li');
      li.textContent = `${h.kind}: v${h.old_version} ${h.old_local_iso} -> v${h.new_version} ${h.new_local_iso} (${h.recorded_at})`;
      hist.append(li);
    }
    root.append(node);
  }
}

// One idempotency key per user intent; a retry of the SAME intent reuses it,
// so a network retry or double-click can never apply a change twice.
async function decide(candidateId, decision, expectedVersion, button) {
  if (!state.pending || state.pending.candidateId !== candidateId || state.pending.decision !== decision) {
    state.pending = { candidateId, decision, expectedVersion, key: newKey() };
  }
  const p = state.pending;
  const group = button ? button.parentElement.querySelectorAll('button') : [];
  group.forEach((b) => { b.disabled = true; });
  hideBanner();
  let res;
  try {
    res = await api(`/api/candidates/${encodeURIComponent(p.candidateId)}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': p.key },
      body: JSON.stringify({ decision: p.decision, expected_version: p.expectedVersion }),
    });
  } catch (e) {
    group.forEach((b) => { b.disabled = false; });
    return showBanner('The request did not reach the server. Your choice may or may not have been saved.',
      'Press Retry: it is safe, the same request cannot be applied twice.', { retry: true });
  }
  if (res.status === 200) {
    state.pending = null;
    showBanner(res.body.message, res.body.status === 'APPLIED' ? `Now version ${res.body.version}.` : '', { kind: 'success' });
    return loadAssignments();
  }
  if (res.status === 401) { signOut(); return showBanner(res.body.error.message, res.body.error.recovery); }
  state.pending = null;  // a definitive refusal: the next attempt is a new intent
  group.forEach((b) => { b.disabled = !state.decisionsEnabled; });
  const err = res.body.error || { message: 'Unexpected response.', recovery: 'Reload and try again.' };
  showBanner(err.message, err.recovery, { reload: [409, 404, 503, 500].includes(res.status) });
}

async function exportIcs(assignmentId) {
  let res;
  try { res = await api(`/api/assignments/${encodeURIComponent(assignmentId)}/calendar.ics`); }
  catch (e) { return showBanner('Cannot reach the local server.', 'Check that it is running.', { reload: true }); }
  if (res.status !== 200) return showBanner(res.body.error?.message || 'Export failed.', res.body.error?.recovery);
  const url = URL.createObjectURL(new Blob([res.body], { type: 'text/calendar' }));
  const a = document.createElement('a');
  a.href = url; a.download = `${assignmentId}.ics`; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function signIn(token) {
  state.token = token;
  let res;
  try { res = await api('/api/me'); }
  catch (e) { return showBanner('Cannot reach the local server.', 'Start it with: python -m src.server'); }
  if (res.status !== 200) { state.token = null; return showBanner(res.body.error.message, res.body.error.recovery); }
  hideBanner();
  $('who').textContent = `Signed in as ${res.body.display_name}`;
  $('signin').hidden = true;
  $('workspace').hidden = false;
  loadAssignments();
}

function signOut() {
  state.token = null; state.pending = null;
  $('workspace').hidden = true; $('signin').hidden = false; $('token').value = '';
}

$('signin-form').addEventListener('submit', (ev) => { ev.preventDefault(); signIn($('token').value.trim()); });
$('signout').addEventListener('click', () => { signOut(); hideBanner(); });
$('banner-close').addEventListener('click', hideBanner);
$('banner-reload').addEventListener('click', () => { hideBanner(); loadAssignments(); });
$('banner-retry').addEventListener('click', () => {
  const p = state.pending;
  if (p) decide(p.candidateId, p.decision, p.expectedVersion, null);
});

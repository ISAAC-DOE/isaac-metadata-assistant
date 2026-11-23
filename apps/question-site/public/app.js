// The question site's page. No framework and no build step: a few views drawn with DOM calls.
// Every piece of text from the server is set with textContent, never as HTML.

import { describeAnswer, pickRun, tally, standing, isStale, shortcutAllowed, CONFIDENCE, BASIS } from './logic.js';

const root = document.getElementById('main');
const toastEl = document.getElementById('toast');

const state = {
  name: null,
  site: null,
  cards: [],
  answers: {},
  view: 'loading', // 'signin' | 'home' | 'card' | 'done'
  run: null, // { ids: [card_id], index, answered: n, single: bool }
  runSize: 10,
  busy: false,
  drafts: {}, // card_id -> { typed, note }: what is typed but not saved, kept across redraws and a new sign-in
  cardError: null, // why the last save on this card failed; stays on the card until the next action
  signinMessage: null,
  resume: null, // the sitting to return to after signing in again
  loadedAt: 0,
  shortcuts: true,
};

let advanceTimer = null;
let lastRenderAt = 0;

function pref(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : v;
  } catch {
    return fallback; // private mode
  }
}
function setPref(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* fine */
  }
}
{
  const saved = Number(pref('qs_run_size', '10'));
  if ([5, 10, 15, 25].includes(saved)) state.runSize = saved;
  state.shortcuts = pref('qs_shortcuts', 'on') !== 'off';
}

// ---- small helpers ---------------------------------------------------------------------------------------------

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, String(v));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return el;
}

/** Text a person typed (a name, an answer, a note): isolated, so its direction cannot rearrange the line. */
function typedText(text, cls) {
  return h('bdi', { class: cls || null, text: String(text) });
}

let toastTimer = null;
function toast(message, bad = false) {
  toastEl.textContent = message;
  toastEl.className = `toast show${bad ? ' bad' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.className = 'toast';
  }, bad ? 6000 : 1400);
}

class ApiError extends Error {
  constructor(status, message, data) {
    super(message);
    this.status = status;
    this.data = data || null;
  }
}

async function api(path, body) {
  let res;
  try {
    res = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
    });
  } catch {
    throw new ApiError(0, 'No connection. Nothing was saved; please try again.');
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* an empty or non-JSON body */
  }
  if (!res.ok) throw new ApiError(res.status, (data && data.error) || 'Something went wrong. Please try again.', data);
  return data;
}

function day(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function card(id) {
  return state.cards.find((c) => c.card_id === id) || null;
}

function currentCardId() {
  return state.view === 'card' && state.run ? state.run.ids[state.run.index] : null;
}

/** Remember what is typed on the card on screen, before it is redrawn or left. */
function captureDraft() {
  const id = root.dataset.card;
  if (!id) return;
  const typed = document.getElementById('typed');
  const note = document.getElementById('note');
  if (!typed && !note) return;
  // only what the person changed is a draft: a card that was merely looked at must not later hide (or replace)
  // a note someone else saved on it
  const changed = (el) => Boolean(el) && el.value !== (el.dataset.prefill || '');
  if (changed(typed) || changed(note)) state.drafts[id] = { typed: typed ? typed.value : '', note: note ? note.value : '' };
  else delete state.drafts[id];
}

function cancelAdvance() {
  if (advanceTimer) {
    clearTimeout(advanceTimer);
    advanceTimer = null;
    state.busy = false;
  }
}

function show(view) {
  cancelAdvance();
  captureDraft();
  state.cardError = null;
  state.view = view;
  render({ keepFocus: false });
  window.scrollTo(0, 0);
  const heading = root.querySelector('h1');
  if (heading) {
    heading.setAttribute('tabindex', '-1');
    heading.focus({ preventScroll: true });
  }
  if (view === 'home') refresh();
}

// ---- loading and sign-in ---------------------------------------------------------------------------------------

async function load() {
  try {
    const data = await api('/api/state');
    state.name = data.name;
    state.site = data.site;
    state.cards = data.cards;
    state.answers = data.answers || {};
    state.loadedAt = Date.now();
    state.signinMessage = null;
    const back = state.resume;
    state.resume = null;
    if (back && back.ids.every((id) => card(id))) {
      state.run = back;
      state.view = 'card';
      render({ keepFocus: false });
    } else {
      state.view = 'home';
      render({ keepFocus: false });
    }
  } catch (err) {
    if (err.status === 401) {
      state.view = 'signin';
      return render({ keepFocus: false });
    }
    root.replaceChildren(
      h('div', { class: 'panel signin' }, h('h1', { class: 'title', text: 'ISAAC questions' }), h('p', { class: 'error', role: 'alert', text: err.message })),
    );
  }
}

/** Pick up answers other people saved, without disturbing what is on screen. */
async function refresh() {
  if (!state.name || state.busy || Date.now() - state.loadedAt < 30_000) return;
  state.loadedAt = Date.now();
  try {
    const data = await api('/api/state');
    if (state.busy) return;
    state.cards = data.cards;
    state.answers = data.answers || {};
    if (state.view !== 'signin') render();
  } catch (err) {
    if (err.status === 401) expired();
  }
}

/** The session ended. Go to sign-in, keeping the sitting and anything typed so nothing is lost. */
function expired(message) {
  captureDraft();
  if (state.run && state.view === 'card') state.resume = state.run;
  state.signinMessage = message || 'Please sign in again to carry on. What you typed is kept.';
  state.view = 'signin';
  render({ keepFocus: false });
}

function viewSignin() {
  const name = h('input', { class: 'input', id: 'name', name: 'name', autocomplete: 'name', required: true, maxlength: 60 });
  const password = h('input', { class: 'input', id: 'password', name: 'password', type: 'password', autocomplete: 'current-password', required: true });
  const error = h('p', { class: 'error', role: 'alert', hidden: !state.signinMessage, text: state.signinMessage || '' });
  const button = h('button', { class: 'btn btn-primary btn-wide', type: 'submit', text: 'Continue' });
  name.value = state.name || pref('qs_name', '');
  return h(
    'form',
    {
      class: 'card signin',
      onsubmit: async (ev) => {
        ev.preventDefault();
        button.disabled = true;
        error.hidden = true;
        try {
          await api('/api/login', { name: name.value, password: password.value });
          setPref('qs_name', name.value.trim());
          await load();
        } catch (err) {
          error.textContent = err.message;
          error.hidden = false;
          button.disabled = false;
          password.focus();
          password.select();
        }
      },
    },
    h('h1', { class: 'q', text: 'A few questions about your beamtime' }),
    h('p', { class: 'lead', text: 'Answer as many as you like. Every answer saves as you go, so you can stop any time.' }),
    h('label', { class: 'field' }, h('span', { text: 'Your name' }), name),
    h('label', { class: 'field' }, h('span', { text: 'Site password' }), password),
    error,
    button,
  );
}

async function signOut() {
  try {
    await api('/api/logout', {});
  } catch {
    // still signed in: say so instead of showing a sign-in page that would be untrue
    return toast('Could not sign out. Please try again.', true);
  }
  window.location.reload(); // drops everything the page held in memory
}

function topbar(where) {
  return h(
    'header',
    { class: 'topbar' },
    h('span', { class: 'brand', text: 'ISAAC' }),
    where ? h('span', { class: 'where', text: where }) : null,
    h('span', { class: 'who' }, h('span', { class: 'who-name' }, typedText(state.name), ' · '), h('button', { class: 'linklike', type: 'button', id: 'sign-out', onclick: signOut, text: 'Sign out' })),
  );
}

/** One line under the top bar: which beamtime this is, from its own files. */
function sourceLine() {
  const b = state.site.beamtime || null;
  const parts = [];
  if (b && b.read_as) parts.push(b.read_as);
  if (b && b.edges && b.edges.length) parts.push(`${b.edges.join(', ')} edge`);
  const dates = b && (b.facts || []).find((f) => f.label === 'Dates');
  if (dates) parts.push(dates.quote);
  const folder = (b && b.folder) || state.site.title;
  return h('p', { class: 'source' }, parts.length ? h('b', { text: parts.join(' · ') }) : null, h('span', { class: 'folder' }, typedText(folder)));
}

// ---- home ------------------------------------------------------------------------------------------------------

function startRun(ids, single = false) {
  if (!ids.length) return;
  state.run = { ids, index: 0, answered: 0, single };
  show('card');
}

function progressBlock(label, done, total, unsure = 0) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  const fill = h('i');
  fill.style.width = `${pct}%`;
  const aside = unsure ? ` (${unsure} marked “don’t know”)` : '';
  return h(
    'div',
    { class: 'progress' },
    h('div', { class: 'progress-line' }, h('span', {}, `${done} of ${total} ${label}${aside}`), h('span', { text: `${pct}%` })),
    h('div', { class: 'bar', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': total, 'aria-valuenow': done, 'aria-label': label }, fill),
  );
}

function viewHome() {
  const t = tally(state.cards, state.answers);
  const next = pickRun(state.cards, state.answers, state.runSize);
  const allDone = t.open === 0;
  const first = state.name.split(' ')[0];

  const size = h(
    'select',
    {
      id: 'run-size',
      onchange: (ev) => {
        state.runSize = Number(ev.target.value);
        setPref('qs_run_size', String(state.runSize));
        render();
      },
    },
    [5, 10, 15, 25].map((n) => h('option', { value: n, selected: n === state.runSize, text: String(n) })),
  );

  const headline = allDone
    ? 'Everything is answered. Thank you.'
    : t.neededOpen
      ? `${t.neededOpen} question${t.neededOpen === 1 ? '' : 's'} left before these records can be exported.`
      : 'The needed questions are all answered.';

  const hero = h(
    'section',
    { class: 'card' },
    h('h1', { class: 'hello' }, allDone ? null : ['Hi ', typedText(first), '. '], headline),
    h('p', { class: 'lead', text: 'Most answers are one click. You can stop any time and change an answer later.' }),
    t.needed ? progressBlock('needed questions answered', t.neededDone, t.needed, t.neededUnsure) : null,
    t.optional ? progressBlock('optional questions answered', t.optionalDone, t.optional) : null,
    allDone
      ? null
      : h(
          'div',
          { class: 'start' },
          h('button', { class: 'btn btn-primary', type: 'button', id: 'start', onclick: () => startRun(next), text: next.length === 1 ? 'Answer the next question' : `Answer the next ${next.length}` }),
          h('label', { for: 'run-size' }, 'Questions per sitting ', size),
        ),
  );

  const sections = [];
  const known = new Set((state.site.sections || []).map((s) => s.id));
  const order = [...(state.site.sections || []), ...[...new Set(state.cards.map((c) => c.section))].filter((id) => !known.has(id)).map((id) => ({ id, title: 'Other questions', blurb: '' }))];
  for (const section of order) {
    const cards = state.cards.filter((c) => c.section === section.id);
    if (!cards.length) continue;
    const done = cards.filter((c) => standing(c, state.answers)).length;
    sections.push(
      h('div', { class: 'section-head' }, h('h2', {}, section.title, ' ', h('span', { class: 'count', text: `${done} of ${cards.length}` })), section.blurb ? h('p', { text: section.blurb }) : null),
      h(
        'ul',
        { class: 'rows' },
        cards.map((c) => {
          const saved = state.answers[c.card_id];
          const a = standing(c, state.answers);
          const cls = !a ? 'dot' : a.action === 'dont_know' ? 'dot unsure' : 'dot done';
          let meta;
          if (a) meta = [typedText(describeAnswer(c, a), a.action === 'dont_know' ? '' : 'row-answer'), ' · ', typedText(a.by), `, ${day(a.at)}`];
          else if (saved) meta = ['The suggestion changed since it was accepted. Please look again.'];
          else meta = [c.applies_to?.summary || 'Not answered yet'];
          return h(
            'li',
            {},
            h(
              'button',
              { class: 'row', type: 'button', id: `row-${c.card_id}`, onclick: () => startRun([c.card_id], true) },
              h('span', { class: cls, 'aria-hidden': 'true' }),
              h('span', { class: 'row-title', text: c.title }),
              h('span', { class: 'row-meta' }, meta),
            ),
          );
        }),
      ),
    );
  }

  const footer = h('div', { class: 'footer' }, h('a', { href: '/api/answers', download: '', text: 'Download all answers (for the ISAAC team)' }));
  return [topbar(), sourceLine(), hero, ...sections, footer];
}

// ---- one question ----------------------------------------------------------------------------------------------

async function save(c, body, { advance = true } = {}) {
  if (state.busy) return;
  cancelAdvance();
  captureDraft();
  state.busy = true;
  state.cardError = null;
  // switch the controls off in place (no redraw), remembering where the cursor was: a disabled field loses focus
  const focusBefore = root.contains(document.activeElement) ? document.activeElement.id || null : null;
  const controls = [...root.querySelectorAll('button, input, textarea, select')];
  for (const el of controls) el.disabled = true;
  const before = state.answers[c.card_id] || null;
  try {
    const out = await api('/api/answer', { card_id: c.card_id, seen_at: before ? before.at : null, ...body });
    if (out.answer) state.answers[c.card_id] = out.answer;
    else delete state.answers[c.card_id];
    delete state.drafts[c.card_id];
    if (body.action === 'clear') {
      state.busy = false;
      toast('Answer cleared');
      return render({ focusId: focusBefore });
    }
    const run = state.run;
    if (run && !before) run.answered += 1;
    toast('Saved');
    if (!advance || !run) {
      state.busy = false;
      return render({ focusId: focusBefore });
    }
    // show the chosen answer for a moment, controls still off, then move on, unless the person moved first
    render();
    const index = run.index;
    advanceTimer = setTimeout(() => {
      advanceTimer = null;
      state.busy = false;
      if (state.view === 'card' && state.run === run && run.index === index) step(1);
      else render();
    }, 450);
  } catch (err) {
    state.busy = false;
    if (err.status === 401) return expired('Please sign in again. Your last answer was not saved; what you typed is kept.');
    if (err.status === 409 && err.data && 'answer' in err.data) {
      // someone else answered or cleared this card: show what is there, overwrite nothing
      if (err.data.answer) state.answers[c.card_id] = err.data.answer;
      else delete state.answers[c.card_id];
    }
    state.cardError = err.message;
    render({ focusId: focusBefore });
    const alert = document.getElementById('card-error');
    if (alert) alert.scrollIntoView({ block: 'nearest' });
  }
}

function step(delta) {
  cancelAdvance();
  const run = state.run;
  if (!run) return show('home');
  const nextIndex = run.index + delta;
  if (nextIndex < 0) return;
  if (nextIndex >= run.ids.length) return run.single ? show('home') : show('done');
  captureDraft();
  run.index = nextIndex;
  show('card');
}

function noteValue() {
  const el = document.getElementById('note');
  return el ? el.value : '';
}

/** Where a quote is, in plain words: "line 36", "lines 9–12", "the file name". The full locator stays in a tooltip. */
function shortLocator(locator) {
  const text = String(locator || '').trim();
  if (!text) return '';
  const lines = /^lines?\s+(\d+)(?:\s*\.\.\s*(\d+))?/i.exec(text);
  if (lines) return lines[2] && lines[2] !== lines[1] ? `lines ${lines[1]}–${lines[2]}` : `line ${lines[1]}`;
  if (/^file ?name token/i.test(text)) return 'the file name';
  return text.split(/\s[([]/)[0];
}

function quoteBlock(item, alsoIn = 0) {
  const where = shortLocator(item.locator);
  const cite = [];
  if (item.file) cite.push(h('span', { class: 'file', text: item.file }));
  if (where) cite.push(item.file ? `, ${where}` : where);
  if (alsoIn) cite.push(` · the same in ${alsoIn} more file${alsoIn === 1 ? '' : 's'}`);
  return h('blockquote', { class: 'quote' }, h('q', { text: item.quote }), cite.length ? h('cite', { title: item.locator || null }, cite) : null);
}

/** The same quoted value in several files reads as one line: "… the same in 2 more files". */
function groupedQuotes(items) {
  const groups = [];
  for (const item of items || []) {
    if (!item || !item.quote) continue;
    const g = groups.find((x) => x.item.quote === item.quote);
    if (g) g.more += 1;
    else groups.push({ item, more: 0 });
  }
  return groups;
}

/** The suggestion's reason without the confidence words the label already shows. */
function reasonText(s) {
  const label = CONFIDENCE[s.confidence];
  let text = String(s.reason || '').trim();
  if (label) text = text.replace(new RegExp(`[;,.]?\\s*${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\.?$`, 'i'), '.').trim();
  return text.replace(/\.\.$/, '.');
}

function lowerFirst(text) {
  return text ? text.charAt(0).toLowerCase() + text.slice(1) : text;
}

function moreBlock(c) {
  const out = [];
  // the detail repeats the suggestion's reason; only what it adds is shown here
  let rest = String(c.detail || '').trim();
  if (c.suggestion?.reason) rest = rest.replace(String(c.suggestion.reason).trim(), '').trim();
  rest = rest.replace(/^(Likely, please check\.|Well supported\.|A guess, please check\.)\s*/, '').trim();
  if (rest && c.suggestion) out.push(h('p', { text: rest }));
  const evidence = c.suggestion?.evidence || [];
  if (evidence.length > 1) out.push(h('h3', { text: 'All the lines behind the suggestion' }), ...groupedQuotes(evidence).map((g) => quoteBlock(g.item, g.more)));
  const breakdown = c.applies_to?.breakdown || [];
  if (breakdown.length > 1) {
    out.push(
      h('h3', { text: `What one answer covers (${c.applies_to.count})` }),
      h('div', { class: 'tablewrap', tabindex: 0, role: 'region', 'aria-label': 'What one answer covers' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', { scope: 'col', text: 'Sample' }), h('th', { scope: 'col', text: 'Measurements' }), h('th', { scope: 'col', text: 'For example' }))), h('tbody', {}, breakdown.map((b) => h('tr', {}, h('td', { text: b.label }), h('td', { text: String(b.count) }), h('td', { text: b.example || '' })))))),
    );
  } else if ((c.applies_to?.items || []).length) {
    const items = c.applies_to.items.slice(0, 10);
    const left = c.applies_to.count - items.length;
    out.push(h('h3', { text: `The measurements it covers (${c.applies_to.count})` }), h('p', { text: items.join(', ') + (left > 0 ? `, and ${left} more` : '') }));
  }
  for (const item of (c.context || []).filter(Boolean)) {
    if (item.kind === 'quotes' && item.items?.length) {
      out.push(h('h3', { text: item.label || 'From your files' }), ...item.items.map((q) => quoteBlock(q)));
    } else if (item.kind === 'values' && item.rows?.length) {
      if (breakdown.length > 1 && /one answer covers/i.test(item.label || '')) continue; // shown above
      out.push(
        h('h3', { text: item.label || 'Values' }),
        h(
          'div',
          { class: 'tablewrap', tabindex: 0, role: 'region', 'aria-label': item.label || 'Values' },
          h('table', {}, h('thead', {}, h('tr', {}, (item.columns || []).map((col) => h('th', { scope: 'col', text: col })))), h('tbody', {}, item.rows.map((row) => h('tr', {}, row.map((cell) => h('td', { text: cell === null || cell === undefined ? '' : String(cell) })))))),
        ),
        item.more ? h('p', { text: `and ${item.more} more` }) : null,
      );
    } else if (item.kind === 'image' && item.image) {
      const src = `/api/image?f=${encodeURIComponent(item.image)}`;
      out.push(
        h('h3', { text: item.label || 'Picture' }),
        h('figure', { class: 'figure' }, h('a', { href: src, target: '_blank', rel: 'noopener' }, h('img', { src, alt: item.alt || item.label || '', loading: 'lazy' })), item.alt ? h('figcaption', { text: item.alt }) : null),
      );
    }
  }
  const facts = state.site.beamtime?.facts || [];
  if (facts.length) {
    out.push(h('h3', { text: 'About this beamtime, from its logbook' }), ...facts.map((f) => quoteBlock({ quote: `${f.label}: ${f.quote}`, file: f.file, locator: f.locator })));
  }
  return out.length ? h('details', { class: 'details', id: 'more' }, h('summary', { text: 'Show the evidence and context' }), out) : null;
}

function viewCard() {
  const run = state.run;
  const c = card(run.ids[run.index]);
  if (!c) return viewHome();
  const saved = state.answers[c.card_id] || null;
  const stale = isStale(c, saved);
  const a = stale ? null : saved;
  const busy = state.busy;
  const draft = state.drafts[c.card_id] || null;
  const kind = c.answer?.kind || 'text';
  const options = c.answer?.options || [];
  const suggestion = c.suggestion || null;
  const chosen = (value) => a && a.action !== 'dont_know' && JSON.stringify(a.value) === JSON.stringify(value);
  const pick = (value, typed = false) => save(c, { action: 'value', value, typed, note: noteValue() });
  const optionButton = (o, i) =>
    h('button', { class: `btn${chosen(o.value) ? ' is-chosen' : ''}`, type: 'button', id: `opt-${i}-${String(o.value).slice(0, 40)}`, disabled: busy, 'aria-pressed': chosen(o.value) ? 'true' : 'false', onclick: () => pick(o.value), text: o.label ?? String(o.value) });

  const parts = [h('h1', { class: 'q', text: c.title })];
  if (c.applies_to?.summary) parts.push(h('p', { class: 'scope', text: `Applies to ${lowerFirst(c.applies_to.summary)}${c.blocking ? '' : ' · optional'}` }));
  if (!suggestion && c.detail) parts.push(h('p', { class: 'lead', text: c.detail }));

  if (state.cardError) parts.push(h('p', { class: 'error', role: 'alert', id: 'card-error', text: state.cardError }));

  if (a) {
    parts.push(
      h(
        'div',
        { class: `saved${a.action === 'dont_know' ? ' unsure' : ''}`, role: 'status' },
        h('strong', {}, a.action === 'dont_know' ? 'Saved as: don’t know' : ['Saved: ', typedText(describeAnswer(c, a))]),
        h('span', { class: 'who-when' }, 'by ', typedText(a.by), `, ${day(a.at)} · `, h('button', { class: 'linklike', type: 'button', id: 'clear', disabled: busy, onclick: () => save(c, { action: 'clear' }, { advance: false }), text: 'Clear' })),
        a.note ? h('span', { class: 'saved-note' }, 'Note: ', typedText(a.note)) : null,
      ),
    );
  } else if (stale) {
    parts.push(h('div', { class: 'saved unsure', role: 'status' }, h('span', {}, h('strong', { text: 'The suggested answer has changed. ' }), typedText(saved.by), ` accepted “${String(saved.value)}” on ${day(saved.at)}. Please look again.`)));
  }

  if (suggestion) {
    const accepted = a && a.action === 'accept';
    const groups = groupedQuotes(suggestion.evidence).slice(0, 1);
    const why = reasonText(suggestion);
    parts.push(
      h(
        'section',
        { class: 'suggest', 'aria-label': 'Suggested answer' },
        h('p', { class: 'label' }, 'Suggested answer', CONFIDENCE[suggestion.confidence] ? h('span', { class: 'confidence', text: ` · ${CONFIDENCE[suggestion.confidence]}` }) : null),
        h('p', { class: 'suggest-value', text: suggestion.label ?? String(suggestion.value) }),
        why ? h('p', { class: 'why', text: why }) : null,
        ...groups.map((g) => quoteBlock(g.item, g.more)),
        h(
          'button',
          { class: `btn btn-primary btn-wide${accepted ? ' is-chosen' : ''}`, type: 'button', id: 'accept', disabled: busy, onclick: () => save(c, { action: 'accept', value: suggestion.value, note: noteValue() }) },
          accepted ? 'Yes, that’s right (your answer)' : 'Yes, that’s right',
          state.shortcuts && !a ? h('span', { class: 'kbd', 'aria-hidden': 'true', text: 'Y' }) : null,
        ),
      ),
    );
  }

  const answers = [];
  if (kind === 'yes_no') {
    answers.push(h('div', { class: 'options' }, optionButton({ value: true, label: 'Yes' }, 'y'), optionButton({ value: false, label: 'No' }, 'n')));
  } else if (kind === 'choice') {
    const rest = options.filter((o) => !suggestion || JSON.stringify(o.value) !== JSON.stringify(suggestion.value));
    const common = c.answer.common?.length ? rest.filter((o) => c.answer.common.includes(o.value)) : rest.length <= 6 ? rest : [];
    const others = rest.filter((o) => !common.includes(o));
    const long = rest.some((o) => String(o.label ?? o.value).length > 28);
    if (common.length) answers.push(h('div', { class: `options${long ? ' stack' : ''}` }, common.map((o, i) => optionButton(o, `c${i}`))));
    if (others.length) {
      const openNow = !common.length || others.some((o) => chosen(o.value));
      answers.push(h('details', { class: 'more-options', open: openNow }, h('summary', { text: common.length ? `More answers (${others.length})` : `Choose from ${others.length} answers` }), h('div', { class: `options${long ? ' stack' : ''}` }, others.map((o, i) => optionButton(o, `o${i}`)))));
    }
  }
  if (kind === 'text' || kind === 'number' || (kind === 'choice' && c.answer.allow_text)) {
    const isNumber = kind === 'number';
    const input = h('input', { class: 'input', id: 'typed', type: 'text', inputmode: isNumber ? 'decimal' : null, placeholder: c.answer.placeholder || (kind === 'choice' ? 'Or type it in your own words' : 'Type your answer'), maxlength: 500, disabled: busy, 'aria-label': kind === 'choice' ? 'Type a different answer' : 'Your answer' });
    const prefill = a && a.typed && a.action === 'value' ? String(a.value) : '';
    input.dataset.prefill = prefill;
    input.value = draft ? draft.typed : prefill;
    answers.push(
      h(
        'form',
        {
          class: answers.length ? 'typed after-options' : 'typed',
          onsubmit: (ev) => {
            ev.preventDefault();
            if (!input.value.trim()) {
              input.focus();
              return toast(isNumber ? 'Please give a number first.' : 'Please type an answer first.', true);
            }
            pick(input.value, true);
          },
        },
        input,
        c.answer.unit ? h('span', { class: 'unit', text: c.answer.unit }) : null,
        h('button', { class: 'btn', type: 'submit', id: 'save-typed', disabled: busy, text: 'Save' }),
      ),
    );
  }
  if (answers.length) parts.push(h('div', { class: 'block' }, h('p', { class: 'label', text: suggestion ? 'Or a different answer' : 'Your answer' }), answers));

  const note = h('textarea', { class: 'input', id: 'note', maxlength: 2000, disabled: busy, placeholder: 'Anything the ISAAC team should know: an exception, a correction, who to ask', 'aria-label': 'A note for the ISAAC team' });
  note.dataset.prefill = a?.note || '';
  note.value = draft ? draft.note : a?.note || '';
  parts.push(
    h(
      'div',
      { class: 'quiet' },
      h('button', { class: `linklike${a && a.action === 'dont_know' ? ' is-chosen' : ''}`, type: 'button', id: 'dont-know', disabled: busy, onclick: () => save(c, { action: 'dont_know', note: noteValue() }) }, 'I don’t know', state.shortcuts && !a ? h('span', { class: 'kbd', 'aria-hidden': 'true', text: 'D' }) : null),
      h('button', { class: 'linklike', type: 'button', id: 'skip', disabled: busy, onclick: () => step(1) }, run.single ? 'Back to the list' : 'Skip for now', run.single || !state.shortcuts ? null : h('span', { class: 'kbd', 'aria-hidden': 'true', text: 'S' })),
    ),
    h(
      'details',
      { class: 'details notebox', id: 'notebox', open: Boolean(note.value) },
      h('summary', { text: a ? 'Add or change a note' : 'Add a note' }),
      note,
      a
        ? h('button', { class: 'btn', type: 'button', id: 'save-note', disabled: busy, onclick: () => save(c, { action: a.action, value: a.value, typed: a.typed, note: noteValue() }, { advance: false }), text: 'Save note' })
        : h('p', { class: 'hint', text: 'The note is saved with your answer, or with “I don’t know”.' }),
    ),
    moreBlock(c),
  );

  const where = run.single ? null : `Question ${run.index + 1} of ${run.ids.length}`;
  const pager = h(
    'nav',
    { class: 'pager', 'aria-label': 'Questions' },
    h('button', { class: 'btn', type: 'button', id: 'to-list', onclick: () => show('home'), text: 'All questions' }),
    run.single
      ? null
      : h('span', { class: 'options' }, h('button', { class: 'btn', type: 'button', id: 'prev', disabled: run.index === 0, onclick: () => step(-1), text: 'Previous' }), h('button', { class: 'btn', type: 'button', id: 'next', onclick: () => step(1), text: run.index + 1 === run.ids.length ? 'Finish' : 'Next' })),
  );

  const keys = h(
    'p',
    { class: 'keys' },
    state.shortcuts ? 'Shortcuts: Y yes, D don’t know, S skip. ' : 'Keyboard shortcuts are off. ',
    h('button', {
      class: 'linklike',
      type: 'button',
      id: 'toggle-keys',
      onclick: () => {
        state.shortcuts = !state.shortcuts;
        setPref('qs_shortcuts', state.shortcuts ? 'on' : 'off');
        render();
      },
      text: state.shortcuts ? 'Turn off' : 'Turn on',
    }),
  );

  return [topbar(where), sourceLine(), h('article', { class: 'card' }, parts), pager, keys];
}

function viewDone() {
  const run = state.run || { answered: 0 };
  const t = tally(state.cards, state.answers);
  const next = pickRun(state.cards, state.answers, state.runSize);
  const left = t.neededOpen
    ? `${t.neededOpen} needed question${t.neededOpen === 1 ? '' : 's'} left.`
    : t.open
      ? `All the needed questions are answered. ${t.open} optional question${t.open === 1 ? '' : 's'} left, only if you have time.`
      : 'Everything is answered.';
  return [
    topbar(),
    sourceLine(),
    h(
      'section',
      { class: 'card' },
      h('h1', { class: 'q', text: run.answered ? `Thank you. ${run.answered} answer${run.answered === 1 ? '' : 's'} saved.` : 'Nothing new saved this time.' }),
      h('p', { class: 'lead', text: `${left} You can stop here and come back any time.` }),
      t.needed ? progressBlock('needed questions answered', t.neededDone, t.needed, t.neededUnsure) : null,
      h(
        'div',
        { class: 'start' },
        next.length ? h('button', { class: 'btn btn-primary', type: 'button', id: 'start', onclick: () => startRun(next), text: next.length === 1 ? 'Answer one more' : `Keep going: the next ${next.length}` }) : null,
        h('button', { class: 'btn', type: 'button', id: 'to-list', onclick: () => show('home'), text: 'Back to all questions' }),
      ),
    ),
  ];
}

// ---- draw and keys ---------------------------------------------------------------------------------------------

function render({ keepFocus = true, focusId: wanted = null } = {}) {
  captureDraft();
  // remember where the cursor is, so a redraw (a failed save, a setting changed) does not drop it on the page body
  const active = document.activeElement;
  const here = keepFocus && active && active !== document.body && root.contains(active) ? active.id : null;
  const focusId = wanted || here;
  const caret = here && here === focusId && 'selectionStart' in active ? [active.selectionStart, active.selectionEnd] : null;

  let nodes;
  if (state.view === 'signin') nodes = [viewSignin()];
  else if (state.view === 'home') nodes = viewHome();
  else if (state.view === 'card') nodes = viewCard();
  else if (state.view === 'done') nodes = viewDone();
  else nodes = [h('p', { class: 'loading', role: 'status', text: 'Loading…' })];
  root.replaceChildren(...nodes.flat().filter(Boolean));
  root.dataset.card = currentCardId() || '';
  lastRenderAt = Date.now();

  if (focusId) {
    const again = document.getElementById(focusId);
    if (again && !again.disabled) {
      again.closest('details')?.setAttribute('open', '');
      again.focus({ preventScroll: true });
      if (caret && 'setSelectionRange' in again) {
        try {
          again.setSelectionRange(caret[0], caret[1]);
        } catch {
          /* not a text field */
        }
      }
    }
  }
}

document.addEventListener('keydown', (ev) => {
  if (state.view !== 'card' || ev.metaKey || ev.ctrlKey || ev.altKey) return;
  const tag = (ev.target.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
  const key = ev.key.toLowerCase();
  const id = { y: 'accept', d: 'dont-know', s: 'skip' }[key];
  if (!id) return;
  const c = card(currentCardId());
  const allowed = shortcutAllowed({
    key,
    enabled: state.shortcuts,
    busy: state.busy,
    msSinceRender: Date.now() - lastRenderAt,
    typedText: document.getElementById('typed')?.value,
    noteText: key === 's' ? '' : noteValue(),
    hasAnswer: Boolean(c && standing(c, state.answers)),
  });
  if (!allowed) return;
  const el = document.getElementById(id);
  if (el && !el.disabled) {
    ev.preventDefault();
    el.click();
  }
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') refresh();
});

load();

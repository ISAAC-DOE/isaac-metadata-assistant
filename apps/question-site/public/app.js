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
  state.drafts[id] = { typed: typed ? typed.value : '', note: note ? note.value : '' };
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
      class: 'panel signin',
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
    h('p', { class: 'brand', text: 'ISAAC' }),
    h('h1', { class: 'title', text: 'A few questions about your beamtime' }),
    h('p', { class: 'subtitle', text: 'Answer as many as you like, whenever you have a few minutes. Every answer saves as you go.' }),
    h('label', { class: 'field' }, h('span', { text: 'Your name' }), name),
    h('label', { class: 'field' }, h('span', { text: 'Site password' }), password),
    error,
    h('div', { class: 'field' }, button),
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

function topbar() {
  return h(
    'div',
    { class: 'topbar' },
    h('span', { class: 'brand', text: 'ISAAC questions' }),
    h('span', { class: 'who' }, 'Signed in as ', typedText(state.name), ' · ', h('button', { class: 'linklike', type: 'button', id: 'sign-out', onclick: signOut, text: 'Sign out' })),
  );
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
    h('div', { class: 'progress-line' }, h('span', {}, h('strong', { text: `${done} of ${total}` }), ` ${label}${aside}`), h('span', { text: `${pct}%` })),
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
    { class: 'panel' },
    h('h1', { class: 'title' }, allDone ? null : ['Hello ', typedText(first), '. '], headline),
    h('p', { class: 'beamtime', text: state.site.title }),
    t.needed ? progressBlock('needed questions done', t.neededDone, t.needed, t.neededUnsure) : null,
    t.optional ? progressBlock('nice-to-have questions done', t.optionalDone, t.optional) : null,
    allDone
      ? null
      : h(
          'div',
          { class: 'start' },
          h('button', { class: 'btn btn-primary', type: 'button', id: 'start', onclick: () => startRun(next), text: next.length === 1 ? 'Answer the next question' : `Answer the next ${next.length}` }),
          h('label', { for: 'run-size' }, 'Questions per sitting: ', size),
        ),
    h('p', { class: 'note-small', text: 'Most answers are one click. Every answer saves as you go, so you can stop any time and come back later. You can change an answer whenever you like.' }),
  );

  const sections = [];
  const known = new Set((state.site.sections || []).map((s) => s.id));
  const order = [...(state.site.sections || []), ...[...new Set(state.cards.map((c) => c.section))].filter((id) => !known.has(id)).map((id) => ({ id, title: 'Other questions', blurb: '' }))];
  for (const section of order) {
    const cards = state.cards.filter((c) => c.section === section.id);
    if (!cards.length) continue;
    const done = cards.filter((c) => standing(c, state.answers)).length;
    sections.push(
      h('div', { class: 'section-head' }, h('h2', { text: `${section.title} (${done} of ${cards.length})` }), section.blurb ? h('p', { text: section.blurb }) : null),
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
          else meta = ['Not answered yet', c.applies_to?.summary ? ` · ${c.applies_to.summary}` : ''];
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
  return [topbar(), hero, ...sections, footer];
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

function quoteBlock(item) {
  const where = [item.file, item.locator].filter(Boolean).join(' · ');
  return h('blockquote', { class: 'quote' }, h('q', { text: item.quote }), where ? h('cite', { text: where }) : null);
}

function contextBlock(c) {
  const items = (c.context || []).filter(Boolean);
  if (!items.length) return null;
  const out = [h('h2', { text: 'What your files say' })];
  for (const item of items) {
    if (item.kind === 'quotes' && item.items?.length) {
      out.push(h('h3', { text: item.label || 'From the files' }), ...item.items.map(quoteBlock));
    } else if (item.kind === 'values' && item.rows?.length) {
      out.push(
        h('h3', { text: item.label || 'Values' }),
        h(
          'div',
          { class: 'tablewrap', tabindex: 0, role: 'region', 'aria-label': item.label || 'Values' },
          h(
            'table',
            {},
            h('thead', {}, h('tr', {}, (item.columns || []).map((col) => h('th', { scope: 'col', text: col })))),
            h('tbody', {}, item.rows.map((row) => h('tr', {}, row.map((cell) => h('td', { text: cell === null || cell === undefined ? '' : String(cell) }))))),
          ),
        ),
      );
    } else if (item.kind === 'image' && item.image) {
      const src = `/api/image?f=${encodeURIComponent(item.image)}`;
      out.push(
        h('h3', { text: item.label || 'Picture' }),
        h('figure', { class: 'figure' }, h('a', { href: src, target: '_blank', rel: 'noopener' }, h('img', { src, alt: item.alt || item.label || '', loading: 'lazy' })), item.alt ? h('figcaption', { text: item.alt }) : null),
      );
    }
  }
  return out.length > 1 ? h('section', { class: 'panel context' }, out) : null;
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

  const parts = [];
  parts.push(
    h(
      'div',
      { class: 'chips' },
      h('span', { class: c.blocking ? 'chip' : 'chip quiet', text: c.blocking ? 'Needed before export' : 'Nice to have' }),
      c.audience === 'processing' ? h('span', { class: 'chip quiet', text: 'About the data processing' }) : null,
      c.unblocks ? h('span', { class: 'chip quiet', text: `Covers ${c.unblocks} record${c.unblocks === 1 ? '' : 's'}` }) : null,
    ),
    h('h1', { class: 'title', text: c.title }),
    c.detail ? h('p', { class: 'detail', text: c.detail }) : null,
  );

  if (c.applies_to?.summary) {
    const items = c.applies_to.items || [];
    parts.push(
      items.length
        ? h(
            'details',
            { class: 'applies' },
            h('summary', { text: `Applies to: ${c.applies_to.summary}` }),
            h('ul', {}, items.map((x) => h('li', { text: x })), c.applies_to.count > items.length ? h('li', { text: `… and ${c.applies_to.count - items.length} more` }) : null),
          )
        : h('p', { class: 'applies', text: `Applies to: ${c.applies_to.summary}` }),
    );
  }

  if (state.cardError) parts.push(h('p', { class: 'error', role: 'alert', id: 'card-error', text: state.cardError }));

  if (a) {
    parts.push(
      h(
        'div',
        { class: `saved${a.action === 'dont_know' ? ' unsure' : ''}`, role: 'status' },
        h('span', {}, h('strong', {}, a.action === 'dont_know' ? 'Marked as: don’t know' : ['Answer: ', typedText(describeAnswer(c, a))]), ' · saved by ', typedText(a.by), `, ${day(a.at)}`),
        h('button', { class: 'linklike', type: 'button', id: 'clear', disabled: busy, onclick: () => save(c, { action: 'clear' }, { advance: false }), text: 'Clear this answer' }),
        a.note ? h('span', { class: 'saved-note' }, 'Note: ', typedText(a.note)) : null,
      ),
    );
  } else if (stale) {
    parts.push(
      h('div', { class: 'saved unsure', role: 'status' }, h('span', {}, h('strong', { text: 'The suggested answer has changed.' }), ' ', typedText(saved.by), ` accepted an earlier suggestion (“${String(saved.value)}”) on ${day(saved.at)}. Please look at the new one.`)),
    );
  }

  if (suggestion) {
    const accepted = a && a.action === 'accept';
    parts.push(
      h(
        'div',
        { class: 'suggest' },
        h('p', { class: 'eyebrow', text: 'Suggested answer' }),
        h('p', { class: 'suggest-value', text: suggestion.label ?? String(suggestion.value) }),
        suggestion.reason ? h('p', { class: 'suggest-why', text: suggestion.reason }) : null,
        h('p', { class: 'suggest-basis', text: [CONFIDENCE[suggestion.confidence], BASIS[suggestion.basis]].filter(Boolean).join(' · ') }),
        ...(suggestion.evidence || []).slice(0, 3).map(quoteBlock),
        h(
          'button',
          { class: `btn btn-primary btn-wide${accepted ? ' is-chosen' : ''}`, type: 'button', id: 'accept', disabled: busy, onclick: () => save(c, { action: 'accept', value: suggestion.value, note: noteValue() }) },
          accepted ? 'Yes, that’s right (your current answer)' : 'Yes, that’s right',
          state.shortcuts && !a ? h('span', { class: 'kbd', 'aria-hidden': 'true', text: 'Y' }) : null,
        ),
      ),
    );
  }

  if (kind === 'yes_no') {
    parts.push(
      h('p', { class: 'group-label', text: 'Your answer' }),
      h('div', { class: 'options' }, optionButton({ value: true, label: 'Yes' }, 'y'), optionButton({ value: false, label: 'No' }, 'n')),
    );
  } else if (kind === 'choice') {
    const rest = options.filter((o) => !suggestion || JSON.stringify(o.value) !== JSON.stringify(suggestion.value));
    const common = c.answer.common?.length ? rest.filter((o) => c.answer.common.includes(o.value)) : rest.length <= 8 ? rest : [];
    const others = rest.filter((o) => !common.includes(o));
    const long = rest.some((o) => String(o.label ?? o.value).length > 28);
    if (common.length) {
      parts.push(h('p', { class: 'group-label', text: suggestion ? 'Or pick a different answer' : 'Pick an answer' }), h('div', { class: `options${long ? ' stack' : ''}` }, common.map((o, i) => optionButton(o, `c${i}`))));
    }
    if (others.length) {
      const openNow = !common.length || others.some((o) => chosen(o.value));
      parts.push(
        h('details', { class: 'more', open: openNow }, h('summary', { text: common.length ? `More options (${others.length})` : suggestion ? `Pick a different answer (${others.length} options)` : `Pick an answer (${others.length} options)` }), h('div', { class: `options${long ? ' stack' : ''}` }, others.map((o, i) => optionButton(o, `o${i}`)))),
      );
    }
  }

  if (kind === 'text' || kind === 'number' || (kind === 'choice' && c.answer.allow_text)) {
    const isNumber = kind === 'number';
    const input = h('input', { class: 'input', id: 'typed', type: 'text', inputmode: isNumber ? 'decimal' : null, placeholder: c.answer.placeholder || null, maxlength: 500, disabled: busy });
    if (draft && draft.typed) input.value = draft.typed;
    else if (a && a.typed && a.action === 'value') input.value = String(a.value);
    const label = kind === 'choice' ? 'None of these? Type it in your own words' : suggestion ? 'Or type a different answer' : 'Type your answer';
    parts.push(
      h('label', { class: 'group-label', for: 'typed', text: label }),
      h(
        'form',
        {
          class: 'typed',
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
        h('button', { class: 'btn', type: 'submit', id: 'save-typed', disabled: busy, text: 'Save answer' }),
      ),
    );
  }

  const note = h('textarea', { class: 'input', id: 'note', maxlength: 2000, disabled: busy, placeholder: 'Anything we should know: who to ask, an exception, a correction…', 'aria-label': 'A note for the ISAAC team' });
  note.value = draft ? draft.note : a?.note || '';
  parts.push(
    h(
      'details',
      { class: 'notebox', id: 'notebox', open: Boolean(note.value) },
      h('summary', { text: a ? 'Add or change a note (optional)' : 'Add a note (optional)' }),
      note,
      a
        ? h('button', { class: 'btn', type: 'button', id: 'save-note', disabled: busy, onclick: () => save(c, { action: a.action, value: a.value, typed: a.typed, note: noteValue() }, { advance: false }), text: 'Save note' })
        : h('p', { class: 'note-small', text: 'The note is saved together with your answer, or with “I don’t know”.' }),
    ),
    h(
      'div',
      { class: 'secondary' },
      h('button', { class: `btn${a && a.action === 'dont_know' ? ' is-chosen' : ''}`, type: 'button', id: 'dont-know', disabled: busy, onclick: () => save(c, { action: 'dont_know', note: noteValue() }) }, 'I don’t know', state.shortcuts && !a ? h('span', { class: 'kbd', 'aria-hidden': 'true', text: 'D' }) : null),
      h('button', { class: 'btn btn-quiet', type: 'button', id: 'skip', disabled: busy, onclick: () => step(1) }, run.single ? 'Back to the list' : 'Skip for now', run.single || !state.shortcuts ? null : h('span', { class: 'kbd', 'aria-hidden': 'true', text: 'S' })),
    ),
  );

  const runbar = h(
    'div',
    { class: 'runbar' },
    h('button', { class: 'linklike', type: 'button', id: 'to-list', onclick: () => show('home'), text: '← All questions' }),
    run.single ? null : h('span', { text: `Question ${run.index + 1} of ${run.ids.length}` }),
  );

  const pager = run.single
    ? null
    : h(
        'div',
        { class: 'pager' },
        h('button', { class: 'btn btn-quiet', type: 'button', id: 'prev', disabled: run.index === 0, onclick: () => step(-1), text: '← Previous' }),
        h('button', { class: 'btn btn-quiet', type: 'button', id: 'next', onclick: () => step(1), text: run.index + 1 === run.ids.length ? 'Finish' : 'Next →' }),
      );

  const keys = h(
    'p',
    { class: 'keys' },
    state.shortcuts ? 'Keyboard shortcuts are on: Y for yes, D for don’t know, S to skip. ' : 'Keyboard shortcuts are off. ',
    h('button', {
      class: 'linklike',
      type: 'button',
      id: 'toggle-keys',
      onclick: () => {
        state.shortcuts = !state.shortcuts;
        setPref('qs_shortcuts', state.shortcuts ? 'on' : 'off');
        render();
      },
      text: state.shortcuts ? 'Turn them off' : 'Turn them on',
    }),
  );

  return [topbar(), runbar, h('section', { class: 'panel' }, parts), contextBlock(c), pager, keys];
}

function viewDone() {
  const run = state.run || { answered: 0 };
  const t = tally(state.cards, state.answers);
  const next = pickRun(state.cards, state.answers, state.runSize);
  const left = t.neededOpen
    ? `${t.neededOpen} needed question${t.neededOpen === 1 ? '' : 's'} left.`
    : t.open
      ? `All the needed questions are answered. ${t.open} nice-to-have question${t.open === 1 ? '' : 's'} left, only if you have time.`
      : 'Everything is answered.';
  return [
    topbar(),
    h(
      'section',
      { class: 'panel' },
      h('h1', { class: 'title', text: run.answered ? `Thank you. ${run.answered} answer${run.answered === 1 ? '' : 's'} saved.` : 'Nothing new saved this time.' }),
      h('p', { class: 'subtitle', text: `${left} You can stop here and come back any time.` }),
      t.needed ? progressBlock('needed questions done', t.neededDone, t.needed, t.neededUnsure) : null,
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

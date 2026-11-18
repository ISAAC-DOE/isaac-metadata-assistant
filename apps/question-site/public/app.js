// The question site's page. No framework and no build step: a few views drawn with DOM calls.
// Every piece of text from the server is set with textContent, never as HTML.

import { describeAnswer, pickRun, tally, CONFIDENCE, BASIS } from './logic.js';

const root = document.getElementById('main');
const toastEl = document.getElementById('toast');

const state = {
  name: null,
  site: null,
  cards: [],
  answers: {},
  view: 'loading', // 'signin' | 'home' | 'card' | 'done'
  run: null, // { ids: [card_id], index, answered: n, skipped: n, single: bool }
  runSize: 10,
  busy: false,
};

try {
  const saved = Number(localStorage.getItem('qs_run_size'));
  if ([5, 10, 15, 25].includes(saved)) state.runSize = saved;
} catch {
  /* private mode: the default size is fine */
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

let toastTimer = null;
function toast(message, bad = false) {
  toastEl.textContent = message;
  toastEl.className = `toast show${bad ? ' bad' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.className = 'toast';
  }, bad ? 5000 : 1400);
}

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
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
    throw new ApiError(0, 'No connection. Your answer was not saved; please try again.');
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* an empty or non-JSON body */
  }
  if (!res.ok) throw new ApiError(res.status, (data && data.error) || 'Something went wrong. Please try again.');
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

function show(view) {
  state.view = view;
  render();
  window.scrollTo(0, 0);
  const heading = root.querySelector('h1');
  if (heading) {
    heading.setAttribute('tabindex', '-1');
    heading.focus({ preventScroll: true });
  }
}

// ---- loading and sign-in ---------------------------------------------------------------------------------------

async function load() {
  try {
    const data = await api('/api/state');
    state.name = data.name;
    state.site = data.site;
    state.cards = data.cards;
    state.answers = data.answers || {};
    show('home');
  } catch (err) {
    if (err.status === 401) return show('signin');
    root.replaceChildren(
      h('div', { class: 'panel signin' }, h('h1', { class: 'title', text: 'ISAAC questions' }), h('p', { class: 'error', text: err.message })),
    );
  }
}

function viewSignin(message) {
  const name = h('input', { class: 'input', id: 'name', name: 'name', autocomplete: 'name', required: true, maxlength: 60 });
  const password = h('input', { class: 'input', id: 'password', name: 'password', type: 'password', autocomplete: 'current-password', required: true });
  const error = h('p', { class: 'error', role: 'alert', hidden: !message, text: message || '' });
  const button = h('button', { class: 'btn btn-primary btn-wide', type: 'submit', text: 'Continue' });
  try {
    name.value = localStorage.getItem('qs_name') || '';
  } catch {
    /* fine */
  }
  const form = h(
    'form',
    {
      class: 'panel signin',
      onsubmit: async (ev) => {
        ev.preventDefault();
        button.disabled = true;
        error.hidden = true;
        try {
          await api('/api/login', { name: name.value, password: password.value });
          try {
            localStorage.setItem('qs_name', name.value.trim());
          } catch {
            /* fine */
          }
          await load();
        } catch (err) {
          error.textContent = err.message;
          error.hidden = false;
          button.disabled = false;
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
  return form;
}

async function signOut() {
  try {
    await api('/api/logout', {});
  } catch {
    /* the cookie may already be gone */
  }
  state.name = null;
  show('signin');
}

function topbar() {
  return h(
    'div',
    { class: 'topbar' },
    h('span', { class: 'brand', text: 'ISAAC questions' }),
    h('span', { class: 'who' }, `Signed in as ${state.name} · `, h('button', { class: 'linklike', type: 'button', onclick: signOut, text: 'Sign out' })),
  );
}

// ---- home ------------------------------------------------------------------------------------------------------

function startRun(ids, single = false) {
  if (!ids.length) return;
  state.run = { ids, index: 0, answered: 0, skipped: 0, single };
  show('card');
}

function progressBlock(label, done, total) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  const fill = h('i');
  fill.style.width = `${pct}%`;
  return h(
    'div',
    { class: 'progress' },
    h('div', { class: 'progress-line' }, h('span', {}, h('strong', { text: `${done} of ${total}` }), ` ${label}`), h('span', { text: `${pct}%` })),
    h('div', { class: 'bar', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': total, 'aria-valuenow': done, 'aria-label': label }, fill),
  );
}

function viewHome() {
  const t = tally(state.cards, state.answers);
  const next = pickRun(state.cards, state.answers, state.runSize);
  const allDone = t.open === 0;

  const size = h(
    'select',
    {
      id: 'run-size',
      onchange: (ev) => {
        state.runSize = Number(ev.target.value);
        try {
          localStorage.setItem('qs_run_size', String(state.runSize));
        } catch {
          /* fine */
        }
        render();
      },
    },
    [5, 10, 15, 25].map((n) => h('option', { value: n, selected: n === state.runSize, text: String(n) })),
  );

  const hero = h(
    'section',
    { class: 'panel' },
    h('h1', { class: 'title', text: allDone ? 'Everything is answered. Thank you.' : `Hello ${state.name.split(' ')[0]}. ${t.neededOpen ? `${t.neededOpen} question${t.neededOpen === 1 ? '' : 's'} left before these records can be exported.` : 'The needed questions are all answered.'}` }),
    h('p', { class: 'beamtime', text: state.site.title }),
    t.needed ? progressBlock('needed questions answered', t.neededDone, t.needed) : null,
    t.optional ? progressBlock('nice-to-have questions answered', t.optionalDone, t.optional) : null,
    allDone
      ? null
      : h(
          'div',
          { class: 'start' },
          h('button', { class: 'btn btn-primary', type: 'button', onclick: () => startRun(next), text: next.length === 1 ? 'Answer the next question' : `Answer the next ${next.length}` }),
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
    const done = cards.filter((c) => state.answers[c.card_id]).length;
    sections.push(
      h('div', { class: 'section-head' }, h('h2', { text: `${section.title} (${done} of ${cards.length})` }), section.blurb ? h('p', { text: section.blurb }) : null),
      h(
        'ul',
        { class: 'rows' },
        cards.map((c) => {
          const a = state.answers[c.card_id];
          const cls = !a ? 'dot' : a.action === 'dont_know' ? 'dot unsure' : 'dot done';
          return h(
            'li',
            {},
            h(
              'button',
              { class: 'row', type: 'button', onclick: () => startRun([c.card_id], true) },
              h('span', { class: cls, 'aria-hidden': 'true' }),
              h('span', { class: 'row-title', text: c.title }),
              h(
                'span',
                { class: 'row-meta' },
                a ? h('span', { class: a.action === 'dont_know' ? '' : 'row-answer', text: describeAnswer(c, a) }) : 'Not answered yet',
                a ? ` · ${a.by}, ${day(a.at)}` : c.applies_to?.summary ? ` · ${c.applies_to.summary}` : '',
              ),
            ),
          );
        }),
      ),
    );
  }

  const footer = h(
    'div',
    { class: 'footer' },
    h('a', { href: '/api/answers', download: '', text: 'Download all answers (for the ISAAC team)' }),
  );

  return [topbar(), hero, ...sections, footer];
}

// ---- one question ----------------------------------------------------------------------------------------------

async function save(c, body, { advance = true } = {}) {
  if (state.busy) return;
  state.busy = true;
  render();
  try {
    const out = await api('/api/answer', { card_id: c.card_id, ...body });
    const had = Boolean(state.answers[c.card_id]);
    if (out.answer) state.answers[c.card_id] = out.answer;
    else delete state.answers[c.card_id];
    state.busy = false;
    if (body.action === 'clear') {
      toast('Answer cleared');
      render();
      return;
    }
    if (state.run && !had) state.run.answered += 1;
    toast('Saved');
    if (advance) {
      // show the chosen answer for a moment, with the buttons still off so a second key press cannot land twice
      state.busy = true;
      render();
      setTimeout(() => {
        state.busy = false;
        step(1);
      }, 450);
    } else render();
  } catch (err) {
    state.busy = false;
    if (err.status === 401) {
      toast('Please sign in again. That answer was not saved.', true);
      return show('signin');
    }
    toast(err.message, true);
    render();
  }
}

function step(delta) {
  const run = state.run;
  if (!run) return show('home');
  const nextIndex = run.index + delta;
  if (nextIndex < 0) return;
  if (nextIndex >= run.ids.length) {
    return run.single ? show('home') : show('done');
  }
  run.index = nextIndex;
  show('card');
}

function skip() {
  const run = state.run;
  if (run && !state.answers[run.ids[run.index]]) run.skipped += 1;
  step(1);
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
  const a = state.answers[c.card_id] || null;
  const busy = state.busy;
  const kind = c.answer?.kind || 'text';
  const options = c.answer?.options || [];
  const suggestion = c.suggestion || null;
  const chosen = (value) => a && a.action !== 'dont_know' && JSON.stringify(a.value) === JSON.stringify(value);

  const pick = (value, typed = false) => save(c, { action: 'value', value, typed, note: noteValue() });

  const optionButton = (o) =>
    h('button', { class: `btn${chosen(o.value) ? ' is-chosen' : ''}`, type: 'button', disabled: busy, 'aria-pressed': chosen(o.value) ? 'true' : 'false', onclick: () => pick(o.value), text: o.label ?? String(o.value) });

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

  if (a) {
    parts.push(
      h(
        'div',
        { class: `saved${a.action === 'dont_know' ? ' unsure' : ''}`, role: 'status' },
        h('span', {}, h('strong', { text: a.action === 'dont_know' ? 'Marked as: don’t know' : `Answer: ${describeAnswer(c, a)}` }), ` · saved by ${a.by}, ${day(a.at)}`),
        h('button', { class: 'linklike', type: 'button', disabled: busy, onclick: () => save(c, { action: 'clear' }, { advance: false }), text: 'Clear this answer' }),
        a.note ? h('span', { class: 'saved-note', text: `Note: ${a.note}` }) : null,
      ),
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
          h('span', { class: 'kbd', 'aria-hidden': 'true', text: 'Y' }),
        ),
      ),
    );
  }

  if (kind === 'yes_no') {
    parts.push(
      h('p', { class: 'group-label', text: 'Your answer' }),
      h('div', { class: 'options' }, optionButton({ value: true, label: 'Yes' }), optionButton({ value: false, label: 'No' })),
    );
  } else if (kind === 'choice') {
    const rest = options.filter((o) => !suggestion || JSON.stringify(o.value) !== JSON.stringify(suggestion.value));
    const common = c.answer.common?.length ? rest.filter((o) => c.answer.common.includes(o.value)) : rest.length <= 8 ? rest : [];
    const others = rest.filter((o) => !common.includes(o));
    const long = rest.some((o) => String(o.label ?? o.value).length > 28);
    if (common.length) {
      parts.push(h('p', { class: 'group-label', text: suggestion ? 'Or pick a different answer' : 'Pick an answer' }), h('div', { class: `options${long ? ' stack' : ''}` }, common.map(optionButton)));
    }
    if (others.length) {
      const openNow = !common.length || others.some((o) => chosen(o.value));
      parts.push(
        h('details', { class: 'more', open: openNow }, h('summary', { text: common.length ? `More options (${others.length})` : suggestion ? `Pick a different answer (${others.length} options)` : `Pick an answer (${others.length} options)` }), h('div', { class: `options${long ? ' stack' : ''}` }, others.map(optionButton))),
      );
    }
  }

  if (kind === 'text' || kind === 'number' || (kind === 'choice' && c.answer.allow_text)) {
    const isNumber = kind === 'number';
    const input = h('input', {
      class: 'input',
      id: 'typed',
      type: 'text',
      inputmode: isNumber ? 'decimal' : null,
      placeholder: c.answer.placeholder || null,
      maxlength: 500,
      'aria-label': kind === 'choice' ? 'A different answer, in your own words' : 'Your answer',
    });
    if (a && a.typed && a.action === 'value') input.value = String(a.value);
    const label = kind === 'choice' ? 'None of these? Type it in your own words' : suggestion ? 'Or type a different answer' : 'Type your answer';
    parts.push(
      h('p', { class: 'group-label', text: label }),
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
        h('button', { class: 'btn', type: 'submit', disabled: busy, text: 'Save answer' }),
      ),
    );
  }

  const note = h('textarea', { class: 'input', id: 'note', maxlength: 2000, placeholder: 'Anything we should know: who to ask, an exception, a correction…', 'aria-label': 'A note for the ISAAC team' });
  if (a?.note) note.value = a.note;
  parts.push(
    h(
      'details',
      { class: 'notebox', open: Boolean(a?.note) },
      h('summary', { text: 'Add a note (optional)' }),
      note,
      h('p', { class: 'note-small', text: 'The note is saved together with your answer, or with “I don’t know”.' }),
    ),
    h(
      'div',
      { class: 'secondary' },
      h('button', { class: `btn${a && a.action === 'dont_know' ? ' is-chosen' : ''}`, type: 'button', id: 'dont-know', disabled: busy, onclick: () => save(c, { action: 'dont_know', note: noteValue() }) }, 'I don’t know', h('span', { class: 'kbd', 'aria-hidden': 'true', text: 'D' })),
      h('button', { class: 'btn btn-quiet', type: 'button', id: 'skip', disabled: busy, onclick: skip }, run.single ? 'Back to the list' : 'Skip for now', run.single ? null : h('span', { class: 'kbd', 'aria-hidden': 'true', text: 'S' })),
    ),
  );

  const runbar = h(
    'div',
    { class: 'runbar' },
    h('button', { class: 'linklike', type: 'button', onclick: () => show('home'), text: '← All questions' }),
    run.single ? null : h('span', { text: `Question ${run.index + 1} of ${run.ids.length}` }),
  );

  const pager = run.single
    ? null
    : h(
        'div',
        { class: 'pager' },
        h('button', { class: 'btn btn-quiet', type: 'button', disabled: run.index === 0, onclick: () => step(-1), text: '← Previous' }),
        h('button', { class: 'btn btn-quiet', type: 'button', onclick: () => step(1), text: run.index + 1 === run.ids.length ? 'Finish' : 'Next →' }),
      );

  return [topbar(), runbar, h('section', { class: 'panel' }, parts), contextBlock(c), pager];
}

function viewDone() {
  const run = state.run || { answered: 0, skipped: 0 };
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
      t.needed ? progressBlock('needed questions answered', t.neededDone, t.needed) : null,
      h(
        'div',
        { class: 'start' },
        next.length ? h('button', { class: 'btn btn-primary', type: 'button', onclick: () => startRun(next), text: next.length === 1 ? 'Answer one more' : `Keep going: the next ${next.length}` }) : null,
        h('button', { class: 'btn', type: 'button', onclick: () => show('home'), text: 'Back to all questions' }),
      ),
    ),
  ];
}

// ---- draw and keys ---------------------------------------------------------------------------------------------

function render() {
  let nodes;
  if (state.view === 'signin') nodes = [viewSignin()];
  else if (state.view === 'home') nodes = viewHome();
  else if (state.view === 'card') nodes = viewCard();
  else if (state.view === 'done') nodes = viewDone();
  else nodes = [h('p', { class: 'loading', role: 'status', text: 'Loading…' })];
  // keep what is being typed when the same card is drawn again (a save in progress, a failed save)
  const keep = {};
  for (const id of ['typed', 'note']) {
    const el = document.getElementById(id);
    if (el && state.view === 'card') keep[id] = { value: el.value, card: root.dataset.card };
  }
  root.replaceChildren(...nodes.flat().filter(Boolean));
  const current = state.view === 'card' && state.run ? state.run.ids[state.run.index] : '';
  for (const [id, saved] of Object.entries(keep)) {
    const el = document.getElementById(id);
    if (el && saved.card === current && saved.value) {
      el.value = saved.value;
      if (id === 'note') el.closest('details')?.setAttribute('open', '');
    }
  }
  root.dataset.card = current;
}

document.addEventListener('keydown', (ev) => {
  if (state.view !== 'card' || ev.metaKey || ev.ctrlKey || ev.altKey) return;
  const tag = (ev.target.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
  const key = ev.key.toLowerCase();
  const click = (id) => {
    const el = document.getElementById(id);
    if (el && !el.disabled) {
      ev.preventDefault();
      el.click();
    }
  };
  if (key === 'y') click('accept');
  else if (key === 'd') click('dont-know');
  else if (key === 's' || key === 'arrowright') click('skip');
  else if (key === 'arrowleft' && state.run && !state.run.single) {
    ev.preventDefault();
    step(-1);
  }
});

load();

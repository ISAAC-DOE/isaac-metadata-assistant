// Tests for the claude.ai artifact page (artifact/index.html) and its seed script (artifact/seed.py).
//
// The page's pure functions sit in `<script id="logic">`. This file reads index.html, cuts out that one script by
// its id and runs it in a Node `vm` context, so the tests run the page's own code with no browser and no copy.

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ARTIFACT = path.join(HERE, '..', 'artifact');
const FIXTURE = path.join(HERE, 'fixtures', 'site-data.json');

const html = fs.readFileSync(path.join(ARTIFACT, 'index.html'), 'utf8');
const logicSource = /<script id="logic">([\s\S]*?)<\/script>/.exec(html)?.[1];
assert.ok(logicSource, 'index.html has a <script id="logic"> block');
const sandbox = {};
vm.runInNewContext(logicSource, sandbox);
// Values made inside the vm have their own Array and Object, so results are passed through JSON before deepEqual.
const L = sandbox.QuestionLogic;
const plain = (v) => JSON.parse(JSON.stringify(v));

const site = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
const cards = site.cards;
const byId = Object.fromEntries(cards.map((c) => [c.card_id, c]));
const technique = byId['C-0000000001'];   // choice, may type, suggestion HERFD-XAS
const noSuggestion = byId['C-0000000002'];
const potential = byId['C-0000000008'];   // number, suggestion 1.2

test('numbers: a decimal point or comma and a bare leading point are read; a thousands comma is refused', () => {
  assert.equal(L.parseNumber('0.125'), 0.125);
  assert.equal(L.parseNumber('0,125'), 0.125);
  assert.equal(L.parseNumber('.5'), 0.5);
  assert.equal(L.parseNumber(' -1.2e-3 '), -0.0012);
  assert.throws(() => L.parseNumber('1,250'), /thousands comma/);
  assert.throws(() => L.parseNumber('abc'), /Please give a number/);
  assert.throws(() => L.parseNumber(''), /Please give a number/);
});

test('accepting is refused when the card has no suggestion', () => {
  assert.equal(noSuggestion.suggestion, null);
  assert.throws(() => L.buildAnswer(noSuggestion, { action: 'accept' }), /no suggested answer/);
  const ok = L.buildAnswer(technique, { action: 'accept', note: ' fine ' });
  assert.deepEqual(plain(ok), { card_id: technique.card_id, action: 'accept', value: 'HERFD-XAS', typed: false, note: 'fine' });
});

test('a typed answer that is not on the list is kept as typed', () => {
  const a = L.buildAnswer(technique, { action: 'value', value: ' Some Other Technique ', typed: true });
  assert.equal(a.value, 'Some Other Technique');
  assert.equal(a.typed, true);
  const picked = L.buildAnswer(technique, { action: 'value', value: technique.answer.options[0].value });
  assert.equal(picked.typed, false);
  assert.throws(() => L.buildAnswer(byId['C-0000000007'], { action: 'value', value: 'free text', typed: true }), /listed answers/);
  assert.equal(L.buildAnswer(potential, { action: 'value', value: '1,5' }).value, 1.5);
});

test('an accepted suggestion that no longer matches the card re-opens the question', () => {
  const accepted = { action: 'accept', value: 'HERFD-XAS' };
  assert.equal(L.isStale(technique, accepted), false);
  assert.equal(L.isStale({ ...technique, suggestion: { ...technique.suggestion, value: 'XAS' } }, accepted), true);
  assert.equal(L.isStale({ ...technique, suggestion: null }, accepted), true);
  assert.equal(L.isStale(technique, { action: 'value', value: 'anything' }), false, 'a typed answer is never stale');
  const answers = { [technique.card_id]: accepted };
  assert.ok(L.standing(technique, answers));
  assert.equal(L.standing({ ...technique, suggestion: null }, answers), null);
  assert.equal(L.describe(technique, accepted), technique.suggestion.label);
  assert.equal(L.describe(potential, { action: 'value', value: 1.5 }), '1.5 V');
});

test('the next sitting puts needed cards first and skips answered ones', () => {
  assert.deepEqual(plain(L.pickRun(cards, {}, 3)), ['C-0000000001', 'C-0000000002', 'C-0000000003']);
  const answers = { 'C-0000000001': { action: 'accept', value: 'HERFD-XAS' }, 'C-0000000003': { action: 'dont_know' } };
  assert.deepEqual(plain(L.pickRun(cards, answers, 3)), ['C-0000000002', 'C-0000000004', 'C-0000000005']);
  const allNeeded = Object.fromEntries(cards.filter((c) => c.blocking).map((c) => [c.card_id, { action: 'dont_know' }]));
  assert.deepEqual(plain(L.pickRun(cards, allNeeded, 10)), ['C-0000000008', 'C-0000000009']);
  const t = L.tally(cards, answers);
  assert.deepEqual([t.needed, t.neededDone, t.neededUnsure, t.neededOpen], [7, 2, 1, 5]);
});

// ---- seed.py -----------------------------------------------------------------------------------------------
const py = spawnSync('python3', ['--version']);
const pySkip = py.error || py.status !== 0 ? 'python3 is not installed' : false;
if (pySkip) console.log(`# skipping the seed.py tests: ${pySkip}`);
const seed = (...args) => spawnSync('python3', ['-I', path.join(ARTIFACT, 'seed.py'), ...args], { encoding: 'utf8' });
const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));

test('seed.py cards: no covers, an image without a URL is dropped, one with a URL is kept', { skip: pySkip }, () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'artifact-seed-'));
  const imageCard = cards.find((c) => (c.context || []).some((i) => i.kind === 'image'));
  const image = imageCard.context.find((i) => i.kind === 'image').image;

  const out1 = path.join(tmp, 'a');
  const r1 = seed('cards', FIXTURE, out1);
  assert.equal(r1.status, 0, r1.stderr);
  assert.match(r1.stdout, /1 image file\(s\) to upload/);
  assert.ok(r1.stdout.includes(image), 'the file to upload is listed');
  for (const c of cards) {
    const doc = readJson(path.join(out1, 'cards', `${c.card_id}.json`));
    assert.equal('covers' in doc, false, 'covers stays local');
    assert.equal(doc.card_id, c.card_id);
  }
  const doc1 = readJson(path.join(out1, 'cards', `${imageCard.card_id}.json`));
  assert.equal(doc1.context.some((i) => i.kind === 'image'), false, 'no URL, no image');
  assert.equal(readJson(path.join(out1, 'meta', 'site.json')).bundle_id, site.bundle_id);

  const urls = path.join(tmp, 'urls.json');
  fs.writeFileSync(urls, JSON.stringify({ [image]: 'https://example.test/asset.png' }));
  const out2 = path.join(tmp, 'b');
  const r2 = seed('cards', FIXTURE, out2, '--image-urls', urls);
  assert.equal(r2.status, 0, r2.stderr);
  const doc2 = readJson(path.join(out2, 'cards', `${imageCard.card_id}.json`));
  assert.equal(doc2.context.find((i) => i.kind === 'image').image_url, 'https://example.test/asset.png');
  assert.equal('covers' in doc2, false);
});

test('seed.py answers writes the contract\'s isaac.question_site_answers format', { skip: pySkip }, () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'artifact-seed-'));
  const read = path.join(tmp, 'read');
  fs.mkdirSync(path.join(read, 'answers'), { recursive: true });
  fs.mkdirSync(path.join(read, 'log'), { recursive: true });
  const one = { card_id: 'C-0000000001', action: 'accept', value: 'HERFD-XAS', typed: false, note: '', by: 'Test Person', at: '2026-01-02T10:00:00Z', by_id: 'x' };
  fs.writeFileSync(path.join(read, 'answers', 'C-0000000001.json'), JSON.stringify({ data: one }));
  fs.writeFileSync(path.join(read, 'log', 'a.json'), JSON.stringify(one));
  const out = path.join(tmp, 'answers.json');
  const r = seed('answers', FIXTURE, read, out);
  assert.equal(r.status, 0, r.stderr);
  const doc = readJson(out);
  assert.equal(doc.format, 'isaac.question_site_answers');
  assert.equal(doc.bundle_id, site.bundle_id);
  assert.equal(doc.answers.length, 1);
  assert.deepEqual(Object.keys(doc.answers[0]), ['card_id', 'action', 'value', 'typed', 'note', 'by', 'at']);
  assert.equal(doc.exported_at, '2026-01-02T10:00:00Z');
  assert.equal(doc.log.length, 1);
});

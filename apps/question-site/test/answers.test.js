import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { setup, call, signIn, FIXTURES } from './helpers.js';
import login from '../api/login.js';
import state from '../api/state.js';
import answer from '../api/answer.js';
import answers from '../api/answers.js';
import image from '../api/image.js';

const post = (cookie, body) => call(answer, { method: 'POST', cookie, body });

test('the page gets every card, and nothing about how an answer is recorded', async () => {
  setup();
  const cookie = await signIn(login);
  const out = await call(state, { cookie });
  assert.equal(out.status, 200);
  assert.equal(out.json.name, 'Test Person');
  assert.equal(out.json.cards.length, 9);
  for (const card of out.json.cards) assert.equal(card.covers, undefined, 'covers stays on the server');
  assert.ok(!out.body.includes('Q-fake'), 'no question id reaches the browser');
  assert.equal(out.headers['cache-control'], 'no-store');
  assert.match(out.headers['x-robots-tag'], /noindex/);
});

test('accepting a suggestion stores the suggestion as the site holds it, with who and when', async () => {
  const store = setup();
  const cookie = await signIn(login, 'First Tester');
  const out = await post(cookie, { card_id: 'C-0000000001', action: 'accept', value: 'HERFD-XAS', by: 'Someone Else', at: '1999-01-01T00:00:00Z' });
  assert.equal(out.status, 200);
  assert.deepEqual(
    { ...out.json.answer, at: null },
    { card_id: 'C-0000000001', action: 'accept', value: 'HERFD-XAS', typed: false, note: '', by: 'First Tester', at: null },
  );
  assert.notEqual(out.json.answer.at, '1999-01-01T00:00:00Z', 'the time is the server clock, never the body');
  assert.equal((await store.current('fake-bundle-0000'))['C-0000000001'].by, 'First Tester');
});

test('"yes" cannot be made to mean something else: a different value is refused', async () => {
  setup();
  const cookie = await signIn(login);
  assert.equal((await post(cookie, { card_id: 'C-0000000001', action: 'accept', value: 'XRD' })).status, 409);
  assert.equal((await post(cookie, { card_id: 'C-0000000002', action: 'accept' })).status, 400, 'no suggestion, nothing to accept');
});

test('a picked option, a typed word, a number and a yes/no are each stored as what they are', async () => {
  setup();
  const cookie = await signIn(login);
  const picked = await post(cookie, { card_id: 'C-0000000001', action: 'value', value: 'XAS' });
  assert.deepEqual([picked.json.answer.value, picked.json.answer.typed], ['XAS', false]);
  const typed = await post(cookie, { card_id: 'C-0000000001', action: 'value', value: '  my own technique word ', typed: true });
  assert.deepEqual([typed.json.answer.value, typed.json.answer.typed], ['my own technique word', true]);
  for (const [typedIn, stored] of [['1,25', 1.25], ['1.25', 1.25], [' -0.3 ', -0.3], ['\u22120.3', -0.3], ['1e-3', 0.001], [2, 2]]) {
    const number = await post(cookie, { card_id: 'C-0000000008', action: 'value', value: typedIn });
    assert.equal(number.json.answer.value, stored, String(typedIn));
  }
  // nothing is reinterpreted: these are refused, not turned into some number
  for (const bad of ['about one', '', '0x10', '1,250', '12,345,678', [5], '1.2.3', 'Infinity', '1e999', null, true]) {
    assert.equal((await post(cookie, { card_id: 'C-0000000008', action: 'value', value: bad })).status, 400, JSON.stringify(bad));
  }
  const yes = await post(cookie, { card_id: 'C-0000000009', action: 'value', value: true });
  assert.equal(yes.json.answer.value, true);
  assert.equal((await post(cookie, { card_id: 'C-0000000009', action: 'value', value: 'yes' })).status, 400);
});

test('a card that takes only listed answers refuses a typed one', async () => {
  setup();
  const cookie = await signIn(login);
  assert.equal((await post(cookie, { card_id: 'C-0000000007', action: 'value', value: 'something else', typed: true })).status, 400);
  assert.equal((await post(cookie, { card_id: 'C-0000000007', action: 'value', value: 'settling' })).status, 200);
});

test('"I don\'t know" is stored with its note and no value', async () => {
  setup();
  const cookie = await signIn(login);
  const out = await post(cookie, { card_id: 'C-0000000006', action: 'dont_know', value: 'ignored', note: 'Ask the person who made the sample.' });
  assert.deepEqual([out.json.answer.action, out.json.answer.value, out.json.answer.note], ['dont_know', null, 'Ask the person who made the sample.']);
});

test('an unknown card, an unknown action, an empty answer and an over-long one are refused', async () => {
  setup();
  const cookie = await signIn(login);
  assert.equal((await post(cookie, { card_id: 'C-nope', action: 'dont_know' })).status, 404);
  assert.equal((await post(cookie, { card_id: 'C-0000000002', action: 'approve' })).status, 400);
  assert.equal((await post(cookie, { card_id: 'C-0000000002', action: 'value', value: '   ' })).status, 400);
  assert.equal((await post(cookie, { card_id: 'C-0000000002', action: 'value', value: 'x'.repeat(501) })).status, 400);
  assert.equal((await post(cookie, { card_id: 'C-0000000002', action: 'value', value: 'ok', note: 'n'.repeat(2001) })).status, 400);
  assert.equal((await call(answer, { method: 'POST', cookie, body: 'not json' })).status, 400);
  assert.equal((await call(answer, { method: 'POST', cookie, body: '{}', headers: { 'content-type': 'text/plain' } })).status, 415);
});

test('the download holds the latest answer per card and the whole history, with each person\'s name', async () => {
  setup();
  const first = await signIn(login, 'First Tester');
  const second = await signIn(login, 'Second Tester');
  await post(first, { card_id: 'C-0000000001', action: 'accept' });
  await post(second, { card_id: 'C-0000000001', action: 'value', value: 'XAS', note: 'not high resolution' });
  await post(first, { card_id: 'C-0000000003', action: 'dont_know' });
  await post(first, { card_id: 'C-0000000003', action: 'clear' });
  const out = await call(answers, { cookie: first });
  assert.equal(out.status, 200);
  assert.match(out.headers['content-disposition'], /^attachment; filename="answers-\d{4}-\d\d-\d\d\.json"$/);
  const doc = JSON.parse(out.body);
  assert.equal(doc.format, 'isaac.question_site_answers');
  assert.equal(doc.format_version, '1.0.0');
  assert.equal(doc.bundle_id, 'fake-bundle-0000');
  assert.equal(doc.bundle_version, 'v-fake-1');
  assert.equal(doc.answers.length, 1, 'the cleared card has no current answer');
  assert.deepEqual([doc.answers[0].value, doc.answers[0].by, doc.answers[0].note], ['XAS', 'Second Tester', 'not high resolution']);
  assert.deepEqual(doc.log.map((e) => e.action), ['accept', 'value', 'dont_know', 'clear']);
  for (const key of ['card_id', 'action', 'value', 'typed', 'note', 'by', 'at']) assert.ok(key in doc.answers[0], key);
});

test('an image is served only by its contract name, only to a signed-in reader, and only if it is that image', async () => {
  setup();
  const cookie = await signIn(login);
  const name = fs.readdirSync(path.join(FIXTURES, 'img')).find((f) => f.endsWith('.png'));
  const ok = await call(image, { url: `/api/image?f=img/${name}`, cookie });
  assert.equal(ok.status, 200);
  assert.equal(ok.headers['content-type'], 'image/png');
  assert.equal(ok.headers['cache-control'], 'no-store', 'nothing of an image stays in the browser after sign-out');
  assert.ok(Buffer.isBuffer(ok.body) && ok.body.length > 1000);
  for (const bad of ['../site-data.json', 'img/../site-data.json', 'site-data.json', `img/${name}/../../site-data.json`, 'img/%2e%2e/site-data.json', '', `img/${name.replace('.png', '.svg')}`, `img/${'0'.repeat(64)}.png`]) {
    const out = await call(image, { url: `/api/image?f=${encodeURIComponent(bad)}`, cookie });
    assert.equal(out.status, 404, bad);
  }
  // a file with an image's name that is not an image is not served
  const fake = `${'a'.repeat(64)}.png`;
  fs.writeFileSync(path.join(FIXTURES, 'img', fake), '<script>alert(1)</script>');
  try {
    assert.equal((await call(image, { url: `/api/image?f=img/${fake}`, cookie })).status, 404);
  } finally {
    fs.unlinkSync(path.join(FIXTURES, 'img', fake));
  }
});

test('a site with no questions, or questions in another format, answers 503', async () => {
  setup();
  const cookie = await signIn(login);
  process.env.QUESTION_SITE_DATA_DIR = path.join(FIXTURES, 'does-not-exist');
  const { resetDataCache } = await import('../lib/data.js');
  resetDataCache();
  assert.equal((await call(state, { cookie })).status, 503);
});

test('an answer someone else gave in the meantime is never overwritten unseen', async () => {
  setup();
  const first = await signIn(login, 'First Tester');
  const second = await signIn(login, 'Second Tester');
  // both have the page open with no answer on the card
  const a = await post(first, { card_id: 'C-0000000002', action: 'value', value: 'Group one', typed: true, seen_at: null });
  assert.equal(a.status, 200);
  const b = await post(second, { card_id: 'C-0000000002', action: 'value', value: 'Group two', typed: true, seen_at: null });
  assert.equal(b.status, 409);
  assert.equal(b.json.answer.value, 'Group one', 'the page is sent what is there');
  assert.match(b.json.error, /First Tester/);
  // having seen it, the second person may change it
  const c = await post(second, { card_id: 'C-0000000002', action: 'value', value: 'Group two', typed: true, seen_at: a.json.answer.at });
  assert.equal(c.status, 200);
  // a clear is protected the same way
  assert.equal((await post(first, { card_id: 'C-0000000002', action: 'clear', seen_at: a.json.answer.at })).status, 409);
  assert.equal((await post(first, { card_id: 'C-0000000002', action: 'clear', seen_at: c.json.answer.at })).status, 200);
  // and answering a card that was cleared under you
  assert.equal((await post(second, { card_id: 'C-0000000002', action: 'dont_know', seen_at: c.json.answer.at })).status, 409);
});

test('hidden direction-changing characters are dropped from answers and notes', async () => {
  setup();
  const cookie = await signIn(login);
  const out = await post(cookie, { card_id: 'C-0000000002', action: 'value', value: 'Gro\u202eup\u200b one', typed: true, note: 'see\u2066 note' });
  assert.deepEqual([out.json.answer.value, out.json.answer.note], ['Group one', 'see note']);
});

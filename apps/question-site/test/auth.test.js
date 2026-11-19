import test from 'node:test';
import assert from 'node:assert/strict';
import { setup, call, signIn, PASSWORD } from './helpers.js';
import login from '../api/login.js';
import logout from '../api/logout.js';
import state from '../api/state.js';
import answer from '../api/answer.js';
import answers from '../api/answers.js';
import image from '../api/image.js';
import { makeSession, readSession, COOKIE } from '../lib/auth.js';

test('every data route refuses a visitor who has not signed in', async () => {
  setup();
  for (const [handler, method] of [[state, 'GET'], [answers, 'GET'], [image, 'GET'], [answer, 'POST']]) {
    const out = await call(handler, { method, body: method === 'POST' ? { card_id: 'C-0000000001', action: 'dont_know' } : undefined });
    assert.equal(out.status, 401, `${method} must be refused`);
    assert.ok(!String(out.body).includes('FAKE'), 'a refusal carries no question text');
  }
});

test('the right password and a name sign in; the cookie is HttpOnly, Secure and SameSite=Strict', async () => {
  setup();
  const out = await call(login, { method: 'POST', body: { name: '  Test   Person ', password: PASSWORD } });
  assert.equal(out.status, 200);
  assert.equal(out.json.name, 'Test Person');
  const cookie = String(out.headers['set-cookie']);
  assert.match(cookie, new RegExp(`^${COOKIE}=`));
  for (const flag of ['HttpOnly', 'Secure', 'SameSite=Strict', 'Path=/']) assert.ok(cookie.includes(flag), flag);
  assert.ok(!cookie.includes(PASSWORD), 'the cookie never carries the password');
});

test('a wrong password is refused and says nothing about the right one', async () => {
  setup();
  const out = await call(login, { method: 'POST', body: { name: 'Test Person', password: 'wrong-password' } });
  assert.equal(out.status, 401);
  assert.equal(out.headers['set-cookie'], undefined);
  assert.ok(!String(out.body).includes(PASSWORD));
});

test('a name is required, and a long or empty one is refused before the password is looked at', async () => {
  setup();
  assert.equal((await call(login, { method: 'POST', body: { name: '   ', password: PASSWORD } })).status, 400);
  assert.equal((await call(login, { method: 'POST', body: { name: 'x'.repeat(61), password: PASSWORD } })).status, 400);
  assert.equal((await call(login, { method: 'POST', body: { name: { a: 1 }, password: PASSWORD } })).status, 400, 'a name must be text');
  const hidden = await call(login, { method: 'POST', body: { name: 'Te\u202est\u200b Person', password: PASSWORD } });
  assert.equal(hidden.json.name, 'Test Person', 'direction-changing and zero-width characters are dropped');
});

test('ten wrong passwords lock an address out, and then even the right password is refused', async () => {
  setup();
  const wrong = (ip) => call(login, { method: 'POST', body: { name: 'A', password: 'nope-nope-nope' }, ip });
  const right = (ip) => call(login, { method: 'POST', body: { name: 'A', password: PASSWORD }, ip });
  for (let i = 0; i < 10; i += 1) assert.equal((await wrong('198.51.100.1')).status, 401, `try ${i + 1}`);
  const blocked = await wrong('198.51.100.1');
  assert.equal(blocked.status, 429);
  // the refusal must not tell a guesser right from wrong
  const rightWhileLocked = await right('198.51.100.1');
  assert.equal(rightWhileLocked.status, 429);
  assert.equal(rightWhileLocked.headers['set-cookie'], undefined);
  assert.deepEqual(rightWhileLocked.json, blocked.json);
  // another address is untouched
  assert.equal((await wrong('198.51.100.2')).status, 401);
  assert.equal((await right('198.51.100.2')).status, 200);
});

test('the lockout is kept in the store, so it holds on an instance that has not seen the address', async () => {
  setup();
  for (let i = 0; i < 10; i += 1) await call(login, { method: 'POST', body: { name: 'A', password: 'nope-nope-nope' }, ip: '198.51.100.9' });
  const { forgetLockouts } = await import('../api/login.js');
  forgetLockouts(); // a fresh instance
  assert.equal((await call(login, { method: 'POST', body: { name: 'A', password: PASSWORD }, ip: '198.51.100.9' })).status, 429);
});

test('nine wrong passwords and then the right one signs in', async () => {
  setup();
  for (let i = 0; i < 9; i += 1) await call(login, { method: 'POST', body: { name: 'A', password: 'nope-nope-nope' }, ip: '198.51.100.3' });
  assert.equal((await call(login, { method: 'POST', body: { name: 'A', password: PASSWORD }, ip: '198.51.100.3' })).status, 200);
});

test('when the counter store cannot be reached, nobody is signed in', async () => {
  setup();
  const { useStore } = await import('../lib/store.js');
  const { HttpError } = await import('../lib/http.js');
  useStore({ count: async () => { throw new HttpError(503, 'down'); }, hit: async () => { throw new HttpError(503, 'down'); } });
  const out = await call(login, { method: 'POST', body: { name: 'A', password: PASSWORD } });
  assert.equal(out.status, 503);
  assert.equal(out.headers['set-cookie'], undefined);
});

test('a tampered, expired or foreign session is not a session', async () => {
  setup();
  const good = makeSession('Test Person');
  assert.equal(readSession(good).name, 'Test Person');
  const [payload, sig] = good.split('.');
  const forged = Buffer.from(JSON.stringify({ n: 'Someone Else', e: Date.now() + 1e9 })).toString('base64url');
  assert.equal(readSession(`${forged}.${sig}`), null, 'a changed name with the old signature');
  assert.equal(readSession(`${payload}.${sig.slice(0, -2)}xx`), null, 'a changed signature');
  assert.equal(readSession(makeSession('Test Person', Date.now() - 40 * 86400_000)), null, 'an expired session');
  assert.equal(readSession('not-a-token'), null);
  assert.equal(readSession(undefined), null);
  process.env.SESSION_SECRET = 'a-secret-added-later';
  assert.equal(readSession(good), null, 'adding or changing the session secret signs everyone out');
  const withSecret = makeSession('Test Person');
  assert.equal(readSession(withSecret).name, 'Test Person');
  process.env.SITE_PASSWORD = 'a-different-password';
  assert.equal(readSession(withSecret), null, 'changing the site password signs everyone out, with a secret set too');
  assert.equal(readSession(good), null);
  delete process.env.SESSION_SECRET;
});

test('a site with no password set answers 503, never "signed in"', async () => {
  setup();
  const cookie = await signIn(login);
  delete process.env.SITE_PASSWORD;
  assert.equal((await call(state, { cookie })).status, 503);
  assert.equal((await call(login, { method: 'POST', body: { name: 'A', password: '' } })).status, 503);
  process.env.SITE_PASSWORD = 'elevenchars';
  assert.equal((await call(login, { method: 'POST', body: { name: 'A', password: 'elevenchars' } })).status, 503, 'a password under 12 characters is not a password');
});

test('a POST from another site is refused even with a valid cookie', async () => {
  setup();
  const cookie = await signIn(login);
  const out = await call(answer, { method: 'POST', cookie, body: { card_id: 'C-0000000001', action: 'dont_know' }, headers: { origin: 'https://evil.example' } });
  assert.equal(out.status, 403);
  const same = await call(answer, { method: 'POST', cookie, body: { card_id: 'C-0000000001', action: 'dont_know' }, headers: { origin: 'https://questions.example.test' } });
  assert.equal(same.status, 200);
});

test('signing out clears the cookie', async () => {
  setup();
  const out = await call(logout, { method: 'POST', body: {} });
  assert.match(String(out.headers['set-cookie']), /Max-Age=0/);
});

test('the wrong method is refused', async () => {
  setup();
  assert.equal((await call(login, { method: 'GET' })).status, 405);
  assert.equal((await call(state, { method: 'POST', body: {} })).status, 405);
});

test('malformed JSON is a 400 even when the host parses the body lazily and throws', async () => {
  setup();
  const { readJson } = await import('../lib/http.js');
  const req = { headers: { 'content-type': 'application/json' }, get body() { throw new Error('Invalid JSON'); } };
  await assert.rejects(readJson(req), (err) => err.status === 400);
  const big = { headers: { 'content-type': 'application/json' }, body: { note: 'x'.repeat(70_000) } };
  await assert.rejects(readJson(big), (err) => err.status === 413, 'a body the host already parsed is size-checked too');
});

test('the session cookie is not marked Secure on any localhost form, and is everywhere else', async () => {
  setup();
  const { sessionCookie } = await import('../lib/auth.js');
  for (const host of ['localhost:5180', '127.0.0.1:5180', '[::1]:5180', 'localhost']) {
    assert.ok(!sessionCookie({ headers: { host } }, 't').includes('Secure'), host);
  }
  assert.ok(sessionCookie({ headers: { host: 'questions.example.test' } }, 't').includes('Secure'));
});

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
});

test('repeated wrong passwords from one address are slowed down; another address is not', async () => {
  setup();
  let last;
  for (let i = 0; i < 11; i += 1) last = await call(login, { method: 'POST', body: { name: 'A', password: 'nope-nope' }, ip: '198.51.100.1' });
  assert.equal(last.status, 429);
  const other = await call(login, { method: 'POST', body: { name: 'A', password: 'nope-nope' }, ip: '198.51.100.2' });
  assert.equal(other.status, 401);
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
  process.env.SITE_PASSWORD = 'a-different-password';
  assert.equal(readSession(good), null, 'changing the site password signs everyone out');
});

test('a site with no password set answers 503, never "signed in"', async () => {
  setup();
  const cookie = await signIn(login);
  delete process.env.SITE_PASSWORD;
  assert.equal((await call(state, { cookie })).status, 503);
  assert.equal((await call(login, { method: 'POST', body: { name: 'A', password: '' } })).status, 503);
  process.env.SITE_PASSWORD = 'short';
  assert.equal((await call(login, { method: 'POST', body: { name: 'A', password: 'short' } })).status, 503, 'a password under 8 characters is not a password');
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

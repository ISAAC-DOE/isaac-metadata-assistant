import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { RedisStore, FileStore, MemoryStore, WRITE_SCRIPT, store, useStore } from '../lib/store.js';

/** A tiny in-memory Redis that speaks the REST batch shape the store sends. */
function fakeRedis() {
  const hashes = new Map();
  const lists = new Map();
  const strings = new Map();
  const expires = new Map();
  const calls = [];
  const run = ([cmd, key, ...rest]) => {
    if (cmd === 'HSET') return (hashes.set(key, { ...(hashes.get(key) || {}), [rest[0]]: rest[1] }), 1);
    if (cmd === 'HDEL') {
      const h = { ...(hashes.get(key) || {}) };
      delete h[rest[0]];
      hashes.set(key, h);
      return 1;
    }
    if (cmd === 'HGETALL') return Object.entries(hashes.get(key) || {}).flat();
    if (cmd === 'RPUSH') return (lists.set(key, [...(lists.get(key) || []), rest[0]]), lists.get(key).length);
    if (cmd === 'LRANGE') return lists.get(key) || [];
    if (cmd === 'EVAL') {
      // the write script, restated in JavaScript: [script, numkeys, answers, times, log, card, check, expect, answer, at, event]
      assert.equal(key, WRITE_SCRIPT);
      const [, answersKey, timesKey, logKey, cardId, check, expect, answerJson, at, eventJson] = rest;
      const times = hashes.get(timesKey) || {};
      if (check === '1' && (times[cardId] || '') !== expect) return [0, (hashes.get(answersKey) || {})[cardId] || ''];
      const answersHash = { ...(hashes.get(answersKey) || {}) };
      const timesHash = { ...times };
      if (answerJson === '') {
        delete answersHash[cardId];
        delete timesHash[cardId];
      } else {
        answersHash[cardId] = answerJson;
        timesHash[cardId] = at;
      }
      hashes.set(answersKey, answersHash);
      hashes.set(timesKey, timesHash);
      lists.set(logKey, [...(lists.get(logKey) || []), eventJson]);
      return [1, ''];
    }
    if (cmd === 'GET') return strings.has(key) ? String(strings.get(key)) : null;
    if (cmd === 'EXPIRE') return rest[1] === 'NX' && expires.has(key) ? 0 : (expires.set(key, Number(rest[0])), 1);
    if (cmd === 'INCR') return (strings.set(key, (strings.get(key) || 0) + 1), strings.get(key));
    throw new Error(`unexpected command ${cmd}`);
  };
  const fetchImpl = async (url, init) => {
    calls.push({ url, auth: init.headers.Authorization, commands: JSON.parse(init.body) });
    return { ok: true, json: async () => JSON.parse(init.body).map((c) => ({ result: run(c) })) };
  };
  return { fetchImpl, calls, expires };
}

const A = { card_id: 'C-1', action: 'value', value: 'one', typed: true, note: '', by: 'Tester', at: '2099-01-01T00:00:00Z' };

test('the Redis store keeps the current answer per card and an append-only log, atomically', async () => {
  const redis = fakeRedis();
  const s = new RedisStore('https://redis.example.test/', 'token-not-real', redis.fetchImpl);
  await s.save('b1', A);
  await s.save('b1', { ...A, value: 'two' });
  assert.deepEqual(await s.current('b1'), { 'C-1': { ...A, value: 'two' } });
  await s.clear('b1', { ...A, action: 'clear', value: null });
  assert.deepEqual(await s.current('b1'), {});
  assert.deepEqual((await s.log('b1')).map((e) => e.action), ['value', 'value', 'clear']);
  assert.deepEqual(await s.current('another-bundle'), {});
  const save = redis.calls[0];
  assert.equal(save.auth, 'Bearer token-not-real');
  assert.equal(save.commands.length, 1, 'the answer, its time and its log entry are written by one script');
  assert.deepEqual(save.commands[0].slice(0, 6), ['EVAL', WRITE_SCRIPT, '3', 'qs:b1:answers', 'qs:b1:at', 'qs:b1:log']);
});

for (const [name, make] of [
  ['memory', () => new MemoryStore()],
  ['Redis', () => new RedisStore('https://redis.example.test', 't', fakeRedis().fetchImpl)],
]) {
  test(`a write that expects an answer that is no longer there writes nothing (${name} store)`, async () => {
    const s = make();
    const B = { ...A, value: 'two', at: '2099-01-01T00:00:01Z' };
    assert.deepEqual(await s.write('b1', { card_id: 'C-1', answer: A, event: A, expect: null }), { ok: true });
    // a second writer who also saw "no answer" is refused and sent what is there
    assert.deepEqual(await s.write('b1', { card_id: 'C-1', answer: B, event: B, expect: null }), { ok: false, current: A });
    assert.deepEqual(await s.current('b1'), { 'C-1': A });
    assert.equal((await s.log('b1')).length, 1, 'a refused write leaves no log entry');
    // having seen it, the write goes through
    assert.deepEqual(await s.write('b1', { card_id: 'C-1', answer: B, event: B, expect: A.at }), { ok: true });
    // a clear with a stale time is refused; with the right one it clears
    const clear = { ...A, action: 'clear', value: null };
    assert.equal((await s.write('b1', { card_id: 'C-1', answer: null, event: clear, expect: A.at })).ok, false);
    assert.equal((await s.write('b1', { card_id: 'C-1', answer: null, event: clear, expect: B.at })).ok, true);
    assert.deepEqual(await s.current('b1'), {});
    // answering a card that was cleared under you
    assert.deepEqual(await s.write('b1', { card_id: 'C-1', answer: A, event: A, expect: B.at }), { ok: false, current: null });
    // a write with no expectation always goes through
    assert.equal((await s.write('b1', { card_id: 'C-1', answer: A, event: A })).ok, true);
  });
}

test('the write script checks, writes and logs in that order, with no step outside it', () => {
  // the script cannot be run here (no Redis); this pins its shape so a change to it is a deliberate one
  const lines = WRITE_SCRIPT.trim().split('\n').map((l) => l.trim());
  assert.equal(lines[0], "local at = redis.call('HGET', KEYS[2], ARGV[1])");
  assert.ok(lines[1].startsWith("if ARGV[2] == '1' and (at or '') ~= ARGV[3] then"));
  assert.ok(lines[2].startsWith('return {0,'), 'a mismatch returns before any write');
  const firstWrite = lines.findIndex((l) => /HSET|HDEL|RPUSH/.test(l));
  assert.ok(firstWrite > 2);
  assert.equal(lines.at(-1), "return {1, ''}");
  assert.equal(lines.filter((l) => l.includes('RPUSH')).length, 1);
});

test('the failed sign-in counter counts in one transaction and always has an expiry', async () => {
  const redis = fakeRedis();
  const s = new RedisStore('https://redis.example.test', 't', redis.fetchImpl);
  assert.equal(await s.count('login:x'), 0);
  assert.deepEqual([await s.hit('login:x', 900), await s.hit('login:x', 900), await s.hit('login:y', 900)], [1, 2, 1]);
  assert.equal(await s.count('login:x'), 2);
  const hit = redis.calls.find((c) => c.commands[0][0] === 'INCR');
  assert.equal(hit.url, 'https://redis.example.test/multi-exec', 'count and expiry are set together, so a counter can never lose its expiry');
  assert.deepEqual(hit.commands[1], ['EXPIRE', 'qs:hit:login:x', '900', 'NX']);
  assert.equal(redis.expires.get('qs:hit:login:x'), 900);
});

test('an unreachable or refusing store is a 503, never a silent success', async () => {
  const down = new RedisStore('https://redis.example.test', 't', async () => ({ ok: false, json: async () => ({}) }));
  await assert.rejects(down.save('b1', A), (err) => err.status === 503);
  const refusing = new RedisStore('https://redis.example.test', 't', async () => ({ ok: true, json: async () => [{ error: 'READONLY' }] }));
  await assert.rejects(refusing.save('b1', A), (err) => err.status === 503);
  const discarded = new RedisStore('https://redis.example.test', 't', async () => ({ ok: true, json: async () => ({ error: 'EXECABORT' }) }));
  await assert.rejects(discarded.save('b1', A), (err) => err.status === 503, 'a discarded transaction is one error object, not a list');
  const thrown = new RedisStore('https://redis.example.test', 't', async () => { throw new TypeError('fetch failed'); });
  await assert.rejects(thrown.save('b1', A), (err) => err.status === 503, 'a network failure');
  const notJson = new RedisStore('https://redis.example.test', 't', async () => ({ ok: true, json: async () => { throw new SyntaxError('x'); } }));
  await assert.rejects(notJson.current('b1'), (err) => err.status === 503);
});

test('one unreadable stored entry does not hide the other answers', async () => {
  const s = new RedisStore('https://redis.example.test', 't', async () => ({
    ok: true,
    json: async () => [{ result: ['C-1', JSON.stringify(A), 'C-2', '{not json'] }],
  }));
  assert.deepEqual(Object.keys(await s.current('b1')), ['C-1']);
  const asObject = new RedisStore('https://redis.example.test', 't', async () => ({ ok: true, json: async () => [{ result: { 'C-1': JSON.stringify(A) } }] }));
  assert.equal((await asObject.current('b1'))['C-1'].value, 'one', 'a reply shaped as an object is read too');
});

test('the file store survives a restart', async () => {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'qs-store-')), 'store.json');
  const first = new FileStore(file);
  await first.save('b1', A);
  await first.clear('b1', { ...A, action: 'clear' });
  await first.save('b1', { ...A, value: 'kept' });
  const second = new FileStore(file);
  assert.equal((await second.current('b1'))['C-1'].value, 'kept');
  assert.equal((await second.log('b1')).length, 3);
});

test('a deployed site with no store configured refuses to save', () => {
  useStore(null);
  const keep = { ...process.env };
  for (const k of ['KV_REST_API_URL', 'KV_REST_API_TOKEN', 'UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN']) delete process.env[k];
  try {
    delete process.env.QUESTION_SITE_DEV_STORE;
    assert.throws(() => store(), (err) => err.status === 503);
    // the dev file store is never used on Vercel, whatever the environment says
    process.env.QUESTION_SITE_DEV_STORE = '/tmp/should-not-be-used.json';
    process.env.VERCEL = '1';
    assert.throws(() => store(), (err) => err.status === 503);
  } finally {
    process.env = keep;
    useStore(null);
  }
});

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { RedisStore, FileStore, store, useStore } from '../lib/store.js';

/** A tiny in-memory Redis that speaks the REST batch shape the store sends. */
function fakeRedis() {
  const hashes = new Map();
  const lists = new Map();
  const strings = new Map();
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
    if (cmd === 'SET') return strings.has(key) ? null : (strings.set(key, Number(rest[0])), 'OK');
    if (cmd === 'INCR') return (strings.set(key, (strings.get(key) || 0) + 1), strings.get(key));
    throw new Error(`unexpected command ${cmd}`);
  };
  const fetchImpl = async (url, init) => {
    calls.push({ url, auth: init.headers.Authorization, commands: JSON.parse(init.body) });
    return { ok: true, json: async () => JSON.parse(init.body).map((c) => ({ result: run(c) })) };
  };
  return { fetchImpl, calls };
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
  assert.equal(save.url, 'https://redis.example.test/multi-exec', 'the answer and its log entry are written together');
  assert.equal(save.auth, 'Bearer token-not-real');
  assert.deepEqual(save.commands.map((c) => c[0]), ['HSET', 'RPUSH']);
  assert.equal(save.commands[0][1], 'qs:b1:answers');
});

test('the failed sign-in counter counts within its window', async () => {
  const redis = fakeRedis();
  const s = new RedisStore('https://redis.example.test', 't', redis.fetchImpl);
  assert.deepEqual([await s.hit('login:x', 900), await s.hit('login:x', 900), await s.hit('login:y', 900)], [1, 2, 1]);
});

test('an unreachable or refusing store is a 503, never a silent success', async () => {
  const down = new RedisStore('https://redis.example.test', 't', async () => ({ ok: false, json: async () => ({}) }));
  await assert.rejects(down.save('b1', A), (err) => err.status === 503);
  const refusing = new RedisStore('https://redis.example.test', 't', async () => ({ ok: true, json: async () => [{ error: 'READONLY' }] }));
  await assert.rejects(refusing.save('b1', A), (err) => err.status === 503);
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

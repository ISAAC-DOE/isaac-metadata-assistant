// Where answers are kept. Three stores with one interface:
//
//   * Redis over REST (Upstash, added from the Vercel project's Storage tab): the real one.
//   * a JSON file: the local dev server.
//   * memory: the tests.
//
// A deployed site with no store configured refuses to save (503). It never pretends an answer was kept.
//
// Interface (all async):
//   current(bundleId)                 -> { [card_id]: answer }
//   write(bundleId, { card_id, answer, event, expect })
//                                     -> { ok: true } | { ok: false, current }
//       Sets the card's current answer (or removes it when `answer` is null) and appends `event` to the log, in one
//       step. With `expect` given (the time of the answer the writer saw, or null for "no answer"), nothing is
//       written unless that is still the card's current answer; the answer that is there comes back instead.
//   save(bundleId, answer) / clear(bundleId, event): `write` without `expect`.
//   log(bundleId)                     -> [event]           (every save and clear, oldest first)
//   hit(key, windowSeconds)           -> number            (count one more in a window that expires: failed sign-ins)
//   count(key)                        -> number            (the current count, without adding to it)

import fs from 'node:fs/promises';
import { HttpError } from './http.js';

export class MemoryStore {
  constructor() {
    this.answers = new Map();
    this.logs = new Map();
    this.hits = new Map();
  }
  async current(bundleId) {
    return { ...(this.answers.get(bundleId) || {}) };
  }
  async write(bundleId, { card_id, answer, event, expect }) {
    const cur = { ...(this.answers.get(bundleId) || {}) };
    const current = cur[card_id] || null;
    if (expect !== undefined && (current ? current.at : null) !== expect) return { ok: false, current };
    if (answer) cur[card_id] = answer;
    else delete cur[card_id];
    this.answers.set(bundleId, cur);
    this.logs.set(bundleId, [...(this.logs.get(bundleId) || []), event]);
    return { ok: true };
  }
  async save(bundleId, answer) {
    await this.write(bundleId, { card_id: answer.card_id, answer, event: answer });
    return answer;
  }
  async clear(bundleId, event) {
    await this.write(bundleId, { card_id: event.card_id, answer: null, event });
  }
  async log(bundleId) {
    return [...(this.logs.get(bundleId) || [])];
  }
  async count(key, now = Date.now()) {
    const cur = this.hits.get(key);
    return cur && cur.until >= now ? cur.n : 0;
  }
  async hit(key, windowSeconds, now = Date.now()) {
    const cur = this.hits.get(key);
    if (!cur || cur.until < now) {
      this.hits.set(key, { n: 1, until: now + windowSeconds * 1000 });
      return 1;
    }
    cur.n += 1;
    return cur.n;
  }
}

/** The dev server's store: the memory store, written to one JSON file after every change. */
export class FileStore extends MemoryStore {
  constructor(path) {
    super();
    this.path = path;
    this.loaded = null;
  }
  async #load() {
    if (!this.loaded) {
      this.loaded = (async () => {
        try {
          const raw = JSON.parse(await fs.readFile(this.path, 'utf8'));
          this.answers = new Map(Object.entries(raw.answers || {}));
          this.logs = new Map(Object.entries(raw.logs || {}));
        } catch (err) {
          if (err.code !== 'ENOENT') throw err;
        }
      })();
    }
    return this.loaded;
  }
  async #flush() {
    const body = JSON.stringify(
      { answers: Object.fromEntries(this.answers), logs: Object.fromEntries(this.logs) },
      null,
      1,
    );
    const tmp = `${this.path}.tmp`;
    await fs.writeFile(tmp, body);
    await fs.rename(tmp, this.path);
  }
  async current(bundleId) {
    await this.#load();
    return super.current(bundleId);
  }
  async write(bundleId, change) {
    await this.#load();
    const out = await super.write(bundleId, change);
    if (out.ok) await this.#flush();
    return out;
  }
  async log(bundleId) {
    await this.#load();
    return super.log(bundleId);
  }
}

// One write, done inside Redis so nothing can slip in between the check and the write.
//   KEYS: the answers hash, the hash of each card's current answer time, the log list
//   ARGV: card id, "1" to check / "0" not to, the expected time ("" for no answer), the answer as JSON ("" to
//         clear), the answer's time, the log event as JSON
// Returns {1, ""} when written, or {0, <the current answer as JSON, or "">} when the expected time did not match.
export const WRITE_SCRIPT = `
local at = redis.call('HGET', KEYS[2], ARGV[1])
if ARGV[2] == '1' and (at or '') ~= ARGV[3] then
  return {0, redis.call('HGET', KEYS[1], ARGV[1]) or ''}
end
if ARGV[4] == '' then
  redis.call('HDEL', KEYS[1], ARGV[1])
  redis.call('HDEL', KEYS[2], ARGV[1])
else
  redis.call('HSET', KEYS[1], ARGV[1], ARGV[4])
  redis.call('HSET', KEYS[2], ARGV[1], ARGV[5])
end
redis.call('RPUSH', KEYS[3], ARGV[6])
return {1, ''}
`;

/** Upstash Redis over its REST API: no client library, one POST per command batch. */
export class RedisStore {
  constructor(url, token, fetchImpl = fetch) {
    this.url = url.replace(/\/+$/, '');
    this.token = token;
    this.fetch = fetchImpl;
  }
  async #run(commands, atomic = false) {
    let res;
    try {
      res = await this.fetch(`${this.url}/${atomic ? 'multi-exec' : 'pipeline'}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(commands),
        signal: AbortSignal.timeout(3000),
      });
    } catch {
      throw new HttpError(503, 'The answer store is not reachable right now. Please try again.');
    }
    if (!res.ok) throw new HttpError(503, 'The answer store is not reachable right now. Please try again.');
    const out = await res.json().catch(() => null);
    // a discarded transaction comes back as one {error} object, not a list
    if (!Array.isArray(out) || out.length !== commands.length) {
      throw new HttpError(503, 'The answer store refused that. Please try again.');
    }
    for (const item of out) {
      if (!item || item.error) throw new HttpError(503, 'The answer store refused that. Please try again.');
    }
    return out.map((item) => item.result);
  }
  #ak(bundleId) {
    return `qs:${bundleId}:answers`;
  }
  #lk(bundleId) {
    return `qs:${bundleId}:log`;
  }
  async current(bundleId) {
    const [raw] = await this.#run([['HGETALL', this.#ak(bundleId)]]);
    // HGETALL over REST is a flat [field, value, field, value, …] list; accept an object too
    const pairs = Array.isArray(raw)
      ? raw.reduce((acc, x, i) => (i % 2 ? acc : [...acc, [x, raw[i + 1]]]), [])
      : Object.entries(raw || {});
    const out = {};
    for (const [field, value] of pairs) {
      try {
        out[field] = typeof value === 'string' ? JSON.parse(value) : value;
      } catch {
        // one unreadable entry must not hide every other answer; the log still holds what was saved
      }
    }
    return out;
  }
  async write(bundleId, { card_id, answer, event, expect }) {
    const [reply] = await this.#run([
      [
        'EVAL',
        WRITE_SCRIPT,
        '3',
        this.#ak(bundleId),
        `qs:${bundleId}:at`,
        this.#lk(bundleId),
        card_id,
        expect === undefined ? '0' : '1',
        expect || '',
        answer ? JSON.stringify(answer) : '',
        answer ? answer.at : '',
        JSON.stringify(event),
      ],
    ]);
    if (!Array.isArray(reply)) throw new HttpError(503, 'The answer store refused that. Please try again.');
    if (Number(reply[0]) === 1) return { ok: true };
    let current = null;
    try {
      current = reply[1] ? JSON.parse(reply[1]) : null;
    } catch {
      /* unreadable: report "something else is there" without it */
    }
    return { ok: false, current };
  }
  async save(bundleId, answer) {
    await this.write(bundleId, { card_id: answer.card_id, answer, event: answer });
    return answer;
  }
  async clear(bundleId, event) {
    await this.write(bundleId, { card_id: event.card_id, answer: null, event });
  }
  async log(bundleId) {
    const [items] = await this.#run([['LRANGE', this.#lk(bundleId), '0', '-1']]);
    const out = [];
    for (const x of items || []) {
      try {
        out.push(typeof x === 'string' ? JSON.parse(x) : x);
      } catch {
        out.push({ unreadable: String(x).slice(0, 200) });
      }
    }
    return out;
  }
  async count(key) {
    const [n] = await this.#run([['GET', `qs:hit:${key}`]]);
    return Number(n) || 0;
  }
  async hit(key, windowSeconds) {
    const k = `qs:hit:${key}`;
    // one transaction: count this hit, and start the window only if none is running
    const [n] = await this.#run(
      [
        ['INCR', k],
        ['EXPIRE', k, String(windowSeconds), 'NX'],
      ],
      true,
    );
    return Number(n);
  }
}

let cached = null;

/** The store this deployment uses. Tests call `useStore(new MemoryStore())` first. */
export function store() {
  if (cached) return cached;
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (url && token) cached = new RedisStore(url, token);
  else if (process.env.QUESTION_SITE_DEV_STORE && !process.env.VERCEL) {
    cached = new FileStore(process.env.QUESTION_SITE_DEV_STORE);
  } else {
    throw new HttpError(503, 'The site is not set up yet: it has nowhere to keep answers.');
  }
  return cached;
}

export function useStore(s) {
  cached = s;
}

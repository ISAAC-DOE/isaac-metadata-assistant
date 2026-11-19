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
//   save(bundleId, answer)            -> answer            (replaces the card's current answer, appends to the log)
//   clear(bundleId, event)            -> void              (removes the card's current answer, appends to the log)
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
  async save(bundleId, answer) {
    this.answers.set(bundleId, { ...(this.answers.get(bundleId) || {}), [answer.card_id]: answer });
    this.logs.set(bundleId, [...(this.logs.get(bundleId) || []), answer]);
    return answer;
  }
  async clear(bundleId, event) {
    const cur = { ...(this.answers.get(bundleId) || {}) };
    delete cur[event.card_id];
    this.answers.set(bundleId, cur);
    this.logs.set(bundleId, [...(this.logs.get(bundleId) || []), event]);
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
  async save(bundleId, answer) {
    await this.#load();
    await super.save(bundleId, answer);
    await this.#flush();
    return answer;
  }
  async clear(bundleId, event) {
    await this.#load();
    await super.clear(bundleId, event);
    await this.#flush();
  }
  async log(bundleId) {
    await this.#load();
    return super.log(bundleId);
  }
}

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
        signal: AbortSignal.timeout(5000),
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
  async save(bundleId, answer) {
    const body = JSON.stringify(answer);
    await this.#run(
      [
        ['HSET', this.#ak(bundleId), answer.card_id, body],
        ['RPUSH', this.#lk(bundleId), body],
      ],
      true,
    );
    return answer;
  }
  async clear(bundleId, event) {
    await this.#run(
      [
        ['HDEL', this.#ak(bundleId), event.card_id],
        ['RPUSH', this.#lk(bundleId), JSON.stringify(event)],
      ],
      true,
    );
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

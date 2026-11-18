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
//   hit(key, windowSeconds)           -> number            (a counter that expires: failed sign-ins)

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
    const res = await this.fetch(`${this.url}/${atomic ? 'multi-exec' : 'pipeline'}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(commands),
    });
    if (!res.ok) throw new HttpError(503, 'The answer store is not reachable right now. Please try again.');
    const out = await res.json();
    for (const item of out) {
      if (item && item.error) throw new HttpError(503, 'The answer store refused that. Please try again.');
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
    const [flat] = await this.#run([['HGETALL', this.#ak(bundleId)]]);
    const out = {};
    // HGETALL over REST is a flat [field, value, field, value, …] list
    for (let i = 0; i + 1 < (flat || []).length; i += 2) out[flat[i]] = JSON.parse(flat[i + 1]);
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
    return (items || []).map((x) => JSON.parse(x));
  }
  async hit(key, windowSeconds) {
    const k = `qs:hit:${key}`;
    // SET … NX starts the window only if no count is running; INCR then counts this hit
    const [, n] = await this.#run([
      ['SET', k, '0', 'EX', String(windowSeconds), 'NX'],
      ['INCR', k],
    ]);
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

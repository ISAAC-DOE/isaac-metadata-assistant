// Test helpers: call a handler the way a host would, with a fake request and response.

import { Readable } from 'node:stream';
import { fixtureDataDir } from './fixture-data.js';
import { MemoryStore, useStore } from '../lib/store.js';
import { resetDataCache } from '../lib/data.js';

export const FIXTURES = fixtureDataDir();
export const PASSWORD = 'test-password-not-real';

export function setup() {
  process.env.SITE_PASSWORD = PASSWORD;
  process.env.QUESTION_SITE_DATA_DIR = FIXTURES;
  delete process.env.SESSION_SECRET;
  const store = new MemoryStore();
  useStore(store);
  resetDataCache();
  return store;
}

export async function call(handler, { method = 'GET', url = '/', body, cookie, headers = {}, ip = '203.0.113.7' } = {}) {
  const payload = body === undefined ? [] : [Buffer.from(typeof body === 'string' ? body : JSON.stringify(body))];
  const req = Readable.from(payload);
  req.method = method;
  req.url = url;
  req.headers = { host: 'questions.example.test', 'x-forwarded-for': ip, ...headers };
  if (body !== undefined && !('content-type' in req.headers)) req.headers['content-type'] = 'application/json';
  if (cookie) req.headers.cookie = cookie;
  req.socket = { remoteAddress: ip };
  const res = {
    statusCode: 200,
    headers: {},
    body: null,
    setHeader(k, v) {
      this.headers[k.toLowerCase()] = v;
    },
    getHeader(k) {
      return this.headers[k.toLowerCase()];
    },
    end(chunk) {
      this.body = chunk === undefined ? null : chunk;
    },
  };
  await handler(req, res);
  let json = null;
  if (res.body && !Buffer.isBuffer(res.body)) {
    try {
      json = JSON.parse(res.body);
    } catch {
      /* not JSON */
    }
  }
  return { status: res.statusCode, headers: res.headers, body: res.body, json };
}

/** Sign in and return the session cookie as a request would send it. */
export async function signIn(login, name = 'Test Person') {
  const out = await call(login, { method: 'POST', body: { name, password: PASSWORD } });
  if (out.status !== 200) throw new Error(`sign-in failed: ${out.status}`);
  return String(out.headers['set-cookie']).split(';')[0];
}

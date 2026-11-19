// Small request/response helpers that work the same on Vercel's Node functions, the local dev server and the tests.
// Handlers use only what plain `http.IncomingMessage` / `http.ServerResponse` give, plus `req.body` when the host
// has already parsed it.

const MAX_BODY = 64 * 1024;

export class HttpError extends Error {
  constructor(status, message, extra = {}) {
    super(message);
    this.status = status;
    this.extra = extra;
  }
}

export function send(res, status, body, headers = {}) {
  res.statusCode = status;
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Robots-Tag', 'noindex, nofollow, noarchive');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  for (const [k, v] of Object.entries(headers)) res.setHeader(k, v);
  if (body === undefined || body === null) return res.end();
  if (Buffer.isBuffer(body)) return res.end(body);
  if (!res.getHeader('Content-Type')) res.setHeader('Content-Type', 'application/json; charset=utf-8');
  return res.end(typeof body === 'string' ? body : JSON.stringify(body));
}

/** The JSON body of a POST. Refuses anything that is not a JSON object, and anything large. */
export async function readJson(req) {
  const type = String(req.headers['content-type'] || '').split(';')[0].trim().toLowerCase();
  if (type !== 'application/json') throw new HttpError(415, 'Send JSON.');
  let body;
  try {
    body = req.body; // Vercel parses the body lazily here, and throws on malformed JSON
  } catch {
    throw new HttpError(400, 'That is not valid JSON.');
  }
  if (body === undefined) {
    const chunks = [];
    let size = 0;
    for await (const chunk of req) {
      size += chunk.length;
      if (size > MAX_BODY) throw new HttpError(413, 'That is too large.');
      chunks.push(chunk);
    }
    body = Buffer.concat(chunks).toString('utf8');
  }
  if (Buffer.isBuffer(body)) body = body.toString('utf8');
  if (typeof body === 'string') {
    if (body.length > MAX_BODY) throw new HttpError(413, 'That is too large.');
    try {
      body = JSON.parse(body || '{}');
    } catch {
      throw new HttpError(400, 'That is not valid JSON.');
    }
  }
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw new HttpError(400, 'Send a JSON object.');
  // a body the host parsed for us never passed the size check above
  if (JSON.stringify(body).length > MAX_BODY) throw new HttpError(413, 'That is too large.');
  return body;
}

export function query(req) {
  const url = new URL(req.url || '/', 'http://local');
  return url.searchParams;
}

export function clientIp(req) {
  const fwd = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
  return fwd || req.socket?.remoteAddress || 'unknown';
}

/**
 * A state-changing request must come from this site's own pages. Browsers send `Origin` on every POST; a request
 * whose Origin names another host is refused. (The session cookie is also SameSite=Strict.)
 */
export function requireSameOrigin(req) {
  const origin = req.headers.origin;
  if (!origin) return; // a non-browser client (curl, the tests): the cookie alone decides
  let host;
  try {
    host = new URL(origin).host;
  } catch {
    throw new HttpError(403, 'Refused.');
  }
  const own = String(req.headers['x-forwarded-host'] || req.headers.host || '');
  if (host !== own) throw new HttpError(403, 'Refused.');
}

/** Wraps a handler: one method, errors as JSON, never a stack trace. */
export function handler(method, fn) {
  return async (req, res) => {
    try {
      if (req.method !== method) {
        return send(res, 405, { error: 'Method not allowed.' }, { Allow: method });
      }
      if (method !== 'GET') requireSameOrigin(req);
      return await fn(req, res);
    } catch (err) {
      if (err instanceof HttpError) return send(res, err.status, { error: err.message, ...err.extra });
      console.error(err);
      return send(res, 500, { error: 'Something went wrong on the site. Your earlier answers are safe.' });
    }
  };
}

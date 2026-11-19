import { handler, readJson, send, clientIp, HttpError } from '../lib/http.js';
import { sitePassword, sameSecret, cleanName, makeSession, sessionCookie } from '../lib/auth.js';
import { store } from '../lib/store.js';

// Ten wrong passwords from one address lock that address out for 15 minutes. While it is locked out, every try
// is refused, the right password included: otherwise the refusal itself would tell a guesser right from wrong.
const PER_ADDRESS = 10;
const WINDOW = 15 * 60;

// Addresses this instance already knows are locked out, so repeat tries cost the answer store nothing.
const locked = new Map();

function refuse() {
  throw new HttpError(429, 'Too many tries. Please wait 15 minutes and try again.', { retry_after: WINDOW });
}

export default handler('POST', async (req, res) => {
  const expected = sitePassword();
  const body = await readJson(req);
  const name = cleanName(body.name);
  const given = typeof body.password === 'string' ? body.password : '';
  const ip = clientIp(req);
  const key = `login:${ip}`;
  const now = Date.now();

  if ((locked.get(ip) || 0) > now) refuse();
  const s = store();
  // a store that cannot be read is a 503 for everyone: a sign-in is never let through unchecked
  if ((await s.count(key)) >= PER_ADDRESS) {
    locked.set(ip, now + 60_000);
    refuse();
  }
  if (!sameSecret(given, expected)) {
    const n = await s.hit(key, WINDOW);
    if (n >= PER_ADDRESS) locked.set(ip, now + 60_000);
    throw new HttpError(401, 'That password is not right.');
  }
  return send(res, 200, { name }, { 'Set-Cookie': sessionCookie(req, makeSession(name)) });
});

/** For the tests: forget which addresses this instance has locked out. */
export function forgetLockouts() {
  locked.clear();
}

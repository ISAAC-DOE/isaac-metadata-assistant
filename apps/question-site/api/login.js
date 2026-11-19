import { handler, readJson, send, clientIp, HttpError } from '../lib/http.js';
import { sitePassword, sameSecret, cleanName, makeSession, sessionCookie } from '../lib/auth.js';
import { store } from '../lib/store.js';

// Ten tries from one address in 15 minutes, right or wrong; after that every try is refused until the window ends,
// the right password included: otherwise the refusal itself would tell a guesser right from wrong.
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

  for (const [addr, until] of locked) if (until <= now) locked.delete(addr);
  if (locked.has(ip)) refuse();
  // Count the try before looking at the password, in one step in the store. Tries sent all at once each get their
  // own number, so only the first ten in a window are ever compared; a store that cannot count signs nobody in.
  const n = await store().hit(key, WINDOW);
  if (n > PER_ADDRESS) {
    locked.set(ip, now + 60_000);
    refuse();
  }
  if (!sameSecret(given, expected)) throw new HttpError(401, 'That password is not right.');
  return send(res, 200, { name }, { 'Set-Cookie': sessionCookie(req, makeSession(name)) });
});

/** For the tests: forget which addresses this instance has locked out. */
export function forgetLockouts() {
  locked.clear();
}

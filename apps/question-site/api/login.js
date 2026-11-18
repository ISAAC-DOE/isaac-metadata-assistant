import { handler, readJson, send, clientIp, HttpError } from '../lib/http.js';
import { sitePassword, sameSecret, cleanName, makeSession, sessionCookie } from '../lib/auth.js';
import { store } from '../lib/store.js';

// Wrong passwords from one address: 10 in 15 minutes, then a wait. Across all addresses: 300 an hour.
const PER_IP = 10;
const PER_IP_WINDOW = 15 * 60;
const GLOBAL = 300;
const GLOBAL_WINDOW = 60 * 60;

export default handler('POST', async (req, res) => {
  const expected = sitePassword();
  const body = await readJson(req);
  const name = cleanName(body.name);
  const given = typeof body.password === 'string' ? body.password : '';
  if (!sameSecret(given, expected)) {
    const s = store();
    const [mine, all] = await Promise.all([
      s.hit(`login:${clientIp(req)}`, PER_IP_WINDOW),
      s.hit('login:all', GLOBAL_WINDOW),
    ]);
    if (mine > PER_IP || all > GLOBAL) {
      throw new HttpError(429, 'Too many tries. Please wait 15 minutes and try again.');
    }
    throw new HttpError(401, 'That password is not right.');
  }
  return send(res, 200, { name }, { 'Set-Cookie': sessionCookie(req, makeSession(name)) });
});

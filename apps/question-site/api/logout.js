import { handler, send } from '../lib/http.js';
import { clearCookie } from '../lib/auth.js';

export default handler('POST', async (req, res) => send(res, 200, { ok: true }, { 'Set-Cookie': clearCookie(req) }));

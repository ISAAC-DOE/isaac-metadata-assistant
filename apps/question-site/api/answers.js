import { handler, send } from '../lib/http.js';
import { requireSession } from '../lib/auth.js';
import { siteData, ANSWERS_FORMAT, FORMAT_VERSION } from '../lib/data.js';
import { store } from '../lib/store.js';

// The download: every current answer and the full log, in the shape `isaac bundle site import` reads.
export default handler('GET', async (req, res) => {
  requireSession(req);
  const { raw } = await siteData();
  const s = store();
  const [current, log] = await Promise.all([s.current(raw.bundle_id), s.log(raw.bundle_id)]);
  const answers = Object.values(current).sort((a, b) => String(a.at).localeCompare(String(b.at)));
  const body = {
    format: ANSWERS_FORMAT,
    format_version: FORMAT_VERSION,
    bundle_id: raw.bundle_id,
    bundle_version: raw.bundle_version ?? null,
    exported_at: new Date().toISOString(),
    answers,
    log,
  };
  const day = body.exported_at.slice(0, 10);
  return send(res, 200, JSON.stringify(body, null, 1), {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Disposition': `attachment; filename="answers-${day}.json"`,
  });
});

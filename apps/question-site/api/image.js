import { handler, send, query } from '../lib/http.js';
import { requireSession } from '../lib/auth.js';
import { readImage } from '../lib/data.js';

// One exported image (a curve, a photo from the logbook), for a signed-in reader only.
export default handler('GET', async (req, res) => {
  requireSession(req);
  const { body, type } = await readImage(query(req).get('f'));
  return send(res, 200, body, { 'Content-Type': type, 'Cache-Control': 'private, max-age=3600' });
});

import { handler, readJson, send, HttpError } from '../lib/http.js';
import { requireSession } from '../lib/auth.js';
import { siteData } from '../lib/data.js';
import { buildAnswer } from '../lib/answers.js';
import { store } from '../lib/store.js';

// Save one answer (or clear it). The answer is stored before the response is sent, so "Saved" on the page is true.
export default handler('POST', async (req, res) => {
  const session = requireSession(req);
  const body = await readJson(req);
  const { raw, byId } = await siteData();
  const card = byId.get(body.card_id);
  if (!card) throw new HttpError(404, 'That question is no longer on this site. Reload the page.');
  const at = new Date().toISOString();
  if (body.action === 'clear') {
    await store().clear(raw.bundle_id, { card_id: card.card_id, action: 'clear', value: null, typed: false, note: '', by: session.name, at });
    return send(res, 200, { card_id: card.card_id, answer: null });
  }
  const answer = buildAnswer(card, body, session.name, at);
  await store().save(raw.bundle_id, answer);
  return send(res, 200, { card_id: card.card_id, answer });
});

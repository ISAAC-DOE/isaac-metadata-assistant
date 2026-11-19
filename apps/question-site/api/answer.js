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
  const current = (await store().current(raw.bundle_id))[card.card_id] || null;
  // The page says which saved answer it was looking at (`seen_at`: that answer's time, or null for none). If
  // someone else has answered or changed this card since, nothing is overwritten: the page is sent what is there.
  if ('seen_at' in body && (current ? current.at : null) !== (body.seen_at ?? null)) {
    return send(res, 409, {
      error: current
        ? `${current.by} answered this while you had the page open. Have a look at their answer first.`
        : 'This answer was cleared while you had the page open. Have a look and answer again.',
      card_id: card.card_id,
      answer: current,
    });
  }
  // an answer's time is also what tells two versions of it apart, so it always moves forward for a card
  let now = Date.now();
  const last = current ? Date.parse(current.at) : NaN;
  if (Number.isFinite(last) && now <= last) now = last + 1;
  const at = new Date(now).toISOString();
  if (body.action === 'clear') {
    await store().clear(raw.bundle_id, { card_id: card.card_id, action: 'clear', value: null, typed: false, note: '', by: session.name, at });
    return send(res, 200, { card_id: card.card_id, answer: null });
  }
  const answer = buildAnswer(card, body, session.name, at);
  await store().save(raw.bundle_id, answer);
  return send(res, 200, { card_id: card.card_id, answer });
});

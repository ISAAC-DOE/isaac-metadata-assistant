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

  // The page says which saved answer it was looking at (`seen_at`: that answer's time, or null for none). The store
  // writes only if that is still the card's answer, in one step; otherwise nothing is overwritten and the page is
  // sent what is there.
  const checked = 'seen_at' in body;
  const seen = checked && typeof body.seen_at === 'string' ? body.seen_at : null;
  // an answer's time is also what tells two versions of it apart, so it always moves forward for a card
  let now = Date.now();
  const last = seen ? Date.parse(seen) : NaN;
  if (Number.isFinite(last) && now <= last) now = last + 1;
  const at = new Date(now).toISOString();

  const clearing = body.action === 'clear';
  const answer = clearing ? null : buildAnswer(card, body, session.name, at);
  const event = clearing
    ? { card_id: card.card_id, action: 'clear', value: null, typed: false, note: '', by: session.name, at }
    : answer;
  const out = await store().write(raw.bundle_id, {
    card_id: card.card_id,
    answer,
    event,
    expect: checked ? seen : undefined,
  });
  if (!out.ok) {
    return send(res, 409, {
      error: out.current
        ? `${out.current.by} answered this while you had the page open. Have a look at their answer first.`
        : 'This answer was cleared while you had the page open. Have a look and answer again.',
      card_id: card.card_id,
      answer: out.current,
    });
  }
  return send(res, 200, { card_id: card.card_id, answer });
});

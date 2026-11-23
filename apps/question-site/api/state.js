import { handler, send } from '../lib/http.js';
import { requireSession } from '../lib/auth.js';
import { siteData, publicCard } from '../lib/data.js';
import { store } from '../lib/store.js';

// Everything the page needs in one request: who is signed in, the cards, and every current answer.
export default handler('GET', async (req, res) => {
  const session = requireSession(req);
  const { raw } = await siteData();
  const answers = await store().current(raw.bundle_id);
  return send(res, 200, {
    name: session.name,
    site: {
      title: raw.title || 'Beamtime questions',
      generated_at: raw.generated_at || null,
      totals: raw.totals || null,
      sections: raw.sections || [],
      beamtime: raw.beamtime || null,
    },
    cards: raw.cards.map(publicCard),
    answers,
  });
});

// The page's pure logic, kept apart from the DOM so the tests can run it in Node.

export const CONFIDENCE = {
  high: 'Well supported',
  medium: 'Likely, please check',
  low: 'A guess, please check',
};

export const BASIS = {
  files: 'from your files',
  logbook: 'from your logbook',
  reading: 'from a reading of your logbook',
  earlier_answer: 'from an answer given on an earlier beamtime',
  rule: 'from a stated rule',
  general_knowledge: 'from general knowledge, not from your files',
};

function same(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * An accepted suggestion that is no longer the suggestion. The person said yes to something the site has since
 * replaced, so the card is open again: it is asked again and never shown as "your current answer".
 */
export function isStale(card, answer) {
  if (!answer || answer.action !== 'accept') return false;
  return !card.suggestion || !same(card.suggestion.value, answer.value);
}

/** The card's answer if it still stands, else null. */
export function standing(card, answers) {
  const a = answers[card.card_id];
  return a && !isStale(card, a) ? a : null;
}

/** A saved answer in the words the person chose it in. */
export function describeAnswer(card, answer) {
  if (!answer) return '';
  if (answer.action === 'dont_know') return 'Don’t know';
  const kind = card.answer?.kind;
  if (kind === 'yes_no' && typeof answer.value === 'boolean') return answer.value ? 'Yes' : 'No';
  if (answer.action === 'accept' && card.suggestion && same(card.suggestion.value, answer.value)) {
    return card.suggestion.label ?? String(answer.value);
  }
  const option = (card.answer?.options || []).find((o) => same(o.value, answer.value));
  if (option) return option.label ?? String(option.value);
  const unit = card.answer?.unit;
  return unit ? `${answer.value} ${unit}` : String(answer.value);
}

/** Counts for the progress bars. "Needed" cards block export; the rest are nice to have. */
export function tally(cards, answers) {
  const needed = cards.filter((c) => c.blocking);
  const optional = cards.filter((c) => !c.blocking);
  const done = (list) => list.filter((c) => standing(c, answers)).length;
  const unsure = (list) => list.filter((c) => standing(c, answers)?.action === 'dont_know').length;
  const neededDone = done(needed);
  const optionalDone = done(optional);
  return {
    needed: needed.length,
    neededDone, // answered or marked "don't know": nothing left for the person to do
    neededUnsure: unsure(needed), // of those, the ones still without a value
    neededOpen: needed.length - neededDone,
    optional: optional.length,
    optionalDone,
    open: cards.length - neededDone - optionalDone,
  };
}

/** Whether a saved answer was given by someone other than `me` (names compared without case or extra spaces). */
export function byOther(answer, me) {
  const norm = (s) => String(s || '').trim().replace(/\s+/g, ' ').toLowerCase();
  return Boolean(answer && me && norm(answer.by) !== norm(me));
}

/**
 * The note to save when a person replaces someone else's answer: their own note, with the earlier person's note kept
 * after it under that person's name, so the replaced note is neither lost nor put in the new person's words.
 */
export function carryNote(mine, before, me) {
  const own = String(mine || '').trim();
  const earlier = before && byOther(before, me) ? String(before.note || '').trim() : '';
  if (!earlier || own.includes(earlier)) return own;
  const kept = `Earlier note from ${String(before.by).trim()}: ${earlier}`;
  return (own ? `${own}\n\n${kept}` : kept).slice(0, 2000);
}

/** The key that remembers "I looked at this answer of someone else's and kept it": a new answer asks again. */
export function keptKey(answer) {
  return answer ? `${answer.card_id}@${answer.at}` : '';
}

/**
 * The next cards to answer: the open ones in the site's own order (needed first, widest reach first). A card marked
 * "don't know" is not offered again: a person who said they do not know should not be asked in a loop.
 * With `me` given, the cards someone else answered come after the open ones, so the person can keep that answer,
 * change it or add a note; `kept` holds the ones they already looked at and kept.
 */
export function pickRun(cards, answers, size, me = null, kept = new Set()) {
  const open = cards.filter((c) => !standing(c, answers));
  const needed = open.filter((c) => c.blocking);
  const rest = open.filter((c) => !c.blocking);
  const others = cards.filter((c) => {
    const a = standing(c, answers);
    return byOther(a, me) && !kept.has(keptKey(a));
  });
  return [...needed, ...rest, ...others].slice(0, Math.max(1, size)).map((c) => c.card_id);
}

/**
 * Whether a single-letter shortcut may act now. Never while something is typed, never straight after the card was
 * redrawn (a key meant for the last card), never while a save is running, and "yes" / "don't know" never replace an
 * answer that already stands: changing an answer takes a click.
 */
export function shortcutAllowed({ key, enabled, busy, msSinceRender, typedText, noteText, hasAnswer }) {
  if (!enabled || busy) return false;
  if (msSinceRender < 400) return false;
  if ((typedText || '').trim() || (noteText || '').trim()) return false;
  if ((key === 'y' || key === 'd') && hasAnswer) return false;
  return true;
}

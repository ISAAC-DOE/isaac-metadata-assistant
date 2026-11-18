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
  const done = (list) => list.filter((c) => answers[c.card_id]).length;
  const neededDone = done(needed);
  const optionalDone = done(optional);
  return {
    needed: needed.length,
    neededDone,
    neededOpen: needed.length - neededDone,
    optional: optional.length,
    optionalDone,
    open: cards.length - neededDone - optionalDone,
  };
}

/**
 * The next cards to answer: unanswered ones in the site's own order (needed first, widest reach first), then, when
 * nothing unanswered is left among the needed ones, the ones marked "don't know" are NOT offered again: a person
 * who said they do not know should not be asked in a loop.
 */
export function pickRun(cards, answers, size) {
  const open = cards.filter((c) => !answers[c.card_id]);
  const needed = open.filter((c) => c.blocking);
  const rest = open.filter((c) => !c.blocking);
  return [...needed, ...rest].slice(0, Math.max(1, size)).map((c) => c.card_id);
}

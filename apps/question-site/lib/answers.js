// What a saved answer may be. The site checks an answer against the card it is for, so that what is stored can be
// imported: the import (`isaac bundle site import`) checks everything again through the bundle's own decide path.

import { HttpError } from './http.js';

export const ACTIONS = ['accept', 'value', 'dont_know'];
const VALUE_MAX = 500;
const NOTE_MAX = 2000;

function text(raw, max, what) {
  if (raw === undefined || raw === null) return '';
  if (typeof raw !== 'string') throw new HttpError(400, `The ${what} must be text.`);
  const out = raw.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '').trim();
  if (out.length > max) throw new HttpError(400, `Please keep the ${what} under ${max} characters.`);
  return out;
}

function sameValue(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * The answer to store for `card`, from a request body. Throws a 400 that says what is wrong.
 * `by` and `at` come from the session and the clock, never from the body.
 */
export function buildAnswer(card, body, by, at) {
  const action = body.action;
  if (!ACTIONS.includes(action)) throw new HttpError(400, 'That is not an answer this site records.');
  const note = text(body.note, NOTE_MAX, 'note');
  const kind = card.answer?.kind;
  let value = null;
  let typed = false;

  if (action === 'accept') {
    if (!card.suggestion) throw new HttpError(400, 'This question has no suggested answer to accept.');
    // the value recorded is the suggestion as the site holds it: the browser cannot change what "yes" means
    if (body.value !== undefined && !sameValue(body.value, card.suggestion.value)) {
      throw new HttpError(409, 'The suggested answer changed. Reload the page and look again.');
    }
    value = card.suggestion.value;
  } else if (action === 'value') {
    typed = body.typed === true;
    if (kind === 'yes_no') {
      if (typeof body.value !== 'boolean') throw new HttpError(400, 'Please answer yes or no.');
      value = body.value;
      typed = false;
    } else if (kind === 'number') {
      const n = typeof body.value === 'number' ? body.value : Number(String(body.value ?? '').trim().replace(',', '.'));
      if (!Number.isFinite(n) || String(body.value ?? '').trim() === '') {
        throw new HttpError(400, 'Please give a number.');
      }
      value = n;
      typed = true;
    } else {
      const picked = (card.answer?.options || []).find((o) => sameValue(o.value, body.value));
      if (picked && !typed) {
        value = picked.value;
      } else {
        if (kind === 'choice' && card.answer?.allow_text !== true) {
          throw new HttpError(400, 'Please pick one of the listed answers.');
        }
        value = text(body.value, VALUE_MAX, 'answer');
        if (!value) throw new HttpError(400, 'Please type an answer first.');
        typed = true;
      }
    }
  }
  return { card_id: card.card_id, action, value, typed, note, by, at };
}

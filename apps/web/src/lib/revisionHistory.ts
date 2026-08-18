/*
 * SUBMISSION HISTORY — the pure half: the words, and nothing else.
 *
 * WHAT THIS FILE IS ALLOWED TO SAY, and it is a short list. It may say what a
 * revision recorded, who is on record for it, and how one address differs between
 * a submitted revision and the record as it stands. It may NOT say why, may not
 * say which side is preferable, and may not characterise a difference as a
 * problem, a conflict, a regression or an improvement. Nothing here is a verdict.
 *
 * THREE RULES CARRIED OVER FROM `runCompare.ts`, DELIBERATELY, because a second
 * surface that broke them would teach the reader that the first one's care was
 * decorative:
 *
 *   1. ABSENCE IS NOT A VALUE. "The record now holds nothing here" and "the record
 *      now holds something else here" are different facts and get different words.
 *      A blank cell beside a filled one, labelled "different", is the defect.
 *   2. NOT ONE WORD IS EVALUATIVE. No "conflict", no "mismatch", no "problem", no
 *      "unexpected", no "stale". Characterising a difference the scientist has not
 *      yet explained is not this surface's job.
 *   3. AN UNRENDERABLE VALUE SAYS SO. `valueText` returns `null` for two different
 *      facts — nothing is there, and an object/array is there — and reporting the
 *      second as the first is a false statement about a record.
 *
 * WHAT IS REUSED AND WHAT IS NOT, stated because reuse here is a judgement rather
 * than a default. `valueText` and `isUnrenderableValue` are `runOverrides`' own and
 * are imported. `categoryWord('value')` — "Different values" — is imported from
 * `runCompare` for the ONE case where the two comparisons genuinely coincide: two
 * sides, both present, holding different scalars. The other two kinds are NOT
 * reused, and that is the point: `runCompare`'s "On one run only" names a relation
 * between two runs at one moment, and it would be false here, where the two sides
 * are the same record at two different moments and the reader needs to know WHICH
 * moment holds the value. Reusing a word that reads well and means the wrong thing
 * is worse than writing a new one.
 */

import { categoryWord } from './runCompare';
import { isUnrenderableValue, valueText } from './runOverrides';
import type {
  ApiHistoryAvailability,
  ApiRevisionActor,
  LifecycleState,
  RevisionChangeKind,
} from './types';

/* ── the actor ─────────────────────────────────────────────────────────────── */

/**
 * WHO IS ON RECORD, INCLUDING NOBODY — and nobody is never rendered as somebody.
 *
 * A revision written by a deployment that could establish no actor carries
 * `subject: null` and `trust_basis: 'unattributed'`. The honest rendering of that
 * is a sentence saying so. It is NOT "System", NOT "Unknown user", NOT "—", and
 * NOT the deployment's name: every one of those reads as a party, and crediting a
 * declaration to a party that did not make it is the single worst thing this
 * surface could invent.
 */
export const NO_ACTOR_TEXT = 'No attributable actor was recorded';

export function actorText(actor: ApiRevisionActor | null | undefined): string {
  if (!actor || !actor.attributed || !actor.subject) return NO_ACTOR_TEXT;
  return actor.subject;
}

/**
 * What the attribution is WORTH, when that is not simply "a person at the edge".
 *
 * `test_fixture` is a real, shipped basis: a deployment configured with the
 * fixture verifier mints a subject from its own process environment, which is not
 * proof anyone authenticated. `submission_store.capability` already publishes that
 * on `/api/health` for the same reason, and flattening every attributed row into
 * "attributed" here would hide it exactly where a reader is most likely to take a
 * name at face value.
 *
 * `null` when there is nothing extra to say — either nobody is named (the sentence
 * above already says everything) or the basis is a verified edge assertion, which
 * is what an attributed row is expected to be.
 */
export function actorBasisNote(actor: ApiRevisionActor | null | undefined): string | null {
  if (!actor || !actor.attributed) return null;
  if (actor.trust_basis === 'test_fixture') {
    return 'recorded on a test-fixture basis — not proof anyone authenticated';
  }
  return null;
}

/* ── one changed address ───────────────────────────────────────────────────── */

/**
 * The two sides of a diff row, named. They are two MOMENTS of one record, not two
 * records, and the words say so everywhere they appear.
 */
export const SIDE_REVISION = 'In this revision';
export const SIDE_NOW = 'In the record now';

/**
 * How one change kind reads when comparing a submitted revision against the
 * record as it stands. See the header for why only one of the three is reused.
 */
export function diffChangeWord(kind: RevisionChangeKind): string {
  switch (kind) {
    case 'added':
      return 'Recorded now, not in this revision';
    case 'removed':
      return 'In this revision, not recorded now';
    case 'modified':
      // The one case `runCompare` already has the right word for.
      return categoryWord('value');
  }
}

/**
 * How one change kind reads in a revision's OWN recorded change list, where the
 * comparison is against the revision before it and the heading states that
 * direction. The server's own three words, capitalised and not reinterpreted.
 */
export function recordedChangeWord(kind: RevisionChangeKind): string {
  switch (kind) {
    case 'added':
      return 'Added';
    case 'removed':
      return 'Removed';
    case 'modified':
      return 'Modified';
  }
}

/** One side of a diff row, as text — or the honest reason there is no text. */
export interface SideText {
  /** The value on one line, or `null`. */
  text: string | null;
  /** True when a value IS there and cannot be shown on one line. */
  unrenderable: boolean;
  /** True when nothing is recorded on this side at all. */
  absent: boolean;
}

export function sideText(value: unknown): SideText {
  return {
    text: valueText(value),
    unrenderable: isUnrenderableValue(value),
    absent: value === null || value === undefined,
  };
}

/** The sentence for a side with no one-line rendering. Never a truncated value. */
export const UNRENDERABLE_TEXT = 'A value is recorded here that cannot be shown on one line';
export const ABSENT_TEXT = 'No value recorded';

/**
 * AN EMPTY STRING IS A RECORDED VALUE, and it is the one case where rendering the
 * value faithfully renders NOTHING — an empty cell, indistinguishable from an
 * absent one.
 *
 * `submissions.field_values` excludes an envelope only when its `value` is null, so
 * `""` is present, is compared, and can be the whole of what changed at an address.
 * Rendering it as `ABSENT_TEXT` would be a false statement about the record, and
 * rendering it as nothing would be a false statement made silently. So it gets its
 * own sentence.
 */
export const EMPTY_STRING_TEXT = 'An empty value is recorded here';

export function sideSentence(side: SideText): string {
  if (side.unrenderable) return UNRENDERABLE_TEXT;
  if (side.absent || side.text === null) return ABSENT_TEXT;
  if (side.text === '') return EMPTY_STRING_TEXT;
  return side.text;
}

/* ── the lifecycle ─────────────────────────────────────────────────────────── */

/**
 * A one-line gloss on each lifecycle state, in product words.
 *
 * `submitted` NAMES ITS OWN SCOPE. "Submitted" alone would be read as "this record
 * has been submitted", and what the server derived is narrower and more useful:
 * a submission is on record for exactly the content this record holds NOW. A
 * record that was submitted and then edited is not in this state, and the gloss is
 * where a reader learns that without having to discover it.
 *
 * NOT ONE OF THESE MENTIONS EXPORT. Export and submission are different acts and
 * the product keeps them apart; a gloss that said "exported and submitted" would
 * merge them in the one place a reader is looking for the distinction.
 */
export const LIFECYCLE_NOTES: Readonly<Record<LifecycleState, string>> = {
  draft: 'Questions the system refused to guess are still unanswered.',
  needs_review:
    'Every question is answered, and this record does not yet pass the export check.',
  ready_to_submit: 'Every question is answered and every record this would publish passes.',
  submitted: 'A submission is on record for exactly the content this record holds now.',
};

/**
 * What to say about the lifecycle when the history could not be read.
 *
 * It never says "not submitted", because that was not observed. The distinction is
 * the whole reason `submission.known` exists.
 */
export const LIFECYCLE_UNKNOWN_NOTE =
  'Whether this content has already been submitted is unknown here, not no — this ' +
  'deployment could not read its submission history.';

/* ── availability ──────────────────────────────────────────────────────────── */

/**
 * The heading for an unavailable history. The server's own MESSAGE is rendered
 * beside it verbatim; this is only the short form for the heading, and it never
 * asserts anything about the record.
 */
export function availabilityHeading(availability: ApiHistoryAvailability): string {
  if (availability.state === 'available') return 'Submission history';
  if (availability.state === 'not_applicable') return 'This record has no submission history';
  return 'Submission history could not be read';
}

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
  ApiRevisionHistory,
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

/* ── REV-002 · the submitted snapshot versus the record now ────────────────── */

/**
 * *** DEC-21's DISTINCTION, AS A PURE FUNCTION OVER WHAT THE SERVER ALREADY
 * SENDS. ***
 *
 * ── THE DECISION THIS IMPLEMENTS, AND WHY IT IS NOT A RE-WORDING ────────────
 *
 * `DEC-21` is CONFIRMED **and CORRECTED**: the planning run proposed describing
 * a resubmission as *"keep editing, then submit again"*, which is mechanically
 * what happens and **understates the modelling requirement**. The owner's
 * correction is that the UI must explicitly distinguish **`Last Submitted
 * Revision`** from **`Current Working Changes`**, and must **never describe the
 * historical submitted revision as mutable**.
 *
 * Measured 2026-09-13: neither phrase existed anywhere in `apps/web/src`.
 * `RevisionHistoryPanel` already rendered the history and already had the
 * per-address vocabulary (`SIDE_REVISION` / `SIDE_NOW`) — what was missing was
 * the screen-level framing those two sides belong to.
 *
 * ── WHY THIS NEEDS NO NEW REQUEST, AND NO GUESS ─────────────────────────────
 *
 * `GET .../revisions` already serves `current_content_signature`, and every
 * `ApiRevisionSummary` already carries its own `content_signature`. So "has the
 * record changed since it was last submitted?" is an **exact string comparison
 * over two values the server computed**, not a diff this client re-derives and
 * not a count it estimates. Confirmed on the wire before this was written:
 * `current_content_signature` and
 * `signature_scope: "export_unit_ids_drafts_and_conflict_decisions"` are both
 * present on a record with no history at all.
 *
 * ── THE THREE ANSWERS, AND WHY THERE ARE THREE RATHER THAN TWO ──────────────
 *
 * `unknown` is a first-class answer and the reason is the one this panel's
 * header already gives about empty lists: the submission-history tables are
 * created by a migration an **operator** applies, so "this record has never
 * been submitted" and "this deployment could not find out" are both reachable
 * and look identical if you are careless. On every deployment shipped today the
 * second is the true one — the server answers `503` and its own lifecycle
 * reason reads *"whether this content has already been submitted is unknown
 * rather than no"*. Collapsing `unknown` into `never` would turn that into a
 * false negative on every current deployment.
 */
export type WorkingStateKind = 'unknown' | 'never_submitted' | 'unchanged' | 'changed';

export interface WorkingState {
  kind: WorkingStateKind;
  /** The revision the comparison is against, or `null` when there is none. */
  revisionNo: number | null;
}

/**
 * Compare the record as it stands against its most recent SUBMITTED revision.
 *
 * Deliberately the most recent **submitted** one, not the most recent revision:
 * a revision row exists for changes that were never declared finished, and
 * comparing against one would answer a question nobody asked. `submission` is
 * `null` on an unsubmitted revision, which is what this filters on.
 *
 * The list's order is not assumed — the newest submitted revision is taken by
 * `revision_no`, so a server that returns ascending or descending gives the same
 * answer.
 */
export function workingState(history: ApiRevisionHistory): WorkingState {
  /*
   * *** C-3, FOUND BY INDEPENDENT REVIEW 2026-09-13. `not_applicable` IS A FACT,
   * NOT AN INABILITY, AND THIS FUNCTION USED TO REPORT IT AS ONE. ***
   *
   * `RevisionHistoryState` has THREE members — `available`, `unavailable`,
   * `not_applicable` — and the first version of this function branched on
   * `!== 'available'`, sending `not_applicable` to `unknown`, whose sentence reads
   * *"This deployment could not read the submission history"*.
   *
   * The server says the opposite, in the served description of that very
   * operation: a worked-example record answers **`200`** with
   * `availability.state: "not_applicable"`, *"which is a fact rather than an
   * inability: such records are never submitted."* So the reader of a
   * worked-example record was told the deployment had failed to read something,
   * when it had read it successfully and the answer was "there is nothing here".
   * It also contradicted `availabilityHeading` two blocks below on the same card.
   *
   * The irony is the useful part: this function was written with deliberate care
   * NOT to collapse `unknown` into `never_submitted` — that would be a false
   * negative on every deployment shipped today — and it collapsed
   * `not_applicable` into `unknown` in the same breath. **Being careful about one
   * direction of a three-way distinction is not being careful about the
   * distinction.**
   *
   * Written as an explicit switch over the three states rather than as a second
   * inequality, so a FOURTH state added later fails to compile here instead of
   * silently inheriting whichever branch the inequality happened to send it to.
   */
  switch (history.availability.state) {
    case 'not_applicable':
      return { kind: 'never_submitted', revisionNo: null };
    case 'unavailable':
      return { kind: 'unknown', revisionNo: null };
    case 'available':
      break;
  }
  if (history.revisions === undefined) {
    // `available` with no `revisions` key is not a shape the server documents, so
    // it is read as an inability rather than as an empty history: claiming "never
    // submitted" about a payload we cannot interpret is the false negative this
    // whole function exists to avoid.
    return { kind: 'unknown', revisionNo: null };
  }
  const submitted = history.revisions.filter((r) => r.submission !== null);
  if (submitted.length === 0) return { kind: 'never_submitted', revisionNo: null };
  const latest = submitted.reduce((a, b) => (b.revision_no > a.revision_no ? b : a));
  return {
    kind:
      latest.content_signature === history.current_content_signature ? 'unchanged' : 'changed',
    revisionNo: latest.revision_no,
  };
}

/**
 * WHAT THE `Last Submitted Revision` CELL SAYS — and why `'None'` is wrong for one
 * of the four states.
 *
 * *** C-4, FOUND BY INDEPENDENT REVIEW 2026-09-13. *** The panel rendered
 * `state.revisionNo === null ? 'None' : 'Revision N'`, and `revisionNo` is `null`
 * for **both** `unknown` and `never_submitted`. On every deployment shipped today
 * the submission-history tables are unapplied, so the state IS `unknown` — and a
 * scientist read **"Last Submitted Revision · None"** about a record whose history
 * had not been read at all.
 *
 * That is this module's own Rule 1 broken by this module: *"ABSENCE IS NOT A
 * VALUE. 'The record now holds nothing here' and 'the record now holds something
 * else here' are different facts and get different words."* `None` is an answer;
 * the truth was that there was no answer.
 *
 * The distinction is not cosmetic. `None` tells a scientist their work has never
 * been submitted — which, if it has been and this deployment simply cannot see the
 * history, is exactly backwards, and is the kind of thing someone acts on.
 */
export function submittedRevisionText(state: WorkingState): string {
  switch (state.kind) {
    case 'unknown':
      return 'Not read on this deployment';
    case 'never_submitted':
      return 'None';
    case 'unchanged':
    case 'changed':
      return `Revision ${state.revisionNo}`;
  }
}

/** The heading for the immutable half. Never varies: it names a kind of thing. */
export const SUBMITTED_REVISION_HEADING = 'Last Submitted Revision';

/** The heading for the mutable half. */
export const WORKING_CHANGES_HEADING = 'Current Working Changes';

/**
 * The immutability sentence — the one `DEC-21` requires and the one this
 * application can actually stand behind.
 *
 * It says what no route does, rather than asserting a database-level guarantee:
 * the five submission-history tables are append-only in
 * `db_write._APPEND_ONLY_TABLES`, but this sentence is read by a scientist about
 * the PRODUCT, and the product-level truth is that nothing here edits, reverts,
 * restores or republishes a submitted revision. The panel's own header already
 * commits to there being no "restore this revision" control until a route exists
 * that could honour it.
 */
export const SUBMITTED_IMMUTABLE_NOTE =
  'A submitted revision is a permanent snapshot of what was declared finished. ' +
  'Nothing in this application edits, reverts, restores or republishes one — ' +
  'further work becomes the next submission, not a change to this one.';

/** What each working state says. One sentence, no verdict, no instruction to obey. */
export function workingStateSentence(state: WorkingState): string {
  switch (state.kind) {
    case 'unknown':
      return (
        'This deployment could not read the submission history, so whether this ' +
        'record has been submitted — and whether it has changed since — is unknown ' +
        'rather than no.'
      );
    case 'never_submitted':
      return 'This record has no submitted revision yet, so there is nothing to compare it against.';
    case 'unchanged':
      return (
        `Nothing that a submission covers has changed since revision ${state.revisionNo} ` +
        'was submitted.'
      );
    case 'changed':
      return (
        `This record has changed since revision ${state.revisionNo} was submitted. ` +
        'Those changes are held here and are not part of any submitted revision.'
      );
  }
}

/**
 * *** THE RENAME TRAP, SURFACED RATHER THAN HIDDEN — and shown ONLY where it can
 * actually bite. ***
 *
 * `DEC-21` requires it: a rename does **not** move `content_signature`, so
 * submit → rename → resubmit yields **`409 already_submitted`**. Verified at the
 * source of truth rather than taken from the decision row —
 * `submissions.content_signature`'s own docstring: *"WHAT IT COVERS: the
 * experiment id, each export unit's id and fully resolved draft, and the
 * record's stored conflict decisions. **Nothing else.**"* A title is none of the
 * three.
 *
 * ── WHY THE SCOPE IS QUOTED FROM THE SERVER AND NOT WRITTEN HERE ────────────
 *
 * The response carries `signature_scope`
 * (`"export_unit_ids_drafts_and_conflict_decisions"`), so the boundary this
 * sentence describes is read from the server that enforces it. Hard-coding the
 * list would be a second expression of one rule, and it would go quietly false
 * the day the scope changes — which is exactly how this repository's measured
 * defects get made. `signature_scope` is rendered verbatim beside the sentence
 * by the panel, under its own label, because it is an identifier a curator maps
 * by rather than a word.
 *
 * ── AND WHY IT IS CONDITIONAL ───────────────────────────────────────────────
 *
 * It is offered only for `unchanged` — the one state where the reader is looking
 * at a record that LOOKS different to them (they may well have just renamed it)
 * and where a resubmission would in fact be refused. On `changed` the
 * resubmission will be accepted and the warning would be noise; on `unknown` and
 * `never_submitted` there is nothing to be refused against. A caution shown in
 * states where it cannot apply is how a true sentence becomes ignored.
 */
export function renameTrapNote(state: WorkingState): string | null {
  if (state.kind !== 'unchanged') return null;
  return (
    'Renaming this record does not count as a change here, and neither does ' +
    'anything else outside the scope named below — so submitting again now would ' +
    'be refused as already submitted. To create a new revision, change something ' +
    'the submission itself covers.'
  );
}

/*
 * DISCARD — every word of it, in one module, because the words are the risky part.
 *
 * WHAT A DISCARD CONTROL IN THIS APPLICATION IS. It clears input a scientist typed
 * into a box on screen and never sent. Nothing more. It issues no request — see
 * `components/DiscardStaged.tsx`, which cannot issue one — so it cannot remove,
 * delete, or roll back anything the record holds.
 *
 * WHY THE COPY IS CENTRALISED. There is no deletion anywhere in this product's notes
 * model to build a deletion promise on. `apps/api/isaac_api/routes.py:8155-8158` states
 * it as a governing rule — "NOTHING CAPTURED IS EVER SILENTLY DISCARDED — there is no
 * DELETE here, and there will not be one. Dismissal is a state." — and
 * `transcript_capture.py:129-159` records two retention states that were deliberately
 * NOT offered for exactly that reason: "both are deletion guarantees, and there is no
 * deletion anywhere in the notes model to build one on. Offering a control that quietly
 * did nothing would be worse than offering none."
 *
 * A Discard control that said it removed anything from the record would BE that
 * control. So SIX rules bind every string below, and
 * `__tests__/discard-claim-parity.test.tsx` enforces ALL SIX mechanically — the count is
 * stated because an earlier version of this header said "five rules … enforces four of
 * them", which was wrong in the file whose subject is unchecked claims:
 *
 *   1. It says what it clears — an input on screen — and names it.
 *   2. It states what is NOT touched, in the same breath.
 *   3. It never claims a deletion, removal, or erasure of stored content.
 *   4. It never says "permanently", "forever" or "cannot be undone". Input that was
 *      never sent does not carry those stakes, and borrowing them is an overstatement
 *      in the direction that makes a reader hesitate over nothing.
 *   5. It never offers to restore what was discarded. Nothing here can.
 *   6. It says the input never reached the record — in ONE SENTENCE, so a negation in one
 *      sentence and a transmission verb in another cannot satisfy it. ~~"in ONE clause"~~
 *      is what this line used to say, and it OVERSTATED the guard by one unit: the check
 *      splits on sentence ends and the em dash, never on a comma (it cannot, without
 *      banning `guidedAnswer`'s own true claim). A reviewer used the gap — one sentence
 *      saying "What you typed has already been captured, and nothing on the record
 *      changes" satisfies rule 6 while asserting its opposite — so a SECOND detector now
 *      runs beside it, banning any clause that affirms the staged thing reached the
 *      record without a negation governing it. This is the one rule with an exception,
 *      and the exception is the point: see the transcript note below.
 *
 * THE TRANSCRIPT HAS TWO BODIES, AND THAT IS THE POINT RATHER THAN AN EXCEPTION. Once
 * Finalize succeeds, every segment of the transcript is stored with the record as
 * Unmapped Notes (`routes.py:9483-9494`), so from that moment a control that cleared the
 * box while saying "nothing has been sent" would be false. The second body is what makes
 * the control truthful after finalize; it is not a softening of the first.
 */

/*
 * THE ASSISTANT COMPOSER HAS NO ENTRY HERE, AND THE REASON IS RECORDED SO IT IS NOT
 * RE-ADDED BLIND. One was written, wired and then withdrawn.
 *
 * WHAT IS ALREADY COVERED THERE. `Clear Conversation` is a shipped, explicit discard
 * for the panel's ephemeral state: `clearConversation` calls `clearSession(experimentId)`
 * and drops `messages`, the live turn, the unapplied graph proposal AND the staged,
 * unconfirmed value proposal — the last of which was itself a fix, because it used to
 * survive a Clear. So two of the three staged states in that panel already have one.
 *
 * WHAT IS NOT, AND WHY IT STAYS THAT WAY. The third is `composerText`: one single-line
 * `<input>` holding a question that has not been asked. A Discard for it must announce
 * its outcome, and every way of doing that adds a live region to `AssistantPanel` —
 * which two committed invariants forbid. `__tests__/assistant-a11y.test.tsx`'s "P34.5
 * single live region" requires the conversation to be announced through exactly one
 * explicitly-marked polite region, with the history log forced to `aria-live="off"`;
 * and `__tests__/graph-semantic-zoom.test.tsx:826` counts `role="status"` across the
 * WHOLE DOCUMENT on Project Memory — a screen that mounts this panel in its right rail
 * — and requires exactly one. A control whose announcement was dropped to satisfy them
 * would be a discard a screen-reader user could not tell had happened.
 *
 * The alternative worth considering is not another control: it is widening
 * `clearConversation` and its `canClear` gate to cover a composer draft. That is a
 * BEHAVIOUR change to a shipped control which today deliberately preserves a half-typed
 * question, so it is named here as an option rather than taken.
 */

/** One Discard control's authored copy. */
export interface DiscardCopy {
  /** The quiet trigger's visible label. Names the thing, not the mechanism. */
  readonly trigger: string;
  /** The confirm step's sentence: what goes, and what is untouched. */
  readonly body: string;
  /** The committing button inside the confirm step. */
  readonly commit: string;
  /** The way out of the confirm step. */
  readonly keep: string;
  /** Announced in a live region after the discard, for a screen-reader user. */
  readonly announcement: string;
}

export const DISCARD_COPY = {
  /**
   * The transcript box before any Finalize has landed. Nothing typed has reached the
   * server: `captureTranscript` is reachable from one button, and the server refuses a
   * body without `finalized: true`.
   */
  transcriptUnsent: {
    trigger: 'Discard this transcript',
    body:
      'This clears the transcript box. Nothing in it has been read or stored — that ' +
      'happens only when you press Finalize — so this record, its notes and its runs ' +
      'stay exactly as they are.',
    commit: 'Discard',
    keep: 'Keep it',
    announcement: 'The transcript box is empty. Nothing in it had been sent.',
  },

  /**
   * The transcript box AFTER a Finalize has landed. The words are on the record as
   * notes and this control does not reach them; a value already accepted is on its run
   * and this control does not reach that either. Both are said, because a reader who has
   * just finalized is the one most likely to read "discard" as "unsend".
   */
  transcriptAfterFinalize: {
    trigger: 'Discard this transcript',
    body:
      'This clears the transcript box, and any value you have typed over a proposal ' +
      'below. The transcript you finalized is already stored with this record as ' +
      'notes and stays there, and any proposal you accepted is already written to its ' +
      'run and stays there. This clears what is in the boxes, and reaches neither.',
    commit: 'Discard',
    keep: 'Keep it',
    announcement:
      'The transcript box is empty. The notes you finalized are still stored with ' +
      'this record.',
  },

  /** One completion question's staged answer, before it is confirmed. */
  guidedAnswer: {
    trigger: 'Discard this answer',
    body:
      'This clears what you have entered for this question. An answer reaches the ' +
      'record only when you confirm it, so this one has not — the record, its evidence ' +
      'and the answers you already confirmed all stay as they are. The question stays ' +
      'open for you to answer later.',
    commit: 'Discard',
    keep: 'Keep it',
    announcement:
      'The boxes for this question are empty. Nothing had been confirmed, and the ' +
      'question is still open.',
  },

  /**
   * One conflict's decision form: a selection, a typed value, a reason, a checkbox.
   *
   * THIS ONE STRING SERVES BOTH STATES OF THE CARD, so it may not assert either of them.
   * `ConflictRow` renders the same form for a conflict nobody has decided AND for one
   * being revised (`revising = conflict.resolution !== null`, primary button "Record a
   * Revised Decision", a `RecordedDecision` block below it, and a header chip reading
   * "decided"). An earlier version said "The conflict stays open" and "the conflict is
   * still open" — true of the first card, FALSE of the second, and contradicted by the
   * chip a few lines above it in the same card. Found in independent review. What is true
   * of both, and is what the reader needs, is that discarding moves the conflict's
   * standing nowhere: whatever it was before the form was filled in, it still is.
   */
  conflictDecision: {
    trigger: 'Discard this decision',
    body:
      'This clears the answer you selected, anything you typed and the reason you ' +
      'wrote. None of it has been recorded. Every competing answer stays on the ' +
      'record, this conflict keeps the standing it already has, and any decision ' +
      'already recorded here is untouched.',
    commit: 'Discard',
    keep: 'Keep it',
    announcement:
      'The decision form is empty. Nothing had been recorded from it, and this ' +
      'conflict keeps the standing it already has.',
  },

  /** The capture box for a new note, before Capture Note is pressed. */
  noteCapture: {
    trigger: 'Discard this note',
    body:
      'This clears the box you are typing in. Nothing has been captured from it yet, ' +
      'so there is nothing on the record to change — and the notes this record already ' +
      'holds are untouched.',
    commit: 'Discard',
    keep: 'Keep it',
    announcement: 'The note box is empty. Nothing had been captured from it.',
  },
} as const satisfies Record<string, DiscardCopy>;

/** Every authored Discard control, for the parity guard and for anyone auditing them. */
export const DISCARD_COPY_ENTRIES: readonly (readonly [string, DiscardCopy])[] =
  Object.entries(DISCARD_COPY);

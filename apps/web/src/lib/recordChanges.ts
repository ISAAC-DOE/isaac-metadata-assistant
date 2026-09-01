/*
 * WHAT THE CHANGE FEED MEANS FOR ONE OPEN RECORD SCREEN — a PURE function, and
 * deliberately not a store.
 *
 * `useChangeFeed` hands a surface the entries and the cursor and decides nothing.
 * This module is the deciding, and it is separated out for one reason: everything
 * here is a pure function of its arguments, so the three properties that matter can
 * be asserted directly rather than through a rendered component.
 *
 *   1. IT READS FOUR FIELDS AND NO OTHERS — `kind`, `entity_id`, `changed_at_rev`
 *      and `state`. A proposal entry carries nothing else (the server's own
 *      `test_a_proposal_entry_carries_NO_CONTENT_over_the_wire` pins the key set to
 *      exactly `{kind, entity_id, changed_at_rev, updated_utc, state}`), so there is
 *      no scientific content within reach of this file even by mistake. That is a
 *      structural guarantee, the same kind `change_feed.py` gets from importing
 *      nothing out of `proposals.py`, rather than a review one.
 *
 *   2. IT NEVER WRITES, AND NOTHING IT RETURNS IS A WRITE INSTRUCTION. The summary
 *      names which canonical reads are now stale. A surface may refetch; no code
 *      path from a change entry reaches a mutation. That is what makes the
 *      save -> feed -> save loop structurally impossible rather than merely
 *      unlikely — there is no second edge to close.
 *
 *   3. IT HOLDS NOTHING. A summary is derived and handed on. The record's entities
 *      continue to live in exactly one place: the screen's own bundle.
 *
 * WHAT IS DELIBERATELY NOT HERE. No latency claim, no "live", no "real-time". The
 * feed is polled at a cadence with jitter that pauses while the tab is hidden, and
 * no bound on the delay is measured anywhere in this repository — so the copy below
 * says what the mechanism does and nothing about how fast it does it.
 */

import type { ApiChangeEntry } from './types';

/**
 * WHAT MOVED, COALESCED, WITH NO ENTITY PAYLOAD.
 *
 * Ids only, never values. The ids are here because a surface has to be able to
 * refetch the thing that moved from the route that owns it; nothing here is
 * renderable as scientific content, and nothing here is a substitute for reading
 * that route.
 */
export interface RecordChangeSummary {
  /** The record's own entry advanced — its draft, title, notes or runs moved. */
  recordMoved: boolean;
  /** Run ids whose version advanced past what this view holds. Sorted, unique. */
  runIds: string[];
  /** Proposal ids that moved. Sorted, unique. NO proposal content, ever. */
  proposalIds: string[];
  /**
   * The distinct lifecycle states those proposals are in NOW, sorted. Passed
   * through verbatim from the server, which classifies nothing — so a state this
   * build has never heard of appears here unchanged rather than mapped onto one it
   * knows.
   *
   * THEY ARE STATES, NOT EVENTS. A proposal accepted between two polls appears here
   * as `accepted`, and there is no entry anywhere saying an acceptance happened.
   */
  proposalStates: string[];
  /**
   * Kinds this build received and has no specific handling for. Reported rather
   * than dropped: a deployment serving a fourth kind should make a surface say "and
   * other parts of this record changed" instead of silently omitting it.
   */
  otherKinds: string[];
  /** The highest sequence position in this batch. Never used as a cursor. */
  highestRev: number;
}

/**
 * THE ONE FILTER, AND IT IS THE REASON `changed_at_rev` IS ON THE WIRE.
 *
 * An entry's `changed_at_rev` is the record's own `rev` at the save that last
 * changed that entity. A view that already holds the record at `rev` R has, by
 * construction, already adopted every save up to and including R — so an entry at
 * `changed_at_rev <= R` is not news to it, whoever made that save.
 *
 * That covers THIS CLIENT'S OWN WRITES as the ordinary case rather than as a special
 * one: a scientist who just saved holds the rev their save produced, so the entry
 * the feed reports for it is filtered by the same comparison that filters a
 * colleague's older edit. There is no list of "my own writes" to keep, and nothing
 * to get out of step.
 *
 * WHAT IT DOES NOT CLOSE, stated rather than left to be discovered: a save whose
 * response has not yet been adopted into `detail` when a poll resolves is reported
 * as news, because at that instant it genuinely is news relative to what the view
 * holds. The window is the gap between a write returning and its version being
 * adopted, and the consequence is a redundant refresh of a read — never a write,
 * and never a lost keystroke, because no surface auto-merges. Narrowing it further
 * would mean tracking revisions this module does not own.
 *
 * A first poll carries no cursor and therefore returns EVERY entity at its current
 * position. Almost all of them sit at or below the rev the screen already holds, so
 * this is also what stops a mount from announcing the whole record as "changed".
 */
export function summariseChanges(
  entries: readonly ApiChangeEntry[],
  knownRev: number | undefined,
): RecordChangeSummary | null {
  // `undefined` means the screen has not told us where it stands. Nothing is
  // filtered then, because a filter with no floor would have to invent one — and
  // inventing `0` would report the entire record on the first poll.
  const floor = knownRev ?? -1;

  const runIds = new Set<string>();
  const proposalIds = new Set<string>();
  const proposalStates = new Set<string>();
  const otherKinds = new Set<string>();
  let recordMoved = false;
  let highestRev = -1;

  for (const entry of entries) {
    // A non-numeric or missing coordinate cannot be compared, so it is treated as
    // news rather than dropped: withholding a change because its position was
    // unreadable is the failure mode that loses one.
    const at = typeof entry.changed_at_rev === 'number' ? entry.changed_at_rev : undefined;
    if (at !== undefined && at <= floor) continue;
    if (at !== undefined && at > highestRev) highestRev = at;

    switch (entry.kind) {
      case 'experiment':
        recordMoved = true;
        break;
      case 'run':
        runIds.add(entry.entity_id);
        break;
      case 'proposal':
        proposalIds.add(entry.entity_id);
        // Only a state the server actually sent. An absent one is absent, not
        // defaulted to "open" — this module decides nothing about a lifecycle.
        if (typeof entry.state === 'string' && entry.state) proposalStates.add(entry.state);
        break;
      default:
        otherKinds.add(entry.kind);
        break;
    }
  }

  const summary: RecordChangeSummary = {
    recordMoved,
    runIds: [...runIds].sort(),
    proposalIds: [...proposalIds].sort(),
    proposalStates: [...proposalStates].sort(),
    otherKinds: [...otherKinds].sort(),
    highestRev,
  };
  return hasNews(summary) ? summary : null;
}

/** Did anything survive the filter? `null` rather than an empty summary, so a
 *  caller cannot mistake "nothing moved" for "something moved, with no detail". */
function hasNews(s: RecordChangeSummary): boolean {
  return (
    s.recordMoved ||
    s.runIds.length > 0 ||
    s.proposalIds.length > 0 ||
    s.otherKinds.length > 0
  );
}

/**
 * DOES THIS SUMMARY MEAN THIS SCREEN'S CANONICAL READ IS STALE? — the selectivity
 * gate, in ONE place.
 *
 * IT WAS WRITTEN FOUR TIMES AND PINNED AT NONE OF ITS THREE REAL SITES. The identical
 * expression `summary.recordMoved || summary.runIds.length > 0 ||
 * summary.otherKinds.length > 0` stood in `RecordWorkbench`, `EvidenceExplorer` and
 * `ExportReadiness` — and a FOURTH copy stood in `change-feed-mount.test.tsx` as a
 * local `gate`, which is what the selectivity tests actually exercised. So a screen
 * whose gate drifted would have failed nothing: the test would have kept proving that
 * a copy of the rule behaves, on a build where the rule had changed. That is exactly
 * the failure `change_feed.py` extracts `SEQUENCE_PROOF` and `GAP_GUARANTEE` into
 * constants to avoid — "a claim written three times is a claim free to drift" — and
 * this file inherited the problem it was written to prevent.
 *
 * WHAT THE RULE IS, AND WHY PROPOSALS ARE NOT IN IT. The three read-only screens
 * render the record, its runs and whatever a kind they do not know might affect; none
 * of them renders a proposal's content, which is read from the route that owns it. So
 * a summary carrying ONLY proposal ids is announced and refetches nothing.
 *
 * STATED HONESTLY, because the branch looks more load-bearing than it is: in this
 * build a proposal act ALSO advances the record's own `rev`
 * (`workspace._authoritative_signature` hashes proposals), so `recordMoved` normally
 * travels with it and the common path DOES refetch. The proposal-only branch is
 * reachable through the feed's contract — the server may serve any combination, and a
 * page boundary can split one save's entities across two pages — and that is what is
 * tested. It is not claimed to be the common case.
 *
 * IT IS NOT `hasNews`. `hasNews` asks "is there anything to SAY", which includes a
 * proposal; this asks "is what this screen has FETCHED now stale", which does not. Two
 * questions, deliberately two functions — collapsing them would make every proposal
 * act refetch three screens' bundles for content none of them shows.
 */
export function needsCanonicalRefetch(summary: RecordChangeSummary): boolean {
  return summary.recordMoved || summary.runIds.length > 0 || summary.otherKinds.length > 0;
}

/**
 * ONE SENTENCE FOR A SCREEN READER, COALESCED — never one message per entry.
 *
 * A record being edited by a colleague produces a change entry for the record and
 * one per run touched, on every poll. Announcing each would make the live region
 * unusable, which is the accessibility failure this function exists to avoid: the
 * batch becomes ONE sentence, and a surface re-announces only when that sentence
 * CHANGES.
 *
 * It names counts and kinds. It never names a value, a field, a title or a
 * proposal's content, because it is built from a summary that holds none.
 *
 * IT MAKES NO CLAIM ABOUT WHEN. No "just now", no "live", no "moments ago" — the
 * poll cadence is jittered, backs off on failure and stops while the tab is hidden,
 * so the only honest tense is that this has happened and what is on screen predates
 * it.
 */
export function describeChangeSummary(s: RecordChangeSummary): string {
  const parts: string[] = [];
  if (s.proposalIds.length > 0) {
    const n = s.proposalIds.length;
    parts.push(`${n} ${n === 1 ? 'suggestion' : 'suggestions'} changed`);
  }
  if (s.runIds.length > 0) {
    const n = s.runIds.length;
    parts.push(`${n} ${n === 1 ? 'run' : 'runs'} changed`);
  }
  // The record's own entry moves on any act inside it, including the ones already
  // named above, so it is only worth saying when it is the ONLY thing to say.
  if (parts.length === 0 && (s.recordMoved || s.otherKinds.length > 0)) {
    parts.push('this record changed');
  } else if (s.otherKinds.length > 0) {
    parts.push('other parts of this record changed');
  }
  return `Updated elsewhere: ${parts.join(', ')}. What is on screen was loaded before that.`;
}

/**
 * THE CADENCE CLAIM FOR A PERSON, and the reason it is a constant.
 *
 * Same rule as `CHANGE_FEED_CADENCE_CLAIM` and `ASSISTANT_NO_MODEL_CLAIM`: a claim
 * a test has to pin cannot be a string literal written at a render site, because
 * that is a claim free to drift from what the code does.
 *
 * "Updates automatically" is a statement about the MECHANISM. "Real-time",
 * "live" and "instantly" would be statements about LATENCY, and this repository has
 * measured no latency figure anywhere — the interval is jittered, it backs off to a
 * minute on repeated failure, and it stops entirely while the tab is hidden.
 */
export const RECORD_ACTIVITY_CADENCE_CLAIM =
  'This screen checks for changes made elsewhere while it is open and the tab is ' +
  'visible, so an update appears shortly after it is made rather than instantly.';

/**
 * WHAT A SURFACE HOLDING UNSENT INPUT PROMISES, and it is the promise this whole
 * slice is written around.
 *
 * `CLAUDE.md` §11 records three banners that told a reader their input was kept
 * beside a Refresh that destroyed it. The promise is only sayable here because the
 * mechanism exists: nothing on the change-feed path refetches a form, and
 * `GuidedCompletion` holds staged answers in a ref ABOVE the component a reload
 * remounts, so neither a background update nor the Refresh button can reach them.
 */
export const RECORD_ACTIVITY_INPUT_SAFETY_CLAIM =
  'Nothing you have typed is changed or cleared by this — here or by Refresh.';

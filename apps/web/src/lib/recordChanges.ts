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
  /**
   * The highest sequence position among the RUN entries that survived, or `-1` when
   * none did — the exact analogue of `proposalRev` below, and it exists for the same
   * reason rather than for symmetry.
   *
   * `RunsSection` issues its OWN paged read (`api.listRuns`, `RUNS_PAGE_SIZE`); the
   * record bundle does not carry the run list it renders. So "where the RUN read
   * stands" is a third position, and a consumer keying a silent re-read on
   * `highestRev` has the defect `proposalRev`'s note sets out in the other direction:
   * `9:R1` followed by `9:R1` is an unchanged key and R1's SECOND move goes unread.
   *
   * A consumer that reasons about the run read reads THIS; `highestRev` answers only
   * "how far did this whole batch reach".
   */
  runRev: number;
  /**
   * The highest sequence position among the PROPOSAL entries that survived, or `-1`
   * when none did.
   *
   * IT IS DELIBERATELY NOT `highestRev`, AND THE DIFFERENCE IS A LOST CHANGE RATHER
   * THAN A REFINEMENT. The feed is ordered by `(changed_at_rev, kind, entity_id)` and
   * a page boundary may fall anywhere in it, so one page can end
   * `[proposal@4, experiment@9]` while the next begins `[proposal@9]` — both orderings
   * are legal and `'experiment' < 'proposal'` decides the tie. A consumer that
   * advanced a proposal position to this batch's `highestRev` (9) would then filter
   * `proposal@9` out of the following page and never read it. A consumer that keys a
   * refresh on `highestRev` has the same defect in the other direction: `9:P1`
   * followed by `9:P1` is an unchanged key, and P1's SECOND move goes unread.
   *
   * So the rule is: anything that reasons about where the PROPOSAL read stands reads
   * this field, and `highestRev` answers only "how far did this whole batch reach".
   */
  proposalRev: number;
}

/**
 * WHERE EACH READ ON THIS SCREEN STANDS — one floor per independent read, and the
 * reason this is an object rather than the single number it used to be.
 *
 * ── THE DEFECT THIS TYPE EXISTS TO MAKE UNWRITEABLE ──────────────────────────────
 *
 * `summariseChanges` used to take ONE floor, `recordRev`, and apply it to every kind.
 * That is correct for `experiment` and `run` — adopting a fresh `detail` genuinely
 * adopts what those entries describe — and it is FALSE for `proposal`, because
 * refetching the record adopts no proposal state whatsoever: proposals are read from
 * `GET /api/experiments/{id}/proposals` by a panel the record refetch never touches.
 *
 * The consequence was measured in the browser rather than reasoned about, in
 * `apps/web/e2e/mutation/proposals.spec.ts`. Two pollers run on the record screen at
 * the same 8 s cadence — `useRecordSync` on the record and `useChangeFeed` on the feed
 * — and a proposal act moves the record's own `rev` (contract DEC-10), so a `proposal`
 * entry and the `experiment` entry beside it always carry the SAME `changed_at_rev`.
 * Whichever poller resolved first decided the outcome:
 *
 *   · feed first  → the entry is above the floor, the panel is told, the list re-reads.
 *   · record first→ `RecordWorkbench`'s `onChange` runs `bundle.reloadSilent()`, the
 *                   floor rises to that same rev, the proposal entry is filtered, and
 *                   because a floor never comes back down IT IS DROPPED FOREVER.
 *
 * Measured, same scenario, two runs: pollers untouched, the feed delivered
 * `{"kind":"proposal","changed_at_rev":2}` at 9,969 ms, the record poller had already
 * refetched at 7,541 ms, and the panel issued NO further list read in 47 s — "Showing
 * 0 of 0" before and after. With the record poll held open, the feed's poll at 8,703 ms
 * produced a summary and the panel re-read at 8,739 ms — "Showing 0 of 0" became
 * "Showing 1 of 1". A refresh that works only when it wins a race is a refresh that
 * does not work.
 *
 * ── WHY THE FLOOR IS NOT SIMPLY REMOVED ──────────────────────────────────────────
 *
 * Because it is load-bearing, and removing it trades a missed change for a false one.
 * The floor is what makes a scientist's OWN save the ordinary filtered case rather
 * than a special one, and it is what stops a first (cursorless) poll announcing the
 * entire record on mount. The defect was never that a floor exists; it was that ONE
 * floor answered TWO different questions. Naming them separately is the fix, and a
 * caller that must fill in both fields cannot conflate them by omission.
 */
export interface ChangeFloors {
  /**
   * The revision the RECORD read has adopted — `detail.rev`, as derived from the
   * authoritative version. Governs `experiment` and unknown kinds.
   *
   * ~~"Governs `experiment`, `run` and unknown kinds"~~ — corrected in place when
   * `run` gained a floor of its own below. The sentence was accurate for as long as
   * one number answered the run question too; leaving it would make a reader believe
   * a `run` entry is measured against this, which is the exact class of confusion the
   * proposal split was written to end.
   *
   * `undefined` means the screen has not said where it stands; nothing is then
   * filtered, because a filter with no floor would have to invent one.
   */
  record: number | undefined;
  /**
   * The revision at which the RUN read stands.
   *
   * IT IS A SEPARATE QUESTION FROM `record`, FOR THE REASON `proposal` IS, AND THE
   * MEASUREMENT IS THE SAME ONE. `RunsSection` fetches the run list itself
   * (`api.listRuns`, its own paging, its own component); the record bundle does not
   * carry it. So refetching the record adopts no run-list state, and a run entry
   * filtered against the RECORD floor after the record poller won is a run change the
   * run list is never told about — a floor never comes back down, so it is dropped
   * permanently. That is the same defect `ChangeFloors` was created for, in the one
   * kind the original split left behind.
   *
   * IT IS NOT ALWAYS DIFFERENT FROM `record`, AND THAT IS DELIBERATE. A caller that
   * wants the historical behaviour passes `run: floors.record` and gets a
   * byte-identical summary — which is what `useRecordSession` does for the summary
   * that drives the visible activity NOTICE, so the sentence a screen-reader user
   * hears is unchanged by this field's existence. The separate, run-floored summary
   * is what feeds a run surface's silent re-read.
   */
  run: number | undefined;
  /**
   * The revision at which the PROPOSAL read stands — in practice the record's revision
   * at the moment this screen loaded, because that is when the proposals list was
   * read. Every proposal at or below it is, by construction, already in the list on
   * screen.
   *
   * IT IS FIXED FOR THE LIFE OF THE SCREEN, and the two things that do NOT move it are
   * each a decision rather than an omission. A record refetch does not move it — that
   * is the defect this whole type exists to fix. And reporting a proposal onward does
   * not move it either: that was implemented, measured, and withdrawn, because a floor
   * that advanced made a REPLAYED batch arrive narrower than the one before it, which
   * changed an outstanding notice's sentence and re-announced it into a live region.
   * Replays are already deduplicated downstream — by the sentence comparison in
   * `RecordActivityNote` and by the `proposalRev`+ids refresh key in
   * `IngestionProposalsPanel` — so a third mechanism here bought nothing and cost the
   * second one its stability.
   *
   * IT IS NOT "WHAT THE PANEL HAS RENDERED", and the difference is honest rather than
   * pedantic: this module cannot observe the panel's read completing. If the two
   * disagree it is in the safe direction — the panel's read happens at or after the
   * bundle's, so at worst an already-held proposal is re-read silently.
   */
  proposal: number | undefined;
}

/**
 * THE FILTER, AND IT IS THE REASON `changed_at_rev` IS ON THE WIRE.
 *
 * ~~"THE ONE FILTER"~~ — corrected in place rather than reworded, because "one"
 * was not a description of the mechanism but the DEFECT in it. There are two
 * floors, they answer two different questions, and `ChangeFloors` above carries
 * the measurement that says so.
 *
 * An entry's `changed_at_rev` is the record's own `rev` at the save that last
 * changed that entity. A view that already holds the record at `rev` R has, by
 * construction, already adopted every save up to and including R — so an entry at
 * `changed_at_rev <= R` is not news to it, whoever made that save.
 *
 * THAT ARGUMENT IS SOUND FOR EXACTLY THE KINDS THE RECORD READ ADOPTS. It holds for
 * `experiment` and for `run`, and for an unknown kind it is the fail-quiet direction.
 * It does NOT hold for `proposal`, because the record read adopts no proposal state:
 * the list lives behind its own route and its own component. So a proposal entry is
 * measured against `floors.proposal` — where the PROPOSAL read stands — and every
 * other kind against `floors.record`.
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
  floors: ChangeFloors,
): RecordChangeSummary | null {
  // `undefined` means the screen has not told us where that read stands. Nothing is
  // filtered then, because a filter with no floor would have to invent one — and
  // inventing `0` would report the entire record on the first poll.
  const recordFloor = floors.record ?? -1;
  const proposalFloor = floors.proposal ?? -1;
  const runFloor = floors.run ?? -1;

  const runIds = new Set<string>();
  const proposalIds = new Set<string>();
  const proposalStates = new Set<string>();
  const otherKinds = new Set<string>();
  let recordMoved = false;
  let highestRev = -1;
  let proposalRev = -1;
  let runRev = -1;

  for (const entry of entries) {
    // A non-numeric or missing coordinate cannot be compared, so it is treated as
    // news rather than dropped: withholding a change because its position was
    // unreadable is the failure mode that loses one.
    const at = typeof entry.changed_at_rev === 'number' ? entry.changed_at_rev : undefined;
    // THE FLOOR IS CHOSEN BEFORE THE COMPARISON, NOT AFTER IT. Reading `entry.kind`
    // here rather than inside the switch is what keeps the two questions apart: a
    // single comparison against a single floor is precisely the shape the defect had.
    const floor =
      entry.kind === 'proposal' ? proposalFloor : entry.kind === 'run' ? runFloor : recordFloor;
    if (at !== undefined && at <= floor) continue;
    if (at !== undefined && at > highestRev) highestRev = at;

    switch (entry.kind) {
      case 'experiment':
        recordMoved = true;
        break;
      case 'run':
        runIds.add(entry.entity_id);
        if (at !== undefined && at > runRev) runRev = at;
        break;
      case 'proposal':
        proposalIds.add(entry.entity_id);
        if (at !== undefined && at > proposalRev) proposalRev = at;
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
    runRev,
    proposalRev,
  };
  return hasNews(summary) ? summary : null;
}

/**
 * HAS THE RECORD VIEW ALREADY CAUGHT UP TO EVERYTHING THIS SUMMARY REPORTED? — the
 * notice's whole rule, named and testable rather than inline.
 *
 * IT HAS EXACTLY ONE PRODUCTION CALLER — `useRecordSession`'s `activity` derivation —
 * and that is stated rather than left to be discovered, because the sibling
 * `needsCanonicalRefetch` below is extracted for the opposite reason (it had four
 * copies and the tests exercised one of them). This one is extracted so the rule can
 * be asserted directly on a summary, and so the derivation reads as a question with a
 * name instead of a comparison a reader has to decode.
 *
 * WHAT IT DECIDES, AND WHY THE ANSWER IS NOT "REFETCH". `RecordActivityNote` is a
 * visible banner whose sentence ends "What is on screen was loaded before that". Once
 * the record read has reached `highestRev` that sentence is false, so the notice must
 * not stand. Under the two floors of `ChangeFloors` a PROPOSAL entry can now survive
 * at a position the record view has already reached — that is the fix — so this
 * question has to be asked about a summary that genuinely exists, where before such a
 * summary was never produced at all.
 *
 * IT IS MEASURED AGAINST THE RECORD'S REVISION, NOT AGAINST THE PROPOSAL FLOOR, and
 * that is deliberate rather than an oversight: the notice is a statement about what is
 * ON SCREEN, and the proposal floor tracks what has been HANDED ONWARD. Using the
 * latter here would make every notice answer "caught up" the instant it was raised.
 */
export function isCaughtUp(
  summary: RecordChangeSummary,
  recordRev: number | undefined,
): boolean {
  return recordRev !== undefined && recordRev >= summary.highestRev;
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
 * ~~STATED HONESTLY, because the branch looks more load-bearing than it is: in this
 * build a proposal act ALSO advances the record's own `rev`
 * (`workspace._authoritative_signature` hashes proposals), so `recordMoved` normally
 * travels with it and the common path DOES refetch. The proposal-only branch is
 * reachable through the feed's contract — the server may serve any combination, and a
 * page boundary can split one save's entities across two pages — and that is what is
 * tested. It is not claimed to be the common case.~~
 *
 * **THAT CAVEAT IS NOW BACKWARDS, and it is struck rather than edited because it was
 * TRUE when written and is a claim a reader acts on.** Its first half still holds: a
 * proposal act does move the record's own `rev`. Its conclusion does not. Under the
 * two floors `ChangeFloors` introduces, the case where the RECORD poller resolves
 * first — measured to be the ordinary one, see that type — now yields a summary in
 * which the `experiment` entry is filtered (the record view already adopted it) and
 * the `proposal` entry survives. **A proposal-only summary is therefore the COMMON
 * shape of a colleague's proposal arriving, not the rare one**, and this gate
 * returning `false` for it is what stops each such arrival refetching three screens'
 * bundles for content none of them renders.
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

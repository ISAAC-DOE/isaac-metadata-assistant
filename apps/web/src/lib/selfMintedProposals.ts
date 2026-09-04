/*
 * SAME-TAB, IN-MEMORY, PER-EXPERIMENT MEMORY OF PROPOSAL IDS THIS TAB JUST MINTED.
 *
 * WHY THIS EXISTS. `IngestionProposalsPanel`'s arrival note is built for a
 * COLLEAGUE's change appearing unprompted — see its own header. Without this, it
 * fires identically for a proposal THIS reader just minted a moment ago, on the
 * SAME screen, via `TranscriptCapturePanel`'s finalize or `UnmappedNotesPanel`'s
 * "Propose a value from this note": the change feed reports both the same way.
 *
 * WHY THE SERVER CANNOT ANSWER THIS. `RecordChangeSummary`'s own header states the
 * change feed's field set precisely: a proposal entry carries exactly `{kind,
 * entity_id, changed_at_rev, updated_utc, state}` — no session, no actor, no
 * origin. That is a deliberate, structural guarantee (`change_feed.py` imports
 * nothing from `proposals.py`), not a gap this module works around improperly: it
 * never claims server knowledge it does not have.
 *
 * WHAT THIS THEREFORE IS, PRECISELY. A purely LOCAL, same-tab courtesy. It knows
 * only what THIS tab did, in THIS page load, and says nothing about any other tab
 * or any other reader — a second tab of the same record, or a colleague's browser,
 * is invisible to it and its arrivals are announced normally. It is fail-CLOSED in
 * the direction that matters: if this module cannot vouch for every id in a batch,
 * the whole batch is treated as a genuine arrival, never suppressed.
 *
 * WHY A MODULE-LEVEL MAP AND NOT REACT STATE OR A NEW `RecordWorkbench` PROP.
 * `TranscriptCapturePanel`, `UnmappedNotesPanel` and `IngestionProposalsPanel` are
 * SIBLINGS under `RecordWorkbench` (PR-B's file, not touched by this change) —
 * there is no shared parent state channel between them today. A JS module is a
 * singleton per page load, which is exactly the "this tab, this session" scope
 * this needs and no wider: it resets on reload, which is correct (a reload is a
 * fresh read of the record, and anything on it now is not "just mine" any more).
 */

/*
 * m7, INDEPENDENT REVIEW OF PR-D — THE TTL, JUSTIFIED AGAINST THE REAL POLL
 * CADENCE, NOT PICKED. `useRecordSync.POLL_INTERVAL_MS` is 8000 (8s) — the
 * steady-state interval `useChangeFeed` polls at once its own backoff ladder
 * (`CHANGE_FEED_DRAIN_DELAY_MS` 250ms, doubling to the 8000ms ceiling) has
 * settled. That ladder's OWN comment measures its worst-case drain window at
 * "13,000 ms" from a burst of changes to the poller catching up. So the
 * longest realistic gap between `finalize()` minting a proposal and
 * `IngestionProposalsPanel` actually SEEING it via the change feed is on the
 * order of one drain cycle plus one steady-state interval — comfortably under
 * 15s in the worst case this codebase has already measured. `TTL_MS = 30_000`
 * is roughly DOUBLE that worst case: generous enough that a slow poll cycle
 * never lets a self-minted entry expire before the arrival it was meant to
 * suppress has even been checked, short enough that this module cannot become
 * an unbounded memory holder for a tab left open for hours (see the pruning
 * below, which is what actually bounds memory — TTL alone only bounds
 * CORRECTNESS, not the size of the map without it).
 */
const TTL_MS = 30_000;

/** experimentId -> proposalId -> the ms timestamp it was minted at. */
const perExperiment = new Map<string, Map<string, number>>();

/**
 * Drops expired entries for one experiment, and the experiment's own map
 * entirely once it is empty. Called opportunistically from both exported
 * functions rather than on a timer — this module has no background work and
 * no cleanup to schedule; it only ever does anything when a caller does.
 */
function pruneExpired(set: Map<string, number>, now: number): void {
  for (const [id, at] of set) {
    if (now - at > TTL_MS) set.delete(id);
  }
}

/** Record that this tab just minted these proposal ids for this experiment. */
export function markSelfMintedProposals(experimentId: string, proposalIds: readonly string[]): void {
  if (proposalIds.length === 0) return;
  const now = Date.now();
  const set = perExperiment.get(experimentId) ?? new Map<string, number>();
  pruneExpired(set, now);
  for (const id of proposalIds) set.set(id, now);
  perExperiment.set(experimentId, set);
}

/**
 * True only when EVERY id in `proposalIds` is a live self-minted entry for this
 * experiment. An empty list is never "all self-minted" — there is nothing to
 * vouch for, so the caller's own "nothing arrived" handling applies instead.
 */
export function allProposalsSelfMinted(experimentId: string, proposalIds: readonly string[]): boolean {
  if (proposalIds.length === 0) return false;
  const set = perExperiment.get(experimentId);
  if (!set) return false;
  const now = Date.now();
  pruneExpired(set, now);
  if (set.size === 0) {
    perExperiment.delete(experimentId);
    return false;
  }
  return proposalIds.every((id) => set.has(id));
}

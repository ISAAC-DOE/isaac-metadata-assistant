import { useEffect, useRef, useState } from 'react';
import { api } from './api';

/**
 * HOW MUCH CAPTURED MATERIAL THIS RECORD HOLDS — read from the server's own
 * totals, never counted on this side.
 *
 * ── WHY IT EXISTS ───────────────────────────────────────────────────────────
 *
 * The record sidebar promotes capture to a destination of its own, and a
 * destination that says nothing about what is behind it is a label. These three
 * numbers are what a scientist wants before deciding to go there: how much has
 * been captured, how much is waiting on a judgement, and whether anything stored
 * could not be read back.
 *
 * ── EVERY NUMBER IS THE SERVER'S OWN TOTAL ──────────────────────────────────
 *
 * `notes.total` is how many notes the record HOLDS (`_notes_payload`: "`total`
 * counts what EXISTS, never what was returned"), and `proposals.by_state.open`
 * is counted server-side over the whole record rather than over the window this
 * request asked for. Nothing here reads `.length` off a fetched array — that is
 * the defect `CLAUDE.md` §11 records four separate surfaces committing, and the
 * proposals read is deliberately `limit: 1`, so a length-based count here would
 * report "1 proposal" on a record holding fifty.
 *
 * ── IT DESCRIBES A DESTINATION THE READER IS NOT IN ────────────────────────
 *
 * `enabled` is false while the capture workspace is the OPEN one, and the hook
 * then reads nothing and reports nothing. That is not a saving trick, it is the
 * rule the summary exists under: on the capture workspace the three panels are
 * on screen stating their own counts, in more detail and from their own reads.
 * A sidebar that fetched the same two lists again to restate them would (a)
 * double `GET .../notes` and `GET .../proposals` on the busiest surface of the
 * record — the exact duplication `notes-live-refresh-integration.test.tsx`
 * counts at the wire — and (b) maintain a SECOND copy of a number already on
 * screen, free to disagree with it for one poll interval.
 *
 * IT RE-READS ON THE WAY BACK OUT, because a note captured inside would
 * otherwise leave a stale count behind. Nothing stale is ever shown: while the
 * workspace is open the line is absent, not frozen.
 *
 * ── IT FOLLOWS THE CHANGE FEED, NOT THE RECORD'S VERSION ────────────────────
 *
 * Keying the re-read on `detail.version` would issue this pair on EVERY save —
 * every answered question, every field edit — which is a cost the record screen
 * has spent two sessions removing. The change feed is the signal the capture
 * panels themselves already follow (`UnmappedNotesPanel`,
 * `IngestionProposalsPanel`), and it COALESCES: ten saves between two polls are
 * one forward step, so this re-reads once rather than ten times. The cost of
 * that choice, stated rather than discovered: a scientist's OWN capture is
 * reflected here at the next poll, not at the instant of the write. The panel
 * they wrote it in updates immediately; this summary is a few seconds behind it.
 *
 * ── A FAILED RE-READ CLEARS THE SUMMARY RATHER THAN KEEPING THE OLD ONE ─────
 *
 * There is no room in a 212px sidebar to qualify a number with the version it
 * was read at, and a count that silently describes an older record is exactly
 * the class of claim this project refuses. Absence is unambiguous: the nav
 * renders no summary line at all, which reads as "not known" and cannot be
 * mistaken for the record holding nothing — that is a different, explicit
 * sentence (`LABELS.captureNavEmpty`).
 *
 * AND THE WITHHOLDING CAN LAST THE WHOLE SESSION, which is the half a reader of
 * the paragraph above would not guess and which is therefore stated rather than
 * left to be discovered. There is NO timed retry. A cleared summary comes back
 * on exactly three events, all of which re-run the read effect:
 *
 *   1. a FORWARD change-feed step for this record (the `generation` bump);
 *   2. an `enabled` TRANSITION — opening the capture workspace and leaving it
 *      again, since `enabled` is in the effect's dependency list;
 *   3. switching to another record and back.
 *
 * On a QUIET record that the reader does not navigate away from, one transient
 * 503 therefore removes the line until they do one of those. That is accepted:
 * the alternative is a retry loop issuing the same unbounded read against a
 * server that just failed, to restore a line that is a convenience. It is a
 * missing convenience, never a wrong number.
 */
export interface CaptureSummary {
  /**
   * `notes.total` — how many notes the record HOLDS, whatever was returned.
   *
   * IT INCLUDES DISMISSED NOTES, and that is the route's own definition rather
   * than a choice made here: `GET .../notes` states "DISMISSED NOTES ARE
   * INCLUDED … dismissing is a review state reached by an explicit act … it is
   * not a deletion, and this API has no operation that deletes a note". So a
   * record whose eight notes were every one dismissed reads "8 notes" — which
   * is true of what the record holds, and is deliberately not a claim about how
   * many are outstanding. The outstanding number this row shows is the
   * proposals one; notes are a size, not a queue.
   */
  notesTotal: number;
  /** `proposals.by_state.open` — how many are awaiting a person's judgement. */
  proposalsOpen: number;
  /**
   * Stored entries neither list could present, summed across the two.
   *
   * COUNTED RATHER THAN DROPPED, for the reason both payloads count their own:
   * the server preserves them verbatim and can neither say what they contain nor
   * discard them. Summing the two kinds into one number is a summary decision —
   * the panels separate them — but reporting zero while the record holds some
   * would let "3 notes" read as the whole of what was captured when it is not.
   */
  unreadableEntries: number;
}

/*
 * ── FOLLOW-UP, FILED RATHER THAN IMPLIED ───────────────────────────────────
 *
 * THE RIGHT END-STATE IS A `capture_summary` BLOCK ON THE RECORD'S OWN DETAIL
 * PAYLOAD — `{notes_total, proposals_open, unreadable_entries}` beside the
 * fields `GET /api/experiments/{id}` already serves. The three numbers are
 * already computed server-side, on data the route has in hand; serving them
 * there would cost ZERO additional requests, arrive already consistent with the
 * rest of the bundle, need no change feed key, and delete this whole hook.
 *
 * It is NOT DONE HERE because it is a server change and this slice was scoped
 * to the frontend. Everything below is the client-side approximation of it, and
 * the approximation's whole cost is the two requests this file issues. A future
 * session picking that up should expect to remove this file, not extend it.
 */

/**
 * @param experimentId the record being described
 * @param activityRev  the highest change-feed position this screen has observed
 *                     for this record's notes or proposals, or `-1` when the
 *                     feed has reported nothing. Only FORWARD motion re-reads.
 * @param enabled      false while the capture workspace itself is open — see the
 *                     header. The hook then reads nothing and returns `null`.
 */
export function useCaptureSummary(
  experimentId: string,
  activityRev: number,
  enabled: boolean,
): CaptureSummary | null {
  /*
   * THE RECORD ID IS HELD BESIDE THE SUMMARY, so a summary read for the previous
   * record can never be rendered under the current one's label. A plain
   * `useState<CaptureSummary | null>` would keep the old numbers on screen for
   * the render in which the id changes and the effect has not yet run.
   */
  const [state, setState] = useState<{ id: string; summary: CaptureSummary | null }>({
    id: experimentId,
    summary: null,
  });

  // The feed position this hook has already re-read for. Reset with the record.
  const readAt = useRef(activityRev);
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    readAt.current = activityRev;
    // No `setGeneration` here: the read effect below already depends on
    // `experimentId`, so a record switch reads exactly once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [experimentId]);

  useEffect(() => {
    if (activityRev <= readAt.current) return;
    readAt.current = activityRev;
    setGeneration((g) => g + 1);
  }, [activityRev]);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    Promise.all([
      /*
       * THE FILTER IS NOT ABOUT THE FILTER, and without this comment it reads
       * as a bug. Nothing here wants dismissed notes; the rows are discarded.
       *
       * `_notes_payload` computes `total`, `by_state` and `unreadable_entries`
       * over `exp.notes` — the WHOLE record — and the route applies `state`
       * only to the rows it selects ("`total` counts what EXISTS, never what
       * was returned", `apps/api/isaac_api/routes.py:11235-11259`). So every
       * number this hook reads is identical with the filter and without it,
       * while the ROW array shrinks. `GET .../notes` has no `limit`, so this is
       * the only bound available to a client today.
       *
       * MEASURED against the running API, 2026-09-10: on the 8-note record
       * 7,544 B -> 2,023 B (-73.2%); on the 3-note record 4,494 B -> 2,023 B
       * (-55.0%); `total`, `by_state` and `unreadable_entries` byte-identical
       * in every pair. 2,023 B is the fixed envelope — the server's own
       * vocabularies and three path lists — which the unfiltered form adds
       * ~610 B per note to, unbounded.
       *
       * `dismissed` rather than another state because it is the one notes LEAVE
       * the queue into, so it is empty on an untriaged record, which is the
       * common case for a sidebar count. IT IS NOT GUARANTEED EMPTY: a heavily
       * triaged record returns its dismissed rows here. The claim is that this
       * is never larger than the unfiltered read and is usually far smaller —
       * not that it is minimal.
       */
      api.listNotes(experimentId, { state: 'dismissed' }),
      // ONE ROW, for the same reason and with the same guarantee: only `total`,
      // `by_state` and `unreadable_entries` are read, and the server computes
      // all three over the whole record regardless of the window.
      api.listProposals(experimentId, { limit: 1 }),
    ])
      .then(([notes, proposals]) => {
        if (!alive) return;
        setState({
          id: experimentId,
          summary: {
            notesTotal: notes.total,
            proposalsOpen: proposals.by_state.open ?? 0,
            unreadableEntries: notes.unreadable_entries + proposals.unreadable_entries,
          },
        });
      })
      .catch(() => {
        // See the header: a summary that could not be re-read is withheld, not
        // kept. The record screen already states a failed refresh in its own
        // live-sync note; this one simply stops asserting.
        if (alive) setState({ id: experimentId, summary: null });
      });
    return () => {
      alive = false;
    };
  }, [experimentId, generation, enabled]);

  return enabled && state.id === experimentId ? state.summary : null;
}

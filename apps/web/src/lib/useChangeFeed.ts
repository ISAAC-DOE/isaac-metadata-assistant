/*
 * POLLING of one record's COALESCING STATE FEED.
 *
 * TWO WORDS IN THAT SENTENCE ARE LOAD-BEARING AND NEITHER IS DECORATION.
 *
 * "Polling", never "real-time", never "near-real-time" and never "live". THIS HEADING
 * USED TO READ "NEAR-REAL-TIME", and the paragraph under it then admitted, in its own
 * words, that "the delay between a change and this hook seeing it is bounded by
 * nothing this repository has measured" — which is precisely the reason the phrase was
 * not available to use. It is a claim about LATENCY, and a latency claim is earned by
 * a measurement or not made; the cadence is a timer with jitter and an exponential
 * backoff that pauses entirely while the tab is hidden, so no bound exists to claim.
 * What this file can honestly claim is EVENTUAL ARRIVAL while the surface is open, and
 * `CHANGE_FEED_CADENCE_CLAIM` is the copy that says exactly that to a person — it was
 * already right, which is why it does not change. There is no SSE and no WebSocket
 * here — deliberately, and not merely because the brief said so: a push channel would
 * be a second synchronisation scheme beside `useRecordSync`, and this file exists
 * precisely to avoid inventing one.
 *
 * "Coalescing state feed", never "event log". The server reports that an entity is at
 * a version later than your cursor. It does not report every act, it cannot report
 * deletions, and a client must not count entries as though they were events. See
 * `apps/api/isaac_api/change_feed.py`, whose three published properties this file's
 * copy constants deliberately do not paraphrase.
 *
 * ARCHITECTURE: the SAME shape as `useRecordSync` — one poller per mounted surface,
 * per-effect-run locals, a `setTimeout` chain rather than `setInterval` so polls can
 * never overlap, ±20% jitter so two tabs desync, exponential backoff to 60 s, and an
 * honest `degraded` flag after three consecutive failures. The CADENCE constants are
 * IMPORTED from that module rather than re-declared: two pollers against one
 * deployment with two different cadences would be two things to reason about.
 *
 * ONE DELIBERATE DIVERGENCE, AND THE SENTENCE ABOVE USED TO DENY IT. It read "nothing
 * here justifies a second number", and then this file grew one — so the claim is
 * narrowed to CADENCE rather than left standing while being false. `useRecordSync`
 * watches a single record whose answer is one bit; this feed is BOUNDED and PAGED, so
 * a client that only ever polls at the cadence drains one page per interval and a
 * 1,000-run backlog takes twenty intervals to reach the present. `has_more` is what
 * the server says about that, the first version of this hook read it NOWHERE, and no
 * test caught it because no fixture ever set it. `CHANGE_FEED_DRAIN_DELAY_MS` is that
 * second number, and it is a different KIND of number — the gap between two pages of
 * one read, not the gap between two reads.
 *
 * WHAT IT NEVER DOES, in the same spirit as `useRecordSync`: it does not fetch the
 * record, does not merge anything, does not submit anything, and does not overwrite
 * unsent input. It hands the caller the entries and the cursor; the surface decides.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { ApiChangeEntry } from './types';
import {
  DEGRADED_THRESHOLD,
  POLL_INTERVAL_MS,
  POLL_MAX_BACKOFF_MS,
} from './useRecordSync';

export { DEGRADED_THRESHOLD, POLL_INTERVAL_MS, POLL_MAX_BACKOFF_MS };

/**
 * HOW LONG TO WAIT BEFORE FETCHING THE **NEXT PAGE** OF A BACKLOG.
 *
 * The feed is bounded — the server hands back at most `limit` entries and says
 * `has_more` — so a client that always waits a full cadence between requests drains
 * at one page per interval. On the workload this feature exists for that is not a
 * detail: a 1,000-run record is 20 pages, which at the 8 s cadence is over two and a
 * half MINUTES before the surface has caught up to now, while `CHANGE_FEED_CADENCE_CLAIM`
 * tells the reader an update "appears shortly after it is made". The first version of
 * this hook ignored `has_more` altogether and no test noticed, because no fixture ever
 * set it.
 *
 * It is deliberately NOT zero and deliberately NOT jittered. Not zero, because a
 * backlog should not become the fastest request loop this application can make; not
 * jittered, because jitter exists to desync two TABS at the cadence, and these
 * requests are continuations of one read rather than a new cadence tick.
 */
export const CHANGE_FEED_DRAIN_DELAY_MS = 250;

/**
 * HOW MANY CONSECUTIVE BACKLOG PAGES BEFORE FALLING BACK TO THE ORDINARY CADENCE.
 *
 * A bound on a SERVER defect, not on legitimate paging. Draining is guaranteed to
 * terminate on its own — every accepted page moves the cursor past what it returned,
 * so `remaining` strictly decreases — and the fast-follow additionally requires the
 * cursor to have MOVED, so a server answering `has_more: true` with an unchanged
 * cursor is refused a second fast request rather than being hammered. This cap is the
 * belt to that pair of braces: 20 pages is 1,000 entries at the default window, past
 * which the client keeps draining at the ordinary cadence rather than stopping. No
 * entry is skipped either way; only the rate changes.
 */
export const CHANGE_FEED_MAX_CONSECUTIVE_DRAINS = 20;

/**
 * THE CADENCE CLAIM, as a person would read it.
 *
 * A constant rather than a string inside a component, for the reason
 * `ASSISTANT_NO_MODEL_CLAIM` is one: the claim has to be pinnable by a test, and a
 * copy written at its render site is a copy free to drift from what the code does.
 *
 * It says "shortly after" rather than naming a number of seconds, and that is the
 * honest form: the interval is 8 s only while every poll succeeds and the tab is
 * visible — a backoff, a hidden tab, or a slow response all move it, and none of
 * those is something the reader can see.
 */
export const CHANGE_FEED_CADENCE_CLAIM =
  'This view checks for changes periodically while it is open and the tab is ' +
  'visible, so an update made elsewhere appears shortly after it is made rather ' +
  'than instantly.';

/**
 * WHAT THE FEED CANNOT TELL A PERSON — the two limitations, in product language.
 *
 * Deliberately NOT a paraphrase of the server's `DELETION_LIMITATION` and
 * `GAP_GUARANTEE`. Those are written for a client author and name `updated_utc`, a
 * cursor and a resync; this is written for a scientist and names a run and a list.
 * Both have to be true, and the test that pins this one also pins that it does not
 * quietly upgrade the guarantee — no "every change", no "always", no "live".
 */
export const CHANGE_FEED_LIMITS_CLAIM =
  'It reports which parts of this record have changed, not a history of what was ' +
  'done: several edits to one run appear as one entry, and a run that was removed ' +
  'is not reported at all — it simply stops appearing.';

interface UseChangeFeedOptions {
  /**
   * Fired with the entries of each non-empty page, in feed order. Never called with
   * an empty array: "nothing changed" is the absence of a call, not a call with
   * nothing in it, so a surface cannot mistake a quiet poll for a change.
   */
  onChanges: (entries: ApiChangeEntry[]) => void;
  /** When false, no polling happens (also gated on a defined recordId). */
  enabled?: boolean;
  /** Page size to ask for. The server clamps it into `[1, 200]` and reports back. */
  limit?: number;
}

/** ±20% jitter so multiple open tabs desync. Tests pin `Math.random`. */
function withJitter(ms: number): number {
  const factor = 1 + (Math.random() * 0.4 - 0.2);
  return Math.round(ms * factor);
}

/**
 * VISIBILITY, ASKED THE WAY THE BRIEF SPECIFIES IT.
 *
 * `visibilityState === 'visible'` rather than `!document.hidden`. The two are
 * complements today and this is the positive form — it treats `prerender` and any
 * future non-visible state as NOT visible, which is the fail-quiet direction for a
 * poller. `useRecordSync` asks the other way; both are correct, and the difference is
 * recorded here rather than silently harmonised because changing that module's
 * predicate is not this slice's business.
 */
function isVisible(): boolean {
  return document.visibilityState === 'visible';
}

export function useChangeFeed(
  recordId: string | undefined,
  opts: UseChangeFeedOptions,
): { degraded: boolean; cursor: string | undefined; checkNow: () => void } {
  const { onChanges, enabled = true, limit } = opts;
  const [degraded, setDegraded] = useState(false);
  // The cursor is state so a surface can show progress, and a ref so the poll chain
  // reads the CURRENT one without re-subscribing the effect on every page.
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const cursorRef = useRef<string | undefined>(undefined);

  const active = enabled && !!recordId;

  const onChangesRef = useRef(onChanges);
  onChangesRef.current = onChanges;

  const currentRef = useRef({ recordId });
  currentRef.current = { recordId };

  const checkNowRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!active) {
      checkNowRef.current = () => {};
      return;
    }

    // PER-EFFECT-RUN LOCALS, for the reason `useRecordSync` sets out at length: a
    // torn-down run's late `.finally` must only ever touch its own already-cleared
    // locals, never a newer run's timer. Getting this wrong there produced a poller
    // that silently stopped while showing no degraded state.
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;
    let inFlight = false;
    let failures = 0;
    let interval = POLL_INTERVAL_MS;
    let cancelled = false;
    // Consecutive backlog pages fetched at `CHANGE_FEED_DRAIN_DELAY_MS`. Reset by any
    // poll that is not a drain, so a later backlog gets a full budget of its own.
    let drains = 0;

    // A fresh record starts a fresh feed: drop the previous record's cursor rather
    // than resuming a position in an order it does not belong to. The server would
    // refuse it (`422`, `reason: wrong_feed`), so this is belt-and-braces — but a
    // client that knowingly sends a foreign cursor is a client asking to be refused.
    cursorRef.current = undefined;
    setCursor(undefined);
    setDegraded(false);

    const pollId = recordId!;

    const clearTimer = () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };

    const schedule = (delay: number) => {
      if (cancelled || !isVisible()) return;
      clearTimer();
      timer = setTimeout(runPoll, delay);
    };

    function runPoll() {
      if (cancelled || !isVisible()) return;
      if (inFlight) return; // never overlap an in-flight poll
      inFlight = true;
      const ac = new AbortController();
      controller = ac;
      // Decided in `.then`, read in `.finally`. A per-poll local rather than a shared
      // one, for the reason every other local in this effect is per-run: a settled
      // poll must never steer a scheduling decision that belongs to a later one.
      let drainNext = false;
      const cursorBefore = cursorRef.current;

      api
        .getChanges(
          pollId,
          { cursor: cursorRef.current, ...(limit !== undefined ? { limit } : {}) },
          ac.signal,
        )
        .then((page) => {
          if (cancelled || ac.signal.aborted) return;
          // Stale guard: the record must not have moved on since this poll started.
          if (currentRef.current.recordId !== pollId) return;
          failures = 0;
          interval = POLL_INTERVAL_MS;
          setDegraded(false);
          // ADVANCE THE CURSOR EVEN ON AN EMPTY PAGE. The server returns the position
          // the caller was already at, so this is a no-op then — but writing it
          // unconditionally means there is one rule ("the cursor is whatever the last
          // page said") rather than two, and no branch to get backwards.
          cursorRef.current = page.next_cursor;
          setCursor(page.next_cursor);
          if (page.changes.length > 0) onChangesRef.current(page.changes);
          // PAGE THROUGH A BACKLOG rather than waiting a full cadence per page. All
          // three conditions are load-bearing: the server has to SAY there is more,
          // the cursor has to have MOVED (otherwise a fast follow-up would ask the
          // identical question), and the budget has to be unspent.
          drainNext =
            page.has_more &&
            page.next_cursor !== cursorBefore &&
            drains < CHANGE_FEED_MAX_CONSECUTIVE_DRAINS;
          // THE BUDGET IS SPENT PER BACKLOG, NOT PER POLL, AND THAT DISTINCTION IS THE
          // WHOLE CAP. It used to reset to 0 on the poll that hit the ceiling, so the
          // next cadence tick began a FRESH 20-page burst: against a server answering
          // `has_more: true` with a moving cursor forever, the sustained rate was
          // ~21 requests per (8s + 20x250ms) — about 1.6 req/s indefinitely, ~13x the
          // ordinary cadence — while the constant's own docstring promised the client
          // "keeps draining at the ORDINARY CADENCE". An independent review measured
          // that; the claim was false and the belt re-buckled itself.
          //
          // It now clears only when the server says the backlog is done. So a capped
          // client really does fall back to one request per cadence until `has_more`
          // goes false, which is what the sentence above has always said.
          drains = page.has_more ? drains + 1 : 0;
        })
        .catch(() => {
          if (cancelled || ac.signal.aborted) return;
          failures += 1;
          if (failures >= DEGRADED_THRESHOLD) setDegraded(true);
          interval = Math.min(interval * 2, POLL_MAX_BACKOFF_MS);
          // A failed poll is never a drain, and it forfeits the budget: backing off
          // and fast-following are contradictory instructions.
          drains = 0;
        })
        .finally(() => {
          inFlight = false;
          controller = null;
          // The next poll is scheduled only after this one SETTLED — a setTimeout
          // chain, never setInterval, which is what makes non-overlap structural.
          schedule(drainNext ? CHANGE_FEED_DRAIN_DELAY_MS : withJitter(interval));
        });
    }

    checkNowRef.current = () => {
      if (cancelled) return;
      clearTimer();
      runPoll();
    };

    const onVisibility = () => {
      if (!isVisible()) {
        // Pause. An in-flight poll's `finally` short-circuits in `schedule`.
        clearTimer();
      } else {
        checkNowRef.current();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);

    schedule(withJitter(POLL_INTERVAL_MS));

    return () => {
      cancelled = true;
      clearTimer();
      controller?.abort();
      controller = null;
      inFlight = false;
      checkNowRef.current = () => {};
      document.removeEventListener('visibilitychange', onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, recordId, limit]);

  const checkNow = useCallback(() => checkNowRef.current(), []);
  return { degraded, cursor, checkNow };
}

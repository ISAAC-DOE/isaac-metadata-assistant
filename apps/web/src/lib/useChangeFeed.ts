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
 * TWO DELIBERATE DIVERGENCES. THE SENTENCE ABOVE USED TO DENY THE FIRST, AND THE
 * SECOND WAS MEASURED INTO EXISTENCE — see `changeFeedBacklogDelayMs`, whose
 * escalating CONTINUATION tier exists because the burst budget alone left a backlog
 * of one page more than the ceiling costing a full 8 s cadence for that one page
 * (measured: caught up at mount+21,000 ms for 22 pages against mount+13,000 ms for
 * 21). The hook also now REPORTS whether it is caught up, from the server's own
 * `has_more`/`remaining` rather than from anything it infers, so a surface can say
 * "still catching up" truthfully instead of showing a stale view that looks current.
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
 * HOW MANY CONSECUTIVE BACKLOG PAGES MAY BE FETCHED AT THE FULL DRAIN RATE.
 *
 * A bound on a SERVER defect, not on legitimate paging. Draining is guaranteed to
 * terminate on its own — every accepted page moves the cursor past what it returned,
 * so `remaining` strictly decreases — and the fast-follow additionally requires the
 * cursor to have MOVED, so a server answering `has_more: true` with an unchanged
 * cursor is refused a second fast request rather than being hammered. This cap is the
 * belt to that pair of braces: 20 pages is 1,000 entries at the default window.
 *
 * ITS NAME AND VALUE ARE UNCHANGED; WHAT HAPPENS AT THE CEILING IS NOT. It used to
 * mean "past here, one page per ORDINARY CADENCE", and the cost of that was measured
 * rather than argued: a backlog of 22 pages caught up at mount+21,000 ms while 21
 * pages caught up at mount+13,000 ms — **8,000 ms for one extra entry**, a cliff at a
 * number no scientist can see. It is now the first of two tiers; see
 * `changeFeedBacklogDelayMs` for the second and for the rate bound that replaces the
 * cliff. No entry is skipped in either tier; only the rate changes.
 */
export const CHANGE_FEED_MAX_CONSECUTIVE_DRAINS = 20;

/**
 * THE DELAY BEFORE THE NEXT BACKLOG PAGE, given how many have already been taken
 * consecutively. The ONE place the drain rate is decided, exported so the contract
 * document and the tests pin the same function the hook runs rather than a
 * transcription of it.
 *
 * TWO TIERS, AND THE SECOND ONE IS WHY THIS FUNCTION EXISTS.
 *
 *   * **Burst** (`drainsSoFar < CHANGE_FEED_MAX_CONSECUTIVE_DRAINS`):
 *     `CHANGE_FEED_DRAIN_DELAY_MS`, i.e. 250 ms — unchanged.
 *   * **Continuation** (at and past the ceiling): the delay DOUBLES from the drain
 *     delay and is capped at `POLL_INTERVAL_MS`, giving 500, 1000, 2000, 4000, 8000,
 *     8000, … So the client keeps paging, at a rate that decays to exactly the
 *     ordinary cadence and never exceeds it.
 *
 * WHAT THIS BUYS, MEASURED (limit 50, jitter pinned to 1.0, mount at t=0):
 *
 *   | backlog | before | after |
 *   |---|---|---|
 *   | 21 pages (the ceiling) | caught up at +13,000 ms | +13,000 ms — unchanged |
 *   | 22 pages (one past it) | +21,000 ms | **+13,500 ms** |
 *   | 25 pages | +45,000 ms | **+20,500 ms** |
 *   | 100 pages | +645,000 ms | **+620,500 ms** |
 *
 * WHAT IT DELIBERATELY DOES NOT DO — and this is the constraint the design was
 * written around rather than an omission. It does NOT refill the burst budget at the
 * ceiling. That was tried once and measured as a defect: resetting the counter there
 * made every cadence tick start a fresh 20-page burst, sustaining ~1.6 req/s
 * indefinitely against a server that answers `has_more: true` forever, while this
 * module's own prose promised the ordinary cadence. The escalation keeps that promise
 * literally — in the limit the continuation delay IS `POLL_INTERVAL_MS`.
 *
 * THE HARD RATE BOUND, which is the property that makes an unbounded loop impossible
 * rather than merely unlikely: under a server answering `has_more: true` with a moving
 * cursor forever, the delays after the first page are 250 x 20, then 500, 1000, 2000,
 * 4000, then `POLL_INTERVAL_MS` forever. So in any window of T milliseconds the client
 * issues **at most 26 + T / POLL_INTERVAL_MS requests** — one more than the 25 pages
 * that fit in the transition, plus the cadence. Pinned by
 * `change-feed.test.ts` -> "sustained has_more never exceeds the documented rate bound".
 *
 * The continuation delay is NOT jittered, for the same reason the burst delay is not:
 * jitter desynchronises two TABS at the cadence, and these requests are continuations
 * of one read. At the ceiling that means an unjittered 8,000 ms against the cadence's
 * jittered 8,000 ± 20%, which is a difference of at most 1.6 s in when one tab's
 * catch-up request lands and is recorded here rather than engineered away.
 */
export function changeFeedBacklogDelayMs(drainsSoFar: number): number {
  if (drainsSoFar < CHANGE_FEED_MAX_CONSECUTIVE_DRAINS) return CHANGE_FEED_DRAIN_DELAY_MS;
  // Clamped so a very long-lived backlog cannot turn the exponent into `Infinity`
  // before `Math.min` sees it. 32 doublings is already far past the ceiling.
  const steps = Math.min(drainsSoFar - CHANGE_FEED_MAX_CONSECUTIVE_DRAINS + 1, 32);
  return Math.min(CHANGE_FEED_DRAIN_DELAY_MS * 2 ** steps, POLL_INTERVAL_MS);
}

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

export interface ChangeFeedState {
  /** Three consecutive failed polls: the feed is not updating and says so. */
  degraded: boolean;
  cursor: string | undefined;
  /**
   * THE SERVER'S OWN `has_more` FROM THE LAST SUCCESSFUL PAGE — never an inference
   * from `changes.length === limit`, which would be wrong in both directions (a
   * full page can be the last one, and the server clamps the limit).
   *
   * `true` means the deployment says there are entities this client has not been
   * handed yet, so a surface that renders "up to date" while this is `true` is
   * making a claim the server has contradicted. It is deliberately NOT cleared by a
   * failed poll: a failure tells you nothing about whether you caught up, and the
   * last thing the server said is still the last thing it said.
   *
   * It stays `true` while the stuck-cursor guard is refusing to fast-follow, which
   * is exactly the state in which a surface must not claim to be current.
   */
  catchingUp: boolean;
  /**
   * THE SERVER'S OWN `remaining` — entities after the page this client last read —
   * or `null` when no successful page has arrived yet, when the server did not send
   * a finite number, or when a refused cursor has just been dropped (at which point
   * the last figure describes a position this client no longer holds).
   *
   * `null` is "this client does not know", never "zero". A surface that renders it
   * as a count must branch on `null` rather than defaulting it.
   */
  remaining: number | null;
  checkNow: () => void;
}

export function useChangeFeed(
  recordId: string | undefined,
  opts: UseChangeFeedOptions,
): ChangeFeedState {
  const { onChanges, enabled = true, limit } = opts;
  const [degraded, setDegraded] = useState(false);
  // The cursor is state so a surface can show progress, and a ref so the poll chain
  // reads the CURRENT one without re-subscribing the effect on every page.
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const cursorRef = useRef<string | undefined>(undefined);
  const [catchingUp, setCatchingUp] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);

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
    // A fresh feed is one nothing is known about yet — not one known to be caught up.
    setCatchingUp(false);
    setRemaining(null);

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
      //
      // `null` means "no backlog continuation — use the ordinary cadence". A NUMBER
      // is the exact delay this poll's answer earned, computed by
      // `changeFeedBacklogDelayMs` at the moment the page was read rather than
      // re-derived in `.finally` from a counter that has since moved.
      let backlogDelay: number | null = null;
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

          // HAND THE ENTRIES OVER **BEFORE** ADOPTING THE POSITION PAST THEM, and
          // that order is the whole no-loss guarantee rather than a stylistic
          // preference. It used to be the other way round, and the consequence was
          // measurable: a consumer that threw — a classifier meeting a `kind` it had
          // never seen, a reducer over a malformed entry — left the cursor already
          // advanced past a page nobody had processed, and the next request resumed
          // AFTER it. The page was gone, silently, and the poll looked successful.
          //
          // Written this way, a throwing consumer takes the whole `.then` into the
          // `.catch` below with the cursor untouched, so the very same page is asked
          // for again on the next poll. The failure is loud (it counts toward
          // `degraded`) and it is lossless, which is the pair worth having. Nothing
          // below this line can run without the entries having been delivered.
          if (page.changes.length > 0) onChangesRef.current(page.changes);

          failures = 0;
          interval = POLL_INTERVAL_MS;
          setDegraded(false);
          // ADVANCE THE CURSOR EVEN ON AN EMPTY PAGE. The server returns the position
          // the caller was already at, so this is a no-op then — but writing it
          // unconditionally means there is one rule ("the cursor is whatever the last
          // page said") rather than two, and no branch to get backwards.
          cursorRef.current = page.next_cursor;
          setCursor(page.next_cursor);

          // WHETHER THIS CLIENT IS CAUGHT UP IS THE SERVER'S ANSWER, NOT A GUESS.
          // `has_more` is read as `=== true` so a page missing the key reads as
          // "caught up" rather than as a truthy object, and `remaining` is taken only
          // when it is a finite number — an absent or non-numeric one becomes `null`,
          // which says "this client does not know" instead of inventing a zero.
          setCatchingUp(page.has_more === true);
          setRemaining(
            typeof page.remaining === 'number' && Number.isFinite(page.remaining)
              ? page.remaining
              : null,
          );

          // PAGE THROUGH A BACKLOG rather than waiting a full cadence per page. Both
          // conditions are load-bearing: the server has to SAY there is more, and the
          // cursor has to have MOVED — otherwise a fast follow-up would ask the
          // identical question of a server that has already failed to answer it.
          //
          // THE BUDGET IS NO LONGER A CLIFF. `changeFeedBacklogDelayMs` decides the
          // rate from how many pages have been taken consecutively: the first 20 at
          // the drain delay, then a doubling continuation that decays to exactly the
          // ordinary cadence. So "the budget is spent" now slows the client rather
          // than dropping it to one page per 8 s at a boundary nobody can see — which
          // was measured at 8,000 ms of extra latency for ONE extra entry.
          backlogDelay =
            page.has_more && page.next_cursor !== cursorBefore
              ? changeFeedBacklogDelayMs(drains)
              : null;

          // THE COUNTER IS SPENT PER BACKLOG, NOT PER POLL, AND THAT DISTINCTION IS
          // THE WHOLE BOUND. It used to reset to 0 on the poll that hit the ceiling,
          // so the next cadence tick began a FRESH 20-page burst: against a server
          // answering `has_more: true` with a moving cursor forever, the sustained
          // rate was ~21 requests per (8s + 20x250ms) — about 1.6 req/s indefinitely,
          // ~13x the ordinary cadence. An independent review measured that; the claim
          // was false and the belt re-buckled itself. The escalation above does NOT
          // reintroduce it: the counter still clears only when the server says the
          // backlog is done, and the continuation delay only ever grows.
          //
          // It increments on `has_more` even when the cursor did NOT move. That is
          // the conservative direction — a stuck server spends the budget rather than
          // banking it — and it means a server that unsticks itself after twenty
          // stuck polls resumes in the continuation tier rather than with a fresh
          // burst. Stated because it is a real behaviour, not because it is ideal.
          drains = page.has_more ? drains + 1 : 0;
        })
        .catch((err: unknown) => {
          if (cancelled || ac.signal.aborted) return;
          // A failed poll is never a drain, and it forfeits the budget: backing off
          // and fast-following are contradictory instructions.
          drains = 0;

          // A REFUSED CURSOR IS RECOVERABLE, AND THIS HOOK USED TO NEVER RECOVER FROM
          // IT. `422 malformed_cursor` is the server's published refusal of a cursor
          // that is the wrong version, the wrong feed, or corrupt, and its single
          // documented remedy is "drop the cursor and resync". The hook did not: it
          // counted a failure, backed off, and sent THE SAME REFUSED CURSOR again on
          // every subsequent poll, forever — a feed permanently dark behind a
          // `degraded` flag whose cause no retry could clear.
          //
          // The condition is `cursorBefore !== undefined` and that is what keeps this
          // from looping. Only a request that CARRIED a cursor may drop one, so a
          // resync that is itself refused (a malformed `limit`, say — FastAPI answers
          // 422 for that too, and this client cannot tell the two apart because
          // `httpErrorWithReason` attaches the server's `error` string on 404 only)
          // falls through to the ordinary ladder below and backs off like any other
          // failure. At most every other request can take this branch.
          //
          // The backoff is deliberately NOT escalated here: the request was refused
          // for a reason that has just been fixed, so making the fix wait longer
          // would be punishing the recovery. The failure IS counted, so three
          // consecutive dark polls still say `degraded` rather than looking healthy.
          const status = (err as { status?: unknown } | null | undefined)?.status;
          if (status === 422 && cursorBefore !== undefined) {
            cursorRef.current = undefined;
            setCursor(undefined);
            // The last `remaining` described a position this client no longer holds.
            setRemaining(null);
            failures += 1;
            if (failures >= DEGRADED_THRESHOLD) setDegraded(true);
            return;
          }

          failures += 1;
          if (failures >= DEGRADED_THRESHOLD) setDegraded(true);
          interval = Math.min(interval * 2, POLL_MAX_BACKOFF_MS);
        })
        .finally(() => {
          inFlight = false;
          controller = null;
          // The next poll is scheduled only after this one SETTLED — a setTimeout
          // chain, never setInterval, which is what makes non-overlap structural.
          schedule(backlogDelay !== null ? backlogDelay : withJitter(interval));
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
  return { degraded, cursor, catchingUp, remaining, checkNow };
}

/*
 * The change-feed client and its poller.
 *
 * WHAT IS GUARDED HERE, AND WHY THE COPY IS TESTED FIRST
 * =====================================================
 * The server's feed is a COALESCING STATE FEED. The failure this file exists to
 * prevent is not that the polling breaks — a broken poller is loud — but that the
 * product describes the feed as something it is not. "Live", "real-time" and "event
 * log" are all one word away from the honest copy and all three would be false: the
 * cadence is a jittered timer that pauses while the tab is hidden, several edits to
 * one run arrive as one entry, and a removed run is never reported at all.
 *
 * So the copy constants are pinned in both directions — the claim is made, and the
 * over-claims are absent — before any behaviour is asserted.
 *
 * The poller sections mirror `record-sync.test.ts` deliberately. This hook reuses
 * `useRecordSync`'s cadence constants, its per-effect-run locals and its setTimeout
 * chain, so the properties worth pinning are the same ones, plus the two that are new
 * here: the cursor advances from the server's answer and is never constructed, and a
 * page with no entries does not call back.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { api } from '../lib/api';
import type { ApiChangeEntry, ApiChangeFeedPage } from '../lib/types';
import {
  useChangeFeed,
  changeFeedBacklogDelayMs,
  CHANGE_FEED_CADENCE_CLAIM,
  CHANGE_FEED_LIMITS_CLAIM,
  CHANGE_FEED_DRAIN_DELAY_MS,
  CHANGE_FEED_MAX_CONSECUTIVE_DRAINS,
  POLL_INTERVAL_MS,
  POLL_MAX_BACKOFF_MS,
  DEGRADED_THRESHOLD,
} from '../lib/useChangeFeed';
import { ApiError } from '../lib/api';
import { EXP_ID, stubFetchRoutes } from '../test/apiFixtures';

function page(over: Partial<ApiChangeFeedPage> = {}): ApiChangeFeedPage {
  return {
    changes: [],
    next_cursor: 'CURSOR-0',
    has_more: false,
    limit: 50,
    returned: 0,
    remaining: 0,
    kinds: ['experiment', 'run'],
    ...over,
  };
}

const ENTRY: ApiChangeEntry = {
  kind: 'run',
  entity_id: '01RUN0000000000000000000AA',
  // THE ORDERING COORDINATE. A run entry carries it alongside its own version
  // series; `updated_utc` below is display metadata and orders nothing.
  changed_at_rev: 4,
  version: 'abcdef0123456789.4',
  rev: 4,
  generation: 'abcdef0123456789',
  updated_utc: '2026-08-30T12:00:00Z',
};

/**
 * A `proposal` entry, whose SHAPE IS THE POINT: it carries the ordering coordinate,
 * a lifecycle `state` and nothing else — no `version`, no `rev`, no `generation`,
 * because `proposals.py` gives a proposal no version series and the server omits a
 * coordinate rather than synthesising one. Pinned on the wire by
 * `test_a_proposal_entry_carries_NO_CONTENT_over_the_wire`.
 */
const PROPOSAL_ENTRY: ApiChangeEntry = {
  kind: 'proposal',
  entity_id: '01SYNTHETICPROPOSALPROPOS',
  changed_at_rev: 7,
  updated_utc: '2026-08-30T12:00:00Z',
  state: 'open',
};

/**
 * jsdom's `document.visibilityState` is a getter on the prototype and is NOT moved by
 * defining `document.hidden`, which is what `record-sync.test.ts` sets. This hook asks
 * the positive question, so the tests have to move the property it actually reads —
 * a mismatch here would make every visibility assertion below pass vacuously.
 */
function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => state,
  });
  document.dispatchEvent(new Event('visibilitychange'));
}

// =============================================================================
// 1. the copy says what the feed is, and does not say what it is not
// =============================================================================

describe('change-feed copy', () => {
  it('claims a periodic check, not a live one', () => {
    expect(CHANGE_FEED_CADENCE_CLAIM).toMatch(/periodically/);
    expect(CHANGE_FEED_CADENCE_CLAIM).toMatch(/tab is\s+visible/);
    // The honest half: it says the update is NOT instant, in a sentence a scientist
    // reads rather than a footnote.
    expect(CHANGE_FEED_CADENCE_CLAIM).toMatch(/rather than instantly/);
  });

  it('says what the feed cannot report', () => {
    expect(CHANGE_FEED_LIMITS_CLAIM).toMatch(/one entry/);
    expect(CHANGE_FEED_LIMITS_CLAIM).toMatch(/removed .* not reported/);
    expect(CHANGE_FEED_LIMITS_CLAIM).toMatch(/not a history of what was done/);
  });

  it.each([
    ['real-time', /real[- ]time/i],
    ['live', /\blive\b/i],
    ['event log', /event log/i],
    ['instant (unqualified)', /\binstantly\b(?!.*rather than)/i],
    ['every change', /every change/i],
  ])('never over-claims: %s appears in neither constant', (_label, pattern) => {
    // `instantly` IS present in the cadence claim, inside "rather than instantly" —
    // the negation. The lookahead above is why that is not a false positive here, and
    // the assertion below is the one that would catch it becoming a promise.
    const both = `${CHANGE_FEED_CADENCE_CLAIM}\n${CHANGE_FEED_LIMITS_CLAIM}`;
    expect(both.replace(/rather than instantly/g, '')).not.toMatch(pattern);
  });
});

// =============================================================================
// 2. api.getChanges — the request it builds and the page it returns
// =============================================================================

describe('api.getChanges', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends no query parameters at all when none were asked for', async () => {
    const calls = stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}/changes`]: { status: 200, body: page() },
    });
    await api.getChanges(EXP_ID);
    // The cursor-less read IS the resync, and it must not be spelled `?cursor=`.
    expect(calls).toEqual([`GET /api/experiments/${EXP_ID}/changes`]);
  });

  it('appends the cursor and limit it was given, and nothing else', async () => {
    const calls = stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}/changes`]: { status: 200, body: page() },
    });
    await api.getChanges(EXP_ID, { cursor: 'OPAQUE-1', limit: 25 });
    expect(calls[0]).toBe(`GET /api/experiments/${EXP_ID}/changes?cursor=OPAQUE-1&limit=25`);
  });

  it('does not validate the limit client-side — the server clamps and says so', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}/changes`]: { status: 200, body: page({ limit: 200 }) },
    });
    // A second bound here could only disagree with the server's. The request goes out
    // as asked, and the ANSWER carries the effective limit.
    const res = await api.getChanges(EXP_ID, { limit: 100000 });
    expect(res.limit).toBe(200);
  });

  it('returns the page verbatim, including an empty one with a cursor', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}/changes`]: {
        status: 200,
        body: page({ next_cursor: 'CURSOR-END' }),
      },
    });
    const res = await api.getChanges(EXP_ID);
    expect(res.changes).toEqual([]);
    // `next_cursor` on an empty page is the position the caller was already at, and it
    // is never `null` — a client must not have to special-case "nothing to resume from".
    expect(res.next_cursor).toBe('CURSOR-END');
  });

  it('throws a typed ApiError on a refused cursor rather than degrading to a resync', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}/changes`]: {
        status: 422,
        body: { error: 'malformed_cursor', reason: 'wrong_feed' },
      },
    });
    // Silently retrying without the cursor would turn a client bug into a full replay
    // of the feed on every poll, which looks like it is working.
    await expect(api.getChanges(EXP_ID, { cursor: 'nope' })).rejects.toMatchObject({
      name: 'ApiError',
      status: 422,
    });
  });

  it('forwards the AbortSignal to fetch', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}/changes`]: { status: 200, body: page() },
    });
    const controller = new AbortController();
    await api.getChanges(EXP_ID, {}, controller.signal);
    const init = (globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } })
      .mock.calls[0][1];
    expect(init.signal).toBe(controller.signal);
  });
});

// =============================================================================
// 3. useChangeFeed — scheduling, visibility, cursor, backoff
// =============================================================================

describe('useChangeFeed', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5); // jitter factor 1.0
    setVisibility('visible');
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('does not poll when disabled or when the record id is undefined', async () => {
    const spy = vi.spyOn(api, 'getChanges');
    renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn(), enabled: false }));
    renderHook(() => useChangeFeed(undefined, { onChanges: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });
    expect(spy).not.toHaveBeenCalled();
  });

  it('does not poll while the tab is hidden, and resumes on becoming visible', async () => {
    setVisibility('hidden');
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page());
    renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });
    expect(spy).not.toHaveBeenCalled();

    await act(async () => {
      setVisibility('visible');
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(spy).toHaveBeenCalledTimes(1); // an immediate check on resume
  });

  it('stops polling when the surface unmounts', async () => {
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page());
    const { unmount } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('never overlaps: a slow in-flight poll blocks the next, checkNow included', async () => {
    const spy = vi.spyOn(api, 'getChanges').mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 4);
      result.current.checkNow();
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('sends back the cursor the server issued, and never one it built itself', async () => {
    const spy = vi
      .spyOn(api, 'getChanges')
      .mockResolvedValueOnce(page({ next_cursor: 'SERVER-A', changes: [ENTRY], returned: 1 }))
      .mockResolvedValueOnce(page({ next_cursor: 'SERVER-B' }));
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    // The FIRST poll carries no cursor: an absent cursor is the start of the order.
    expect(spy.mock.calls[0][1]).toEqual({});

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy.mock.calls[1][1]).toEqual({ cursor: 'SERVER-A' });
    expect(result.current.cursor).toBe('SERVER-B');
  });

  it('advances the cursor even when the page is empty', async () => {
    const spy = vi
      .spyOn(api, 'getChanges')
      .mockResolvedValueOnce(page({ next_cursor: 'SERVER-A' }))
      .mockResolvedValueOnce(page({ next_cursor: 'SERVER-A' }));
    renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2);
    });
    // ONE rule — "the cursor is whatever the last page said" — rather than a branch on
    // emptiness that a later edit could get backwards.
    expect(spy.mock.calls[1][1]).toEqual({ cursor: 'SERVER-A' });
  });

  it('calls back only for a page that has entries', async () => {
    const onChanges = vi.fn();
    vi.spyOn(api, 'getChanges')
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(page({ changes: [ENTRY], returned: 1 }));
    renderHook(() => useChangeFeed(EXP_ID, { onChanges }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    // "Nothing changed" is the ABSENCE of a call, never a call with an empty array —
    // a surface must not have to distinguish those two.
    expect(onChanges).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(onChanges).toHaveBeenCalledTimes(1);
    expect(onChanges).toHaveBeenCalledWith([ENTRY]);
  });

  it('forwards an explicit limit on every poll', async () => {
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page({ next_cursor: 'C1' }));
    renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn(), limit: 10 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2);
    });
    expect(spy.mock.calls[0][1]).toEqual({ limit: 10 });
    expect(spy.mock.calls[1][1]).toEqual({ cursor: 'C1', limit: 10 });
  });

  it('backs off exponentially and surfaces degraded after three failures', async () => {
    const spy = vi.spyOn(api, 'getChanges').mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(result.current.degraded).toBe(false);

    // 2nd at +2x, 3rd at +4x. `degraded` only after DEGRADED_THRESHOLD in a row, so a
    // single blip never tells a person their view is stale when it is not.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2);
    });
    expect(spy).toHaveBeenCalledTimes(2);
    expect(result.current.degraded).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 4);
    });
    expect(spy).toHaveBeenCalledTimes(DEGRADED_THRESHOLD);
    expect(result.current.degraded).toBe(true);
  });

  it('caps the backoff and clears degraded on the next success', async () => {
    const spy = vi.spyOn(api, 'getChanges').mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    // Far past the ladder's ceiling: every later poll is one POLL_MAX_BACKOFF_MS apart.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MAX_BACKOFF_MS * 12);
    });
    expect(result.current.degraded).toBe(true);
    const attempts = spy.mock.calls.length;

    spy.mockResolvedValue(page({ next_cursor: 'RECOVERED' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MAX_BACKOFF_MS);
    });
    expect(spy.mock.calls.length).toBeGreaterThan(attempts);
    expect(result.current.degraded).toBe(false);
  });

  it('drops the previous record cursor when the record changes', async () => {
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page({ next_cursor: 'A-1' }));
    const { rerender } = renderHook(({ id }) => useChangeFeed(id, { onChanges: vi.fn() }), {
      initialProps: { id: EXP_ID },
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy.mock.calls[0][1]).toEqual({});

    rerender({ id: '01OTHEREXPERIMENT000000000' });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    // A cursor is a position in ONE feed's order. Carrying it across would be asking
    // the server to refuse it — which it would, with `wrong_feed`.
    const last = spy.mock.calls[spy.mock.calls.length - 1];
    expect(last[0]).toBe('01OTHEREXPERIMENT000000000');
    expect(last[1]).toEqual({});
  });

  // ===========================================================================
  // draining a BACKLOG — the feed is bounded, so the client has to page
  // ===========================================================================
  //
  // `has_more` was returned by the server, typed in `ApiChangeFeedPage`, and read by
  // NOTHING. No fixture in this file ever set it to `true`, so the gap was invisible
  // to every test here: the hook drained one page per 8 s cadence, which on the
  // 1,000-run record this feature exists for is 20 pages and over two and a half
  // minutes to reach the present — while the copy promises "shortly after".

  it('pages straight through a backlog instead of waiting a cadence per page', async () => {
    const onChanges = vi.fn();
    const spy = vi
      .spyOn(api, 'getChanges')
      .mockResolvedValueOnce(page({ changes: [ENTRY], has_more: true, next_cursor: 'C-1' }))
      .mockResolvedValueOnce(page({ changes: [ENTRY], has_more: true, next_cursor: 'C-2' }))
      .mockResolvedValueOnce(page({ changes: [ENTRY], has_more: false, next_cursor: 'C-3' }));
    renderHook(() => useChangeFeed(EXP_ID, { onChanges }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);

    // The next two pages arrive at the DRAIN delay, not at the cadence.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CHANGE_FEED_DRAIN_DELAY_MS);
    });
    expect(spy).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CHANGE_FEED_DRAIN_DELAY_MS);
    });
    expect(spy).toHaveBeenCalledTimes(3);

    // Each page resumed from the cursor the one before it issued.
    expect(spy.mock.calls.map((c) => c[1]?.cursor)).toEqual([undefined, 'C-1', 'C-2']);
    expect(onChanges).toHaveBeenCalledTimes(3);

    // `has_more: false` ends the drain: the ordinary cadence resumes, so nothing
    // further happens at the drain delay.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CHANGE_FEED_DRAIN_DELAY_MS * 4);
    });
    expect(spy).toHaveBeenCalledTimes(3);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(4);
  });

  it('refuses to fast-follow when has_more is true but the cursor did not move', async () => {
    // The defensive half, and it is about a SERVER defect rather than a client one: a
    // page that says "there is more" while handing back the position you already held
    // is a page a fast follow-up would ask again, identically, forever.
    const spy = vi
      .spyOn(api, 'getChanges')
      .mockResolvedValue(page({ has_more: true, next_cursor: 'STUCK' }));
    renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    // The FIRST page does move the cursor (undefined -> 'STUCK'), so one drain is
    // legitimate; the one after it is not, because the cursor stops moving.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CHANGE_FEED_DRAIN_DELAY_MS);
    });
    expect(spy).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CHANGE_FEED_DRAIN_DELAY_MS * 6);
    });
    expect(spy).toHaveBeenCalledTimes(2);
    // ...and the ordinary cadence still runs, so the client is slowed, never stopped.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(3);
  });

  it('caps the FULL-RATE burst at exactly the budget, then continues rather than stalling', async () => {
    let n = 0;
    const spy = vi
      .spyOn(api, 'getChanges')
      .mockImplementation(async () =>
        page({ changes: [ENTRY], has_more: true, next_cursor: `C-${++n}` }),
      );
    renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    // One cadence poll plus exactly the budget of full-rate drains — the BURST is
    // bounded, and nothing beyond it arrives at the drain delay however long we wait.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
      await vi.advanceTimersByTimeAsync(
        CHANGE_FEED_DRAIN_DELAY_MS * CHANGE_FEED_MAX_CONSECUTIVE_DRAINS,
      );
    });
    const burst = spy.mock.calls.length;
    expect(burst).toBe(1 + CHANGE_FEED_MAX_CONSECUTIVE_DRAINS);

    // THE OLD BEHAVIOUR WAS A CLIFF AND THIS ASSERTION IS WHERE IT SHOWED. The page
    // after the budget used to wait a full POLL_INTERVAL_MS; it now waits the first
    // continuation delay, which `changeFeedBacklogDelayMs` puts at twice the drain
    // delay. Asserted through the function rather than as a literal so the ladder has
    // exactly one definition.
    const firstContinuation = changeFeedBacklogDelayMs(CHANGE_FEED_MAX_CONSECUTIVE_DRAINS);
    expect(firstContinuation).toBe(CHANGE_FEED_DRAIN_DELAY_MS * 2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(firstContinuation - 1);
    });
    expect(spy.mock.calls.length).toBe(burst); // not yet — the burst really is spent
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(spy.mock.calls.length).toBe(burst + 1);
  });

  it('does not drain while the tab is hidden', async () => {
    const spy = vi
      .spyOn(api, 'getChanges')
      .mockImplementation(async () => page({ has_more: true, next_cursor: `H-${Math.random()}` }));
    renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);

    await act(async () => {
      setVisibility('hidden');
      await vi.advanceTimersByTimeAsync(CHANGE_FEED_DRAIN_DELAY_MS * 8);
    });
    // A backlog is not a reason to keep polling a tab nobody is looking at: the drain
    // is scheduled through the same `schedule` that the visibility gate guards.
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('hands a PROPOSAL entry through untouched, coordinates it does not carry and all', async () => {
    /*
     * THE THIRD KIND. A proposal carries `changed_at_rev`, `updated_utc` and `state`
     * and NOTHING ELSE — no `version`, `rev` or `generation`, because `proposals.py`
     * gives it no version series and the server omits a coordinate rather than
     * synthesising one that would compare, sort and look real. The exact key set is
     * pinned on the wire by
     * `test_a_proposal_entry_carries_NO_CONTENT_over_the_wire`.
     *
     * This hook is a transport: it must not read, require, default or repair any of
     * those. Before `ApiChangeEntry` was corrected, all four were declared REQUIRED,
     * so this shape did not typecheck — which is a defect that would have surfaced at
     * the first surface to actually mount the feed, and no surface did.
     */
    const onChanges = vi.fn();
    vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({ changes: [PROPOSAL_ENTRY, ENTRY], returned: 2 }),
    );
    renderHook(() => useChangeFeed(EXP_ID, { onChanges }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    expect(onChanges).toHaveBeenCalledTimes(1);
    // Passed through by reference and by value: nothing added, nothing dropped.
    expect(onChanges.mock.calls[0][0]).toEqual([PROPOSAL_ENTRY, ENTRY]);
    const [proposal] = onChanges.mock.calls[0][0];
    expect(proposal).not.toHaveProperty('version');
    expect(proposal).not.toHaveProperty('rev');
    expect(proposal).not.toHaveProperty('generation');
    expect(proposal.state).toBe('open');
  });
});

// =============================================================================
// 4. THE DRAIN BUDGET AND ITS CONTINUATION — every number here was measured
// =============================================================================
//
// WHY THIS SECTION EXISTS, AND WHAT WAS WRONG BEFORE IT DID. The drain budget was
// tested at exactly one point: "20 consecutive drains happen, and a 21st does not."
// Nothing tested what a backlog of one page MORE than the budget cost, and the answer
// was a cliff — measured on this file's own harness before the fix:
//
//   21 pages (1,050 entries at limit 50) -> caught up at mount+13,000 ms
//   22 pages (1,100 entries at limit 50) -> caught up at mount+21,000 ms
//
// Eight full seconds of extra latency for ONE extra entry, at a boundary no scientist
// can see, because past the budget the client dropped to one page per 8 s cadence and
// `drains` never cleared while `has_more` stayed true. A 100-page backlog took
// mount+645,000 ms — ten minutes and forty-five seconds — while `CHANGE_FEED_CADENCE_CLAIM`
// tells the reader an update "appears shortly after it is made".
//
// Every "before" figure quoted in a comment below came from running this same harness
// against the pre-fix hook, and every "after" figure is asserted by the test it sits
// in. `docs/change-feed-client-contract.md` is the same table, with the test names.

/**
 * A DETERMINISTIC PAGING SERVER, in the shape the real one publishes.
 *
 * Cursors are `K-<n>` where `n` is how many entries the caller has already been
 * handed — opaque to the hook, an index here. Every request records the FAKE clock at
 * which it was made, which is what makes "time to drain" a measurement rather than an
 * argument: `vi.useFakeTimers()` fakes `Date` as well as the timers, so `Date.now()`
 * inside this stub reads the scheduler's own timeline.
 *
 * `grow` adds entries AFTER each page is cut, which is how a record under sustained
 * writes is modelled: the cursor keeps moving and `has_more` never goes false.
 */
function feedServer(opts: {
  total: number;
  limit?: number;
  grow?: number;
  /**
   * Report `has_more: false` on every Nth reply EVEN THOUGH entries remain. Not a
   * hypothetical: it is the counterexample an independent review used to measure the
   * published rate bound false, and it models any server that reports a lull it is
   * about to contradict. The client cannot audit the claim, so it clears its budget.
   */
  flapEvery?: number;
}) {
  const pageSize = opts.limit ?? 50;
  let total = opts.total;
  const at: number[] = [];
  const sent: (string | undefined)[] = [];
  let caughtUpAt: number | null = null;
  let replies = 0;

  const impl = async (
    _id: string,
    o: { cursor?: string; limit?: number } = {},
  ): Promise<ApiChangeFeedPage> => {
    const now = Date.now();
    at.push(now);
    sent.push(o.cursor);
    const from = o.cursor === undefined ? 0 : Number(o.cursor.slice(2));
    const size = o.limit ?? pageSize;
    const end = Math.min(from + size, total);
    const changes: ApiChangeEntry[] = Array.from({ length: end - from }, (_, i) => ({
      ...ENTRY,
      entity_id: `E-${from + i}`,
      changed_at_rev: from + i,
    }));
    total += opts.grow ?? 0;
    replies += 1;
    const flapping = opts.flapEvery !== undefined && replies % opts.flapEvery === 0;
    const has_more = end < total && !flapping;
    if (!has_more && caughtUpAt === null) caughtUpAt = now;
    return {
      changes,
      next_cursor: `K-${end}`,
      has_more,
      limit: size,
      returned: changes.length,
      remaining: total - end,
      kinds: ['experiment', 'run'],
    };
  };

  return {
    impl,
    at,
    sent,
    /** New entries arriving after the client has already caught up. */
    addEntries(n: number) {
      total += n;
    },
    get requests() {
      return at.length;
    },
    get caughtUpAt() {
      return caughtUpAt;
    },
    /** Every inter-request interval, in order. */
    get gaps() {
      return at.slice(1).map((t, k) => t - at[k]);
    },
  };
}

describe('changeFeedBacklogDelayMs — the two-tier ladder, as a pure function', () => {
  it('holds the full drain rate for exactly the budget', () => {
    for (let n = 0; n < CHANGE_FEED_MAX_CONSECUTIVE_DRAINS; n += 1) {
      expect(changeFeedBacklogDelayMs(n)).toBe(CHANGE_FEED_DRAIN_DELAY_MS);
    }
  });

  it('doubles from the ceiling and stops at the ordinary cadence', () => {
    const M = CHANGE_FEED_MAX_CONSECUTIVE_DRAINS;
    expect(changeFeedBacklogDelayMs(M)).toBe(500);
    expect(changeFeedBacklogDelayMs(M + 1)).toBe(1000);
    expect(changeFeedBacklogDelayMs(M + 2)).toBe(2000);
    expect(changeFeedBacklogDelayMs(M + 3)).toBe(4000);
    expect(changeFeedBacklogDelayMs(M + 4)).toBe(POLL_INTERVAL_MS);
    // ...and never past it, however long the backlog lives. This is the ceiling the
    // whole rate bound rests on, so it is asserted far out rather than at the knee.
    for (const n of [M + 5, M + 40, M + 5000, Number.MAX_SAFE_INTEGER]) {
      expect(changeFeedBacklogDelayMs(n)).toBe(POLL_INTERVAL_MS);
    }
  });

  it('never returns a delay below the drain delay, at any input', () => {
    // The one-way property: a continuation is always SLOWER than the burst, so no
    // arithmetic slip can turn the escalation into an acceleration.
    for (const n of [0, 1, 19, 20, 21, 25, 100]) {
      expect(changeFeedBacklogDelayMs(n)).toBeGreaterThanOrEqual(CHANGE_FEED_DRAIN_DELAY_MS);
    }
  });
});

describe('useChangeFeed drain boundaries', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5); // jitter factor exactly 1.0
    setVisibility('visible');
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  /** Advance the fake clock inside `act`, so React state settles with it. */
  async function advance(ms: number) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  }

  /** Mount against a `feedServer`, returning the server and the hook result. */
  function mount(server: ReturnType<typeof feedServer>, onChanges = vi.fn()) {
    vi.spyOn(api, 'getChanges').mockImplementation(server.impl as never);
    const hook = renderHook(() => useChangeFeed(EXP_ID, { onChanges }));
    return { hook, onChanges };
  }

  /** The offsets of every request, relative to mount. */
  function offsets(server: ReturnType<typeof feedServer>, mountAt: number): number[] {
    return server.at.map((t) => t - mountAt);
  }

  // --- the small boundaries: no backlog, so no drain at all ------------------

  it('EMPTY FEED: one request per cadence, no callback, and it says it is caught up', async () => {
    const srv = feedServer({ total: 0 });
    const t0 = Date.now();
    const { hook, onChanges } = mount(srv);
    await advance(POLL_INTERVAL_MS * 3);

    expect(offsets(srv, t0)).toEqual([8000, 16000, 24000]);
    // "Nothing changed" is the ABSENCE of a call, never a call with an empty array.
    expect(onChanges).not.toHaveBeenCalled();
    expect(hook.result.current.catchingUp).toBe(false);
    expect(hook.result.current.remaining).toBe(0);
  });

  it('ONE PAGE: 10 of a 50 window is one request, and nothing follows at the drain delay', async () => {
    const srv = feedServer({ total: 10 });
    const t0 = Date.now();
    const { hook, onChanges } = mount(srv);
    await advance(POLL_INTERVAL_MS);
    expect(offsets(srv, t0)).toEqual([8000]);
    expect(onChanges).toHaveBeenCalledTimes(1);
    expect(onChanges.mock.calls[0][0]).toHaveLength(10);
    expect(hook.result.current.catchingUp).toBe(false);
    expect(hook.result.current.remaining).toBe(0);

    await advance(CHANGE_FEED_DRAIN_DELAY_MS * 10);
    expect(srv.requests).toBe(1);
  });

  it('EXACTLY THE PAGE LIMIT: a FULL page with has_more:false does not drain', async () => {
    /*
     * THE ANTI-INFERENCE TEST. A client that guessed at continuation from
     * `changes.length === limit` would fast-follow here, and be wrong: 50 entries in
     * a 50 window with `has_more: false` is a feed that is exactly caught up. The
     * server states continuation; the client never infers it.
     */
    const srv = feedServer({ total: 50, limit: 50 });
    const t0 = Date.now();
    const { hook, onChanges } = mount(srv);
    await advance(POLL_INTERVAL_MS);
    expect(onChanges.mock.calls[0][0]).toHaveLength(50);
    expect(hook.result.current.catchingUp).toBe(false);

    await advance(CHANGE_FEED_DRAIN_DELAY_MS * 10);
    expect(offsets(srv, t0)).toEqual([8000]); // no fast follow-up at all
  });

  it('ONE PAST THE PAGE LIMIT: the 51st entry costs one drain, not one cadence', async () => {
    const srv = feedServer({ total: 51, limit: 50 });
    const t0 = Date.now();
    const { hook, onChanges } = mount(srv);
    await advance(POLL_INTERVAL_MS);
    // Mid-backlog, the hook says so — from the server's own two fields.
    expect(hook.result.current.catchingUp).toBe(true);
    expect(hook.result.current.remaining).toBe(1);

    await advance(CHANGE_FEED_DRAIN_DELAY_MS);
    expect(offsets(srv, t0)).toEqual([8000, 8250]);
    expect(srv.caughtUpAt! - t0).toBe(8250);
    expect(hook.result.current.catchingUp).toBe(false);
    expect(hook.result.current.remaining).toBe(0);
    expect(onChanges.mock.calls.map((c) => c[0].length)).toEqual([50, 1]);
  });

  // --- the budget boundary, which is where the cliff was --------------------

  it('EXACTLY THE BUDGET (21 pages): the whole backlog is one burst, caught up at mount+13,000 ms', async () => {
    const srv = feedServer({ total: 1050, limit: 50 });
    const t0 = Date.now();
    const { hook } = mount(srv);
    await advance(POLL_INTERVAL_MS + CHANGE_FEED_DRAIN_DELAY_MS * 25);

    // One cadence poll plus exactly the 20-drain budget, at 250 ms apart.
    expect(srv.requests).toBe(1 + CHANGE_FEED_MAX_CONSECUTIVE_DRAINS);
    expect(offsets(srv, t0)).toEqual(
      Array.from({ length: 21 }, (_, i) => POLL_INTERVAL_MS + i * CHANGE_FEED_DRAIN_DELAY_MS),
    );
    expect(srv.caughtUpAt! - t0).toBe(13_000);
    expect(hook.result.current.catchingUp).toBe(false);
  });

  it('ONE PAGE PAST THE BUDGET (22 pages): +13,500 ms, where it used to be +21,000 ms', async () => {
    /*
     * THE CLIFF, AND ITS REMOVAL. Measured against the pre-fix hook on this exact
     * harness: 22 pages caught up at mount+21,000 ms — 8,000 ms more than 21 pages,
     * for one more entry. The 22nd page now arrives one CONTINUATION delay after the
     * burst rather than one cadence, and the marginal cost of crossing the ceiling is
     * 500 ms instead of 8,000 ms.
     */
    const srv = feedServer({ total: 1100, limit: 50 });
    const t0 = Date.now();
    const { hook, onChanges } = mount(srv);
    await advance(POLL_INTERVAL_MS + 10_000);

    expect(srv.requests).toBe(22);
    expect(offsets(srv, t0)[20]).toBe(13_000); // the last burst page
    expect(offsets(srv, t0)[21]).toBe(13_500); // the first continuation page
    expect(srv.caughtUpAt! - t0).toBe(13_500);
    expect(srv.caughtUpAt! - t0).toBeLessThan(21_000); // the measured "before"
    expect(hook.result.current.catchingUp).toBe(false);
    expect(hook.result.current.remaining).toBe(0);

    // NO ENTRY IS SKIPPED AT THE CEILING. Every entity arrives exactly once, in feed
    // order, across the burst/continuation boundary — which is the property the whole
    // rate design is only allowed to touch if it preserves.
    const seen = onChanges.mock.calls.flatMap((c) => c[0]).map((e: ApiChangeEntry) => e.entity_id);
    expect(seen).toHaveLength(1100);
    expect(seen).toEqual(Array.from({ length: 1100 }, (_, i) => `E-${i}`));
  });

  it('A LONG BACKLOG (100 pages) drains in bounded time, and every entry arrives once', async () => {
    const srv = feedServer({ total: 5000, limit: 50 });
    const t0 = Date.now();
    const { hook, onChanges } = mount(srv);
    // Advanced to EXACTLY the catch-up instant, so the count is the cost of draining
    // and not that plus however many ordinary cadence polls a longer window allows.
    await advance(620_500);

    // 21 burst pages, then 500 + 1000 + 2000 + 4000, then 75 at the cadence ceiling.
    expect(srv.requests).toBe(100);
    expect(srv.caughtUpAt! - t0).toBe(620_500); // measured "before": 645,000 ms
    expect(hook.result.current.catchingUp).toBe(false);
    const seen = onChanges.mock.calls.flatMap((c) => c[0]).map((e: ApiChangeEntry) => e.entity_id);
    expect(seen).toEqual(Array.from({ length: 5000 }, (_, i) => `E-${i}`));
  }, 20_000);

  // --- sustained writes: the hard rate bound -------------------------------

  it('SUSTAINED has_more never exceeds the documented rate bound', async () => {
    /*
     * The pathological workload: the server hands back a moving cursor and says
     * `has_more: true` forever, so nothing the client does ends the backlog. The
     * claim being pinned is the one in `changeFeedBacklogDelayMs`'s docstring — at
     * most `26 + T / POLL_INTERVAL_MS` requests in any window of T ms — and it is
     * checked at three horizons, because a bound that only holds at one is not a bound.
     */
    const srv = feedServer({ total: 60, limit: 50, grow: 1000 });
    const t0 = Date.now();
    mount(srv);

    for (const T of [60_000, 120_000, 600_000]) {
      await advance(t0 + T - Date.now());
      expect(srv.requests).toBeLessThanOrEqual(26 + T / POLL_INTERVAL_MS);
    }
    // ...and it is not vacuous: the client really is still paging, not stalled.
    expect(srv.requests).toBeGreaterThan(26);
    // The steady state IS the ordinary cadence — the last stretch adds one request
    // per POLL_INTERVAL_MS and no more, which is the promise the escalation keeps.
    const tail = srv.at.filter((t) => t - t0 > 200_000);
    const gaps = tail.slice(1).map((t, i) => t - tail[i]);
    expect(new Set(gaps)).toEqual(new Set([POLL_INTERVAL_MS]));
  }, 20_000);

  it('a FLAPPING server gets a fresh burst per cycle — the sustained bound does NOT cover it', async () => {
    /*
     * THE COUNTEREXAMPLE TO THE PUBLISHED BOUND, MEASURED RATHER THAN ARGUED, and
     * this test exists because an independent review found the branch publishing
     * `26 + T / POLL_INTERVAL_MS` as "the hard rate bound" with no premise attached.
     * The premise is a server answering `has_more: true` CONTINUOUSLY. A server that
     * reports `has_more: false` every 21st reply while entries still remain clears
     * `drains` each time and is handed a fresh 20-page burst every cycle.
     *
     * THE CLIENT IS NOT WRONG TO DO THAT, which is why nothing here is "fixed": the
     * reset rule is "the server said it had finished", and a client cannot audit that
     * claim. Weakening it was tried and measured WORSE. What was wrong was publishing
     * a bound without its premise, and the remedy is the honest cycle bound below.
     */
    const CYCLE = POLL_INTERVAL_MS + CHANGE_FEED_MAX_CONSECUTIVE_DRAINS * CHANGE_FEED_DRAIN_DELAY_MS;
    expect(CYCLE).toBe(13_000);
    const srv = feedServer({ total: 10_000_000, limit: 50, flapEvery: 21 });
    const t0 = Date.now();
    mount(srv);

    await advance(60_000 - (Date.now() - t0));
    // THE MEASURED NUMBER, asserted exactly. The sustained bound would have said 33.
    expect(srv.requests).toBe(85);

    await advance(600_000 - (Date.now() - t0));
    expect(srv.requests).toBe(966);

    // THE BOUND THAT DOES HOLD against any server behaviour, because the reset is the
    // server's word: at most one cadence gap plus a whole burst per cycle.
    const perCycle = 1 + CHANGE_FEED_MAX_CONSECUTIVE_DRAINS;
    expect(966).toBeLessThanOrEqual(perCycle * (Math.ceil(600_000 / CYCLE) + 1));
    expect(85).toBeLessThanOrEqual(perCycle * (Math.ceil(60_000 / CYCLE) + 1));
    // ~1.6 req/s — the same figure the rejected budget-refill design was measured at.
    // Recorded because the ceiling is structural, not because it is comfortable.
    expect(966 / 600).toBeCloseTo(1.61, 1);

    // And it never goes faster than the drain delay, at any point in any cycle.
    expect(Math.min(...srv.gaps)).toBe(CHANGE_FEED_DRAIN_DELAY_MS);
  }, 30_000);

  it('a SECOND backlog, after the first one finished, drains at the FULL burst rate', async () => {
    /*
     * THE COUNTER IS CLEARED BY `has_more: false`, AND NOTHING PINNED THAT. The mutant
     * `drains = drains + 1` — never reset at all — passed all 53 tests of the previous
     * revision, while this file's own prose promised "a later backlog gets a full
     * budget of its own". Under that mutant the first backlog leaves the counter at 21,
     * so the second one starts in the CONTINUATION tier at 1,000 ms instead of 250 ms.
     *
     * The first backlog is deliberately 21 pages rather than two: a short first
     * backlog leaves the counter below the ceiling, where `changeFeedBacklogDelayMs`
     * returns the same 250 ms either way and the mutant survives.
     */
    const srv = feedServer({ total: 1050, limit: 50 }); // 21 pages
    const t0 = Date.now();
    mount(srv);
    await advance(POLL_INTERVAL_MS + CHANGE_FEED_DRAIN_DELAY_MS * 20);
    expect(srv.requests).toBe(21);
    expect(srv.caughtUpAt! - t0).toBe(13_000); // the counter is now cleared

    srv.addEntries(1000); // a new backlog arrives while the client is idle
    await advance(POLL_INTERVAL_MS);
    expect(offsets(srv, t0)[21]).toBe(21_000); // found at the ordinary cadence

    await advance(CHANGE_FEED_DRAIN_DELAY_MS * 3);
    // 250 ms apart — the burst rate, not the 1,000 ms the continuation tier would give.
    expect(offsets(srv, t0).slice(21, 25)).toEqual([21_000, 21_250, 21_500, 21_750]);
  });

  // --- the feed floor: a refused cursor -------------------------------------

  it('RESYNCS FROM THE FEED FLOOR after a 422, instead of resending the refused cursor forever', async () => {
    /*
     * MEASURED DEFECT, NOT A HYPOTHETICAL. `422 malformed_cursor` is the server's
     * published refusal of a cursor that is the wrong version, the wrong feed or
     * corrupt, and its one documented remedy is "drop the cursor and resync". The
     * hook did neither: it counted a failure, backed off, and sent the SAME refused
     * cursor on every later poll — a feed permanently dark that no retry could clear.
     */
    const refusal = new ApiError('refused', { status: 422, reason: 'malformed_cursor' });
    let refuse = true;
    const spy = vi.spyOn(api, 'getChanges').mockImplementation(async (_id, o = {}) => {
      if (refuse && o.cursor !== undefined) throw refusal;
      return page({ next_cursor: 'FRESH-1', changes: [ENTRY], returned: 1, remaining: 0 });
    });
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await advance(POLL_INTERVAL_MS); // 1st poll: no cursor, succeeds, cursor FRESH-1
    expect(spy.mock.calls[0][1]).toEqual({});
    expect(result.current.cursor).toBe('FRESH-1');

    await advance(POLL_INTERVAL_MS); // 2nd poll: carries FRESH-1, refused
    expect(spy.mock.calls[1][1]).toEqual({ cursor: 'FRESH-1' });
    // The cursor is DROPPED, and `remaining` with it: the old figure described a
    // position this client no longer holds, and `null` says "unknown", not "zero".
    expect(result.current.cursor).toBeUndefined();
    expect(result.current.remaining).toBeNull();

    // The recovery is NOT delayed by a backoff step — the refusal has already been
    // fixed, so the next poll comes at the ordinary cadence and carries no cursor.
    await advance(POLL_INTERVAL_MS);
    expect(spy.mock.calls[2][1]).toEqual({});
    expect(result.current.cursor).toBe('FRESH-1');
    expect(result.current.degraded).toBe(false);

    refuse = false;
    await advance(POLL_INTERVAL_MS * 2);
    expect(result.current.degraded).toBe(false);
  });

  it('a 422 on a request that carried NO cursor is an ordinary failure, and still degrades', async () => {
    /*
     * The loop guard, stated as a test. Only a request that CARRIED a cursor may drop
     * one, so a 422 that a resync cannot fix (a malformed `limit`, say — FastAPI
     * answers 422 for that too and this client cannot tell them apart) falls through
     * to the ordinary backoff ladder rather than retrying at the cadence forever.
     */
    const spy = vi
      .spyOn(api, 'getChanges')
      .mockRejectedValue(new ApiError('refused', { status: 422 }));
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await advance(POLL_INTERVAL_MS);
    expect(spy).toHaveBeenCalledTimes(1);
    // Backed off: nothing at the plain cadence, the 2nd attempt is at 2x.
    await advance(POLL_INTERVAL_MS);
    expect(spy).toHaveBeenCalledTimes(1);
    await advance(POLL_INTERVAL_MS);
    expect(spy).toHaveBeenCalledTimes(2);
    await advance(POLL_INTERVAL_MS * 4);
    expect(spy).toHaveBeenCalledTimes(DEGRADED_THRESHOLD);
    expect(result.current.degraded).toBe(true);
  });

  it('a 404 does NOT drop the cursor: only the refusal whose remedy is a resync does', async () => {
    let fail = false;
    const spy = vi.spyOn(api, 'getChanges').mockImplementation(async () => {
      if (fail) throw new ApiError('gone', { status: 404, reason: 'experiment_not_found' });
      return page({ next_cursor: 'KEEP-1' });
    });
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));
    await advance(POLL_INTERVAL_MS);
    expect(result.current.cursor).toBe('KEEP-1');

    fail = true;
    await advance(POLL_INTERVAL_MS);
    expect(spy).toHaveBeenCalledTimes(2);
    // A missing record is not a bad cursor. Replaying the whole feed on the next poll
    // would turn one server-side condition into a full re-delivery of every entry.
    expect(result.current.cursor).toBe('KEEP-1');
  });

  // --- errors, cancellation and visibility, all MID-DRAIN -------------------

  it('a retryable failure MID-DRAIN forfeits the budget, backs off, and loses no entry', async () => {
    const srv = feedServer({ total: 200, limit: 50 }); // 4 pages
    const t0 = Date.now();
    let failOnce = false;
    const onChanges = vi.fn();
    vi.spyOn(api, 'getChanges').mockImplementation(async (id, o = {}) => {
      if (failOnce) {
        failOnce = false;
        throw new Error('transport');
      }
      return srv.impl(id as string, o);
    });
    renderHook(() => useChangeFeed(EXP_ID, { onChanges }));

    await advance(POLL_INTERVAL_MS); // page 1
    await advance(CHANGE_FEED_DRAIN_DELAY_MS); // page 2
    expect(srv.requests).toBe(2);

    failOnce = true;
    await advance(CHANGE_FEED_DRAIN_DELAY_MS); // the drain attempt fails, at +8,500
    expect(srv.requests).toBe(2);
    // Backing off and fast-following are contradictory instructions: the budget is
    // forfeited, so the retry comes at 2x the cadence (+16,000, i.e. at +24,500) and
    // not at the drain delay. Advanced to one millisecond short of it first, so the
    // assertion is that nothing came EARLY rather than merely that something came.
    await advance(POLL_INTERVAL_MS * 2 - 1);
    expect(srv.requests).toBe(2);
    await advance(1);
    expect(srv.requests).toBe(3);
    expect(offsets(srv, t0)[2]).toBe(24_500);

    // NOTHING WAS LOST: the retry resumed from the cursor page 2 issued, and the
    // remaining pages arrive at the full drain rate again.
    expect(srv.sent[2]).toBe('K-100');
    await advance(CHANGE_FEED_DRAIN_DELAY_MS * 2);
    const seen = onChanges.mock.calls.flatMap((c) => c[0]).map((e: ApiChangeEntry) => e.entity_id);
    expect(seen).toEqual(Array.from({ length: 200 }, (_, i) => `E-${i}`));
  });

  it('a THROWING consumer does not advance the cursor past the page it could not process', async () => {
    /*
     * THE NO-LOSS ORDERING, pinned. `onChanges` runs BEFORE the cursor is adopted, so
     * a consumer that throws leaves the position untouched and the same page is asked
     * for again. The other order — which is what this hook used to do — advanced past
     * a page nobody had processed and the poll still looked successful.
     */
    const srv = feedServer({ total: 10 });
    let boom = true;
    // Typed parameter so `mock.calls[n][0]` is the entry array rather than `never`.
    const onChanges = vi.fn((_entries: ApiChangeEntry[]) => {
      if (boom) throw new Error('consumer exploded');
    });
    vi.spyOn(api, 'getChanges').mockImplementation(srv.impl as never);
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges }));

    await advance(POLL_INTERVAL_MS);
    expect(srv.requests).toBe(1);
    expect(result.current.cursor).toBeUndefined(); // NOT advanced to K-10

    boom = false;
    await advance(POLL_INTERVAL_MS * 4);
    // The retry carried no cursor, so the page was re-delivered rather than skipped.
    expect(srv.sent[1]).toBeUndefined();
    expect(result.current.cursor).toBe('K-10');
    expect(onChanges.mock.calls[1][0]).toHaveLength(10);
  });

  it('UNMOUNTING MID-DRAIN aborts the request in flight, leaves no timer, and updates no state', async () => {
    const srv = feedServer({ total: 1000, limit: 50 });
    const aborted: boolean[] = [];
    // The LAST request never settles, so there is genuinely one in flight at unmount.
    // Written this way because the first version of this test unmounted between polls
    // and asserted an abort that could not have happened — it failed, which is the
    // only reason the gap was visible at all.
    let hang = false;
    vi.spyOn(api, 'getChanges').mockImplementation((id, o = {}, signal) => {
      signal?.addEventListener('abort', () => aborted.push(true));
      if (hang) return new Promise<ApiChangeFeedPage>((res) => (release = res));
      return srv.impl(id as string, o);
    });
    const onChanges = vi.fn();
    let release: (p: ApiChangeFeedPage) => void = () => {};
    const { unmount } = renderHook(() => useChangeFeed(EXP_ID, { onChanges }));
    await advance(POLL_INTERVAL_MS + CHANGE_FEED_DRAIN_DELAY_MS * 2);
    const during = srv.requests;
    expect(during).toBe(3); // genuinely mid-drain
    hang = true;
    await advance(CHANGE_FEED_DRAIN_DELAY_MS); // a 4th request, which never settles

    unmount();
    // Exactly one abort: each poll owns its own controller and only the one still in
    // flight is torn down, so this also pins that a settled poll's controller is
    // released rather than accumulated.
    expect(aborted).toEqual([true]);
    expect(vi.getTimerCount()).toBe(0); // no timer left behind

    await advance(POLL_INTERVAL_MS * 5);
    expect(srv.requests).toBe(during);

    // NO WORK HAPPENS WHEN THE ABORTED REQUEST LATER SETTLES, and this assertion
    // replaces one that could not fail. The previous version spied on `console.error`
    // and asserted no "update on an unmounted component" warning — but React 18.3.1
    // REMOVED that warning entirely, so the spy was asserting the absence of something
    // this version of React never emits. It was vacuous, and its comment said the
    // opposite. `onChanges` is an OBSERVABLE post-unmount side effect: the `.then`
    // guard is the same `cancelled || ac.signal.aborted` check that gates every
    // `setState` in the chain, so a callback that does not fire is evidence the guard
    // held, where a missing console warning was evidence of nothing.
    const beforeRelease = onChanges.mock.calls.length;
    await act(async () => {
      release(page({ changes: [ENTRY], returned: 1, next_cursor: 'LATE', remaining: 0 }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(onChanges.mock.calls.length).toBe(beforeRelease);
    expect(srv.requests).toBe(during); // and it did not restart the chain either
    expect(vi.getTimerCount()).toBe(0);
  });

  it('UNMOUNTING BETWEEN POLLS leaves no pending timer', async () => {
    /*
     * SEPARATE FROM THE TEST ABOVE, AND THE REASON IS A SURVIVING MUTANT. That one
     * unmounts with a request IN FLIGHT — at which moment no timer is pending anyway,
     * because the chain schedules the next poll only in `.finally`. So its
     * `getTimerCount() === 0` was vacuously true and a cleanup that never called
     * `clearTimeout` passed it. This one unmounts while a timer really is armed.
     */
    const srv = feedServer({ total: 0 });
    const { hook } = mount(srv);
    await advance(POLL_INTERVAL_MS);
    expect(srv.requests).toBe(1);
    expect(vi.getTimerCount()).toBe(1); // the next cadence poll is armed

    hook.unmount();
    expect(vi.getTimerCount()).toBe(0);
    await advance(POLL_INTERVAL_MS * 5);
    expect(srv.requests).toBe(1);
  });

  it('a poll that SETTLES AFTER the tab is hidden arms no timer', async () => {
    /*
     * THE ONLY PATH THAT EXERCISES THE VISIBILITY GATE INSIDE `schedule`, and it took
     * a surviving mutant to find that out. Hiding the tab between polls is handled by
     * the visibility listener's `clearTimer`, and a timer that fires while hidden is
     * handled by `runPoll`'s own guard — so removing the gate from `schedule` changed
     * nothing either test could see. This is the remaining case: a request already in
     * flight when the tab is hidden, whose `.finally` runs afterwards and would arm a
     * timer on a paused poller.
     */
    let release: (p: ApiChangeFeedPage) => void = () => {};
    vi.spyOn(api, 'getChanges').mockImplementation(
      () => new Promise<ApiChangeFeedPage>((res) => (release = res)),
    );
    renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await advance(POLL_INTERVAL_MS);
    expect(vi.getTimerCount()).toBe(0); // in flight: the chain arms nothing until it settles

    await act(async () => {
      setVisibility('hidden');
    });
    await act(async () => {
      release(page({ next_cursor: 'LATE' }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(vi.getTimerCount()).toBe(0);
  });

  it('HIDING THE TAB MID-DRAIN stops the backlog, and showing it resumes from the same cursor', async () => {
    const srv = feedServer({ total: 1000, limit: 50 });
    mount(srv);
    await advance(POLL_INTERVAL_MS + CHANGE_FEED_DRAIN_DELAY_MS * 2);
    const during = srv.requests;
    expect(during).toBe(3);

    await act(async () => {
      setVisibility('hidden');
      await vi.advanceTimersByTimeAsync(CHANGE_FEED_DRAIN_DELAY_MS * 20);
    });
    // A backlog is not a reason to keep polling a tab nobody is looking at.
    expect(srv.requests).toBe(during);
    // AND IT PARKS RATHER THAN SPINS. The request count alone cannot tell those apart
    // — `runPoll` bails on a hidden tab too, so a poller that kept scheduling timers
    // that immediately return would look identical here. This is the assertion that
    // separates them, and it was added because the mutant that removes the visibility
    // gate from `schedule` survived without it.
    expect(vi.getTimerCount()).toBe(0);

    await act(async () => {
      setVisibility('visible');
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(srv.requests).toBe(during + 1);
    // Resumed from where it stopped — the pause costs time, never entries.
    expect(srv.sent[during]).toBe(`K-${during * 50}`);
  });

  it('reports catchingUp while the stuck-cursor guard is refusing to fast-follow', async () => {
    // The server insists there is more and hands back the position already held. The
    // client is right not to hammer it, and would be WRONG to let a surface render
    // "up to date": `has_more` is the server's answer and it says otherwise.
    vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({ has_more: true, next_cursor: 'STUCK', remaining: 7 }),
    );
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));
    await advance(POLL_INTERVAL_MS * 3);
    expect(result.current.catchingUp).toBe(true);
    expect(result.current.remaining).toBe(7);
  });

  it('reports remaining as null — never zero — when the server did not send a number', async () => {
    vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({ remaining: undefined as unknown as number }),
    );
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));
    await advance(POLL_INTERVAL_MS);
    // `null` is "this client does not know". Defaulting it to 0 would publish a
    // caught-up claim the deployment never made.
    expect(result.current.remaining).toBeNull();
  });

  it('keeps the last known catchingUp across a failed poll rather than inventing a verdict', async () => {
    let fail = false;
    vi.spyOn(api, 'getChanges').mockImplementation(async () => {
      if (fail) throw new Error('down');
      return page({ has_more: true, next_cursor: `M-${Math.random()}`, remaining: 400 });
    });
    const { result } = renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));
    await advance(POLL_INTERVAL_MS);
    expect(result.current.catchingUp).toBe(true);

    fail = true;
    await advance(POLL_INTERVAL_MS * 8);
    // A failure says nothing about whether the backlog cleared, and clearing the flag
    // would let a surface claim to be current on the strength of an error.
    expect(result.current.catchingUp).toBe(true);
    expect(result.current.degraded).toBe(true);
  });

  it('starts a NEW record with no cursor, no catch-up claim and no remaining', async () => {
    const srv = feedServer({ total: 1000, limit: 50 });
    vi.spyOn(api, 'getChanges').mockImplementation(srv.impl as never);
    const { result, rerender } = renderHook(({ id }) => useChangeFeed(id, { onChanges: vi.fn() }), {
      initialProps: { id: EXP_ID },
    });
    await advance(POLL_INTERVAL_MS + CHANGE_FEED_DRAIN_DELAY_MS);
    expect(result.current.catchingUp).toBe(true);
    expect(result.current.remaining).toBeGreaterThan(0);

    rerender({ id: '01OTHEREXPERIMENT000000000' });
    // A fresh feed is one nothing is known about — not one known to be caught up, and
    // certainly not one carrying the previous record's backlog figure.
    expect(result.current.catchingUp).toBe(false);
    expect(result.current.remaining).toBeNull();
    expect(result.current.cursor).toBeUndefined();
  });
});

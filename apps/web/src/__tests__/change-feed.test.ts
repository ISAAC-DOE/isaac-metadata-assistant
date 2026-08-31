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
import type { ApiChangeFeedPage } from '../lib/types';
import {
  useChangeFeed,
  CHANGE_FEED_CADENCE_CLAIM,
  CHANGE_FEED_LIMITS_CLAIM,
  CHANGE_FEED_DRAIN_DELAY_MS,
  CHANGE_FEED_MAX_CONSECUTIVE_DRAINS,
  POLL_INTERVAL_MS,
  POLL_MAX_BACKOFF_MS,
  DEGRADED_THRESHOLD,
} from '../lib/useChangeFeed';
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

const ENTRY = {
  kind: 'run',
  entity_id: '01RUN0000000000000000000AA',
  version: 'abcdef0123456789.4',
  rev: 4,
  generation: 'abcdef0123456789',
  updated_utc: '2026-08-30T12:00:00Z',
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

  it('caps consecutive drains and falls back to the ordinary cadence, losing nothing', async () => {
    let n = 0;
    const spy = vi
      .spyOn(api, 'getChanges')
      .mockImplementation(async () =>
        page({ changes: [ENTRY], has_more: true, next_cursor: `C-${++n}` }),
      );
    renderHook(() => useChangeFeed(EXP_ID, { onChanges: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
      await vi.advanceTimersByTimeAsync(
        CHANGE_FEED_DRAIN_DELAY_MS * (CHANGE_FEED_MAX_CONSECUTIVE_DRAINS + 4),
      );
    });
    // One cadence poll plus exactly the budget — the burst is bounded.
    const capped = spy.mock.calls.length;
    expect(capped).toBe(1 + CHANGE_FEED_MAX_CONSECUTIVE_DRAINS);

    // The budget really is spent: more drain delay buys nothing.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CHANGE_FEED_DRAIN_DELAY_MS * 6);
    });
    expect(spy.mock.calls.length).toBe(capped);

    // FALLS BACK rather than stops: the next cadence tick resumes progress with a
    // fresh budget, so a genuine backlog longer than the cap still drains — more
    // slowly, which is the whole intent of a cap aimed at a server defect. The
    // assertion is "progress resumed", not an exact count: how many drains fit inside
    // one advanced cadence window is timer bookkeeping, and pinning it would make
    // this test about `vi.advanceTimersByTimeAsync` rather than about the cap.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy.mock.calls.length).toBeGreaterThan(capped);
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
});

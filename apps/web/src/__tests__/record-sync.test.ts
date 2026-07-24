import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { api, ApiError } from '../lib/api';
import type { ApiExperimentDetail } from '../lib/types';
import {
  useRecordSync,
  POLL_INTERVAL_MS,
  POLL_MAX_BACKOFF_MS,
} from '../lib/useRecordSync';
import { EXP_ID, experimentDetailChanged, stubFetchRoutes } from '../test/apiFixtures';

// The changed detail, typed as the real detail shape for the mocked resolver.
const CHANGED = experimentDetailChanged as unknown as ApiExperimentDetail;
type SyncResult = Awaited<ReturnType<typeof api.checkRecordVersion>>;

// A hand-controlled promise so a test can hold a poll "in flight" and resolve /
// reject it on demand under fake timers.
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// Set document.hidden (jsdom) and fire the visibilitychange event the hook listens for.
function setHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event('visibilitychange'));
}

// ---------------------------------------------------------------------------
// api.checkRecordVersion — the client half of the conditional GET (real fetch
// path via the stub, so 304-vs-200-vs-error handling is exercised end to end).
// ---------------------------------------------------------------------------

describe('api.checkRecordVersion — conditional GET', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends If-None-Match: "<version>" and returns {changed:false} on 304', async () => {
    const calls = stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}`]: { status: 304, body: undefined, etag: '"1.0"' },
    });
    const res = await api.checkRecordVersion(EXP_ID, '1.0');
    expect(res).toEqual({ changed: false });
    expect(calls).toContain(`GET /api/experiments/${EXP_ID}`);
    const init = (globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } })
      .mock.calls[0][1];
    expect((init.headers as Record<string, string>)['If-None-Match']).toBe('"1.0"');
  });

  it('returns {changed:true, detail} on a 200 with the fresh body', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}`]: { status: 200, body: experimentDetailChanged, etag: '"2.0"' },
    });
    const res = await api.checkRecordVersion(EXP_ID, '1.0');
    expect(res.changed).toBe(true);
    expect(res.detail?.version).toBe('2.0');
    expect(res.detail?.rev).toBe(9);
  });

  it('throws an ApiError carrying the status on any other status', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}`]: { status: 500, body: { error: 'boom' } },
    });
    await expect(api.checkRecordVersion(EXP_ID, '1.0')).rejects.toMatchObject({
      name: 'ApiError',
      status: 500,
    });
  });

  it('forwards the AbortSignal to fetch', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}`]: { status: 304, body: undefined },
    });
    const controller = new AbortController();
    await api.checkRecordVersion(EXP_ID, '1.0', controller.signal);
    const init = (globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } })
      .mock.calls[0][1];
    expect(init.signal).toBe(controller.signal);
  });
});

// ---------------------------------------------------------------------------
// useRecordSync — scheduling / non-overlap / abort / backoff / visibility.
// Spy on checkRecordVersion so each poll's outcome is controlled precisely.
// ---------------------------------------------------------------------------

describe('useRecordSync', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Pin jitter to 0 (factor 1.0) so polls land exactly on POLL_INTERVAL_MS.
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    setHidden(false);
  });
  afterEach(() => {
    vi.clearAllTimers(); // drop pending polls without executing them (no post-test state updates)
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('does not poll when disabled or when id/version is undefined', async () => {
    const spy = vi.spyOn(api, 'checkRecordVersion');
    const onChanged = vi.fn();

    renderHook(() => useRecordSync(EXP_ID, '1.0', { onChanged, enabled: false }));
    renderHook(() => useRecordSync(undefined, '1.0', { onChanged }));
    renderHook(() => useRecordSync(EXP_ID, undefined, { onChanged }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });
    expect(spy).not.toHaveBeenCalled();
  });

  it('starts one poll per interval for an active record and stops on unmount', async () => {
    const spy = vi.spyOn(api, 'checkRecordVersion').mockResolvedValue({ changed: false });
    const { unmount } = renderHook(() => useRecordSync(EXP_ID, '1.0', { onChanged: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(2);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });
    expect(spy).toHaveBeenCalledTimes(2); // no polls after unmount
  });

  it('never overlaps: a slow in-flight poll blocks the next (incl. checkNow)', async () => {
    const spy = vi.spyOn(api, 'checkRecordVersion').mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useRecordSync(EXP_ID, '1.0', { onChanged: vi.fn() }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1); // in flight, never resolves

    // No reschedule happens while in flight, and checkNow can't start a 2nd.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 4);
      result.current.checkNow();
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('a 304 tick does NOT call onChanged; a 200 tick calls it once with the detail', async () => {
    const onChanged = vi.fn();
    const spy = vi
      .spyOn(api, 'checkRecordVersion')
      .mockResolvedValueOnce({ changed: false })
      .mockResolvedValueOnce({ changed: true, detail: CHANGED });
    renderHook(() => useRecordSync(EXP_ID, '1.0', { onChanged }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(onChanged).not.toHaveBeenCalled(); // 304 → nothing

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(onChanged).toHaveBeenCalledWith(CHANGED);
  });

  it('aborts the in-flight poll on a version change and never fires a stale onChanged', async () => {
    const onChanged = vi.fn();
    const d = deferred<SyncResult>();
    let capturedSignal: AbortSignal | undefined;
    vi.spyOn(api, 'checkRecordVersion').mockImplementation((_id, _v, signal) => {
      capturedSignal = signal;
      return d.promise;
    });

    const { rerender } = renderHook(({ v }) => useRecordSync(EXP_ID, v, { onChanged }), {
      initialProps: { v: '1.0' },
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(capturedSignal?.aborted).toBe(false);

    // Version changes → old poller torn down (aborted), fresh one starts.
    rerender({ v: '2.0' });
    expect(capturedSignal?.aborted).toBe(true);

    // The superseded poll resolves late with a change — it must be ignored.
    await act(async () => {
      d.resolve({ changed: true, detail: CHANGED });
      await Promise.resolve();
    });
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('survives an in-place version adoption while a poll is in flight (poller stays alive)', async () => {
    // Regression guard for the shared-ref teardown bug: when version changes IN
    // PLACE mid-poll, the old aborted poll's late .finally must NOT clobber the
    // new poller's timer. Pre-fix this left NO timer scheduled and polling died
    // silently (no failures → degraded never flips → stale shown as current).
    const held = deferred<SyncResult>();
    const versions: (string | undefined)[] = [];
    let call = 0;
    vi.spyOn(api, 'checkRecordVersion').mockImplementation((_id, v) => {
      versions.push(v);
      call += 1;
      return call === 1 ? held.promise : Promise.resolve({ changed: false });
    });

    const { rerender } = renderHook(({ v }) => useRecordSync(EXP_ID, v, { onChanged: vi.fn() }), {
      initialProps: { v: '1.0' },
    });

    // first poll for v1.0 fires and stays in flight
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(versions).toEqual(['1.0']);

    // adopt a new version IN PLACE (same record, still enabled) mid-flight
    rerender({ v: '2.0' });

    // the old (now-aborted) poll resolves late — its finally must not kill the new timer
    await act(async () => {
      held.resolve({ changed: false });
      await Promise.resolve();
    });

    // the NEW poller is still alive: it polls again, for v2.0
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(call).toBeGreaterThanOrEqual(2);
    expect(versions).toContain('2.0');
  });

  it('a stale response for a superseded version cannot call onChanged for the new one', async () => {
    const onChanged = vi.fn();
    const first = deferred<SyncResult>();
    let call = 0;
    vi.spyOn(api, 'checkRecordVersion').mockImplementation(() => {
      call += 1;
      // First (version 1.0) poll is held; later polls resolve 304 harmlessly.
      return call === 1 ? first.promise : Promise.resolve({ changed: false });
    });

    const { rerender } = renderHook(({ v }) => useRecordSync(EXP_ID, v, { onChanged }), {
      initialProps: { v: '1.0' },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    rerender({ v: '2.0' }); // now the current version is 2.0

    await act(async () => {
      // The held v1.0 poll resolves "changed" — stale guard must drop it.
      first.resolve({ changed: true, detail: CHANGED });
      await Promise.resolve();
    });
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('backs off exponentially (bounded) after failures and resets on success', async () => {
    const spy = vi
      .spyOn(api, 'checkRecordVersion')
      .mockRejectedValue(new ApiError('down', { unreachable: true }));
    const { result } = renderHook(() => useRecordSync(EXP_ID, '1.0', { onChanged: vi.fn() }));

    // fail #1 at 8s, fail #2 at +16s (24s), fail #3 at +32s (56s) → degraded.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(result.current.degraded).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2);
    });
    expect(spy).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 4);
    });
    expect(spy).toHaveBeenCalledTimes(3);
    expect(result.current.degraded).toBe(true);

    // A success clears degraded and resets the ladder back to the base interval.
    spy.mockResolvedValue({ changed: false });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MAX_BACKOFF_MS); // next poll was at +60s
    });
    expect(result.current.degraded).toBe(false);
  });

  it('an abort is not a user-facing failure and does not flip degraded', async () => {
    const d = deferred<SyncResult>();
    let capturedSignal: AbortSignal | undefined;
    vi.spyOn(api, 'checkRecordVersion').mockImplementation((_id, _v, signal) => {
      capturedSignal = signal;
      return d.promise;
    });
    const { result, rerender } = renderHook(({ v }) => useRecordSync(EXP_ID, v, { onChanged: vi.fn() }), {
      initialProps: { v: '1.0' },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    rerender({ v: '2.0' }); // aborts the in-flight poll
    await act(async () => {
      d.reject(new ApiError('aborted / unreachable', { unreachable: true }));
      await Promise.resolve();
    });
    expect(capturedSignal?.aborted).toBe(true);
    expect(result.current.degraded).toBe(false); // abort never counts as failure
  });

  it('pauses while hidden and does an immediate check on visibility-regain', async () => {
    const spy = vi.spyOn(api, 'checkRecordVersion').mockResolvedValue({ changed: false });
    renderHook(() => useRecordSync(EXP_ID, '1.0', { onChanged: vi.fn() }));

    // Hide before the first poll fires → no polling while hidden.
    await act(async () => {
      setHidden(true);
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });
    expect(spy).not.toHaveBeenCalled();

    // Becoming visible triggers an immediate check.
    await act(async () => {
      setHidden(false);
      await Promise.resolve();
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

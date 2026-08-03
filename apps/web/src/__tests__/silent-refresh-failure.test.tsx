/*
 * R1b · a refresh that fails must not fail invisibly.
 *
 * WHAT SHIPPED, on three surfaces, from two separate pieces of code:
 *
 *  (a) `lib/useFetch.ts`'s `reloadSilent` caught every rejection and did
 *      NOTHING with it — "keep the current data; a failed silent refresh must not
 *      blank/error". Not blanking is right. Saying nothing is not. Used by
 *      `screens/RecordWorkbench.tsx` (poll signal, and the post-write refetch
 *      after a confirmed assistant proposal) and `screens/EvidenceExplorer.tsx`,
 *      where a failed POST-WRITE refetch leaves the PRE-write draft on screen
 *      with no indication that what is shown is stale.
 *
 *  (b) `screens/ExportReadiness.tsx`'s own `runFetch(showLoading)` set the error
 *      state only `if (showLoading)`. `Re-Validate` on the PASS card calls
 *      `runFetch(false)`, so on a backend outage the PASS card simply stayed put
 *      and the reader believed they had just re-validated a passing record. That
 *      is the worst instance: a trust control that silently does nothing.
 *
 * THE FIX'S SHAPE, which these tests pin rather than the implementation: a failed
 * background refresh raises an OBSERVABLE, non-blocking notice that says the data
 * on screen is the last loaded state, and offers a retry. It must NOT flip the
 * screen to a loading blank — that is the property `showLoading: false` existed
 * for, and regressing it would trade one defect for another.
 *
 * WHAT THIS DOES NOT COVER. It does not assert the notice is visually prominent,
 * only that it is in the accessibility tree with an assertive role and real text.
 * Whether a reader NOTICES it is a human-QA question.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, act, fireEvent, renderHook, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { LiveSyncNote } from '../components/LiveSyncNote';
import { useFetch } from '../lib/useFetch';
import { ApiError } from '../lib/api';
import {
  auditExported,
  bundleRoutes,
  evidenceBundleRoutes,
  exportReadyRoutes,
  exportSuccess,
  liveDetailRoute,
  stubFetchRoutes,
} from '../test/apiFixtures';

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

/** Advance fake timers by `ms` (default 0 → just flush pending microtasks). */
async function settle(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

// --- 1. the mechanism: useFetch reports a failed silent reload ----------------

describe('R1b · useFetch surfaces a failed silent reload instead of swallowing it', () => {
  it('keeps the data, does not blank to loading, and reports the failure', async () => {
    let attempt = 0;
    const fetcher = vi.fn(async () => {
      attempt += 1;
      if (attempt === 1) return 'first';
      throw new ApiError('backend unreachable');
    });

    const { result } = renderHook(() => useFetch(fetcher, ['k']));
    await waitFor(() => expect(result.current.status).toBe('data'));
    expect(result.current.refreshFailed).toBe(false);

    await act(async () => {
      result.current.reloadSilent();
    });

    // The three properties together are the whole contract.
    expect(result.current.status).toBe('data'); // never blanked
    expect(result.current.status === 'data' && result.current.data).toBe('first'); // data kept
    expect(result.current.refreshFailed).toBe(true); // and NOT swallowed
  });

  it('clears the flag once a later silent reload succeeds', async () => {
    let attempt = 0;
    const fetcher = vi.fn(async () => {
      attempt += 1;
      if (attempt === 2) throw new ApiError('transient');
      return `load-${attempt}`;
    });

    const { result } = renderHook(() => useFetch(fetcher, ['k']));
    await waitFor(() => expect(result.current.status).toBe('data'));

    await act(async () => {
      result.current.reloadSilent();
    });
    expect(result.current.refreshFailed).toBe(true);

    await act(async () => {
      result.current.reloadSilent();
    });
    expect(result.current.refreshFailed).toBe(false);
    expect(result.current.status === 'data' && result.current.data).toBe('load-3');
  });

  it('an explicit reload clears the flag as it re-enters the loading state', async () => {
    let attempt = 0;
    const fetcher = vi.fn(async () => {
      attempt += 1;
      if (attempt === 2) throw new ApiError('transient');
      return `load-${attempt}`;
    });

    const { result } = renderHook(() => useFetch(fetcher, ['k']));
    await waitFor(() => expect(result.current.status).toBe('data'));
    await act(async () => {
      result.current.reloadSilent();
    });
    expect(result.current.refreshFailed).toBe(true);

    await act(async () => {
      result.current.reload();
    });
    await waitFor(() => expect(result.current.status).toBe('data'));
    expect(result.current.refreshFailed).toBe(false);
  });
});

// --- 2. the presentation: an observable, non-blocking notice ------------------

describe('R1b · LiveSyncNote states a failed refresh assertively', () => {
  it('renders nothing when neither degraded nor failed', () => {
    const { container } = render(<LiveSyncNote degraded={false} onRefresh={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it('states that the shown state is the last loaded one, and offers a retry', () => {
    const onRefresh = vi.fn();
    const { getByRole, getByText } = render(
      <LiveSyncNote degraded={false} refreshFailed onRefresh={onRefresh} />,
    );
    // An outage the reader acted into is an alert, not a passive status.
    const note = getByRole('alert');
    expect(note.textContent ?? '').toMatch(/last loaded state/i);
    expect(note.textContent ?? '').not.toMatch(/freshly (verified|checked)( one)?\./i);
    fireEvent.click(getByText('Refresh'));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('keeps the pre-existing degraded note unchanged when no refresh failed', () => {
    const { getByRole, getByText } = render(<LiveSyncNote degraded onRefresh={() => {}} />);
    expect(getByRole('status')).toBeInTheDocument();
    expect(getByText(/Live updates paused/)).toBeInTheDocument();
  });
});

// --- 3. the three real surfaces ----------------------------------------------

describe('R1b · the three surfaces that used a silent refresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5); // pin poll jitter
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  /**
   * A route that serves its real fixture until the test flips the switch, then
   * fails at HTTP level for every later call. A CALL-INDEX guard would be
   * fragile: how many times a screen loads an endpoint during its first paint is
   * an implementation detail (`getEvidenceBundle` fans out over five endpoints
   * plus one source-preview per cited file), and getting it wrong makes the
   * INITIAL load fail — which looks like a caught defect and is really a broken
   * test.
   */
  function failable(real: unknown) {
    const state = { failing: false };
    return {
      state,
      entry: () => (state.failing ? { status: 503, body: {} } : (real as { body: unknown })),
    };
  }

  /** The one honest note this fix adds, wherever it appears. */
  function refreshNote(container: HTMLElement): HTMLElement | null {
    return container.querySelector('.livesync-refresh-failed');
  }

  it('S6: Re-Validate on a passing card says so when the refresh does not land', async () => {
    const ready = exportReadyRoutes('demo');
    const readiness = failable(ready['POST /api/experiments/demo/validate']);
    stubFetchRoutes({
      ...ready,
      'POST /api/experiments/demo/audit': { body: auditExported },
      'POST /api/experiments/demo/export': { body: exportSuccess },
      'POST /api/experiments/demo/validate': readiness.entry,
    });

    const { getByText, queryByText, container } = renderAt('/record/demo/export');
    await settle();

    // The reserved PASS verdict — and its Re-Validate control — exist only after
    // a real export, so the flow is driven rather than faked into place.
    fireEvent.click(getByText('Export Official Record + Sidecar'));
    await settle();
    expect(getByText('Valid against official ISAAC schema v1.05.')).toBeInTheDocument();

    // Now the backend goes away, and the reader presses the trust control.
    readiness.state.failing = true;
    fireEvent.click(getByText('Re-Validate'));
    await settle();

    const note = refreshNote(container);
    expect(note, 'a failed Re-Validate must be observable').not.toBeNull();
    expect(note!.textContent ?? '').toMatch(/last loaded state/i);
    expect(note!.getAttribute('role')).toBe('alert');
    // ...and the screen was NOT blanked to a loading state.
    expect(queryByText(/Loading validation, coverage and advisory/)).toBeNull();
  });

  it('S3: a failed post-signal bundle refetch is stated, and the record stays on screen', async () => {
    const live = liveDetailRoute('demo');
    const routes = bundleRoutes('demo');
    const draft = failable(routes['GET /api/experiments/demo/draft']);
    stubFetchRoutes({
      ...routes,
      'GET /api/experiments/demo': live.route,
      'GET /api/experiments/demo/draft': draft.entry,
    });

    const { getByText, queryByText, container } = renderAt('/record/demo');
    await settle();
    expect(getByText('5 Fields Need Your Confirmation')).toBeInTheDocument();

    // A change elsewhere triggers the silent refetch, which now fails.
    draft.state.failing = true;
    live.bump();
    await settle(30_000);

    const note = refreshNote(container);
    expect(note, 'a failed silent refetch must be observable').not.toBeNull();
    expect(note!.textContent ?? '').toMatch(/last loaded state/i);
    // The record is still there — the fix must not blank or error the screen.
    expect(getByText('5 Fields Need Your Confirmation')).toBeInTheDocument();
    expect(queryByText(/Loading the record from the ISAAC API/)).toBeNull();
  });

  it('S5: the evidence trail says so too, rather than showing a pre-refresh state silently', async () => {
    const live = liveDetailRoute('demo');
    const routes = evidenceBundleRoutes('demo');
    const evidence = failable(routes['GET /api/experiments/demo/evidence']);
    stubFetchRoutes({
      ...routes,
      'GET /api/experiments/demo': live.route,
      'GET /api/experiments/demo/evidence': evidence.entry,
    });

    const { container, queryByText } = renderAt('/record/demo/evidence');
    await settle();
    expect(queryByText(/Loading the evidence trail/)).toBeNull(); // loaded first

    evidence.state.failing = true;
    live.bump();
    await settle(30_000);

    const note = refreshNote(container);
    expect(note, 'a failed silent refetch must be observable').not.toBeNull();
    expect(note!.textContent ?? '').toMatch(/last loaded state/i);
    expect(queryByText(/Loading the evidence trail/)).toBeNull();
  });
});

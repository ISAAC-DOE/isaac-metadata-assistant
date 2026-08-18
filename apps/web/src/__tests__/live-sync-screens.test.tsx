import { describe, it, expect, afterEach, beforeEach, vi, type Mock } from 'vitest';
import { render, act, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { LiveSyncNote } from '../components/LiveSyncNote';
import { api, ApiError } from '../lib/api';
import { POLL_INTERVAL_MS } from '../lib/useRecordSync';
import {
  bundleRoutes,
  evidenceBundleRoutes,
  exportReadyRoutes,
  experimentSummary,
  liveDetailRoute,
  stubFetchRoutes,
} from '../test/apiFixtures';

// RTL's async helpers (findBy/waitFor) don't drive vitest's fake timers, so these
// tests advance time manually and query synchronously after each flush.
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

function setHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event('visibilitychange'));
}

/** How many fetches so far hit a URL containing `substr`. */
function countCalls(substr: string): number {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls.filter(([url]) => String(url).includes(substr)).length;
}

/** How many polls (conditional GETs) fired — only checkRecordVersion sends If-None-Match. */
function countPolls(): number {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls.filter(
    ([, init]) => (init?.headers as Record<string, string> | undefined)?.['If-None-Match'] !== undefined,
  ).length;
}

describe('P27.6 · LiveSyncNote (degraded indicator)', () => {
  it('renders nothing until degraded, then shows an honest note + a working Refresh', () => {
    const onRefresh = vi.fn();
    const { container, rerender, getByText, getByRole } = render(
      <LiveSyncNote degraded={false} onRefresh={onRefresh} />,
    );
    expect(container.firstChild).toBeNull(); // not degraded → nothing

    rerender(<LiveSyncNote degraded onRefresh={onRefresh} />);
    // honest: it says "last loaded", never implies the shown state is fresh
    expect(getByText(/Live updates paused/)).toBeInTheDocument();
    expect(getByText(/last loaded state/)).toBeInTheDocument();
    expect(getByRole('status')).toBeInTheDocument();

    fireEvent.click(getByText('Refresh'));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});

describe('P27.6 · live-sync screen wiring', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5); // pin jitter → exact intervals
    setHidden(false);
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('S3: a change signal silently refetches the bundle (never blanks) and settles — no storm', async () => {
    const live = liveDetailRoute('demo');
    stubFetchRoutes({ ...bundleRoutes('demo'), 'GET /api/experiments/demo': live.route });
    const { getByText, queryByText } = renderAt('/record/demo');

    await settle(); // initial bundle load
    expect(getByText('5 Fields Need Your Confirmation')).toBeInTheDocument();
    expect(countCalls('/experiments/demo/draft')).toBe(1); // one bundle load so far

    // a couple of unchanged (304) ticks: no refetch, no blank
    await settle(POLL_INTERVAL_MS);
    await settle(POLL_INTERVAL_MS);
    expect(countCalls('/experiments/demo/draft')).toBe(1);
    expect(queryByText(/Loading the record/)).toBeNull();

    // change elsewhere → next poll is a 200 → exactly ONE silent bundle refetch
    live.bump();
    await settle(POLL_INTERVAL_MS);
    expect(countCalls('/experiments/demo/draft')).toBe(2);
    expect(queryByText(/Loading the record/)).toBeNull(); // still no loading blank
    expect(getByText('5 Fields Need Your Confirmation')).toBeInTheDocument();

    // the screen adopted the new version → further polls are 304 → no more refetches,
    // but the poller is still ALIVE: polls keep firing (a dead poller would also
    // hold draft at 2, so assert a POSITIVE further-poll count, not just "stayed").
    const pollsBefore = countPolls();
    await settle(POLL_INTERVAL_MS);
    await settle(POLL_INTERVAL_MS);
    expect(countCalls('/experiments/demo/draft')).toBe(2); // no storm
    expect(countPolls()).toBeGreaterThan(pollsBefore); // poller survived the adoption
  });

  it('S3: after repeated poll failures the degraded note shows and manual Refresh reloads', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    // The bundle loads via fetch; the poller (checkRecordVersion) fails every time.
    const spy = vi
      .spyOn(api, 'checkRecordVersion')
      .mockRejectedValue(new ApiError('down', { unreachable: true }));
    const { getByText, queryByText } = renderAt('/record/demo');

    await settle();
    expect(getByText('5 Fields Need Your Confirmation')).toBeInTheDocument();
    expect(queryByText(/Live updates paused/)).toBeNull();

    // three consecutive failures at 8s, +16s, +32s → degraded
    await settle(POLL_INTERVAL_MS);
    await settle(POLL_INTERVAL_MS * 2);
    await settle(POLL_INTERVAL_MS * 4);
    expect(spy).toHaveBeenCalledTimes(3);
    expect(getByText(/Live updates paused/)).toBeInTheDocument();

    // manual Refresh still works → a full bundle reload (draft fetched again)
    const before = countCalls('/experiments/demo/draft');
    fireEvent.click(getByText('Refresh'));
    await settle();
    expect(countCalls('/experiments/demo/draft')).toBeGreaterThan(before);
  });

  it('S5: a change signal silently refetches the evidence bundle', async () => {
    const live = liveDetailRoute('demo');
    stubFetchRoutes({ ...evidenceBundleRoutes('demo'), 'GET /api/experiments/demo': live.route });
    renderAt('/record/demo/evidence');

    // Count only the /evidence endpoint (not the P28.5 /evidence-classification,
    // which shares the `/evidence` prefix) as the proxy for one bundle load.
    const countEvidence = () =>
      ((globalThis.fetch as Mock).mock.calls as [string, RequestInit?][]).filter(([url]) =>
        String(url).endsWith('/experiments/demo/evidence'),
      ).length;

    await settle();
    expect(countEvidence()).toBe(1); // bundle loaded once

    live.bump();
    await settle(POLL_INTERVAL_MS);
    expect(countEvidence()).toBe(2); // one silent refetch
  });

  it('S4: a change elsewhere shows the input-preserving banner; staged input survives; Refresh reloads', async () => {
    const live = liveDetailRoute('demo');
    stubFetchRoutes({ ...bundleRoutes('demo'), 'GET /api/experiments/demo': live.route });
    const { getByText, getByLabelText, queryByText } = renderAt('/record/demo/complete');

    await settle();
    expect(getByText('What is the sha256 of the processing notebook?')).toBeInTheDocument();

    // stage input WITHOUT submitting
    fireEvent.change(getByLabelText('Asset Hash'), { target: { value: 'staged-hash' } });

    // a change elsewhere → the poller signals; NO auto-refetch, only the banner
    live.bump();
    await settle(POLL_INTERVAL_MS);
    expect(
      getByText(/This record changed elsewhere\. What you typed is kept, including through Refresh/),
    ).toBeInTheDocument();
    // the staged input is preserved (GuidedPrompt was not unmounted / not refetched)
    expect((getByLabelText('Asset Hash') as HTMLInputElement).value).toBe('staged-hash');
    expect(countCalls('/experiments/demo/answers')).toBe(0); // nothing submitted

    // Refresh reloads via the parent (a fresh pending fetch) and clears the banner
    const beforePending = countCalls('/experiments/demo/pending');
    fireEvent.click(getByText('Refresh'));
    await settle();
    expect(countCalls('/experiments/demo/pending')).toBeGreaterThan(beforePending);
    expect(queryByText(/This record changed elsewhere/)).toBeNull();

    /*
     * AND THE STAGED INPUT SURVIVED THE REFRESH — asserted here for the first time.
     *
     * This test preserved the input across the POLLER's signal, which never
     * refetched, and then pressed the very button that did. `reload` unmounts
     * `LoadedCompletion` and `GuidedPrompt` with it, so the field came back empty
     * beside a banner promising otherwise. The staged text now lives in a ref on the
     * parent, which the reload does not unmount.
     */
    expect((getByLabelText('Asset Hash') as HTMLInputElement).value).toBe('staged-hash');
  });

  it('S6: a change signal silently refetches the export readiness', async () => {
    const live = liveDetailRoute('demo');
    stubFetchRoutes({ ...exportReadyRoutes('demo'), 'GET /api/experiments/demo': live.route });
    const { getByText } = renderAt('/record/demo/export');

    await settle();
    expect(getByText('Export Official Record + Sidecar')).toBeInTheDocument();
    const before = countCalls('/experiments/demo/pending');

    live.bump();
    await settle(POLL_INTERVAL_MS);
    expect(countCalls('/experiments/demo/pending')).toBeGreaterThan(before); // silent refetch
  });

  it('Dashboard: no tight poll; a visibility-regain refetches the list once', async () => {
    stubFetchRoutes({ 'GET /api/experiments': { body: { experiments: [experimentSummary] } } });
    renderAt('/');

    await settle();
    expect(countCalls('/api/experiments')).toBe(1);

    // no interval polling — advancing time alone must not refetch the list
    await settle(POLL_INTERVAL_MS * 5);
    expect(countCalls('/api/experiments')).toBe(1);

    // regaining visibility refetches the list exactly once
    await act(async () => setHidden(true));
    await settle();
    await act(async () => setHidden(false));
    await settle();
    expect(countCalls('/api/experiments')).toBe(2);
  });

  it('no credential / token value ever appears in the rendered output', async () => {
    vi.stubEnv('VITE_API_KEY', 'super-secret-token-value');
    const live = liveDetailRoute('demo');
    stubFetchRoutes({ ...bundleRoutes('demo'), 'GET /api/experiments/demo': live.route });
    const { container } = renderAt('/record/demo');

    await settle();
    live.bump();
    await settle(POLL_INTERVAL_MS);

    expect(container.textContent).not.toContain('super-secret-token-value');
    expect(container.innerHTML).not.toContain('Bearer');
    vi.unstubAllEnvs();
  });
});

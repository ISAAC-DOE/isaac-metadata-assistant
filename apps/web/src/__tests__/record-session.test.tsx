import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { renderHook, act, render, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { api } from '../lib/api';
import { POLL_INTERVAL_MS } from '../lib/useRecordSync';
import { useRecordSession } from '../lib/useRecordSession';
import {
  clearAllSessions,
  loadSession,
  stageProposal,
  appendMessage,
} from '../lib/assistantSession';
import { confirmProposal, type AgentContext, type Proposal } from '../lib/assistantAgent';
import {
  EXP_ID,
  experimentDetail,
  experimentDetailChanged,
  pendingResponse,
  evidenceClassificationResponse,
  bundleRoutes,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { ApiExperimentDetail } from '../lib/types';

const DETAIL = experimentDetail as unknown as ApiExperimentDetail; // rev 3, version '1.0'
const CHANGED = experimentDetailChanged as unknown as ApiExperimentDetail; // rev 9, version '2.0'

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

/** Flush pending microtasks (the extras Promise.all) under fake timers. */
async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

// ---------------------------------------------------------------------------
// The hook: one shared authoritative record-session state (P29.4).
// ---------------------------------------------------------------------------

describe('useRecordSession — shared authoritative record state', () => {
  beforeEach(() => {
    clearAllSessions();
    vi.spyOn(api, 'getPending').mockResolvedValue(pendingResponse.pending as never);
    vi.spyOn(api, 'getEvidenceClassification').mockResolvedValue(
      evidenceClassificationResponse as never,
    );
    vi.spyOn(api, 'checkRecordVersion').mockResolvedValue({ changed: false });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAllSessions();
  });

  it('assembles the AgentContext from detail.workflow + pending + evidence-classification', async () => {
    const { result } = renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL }));
    await flush();

    const ctx = result.current.context!;
    expect(ctx).toBeDefined();
    expect(ctx.experimentId).toBe(EXP_ID);
    // rev is DERIVED from the version string (trailing segment), never read from
    // detail.rev independently, so it always matches the If-Match token.
    expect(ctx.recordRev).toBe(Number(DETAIL.version.split('.').pop()));
    expect(ctx.version).toBe(DETAIL.version); // authoritative ETag token
    expect(result.current.loading).toBe(false); // inputs settled
    expect(ctx.workflow.current_step).toBe(DETAIL.workflow.current_step);
    expect(ctx.workflow.ordered_steps.length).toBe(DETAIL.workflow.ordered_steps.length);
    expect(ctx.pending.length).toBe(pendingResponse.pending.length);
    expect(ctx.evidence.length).toBe(evidenceClassificationResponse.field_results.length);
    expect(result.current.degraded).toBe(false);
  });

  it('a manual edit that bumps the version updates the shared context the assistant reads', async () => {
    // Versions encode the rev in the trailing segment (`<generation>.<rev>`).
    const detailV5 = { ...DETAIL, version: '1.5', rev: 5 } as ApiExperimentDetail;
    const detailV6 = { ...DETAIL, version: '1.6', rev: 6 } as ApiExperimentDetail;
    const { result, rerender } = renderHook(
      ({ detail }: { detail: ApiExperimentDetail }) => useRecordSession(EXP_ID, { detail }),
      { initialProps: { detail: detailV5 } },
    );
    await flush();
    expect(result.current.context!.recordRev).toBe(5);
    expect(result.current.version).toBe('1.5');

    // A manual edit (submitAnswer/editField) advances the version; the screen
    // adopts the fresh detail and hands it to the ONE shared owner.
    rerender({ detail: detailV6 });
    await flush();
    expect(result.current.context!.recordRev).toBe(6); // assistant now sees the new rev
    expect(result.current.version).toBe('1.6');
  });

  it('a version change invalidates a staged proposal — it then cannot be confirmed', async () => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    // A proposal grounded in the OLD rev (3).
    stageProposal(EXP_ID, { field: 'sample.material.formula', value: 'CuO2', sourceRev: 3 });
    // The next poll reports the record advanced to rev 9.
    (api.checkRecordVersion as unknown as Mock).mockResolvedValue({ changed: true, detail: CHANGED });

    const { result } = renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    // The staged proposal is marked stale (never silently confirmable).
    expect(result.current.session.proposal?.stale).toBe(true);
    expect(loadSession(EXP_ID).proposal?.stale).toBe(true);

    // And an agent-shaped proposal at the old rev cannot be confirmed against the
    // advanced context: confirmProposal refuses (stale) WITHOUT touching the api.
    const submit = vi.spyOn(api, 'submitAnswer');
    const edit = vi.spyOn(api, 'editField');
    const staleProposal: Proposal = {
      id: 'p1',
      experimentId: EXP_ID,
      field: 'sample.material.formula',
      value: 'CuO2',
      origin: 'user',
      sourceRev: 3,
      confirmationState: 'pending',
    };
    const advancedCtx: AgentContext = {
      experimentId: EXP_ID,
      recordRev: 9,
      version: '2.0',
      workflow: { current_step: null, ordered_steps: [] },
      evidence: [],
      pending: [],
    };
    const outcome = await confirmProposal(staleProposal, advancedCtx, api);
    expect(outcome.status).toBe('stale');
    expect(submit).not.toHaveBeenCalled();
    expect(edit).not.toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('a stale/out-of-order async response for a previous record does not clobber the current one', async () => {
    // Record A holds its extras fetch open; record B resolves first. When A's
    // late response finally lands it must be dropped by the stale guard.
    let resolveA: (v: unknown) => void = () => {};
    (api.getPending as unknown as Mock).mockImplementation((id: string) => {
      if (id === 'A') return new Promise((res) => (resolveA = res));
      return Promise.resolve([{ id: 'b-pending', kind: 'asset', question: 'B?' }]);
    });
    (api.getEvidenceClassification as unknown as Mock).mockImplementation((id: string) =>
      Promise.resolve({
        record_rev: 0,
        field_results: id === 'A' ? [{ field: 'a.field' }] : [{ field: 'b.field' }],
        counts: {},
      }),
    );

    const detailA = { ...DETAIL, id: 'A' } as ApiExperimentDetail;
    const detailB = { ...DETAIL, id: 'B' } as ApiExperimentDetail;

    const { result, rerender } = renderHook(
      ({ id, detail }: { id: string; detail: ApiExperimentDetail }) =>
        useRecordSession(id, { detail }),
      { initialProps: { id: 'A', detail: detailA } },
    );
    // Switch to B before A's pending resolves.
    rerender({ id: 'B', detail: detailB });
    await flush();
    expect(result.current.context!.experimentId).toBe('B');

    // A's superseded response lands late — it must NOT overwrite B's state.
    await act(async () => {
      resolveA([{ id: 'a-pending', kind: 'asset', question: 'A?' }]);
      await Promise.resolve();
    });
    expect(result.current.context!.experimentId).toBe('B');
    expect(result.current.context!.evidence[0]?.field).toBe('b.field');
  });

  it('switching records does not leak the prior record conversation (per-experiment key)', async () => {
    appendMessage('A', { role: 'user', text: 'question about A', id: 'ma' });

    const { result, rerender } = renderHook(
      ({ id, detail }: { id: string; detail: ApiExperimentDetail }) =>
        useRecordSession(id, { detail }),
      { initialProps: { id: 'A', detail: { ...DETAIL, id: 'A' } as ApiExperimentDetail } },
    );
    await flush();
    expect(result.current.session.messages.some((m) => m.text === 'question about A')).toBe(true);

    rerender({ id: 'B', detail: { ...DETAIL, id: 'B' } as ApiExperimentDetail });
    await flush();
    expect(result.current.session.messages.length).toBe(0); // B starts clean
  });

  it('a still-pending inputs fetch is LOADING, not degraded; degraded only after it FAILS', async () => {
    // Hold the AgentContext inputs in-flight — a healthy slow network.
    let rejectPending: (e: unknown) => void = () => {};
    (api.getPending as unknown as Mock).mockImplementation(
      () => new Promise((_res, rej) => (rejectPending = rej)),
    );

    const { result } = renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL }));
    await flush();

    // Not-yet-loaded must NOT read as degraded (no false "cannot verify" flash).
    expect(result.current.degraded).toBe(false);
    expect(result.current.loading).toBe(true);
    expect(result.current.context).toBeUndefined();

    // Only once the fetch actually FAILS does the honest degraded state appear.
    await act(async () => {
      rejectPending(new Error('network'));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.degraded).toBe(true);
    expect(result.current.loading).toBe(false);
    expect(result.current.context!.degraded).toBe(true);
  });

  it('rev is derived from the version so it can never desync (advanced version wins over stale detail.rev)', async () => {
    // The screen advanced the If-Match token to rev 6 (a local edit), but the
    // stale bundle detail.rev is still 5. The derived context rev must follow the
    // VERSION (6), not the stale detail.rev (5).
    const detailAdvanced = { ...DETAIL, version: '1.6', rev: 5 } as ApiExperimentDetail;
    const { result } = renderHook(() => useRecordSession(EXP_ID, { detail: detailAdvanced }));
    await flush();

    expect(result.current.context!.version).toBe('1.6');
    expect(result.current.context!.recordRev).toBe(6); // matches the version, not detail.rev (5)

    // A proposal staged at the OLD rev (5) is therefore correctly stale against
    // the advanced context and cannot be confirmed — closing the desync window.
    const submit = vi.spyOn(api, 'submitAnswer');
    const staleProposal: Proposal = {
      id: 'p2',
      experimentId: EXP_ID,
      field: 'sample.material.formula',
      value: 'CuO2',
      origin: 'user',
      sourceRev: 5,
      confirmationState: 'pending',
    };
    const outcome = await confirmProposal(staleProposal, result.current.context!, api);
    expect(outcome.status).toBe('stale');
    expect(submit).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Screen wiring: one poller, manual-first degradation.
// ---------------------------------------------------------------------------

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={FUTURE}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

function setHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event('visibilitychange'));
}

function countPolls(): number {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls.filter(
    ([, init]) =>
      (init?.headers as Record<string, string> | undefined)?.['If-None-Match'] !== undefined,
  ).length;
}

describe('P29.4 · record screen wiring', () => {
  it('mounts exactly ONE poller per record (no duplicate useRecordSync)', async () => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    setHidden(false);
    stubFetchRoutes(bundleRoutes('demo'));
    renderAt('/record/demo');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    // Exactly one conditional GET per interval → one poller. Two pollers would
    // double it.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(countPolls()).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(countPolls()).toBe(2);

    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('manual-first degradation: the workflow + fields still render when the assistant context fetch fails', async () => {
    // The evidence-classification endpoint (an AgentContext input) fails; the
    // assistant degrades honestly, but the manual record workflow stays usable.
    const routes = {
      ...bundleRoutes('demo'),
      'GET /api/experiments/demo/evidence-classification': { status: 500, body: { error: 'boom' } },
    };
    stubFetchRoutes(routes);
    const { findByText, getByText } = renderAt('/record/demo');

    // Manual workflow renders: the grouped draft + the needs-you gate.
    await findByText('5 Fields Need Your Confirmation');
    expect(getByText('Technique')).toBeInTheDocument(); // a real draft field
    // The assistant shows an honest degraded state (never disables the workflow).
    await findByText(/cannot verify the current record state/i);
  });
});

// ---------------------------------------------------------------------------
// Reset clears the session.
// ---------------------------------------------------------------------------

describe('P29.4 · Reset clears the assistant session', () => {
  it('a successful Reset Demo clears conversation + staged proposals', async () => {
    const { resetDemoRoutes } = await import('../test/apiFixtures');
    const { routes } = resetDemoRoutes();
    stubFetchRoutes(routes);

    // Seed a conversation + a staged proposal for some experiment.
    appendMessage(EXP_ID, { role: 'user', text: 'seeded question', id: 'seed' });
    stageProposal(EXP_ID, { field: 'sample.material.formula', value: 'CuO2', sourceRev: 3 });
    expect(loadSession(EXP_ID).messages.length).toBe(1);
    expect(loadSession(EXP_ID).proposal).not.toBeNull();

    const view = renderAt('/experiments');
    const trigger = (await view.findByRole('button', { name: 'Reset Demo' })) as HTMLButtonElement;
    fireEvent.click(trigger);

    const dialog = await view.findByRole('dialog');
    const input = within(dialog).getByLabelText(/Type RESET to confirm/i);
    fireEvent.change(input, { target: { value: 'RESET' } });
    const confirm = within(dialog).getByRole('button', { name: /Reset the Demo|Reset Demo|Reset/i });
    fireEvent.click(confirm);

    await waitFor(() => {
      // After a successful reset, the ephemeral session is wiped: no messages,
      // no staged proposal (a prior proposal can never be confirmed post-reset).
      expect(loadSession(EXP_ID).messages.length).toBe(0);
      expect(loadSession(EXP_ID).proposal).toBeNull();
    });
  });
});

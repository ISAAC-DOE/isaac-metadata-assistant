import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  bundleRoutes,
  evidenceBundleRoutes,
  experimentSummary,
  graphStatusAvailable,
  stubFetchRoutes,
} from '../test/apiFixtures';

/*
 * P33 S5 (A11Y-1) — every routed surface exposes exactly ONE screen-level <h1>
 * so screen-reader users get a correct document outline. Before S5: record /
 * evidence / export had none, Guided Completion had two, and memory/governance/
 * settings started at <h2>. This pins the one-h1 contract.
 */

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

async function h1CountAt(
  path: string,
  stub: Record<string, unknown> | null,
  awaitText: string | null,
): Promise<number> {
  if (stub) stubFetchRoutes(stub as never);
  const view = renderAt(path);
  if (awaitText) await view.findByText(awaitText);
  return view.container.querySelectorAll('h1').length;
}

describe('A11Y-1 — one screen-level h1 per routed surface', () => {
  it('My Experiments', async () => {
    expect(
      await h1CountAt('/experiments', { 'GET /api/experiments': { body: { experiments: [experimentSummary] } } }, 'Synthetic XANES — CuO (Cu K-edge) Demo'),
    ).toBe(1);
  });
  it('Record Workbench', async () => {
    expect(await h1CountAt('/record/demo', bundleRoutes('demo'), '5 Fields Need Your Confirmation')).toBe(1);
  });
  it('Guided Completion', async () => {
    expect(await h1CountAt('/record/demo/complete', bundleRoutes('demo'), 'Answer 5 Questions to Finish This Record')).toBe(1);
  });
  it('Evidence Explorer', async () => {
    expect(await h1CountAt('/record/demo/evidence', evidenceBundleRoutes('demo'), 'Direct Fields')).toBe(1);
  });
  it('Export Readiness', async () => {
    expect(await h1CountAt('/record/demo/export', bundleRoutes('demo'), '5 fields still block export')).toBe(1);
  });
  it('Project Memory', async () => {
    expect(await h1CountAt('/memory', { 'GET /api/graph/status': { body: graphStatusAvailable } }, 'Memory Available')).toBe(1);
  });
  it('Governance & Safety', async () => {
    expect(await h1CountAt('/governance', null, null)).toBe(1);
  });
  it('Settings', async () => {
    expect(await h1CountAt('/settings', null, null)).toBe(1);
  });
});

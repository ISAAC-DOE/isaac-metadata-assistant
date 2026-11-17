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

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('router-level smoke: each surface renders without error', () => {
  it('S1 · My Experiments (/experiments) — live queue', async () => {
    stubFetchRoutes({
      'GET /api/experiments': { body: { experiments: [experimentSummary] } },
    });
    const { findByText } = renderAt('/experiments');
    expect(await findByText('Synthetic XANES — CuO (Cu K-edge) Demo')).toBeInTheDocument();
  });

  // ~~S2 · Load Materials (/load)~~ — retired 2026-11-16: `/load` redirects to My
  // Experiments (`historical-import-guide.test.tsx`).
  it('Historical Import (/imports) is the skill guide', () => {
    const { getByText, getAllByText } = renderAt('/imports');
    expect(getByText('Historical Import', { selector: 'h1' })).toBeInTheDocument();
    expect(getAllByText('scripts/setup_isaac_local.sh --install-skill').length).toBeGreaterThan(0);
  });

  it('S3 · Review Record (/record/:id) — live bundle', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText } = renderAt('/record/demo');
    expect(await findByText('5 Fields Need Your Confirmation')).toBeInTheDocument();
  });

  it('S4 · Complete Missing Fields (/record/:id/complete) — live pending', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText } = renderAt('/record/demo/complete');
    expect(await findByText('Answer 5 Questions to Finish This Record')).toBeInTheDocument();
  });

  it('S5 · Evidence & File Preview (/record/:id/evidence) — live evidence trail', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { findByText } = renderAt('/record/demo/evidence');
    expect(await findByText('Direct Fields')).toBeInTheDocument();
  });

  it('S6 · Ready to Export (/record/:id/export) — live gate state', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText } = renderAt('/record/demo/export');
    expect(await findByText('5 fields still block export')).toBeInTheDocument();
  });

  it('Project Memory (/memory) is a separate destination, with the developer flag', async () => {
    vi.stubEnv('VITE_ISAAC_DEV_TOOLS', '1');
    stubFetchRoutes({ 'GET /api/graph/status': { body: graphStatusAvailable } });
    const { getByText, findByText } = renderAt('/memory');
    // ~~'Memory / Query Plane'~~ — the eyebrow was removed 2026-10-12 (clutter audit;
    // an eyebrow over a heading restates it). The destination is named by its h1.
    expect(getByText('Project Memory', { selector: 'h1' })).toBeInTheDocument();
    // Freshness is live from the endpoint, not a hardcoded claim.
    await findByText('Memory Available');
  });

  it('the index route redirects into the queue', async () => {
    stubFetchRoutes({
      'GET /api/experiments': { body: { experiments: [experimentSummary] } },
    });
    const { findByText } = renderAt('/');
    expect(await findByText('Synthetic XANES — CuO (Cu K-edge) Demo')).toBeInTheDocument();
  });
});

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { bundleRoutes, experimentSummary, stubFetchRoutes } from '../test/apiFixtures';

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

  it('S2 · Load Materials (/load)', () => {
    const { getByText } = renderAt('/load');
    expect(getByText('Run the Synthetic Demo')).toBeInTheDocument();
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

  it('S5 · Evidence & File Preview (/record/:id/evidence)', () => {
    const { getByText } = renderAt('/record/demo/evidence');
    expect(getByText('Direct Fields')).toBeInTheDocument();
  });

  it('S6 · Ready to Export (/record/:id/export) — live gate state', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText } = renderAt('/record/demo/export');
    expect(await findByText('5 fields still block export')).toBeInTheDocument();
  });

  it('Project Memory (/memory) is a separate destination', () => {
    const { getByText } = renderAt('/memory');
    expect(getByText('Memory / Query Plane')).toBeInTheDocument();
  });

  it('the index route redirects into the queue', async () => {
    stubFetchRoutes({
      'GET /api/experiments': { body: { experiments: [experimentSummary] } },
    });
    const { findByText } = renderAt('/');
    expect(await findByText('Synthetic XANES — CuO (Cu K-edge) Demo')).toBeInTheDocument();
  });
});

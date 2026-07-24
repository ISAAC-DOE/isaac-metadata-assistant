import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TopBar } from '../components/TopBar';
import { __resetHealthCache } from '../lib/useHealth';
import {
  healthNonSynthetic,
  healthSynthetic,
  stubFetchDown,
  stubFetchRoutes,
} from '../test/apiFixtures';

// P27.5 — the Synthetic mode chip is driven by the backend health.mode (via the
// shared, cached useHealth) rather than a hardcoded label. The backend reports
// mode "synthetic-only", which maps to the friendly "Synthetic" label. Because
// this is a synthetic-only app, a missing/failed health check must degrade to the
// same synthetic indicator — never vanish, never imply non-synthetic.

beforeEach(() => {
  __resetHealthCache(); // fresh module cache so each case proves a real fetch
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderTopBar() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <TopBar variant="home" />
    </MemoryRouter>,
  );
}

describe('Synthetic mode chip — health-driven', () => {
  it('renders "Synthetic" from health.mode "synthetic-only" (queries the health endpoint)', async () => {
    const calls = stubFetchRoutes({ 'GET /api/health': { body: healthSynthetic } });
    const { container } = renderTopBar();

    // the chip drives itself from the health endpoint, not a hardcoded label
    await waitFor(() => expect(calls).toContain('GET /api/health'));
    const chip = container.querySelector('.mode-chip')!;
    expect(chip).not.toBeNull();
    expect(chip.textContent).toContain('Synthetic');
  });

  it('surfaces an UNEXPECTED backend mode truthfully — a distinct label, never masked as "Synthetic"', async () => {
    // healthNonSynthetic.mode is 'production'. This app is synthetic-only by hard
    // invariant, so an anomalous reported mode must be shown, not hidden. This
    // test is falsifiable: it fails if health.mode stops driving the label.
    const calls = stubFetchRoutes({ 'GET /api/health': { body: healthNonSynthetic } });
    const { container } = renderTopBar();

    await waitFor(() => expect(calls).toContain('GET /api/health'));
    await waitFor(() => {
      const chip = container.querySelector('.mode-chip')!;
      expect(chip.textContent).toContain('Production'); // capitalized raw mode
      expect(chip.textContent).not.toContain('Synthetic');
    });
  });

  it('still shows the synthetic indicator when the health check fails (degrades gracefully)', async () => {
    stubFetchDown();
    const { container } = renderTopBar();

    // a failed health check must NOT hide the chip or imply non-synthetic
    await waitFor(() => {
      const chip = container.querySelector('.mode-chip');
      expect(chip).not.toBeNull();
      expect(chip!.textContent).toContain('Synthetic');
    });
  });
});

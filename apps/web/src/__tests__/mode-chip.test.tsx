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

// P27.5 — the mode chip is driven by the backend health.mode (via the shared,
// cached useHealth) rather than a hardcoded label. The backend reports mode
// "synthetic-only", which maps to the product-facing "Example workspace" label
// (R0; the WIRE value is untouched). Because this app is synthetic-only by hard
// invariant, a missing/failed health check must degrade to the SAME indicator —
// never vanish, and never read as something else.

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

describe('mode chip — health-driven', () => {
  it('renders "Example workspace" from health.mode "synthetic-only" (queries the health endpoint)', async () => {
    const calls = stubFetchRoutes({ 'GET /api/health': { body: healthSynthetic } });
    const { container } = renderTopBar();

    // the chip drives itself from the health endpoint, not a hardcoded label
    await waitFor(() => expect(calls).toContain('GET /api/health'));
    const chip = container.querySelector('.mode-chip')!;
    expect(chip).not.toBeNull();
    expect(chip.textContent).toContain('Example workspace');
  });

  it('surfaces an UNEXPECTED backend mode truthfully — a distinct label, never masked as the expected one', async () => {
    // healthNonSynthetic.mode is 'production'. This app is synthetic-only by hard
    // invariant, so an anomalous reported mode must be shown, not hidden. This
    // test is falsifiable: it fails if health.mode stops driving the label.
    const calls = stubFetchRoutes({ 'GET /api/health': { body: healthNonSynthetic } });
    const { container } = renderTopBar();

    await waitFor(() => expect(calls).toContain('GET /api/health'));
    await waitFor(() => {
      const chip = container.querySelector('.mode-chip')!;
      expect(chip.textContent).toContain('Production'); // capitalized raw mode
      expect(chip.textContent).not.toContain('Example workspace');
      expect(chip.textContent).not.toContain('Synthetic');
    });
  });

  it('still shows the example-workspace indicator when the health check fails (degrades gracefully)', async () => {
    stubFetchDown();
    const { container } = renderTopBar();

    // a failed health check must NOT hide the chip or read as something else
    await waitFor(() => {
      const chip = container.querySelector('.mode-chip');
      expect(chip).not.toBeNull();
      expect(chip!.textContent).toContain('Example workspace');
    });
  });
});

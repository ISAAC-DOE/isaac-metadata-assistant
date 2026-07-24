import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  bundleRoutes,
  evidenceBundleRoutes,
  stubFetchRoutes,
  graphStatusAvailable,
} from '../test/apiFixtures';

/*
 * P33 Human-QA #6/#7 — memory casing + single-state.
 *  - Where the assistant head is the SOLE availability indicator (the record
 *    workbench has no GraphStatusChip), it reads the Title-Case state
 *    "Memory Available" (never the lowercase "memory: available"), keeping its
 *    dot.
 *  - Where a GraphStatusChip already owns the state (Project Memory, Evidence
 *    Explorer), the assistant head does NOT duplicate it (single "Memory
 *    Available" state on the page). `availability` is still passed to the panel,
 *    so classification / caveat behavior is unchanged.
 */

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('P33 HQA#6 — assistant memory head casing', () => {
  it('record workbench (sole indicator): Title-Case "Memory Available", not "memory: available"', async () => {
    stubFetchRoutes({ ...bundleRoutes('demo'), 'GET /api/graph/status': { body: graphStatusAvailable } });
    const { findByText, container } = renderAt('/record/demo');
    await findByText('5 Fields Need Your Confirmation');
    const head = container.querySelector('.assistant-memory') as HTMLElement;
    expect(head).not.toBeNull();
    expect(head.textContent).toMatch(/Memory Available/);
    expect(head.textContent).not.toMatch(/memory: available/i);
    // the dot is preserved (color is never the only signal — text carries it)
    expect(head.querySelector('.dot-memory')).not.toBeNull();
  });
});

describe('P33 HQA#7 — no duplicate availability state where a chip owns it', () => {
  it('Project Memory: the assistant head does not duplicate the GraphStatusChip', async () => {
    stubFetchRoutes({ 'GET /api/graph/status': { body: graphStatusAvailable } });
    const { findByText, container } = renderAt('/memory');
    await findByText('Memory Available'); // exactly one — the chip
    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant).not.toBeNull();
    expect(assistant.querySelector('.assistant-memory')).toBeNull();
  });

  it('Evidence Explorer: the assistant head does not duplicate the status-bar chip', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo/evidence');
    await findByText('Direct Fields');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant).not.toBeNull();
    expect(assistant.querySelector('.assistant-memory')).toBeNull();
  });
});

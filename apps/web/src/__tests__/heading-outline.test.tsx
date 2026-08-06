import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  bundleRoutes,
  evidenceBundleRoutes,
  experimentSummary,
  graphStatusAvailable,
  graphStatusUnavailable,
  memoryGraphAvailable,
  statisticsRoutes,
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
  it('Statistics', async () => {
    // Awaiting the Title-Cased runtime mode settles the /api/about read, so the
    // count is taken on the LOADED dashboard rather than on its loading state.
    expect(await h1CountAt('/statistics', statisticsRoutes(), 'Synthetic-Only')).toBe(1);
  });
});

/*
 * P36V PR2 — one h1 is necessary but not sufficient: an outline also has to be
 * READABLE in document order. The Graph tab shipped a `<h4>Legend</h4>` under
 * the card's `<h2>` and BEFORE the detail pane's `<h3>`, so the outline both
 * skipped a level and went deeper-then-shallower — the one shape a screen
 * reader's heading navigation cannot recover from. Level 1 is the app shell's.
 */
describe('A11Y — heading levels never skip a level or go backwards', () => {
  const levels = (root: ParentNode): number[] =>
    [...root.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((h) => Number(h.tagName[1]));

  /** Every step down must be by exactly one; steps up may go any distance. */
  function assertMonotonic(found: number[], where: string) {
    expect(found.length, `${where}: no headings found`).toBeGreaterThan(0);
    for (let i = 1; i < found.length; i += 1) {
      expect(
        found[i] - found[i - 1],
        `${where}: h${found[i - 1]} → h${found[i]} at index ${i} (${found.join(',')})`,
      ).toBeLessThanOrEqual(1);
    }
  }

  it('Project Memory · Graph (Explore, a node selected)', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const view = renderAt('/memory');
    fireEvent.click(view.getByRole('tab', { name: 'Graph' }));
    await view.findByText('Graph', { selector: 'h2' });

    // The legend renders in Explore; the detail pane needs a selection, which
    // Browse can make and Explore then keeps — that is the exact pairing that
    // put an h4 before an h3.
    fireEvent.click(view.getByRole('radio', { name: 'Browse' }));
    fireEvent.click(view.getByText('src/fake_mod.py'));
    fireEvent.click(view.getByRole('radio', { name: 'Explore' }));

    const card = view.container.querySelector('.memory-graph-card') as HTMLElement;
    expect(card.querySelector('.graph-legend')).not.toBeNull();
    expect(card.querySelector('.memory-graph-detail')).not.toBeNull();
    assertMonotonic(levels(card), 'graph card');
    assertMonotonic(levels(view.container), 'Project Memory page');
  });

  /*
   * `/statistics` was in the one-h1 suite above but absent from this one — the
   * only screen whose outline goes THREE levels deep, which is precisely the shape
   * a skip or a backwards step hides in.
   *
   * THE EXPECTED OUTLINE CHANGED WITH THE TAB RESTRUCTURE, and the reason is
   * worth writing down because it is the interesting part. Its General ISAAC tab
   * is now h1 → four h2 sections (Workspace at a Glance · Workflow Distribution ·
   * Evidence and Validation, which nests `Evidence Support` and `Export Gate` as
   * h3 · This Application Collects No Analytics) → a fifth h2 `Technical Details`
   * which nests THREE h3 sections (Runtime · Project Memory · API Surface).
   *
   * The three trailing h3s are inside a `<details>` that is CLOSED by default, and
   * they are counted here on purpose: `querySelectorAll` sees the whole DOM, so
   * this asserts the outline is well-formed in BOTH states of the disclosure.
   * (`e2e/specs/structure.spec.ts` filters by computed style and therefore checks
   * the collapsed state as a real browser renders it — the two are complementary,
   * and neither alone would catch a heading that is only wrong when open.)
   */
  it('Statistics · General ISAAC (every section loaded, Technical Details closed)', async () => {
    stubFetchRoutes(statisticsRoutes());
    const view = renderAt('/statistics');
    // Settles /api/about, which is the last of the four reads to paint.
    await view.findByText('Synthetic-Only');

    const found = levels(view.container);
    // The FIVE 3s in the middle are Record Verification's own sub-headings,
    // under its h2: the official/shadow comparison, the issue distributions,
    // mutation verification, safeguards, and the run details. (It was four
    // before the comparison became a grouped chart with a heading of its own —
    // the outline is unchanged in shape, one level deeper nowhere.)
    expect(found).toEqual([1, 2, 2, 2, 3, 3, 2, 3, 3, 3, 3, 3, 2, 2, 3, 3, 3]);
    assertMonotonic(found, 'Statistics page · General ISAAC');
  });

  /*
   * ...AND THE MY STATS TAB, which has its own outline and would otherwise be
   * checked by nothing: it is a `?tab=` deep link, so a page-level render at
   * `/statistics` never reaches it. h1 → h2 `Personal Statistics` → h2 `Views
   * Prepared for Your Account` → one h3 per planned view.
   */
  it('Statistics · My Stats', async () => {
    stubFetchRoutes(statisticsRoutes());
    const view = renderAt('/statistics?tab=mine');
    await view.findByText('Not Available in This Preview');

    const found = levels(view.container);
    expect(found.slice(0, 3)).toEqual([1, 2, 2]);
    expect(found.slice(3)).toEqual([3, 3, 3, 3, 3, 3, 3, 3]);
    assertMonotonic(found, 'Statistics page · My Stats');
  });

  it('Project Memory · Graph · About This Graph drawer', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const view = renderAt('/memory');
    fireEvent.click(view.getByRole('tab', { name: 'Graph' }));
    await view.findByText('Graph', { selector: 'h2' });
    fireEvent.click(view.getByRole('button', { name: 'About This Graph' }));
    assertMonotonic(levels(view.getByRole('dialog')), 'graph help dialog');
  });
});

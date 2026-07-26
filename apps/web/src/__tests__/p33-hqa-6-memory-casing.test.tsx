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
 *  - Where the assistant panel is the SOLE availability indicator (the record
 *    workbench has no GraphStatusChip), it reads the Title-Case state
 *    "Memory Available" (never the lowercase "memory: available"), keeping its
 *    dot.
 *  - Where a GraphStatusChip already owns the state (Project Memory, Evidence
 *    Explorer), the assistant does NOT duplicate it (single "Memory Available"
 *    state on the page). `availability` is still passed to the panel, so
 *    classification / caveat behavior is unchanged.
 *
 * P36V S-A briefly deleted the `showAvailabilityHead` opt-out, which reversed
 * HQA#7 and made the identical state render twice on those two pages. The
 * opt-out is back as `showAvailabilityStatus`, and this file now guards the
 * contract more tightly than it did before:
 *
 *   - the axis is stated EXACTLY ONCE page-wide, and
 *   - no two elements expose DIFFERENTLY-WORDED accessible names for it.
 *
 * That second guard is the one that matters most for assistive tech: the chip's
 * accessible name is "Project memory available — memory plane, advisory only,
 * never a validator" while the assistant row's name is its visible text
 * "Memory Available", so a duplicate is not merely redundant — it announces one
 * axis in two different wordings.
 */

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

/*
 * The axis LABEL wordings — deliberately anchored, so this counts status LABELS
 * and not prose. Both current forms are covered, plus the retired lowercase one:
 *   · the assistant status row's own text  → "Memory Available" / "memory: available"
 *   · the GraphStatusChip's accessible name → "Project memory available — …"
 * The honest memory CAVEAT ("Project Memory is unavailable, so no memory-based
 * answer is available here.") is a different sentence making a different point,
 * and is correctly NOT counted as a second statement of the status label.
 */
const AXIS_TEXT = /^memory:?\s*(un)?available$/i;
const AXIS_LABEL = /^project memory:?\s*(un)?available\b/i;

/** An element's OWN text (direct text-node children only), normalised. */
function ownText(el: Element): string {
  return Array.from(el.childNodes)
    .filter((n) => n.nodeType === Node.TEXT_NODE)
    .map((n) => n.textContent ?? '')
    .join('')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Every element on the page that STATES the availability axis to a reader, with
 * the exact wording each one exposes.
 *
 * An element is a statement root when it either
 *   (a) carries an `aria-label` about the axis — which REPLACES its whole
 *       subtree for assistive tech, so its visible inner label is not announced
 *       separately (this is the GraphStatusChip), or
 *   (b) carries the axis as its own direct text and is not inside such an
 *       aria-labelled element (this is the assistant status row).
 * The `wording` is therefore what a screen reader would actually announce.
 */
function axisStatements(root: ParentNode): { el: Element; wording: string }[] {
  const labelled = Array.from(root.querySelectorAll('[aria-label]')).filter((el) =>
    AXIS_LABEL.test((el.getAttribute('aria-label') ?? '').trim()),
  );
  const out = labelled.map((el) => ({ el, wording: el.getAttribute('aria-label')!.trim() }));
  for (const el of Array.from(root.querySelectorAll('*'))) {
    const own = ownText(el);
    if (!AXIS_TEXT.test(own)) continue;
    if (labelled.some((l) => l === el || l.contains(el))) continue; // announced via the aria-label
    out.push({ el, wording: own });
  }
  return out;
}

afterEach(() => vi.unstubAllGlobals());

describe('P33 HQA#6 — assistant memory status casing', () => {
  it('record workbench (sole indicator): Title-Case "Memory Available", not "memory: available"', async () => {
    stubFetchRoutes({ ...bundleRoutes('demo'), 'GET /api/graph/status': { body: graphStatusAvailable } });
    const { findByText, getAllByText, container } = renderAt('/record/demo');
    await findByText('5 Fields Need Your Confirmation');
    const head = container.querySelector('.assistant-memory') as HTMLElement;
    expect(head).not.toBeNull();
    expect(head.textContent).toMatch(/Memory Available/);
    expect(head.textContent).not.toMatch(/memory: available/i);
    // the dot is preserved (color is never the only signal — text carries it)
    expect(head.querySelector('.dot-memory')).not.toBeNull();
    // this screen renders NO GraphStatusChip, so the panel is the sole owner:
    // the axis is stated exactly once, in exactly one wording, by the panel.
    expect(getAllByText('Memory Available').length).toBe(1);
    const stmts = axisStatements(container);
    expect(stmts.length).toBe(1);
    expect(stmts[0].el.closest('.assistant')).not.toBeNull();
  });
});

describe('P33 HQA#7 — no duplicate availability state where a chip owns it', () => {
  it('Project Memory: the assistant does not duplicate the GraphStatusChip', async () => {
    stubFetchRoutes({ 'GET /api/graph/status': { body: graphStatusAvailable } });
    const { findByText, getAllByText, container } = renderAt('/memory');
    // singular findByText: it THROWS on more than one match, so this alone is a
    // duplicate guard — exactly one visible "Memory Available", the chip's.
    await findByText('Memory Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant).not.toBeNull();
    expect(assistant.querySelector('.assistant-memory')).toBeNull();

    // stated EXACTLY ONCE page-wide …
    expect(getAllByText('Memory Available').length).toBe(1);
    const stmts = axisStatements(container);
    expect(stmts.length).toBe(1);
    // … by the PAGE, not the assistant …
    expect(stmts[0].el.closest('.assistant')).toBeNull();
    expect(stmts[0].el.getAttribute('aria-label')).toMatch(/memory plane, advisory only/i);
    // … and therefore in exactly ONE wording (no second, differently-worded
    // accessible name for the same axis).
    expect(new Set(stmts.map((s) => s.wording)).size).toBe(1);
    // the retired lowercase form appears nowhere on the page
    expect(container.textContent).not.toMatch(/memory: available/i);
  });

  it('Evidence Explorer: the assistant does not duplicate the status-bar chip', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { findByText, getAllByText, container } = renderAt('/record/demo/evidence');
    await findByText('Direct Fields');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant).not.toBeNull();
    expect(assistant.querySelector('.assistant-memory')).toBeNull();

    // this fixture reports the memory plane as unavailable; it degrades quietly
    // and is still stated exactly once, by the status-bar chip.
    expect(getAllByText('Memory Unavailable').length).toBe(1);
    const stmts = axisStatements(container);
    expect(stmts.length).toBe(1);
    expect(stmts[0].el.closest('.assistant')).toBeNull();
    expect(stmts[0].el.getAttribute('aria-label')).toMatch(/memory plane, advisory only/i);
    expect(new Set(stmts.map((s) => s.wording)).size).toBe(1);
    expect(container.textContent).not.toMatch(/memory: (un)?available/i);
  });
});

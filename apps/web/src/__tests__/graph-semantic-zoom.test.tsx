import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, render, fireEvent, waitFor, within, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  LOD_CLUSTER_SCALE,
  LOD_SYMBOL_SCALE,
  MAX_MARK_UNITS_AT_SCALE_1,
  MIN_MARK_UNITS_AT_SCALE_1,
} from '../lib/graphModel';
import {
  stubFetchRoutes,
  graphStatusUnavailable,
  memoryGraphAvailable,
} from '../test/apiFixtures';
import {
  DEEP_BUILT_AT_COMMIT,
  DEEP_EDGE_ROWS,
  DEEP_NODE_ROWS,
  memoryGraphDetailAvailable,
  memoryGraphDetailStaleServedSet,
  memoryGraphDetailUnavailable,
} from '../test/graphDeepFixture';

/*
 * P36V.1 Unit F — SEMANTIC ZOOM on the Project Memory graph, mounted.
 *
 * The defect: zooming magnified the same sparse node set (every size was a
 * constant in SVG user units, and label visibility was decided by node count,
 * never by zoom). The fix has three parts, all asserted here:
 *   1. screen-space sizing, so nothing grows without bound;
 *   2. a LAZY deep layer that reveals real clusters and then real symbols;
 *   3. explicit structural-staleness provenance, because a 2,612-node symbol map
 *      READS as a map of the current code and this one is pinned to a commit.
 *
 * Routes are stubbed per scenario; `stubFetchRoutes` throws on any unstubbed
 * call, so an accidental eager fetch of the ~500 kB deep payload fails loudly —
 * which is exactly what section 1 relies on.
 */

const baseRoutes = {
  'GET /api/graph/status': { body: graphStatusUnavailable },
  'GET /api/memory/graph': { body: memoryGraphAvailable },
};
const deepRoute = 'GET /api/memory/graph/detail';

function renderGraph(routes: Record<string, { body: unknown }> = baseRoutes) {
  const calls = stubFetchRoutes(routes);
  const view = render(
    <MemoryRouter
      initialEntries={['/memory?tab=graph']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
    </MemoryRouter>,
  );
  return { view, calls };
}

const withDeep = { ...baseRoutes, [deepRoute]: { body: memoryGraphDetailAvailable } };

const svgEl = () => document.querySelector('.memory-graph-svg') as SVGSVGElement;
const deepMarks = () => [...document.querySelectorAll('.memory-graph-deep-node')];
const deepEdges = () => [...document.querySelectorAll('.memory-graph-deep-edge')];
const baseNodes = () => [...document.querySelectorAll('.memory-graph-node:not(.memory-graph-deep-node)')];
const reveal = (view: RenderResult) =>
  fireEvent.click(view.getByRole('button', { name: 'Reveal Detail' }));

/** Select a BASE node from the keyboard, which also anchors Reveal Detail on it. */
function selectBaseNode(name: RegExp) {
  const svg = svgEl() as unknown as HTMLElement;
  const node = within(svg).getByRole('button', { name });
  fireEvent.keyDown(node, { key: 'Enter' });
  return node;
}

/** Zoom to the symbol level, centred on `src/fake_mod.py`. */
async function zoomToSymbols(view: RenderResult) {
  await view.findByText('Graph', { selector: 'h2' });
  selectBaseNode(/^src\/fake_mod\.py, file/);
  reveal(view); // → cluster level, centred on the selection
  await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
  reveal(view); // → symbol level
  await waitFor(() =>
    expect(deepMarks().every((m) => m.getAttribute('data-deep-kind') === 'symbol')).toBe(true),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- 1. the deep layer is LAZY ----------------------------------------------

describe('semantic zoom — the deep layer costs nothing until it is asked for', () => {
  it('is never fetched on mount, or at 100% zoom', async () => {
    const { view, calls } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });
    expect(calls).toContain('GET /api/memory/graph');
    expect(calls).not.toContain(deepRoute);
    expect(view.container.textContent).toMatch(/zoom 100%/);
    expect(view.container.textContent).toMatch(/showing files/);
    expect(deepMarks()).toEqual([]);
  });

  it('is fetched ONCE, on the first zoom past the cluster threshold', async () => {
    const { view, calls } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    expect(view.container.textContent).toMatch(
      new RegExp(`zoom ${Math.round(LOD_CLUSTER_SCALE * 100)}%`),
    );
    expect(calls.filter((c) => c === deepRoute).length).toBe(1);

    // Zooming deeper, out, and in again reuses the one fetched payload.
    reveal(view);
    await waitFor(() => expect(view.container.textContent).toMatch(/showing symbols/));
    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(view.container.textContent).toMatch(/zoom 100%/));
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    expect(calls.filter((c) => c === deepRoute).length).toBe(1);
  });
});

// --- 2. the three levels ------------------------------------------------------

describe('semantic zoom — three levels, each from a real field', () => {
  it('opens real (file, cluster) groups at the mid level, named from the payload', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    expect(baseNodes().length).toBe(memoryGraphAvailable.nodes.length);

    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    expect(deepMarks().every((m) => m.getAttribute('data-deep-kind') === 'cluster')).toBe(true);
    // Every cluster mark names a real (source_file, community_id) pair.
    for (const mark of deepMarks()) {
      const file = mark.getAttribute('data-deep-file') ?? '';
      const community = mark.getAttribute('data-deep-community') ?? '';
      expect(
        DEEP_NODE_ROWS.some((row) => row[3] === file && row[5] === community),
      ).toBe(true);
    }
    // The cluster the payload names, and the one it does NOT (id fallback).
    const labels = deepMarks().map((m) => m.getAttribute('aria-label') ?? '');
    expect(labels.some((l) => l.startsWith('Export Pipeline'))).toBe(true);
    // The file each group lives in is outlined and named — real containment.
    const regions = [...document.querySelectorAll('.memory-graph-deep-region')];
    expect(regions.length).toBeGreaterThan(0);
    for (const region of regions) {
      expect(DEEP_NODE_ROWS.some((row) => row[3] === region.getAttribute('data-region'))).toBe(true);
    }
    // The base file/concept nodes are no longer drawn — the canvas shows ONE
    // level at a time, so a count can never describe the wrong layer.
    expect(baseNodes()).toEqual([]);
    // …and the file-projection count line above the canvas says so, instead of
    // reading as a description of the marks now on screen.
    expect(document.querySelector('.memory-graph-list-summary')?.textContent).toMatch(
      /the canvas is zoomed inside them, drawing symbol-level detail/,
    );
  });

  it('opens individual real symbols at the detail level, and returns on zoom out', async () => {
    const { view } = renderGraph(withDeep);
    await zoomToSymbols(view);

    const ids = deepMarks().map((m) => m.getAttribute('aria-label') ?? '');
    expect(ids.length).toBeGreaterThan(0);
    // Every symbol mark is a real payload row, inside the file it belongs to.
    for (const mark of deepMarks()) {
      const file = mark.getAttribute('data-deep-file') ?? '';
      expect(DEEP_NODE_ROWS.some((row) => row[3] === file)).toBe(true);
    }
    expect(ids.some((l) => l.startsWith('export_record'))).toBe(true);
    expect(view.container.textContent).toMatch(/showing symbols/);

    // Zooming back out restores the file projection exactly.
    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(deepMarks()).toEqual([]));
    expect(baseNodes().length).toBe(memoryGraphAvailable.nodes.length);
    expect(view.container.textContent).toMatch(/showing files/);
  });

  it('says so honestly when the viewport holds no deeper structure', async () => {
    const { view } = renderGraph(withDeep);
    await zoomToSymbols(view);
    // Pan the viewport off the open file with the canvas's own arrow-key pan,
    // until nothing with symbol-level structure is left in view.
    const svg = svgEl();
    for (let i = 0; i < 20; i += 1) fireEvent.keyDown(svg, { key: 'ArrowRight' });
    await waitFor(() =>
      expect(view.container.textContent).toMatch(
        /No file with symbol-level structure is inside the viewport/,
      ),
    );
    expect(deepMarks()).toEqual([]);
    expect(view.container.textContent).toMatch(/a statement about the viewport, not about the graph/);
  });
});

// --- 3. screen-space sizing --------------------------------------------------

describe('semantic zoom — nothing grows without bound', () => {
  /** Rendered size of a mark, in px-equivalents: user units × the live scale. */
  const renderedSizes = (scale: number) => {
    const shapes = [...document.querySelectorAll('.memory-graph-node-shape')];
    // A file / cluster mark is a circle (`r`), a symbol mark a square (`width`),
    // a concept a diamond (`points`) — all three are measured here.
    const radii = shapes
      .map((s) => {
        const r = Number(s.getAttribute('r') ?? NaN);
        if (Number.isFinite(r)) return r;
        const width = Number(s.getAttribute('width') ?? NaN);
        if (Number.isFinite(width)) return width / 2;
        const points = (s.getAttribute('points') ?? '').match(/-?[0-9.]+/g) ?? [];
        return points.length > 0 ? Math.abs(Number(points[1])) : NaN;
      })
      .filter((r) => Number.isFinite(r));
    const labels = [...document.querySelectorAll('.memory-graph-node-label')].map((l) =>
      Number(l.getAttribute('font-size') ?? NaN),
    );
    return {
      radii: radii.map((r) => r * scale),
      labels: labels.filter(Number.isFinite).map((f) => f * scale),
    };
  };

  it('keeps base node radii and label sizes CONSTANT on screen from 100% to 2400%', async () => {
    // The deep layer is honestly unavailable here, so the BASE marks stay on
    // screen at every zoom and this measures exactly the reported defect.
    const { view } = renderGraph({
      ...baseRoutes,
      [deepRoute]: { body: memoryGraphDetailUnavailable },
    });
    await view.findByText('Graph', { selector: 'h2' });
    const at100 = renderedSizes(1);
    expect(at100.radii.length).toBeGreaterThan(0);
    expect(at100.labels.length).toBeGreaterThan(0);

    // The third press crosses the first threshold, so the (unavailable) deep
    // layer is requested; awaited here so its degraded state is observed.
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    await waitFor(() =>
      expect(view.container.textContent).toMatch(/Symbol-level detail is unavailable/),
    );

    // 15 presses of the 1.25× control in total reaches the 24× clamp.
    let scale = Math.pow(1.25, 3);
    for (let i = 0; i < 12; i += 1) {
      fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
      scale = Math.min(24, scale * 1.25);
      const measured = renderedSizes(scale);
      // Same set of marks, same rendered sizes — this is the whole fix.
      expect(measured.radii.map((r) => Number(r.toFixed(6)))).toEqual(
        at100.radii.map((r) => Number(r.toFixed(6))),
      );
      for (const label of measured.labels) {
        expect(label).toBeGreaterThanOrEqual(6 - 1e-6);
        expect(label).toBeLessThanOrEqual(18 + 1e-6);
      }
      for (const radius of measured.radii) {
        expect(radius).toBeGreaterThanOrEqual(MIN_MARK_UNITS_AT_SCALE_1 - 1e-6);
        expect(radius).toBeLessThanOrEqual(MAX_MARK_UNITS_AT_SCALE_1 + 1e-6);
      }
    }
    expect(view.container.textContent).toMatch(/zoom 2400%/);
  });

  it('bounds deep marks, labels and strokes the same way', async () => {
    const { view } = renderGraph(withDeep);
    await zoomToSymbols(view);
    const measured = renderedSizes(LOD_SYMBOL_SCALE);
    expect(measured.radii.length).toBeGreaterThan(0);
    for (const radius of measured.radii) {
      expect(radius).toBeGreaterThanOrEqual(MIN_MARK_UNITS_AT_SCALE_1 - 1e-6);
      expect(radius).toBeLessThanOrEqual(MAX_MARK_UNITS_AT_SCALE_1 + 1e-6);
    }
    // Edges keep a legible width instead of thickening with the viewBox.
    for (const edge of deepEdges()) {
      expect(edge.getAttribute('vector-effect')).toBe('non-scaling-stroke');
    }
    // Deeper still: the same marks, the same rendered radii.
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    await waitFor(() => expect(view.container.textContent).toMatch(/zoom 500%/));
    const deeper = renderedSizes(LOD_SYMBOL_SCALE * 1.25);
    expect(deeper.radii.map((r) => Number(r.toFixed(6))).sort()).toEqual(
      measured.radii.map((r) => Number(r.toFixed(6))).sort(),
    );
  });
});

// --- 4. no invented edges, direction preserved -------------------------------

describe('semantic zoom — every drawn line is a real payload edge', () => {
  it('cites the payload row each mid-level line folds, and folds only real ones', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));

    const drawn = deepEdges();
    expect(drawn.length).toBeGreaterThan(0);
    const marks = new Set(deepMarks().map((m) => m.getAttribute('data-deep-file') ?? ''));
    for (const line of drawn) {
      const index = Number(line.getAttribute('data-edge-index'));
      const backing = Number(line.getAttribute('data-edge-backing'));
      expect(DEEP_EDGE_ROWS[index]).toBeDefined();
      expect(backing).toBeGreaterThanOrEqual(1);
      // Its relation values are real, and are the values that row carries.
      const relations = (line.getAttribute('data-edge-relations') ?? '').split(',');
      for (const relation of relations) {
        expect(DEEP_EDGE_ROWS.some((row) => row[2] === relation)).toBe(true);
      }
      expect(relations).toContain(DEEP_EDGE_ROWS[index][2]);
      // Both endpoints are marks on screen: no line into nothing.
      const from = line.getAttribute('data-edge-from') ?? '';
      const to = line.getAttribute('data-edge-to') ?? '';
      expect(marks.has(from.split('\u0000')[0])).toBe(true);
      expect(marks.has(to.split('\u0000')[0])).toBe(true);
    }
    // A reduction can never produce more lines than the rows it reduces.
    expect(drawn.length).toBeLessThanOrEqual(DEEP_EDGE_ROWS.length);
  });

  it('draws one real row per line at the symbol level, with its direction', async () => {
    const { view } = renderGraph(withDeep);
    await zoomToSymbols(view);
    const ids = new Set(
      deepMarks().map((m) => (m.getAttribute('aria-label') ?? '').split(',')[0]),
    );
    const drawn = deepEdges();
    expect(drawn.length).toBeGreaterThan(0);
    for (const line of drawn) {
      const index = Number(line.getAttribute('data-edge-index'));
      const row = DEEP_EDGE_ROWS[index];
      expect(row).toBeDefined();
      expect(line.getAttribute('data-edge-backing')).toBe('1');
      // Direction is the payload's own: from row[0] to row[1], never re-sorted.
      expect(line.getAttribute('data-edge-from')).toBe(DEEP_NODE_ROWS[row[0]][0]);
      expect(line.getAttribute('data-edge-to')).toBe(DEEP_NODE_ROWS[row[1]][0]);
      expect(line.getAttribute('data-edge-relations')).toBe(row[2]);
      expect(line.getAttribute('marker-end')).toBe('url(#graph-deep-arrow)');
      expect(ids.has(DEEP_NODE_ROWS[row[0]][1] as string)).toBe(true);
    }
    // The base layer's lines carry NO arrow: its edges are de-duplicated and
    // undirected, so an arrow there would assert a direction it does not have.
    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(deepEdges()).toEqual([]));
    for (const line of document.querySelectorAll('.memory-graph-edge')) {
      expect(line.getAttribute('marker-end')).toBeNull();
    }
  });
});

// --- 4b. C2: the cluster level does not MISSTATE what it is drawing ---------

describe('semantic zoom — an aggregate line says it is one, perceivably', () => {
  const caption = () => document.querySelector('.graph-canvas-caption')?.textContent ?? '';
  const note = () => document.querySelector('.graph-deep-note')?.textContent ?? '';

  it('never claims the cluster level draws graph objects, and states the real backing count', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));

    // THE DEFECT: this exact sentence used to be printed at BOTH deep levels. At
    // the cluster level neither the marks nor the lines are graph objects — the
    // marks are (file, community) GROUPS and the lines are FOLDS.
    expect(caption()).not.toContain('only the marks and the arrows come from the graph');
    expect(caption()).toContain('GROUP of symbols');
    expect(caption()).toContain('SUMMARISES');
    expect(caption()).toMatch(/one line can stand for several/);

    // The count line states the REAL number of recorded references behind the
    // lines, not the line count dressed up as a relationship count.
    const lines = deepEdges().length;
    const backing = deepEdges().reduce(
      (sum, e) => sum + Number(e.getAttribute('data-edge-backing')),
      0,
    );
    expect(backing).toBeGreaterThan(lines); // the fixture really does fold
    expect(note()).toContain(`${lines} line`);
    expect(note()).toContain(`${backing} recorded reference`);
    expect(note()).not.toMatch(new RegExp(`${lines} relationships? drawn`));
  });

  it('draws an aggregate line so it cannot be mistaken for a 1:1 edge', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(deepEdges().length).toBeGreaterThan(0));

    for (const line of deepEdges()) {
      // Distinct stroke treatment and a DIFFERENT arrowhead — not colour alone.
      expect(line.classList.contains('memory-graph-deep-edge-aggregate')).toBe(true);
      expect(line.getAttribute('marker-end')).toBe('url(#graph-deep-arrow-aggregate)');
    }
    // Both markers are defined, and the aggregate one is hollow (stroke, no fill).
    expect(document.getElementById('graph-deep-arrow')).not.toBeNull();
    expect(document.getElementById('graph-deep-arrow-aggregate')).not.toBeNull();
    expect(
      document.querySelector('.memory-graph-deep-arrowhead-aggregate'),
    ).not.toBeNull();

    // At the SYMBOL level a line is one real row: no aggregate treatment at all.
    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(deepMarks()).toEqual([]));
    await zoomToSymbols(view);
    expect(deepEdges().length).toBeGreaterThan(0);
    for (const line of deepEdges()) {
      expect(line.classList.contains('memory-graph-deep-edge-aggregate')).toBe(false);
      expect(line.getAttribute('marker-end')).toBe('url(#graph-deep-arrow)');
      expect(line.querySelector('title')).toBeNull();
    }
    expect(caption()).toContain('ONE recorded reference');
    expect(caption()).not.toContain('SUMMARISES');
  });

  it('gives every aggregate line a PERCEIVABLE description, not only data- attributes', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(deepEdges().length).toBeGreaterThan(0));

    for (const line of deepEdges()) {
      const backing = Number(line.getAttribute('data-edge-backing'));
      const relations = (line.getAttribute('data-edge-relations') ?? '').split(',');
      // A <title> (the native hover tooltip) AND an aria-label, both saying what
      // the line summarises. The proof used to live only in `data-` attributes,
      // which no reader and no assistive technology can reach.
      const title = line.querySelector('title');
      expect(title).not.toBeNull();
      expect(line.getAttribute('role')).toBe('img');
      const described = line.getAttribute('aria-label') ?? '';
      expect(described).toBe(title!.textContent);
      expect(described).toContain(`${backing} recorded reference`);
      expect(described).toContain('summarised into this one line');
      // The distinct relation kinds it folds are named, in readable form.
      for (const relation of relations) {
        expect(described.toLowerCase()).toContain(
          relation.replace(/_/g, ' ').toLowerCase().slice(0, 6),
        );
      }
      // Both endpoint files are named.
      expect(described).toContain((line.getAttribute('data-edge-from') ?? '').split(' ')[0]);
      expect(described).toContain((line.getAttribute('data-edge-to') ?? '').split(' ')[0]);
    }
  });

  it('explains the fold as TEXT in the pinned cluster panel, reachable from the keyboard', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));

    const mark = deepMarks().find((m) => m.getAttribute('tabindex') === '0') as HTMLElement;
    act(() => mark.focus());
    fireEvent.keyDown(mark, { key: 'Enter' });
    await waitFor(() => expect(document.querySelector('.memory-graph-deep-detail')).not.toBeNull());
    const panel = document.querySelector('.memory-graph-deep-detail') as HTMLElement;
    const text = panel.textContent ?? '';
    // The two halves of the fold, in words, where a keyboard user reads detail:
    // what is counted but not drawn, and what is summarised into a line.
    expect(text).toMatch(/counted, not\s+drawn as a line at cluster zoom/);
    expect(text).toMatch(/summarised into the dashed lines between\s+cluster marks/);
    expect(text).toMatch(/one such line can stand for several recorded references/);
  });
});

// --- 5. hover, keyboard focus, selection ------------------------------------

describe('semantic zoom — hover and keyboard focus are the same affordance', () => {
  const tooltip = () => document.querySelector('[data-canvas-tooltip]');

  it('describes a mark on hover, and identically on keyboard focus', async () => {
    const { view } = renderGraph(withDeep);
    await zoomToSymbols(view);
    const mark = deepMarks().find((m) =>
      (m.getAttribute('aria-label') ?? '').startsWith('export_record'),
    ) as SVGGElement;

    expect(tooltip()).toBeNull();
    fireEvent.pointerEnter(mark);
    const hovered = tooltip()!;
    expect(hovered).not.toBeNull();
    const hoverText = hovered.textContent ?? '';
    // Human-readable, and not a raw dump: label, kind, cluster, connection
    // count, source path + line, relationship summary.
    expect(hoverText).toContain('export_record');
    expect(hoverText).toContain('code node');
    expect(hoverText).toContain('Export Pipeline');
    expect(hoverText).toMatch(/4 recorded relationships/);
    expect(hoverText).toContain('src/fake_mod.py L20');
    expect(hoverText).toMatch(/Imports/);
    fireEvent.pointerLeave(mark);
    expect(tooltip()).toBeNull();

    // KEYBOARD EQUIVALENCE: focus alone produces the same description.
    fireEvent.focus(mark);
    expect((tooltip()!.textContent ?? '')).toBe(hoverText);
    fireEvent.blur(mark);
    expect(tooltip()).toBeNull();
  });

  it('pins a mark from the keyboard and reads its real relationships as text', async () => {
    const { view } = renderGraph(withDeep);
    await zoomToSymbols(view);
    const mark = deepMarks().find((m) =>
      (m.getAttribute('aria-label') ?? '').startsWith('export_record'),
    ) as SVGGElement;
    expect(mark.getAttribute('aria-pressed')).toBe('false');

    fireEvent.keyDown(mark, { key: 'Enter' });
    await waitFor(() =>
      expect(document.querySelector('.memory-graph-deep-detail')).not.toBeNull(),
    );
    const panel = document.querySelector('.memory-graph-deep-detail') as HTMLElement;
    const text = panel.textContent ?? '';
    expect(text).toContain('export_record');
    expect(text).toContain('code node');
    expect(text).toContain('src/fake_mod.py');
    expect(text).toContain('L20');
    // Direction is named, not implied by an arrow glyph alone.
    expect(text).toContain('References out');
    expect(text).toContain('Referenced by');
    // The real neighbours of row 1: contains ← mod_root; calls → validate_draft;
    // imports → load_snapshot; imports_from → other_mod.py.
    for (const label of ['fake_mod.py', 'validate_draft', 'load_snapshot', 'other_mod.py']) {
      expect(text).toContain(label);
    }
    // Structural staleness is stated ONCE on the screen, not twice. It used to be
    // printed both under the canvas and again in this panel, which reads as two
    // separate warnings and dilutes both. While the canvas is drawing a deep
    // layer, the canvas carries it and the panel does not.
    const claim = 'does NOT describe the current repository HEAD';
    const occurrences = (view.container.textContent ?? '').split(claim).length - 1;
    expect(occurrences).toBe(1);
    expect(document.querySelector('.graph-deep-staleness')?.textContent).toContain(claim);
    expect(document.querySelector('.memory-graph-deep-detail-provenance')).toBeNull();
    // The panel still carries the leads-not-verdicts boundary, always.
    expect(text).toContain('navigational lead into the project source');

    // Following a relationship pins that node instead.
    fireEvent.click(within(panel).getByRole('button', { name: /validate_draft/ }));
    await waitFor(() =>
      expect(
        (document.querySelector('.memory-graph-deep-detail')?.textContent ?? '').includes(
          'validate_draft',
        ),
      ).toBe(true),
    );
    fireEvent.click(
      within(document.querySelector('.memory-graph-deep-detail') as HTMLElement).getByRole(
        'button',
        { name: 'Unpin' },
      ),
    );
    await waitFor(() => expect(document.querySelector('.memory-graph-deep-detail')).toBeNull());
  });

  /* --- C1: focus SURVIVES every level-of-detail transition ------------------
   *
   * The defect this pins: a level change replaces the whole mark set, React
   * unmounts the focused <g>, and the roving tabindex — which was maintained
   * correctly — says only where focus WOULD go, not where it is. Measured
   * against the real artifact before the fix: focus a cluster, press `+` four
   * times, and `document.activeElement === document.body`. Identical on the way
   * out. A keyboard user zoomed into a cluster and was dumped at the top of the
   * document with no indication anything had happened.
   *
   * The contract now asserted at BOTH crossings, in BOTH directions: focus lands
   * on the mark that CONTAINS (or is contained by) the one it left, and never on
   * <body>.
   */
  const active = () => document.activeElement as HTMLElement;
  const activeIsMark = () => {
    expect(active()).not.toBe(document.body);
    expect(active().getAttribute('role')).toBe('button');
    return active();
  };
  const baseMark = (name: RegExp) =>
    within(svgEl() as unknown as HTMLElement).getByRole('button', { name });

  /**
   * Land on the CLUSTER level centred on `src/fake_mod.py` with the deep payload
   * already fetched, then step back OUT one zoom notch to the file level, keeping
   * that centre. This is the state a reader is actually in when they zoom a file
   * open: the file under the pointer is in the middle of the viewport. (Pressing
   * `+` from the default 100% centre instead moves the window off every file that
   * carries structure, which is a different case — covered separately below.)
   */
  async function atFileLevelCentredOnFakeMod(view: RenderResult) {
    await view.findByText('Graph', { selector: 'h2' });
    selectBaseNode(/^src\/fake_mod\.py, file/);
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    fireEvent.keyDown(svgEl(), { key: '-' });
    await waitFor(() => expect(deepMarks()).toEqual([]));
  }

  it('MOVES focus to the containing cluster across the file → cluster crossing', async () => {
    const { view } = renderGraph(withDeep);
    await atFileLevelCentredOnFakeMod(view);

    const file = baseMark(/^src\/fake_mod\.py, file/);
    act(() => file.focus());
    expect(active()).toBe(file);

    fireEvent.keyDown(active(), { key: '+' });
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));

    // Focus is on a CLUSTER inside the file it was on — not on <body>, and not
    // on whatever mark happens to be first in the plan.
    const landed = activeIsMark();
    expect(landed.classList.contains('memory-graph-deep-node')).toBe(true);
    expect(landed.getAttribute('data-deep-file')).toBe('src/fake_mod.py');
    // The roving tabindex agrees with where focus actually is.
    expect(landed.getAttribute('tabindex')).toBe('0');
    expect(deepMarks().filter((m) => m.getAttribute('tabindex') === '0').length).toBe(1);
  });

  it('MOVES focus into the same cluster across the cluster → symbol crossing, and back OUT again', async () => {
    const { view } = renderGraph(withDeep);
    await atFileLevelCentredOnFakeMod(view);
    act(() => baseMark(/^src\/fake_mod\.py, file/).focus());

    fireEvent.keyDown(active(), { key: '+' }); // → cluster
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    const community = activeIsMark().getAttribute('data-deep-community');

    // 175% → … → 427%: crosses LOD_SYMBOL_SCALE.
    for (let i = 0; i < 4; i += 1) fireEvent.keyDown(active(), { key: '+' });
    await waitFor(() =>
      expect(deepMarks().every((m) => m.getAttribute('data-deep-kind') === 'symbol')).toBe(true),
    );
    const symbol = activeIsMark();
    expect(symbol.getAttribute('data-deep-kind')).toBe('symbol');
    expect(symbol.getAttribute('data-deep-file')).toBe('src/fake_mod.py');
    // Containment, not proximity: the symbol belongs to the cluster left behind.
    expect(symbol.getAttribute('data-deep-community')).toBe(community);

    // ZOOM OUT, symbol → cluster: back to the cluster that symbol belongs to.
    fireEvent.keyDown(active(), { key: '-' });
    await waitFor(() =>
      expect(deepMarks().every((m) => m.getAttribute('data-deep-kind') === 'cluster')).toBe(true),
    );
    expect(activeIsMark().getAttribute('data-deep-community')).toBe(community);

    // ZOOM OUT, cluster → file: back to the file the cluster lived in.
    for (let i = 0; i < 4; i += 1) fireEvent.keyDown(active(), { key: '-' });
    await waitFor(() => expect(deepMarks()).toEqual([]));
    expect(activeIsMark().getAttribute('aria-label')).toMatch(/^src\/fake_mod\.py, file/);
  });

  it('does NOT steal focus when no mark held it', async () => {
    const { view } = renderGraph(withDeep);
    await atFileLevelCentredOnFakeMod(view);
    // Nothing on the canvas has focus — the reader is driving the toolbar. A
    // level change must then leave focus exactly where the browser put it and
    // must not yank it onto a mark: focus restoration is for focus that was
    // genuinely DESTROYED, never a general "grab the canvas" behaviour.
    (document.activeElement as HTMLElement | null)?.blur?.();
    expect(active()).toBe(document.body);
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    expect(active()).toBe(document.body);
    // …and the roving tabindex is still correct, so Tab still reaches the layer.
    expect(deepMarks().filter((m) => m.getAttribute('tabindex') === '0').length).toBe(1);

    // Same for a mark that was focused and then abandoned: the armed request is
    // disarmed as soon as focus leaves it, so a later set change cannot yank it.
    const mark = deepMarks().find((m) => m.getAttribute('tabindex') === '0') as HTMLElement;
    act(() => mark.focus());
    fireEvent.keyDown(mark, { key: '+' }); // arms the request, stays at cluster level
    await waitFor(() => expect(view.container.textContent).toMatch(/zoom 219%/));
    act(() => mark.blur());
    expect(active()).toBe(document.body);
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    await waitFor(() => expect(view.container.textContent).toMatch(/showing symbols/));
    expect(active()).toBe(document.body);
  });

  it('never leaves focus on <body> when the crossing has no counterpart mark', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    // COLD path, and the hard case: the deep payload is fetched DURING this
    // crossing (so the mark set is replaced a render later than the zoom), and
    // the default centre leaves no file with structure in the window at 195%, so
    // there is no counterpart mark to move to at all. The canvas — always mounted
    // and focusable — is where focus must land.
    const file = baseMark(/^src\/fake_mod\.py, file/);
    act(() => file.focus());
    for (let i = 0; i < 3; i += 1) fireEvent.keyDown(active(), { key: '+' });
    await waitFor(() => expect(view.container.textContent).toMatch(/showing clusters|zoom 195%/));
    await waitFor(() => expect(active()).not.toBe(document.body));
    expect(active() === (svgEl() as unknown as HTMLElement) || active().getAttribute('role') === 'button').toBe(
      true,
    );
  });

  it('gives every deep mark a real focus stop, with a roving tabindex', async () => {
    const { view } = renderGraph(withDeep);
    await zoomToSymbols(view);
    const marks = deepMarks();
    expect(marks.length).toBeGreaterThan(1);
    for (const mark of marks) {
      expect(mark.getAttribute('role')).toBe('button');
      expect(mark.getAttribute('tabindex')).toBeTruthy();
      expect(mark.getAttribute('aria-label')).toBeTruthy();
    }
    expect(marks.filter((m) => m.getAttribute('tabindex') === '0').length).toBe(1);

    const first = marks.find((m) => m.getAttribute('tabindex') === '0') as HTMLElement;
    // A real focus() call, wrapped: focusing a mark shows its description, which
    // is a state update — the same path a Tab press takes.
    act(() => first.focus());
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    expect(document.activeElement).not.toBe(first);
    expect((document.activeElement as HTMLElement).getAttribute('role')).toBe('button');
    // Zoom keys still work while a deep mark holds focus, as at the file level.
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: '-' });
    await waitFor(() => expect(view.container.textContent).toMatch(/zoom 320%/));
  });
});

// --- 5b. I3: a level change is ANNOUNCED, once -------------------------------

describe('semantic zoom — level changes reach a screen reader', () => {
  /** The canvas's single polite status region. */
  const statusRegion = () =>
    [...document.querySelectorAll('[role="status"]')].find((el) =>
      el.classList.contains('memory-graph-visually-hidden'),
    ) as HTMLElement;
  const announced = () => statusRegion()?.textContent ?? '';

  it('announces nothing on arrival — the state you land in is not news', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    expect(statusRegion()).not.toBeUndefined();
    expect(announced()).toBe('');
  });

  it('announces each level exactly once, and says what that level draws', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });

    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    // The wording matches what the level actually is — a group and a summary, not
    // "the marks and the arrows come from the graph".
    expect(announced()).toContain('Cluster detail');
    expect(announced()).toContain('group of symbols');
    expect(announced()).toContain('summarises the references');
    // ONE announcement: the text is one node, replaced, not appended to.
    expect(statusRegion().children).toHaveLength(0);

    reveal(view);
    await waitFor(() => expect(view.container.textContent).toMatch(/showing symbols/));
    expect(announced()).toContain('Symbol detail');
    expect(announced()).toContain('one recorded reference');

    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(deepMarks()).toEqual([]));
    expect(announced()).toContain('The file projection');
    expect(announced()).toContain('No symbol-level detail is drawn');
  });

  it('does NOT re-announce while panning or zooming inside one level', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    const atCluster = announced();
    expect(atCluster).toContain('Cluster detail');
    const node = statusRegion().firstChild;

    // Three zoom steps and two pans that all stay inside the cluster level: the
    // live region's text node must be untouched, or every arrow-key press would
    // speak. (The counts note DOES change here — which is exactly why the counts
    // are deliberately not in the region.)
    for (let i = 0; i < 3; i += 1) fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    for (let i = 0; i < 2; i += 1) fireEvent.keyDown(svgEl(), { key: 'ArrowRight' });
    await waitFor(() => expect(view.container.textContent).toMatch(/zoom 342%/));
    expect(deepMarks().length).toBeGreaterThan(0);
    expect(announced()).toBe(atCluster);
    expect(statusRegion().firstChild).toBe(node);

    // Panning right OFF every file with structure is a real state change, and it
    // IS announced — silence there would leave a keyboard user panning into an
    // empty canvas with no signal at all.
    for (let i = 0; i < 30; i += 1) fireEvent.keyDown(svgEl(), { key: 'ArrowRight' });
    await waitFor(() => expect(deepMarks()).toEqual([]));
    expect(announced()).toContain('Nothing is drawn at this zoom');
  });

  it('announces the honest degraded and suspended states too', async () => {
    const { view } = renderGraph({
      ...baseRoutes,
      [deepRoute]: { body: memoryGraphDetailUnavailable },
    });
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(announced()).toMatch(/unavailable in this deployment/));
    expect(announced()).toContain('stays on the file projection');
    // There is exactly ONE status region on the canvas — the loading note's
    // separate `role="status"` was folded into this one.
    expect(document.querySelectorAll('[role="status"]').length).toBe(1);
  });
});

// --- 6. filters, focus, and Browse ------------------------------------------

describe('semantic zoom — the deeper layers inherit the surface they sit under', () => {
  it('only opens files the active filters leave on the canvas', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    const filesBefore = new Set(deepMarks().map((m) => m.getAttribute('data-deep-file')));
    // Reveal Detail centres on the nearest node, so this is the file it opened.
    expect(filesBefore.has('src/fake_mod.py')).toBe(true);

    // A search that leaves only other_mod.py on the canvas must close the
    // clusters of the file it filtered out — the deeper layers only ever open
    // files the base layer is still showing.
    fireEvent.change(view.getByLabelText('Search graph nodes'), { target: { value: 'other_mod' } });
    await waitFor(() =>
      expect(
        new Set(deepMarks().map((m) => m.getAttribute('data-deep-file'))).has('src/fake_mod.py'),
      ).toBe(false),
    );
    for (const mark of deepMarks()) {
      expect(mark.getAttribute('data-deep-file')).toBe('src/other_mod.py');
    }
  });

  it('keeps the file projection while a path or neighbourhood focus is active, and says why', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));

    fireEvent.click(view.getByRole('button', { name: 'Find a Path' }));
    fireEvent.change(view.getByLabelText('From'), { target: { value: 'src/fake_mod.py' } });
    fireEvent.change(view.getByLabelText('To'), { target: { value: 'src/other_mod.py' } });
    fireEvent.click(view.getByRole('button', { name: 'Find Path' }));
    // Finding a path FRAMES the route, which on this layout lands back below the
    // first threshold — so the level is stepped up again explicitly, with the
    // focus still active.
    await waitFor(() => expect(deepMarks()).toEqual([]));
    reveal(view);

    await waitFor(() => expect(deepMarks()).toEqual([]));
    expect(view.container.textContent).toMatch(
      /A neighbourhood or path focus is active, so the canvas keeps the file projection/,
    );
    expect(view.container.textContent).toMatch(/showing files \(focus active\)/);
    expect(baseNodes().length).toBeGreaterThan(0);
  });

  /* --- I4: Browse is the accessible COMPLEMENT, not a second-class fallback ---
   *
   * The defect: the deep payload was fetched only when the CANVAS crossed a zoom
   * threshold (`deepNeeded` required `mode === 'explore'`), so a reader who
   * entered Browse directly never fetched it — measured: 0 deep notes, 0 per-row
   * counts — and even once populated Browse offered per-file COUNTS only, with no
   * symbol list and no way to select a symbol. `GraphDeepDetail` was therefore
   * reachable only through a canvas interaction, which violates both "no
   * pointer-only graph access" and "Browse remains the exact accessible textual
   * complement to Graph Explore".
   */
  it('offers its OWN way into the deep layer, and does not fetch it unasked', async () => {
    const { view, calls } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    fireEvent.click(view.getByRole('radio', { name: 'Browse' }));

    // Still lazy: entering Browse does not pull the ~500 kB artifact by itself.
    expect(calls).not.toContain(deepRoute);
    const load = view.getByRole('button', { name: 'Load Symbol-Level Detail' });
    // …and it says what it will do before doing it.
    expect(document.querySelector('.memory-graph-list-deepload')?.textContent).toMatch(
      /separate, larger artifact, so it is fetched only when asked for/,
    );

    fireEvent.click(load);
    await waitFor(() =>
      expect(document.querySelectorAll('.memory-graph-list-deepcount').length).toBeGreaterThan(0),
    );
    expect(calls.filter((c) => c === deepRoute).length).toBe(1);
    expect(view.queryByRole('button', { name: 'Load Symbol-Level Detail' })).toBeNull();
    // Browse gained the LAYER, not a viewport.
    expect(view.queryByRole('button', { name: 'Reveal Detail' })).toBeNull();
    expect(view.queryByRole('button', { name: 'Zoom in' })).toBeNull();
  });

  it('reaches a symbol and its full detail from Browse alone, with no canvas gesture', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    fireEvent.click(view.getByRole('radio', { name: 'Browse' }));
    fireEvent.click(view.getByRole('button', { name: 'Load Symbol-Level Detail' }));
    await waitFor(() =>
      expect(document.querySelectorAll('.memory-graph-list-deepcount').length).toBeGreaterThan(0),
    );
    // No canvas exists in Browse at all, so nothing below can be a canvas gesture.
    expect(document.querySelector('.memory-graph-svg')).toBeNull();

    // The row's count is a real disclosure BUTTON, not static text.
    const toggle = view.getByRole('button', { name: /4 symbols · 2 clusters/ });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const list = document.getElementById(toggle.getAttribute('aria-controls') ?? '');
    expect(list).not.toBeNull();

    // Every symbol of that file, as text: kind, cluster, line, relationship count.
    const symbol = within(list as HTMLElement).getByRole('button', { name: /export_record/ });
    expect(symbol.textContent).toContain('code');
    expect(symbol.textContent).toContain('Export Pipeline');
    expect(symbol.textContent).toContain('L20');
    expect(symbol.textContent).toMatch(/4 recorded relationships/);

    // Selecting it opens the SHARED deep detail panel — the same component the
    // canvas opens, with the relationships split by direction.
    expect(symbol.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(symbol);
    await waitFor(() => expect(document.querySelector('.memory-graph-deep-detail')).not.toBeNull());
    const panel = document.querySelector('.memory-graph-deep-detail') as HTMLElement;
    expect(panel.textContent).toContain('export_record');
    expect(panel.textContent).toContain('References out');
    expect(panel.textContent).toContain('Referenced by');
    expect(
      view.getByRole('button', { name: /export_record/, pressed: true }),
    ).not.toBeNull();
    // Toggling it off again needs no Clear control to hunt for.
    fireEvent.click(symbol);
    await waitFor(() => expect(document.querySelector('.memory-graph-deep-detail')).toBeNull());
  });

  it('degrades honestly in Browse when the layer is unavailable', async () => {
    const { view } = renderGraph({
      ...baseRoutes,
      [deepRoute]: { body: memoryGraphDetailUnavailable },
    });
    await view.findByText('Graph', { selector: 'h2' });
    fireEvent.click(view.getByRole('radio', { name: 'Browse' }));
    fireEvent.click(view.getByRole('button', { name: 'Load Symbol-Level Detail' }));
    await waitFor(() =>
      expect(document.querySelector('.memory-graph-list-deepnote.advisory')).not.toBeNull(),
    );
    const note = document.querySelector('.memory-graph-list-deepnote.advisory') as HTMLElement;
    expect(note.textContent).toContain('the deployment ships no symbol-level artifact');
    expect(note.textContent).toMatch(/nothing was aggregated, estimated or stood in for/);
    expect(document.querySelectorAll('.memory-graph-list-deepcount')).toHaveLength(0);
  });

  it('reflects the deeper structure in Browse as text, without gaining a viewport', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));

    fireEvent.click(view.getByRole('radio', { name: 'Browse' }));
    const list = document.querySelector('.memory-graph-list') as HTMLElement;
    expect(list.textContent).toMatch(/8 symbol-level nodes are recorded inside 3 of the 5 listed/);
    const counts = [...list.querySelectorAll('.memory-graph-list-deepcount')].map(
      (c) => c.textContent ?? '',
    );
    // Per-row counts, from the payload's own groups: 4 / 2 / 2 symbols.
    expect(counts.some((c) => c.includes('4 symbols · 2 clusters'))).toBe(true);
    expect(counts.some((c) => c.includes('2 symbols · 1 cluster'))).toBe(true);
    // Browse still has no viewport controls of its own.
    expect(view.queryByRole('button', { name: 'Reveal Detail' })).toBeNull();
  });
});

// --- 7. degraded path + staleness -------------------------------------------

describe('semantic zoom — honesty when the layer is missing or stale', () => {
  it('degrades to the file projection when the deep layer is unavailable', async () => {
    const { view } = renderGraph({
      ...baseRoutes,
      [deepRoute]: { body: memoryGraphDetailUnavailable },
    });
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() =>
      expect(view.container.textContent).toMatch(
        /Symbol-level detail is unavailable in this deployment/,
      ),
    );
    expect(view.container.textContent).toMatch(/the deployment ships no symbol-level artifact/);
    expect(view.container.textContent).toMatch(
      /nothing was aggregated, estimated or stood in for the missing structure/,
    );
    // The base projection is intact and still interactive.
    expect(deepMarks()).toEqual([]);
    expect(baseNodes().length).toBe(memoryGraphAvailable.nodes.length);
    expect(view.container.textContent).toMatch(/showing files \(no deeper layer\)/);
    // No staleness claim is made when no provenance was received.
    expect(document.querySelector('.graph-deep-staleness')).toBeNull();
  });

  it('degrades honestly when the request itself fails', async () => {
    const { view } = renderGraph(baseRoutes); // the deep route is not stubbed
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() =>
      expect(view.container.textContent).toMatch(/the request for it did not complete/),
    );
    expect(baseNodes().length).toBe(memoryGraphAvailable.nodes.length);
  });

  it('states the structural staleness ON the canvas surface, unsoftened', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() =>
      expect(document.querySelector('.graph-deep-staleness')).not.toBeNull(),
    );
    const note = document.querySelector('.graph-deep-staleness') as HTMLElement;
    const text = note.textContent ?? '';
    expect(text).toContain(DEEP_BUILT_AT_COMMIT.slice(0, 7));
    expect(text).toContain('point-in-time index');
    expect(text).toContain('does NOT describe the current repository HEAD');
    expect(text).toContain('including work that exists in the running app');
    expect(text.toLowerCase()).not.toContain('slightly');
    expect(note.getAttribute('data-staleness-commit')).toBe(DEEP_BUILT_AT_COMMIT);
    // It is on the surface, not only inside the About This Graph dialog.
    expect(note.closest('[role="dialog"]')).toBeNull();

    // …and it does NOT outlive the layer it describes. Back at the file level no
    // deep layer is drawn, so the canvas makes no claim about one. It used to
    // persist for the rest of the session once the payload had been fetched.
    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(deepMarks()).toEqual([]));
    expect(document.querySelector('.graph-deep-staleness')).toBeNull();
    expect(view.container.textContent).not.toContain('point-in-time index');
  });

  it('adds the served-set clause when the payload reports the path set has moved (M2)', async () => {
    // `served_set_consistency` is a second, INDEPENDENT axis: the structure's
    // commit and whether the served file set still matches it. The backend
    // measures `current` today, so this clause had no coverage at all — it is
    // driven from a fixture here rather than left unexercised.
    const { view } = renderGraph({
      ...baseRoutes,
      [deepRoute]: { body: memoryGraphDetailStaleServedSet },
    });
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(document.querySelector('.graph-deep-staleness')).not.toBeNull());
    const text = document.querySelector('.graph-deep-staleness')?.textContent ?? '';
    // Both axes, in one place, neither collapsed into the other.
    expect(text).toContain('does NOT describe the current repository HEAD');
    expect(text).toContain('The served file set has also changed since then');
    expect(text).toContain('some files here may no longer be served');
  });

  it('makes no served-set claim when the payload reports the path set is current', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    reveal(view);
    await waitFor(() => expect(document.querySelector('.graph-deep-staleness')).not.toBeNull());
    expect(document.querySelector('.graph-deep-staleness')?.textContent).not.toContain(
      'The served file set has also changed',
    );
  });

  it('clears the pinned deep mark when the canvas zooms back out of the layer', async () => {
    // The orchestrator's cross-unit ruling: deep-only UI must not persist when no
    // deep layer is drawn. The pinned-symbol panel — and Unit G's deep suggested
    // commands, which read the same `deepSelectedId` — used to keep describing a
    // symbol that is not on screen at 100% zoom.
    const { view } = renderGraph(withDeep);
    await zoomToSymbols(view);
    const mark = deepMarks().find((m) =>
      (m.getAttribute('aria-label') ?? '').startsWith('export_record'),
    ) as SVGGElement;
    fireEvent.keyDown(mark, { key: 'Enter' });
    await waitFor(() => expect(document.querySelector('.memory-graph-deep-detail')).not.toBeNull());

    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(deepMarks()).toEqual([]));
    expect(document.querySelector('.memory-graph-deep-detail')).toBeNull();

    // Browse is NOT affected: nothing is drawn there at any zoom, and the panel
    // is Browse's textual route into the layer, so clearing there would remove a
    // keyboard path rather than a stale claim.
    await zoomToSymbols(view);
    fireEvent.keyDown(
      deepMarks().find((m) =>
        (m.getAttribute('aria-label') ?? '').startsWith('export_record'),
      ) as SVGGElement,
      { key: 'Enter' },
    );
    await waitFor(() => expect(document.querySelector('.memory-graph-deep-detail')).not.toBeNull());
    fireEvent.click(view.getByRole('radio', { name: 'Browse' }));
    expect(document.querySelector('.memory-graph-deep-detail')).not.toBeNull();
    // …and there the panel DOES carry the staleness sentence, because no canvas
    // is stating it.
    expect(document.querySelector('.memory-graph-deep-detail-provenance')?.textContent).toContain(
      'does NOT describe the current repository HEAD',
    );
  });
});

// --- 8. bounded DOM, and the viewport controls ------------------------------

describe('semantic zoom — a bounded number of elements, and the same controls', () => {
  /*
   * The element BOUND is asserted at real payload size in
   * `graph-real-artifact.test.tsx` — against the committed 2,612-row artifact,
   * where the caps can actually bite. It used to be asserted here, against this
   * file's EIGHT-row fixture, which could never reach any cap and therefore
   * proved nothing; the 1,263 elements reported alongside it were also not
   * reproducible (the real figures are 968 file / 557 cluster / 985 symbol).
   *
   * What this fixture is good for is the SHAPE of the render: one level at a
   * time, and no stray element left behind by the level that just unmounted.
   */
  it('draws exactly one level at a time, leaving nothing from the other behind', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    expect(baseNodes().length).toBe(memoryGraphAvailable.nodes.length);
    expect(deepMarks()).toEqual([]);
    expect(document.querySelectorAll('.memory-graph-deep-region')).toHaveLength(0);

    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    expect(baseNodes()).toEqual([]);
    expect(document.querySelectorAll('.memory-graph-edges')).toHaveLength(0);

    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(deepMarks()).toEqual([]));
    await zoomToSymbols(view);
    expect(baseNodes()).toEqual([]);
    expect(deepMarks().every((m) => m.getAttribute('data-deep-kind') === 'symbol')).toBe(true);

    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(baseNodes().length).toBe(memoryGraphAvailable.nodes.length));
    expect(deepMarks()).toEqual([]);
    expect(deepEdges()).toEqual([]);
    expect(document.querySelectorAll('.memory-graph-deep-region')).toHaveLength(0);
  });

  it('keeps Fit to View and Reset View working at the deepest level', async () => {
    const { view } = renderGraph(withDeep);
    await zoomToSymbols(view);
    const before = svgEl().getAttribute('viewBox');

    fireEvent.click(view.getByRole('button', { name: 'Fit to View' }));
    await waitFor(() => expect(svgEl().getAttribute('viewBox')).not.toBe(before));

    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(view.container.textContent).toMatch(/zoom 100%/));
    expect(baseNodes().length).toBe(memoryGraphAvailable.nodes.length);
    // Reveal Detail is disabled only at the deepest level, never hidden.
    expect(view.getByRole('button', { name: 'Reveal Detail' })).not.toBeDisabled();
    for (let i = 0; i < 2; i += 1) reveal(view);
    await waitFor(() =>
      expect(view.container.textContent).toMatch(
        new RegExp(`zoom ${Math.round(LOD_SYMBOL_SCALE * 100)}%`),
      ),
    );
    expect(view.getByRole('button', { name: 'Reveal Detail' })).toBeDisabled();
  });
});

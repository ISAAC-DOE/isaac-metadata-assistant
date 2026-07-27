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
      expect(marks.has(from.split(' ')[0])).toBe(true);
      expect(marks.has(to.split(' ')[0])).toBe(true);
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
    // Structural staleness is repeated where the detail is read.
    expect(text).toContain('does NOT describe the current repository HEAD');

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
  });
});

// --- 8. bounded DOM, and the viewport controls ------------------------------

describe('semantic zoom — a bounded number of elements, and the same controls', () => {
  it('draws a few hundred elements at most, at every level', async () => {
    const { view } = renderGraph(withDeep);
    await view.findByText('Graph', { selector: 'h2' });
    const countAll = () => svgEl().querySelectorAll('*').length;
    const atFile = countAll();

    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    const atCluster = countAll();

    // Back to the file projection first: a base node has to be selectable to
    // anchor the descent to the symbol level.
    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(deepMarks()).toEqual([]));
    await zoomToSymbols(view);
    const atSymbol = countAll();

    for (const count of [atFile, atCluster, atSymbol]) {
      expect(count).toBeGreaterThan(0);
      expect(count).toBeLessThan(1200);
    }
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

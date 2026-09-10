/*
 * EVERY NUMBER THE EXPERIMENT GRAPH PUBLISHES MUST SAY WHAT IT COUNTS.
 *
 * MEASURED DEFECT, in Chromium at `?view=graph` on a record created over HTTP,
 * all four figures inside one ~400px band:
 *
 *   [data-testid=expgraph-counts]            "9 of 22 nodes drawn · 8 of 21 relationships"
 *   sum of the SHOW chip counts               21
 *   .expgraph-canvas text                      8
 *   the `Workflow Step 5` chip                 above a canvas holding ONE workflow-step node
 *
 * Each was correct about a DIFFERENT set — the whole graph, the whole graph
 * minus the unfilterable anchor, the labels actually placed, and the drawn
 * subset — and not one of them said which. The node with no label
 * (`NO_MEASUREMENT_SERIES` in the reviewed instance) read as a rendering fault
 * rather than as `placedLabelIds` deliberately dropping a colliding glyph, and
 * nothing on the surface named the withheld nodes or how to reach them.
 *
 * What is pinned here:
 *
 *   1. every published figure is traced to the MODEL VALUE it claims to be, and
 *      the drawn figures additionally to the DOM they describe;
 *   2. `drawTally`'s four categories are an exact PARTITION of the node total,
 *      so "not drawn" is accounted for rather than implied by subtraction;
 *   3. the chip row states its own scope, and states its own arithmetic gap
 *      rather than leaving a reader to notice the sum is short;
 *   4. every DRAWN node is named — by a `<text>` label, or, when the label was
 *      dropped for collision, by an SVG `<title>` — so the sentence promising
 *      "hover or select the node to read its name" is true.
 *
 * Nothing here asserts a hand-written number. Each expectation is computed from
 * `buildExperimentGraph` / `drawTally` and compared with what rendered, which is
 * the property that was missing: the old single line agreed with no source.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { fireEvent, render, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExperimentGraphPanel } from '../screens/graph/ExperimentGraphPanel';
import {
  MAX_VISIBLE_NODES,
  buildExperimentGraph,
  drawTally,
  initialExperimentGraphState,
  visibleEdges,
  visibleNodeIds,
  type ExperimentGraph,
  type ExperimentGraphViewState,
} from '../lib/experimentGraph';
import {
  experimentGraphBundle,
  exportedExperimentGraphBundle,
  stressExperimentGraphBundle,
} from '../test/experimentGraphFixtures';
import type { ExperimentGraphBundle } from '../lib/types';

vi.setConfig({ testTimeout: 30000 });

afterEach(() => {
  vi.unstubAllGlobals();
});

/** The panel alone — no router-level record shell, no fetch: this file is about
 *  the arithmetic between the model and the markup, and nothing else. */
function renderPanel(bundle: ExperimentGraphBundle = experimentGraphBundle()): RenderResult {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ExperimentGraphPanel bundle={bundle} readInScope={null} currentScope={null} />
    </MemoryRouter>,
  );
}

/** The same graph the panel built, for comparison against what it published. */
function modelGraph(bundle: ExperimentGraphBundle = experimentGraphBundle()): ExperimentGraph {
  const result = buildExperimentGraph(bundle, { readIn: null, current: null });
  if (!result.ok) throw new Error(`fixture bundle refused: ${result.reason}`);
  return result.graph;
}

const text = (view: RenderResult, id: string) =>
  view.getByTestId(id).textContent?.replace(/\s+/g, ' ').trim() ?? '';

/** Every integer in a published sentence, in order. */
const numbersIn = (s: string): number[] => (s.match(/\d+/g) ?? []).map(Number);

// ------------------------------------------------------- 1. figure -> source

describe('each published figure names the set it counts', () => {
  it("the headline is the RECORD's cardinality, from the built graph", () => {
    const view = renderPanel();
    const graph = modelGraph();
    const line = text(view, 'expgraph-count-total');

    expect(line).toContain("In this record's graph");
    expect(numbersIn(line)).toEqual([graph.nodes.length, graph.edges.length]);
    // It is NOT the drawn figure, which is the conflation being removed.
    expect(graph.nodes.length).toBeGreaterThan(
      visibleNodeIds(initialExperimentGraphState(graph), graph).length,
    );
  });

  it('the drawn figure is the DOM, and the model, and says so', () => {
    const view = renderPanel();
    const graph = modelGraph();
    const state = initialExperimentGraphState(graph);
    const drawnNodes = view.container.querySelectorAll('.expgraph-node').length;
    const drawnEdges = view.container.querySelectorAll('.expgraph-edge').length;

    // The model, the markup and the sentence, all three.
    expect(drawnNodes).toBe(visibleNodeIds(state, graph).length);
    expect(drawnNodes).toBe(drawTally(state, graph).drawn);
    expect(drawnEdges).toBe(visibleEdges(visibleNodeIds(state, graph), graph).length);

    const line = text(view, 'expgraph-count-drawn');
    expect(line).toContain('Drawn on the canvas now');
    expect(numbersIn(line)).toEqual([drawnNodes, drawnEdges]);
    // NOT attributed to zoom: `visibleNodeIds` never reads `state.view.scale`.
    expect(line).not.toMatch(/zoom/i);
  });

  it('the label figure is the labels actually placed, WITH a collision present', () => {
    /*
     * NOT WRITTEN AS `if (placed < drawn) { ... }`. That form reads as a pass on
     * a fixture where every label happens to fit, which would be a test of
     * nothing on the exact case the defect was about. The default fixture is
     * ASSERTED to contain a collision, so the branch cannot silently stop being
     * exercised; the all-labelled branch gets its own test below.
     */
    const view = renderPanel();
    const placed = view.container.querySelectorAll('.expgraph-canvas text').length;
    const drawnNodes = view.container.querySelectorAll('.expgraph-node').length;
    expect(placed).toBeLessThan(drawnNodes);

    const line = text(view, 'expgraph-count-labels');
    expect(numbersIn(line)).toEqual([placed, drawnNodes, drawnNodes - placed]);
    // The reason is stated, and it is the real one (`placedLabelIds` drops a
    // glyph that would overlap one already placed).
    expect(line).toMatch(/overlap/);
    // And it points at the two ways to read the name anyway, both of which exist.
    expect(line).toMatch(/hover or select/);
    expect(view.container.querySelectorAll('.expgraph-node title').length).toBe(
      drawnNodes - placed,
    );
  });

  it('and says so plainly when nothing collided', () => {
    const view = renderPanel(exportedExperimentGraphBundle());
    const placed = view.container.querySelectorAll('.expgraph-canvas text').length;
    const drawnNodes = view.container.querySelectorAll('.expgraph-node').length;
    expect(placed).toBe(drawnNodes);

    const line = text(view, 'expgraph-count-labels');
    expect(line).toBe(`All ${drawnNodes} drawn nodes carry a visible label.`);
    expect(line).not.toMatch(/overlap/);
    expect(view.container.querySelectorAll('.expgraph-node title').length).toBe(0);
  });

  it('the withheld figure is total minus drawn, itemised by reason', () => {
    const view = renderPanel();
    const graph = modelGraph();
    const tally = drawTally(initialExperimentGraphState(graph), graph);
    const line = text(view, 'expgraph-count-undrawn');
    const missing = tally.total - tally.drawn;

    expect(missing).toBeGreaterThan(0);
    expect(line.startsWith(`${missing} nodes not drawn:`)).toBe(true);
    // The itemisation is compared against the TALLY rather than re-parsed out of
    // the sentence, so a reason whose count happened to equal `MAX_VISIBLE_NODES`
    // (or any other constant in the copy) cannot be mistaken for prose.
    expect(line).toContain(`${tally.notOpened} not opened yet`);
    expect(tally.notOpened).toBe(missing);
    expect(line).not.toContain('hidden by a Show filter');
    expect(line).not.toContain(`${MAX_VISIBLE_NODES}-node limit`);
    // And the reason names the control the reader would use.
    expect(line).toMatch(/select a node and press Enter, or use Expand/);
  });

  it('names the view cap as its own reason when the cap is what is biting', () => {
    const graph = modelGraph(stressExperimentGraphBundle());
    const state: ExperimentGraphViewState = {
      ...initialExperimentGraphState(graph),
      expanded: graph.nodes.map((n) => n.id),
    };
    const tally = drawTally(state, graph);
    expect(tally.overCap).toBeGreaterThan(0);
    expect(tally.drawn).toBe(MAX_VISIBLE_NODES);
    expect(tally.drawn + tally.overCap + tally.notOpened + tally.hiddenByFilter).toBe(
      tally.total,
    );
  });
});

// ------------------------------------------------------------ 2. the partition

describe('drawTally is an exact partition of the node total', () => {
  const partitions = (state: ExperimentGraphViewState, graph: ExperimentGraph) => {
    const t = drawTally(state, graph);
    expect(t.drawn + t.notOpened + t.hiddenByFilter + t.overCap).toBe(t.total);
    expect(t.drawn).toBe(visibleNodeIds(state, graph).length);
    expect(t.notOpened).toBeGreaterThanOrEqual(0);
    expect(t.hiddenByFilter).toBeGreaterThanOrEqual(0);
    expect(t.overCap).toBeGreaterThanOrEqual(0);
    return t;
  };

  it('on first paint', () => {
    const graph = modelGraph();
    const t = partitions(initialExperimentGraphState(graph), graph);
    expect(t.hiddenByFilter).toBe(0);
    expect(t.overCap).toBe(0);
    expect(t.notOpened).toBeGreaterThan(0);
  });

  it('with a kind hidden — the hidden nodes move category, they do not vanish', () => {
    const graph = modelGraph();
    const before = partitions(initialExperimentGraphState(graph), graph);
    const state: ExperimentGraphViewState = {
      ...initialExperimentGraphState(graph),
      hiddenKinds: ['section'],
    };
    const after = partitions(state, graph);
    expect(after.hiddenByFilter).toBe(graph.counts.section);
    expect(after.total).toBe(before.total);
  });

  it('with everything expanded on a large graph — the cap is a category, not a silence', () => {
    const graph = modelGraph(stressExperimentGraphBundle());
    const state: ExperimentGraphViewState = {
      ...initialExperimentGraphState(graph),
      expanded: graph.nodes.map((n) => n.id),
    };
    const t = partitions(state, graph);
    expect(t.drawn).toBe(MAX_VISIBLE_NODES);
    expect(t.overCap).toBeGreaterThan(0);
  });

  it('an exported record, whose graph carries a record node as well', () => {
    const graph = modelGraph(exportedExperimentGraphBundle());
    partitions(initialExperimentGraphState(graph), graph);
  });
});

// ---------------------------------------------------------------- 3. the chips

describe('the SHOW chips state their own scope and their own arithmetic', () => {
  it('says the numbers are per-kind totals, not drawn counts', () => {
    const view = renderPanel();
    const hint = text(view, 'expgraph-kinds-hint');
    expect(hint).toContain("in this record's graph");
    expect(hint).toContain('not how many are drawn');
  });

  it('the stated chip total IS the sum of the rendered chips', () => {
    const view = renderPanel();
    const graph = modelGraph();
    const chipCounts = [...view.container.querySelectorAll('.expgraph-kind-count')].map((el) =>
      Number((el.textContent ?? '').match(/\d+/)?.[0]),
    );
    const chipTotal = chipCounts.reduce((a, b) => a + b, 0);
    const hint = text(view, 'expgraph-kinds-hint');

    // The gap is MEASURED and printed, not reasoned about: on an unexported
    // record it is 1 (the experiment anchor), and on an exported one it is 2 —
    // an earlier draft of this sentence asserted "one less" and was wrong.
    expect(hint).toContain(`total ${chipTotal}, not ${graph.nodes.length}`);
    expect(graph.nodes.length - chipTotal).toBeGreaterThan(0);
  });

  it('an exported record shows the LARGER gap, because it has two unfilterable nodes', () => {
    const view = renderPanel(exportedExperimentGraphBundle());
    const graph = modelGraph(exportedExperimentGraphBundle());
    const chipTotal = [...view.container.querySelectorAll('.expgraph-kind-count')]
      .map((el) => Number((el.textContent ?? '').match(/\d+/)?.[0]))
      .reduce((a, b) => a + b, 0);
    expect(text(view, 'expgraph-kinds-hint')).toContain(
      `total ${chipTotal}, not ${graph.nodes.length}`,
    );
    expect(graph.nodes.length - chipTotal).toBe(2);
  });

  it("a chip's accessible name still CONTAINS its visible text, plus the scope", () => {
    const view = renderPanel();
    const chip = view.container.querySelector('.expgraph-kind-chip') as HTMLElement;
    const name = (chip.textContent ?? '').replace(/\s+/g, ' ').trim();
    // e.g. "Section 6 in this record's graph" — the scope is appended
    // visually-hidden rather than replacing the name with an `aria-label`, so
    // WCAG 2.5.3 label-in-name still holds against the visible "Section" + "6".
    expect(name).toMatch(/^\S.*\d+ in this record's graph$/);
    expect(chip.getAttribute('aria-label')).toBeNull();
  });

  it('hiding a kind moves the count into the withheld sentence', () => {
    const view = renderPanel();
    const graph = modelGraph();
    const chip = [...view.container.querySelectorAll('.expgraph-kind-chip')].find((c) =>
      (c.textContent ?? '').startsWith('Section'),
    ) as HTMLElement;
    const drawnBefore = view.container.querySelectorAll('.expgraph-node').length;

    fireEvent.click(chip);

    const line = text(view, 'expgraph-count-undrawn');
    expect(line).toContain(`${graph.counts.section} hidden by a Show filter above`);
    expect(view.container.querySelectorAll('.expgraph-node').length).toBeLessThan(drawnBefore);
    // The headline is unmoved: hiding a category does not change what the record
    // is made of, and the old single line could not have said that.
    expect(numbersIn(text(view, 'expgraph-count-total'))).toEqual([
      graph.nodes.length,
      graph.edges.length,
    ]);
  });
});

// ------------------------------------------------------------ 4. every node named

describe('a drawn node is never nameless', () => {
  it('each drawn node carries a text label or an SVG title, and an aria-label', () => {
    const view = renderPanel();
    const nodes = [...view.container.querySelectorAll('.expgraph-node')];
    expect(nodes.length).toBeGreaterThan(0);

    for (const node of nodes) {
      const labelled = node.querySelector('text') !== null;
      const titled = node.querySelector('title') !== null;
      expect(
        labelled || titled,
        `node ${node.getAttribute('data-node-id')} has neither a label nor a title`,
      ).toBe(true);
      // Exactly one of the two: a `<title>` beside a visible label would be a
      // duplicate tooltip, and neither is the defect.
      expect(labelled).not.toBe(titled);
      expect(node.getAttribute('aria-label')).toBeTruthy();
    }
  });

  it("the canvas's accessible name carries the same four figures as the visible block", () => {
    const view = renderPanel();
    const aria = view.container
      .querySelector('.expgraph-canvas')!
      .getAttribute('aria-label')!
      .replace(/\s+/g, ' ');
    for (const id of [
      'expgraph-count-total',
      'expgraph-count-drawn',
      'expgraph-count-undrawn',
      'expgraph-count-labels',
    ]) {
      expect(aria).toContain(text(view, id));
    }
  });
});

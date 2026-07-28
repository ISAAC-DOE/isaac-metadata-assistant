import { describe, it, expect } from 'vitest';
import {
  DEEP_HUB_LABEL_COUNT,
  DEEP_LABEL_LIMIT,
  MAX_DEEP_EDGES,
  MAX_DEEP_NODES,
  MAX_DEEP_NEIGHBORS,
  FILE_RADIUS_MAX,
  FILE_RADIUS_MIN,
  clusterKeyOf,
  decodeDeepGraph,
  deepCountsSentence,
  deepFileRadius,
  deepMarkLabelText,
  deepRelationSummary,
  deepRenderPlan,
  deepStaleness,
  placedDeepLabelIds,
  stalenessSentence,
  type DeepIndex,
} from '../lib/graphDeep';
import {
  LOD_CLUSTER_SCALE,
  LOD_SYMBOL_SCALE,
  MAX_MARK_UNITS_AT_SCALE_1,
  MAX_SCALE,
  MIN_MARK_UNITS_AT_SCALE_1,
  MIN_SCALE,
  MARK_UNITS,
  LABEL_UNITS,
  SELECTED_MARK_FACTOR,
  buildGraphIndex,
  graphLodLevel,
  initialGraphViewState,
  nextLodScale,
  screenBoundedUnits,
  visibleNodeIds,
  type GraphIndex,
  type GraphViewState,
} from '../lib/graphModel';
import { memoryGraphAvailable } from '../test/apiFixtures';
import {
  DEEP_BUILT_AT_COMMIT,
  DEEP_EDGE_ROWS,
  DEEP_NODE_ROWS,
  bigDeepPayload,
  memoryGraphDetailAvailable,
  memoryGraphDetailUnavailable,
  memoryGraphDetailUnknownSchema,
} from '../test/graphDeepFixture';

/*
 * P36V.1 Unit F — the deep (symbol-level) layer as a UNIT.
 *
 * The mounted behaviour lives in graph-semantic-zoom.test.tsx; this file pins
 * the three invariants the module exists to hold — no invented nodes, no
 * invented edges, no invented hierarchy — plus the deterministic layout, the
 * level-of-detail thresholds, the screen-space size bounds, and the caps.
 */

const base: GraphIndex = buildGraphIndex(memoryGraphAvailable);
const deep = decodeDeepGraph(memoryGraphDetailAvailable) as DeepIndex;

function viewAt(scale: number, cx = 0, cy = 0): GraphViewState {
  const state = initialGraphViewState();
  return { ...state, view: { cx, cy, scale } };
}

const allVisible = (state: GraphViewState) => visibleNodeIds(state, base);

/** A 200-file base projection to match `bigDeepPayload(200, …)` — the only way to
 *  reach the marks / lines / neighbour caps, which an 8-row fixture cannot. */
const bigBaseIndex = buildGraphIndex({
  ...memoryGraphAvailable,
  nodes: Array.from({ length: 200 }, (_, f) => ({
    id: `synthetic/chain-${String(f).padStart(4, '0')}.py`,
    kind: 'file' as const,
    label: `chain-${f}`,
    file_type: 'code',
    community_id: null,
    community_name: null,
    node_count: 1,
    on_disk: true,
  })),
  edges: Array.from({ length: 199 }, (_, f) => ({
    source: `synthetic/chain-${String(f).padStart(4, '0')}.py`,
    target: `synthetic/chain-${String(f + 1).padStart(4, '0')}.py`,
    relations: ['imports'],
  })),
  communities: [],
});

// --- 1. decoding -------------------------------------------------------------

describe('deep layer — decoding is by CONTRACT, and never repairs a row', () => {
  it('decodes every well-formed row and nothing else', () => {
    expect(deep.nodes.length).toBe(DEEP_NODE_ROWS.length);
    expect(deep.edges.length).toBe(DEEP_EDGE_ROWS.length);
    expect(deep.droppedNodeRows).toBe(0);
    expect(deep.droppedEdgeRows).toBe(0);
    // NO INVENTED NODES: every decoded id is a payload id, and vice versa.
    expect(deep.nodes.map((n) => n.id).sort()).toEqual(
      DEEP_NODE_ROWS.map((r) => r[0] as string).sort(),
    );
  });

  it('resolves the columns by NAME, so an unrecognised contract decodes nothing', () => {
    expect(decodeDeepGraph(memoryGraphDetailUnknownSchema)).toBeNull();
    expect(decodeDeepGraph(memoryGraphDetailUnavailable)).toBeNull();
    expect(decodeDeepGraph(null)).toBeNull();
  });

  it('drops an unusable row instead of guessing, and keeps the surviving indices valid', () => {
    const damaged = decodeDeepGraph({
      ...memoryGraphDetailAvailable,
      nodes: [
        ...DEEP_NODE_ROWS.slice(0, 2),
        [null, 'no id at all', 'code', 'src/fake_mod.py', 'L4', '131'],
        ...DEEP_NODE_ROWS.slice(3),
      ],
      edges: [
        ...DEEP_EDGE_ROWS,
        [0, 999, 'calls'], // endpoint out of range
        [3, 3, 'calls'], // self edge
      ],
    }) as DeepIndex;
    expect(damaged.droppedNodeRows).toBe(1);
    // The two malformed rows, plus the THREE rows that pointed at the dropped
    // node (edges 1, 2 and 3) — dropped, never re-pointed at a nearby node.
    expect(damaged.droppedEdgeRows).toBe(5);
    // Row 3's identity is UNCHANGED by the hole at row 2.
    expect(damaged.byIndex.get(3)?.id).toBe('fake/helper_fn');
    for (const edge of damaged.edges) {
      expect(damaged.byIndex.has(edge.source)).toBe(true);
      expect(damaged.byIndex.has(edge.target)).toBe(true);
    }
  });

  it('counts degree from the real edges and preserves the real relation values', () => {
    expect(deep.byId.get('fake/export_fn')?.degree).toBe(4);
    expect(deep.byId.get('fake/helper_fn')?.degree).toBe(1);
    expect([...deep.relationCounts.entries()].sort()).toEqual([
      ['calls', 2],
      ['contains', 3],
      ['imports', 1],
      ['imports_from', 1],
      ['rationale_for', 1],
    ]);
  });
});

// --- 2. the hierarchy is the DATA's, not ours ---------------------------------

describe('deep layer — the hierarchy comes from real fields only', () => {
  it('groups by source_file (containment) and by community_id INSIDE a file', () => {
    expect(deep.files).toEqual(['docs/fake-note.md', 'src/fake_mod.py', 'src/other_mod.py']);
    expect(deep.byFile.get('src/fake_mod.py')?.length).toBe(4);
    // One file, TWO real communities — a community is not a container of files.
    const clusters = deep.clustersByFile.get('src/fake_mod.py') ?? [];
    expect(clusters.map((c) => c.communityId).sort()).toEqual(['131', '77']);
    for (const cluster of clusters) {
      for (const member of cluster.members) {
        expect(deep.byIndex.get(member)?.sourceFile).toBe('src/fake_mod.py');
        expect(deep.byIndex.get(member)?.communityId).toBe(cluster.communityId);
      }
    }
  });

  it('names a cluster from community_names, and falls back to the id rather than inventing one', () => {
    expect(deep.clusterByKey.get(clusterKeyOf('src/fake_mod.py', '131'))?.name).toBe(
      'Export Pipeline',
    );
    // 55 is absent from community_names — the name stays null; the UI shows the id.
    expect(deep.clusterByKey.get(clusterKeyOf('src/other_mod.py', '55'))?.name).toBeNull();
  });

  it('tallies real internal / external edges per cluster', () => {
    const c131 = deep.clusterByKey.get(clusterKeyOf('src/fake_mod.py', '131'))!;
    const c77 = deep.clusterByKey.get(clusterKeyOf('src/fake_mod.py', '77'))!;
    expect(c131.internalEdges).toBe(1); // edge 0: contains, 131 → 131
    expect(c131.externalEdges).toBe(4); // edges 1, 3, 4, 7
    expect(c77.internalEdges).toBe(1); // edge 2: calls, 77 → 77
    expect(c77.externalEdges).toBe(2); // edges 1, 3
  });
});

// --- 3. deterministic layout --------------------------------------------------

describe('deep layer — the nested layout is deterministic and bounded', () => {
  it('produces byte-identical offsets on a second decode', () => {
    const again = decodeDeepGraph(memoryGraphDetailAvailable) as DeepIndex;
    expect(again.nodes.map((n) => [n.id, n.dx, n.dy])).toEqual(
      deep.nodes.map((n) => [n.id, n.dx, n.dy]),
    );
    expect([...again.fileRadius.entries()]).toEqual([...deep.fileRadius.entries()]);
  });

  it('keeps every symbol inside its own file radius, and the radius inside its bounds', () => {
    for (const file of deep.files) {
      const radius = deep.fileRadius.get(file)!;
      expect(radius).toBeGreaterThanOrEqual(FILE_RADIUS_MIN);
      expect(radius).toBeLessThanOrEqual(FILE_RADIUS_MAX);
      for (const index of deep.byFile.get(file) ?? []) {
        const node = deep.byIndex.get(index)!;
        expect(Math.hypot(node.dx, node.dy)).toBeLessThanOrEqual(radius + 1e-9);
      }
    }
    expect(deepFileRadius(1)).toBe(FILE_RADIUS_MIN);
    expect(deepFileRadius(10_000)).toBe(FILE_RADIUS_MAX);
  });

  it('places a cluster at the centroid of its own members — never at a chosen spot', () => {
    for (const cluster of deep.clusterByKey.values()) {
      const members = cluster.members.map((i) => deep.byIndex.get(i)!);
      const cx = members.reduce((sum, m) => sum + m.dx, 0) / members.length;
      const cy = members.reduce((sum, m) => sum + m.dy, 0) / members.length;
      expect(cluster.dx).toBeCloseTo(cx, 12);
      expect(cluster.dy).toBeCloseTo(cy, 12);
    }
  });
});

// --- 4. level-of-detail thresholds -------------------------------------------

describe('level of detail — thresholds are explicit and monotonic', () => {
  it('maps a scale to exactly one level', () => {
    expect(graphLodLevel(MIN_SCALE)).toBe('file');
    expect(graphLodLevel(1)).toBe('file');
    expect(graphLodLevel(LOD_CLUSTER_SCALE - 0.01)).toBe('file');
    expect(graphLodLevel(LOD_CLUSTER_SCALE)).toBe('cluster');
    expect(graphLodLevel(LOD_SYMBOL_SCALE - 0.01)).toBe('cluster');
    expect(graphLodLevel(LOD_SYMBOL_SCALE)).toBe('symbol');
    expect(graphLodLevel(MAX_SCALE)).toBe('symbol');
  });

  it('never crosses more than one threshold per Reveal Detail step', () => {
    expect(nextLodScale(1)).toBe(LOD_CLUSTER_SCALE);
    expect(nextLodScale(LOD_CLUSTER_SCALE)).toBe(LOD_SYMBOL_SCALE);
    expect(nextLodScale(LOD_SYMBOL_SCALE)).toBeNull();
    expect(nextLodScale(MAX_SCALE)).toBeNull();
  });

  it('leaves room to READ the deepest level (the old 8× cap did not)', () => {
    expect(MAX_SCALE).toBeGreaterThan(LOD_SYMBOL_SCALE * 2);
  });

  it('treats a scale that MULTIPLIED onto a threshold as being at it', () => {
    // Reveal Detail from 1.4 dispatches factor 1.75/1.4 and lands at
    // 1.7499999999999998. With an exact `>=` that read as the FILE level, so the
    // control zoomed in and revealed nothing — and nextLodScale returned 1.75
    // again, so repeated presses could never reach the symbol level.
    // The exact value the mounted surface produced, reproduced as a literal so
    // the case cannot be lost to a different rounding path.
    const short = 1.7499999999999998;
    expect(short).toBeLessThan(LOD_CLUSTER_SCALE); // the float really is below it
    expect(graphLodLevel(short)).toBe('cluster');
    expect(nextLodScale(short)).toBe(LOD_SYMBOL_SCALE);
    const deepShort = 3.9999999999999996;
    expect(deepShort).toBeLessThan(LOD_SYMBOL_SCALE);
    expect(graphLodLevel(deepShort)).toBe('symbol');
    expect(nextLodScale(deepShort)).toBeNull();
    // …and a scale genuinely below a threshold is still below it.
    expect(graphLodLevel(LOD_CLUSTER_SCALE - 0.001)).toBe('file');
    expect(nextLodScale(LOD_SYMBOL_SCALE - 0.001)).toBe(LOD_SYMBOL_SCALE);
  });
});

// --- 5. SCREEN-SPACE sizing — the core fix -----------------------------------

describe('screen-space sizing — rendered size is invariant under zoom and bounded', () => {
  const scales = [MIN_SCALE, 0.5, 1, LOD_CLUSTER_SCALE, 2.5, LOD_SYMBOL_SCALE, 8, 13.37, MAX_SCALE];

  it('renders every mark and label at a CONSTANT screen size across the whole range', () => {
    for (const unitsAtScale1 of [MARK_UNITS.file, MARK_UNITS.concept, MARK_UNITS.cluster, MARK_UNITS.symbol, LABEL_UNITS]) {
      const rendered = scales.map((s) => screenBoundedUnits(unitsAtScale1, s) * s);
      for (const r of rendered) expect(r).toBeCloseTo(rendered[0], 9);
    }
  });

  it('bounds the rendered size no matter how extreme the request', () => {
    for (const s of scales) {
      for (const request of [0, 0.1, 1, 9, 40, 5000]) {
        const rendered = screenBoundedUnits(request, s) * s;
        expect(rendered).toBeGreaterThanOrEqual(MIN_MARK_UNITS_AT_SCALE_1 - 1e-9);
        expect(rendered).toBeLessThanOrEqual(MAX_MARK_UNITS_AT_SCALE_1 + 1e-9);
      }
      // An explicit narrower band (labels) is honoured too.
      const label = screenBoundedUnits(LABEL_UNITS, s, 6, 18) * s;
      expect(label).toBeGreaterThanOrEqual(6 - 1e-9);
      expect(label).toBeLessThanOrEqual(18 + 1e-9);
    }
  });

  /*
   * WHAT IS AND IS NOT PRESERVED AT 100 %.
   *
   * The claim "the 100% view is pixel-identical to P36R" was made in a code
   * comment and in the slice report, and it was FALSE for two independent
   * reasons. This test now pins the part that is true and names the two parts
   * that were not, so the claim cannot quietly come back.
   *
   *   (a) `vector-effect="non-scaling-stroke"` is new on the node shapes and the
   *       base edges — no stylesheet in this project had ever set `vector-effect`
   *       — so `stroke-width: 1.5` renders as 1.5 device px rather than 1.5 user
   *       units (≈ 0.8 px on a 600 px canvas). KEPT, deliberately: those widths
   *       are state-driven CSS rules and so cannot be attributes, and in user
   *       units the 3.4 focus ring reached ~44 px at the 2400 % clamp. jsdom
   *       paints nothing, so this is reasoned from the declared values, not seen.
   *   (b) A selected mark was enlarged by SELECTED_MARK_FACTOR. REVERTED for the
   *       base layer, which is what the assertion below now pins.
   */
  it('keeps the P36R radii and label size at 100% — including for a SELECTED mark', () => {
    expect(screenBoundedUnits(MARK_UNITS.file, 1)).toBe(9);
    expect(screenBoundedUnits(MARK_UNITS.concept, 1)).toBe(11);
    expect(screenBoundedUnits(LABEL_UNITS, 1, 6, 18)).toBe(11);
    // The selection multiplier exists for the DEEP marks only; applying it to a
    // base mark is what made a selected file node 35% larger than P36R's.
    expect(SELECTED_MARK_FACTOR).toBeGreaterThan(1);
    expect(screenBoundedUnits(MARK_UNITS.symbol * SELECTED_MARK_FACTOR, 1)).toBeGreaterThan(
      screenBoundedUnits(MARK_UNITS.symbol, 1),
    );
  });

  it('clamps a scale outside the viewport range instead of dividing by it', () => {
    expect(screenBoundedUnits(9, 0)).toBe(9 / MIN_SCALE);
    expect(screenBoundedUnits(9, 1e9)).toBe(9 / MAX_SCALE);
  });
});

// --- 6. the render plan: no invented nodes, no invented edges ----------------

describe('deep render plan — every mark and every line is traceable to the payload', () => {
  it('opens only files the base layer is showing, inside the viewport', () => {
    const state = viewAt(LOD_CLUSTER_SCALE);
    const plan = deepRenderPlan(deep, base, state, allVisible(state), 'cluster', null);
    expect(plan.openFiles).toBeGreaterThan(0);
    for (const region of plan.regions) {
      expect(deep.byFile.has(region.sourceFile)).toBe(true);
      expect(allVisible(state)).toContain(region.sourceFile);
      expect(region.memberCount).toBe(deep.byFile.get(region.sourceFile)!.length);
    }
    // Every drawn cluster belongs to an open file — nothing is drawn for a file
    // that is not on the canvas.
    const open = new Set(plan.regions.map((r) => r.sourceFile));
    for (const mark of plan.nodes) {
      expect(open.has(mark.sourceFile)).toBe(true);
      expect(deep.clusterByKey.has(mark.id)).toBe(true);
      expect(mark.memberCount).toBe(deep.clusterByKey.get(mark.id)!.members.length);
    }
  });

  it('folds real edges into one aggregate per ordered group pair, with its backing count', () => {
    // The default centre frames the connected core, so both code files are open.
    const state = viewAt(LOD_CLUSTER_SCALE);
    const plan = deepRenderPlan(deep, base, state, allVisible(state), 'cluster', null);
    const drawn = new Set(plan.nodes.map((n) => n.id));
    expect(drawn.has(clusterKeyOf('src/fake_mod.py', '131'))).toBe(true);
    expect(drawn.has(clusterKeyOf('src/other_mod.py', '55'))).toBe(true);

    // Edges 4 (imports) and 7 (imports_from) share the 131 → 55 pair: ONE line,
    // backing 2, carrying both real relation values and no third one.
    const folded = plan.edges.find(
      (e) =>
        e.from === clusterKeyOf('src/fake_mod.py', '131') &&
        e.to === clusterKeyOf('src/other_mod.py', '55'),
    )!;
    expect(folded.backing).toBe(2);
    expect(folded.relations).toEqual(['imports', 'imports_from']);

    // NO INVENTED EDGES, proven per line: each aggregate cites a real payload
    // row, and every backing row really does connect those two groups.
    for (const line of plan.edges) {
      const cited = deep.edges.find((e) => e.index === line.payloadIndex)!;
      expect(cited).toBeDefined();
      expect(deep.byIndex.get(cited.source)!.clusterKey).toBe(line.from);
      expect(deep.byIndex.get(cited.target)!.clusterKey).toBe(line.to);
      const backing = deep.edges.filter(
        (e) =>
          deep.byIndex.get(e.source)!.clusterKey === line.from &&
          deep.byIndex.get(e.target)!.clusterKey === line.to,
      );
      expect(backing.length).toBe(line.backing);
      expect(line.relations.every((r) => backing.some((e) => e.relation === r))).toBe(true);
    }
    // An aggregate set can never be larger than the real edge set it reduces.
    expect(plan.edges.length).toBeLessThanOrEqual(deep.edges.length);
  });

  it('draws one real payload edge per line at the symbol level, direction preserved', () => {
    const fakePos = base.layout.get('src/fake_mod.py')!;
    const state = viewAt(LOD_SYMBOL_SCALE, fakePos.x, fakePos.y);
    const plan = deepRenderPlan(deep, base, state, allVisible(state), 'symbol', null);
    const drawn = new Map(plan.nodes.map((n) => [n.id, n]));
    expect(drawn.size).toBeGreaterThan(0);
    for (const mark of plan.nodes) {
      expect(deep.byId.has(mark.id)).toBe(true);
      expect(mark.memberCount).toBe(1);
    }
    for (const line of plan.edges) {
      expect(line.backing).toBe(1);
      const cited = deep.edges.find((e) => e.index === line.payloadIndex)!;
      expect(deep.byIndex.get(cited.source)!.id).toBe(line.from);
      expect(deep.byIndex.get(cited.target)!.id).toBe(line.to);
      expect(line.relations).toEqual([cited.relation]);
      // Both endpoints are actually on screen — no line to a culled mark.
      expect(drawn.has(line.from)).toBe(true);
      expect(drawn.has(line.to)).toBe(true);
    }
  });

  it('culls to the viewport — a distant file is neither opened nor half-drawn', () => {
    // docs/fake-note.md sits on the base layout's unconnected belt, far out.
    const notePos = base.layout.get('docs/fake-note.md')!;
    const near = viewAt(LOD_SYMBOL_SCALE, notePos.x, notePos.y);
    const far = viewAt(LOD_SYMBOL_SCALE, 0, 0);
    const nearPlan = deepRenderPlan(deep, base, near, allVisible(near), 'symbol', null);
    const farPlan = deepRenderPlan(deep, base, far, allVisible(far), 'symbol', null);
    expect(nearPlan.nodes.some((n) => n.sourceFile === 'docs/fake-note.md')).toBe(true);
    expect(farPlan.nodes.some((n) => n.sourceFile === 'docs/fake-note.md')).toBe(false);
    // An empty viewport is reported as empty — never padded out.
    const nowhere = viewAt(LOD_SYMBOL_SCALE, 90_000, 90_000);
    const emptyPlan = deepRenderPlan(deep, base, nowhere, allVisible(nowhere), 'symbol', null);
    expect(emptyPlan.nodes).toEqual([]);
    expect(emptyPlan.edges).toEqual([]);
    expect(emptyPlan.openFiles).toBe(0);
  });

  it('honours the active relationship filter with the payload’s own values', () => {
    const fakePos = base.layout.get('src/fake_mod.py')!;
    const state: GraphViewState = {
      ...viewAt(LOD_SYMBOL_SCALE, fakePos.x, fakePos.y),
      relationFilter: ['calls'],
    };
    const plan = deepRenderPlan(deep, base, state, allVisible(state), 'symbol', null);
    expect(plan.edges.length).toBeGreaterThan(0);
    for (const line of plan.edges) expect(line.relations).toEqual(['calls']);
    const none: GraphViewState = { ...state, relationFilter: [] };
    expect(deepRenderPlan(deep, base, none, allVisible(none), 'symbol', null).edges).toEqual([]);
  });

  it('pins the selection and a BOUNDED local neighbourhood, wherever they sit', () => {
    // A viewport that contains nothing: only the pinned selection and its real
    // neighbours are drawn, so a selected mark never silently disappears.
    const nowhere = viewAt(LOD_SYMBOL_SCALE, 90_000, 90_000);
    const plan = deepRenderPlan(
      deep,
      base,
      nowhere,
      allVisible(nowhere),
      'symbol',
      'fake/export_fn',
    );
    const ids = plan.nodes.map((n) => n.id);
    expect(ids).toContain('fake/export_fn');
    // Its four real neighbours, and nothing else.
    expect(ids.sort()).toEqual(
      ['fake/export_fn', 'fake/mod_root', 'fake/validate_fn', 'other/load_fn', 'other/mod_root'].sort(),
    );
    expect(plan.nodes.filter((n) => n.pinned).length).toBeLessThanOrEqual(MAX_DEEP_NEIGHBORS + 1);
  });

  it('reports files with no symbol-level structure instead of inventing one', () => {
    const withoutNote = decodeDeepGraph({
      ...memoryGraphDetailAvailable,
      nodes: DEEP_NODE_ROWS.slice(0, 6),
      edges: DEEP_EDGE_ROWS.filter(([s, t]) => s < 6 && t < 6),
    }) as DeepIndex;
    const state = viewAt(LOD_CLUSTER_SCALE);
    const plan = deepRenderPlan(withoutNote, base, state, allVisible(state), 'cluster', null);
    expect(plan.filesWithoutDeepStructure).toBe(1);
    expect(plan.nodes.some((n) => n.sourceFile === 'docs/fake-note.md')).toBe(false);
  });

  it('summarises relationships from real values and counts only', () => {
    const state = viewAt(LOD_SYMBOL_SCALE, 0, 0);
    const mark = deepRenderPlan(
      deep,
      base,
      state,
      allVisible(state),
      'symbol',
      'fake/export_fn',
    ).nodes.find((n) => n.id === 'fake/export_fn')!;
    // Its four real incident rows: 0 (contains), 3 (calls), 4 (imports),
    // 7 (imports_from) — one each, and no fifth relation.
    expect(deepRelationSummary(deep, mark, null)).toEqual([
      { relation: 'calls', count: 1 },
      { relation: 'contains', count: 1 },
      { relation: 'imports', count: 1 },
      { relation: 'imports_from', count: 1 },
    ]);
    expect(deepRelationSummary(deep, mark, ['imports'])).toEqual([{ relation: 'imports', count: 1 }]);
  });
});

// --- 6b. the fold, said out loud (C2) + labelling (I2) -----------------------

describe('deep render plan — an aggregate line is ACCOUNTED for, not just honest', () => {
  const clusterPlan = () => {
    const state = viewAt(LOD_CLUSTER_SCALE);
    return deepRenderPlan(deep, base, state, allVisible(state), 'cluster', null);
  };

  it('reports what the drawn lines really stand for', () => {
    const plan = clusterPlan();
    // The model was already truthful; these are the figures the SCREEN needs.
    expect(plan.edgesBacking).toBe(plan.edges.reduce((sum, e) => sum + e.backing, 0));
    expect(plan.edgesBacking).toBeGreaterThan(plan.edges.length); // at least one fold
    expect(plan.edgesFolded).toBe(plan.edges.filter((e) => e.backing > 1).length);
    expect(plan.edgesMultiRelation).toBe(plan.edges.filter((e) => e.relations.length > 1).length);
    // TWO ordered pairs fold, and both bundle two different relation values —
    // which is precisely the presentation defect: one identical stroke stood for
    // either of these.
    //   131 → 77      : edge 1 `contains` + edge 3 `calls`
    //   131 → other 55: edge 4 `imports`  + edge 7 `imports_from`
    expect(plan.edgesFolded).toBe(2);
    expect(plan.edgesMultiRelation).toBe(2);
    expect(plan.edges.map((e) => e.relations)).toEqual([
      ['calls', 'contains'],
      ['imports', 'imports_from'],
    ]);
    // An aggregate set can never claim more backing than the real edge set holds.
    expect(plan.edgesBacking + plan.edgesInsideGroups).toBeLessThanOrEqual(deep.edges.length);
  });

  it('counts the intra-cluster edges it deliberately does not draw', () => {
    const plan = clusterPlan();
    const drawn = new Set(plan.nodes.map((n) => n.id));
    const inside = deep.edges.filter((e) => {
      const from = deep.byIndex.get(e.source)!;
      const to = deep.byIndex.get(e.target)!;
      return from.clusterKey === to.clusterKey && drawn.has(from.clusterKey);
    });
    expect(plan.edgesInsideGroups).toBe(inside.length);
    expect(plan.edgesInsideGroups).toBeGreaterThan(0);
  });

  it('states the fold, the real backing count and the intra-cluster remainder in the note', () => {
    const plan = clusterPlan();
    const sentence = deepCountsSentence(plan);
    expect(sentence).toContain(`${plan.nodes.length} cluster`);
    expect(sentence).toContain(`${plan.edges.length} line`);
    // The real backing count appears, and the line count is NOT presented as a
    // number of relationships.
    expect(sentence).toContain(`${plan.edgesBacking} recorded reference`);
    expect(sentence).toMatch(/SUMMARISES/);
    expect(sentence).toMatch(/one line can stand for several/);
    expect(sentence).toContain('fold more than one kind of reference');
    expect(sentence).toContain(`${plan.edgesInsideGroups} recorded reference`);
    expect(sentence).toMatch(/counted here and not drawn as lines/);
  });

  it('says ONE reference per line at the symbol level, and never the fold wording', () => {
    const fakePos = base.layout.get('src/fake_mod.py')!;
    const state = viewAt(LOD_SYMBOL_SCALE, fakePos.x, fakePos.y);
    const plan = deepRenderPlan(deep, base, state, allVisible(state), 'symbol', null);
    expect(plan.edgesBacking).toBe(plan.edges.length);
    expect(plan.edgesFolded).toBe(0);
    expect(plan.edgesMultiRelation).toBe(0);
    expect(plan.edgesInsideGroups).toBe(0);
    const sentence = deepCountsSentence(plan);
    expect(sentence).toContain('Each line is ONE recorded reference');
    expect(sentence).not.toMatch(/SUMMARISES/);
  });

  it('discloses EVERY bound it applies — none of them silently (M3, M4, M7)', () => {
    // The node cap and the edge cap, at real payload density.
    const payload = bigDeepPayload(200, 14);
    const index = decodeDeepGraph(payload) as DeepIndex;
    const state = viewAt(LOD_SYMBOL_SCALE);
    const visible = visibleNodeIds(state, bigBaseIndex);
    const capped = deepRenderPlan(index, bigBaseIndex, state, visible, 'symbol', null);
    expect(capped.nodesTruncated).toBe(true);
    expect(deepCountsSentence(capped)).toContain(`capped from ${capped.nodesConsidered}`);
    if (capped.edgesTruncated) {
      // The edge cap now uses the word "capped", like the node cap — it used to
      // read "; N relationships matched the view", which never said so.
      expect(deepCountsSentence(capped)).toContain(
        `lines are capped from ${capped.edgesConsidered}`,
      );
    }

    // MAX_DEEP_NEIGHBORS — this unit's only formerly SILENT cap.
    const hub = index.nodes.reduce((a, b) => (b.degree > a.degree ? b : a));
    expect(hub.degree).toBeGreaterThan(0);
    const nowhere = viewAt(LOD_SYMBOL_SCALE, 90_000, 90_000);
    const pinnedPlan = deepRenderPlan(
      index,
      bigBaseIndex,
      nowhere,
      visibleNodeIds(nowhere, bigBaseIndex),
      'symbol',
      hub.id,
    );
    expect(pinnedPlan.pinnedNeighborsConsidered).toBeGreaterThan(0);
    if (pinnedPlan.pinnedNeighborsTruncated) {
      expect(deepCountsSentence(pinnedPlan)).toContain(
        `${pinnedPlan.pinnedNeighborsConsidered} recorded neighbours`,
      );
      expect(deepCountsSentence(pinnedPlan)).toContain(`${MAX_DEEP_NEIGHBORS} of them are kept`);
    }

    // Concepts LEAVE the canvas at the deeper levels. Nothing said so before:
    // `filesWithoutDeepStructure` counts only `kind === 'file'`.
    const clusterState = viewAt(LOD_CLUSTER_SCALE);
    const plan = deepRenderPlan(deep, base, clusterState, allVisible(clusterState), 'cluster', null);
    const concepts = allVisible(clusterState).filter(
      (id) => base.byId.get(id)?.kind === 'concept',
    ).length;
    expect(plan.conceptsNotInLayer).toBe(concepts);
    expect(concepts).toBeGreaterThan(0);
    expect(deepCountsSentence(plan)).toContain(
      `${concepts} concept${concepts === 1 ? '' : 's'}`,
    );
    expect(deepCountsSentence(plan)).toMatch(/leaves? the canvas at this zoom/);

    // …and the payload's own cap.
    expect(deepCountsSentence(plan, true)).toContain('The served payload itself is capped');
    expect(deepCountsSentence(plan, false)).not.toContain('The served payload itself is capped');
  });
});

describe('deep labelling — landmarks, not silence (I2)', () => {
  it('labels every mark while few are drawn', () => {
    const state = viewAt(LOD_CLUSTER_SCALE);
    const plan = deepRenderPlan(deep, base, state, allVisible(state), 'cluster', null);
    expect(plan.nodes.length).toBeLessThanOrEqual(DEEP_LABEL_LIMIT);
    expect(plan.labelIds.sort()).toEqual(plan.nodes.map((n) => n.id).sort());
  });

  it('keeps a bounded, collision-filtered landmark set above the limit — never an empty one', () => {
    const payload = bigDeepPayload(200, 14);
    const index = decodeDeepGraph(payload) as DeepIndex;
    for (const level of ['cluster', 'symbol'] as const) {
      const state = viewAt(level === 'symbol' ? LOD_SYMBOL_SCALE : LOD_CLUSTER_SCALE);
      const plan = deepRenderPlan(
        index,
        bigBaseIndex,
        state,
        visibleNodeIds(state, bigBaseIndex),
        level,
        null,
      );
      expect(plan.nodes.length).toBeGreaterThan(DEEP_LABEL_LIMIT);
      // The defect: at the symbol level this used to be ZERO — 260 anonymous
      // marks at the deepest level of a "zoom reveals detail" feature.
      expect(plan.labelIds.length).toBeGreaterThan(0);
      expect(plan.labelIds.length).toBeLessThanOrEqual(DEEP_HUB_LABEL_COUNT);
      // Every label names a mark that is actually drawn.
      const drawn = new Set(plan.nodes.map((n) => n.id));
      for (const id of plan.labelIds) expect(drawn.has(id)).toBe(true);
      // Landmarks come from the plan's own ranking, so "what stays labelled" and
      // "what survives the cap" cannot disagree.
      const rank = new Map(plan.nodes.map((n, i) => [n.id, i] as const));
      for (const id of plan.labelIds) {
        expect(rank.get(id)!).toBeLessThan(DEEP_HUB_LABEL_COUNT * 3);
      }
    }
  });

  it('is deterministic and elides exactly as the canvas paints', () => {
    const nodes = Array.from({ length: 60 }, (_, i) => ({
      key: `k${i}`,
      kind: 'symbol' as const,
      id: `id-${i}`,
      label: `symbol_name_number_${i}`,
      x: i * 40,
      y: 0,
      sourceFile: 'src/fake_mod.py',
      communityId: '1',
      communityName: null,
      fileType: 'code',
      sourceLocation: null,
      memberCount: 1,
      connections: 1,
      pinned: false,
    }));
    const a = placedDeepLabelIds(nodes, LOD_SYMBOL_SCALE);
    const b = placedDeepLabelIds(nodes, LOD_SYMBOL_SCALE);
    expect(a).toEqual(b);
    expect(a.length).toBe(DEEP_HUB_LABEL_COUNT);
    // Overlapping candidates are REJECTED rather than smeared on top of one
    // another: the same nodes stacked at one point yield a single label.
    const stacked = nodes.map((n) => ({ ...n, x: 0, y: 0 }));
    expect(placedDeepLabelIds(stacked, LOD_SYMBOL_SCALE).length).toBe(1);
    expect(deepMarkLabelText('short')).toBe('short');
    expect(deepMarkLabelText('x'.repeat(40))).toBe(`${'x'.repeat(25)}…`);
    expect(deepMarkLabelText('x'.repeat(40)).length).toBe(26);
  });
});

// --- 7. bounds + performance --------------------------------------------------

describe('deep layer — bounded work at the real payload size', () => {
  const bigBase = bigBaseIndex;

  it('decodes a payload the size of the real artifact well inside a frame budget', () => {
    // 200 files × 14 symbols = 2,800 nodes — larger than the real 2,612.
    const payload = bigDeepPayload(200, 14);
    expect(payload.nodes.length).toBe(2800);
    const started = performance.now();
    const index = decodeDeepGraph(payload) as DeepIndex;
    const elapsed = performance.now() - started;
    expect(index.nodes.length).toBe(2800);
    // Generous, but a REAL bound: a decode that regressed into O(n²) would blow
    // straight through it (the pre-fix `find`-per-edge version took ~4 s here).
    expect(elapsed).toBeLessThan(600);
  });

  it('caps the rendered marks and lines however dense the viewport', () => {
    const payload = bigDeepPayload(200, 14);
    const index = decodeDeepGraph(payload) as DeepIndex;
    const state = viewAt(LOD_SYMBOL_SCALE);
    const visible = visibleNodeIds(state, bigBase);
    const started = performance.now();
    const plan = deepRenderPlan(index, bigBase, state, visible, 'symbol', null);
    const elapsed = performance.now() - started;
    expect(plan.nodes.length).toBeLessThanOrEqual(MAX_DEEP_NODES);
    expect(plan.edges.length).toBeLessThanOrEqual(MAX_DEEP_EDGES);
    expect(elapsed).toBeLessThan(250);
    if (plan.nodesTruncated) expect(plan.nodesConsidered).toBeGreaterThan(plan.nodes.length);

    const clusterState = viewAt(LOD_CLUSTER_SCALE);
    const clusterPlan = deepRenderPlan(
      index,
      bigBase,
      clusterState,
      visibleNodeIds(clusterState, bigBase),
      'cluster',
      null,
    );
    expect(clusterPlan.nodes.length).toBeLessThanOrEqual(MAX_DEEP_NODES);
    expect(clusterPlan.edges.length).toBeLessThanOrEqual(MAX_DEEP_EDGES);
  });

  it('produces the same plan twice for the same viewport — no hidden state', () => {
    const state = viewAt(LOD_SYMBOL_SCALE, 12, -34);
    const a = deepRenderPlan(deep, base, state, allVisible(state), 'symbol', 'fake/export_fn');
    const b = deepRenderPlan(deep, base, state, allVisible(state), 'symbol', 'fake/export_fn');
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
  });
});

// --- 8. structural staleness --------------------------------------------------

describe('structural staleness — stated, from the payload, unsoftened', () => {
  it('reads the honesty flags rather than assuming a flattering default', () => {
    const staleness = deepStaleness(memoryGraphDetailAvailable.meta.provenance);
    expect(staleness.builtAtCommit).toBe(DEEP_BUILT_AT_COMMIT);
    expect(staleness.shortCommit).toBe(DEEP_BUILT_AT_COMMIT.slice(0, 7));
    expect(staleness.isPointInTime).toBe(true);
    expect(staleness.describesCurrentHead).toBe(false);
  });

  it('says the structure does NOT describe HEAD, and never hedges it', () => {
    const sentence = stalenessSentence(deepStaleness(memoryGraphDetailAvailable.meta.provenance));
    expect(sentence).toContain(DEEP_BUILT_AT_COMMIT.slice(0, 7));
    expect(sentence).toContain('point-in-time');
    expect(sentence).toContain('does NOT describe the current repository HEAD');
    expect(sentence.toLowerCase()).not.toContain('slightly');
    expect(sentence.toLowerCase()).not.toContain('may be out of date');
  });

  it('never denies describing HEAD when the payload says it does (M6 — the guard, covered)', () => {
    // Unreachable with today's backend (`memory_graph.py` hardcodes both flags),
    // which is exactly why it is driven directly here rather than left as dead
    // code no test could distinguish from a bug. Both flag combinations that
    // report HEAD must avoid the denial.
    for (const isPointInTime of [true, false]) {
      const sentence = stalenessSentence(
        deepStaleness({
          ...memoryGraphDetailAvailable.meta.provenance,
          describes_current_head: true,
          is_point_in_time: isPointInTime,
        }),
      );
      expect(sentence).toContain('reports as the current repository HEAD');
      expect(sentence).not.toContain('does NOT describe the current repository HEAD');
      // The point-in-time axis is reported separately, because it is a separate
      // fact from whether the indexed commit is HEAD.
      expect(sentence.includes('still a point-in-time index')).toBe(isPointInTime);
    }
    // …and the real payload's flags still produce the unsoftened denial.
    expect(stalenessSentence(deepStaleness(memoryGraphDetailAvailable.meta.provenance))).toContain(
      'does NOT describe the current repository HEAD',
    );
  });

  it('does not invent a commit when the payload names none', () => {
    const sentence = stalenessSentence(
      deepStaleness({
        ...memoryGraphDetailAvailable.meta.provenance,
        built_at_commit: null,
      }),
    );
    expect(sentence).toContain('a commit the payload does not name');
  });
});

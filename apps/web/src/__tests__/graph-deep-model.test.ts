import { describe, it, expect } from 'vitest';
import {
  MAX_DEEP_EDGES,
  MAX_DEEP_NODES,
  MAX_DEEP_NEIGHBORS,
  FILE_RADIUS_MAX,
  FILE_RADIUS_MIN,
  clusterKeyOf,
  decodeDeepGraph,
  deepFileRadius,
  deepRelationSummary,
  deepRenderPlan,
  deepStaleness,
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

  it('is UNCHANGED at 100% zoom — the P36R canvas is pixel-identical there', () => {
    expect(screenBoundedUnits(MARK_UNITS.file, 1)).toBe(9);
    expect(screenBoundedUnits(MARK_UNITS.concept, 1)).toBe(11);
    expect(screenBoundedUnits(LABEL_UNITS, 1, 6, 18)).toBe(11);
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

// --- 7. bounds + performance --------------------------------------------------

describe('deep layer — bounded work at the real payload size', () => {
  const bigBase = buildGraphIndex({
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

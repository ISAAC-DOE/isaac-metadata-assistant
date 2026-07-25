import { describe, it, expect } from 'vitest';
import {
  HUB_LABEL_COUNT,
  LABEL_LIMIT,
  LAYOUT_ITERATIONS,
  MAX_NEIGHBORHOOD_NODES,
  MAX_RENDER_NODES,
  MAX_SCALE,
  MIN_SCALE,
  PALETTE_SLOTS,
  CANVAS_LABEL_MAX_CHARS,
  applyGraphAction,
  buildGraphIndex,
  canvasNodeLabel,
  communityColorIndex,
  communityLabelAmong,
  communityOptionLabel,
  computeLayout,
  connectedNodes,
  edgeKey,
  filteredNodeIds,
  fitViewport,
  hubLabelIds,
  initialGraphViewState,
  labelBox,
  placedLabelIds,
  neighborhood,
  nodePosition,
  resolveCommunity,
  resolveNode,
  shortestPath,
  viewBoxOf,
  visibleEdges,
  visibleNodeIds,
  type GraphAction,
  type GraphIndex,
  type GraphViewState,
} from '../lib/graphModel';
import type { ApiMemoryGraphEdge, ApiMemoryGraphNode, ApiMemoryGraphResponse } from '../lib/types';
import { memoryGraphAvailable } from '../test/apiFixtures';

/*
 * P36R S3 — the shared, PURE graph model. Slices 4 (command bar) and 5
 * (Assistant graph intents) are additional front-ends over this same module, so
 * these tests pin the contract they will build on: one reducer, deterministic
 * layout, bounded traversal, and identity that is resolved or refused — never
 * guessed.
 */

const FIXTURE = memoryGraphAvailable as unknown as ApiMemoryGraphResponse;

function makeResponse(
  nodes: ApiMemoryGraphNode[],
  edges: ApiMemoryGraphEdge[],
  communities: { id: string; name: string | null; file_count: number }[] = [],
): ApiMemoryGraphResponse {
  return {
    plane: 'memory',
    note: 'synthetic',
    available: true,
    truncated: false,
    nodes,
    edges,
    communities,
    meta: {
      counts: {
        files: nodes.filter((n) => n.kind === 'file').length,
        concepts: nodes.filter((n) => n.kind === 'concept').length,
        reference_edges: edges.length,
        files_with_references: 0,
        isolated_files: 0,
        communities_rendered: communities.length,
      },
      underlying_graph: {
        embedded: false,
        node_count: null,
        edge_count: null,
        community_count: null,
        note: 'n/a',
      },
      provenance: {
        built_at_commit: null,
        source_graph_sha256: null,
        snapshot_schema_version: null,
        provider: 'unavailable',
        integrity: 'unknown',
      },
    },
  };
}

const file = (id: string, community: string | null = null): ApiMemoryGraphNode => ({
  id,
  kind: 'file',
  label: id,
  file_type: 'code',
  community_id: community,
  community_name: community ? `cluster ${community}` : null,
  node_count: 1,
  on_disk: true,
});

/** A chain a-0 — a-1 — … — a-(n-1), used for traversal + render-bound tests. */
function chain(n: number): ApiMemoryGraphResponse {
  const nodes = Array.from({ length: n }, (_, i) => file(`a-${String(i).padStart(4, '0')}`));
  const edges: ApiMemoryGraphEdge[] = [];
  for (let i = 0; i + 1 < n; i += 1) {
    edges.push({ source: nodes[i].id, target: nodes[i + 1].id, relations: ['imports'] });
  }
  return makeResponse(nodes, edges);
}

// --- 1. deterministic projection --------------------------------------------

describe('P36R S3 · deterministic layout', () => {
  it('computeLayout run twice on the same input yields IDENTICAL coordinates', () => {
    const ids = FIXTURE.nodes.map((n) => n.id);
    const a = computeLayout(ids, FIXTURE.edges);
    const b = computeLayout(ids, FIXTURE.edges);
    expect([...a.entries()]).toEqual([...b.entries()]);
    // Not vacuous: real, finite, distinct coordinates were produced.
    expect(a.size).toBe(ids.length);
    for (const p of a.values()) {
      expect(Number.isFinite(p.x)).toBe(true);
      expect(Number.isFinite(p.y)).toBe(true);
    }
    expect(new Set([...a.values()].map((p) => `${p.x},${p.y}`)).size).toBe(ids.length);
  });

  it('is insensitive to INPUT ORDER (the id sort is the seed, not the array order)', () => {
    const ids = FIXTURE.nodes.map((n) => n.id);
    const a = computeLayout(ids, FIXTURE.edges);
    const b = computeLayout([...ids].reverse(), [...FIXTURE.edges].reverse());
    expect([...a.entries()].sort()).toEqual([...b.entries()].sort());
  });

  it('buildGraphIndex run twice yields an identical layout', () => {
    const a = buildGraphIndex(FIXTURE);
    const b = buildGraphIndex(FIXTURE);
    expect([...a.layout.entries()]).toEqual([...b.layout.entries()]);
    expect(a.renderIds).toEqual(b.renderIds);
  });

  it('uses a FIXED iteration count — no time/frame dependence', () => {
    expect(LAYOUT_ITERATIONS).toBeGreaterThan(0);
    const big = chain(120);
    const t0 = computeLayout(
      big.nodes.map((n) => n.id),
      big.edges,
    );
    const t1 = computeLayout(
      big.nodes.map((n) => n.id),
      big.edges,
    );
    expect([...t0.entries()]).toEqual([...t1.entries()]);
  });

  it('degenerates honestly: empty ⇒ empty, single node ⇒ origin', () => {
    expect(computeLayout([], []).size).toBe(0);
    expect([...computeLayout(['only'], []).entries()]).toEqual([['only', { x: 0, y: 0 }]]);
  });
});

// --- 2. no invented edges -----------------------------------------------------

describe('P36R S3 · no invented edges', () => {
  it('every indexed edge exists in the payload', () => {
    const index = buildGraphIndex(FIXTURE);
    const payloadKeys = new Set(FIXTURE.edges.map((e) => edgeKey(e.source, e.target)));
    for (const e of index.edges) expect(payloadKeys.has(edgeKey(e.source, e.target))).toBe(true);
    expect(index.edges.length).toBeLessThanOrEqual(FIXTURE.edges.length);
  });

  it('drops — never repairs — an edge whose endpoint is not a node', () => {
    const data = makeResponse(
      [file('a'), file('b')],
      [
        { source: 'a', target: 'b', relations: ['imports'] },
        { source: 'a', target: 'ghost', relations: ['imports'] },
        { source: 'a', target: 'a', relations: ['imports'] },
      ],
    );
    const index = buildGraphIndex(data);
    expect(index.edges).toEqual([{ source: 'a', target: 'b', relations: ['imports'] }]);
    expect(index.byId.has('ghost')).toBe(false);
  });

  it('visibleEdges can only ever REMOVE edges from the indexed set', () => {
    const index = buildGraphIndex(FIXTURE);
    const state = initialGraphViewState();
    const visible = new Set(visibleNodeIds(state, index));
    for (const e of visibleEdges(state, index, visible)) {
      expect(index.edgeKeys.has(edgeKey(e.source, e.target))).toBe(true);
    }
  });

  it('adjacency is symmetric and derived only from indexed edges', () => {
    const index = buildGraphIndex(FIXTURE);
    for (const [id, list] of index.adjacency) {
      for (const nb of list) {
        expect(index.edgeKeys.has(edgeKey(id, nb.id))).toBe(true);
        expect((index.adjacency.get(nb.id) ?? []).some((x) => x.id === id)).toBe(true);
      }
    }
  });
});

// --- 3. render bounds ---------------------------------------------------------

/*
 * The contract these guards encode (orchestrator decision R8, 2026-07-25): the
 * WHOLE-GRAPH overview is the default Explore view — not a search-first empty
 * canvas — and it is bounded by MAX_RENDER_NODES, applied as a deterministic
 * sorted prefix and reported honestly when it bites.
 *
 * Both halves are load-bearing. A change that silently UNBOUNDS the canvas and
 * a change that silently TRUNCATES it must each fail here.
 */
describe('P36R S3 · render bounds', () => {
  it('does not bite on the real-shaped projection', () => {
    const index = buildGraphIndex(FIXTURE);
    expect(index.renderTruncated).toBe(false);
    expect(index.renderIds.length).toBe(FIXTURE.nodes.length);
  });

  it('the DEFAULT view is the whole graph up to the cap — no search-first subset', () => {
    const index = buildGraphIndex(FIXTURE);
    const state = initialGraphViewState();
    // Nothing is pre-applied: no query, no filter, no focus.
    expect(state.search).toBe('');
    expect(state.typeFilter).toBe('all');
    expect(state.communityFilter).toBe('all');
    expect(state.focus).toBeNull();
    expect(visibleNodeIds(state, index)).toEqual(index.nodes.map((n) => n.id));
    expect(visibleNodeIds(state, index).length).toBe(
      Math.min(FIXTURE.nodes.length, MAX_RENDER_NODES),
    );
  });

  it('caps at MAX_RENDER_NODES and reports it, with a deterministic sorted prefix', () => {
    const big = chain(MAX_RENDER_NODES + 40);
    const a = buildGraphIndex(big);
    const b = buildGraphIndex(big);
    expect(a.renderTruncated).toBe(true);
    expect(a.renderIds.length).toBe(MAX_RENDER_NODES);
    expect(a.renderIds).toEqual(b.renderIds);
    // The prefix is exactly "degree desc, then id asc", stored sorted by id —
    // pinned explicitly so the selection cannot drift into an arbitrary slice.
    const degree = (id: string) => a.adjacency.get(id)?.length ?? 0;
    const cmp = (x: string, y: string) => (x < y ? -1 : x > y ? 1 : 0);
    const expected = a.nodes
      .map((n) => n.id)
      .sort((x, y) => degree(y) - degree(x) || cmp(x, y))
      .slice(0, MAX_RENDER_NODES)
      .sort(cmp);
    expect(a.renderIds).toEqual(expected);
    // Every capped node is still INDEXED (reachable in Browse / by search) —
    // the bound is a rendering bound, not a data bound.
    expect(a.nodes.length).toBe(MAX_RENDER_NODES + 40);
  });

  it('above the cap the default draws exactly the cap and the rest stay reachable', () => {
    const index = buildGraphIndex(chain(MAX_RENDER_NODES + 40));
    const state = initialGraphViewState();
    const drawn = visibleNodeIds(state, index);
    const listed = filteredNodeIds(state, index);
    expect(drawn.length).toBe(MAX_RENDER_NODES);
    expect(listed.length).toBe(MAX_RENDER_NODES + 40);
    const capped = listed.filter((id) => !drawn.includes(id));
    expect(capped.length).toBe(40);
    // The chain's two ends have degree 1, so they lose the cap — and are still
    // present in the index, findable by search and listed in Browse.
    expect(capped).toContain('a-0000');
    for (const id of capped) {
      expect(index.byId.has(id)).toBe(true);
      expect(resolveNode(id, index)).toEqual({ status: 'found', id });
    }
  });
});

// --- 3b. label bounds ---------------------------------------------------------

describe('P36R S3 · label bounds', () => {
  const index = buildGraphIndex(chain(120));

  it('labels the most-connected nodes first, ties by sorted id, deterministically', () => {
    const ids = index.nodes.map((n) => n.id);
    const hubs = hubLabelIds(ids, index);
    expect(hubs.length).toBe(HUB_LABEL_COUNT);
    expect(hubs).toEqual(hubLabelIds(ids, index));
    // In a chain every interior node has degree 2 and the two ends have degree
    // 1, so the id tie-break is what decides — and it must decide exactly this.
    expect(hubs).toEqual(
      ids.filter((id) => (index.adjacency.get(id)?.length ?? 0) === 2).slice(0, HUB_LABEL_COUNT),
    );
    expect(hubs).not.toContain('a-0000'); // a degree-1 end loses to the interior
  });

  it('a canvas ABOVE the all-labels limit is never left with zero labels', () => {
    expect(HUB_LABEL_COUNT).toBeGreaterThan(0);
    expect(HUB_LABEL_COUNT).toBeLessThanOrEqual(LABEL_LIMIT);
    const visible = visibleNodeIds(initialGraphViewState(), index);
    expect(visible.length).toBeGreaterThan(LABEL_LIMIT); // the labelling branch
    expect(hubLabelIds(visible, index).length).toBe(HUB_LABEL_COUNT);
  });

  it('never labels more than it was given, and takes none when asked for none', () => {
    expect(hubLabelIds(['a-0000'], index)).toEqual(['a-0000']);
    expect(hubLabelIds([], index)).toEqual([]);
    expect(hubLabelIds(index.renderIds, index, 0)).toEqual([]);
  });

  it('placement drops candidates whose labels would COLLIDE, and is deterministic', () => {
    const visible = visibleNodeIds(initialGraphViewState(), index);
    const placed = placedLabelIds(visible, index);
    expect(placed).toEqual(placedLabelIds(visible, index));
    expect(placed.length).toBeGreaterThan(0);
    expect(placed.length).toBeLessThanOrEqual(HUB_LABEL_COUNT);
    for (const id of placed) expect(visible).toContain(id);

    // No two painted labels overlap — the point of the placement pass. The
    // highest-degree nodes sit in a cluster's core, so labelling the raw top-N
    // outright produced a smear of overlapping text.
    const boxes = placed.map((id) => labelBox(id, index)).filter((b) => b !== null);
    expect(boxes.length).toBe(placed.length);
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i]!;
        const b = boxes[j]!;
        const hit = a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
        expect(hit, `labels ${placed[i]} and ${placed[j]} overlap`).toBe(false);
      }
    }
  });

  it('the label text the placer measures is the text the canvas paints', () => {
    // One definition, so the width estimate can never drift from the glyphs.
    expect(canvasNodeLabel(file('src/deep/nested/module.py'))).toBe('module.py');
    const long = 'x'.repeat(CANVAS_LABEL_MAX_CHARS + 10);
    expect(canvasNodeLabel(file(long)).length).toBe(CANVAS_LABEL_MAX_CHARS);
    expect(canvasNodeLabel(file(long)).endsWith('…')).toBe(true);
  });
});

// --- 4. identity is resolved or refused, never guessed ------------------------

describe('P36R S3 · resolveNode', () => {
  const index = buildGraphIndex(FIXTURE);

  it('resolves an exact id', () => {
    expect(resolveNode('src/fake_mod.py', index)).toEqual({
      status: 'found',
      id: 'src/fake_mod.py',
    });
  });

  it('resolves an unambiguous basename and an unambiguous label', () => {
    expect(resolveNode('fake_mod.py', index)).toEqual({ status: 'found', id: 'src/fake_mod.py' });
    expect(resolveNode('Provenance', index)).toEqual({ status: 'found', id: 'concept-provenance' });
  });

  it('returns a BOUNDED candidate list instead of guessing when ambiguous', () => {
    const r = resolveNode('mod', index);
    expect(r.status).toBe('ambiguous');
    if (r.status !== 'ambiguous') throw new Error('unreachable');
    expect(r.candidates).toEqual(['src/fake_mod.py', 'src/other_mod.py']);
  });

  it('returns not_found for an unknown token and for empty input', () => {
    expect(resolveNode('does/not/exist.py', index)).toEqual({ status: 'not_found' });
    expect(resolveNode('   ', index)).toEqual({ status: 'not_found' });
  });
});

describe('P36R S3 · resolveCommunity', () => {
  // A cluster token (`community <name|id>`) gets the SAME treatment as a node
  // token: resolved, bounded-ambiguous, or an honest miss — never guessed, and
  // never silently turned into an empty view.
  const idx = buildGraphIndex(
    makeResponse(
      [file('a', '41'), file('b', '52'), file('c', '9')],
      [],
      [
        { id: '41', name: 'Export Pipeline (28)', file_count: 3 },
        { id: '52', name: 'Export Pipeline (42)', file_count: 2 },
        { id: '9', name: 'Audit', file_count: 1 },
      ],
    ),
  );

  it('resolves by exact id and by name, case-insensitively', () => {
    expect(resolveCommunity('52', idx)).toEqual({ status: 'found', id: '52' });
    expect(resolveCommunity('Audit', idx)).toEqual({ status: 'found', id: '9' });
    expect(resolveCommunity('audit', idx)).toEqual({ status: 'found', id: '9' });
  });

  it('offers bounded candidates instead of picking one when a name is shared', () => {
    expect(resolveCommunity('Export Pipeline', idx)).toEqual({
      status: 'ambiguous',
      candidates: ['41', '52'],
    });
  });

  it('is honest about a miss', () => {
    expect(resolveCommunity('no-such-cluster', idx)).toEqual({ status: 'not_found' });
    expect(resolveCommunity('   ', idx)).toEqual({ status: 'not_found' });
  });
});

// --- 5. traversal -------------------------------------------------------------

describe('P36R S3 · shortestPath', () => {
  const long = buildGraphIndex(chain(6));

  it('finds the route and returns it start → end', () => {
    expect(shortestPath('a-0000', 'a-0005', long)).toEqual([
      'a-0000',
      'a-0001',
      'a-0002',
      'a-0003',
      'a-0004',
      'a-0005',
    ]);
  });

  it('is deterministic across repeated calls', () => {
    const a = shortestPath('a-0000', 'a-0005', long);
    const b = shortestPath('a-0000', 'a-0005', long);
    expect(a).toEqual(b);
  });

  it('returns null — honestly — when the nodes are not connected', () => {
    const index = buildGraphIndex(makeResponse([file('a'), file('b')], []));
    expect(shortestPath('a', 'b', index)).toBeNull();
  });

  it('returns null for an unknown endpoint and [self] for from === to', () => {
    expect(shortestPath('a-0000', 'nope', long)).toBeNull();
    expect(shortestPath('a-0000', 'a-0000', long)).toEqual(['a-0000']);
  });

  it('respects the relation filter when travelling', () => {
    const data = makeResponse(
      [file('a'), file('b'), file('c')],
      [
        { source: 'a', target: 'b', relations: ['imports'] },
        { source: 'b', target: 'c', relations: ['references'] },
      ],
    );
    const index = buildGraphIndex(data);
    expect(shortestPath('a', 'c', index)).toEqual(['a', 'b', 'c']);
    expect(shortestPath('a', 'c', index, ['imports'])).toBeNull();
  });
});

describe('P36R S3 · neighborhood', () => {
  const index = buildGraphIndex(chain(8));

  it('1-hop returns the node and its direct neighbours only', () => {
    expect(neighborhood('a-0003', 1, index).ids).toEqual(['a-0002', 'a-0003', 'a-0004']);
  });

  it('2-hop reaches one step further and is a superset of 1-hop', () => {
    const one = neighborhood('a-0003', 1, index).ids;
    const two = neighborhood('a-0003', 2, index).ids;
    expect(two).toEqual(['a-0001', 'a-0002', 'a-0003', 'a-0004', 'a-0005']);
    for (const id of one) expect(two).toContain(id);
  });

  it('bounds the expansion and says so', () => {
    const star = makeResponse(
      [file('hub'), ...Array.from({ length: 90 }, (_, i) => file(`leaf-${String(i).padStart(3, '0')}`))],
      Array.from({ length: 90 }, (_, i) => ({
        source: 'hub',
        target: `leaf-${String(i).padStart(3, '0')}`,
        relations: ['imports'],
      })),
    );
    const hood = neighborhood('hub', 1, buildGraphIndex(star));
    expect(hood.truncated).toBe(true);
    expect(hood.ids.length).toBe(MAX_NEIGHBORHOOD_NODES);
  });

  it('returns nothing for an unknown node — never a fabricated set', () => {
    expect(neighborhood('ghost', 2, index)).toEqual({ ids: [], truncated: false });
  });
});

// --- 6. the reducer is the ONE mutation path ---------------------------------

describe('P36R S3 · applyGraphAction', () => {
  const index = buildGraphIndex(FIXTURE);
  const base = initialGraphViewState();
  const apply = (state: GraphViewState, ...actions: Parameters<typeof applyGraphAction>[1][]) =>
    actions.reduce((s, a) => applyGraphAction(s, a, index), state);

  it('setMode switches between the two permanent modes', () => {
    expect(apply(base, { kind: 'setMode', mode: 'browse' }).mode).toBe('browse');
    expect(apply(base, { kind: 'setMode', mode: 'explore' }).mode).toBe('explore');
  });

  it('select stores a real id and REFUSES an unknown one with a notice', () => {
    expect(apply(base, { kind: 'select', nodeId: 'src/fake_mod.py' }).selectedId).toBe(
      'src/fake_mod.py',
    );
    const bad = apply(base, { kind: 'select', nodeId: 'ghost' });
    expect(bad.selectedId).toBeNull();
    expect(bad.notice).toEqual({ kind: 'not_found', token: 'ghost' });
  });

  it('select RESOLVES its token the way neighbors and path do', () => {
    // A pointer click sends an exact id and is unaffected (byId, first tier)…
    expect(apply(base, { kind: 'select', nodeId: 'src/fake_mod.py' }).selectedId).toBe(
      'src/fake_mod.py',
    );
    // …a typed or proposed basename resolves instead of failing…
    expect(apply(base, { kind: 'select', nodeId: 'fake_mod.py' }).selectedId).toBe(
      'src/fake_mod.py',
    );
    // …and an ambiguous token stops with the SAME bounded candidate list the
    // other actions build, so a caller never has to rebuild that notice.
    const amb = apply(base, { kind: 'select', nodeId: 'mod' });
    expect(amb.selectedId).toBeNull();
    expect(amb.notice).toEqual({
      kind: 'ambiguous',
      token: 'mod',
      candidates: ['src/fake_mod.py', 'src/other_mod.py'],
    });
    // null still means "clear the selection", not "resolve the empty string".
    const cleared = apply(base, { kind: 'select', nodeId: 'src/fake_mod.py' }, {
      kind: 'select',
      nodeId: null,
    });
    expect(cleared.selectedId).toBeNull();
    expect(cleared.notice).toBeNull();
  });

  it('filterCommunity resolves a cluster by id OR name and refuses the rest', () => {
    expect(apply(base, { kind: 'filterCommunity', id: '131' }).communityFilter).toBe('131');
    expect(apply(base, { kind: 'filterCommunity', id: 'Export Pipeline' }).communityFilter).toBe(
      '131',
    );
    const miss = apply(base, { kind: 'filterCommunity', id: 'no-such-cluster' });
    // The filter is left alone — a garbage token must not silently produce an
    // empty view that looks like an answer.
    expect(miss.communityFilter).toBe('all');
    expect(miss.notice).toEqual({ kind: 'community_not_found', token: 'no-such-cluster' });
    expect(apply(base, { kind: 'filterCommunity', id: 'all' }).notice).toBeNull();
    expect(apply(base, { kind: 'filterCommunity', id: 'all' }).communityFilter).toBe('all');
  });

  it('filterRelation NAMES the values it could not apply', () => {
    const mixed = apply(base, { kind: 'filterRelation', relations: ['imports', 'bogus'] });
    expect(mixed.relationFilter).toEqual(['imports']);
    expect(mixed.notice).toEqual({ kind: 'relation_unknown', tokens: ['bogus'] });
    // All-unknown draws nothing — but says why, instead of a blank canvas.
    const blank = apply(base, { kind: 'filterRelation', relations: ['bogus'] });
    expect(blank.relationFilter).toEqual([]);
    expect(blank.notice).toEqual({ kind: 'relation_unknown', tokens: ['bogus'] });
    expect(apply(base, { kind: 'filterRelation', relations: ['imports'] }).notice).toBeNull();
  });

  it('an UNRECOGNISED action returns the state untouched, never the action object', () => {
    // Unreachable through today's typed dispatch; reachable the moment free
    // text or URL state is parsed into an action. Returning the action put
    // `undefined` in state.view and threw in viewBoxOf.
    const out = applyGraphAction(base, { kind: 'not-an-action' } as unknown as GraphAction, index);
    expect(out).toBe(base);
    expect(() => viewBoxOf(out.view)).not.toThrow();
  });

  it('search / filterType / filterCommunity narrow the node set', () => {
    expect(filteredNodeIds(apply(base, { kind: 'search', query: 'other' }), index)).toEqual([
      'src/other_mod.py',
    ]);
    const conceptsOnly = apply(base, { kind: 'filterType', value: 'concept' });
    expect(filteredNodeIds(conceptsOnly, index)).toEqual(['concept-governance', 'concept-provenance']);
    const c131 = apply(base, { kind: 'filterCommunity', id: '131' });
    expect(filteredNodeIds(c131, index)).toEqual(['concept-provenance', 'src/fake_mod.py']);
  });

  it('filterRelation keeps only known relation values and filters the drawn edges', () => {
    const onlyImports = apply(base, { kind: 'filterRelation', relations: ['imports', 'bogus'] });
    expect(onlyImports.relationFilter).toEqual(['imports']);
    const visible = new Set(visibleNodeIds(onlyImports, index));
    expect(visibleEdges(onlyImports, index, visible).length).toBe(1);
    const none = apply(base, { kind: 'filterRelation', relations: ['references'] });
    expect(visibleEdges(none, index, new Set(visibleNodeIds(none, index))).length).toBe(0);
  });

  it('neighbors sets a bounded focus and an honest notice', () => {
    const s = apply(base, { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 1 });
    expect(s.focus).toEqual({
      kind: 'neighbors',
      nodeId: 'src/fake_mod.py',
      depth: 1,
      ids: ['src/fake_mod.py', 'src/other_mod.py'],
      truncated: false,
    });
    expect(s.notice).toMatchObject({ kind: 'neighborhood', count: 2 });
    expect(filteredNodeIds(s, index)).toEqual(['src/fake_mod.py', 'src/other_mod.py']);
  });

  it('a successful neighbourhood or path FRAMES its result (no speck in an empty field)', () => {
    const hood = apply(base, { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 1 });
    expect(hood.view).toEqual(fitViewport(visibleNodeIds(hood, index), hood, index));
    expect(hood.view).not.toEqual(base.view);

    const routed = apply(base, { kind: 'path', from: 'fake_mod.py', to: 'other_mod.py' });
    expect(routed.view).toEqual(fitViewport(visibleNodeIds(routed, index), routed, index));
    expect(routed.view).not.toEqual(base.view);

    // …but a REFUSAL never moves the viewport.
    expect(apply(base, { kind: 'path', from: 'ghost', to: 'src/fake_mod.py' }).view).toEqual(
      base.view,
    );
    expect(
      apply(base, { kind: 'path', from: 'src/fake_mod.py', to: 'docs/fake-note.md' }).view,
    ).toEqual(base.view);
  });

  it('neighbors on an ambiguous token stops with candidates and changes nothing else', () => {
    const s = apply(base, { kind: 'neighbors', nodeId: 'mod', depth: 1 });
    expect(s.focus).toBeNull();
    expect(s.selectedId).toBeNull();
    expect(s.notice).toEqual({
      kind: 'ambiguous',
      token: 'mod',
      candidates: ['src/fake_mod.py', 'src/other_mod.py'],
    });
  });

  it('path found: focus carries the ORDERED route and the visibility set', () => {
    const s = apply(base, { kind: 'path', from: 'fake_mod.py', to: 'other_mod.py' });
    expect(s.focus).toEqual({
      kind: 'path',
      from: 'src/fake_mod.py',
      to: 'src/other_mod.py',
      ids: ['src/fake_mod.py', 'src/other_mod.py'],
      ordered: ['src/fake_mod.py', 'src/other_mod.py'],
    });
    expect(s.notice).toEqual({
      kind: 'path_found',
      from: 'src/fake_mod.py',
      to: 'src/other_mod.py',
      hops: 1,
    });
  });

  it('path NOT found: no focus, an explicit no_path notice, nothing invented', () => {
    const s = apply(base, { kind: 'path', from: 'src/fake_mod.py', to: 'docs/fake-note.md' });
    expect(s.focus).toBeNull();
    expect(s.notice).toEqual({
      kind: 'no_path',
      from: 'src/fake_mod.py',
      to: 'docs/fake-note.md',
    });
  });

  it('path with an unknown or ambiguous endpoint refuses instead of guessing', () => {
    expect(apply(base, { kind: 'path', from: 'ghost', to: 'src/fake_mod.py' }).notice).toEqual({
      kind: 'not_found',
      token: 'ghost',
    });
    expect(apply(base, { kind: 'path', from: 'src/fake_mod.py', to: 'mod' }).notice).toMatchObject({
      kind: 'ambiguous',
      token: 'mod',
    });
  });

  it('pan / zoom / fit / reset are pure viewport transitions', () => {
    const panned = apply(base, { kind: 'pan', dx: 40, dy: -25 });
    expect(panned.view).toEqual({ cx: 40, cy: -25, scale: 1 });

    let zoomed = base;
    for (let i = 0; i < 40; i += 1) zoomed = apply(zoomed, { kind: 'zoom', factor: 2 });
    expect(zoomed.view.scale).toBe(MAX_SCALE);
    for (let i = 0; i < 80; i += 1) zoomed = apply(zoomed, { kind: 'zoom', factor: 0.5 });
    expect(zoomed.view.scale).toBe(MIN_SCALE);

    const fitted = apply(base, { kind: 'fit' });
    expect(fitted.view).toEqual(fitViewport(visibleNodeIds(base, index), base, index));

    const dirty = apply(panned, { kind: 'moveNode', nodeId: 'src/fake_mod.py', x: 5, y: 6 });
    expect(nodePosition('src/fake_mod.py', dirty, index)).toEqual({ x: 5, y: 6 });
    const reset = apply(dirty, { kind: 'reset' });
    expect(reset.view).toEqual({ cx: 0, cy: 0, scale: 1 });
    expect(reset.moved).toEqual({});
    expect(nodePosition('src/fake_mod.py', reset, index)).toEqual(
      index.layout.get('src/fake_mod.py'),
    );
  });

  it('moveNode refuses an unknown node', () => {
    expect(apply(base, { kind: 'moveNode', nodeId: 'ghost', x: 1, y: 1 })).toEqual(base);
  });

  it('clearFilters resets search/filters/focus but keeps the selection', () => {
    const dirty = apply(
      base,
      { kind: 'select', nodeId: 'src/fake_mod.py' },
      { kind: 'search', query: 'other' },
      { kind: 'filterType', value: 'file' },
      { kind: 'filterCommunity', id: '131' },
      { kind: 'filterRelation', relations: ['imports'] },
      { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 2 },
    );
    const cleared = apply(dirty, { kind: 'clearFilters' });
    expect(cleared.search).toBe('');
    expect(cleared.typeFilter).toBe('all');
    expect(cleared.communityFilter).toBe('all');
    expect(cleared.relationFilter).toBeNull(); // null = no filter, not "none"
    expect(cleared.focus).toBeNull();
    expect(cleared.selectedId).toBe('src/fake_mod.py');
  });

  it('clearFocus and dismissNotice are narrow, not blanket resets', () => {
    const focused = apply(base, { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 1 });
    expect(apply(focused, { kind: 'clearFocus' }).focus).toBeNull();
    expect(apply(focused, { kind: 'clearFocus' }).selectedId).toBe('src/fake_mod.py');
    expect(apply(focused, { kind: 'dismissNotice' }).notice).toBeNull();
    expect(apply(focused, { kind: 'dismissNotice' }).focus).not.toBeNull();
  });
});

// --- 7. selectors + palette ---------------------------------------------------

describe('P36R S3 · selectors', () => {
  const index = buildGraphIndex(FIXTURE);

  it('connectedNodes honours the relation filter', () => {
    const base = initialGraphViewState();
    expect(connectedNodes('src/fake_mod.py', base, index).map((n) => n.id)).toEqual([
      'src/other_mod.py',
    ]);
    const filtered = applyGraphAction(base, { kind: 'filterRelation', relations: ['calls'] }, index);
    expect(connectedNodes('src/fake_mod.py', filtered, index)).toEqual([]);
  });

  it('fitViewport frames the given nodes and degrades to the identity view', () => {
    expect(fitViewport([], initialGraphViewState(), index)).toEqual({ cx: 0, cy: 0, scale: 1 });
    const v = fitViewport(index.renderIds, initialGraphViewState(), index);
    expect(Number.isFinite(v.cx) && Number.isFinite(v.cy)).toBe(true);
    expect(v.scale).toBeGreaterThanOrEqual(MIN_SCALE);
    expect(v.scale).toBeLessThanOrEqual(MAX_SCALE);
  });

  it('community colours are BOUNDED — beyond the palette a cluster is neutral', () => {
    const many = makeResponse(
      Array.from({ length: 20 }, (_, i) => file(`f-${i}`, `c-${i}`)),
      [],
      Array.from({ length: 20 }, (_, i) => ({
        id: `c-${i}`,
        name: `cluster ${i}`,
        file_count: 20 - i,
      })),
    );
    const idx: GraphIndex = buildGraphIndex(many);
    const slots = idx.communitiesBySize.map((c) => communityColorIndex(c.id, idx));
    expect(slots.slice(0, PALETTE_SLOTS)).toEqual([...Array(PALETTE_SLOTS).keys()]);
    expect(slots.slice(PALETTE_SLOTS).every((s) => s === null)).toBe(true);
    expect(communityColorIndex(null, idx)).toBeNull();
    expect(communityColorIndex('not-a-cluster', idx)).toBeNull();
  });

  it('cluster labels never carry two adjacent parentheticals, and collisions show the id', () => {
    // Upstream names ALREADY carry a disambiguating parenthetical, e.g.
    // "Official schema v1.05 (28)". Appending "(13)" for the file count would
    // put two numbers of different kinds side by side.
    const data = makeResponse(
      [file('x', '41'), file('y', '52')],
      [],
      [
        { id: '41', name: 'Official schema v1.05 (28)', file_count: 13 },
        { id: '52', name: 'Official schema v1.05 (28)', file_count: 4 },
      ],
    );
    const idx = buildGraphIndex(data);
    const [big, small] = idx.communitiesBySize;
    expect(communityOptionLabel(big)).toBe('Official schema v1.05 (28) · 13 files');
    expect(communityOptionLabel(big)).not.toMatch(/\)\s*\(/);
    // Same name in the peer set ⇒ the cluster id, which is what actually
    // distinguishes them in the data. No invented name.
    expect(communityLabelAmong(big, idx.communitiesBySize)).toBe(
      'Official schema v1.05 (28) · cluster 41 · 13 files',
    );
    expect(communityLabelAmong(big, idx.communitiesBySize)).not.toMatch(/\)\s*\(/);
    // A unique name keeps the plain form.
    expect(communityLabelAmong(small, [small])).toBe('Official schema v1.05 (28) · 4 files');
  });

  it('ranks clusters by file_count descending and flags singletons honestly', () => {
    const data = makeResponse(
      [file('x', 'big'), file('y', 'big'), file('z', 'small')],
      [],
      [
        { id: 'small', name: 'z.py', file_count: 1 },
        { id: 'big', name: 'Export Pipeline', file_count: 2 },
      ],
    );
    const idx = buildGraphIndex(data);
    expect(idx.communitiesBySize.map((c) => c.id)).toEqual(['big', 'small']);
    expect(idx.communitiesBySize.map((c) => c.isSingleton)).toEqual([false, true]);
    expect(idx.counts.singletonCommunities).toBe(1);
  });
});

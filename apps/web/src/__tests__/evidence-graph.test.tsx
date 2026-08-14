import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { EvidenceGraphPanel } from '../screens/graph/EvidenceGraphPanel';
import {
  EDGE_PRODUCERS,
  EVIDENCE_EDGE_KINDS,
  EVIDENCE_GRAPH_DISCLOSURE,
  buildEvidenceGraph,
  emptyRunCheckStore,
  evidenceGraphFreshnessKey,
  evidenceTreeRows,
  initialEvidenceGraphState,
  nodeIds,
  readRunCheck,
  rekeyRunCheckStore,
  visibleEvidenceNodeIds,
  writeRunCheck,
  type EvidenceGraph,
  type EvidenceGraphInput,
} from '../lib/evidenceGraph';
import {
  EXP_ID,
  evidenceBundleRoutes,
  experimentDetail,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type {
  ApiEvidenceClassification,
  ApiEvidenceEntry,
  ApiExperimentDetail,
  ApiRunCheckResponse,
  ApiRunView,
} from '../lib/types';

/*
 * The EVIDENCE GRAPH — one experiment, shaped around its runs.
 *
 * What this file exists to hold in place, in the order it matters:
 *
 *  · EVERY node and EVERY edge derives from stored schema, provenance, evidence
 *    or validation state, and names which — checked mechanically against the
 *    closed producer lists, not asserted in a comment;
 *  · an edge with NO backing state cannot be produced, however plausible it
 *    looks — the negative controls below are the point of the whole slice;
 *  · runs are COLLAPSED on the first paint, and opening one fetches that run's
 *    findings and nobody else's;
 *  · a moved version token evicts the one cache rather than serving it;
 *  · the disclosure is on screen, verbatim;
 *  · every relationship is reachable without seeing the layout.
 */

vi.setConfig({ testTimeout: 30000 });

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- fixtures (synthetic, unmistakably fake) --------------------------------

const GRAPH_EXP = '01SYNTHEVGRAPHEXP000000000';
const RUN_A = '01SYNTHEVGRAPHRUNA00000000';
const RUN_B = '01SYNTHEVGRAPHRUNB00000000';

const detailFixture = (over: Partial<ApiExperimentDetail> = {}): ApiExperimentDetail =>
  ({
    ...experimentDetail,
    id: GRAPH_EXP,
    title: 'Synthetic XANES — evidence graph fixture',
    ...over,
  }) as ApiExperimentDetail;

/**
 * The EXPERIMENT-level trail.
 *
 * `context.environment` deliberately carries EXACTLY TWO entries: it is the only
 * shape from which a `conflicts_with` edge may be drawn.
 */
const evidenceFixture: ApiEvidenceEntry[] = [
  {
    path: 'sample.material.formula',
    value: 'CuO2',
    status: 'verified',
    evidence: [
      {
        source_type: 'spreadsheet',
        source_file: 'mock_campaign.csv',
        locator: "Sheet 'Sample', field=formula",
        quote: 'CuO2',
      },
    ],
  },
  {
    path: 'context.environment',
    value: 'in_situ',
    status: 'needs_confirmation',
    evidence: [
      {
        source_type: 'spreadsheet',
        source_file: 'mock_campaign.csv',
        locator: "Sheet 'Campaign Info', field=environment",
        quote: 'in_situ',
      },
      {
        source_type: 'file_listing',
        source_file: 'raw_scan_listing.txt',
        locator: 'line 4',
        quote: 'ex_situ',
      },
    ],
  },
];

const classificationFixture = (
  over: Partial<ApiEvidenceClassification> = {},
): ApiEvidenceClassification => ({
  record_rev: 3,
  // All six classes, because the contract says the histogram sums to
  // `field_results.length` over the SAME axis — a fixture missing a key models
  // a response the backend does not send.
  counts: {
    supported: 1,
    inferred_candidate: 0,
    insufficient_evidence: 0,
    conflicting_evidence: 1,
    unknown: 0,
    unreadable: 0,
  },
  field_results: [
    {
      field: 'context.environment',
      classification: 'conflicting_evidence',
      value_state: 'candidate',
      explanation: 'Two recorded entries disagree about the environment.',
      sources: [],
    },
  ],
  ...over,
});

/**
 * Run A — one address in each of the five grouped kinds, so every containment
 * edge kind has a producer that actually fires.
 */
const runA = (over: Partial<ApiRunView> = {}): ApiRunView =>
  ({
    id: RUN_A,
    experiment_id: GRAPH_EXP,
    label: 'Run 1',
    ordinal: 1,
    created_utc: '2099-04-02T09:05:00Z',
    updated_utc: '2099-04-02T09:05:00Z',
    rev: 0,
    version: 'rA.0',
    record_id: null,
    fields: {
      'sample.material.name': {
        value: 'Synthetic CuO powder',
        status: 'verified',
        evidence: [
          {
            source_type: 'spreadsheet',
            source_file: 'mock_campaign.csv',
            locator: "Sheet 'Sample', row 2",
          },
        ],
      },
      'measurement.edge_energy_eV': {
        value: 8979,
        status: 'verified',
        evidence: [{ source_type: 'derivation', rule: 'edge energy = Cu K-edge tabulated value' }],
      },
      'context.temperature_K': { value: 300, status: 'verified', evidence: [] },
      'assets[0].filename': {
        value: 'scan_001.dat',
        status: 'verified',
        evidence: [{ source_type: 'file_listing', source_file: 'raw_scan_listing.txt' }],
      },
      'descriptors.outputs[0].descriptors[0].name': {
        value: 'whiteline_position',
        status: 'verified',
        evidence: [
          {
            source_type: 'user_confirmation',
            question: 'Is whiteline_position the descriptor you computed?',
            answer: 'yes',
            timestamp: '2099-04-02T10:00:00Z',
          },
        ],
      },
    },
    inherited: {
      // `inherited` → draws `derived_from` UP to the experiment node that holds
      // the evidence, rather than copying the evidence down onto the run.
      'field:sample.material.formula': {
        state: 'inherited',
        payload: { value: 'CuO2', status: 'verified', evidence: [] },
        inherited_payload: { value: 'CuO2', status: 'verified', evidence: [] },
        overridable: true,
      },
      // `absent` → draws NOTHING. The whole point of "only where data exists".
      'field:sample.material.batch_id': {
        state: 'absent',
        payload: null,
        inherited_payload: null,
        overridable: false,
      },
    },
    ...over,
  }) as unknown as ApiRunView;

/**
 * Run B — carries the SAME sample material name as Run A, and cites a DIFFERENT
 * source file. Both halves are deliberate: the matching value is the temptation
 * the negative control tests, and the different file keeps that control clean of
 * the (legitimate) join a genuinely shared source would create.
 */
const runB = (over: Partial<ApiRunView> = {}): ApiRunView =>
  ({
    id: RUN_B,
    experiment_id: GRAPH_EXP,
    label: 'Run 2',
    ordinal: 2,
    created_utc: '2099-04-02T11:05:00Z',
    updated_utc: '2099-04-02T11:05:00Z',
    rev: 0,
    version: 'rB.0',
    record_id: null,
    fields: {
      'sample.material.name': {
        value: 'Synthetic CuO powder',
        status: 'verified',
        evidence: [
          {
            source_type: 'spreadsheet',
            source_file: 'second_campaign.csv',
            locator: "Sheet 'Sample', row 9",
          },
        ],
      },
    },
    inherited: {},
    ...over,
  }) as unknown as ApiRunView;

const checkFixture = (over: Partial<ApiRunCheckResponse> = {}): ApiRunCheckResponse => ({
  ok: false,
  // A BARE blocker (no `path`) attaches to the run itself, which is what makes it
  // visible as soon as the run is opened.
  blockers: ['This run has no measurement series recorded.'],
  draft: { ok: true, errors: [] },
  official: { ok: false, errors: [], dry_run: true },
  checked_run_version: 'rA.0',
  ...over,
});

const inputFixture = (over: Partial<EvidenceGraphInput> = {}): EvidenceGraphInput => ({
  detail: detailFixture(),
  runs: [runA(), runB()],
  runsMeta: { total: 2, matched: 2, returned: 2, offset: 0 },
  evidence: evidenceFixture,
  classification: classificationFixture(),
  checks: {},
  focusRunId: null,
  ...over,
});

function buildOk(over: Partial<EvidenceGraphInput> = {}): EvidenceGraph {
  const result = buildEvidenceGraph(inputFixture(over));
  if (!result.ok) throw new Error(`expected a graph, got ${result.reason}`);
  return result.graph;
}

/** Every node id in the containment subtree under `rootId`, inclusive. */
function subtreeOf(graph: EvidenceGraph, rootId: string): Set<string> {
  const out = new Set<string>();
  const walk = (id: string) => {
    if (out.has(id)) return;
    out.add(id);
    for (const child of graph.childrenOf.get(id) ?? []) walk(child);
  };
  walk(rootId);
  return out;
}

// ===========================================================================
// 1 · derivation — every node and every edge traces to stored state
// ===========================================================================

describe('evidence graph · derivation from stored state', () => {
  it('builds Experiment → Run 1 → Run 2 from the runs listing', () => {
    const graph = buildOk();
    const root = nodeIds.experiment(GRAPH_EXP);

    expect(graph.rootId).toBe(root);
    expect(graph.byId.get(root)?.kind).toBe('experiment');
    // Server order, not a re-sort — a re-sort would put Run 10 before Run 2.
    expect(graph.runOrder).toEqual([nodeIds.run(RUN_A), nodeIds.run(RUN_B)]);

    const hasRun = graph.edges.filter((e) => e.kind === 'has_run');
    expect(hasRun.map((e) => e.target).sort()).toEqual(
      [nodeIds.run(RUN_A), nodeIds.run(RUN_B)].sort(),
    );
    expect(hasRun.every((e) => e.source === root)).toBe(true);
  });

  it('emits a grounded child only for the kinds the run actually resolves', () => {
    const graph = buildOk();
    const runNode = nodeIds.run(RUN_A);
    const kinds = (graph.childrenOf.get(runNode) ?? [])
      .map((id) => graph.byId.get(id)?.kind)
      .filter(Boolean);

    // Run A carries a sample, a context, a measurement, an asset and a descriptor.
    for (const kind of ['sample', 'context', 'measurement', 'asset', 'descriptor']) {
      expect(kinds, `Run 1 should carry a ${kind}`).toContain(kind);
    }

    // Run B carries ONLY a sample. Nothing is invented to make the two runs
    // look alike.
    const bKinds = (graph.childrenOf.get(nodeIds.run(RUN_B)) ?? []).map(
      (id) => graph.byId.get(id)?.kind,
    );
    expect(bKinds).toEqual(['sample']);
  });

  it('draws nothing at all for an address the server resolved as `absent`', () => {
    const graph = buildOk();
    const everyAddress = graph.nodes
      .flatMap((n) => n.detail)
      .filter((line) => line.term === 'Address')
      .map((line) => line.value);
    expect(everyAddress).not.toContain('sample.material.batch_id');
  });

  it('EVERY emitted edge carries a producer declared for its own kind', () => {
    const graph = buildOk({ checks: { [RUN_A]: checkFixture() } });
    expect(graph.edges.length).toBeGreaterThan(0);

    for (const edge of graph.edges) {
      expect(EVIDENCE_EDGE_KINDS, `unknown edge kind ${edge.kind}`).toContain(edge.kind);
      expect(
        EDGE_PRODUCERS[edge.kind],
        `${edge.kind} carried an undeclared producer: ${edge.producer}`,
      ).toContain(edge.producer);
      // An edge that cannot say WHY it exists is an edge a reader cannot check.
      expect(edge.why.trim().length).toBeGreaterThan(0);
    }
  });

  it('EVERY emitted node carries a declared producer, and both endpoints of every edge exist', () => {
    const graph = buildOk({ checks: { [RUN_A]: checkFixture() } });
    for (const node of graph.nodes) {
      expect(node.producer.trim().length).toBeGreaterThan(0);
    }
    for (const edge of graph.edges) {
      expect(graph.byId.has(edge.source)).toBe(true);
      expect(graph.byId.has(edge.target)).toBe(true);
    }
  });

  it('exercises all ten permitted edge kinds from stored state alone', () => {
    const graph = buildOk({ checks: { [RUN_A]: checkFixture() } });
    const kinds = new Set(graph.edges.map((e) => e.kind));

    // The nine that this fixture's stored state supports.
    for (const kind of [
      'has_run',
      'performed_on',
      'measured_under',
      'has_context',
      'has_descriptor',
      'references',
      'supported_by',
      'derived_from',
      'validated_by',
      'conflicts_with',
    ]) {
      expect(kinds, `no ${kind} edge was produced`).toContain(kind);
    }
    // And nothing outside the closed vocabulary.
    for (const kind of kinds) expect(EVIDENCE_EDGE_KINDS).toContain(kind);
  });

  it('a run reading the experiment’s value derives from the EXPERIMENT node, not a copy', () => {
    const graph = buildOk();
    const derived = graph.edges.filter(
      (e) => e.kind === 'derived_from' && e.label === 'inherited',
    );
    expect(derived.length).toBe(1);
    // …and it points at a node owned by the experiment, not by the run.
    const target = graph.byId.get(derived[0].target);
    expect(target?.runId).toBeNull();
    expect(derived[0].producer).toBe(EDGE_PRODUCERS.derived_from[1]);
  });

  it('a validation finding belongs to the run whose check produced it', () => {
    const graph = buildOk({ checks: { [RUN_A]: checkFixture() } });
    const findings = graph.nodes.filter((n) => n.kind === 'validation_finding');
    expect(findings.length).toBe(1);
    expect(findings[0].runId).toBe(RUN_A);
    // A run with no check fetched contributes no findings — and that is stated.
    expect(graph.notes.map((n) => n.kind)).toContain('checks_on_demand');
  });
});

// ===========================================================================
// 2 · the negative controls — an edge with no backing state cannot exist
// ===========================================================================

describe('evidence graph · no invented edge', () => {
  it('does NOT join two runs that record the identical sample value', () => {
    const graph = buildOk();
    const a = subtreeOf(graph, nodeIds.run(RUN_A));
    const b = subtreeOf(graph, nodeIds.run(RUN_B));

    // Both runs record the same material name. A graph that "helpfully" joined
    // them would be asserting an identity nothing recorded.
    const crossing = graph.edges.filter(
      (e) => (a.has(e.source) && b.has(e.target)) || (b.has(e.source) && a.has(e.target)),
    );
    expect(crossing).toEqual([]);

    /*
     * The same claim again, stated over run OWNERSHIP rather than over the
     * containment tree — because the first form is only as strong as the tree
     * is, and a defect that merges two runs' nodes would corrupt the tree and
     * the assertion together. Ownership is read off the node, so it survives
     * that: no edge may join a node owned by one run to a node owned by
     * another. (Endpoints owned by NO run are experiment-level and are exactly
     * how a run legitimately reaches shared state.)
     */
    for (const edge of graph.edges) {
      const from = graph.byId.get(edge.source)?.runId ?? null;
      const to = graph.byId.get(edge.target)?.runId ?? null;
      if (from !== null && to !== null) {
        expect(from, `${edge.kind} joined two different runs`).toBe(to);
      }
    }

    // And no node is shared between two runs in the first place.
    const aOwned = graph.nodes.filter((n) => n.runId === RUN_A).map((n) => n.id);
    const bOwned = new Set(graph.nodes.filter((n) => n.runId === RUN_B).map((n) => n.id));
    expect(aOwned.filter((id) => bOwned.has(id))).toEqual([]);
  });

  it('does NOT order runs in time, however suggestive `created_utc` is', () => {
    const graph = buildOk();
    const between = graph.edges.filter(
      (e) =>
        (e.source === nodeIds.run(RUN_A) && e.target === nodeIds.run(RUN_B)) ||
        (e.source === nodeIds.run(RUN_B) && e.target === nodeIds.run(RUN_A)),
    );
    expect(between).toEqual([]);
  });

  it('refuses `conflicts_with` when the classified address has THREE entries', () => {
    // The stored state says the entries disagree. It does NOT say WHICH PAIR,
    // and drawing all three pairs would be an invention.
    const threeEntries: ApiEvidenceEntry[] = [
      {
        ...evidenceFixture[1],
        evidence: [
          ...evidenceFixture[1].evidence,
          { source_type: 'document', source_file: 'third_note.txt', locator: 'p1' },
        ],
      },
    ];
    const graph = buildOk({ evidence: threeEntries });

    expect(graph.edges.filter((e) => e.kind === 'conflicts_with')).toEqual([]);
    expect(graph.notes.map((n) => n.kind)).toContain('conflict_pair_unknown');
  });

  it('refuses `conflicts_with` when the classified address carries NO stored entries', () => {
    // The classification names a field the trail does not hold. There is nothing
    // to join, so nothing is joined — and no placeholder entry is conjured.
    const graph = buildOk({
      classification: classificationFixture({
        field_results: [
          {
            field: 'sample.material.purity',
            classification: 'conflicting_evidence',
            value_state: 'candidate',
            explanation: 'Recorded entries disagree.',
            sources: [],
          },
        ],
      }),
    });
    expect(graph.edges.filter((e) => e.kind === 'conflicts_with')).toEqual([]);
  });

  it('drops an evidence item that carries no readable source type, and says so', () => {
    const graph = buildOk({
      evidence: [
        {
          path: 'sample.material.formula',
          value: 'CuO2',
          status: 'verified',
          // Neither item can be described. Nothing is invented in their place.
          evidence: [{} as never, { source_type: '' } as never],
        },
      ],
    });
    // Scoped to the EXPERIMENT level, which is the trail this case replaced —
    // the runs still carry their own (readable) evidence and are unaffected,
    // which is the isolation the backend contract promises entry by entry.
    expect(graph.nodes.filter((n) => n.kind === 'evidence_entry' && n.runId === null)).toEqual(
      [],
    );
    expect(graph.notes.map((n) => n.kind)).toContain('unreadable_evidence');
  });

  it('does NOT model an address outside the five grounded kinds — it counts it', () => {
    const graph = buildOk({
      runs: [
        runA({
          fields: {
            'system.instrument': { value: 'BL 7-3', status: 'verified', evidence: [] },
          } as unknown as ApiRunView['fields'],
          inherited: {},
        }),
      ],
      runsMeta: { total: 1, matched: 1, returned: 1, offset: 0 },
    });
    // `system.*` is a real address this view does not draw. Guessing it into
    // "Measurement" because an instrument feels measurement-ish is exactly the
    // invention this graph refuses.
    expect(graph.nodes.some((n) => n.label === 'BL 7-3')).toBe(false);
    const note = graph.notes.find((n) => n.kind === 'unmodelled_addresses');
    expect(note?.text).toContain('system');
  });

  it('never names a repository path, a module or a Graphify concept', () => {
    const graph = buildOk({ checks: { [RUN_A]: checkFixture() } });
    const corpus = [
      ...graph.nodes.flatMap((n) => [n.label, n.producer, ...n.detail.map((d) => d.value)]),
      ...graph.edges.flatMap((e) => [e.why, e.producer, e.label ?? '']),
      ...graph.notes.map((n) => n.text),
    ].join('\n');

    // This is a scientist looking at their experiment, not a codebase browser.
    for (const forbidden of ['graphify', 'apps/web', 'apps/api', 'src/isaac', '.tsx', '.py']) {
      expect(corpus.toLowerCase()).not.toContain(forbidden.toLowerCase());
    }
  });
});

// ===========================================================================
// 3 · shape, bounds and progressive disclosure
// ===========================================================================

describe('evidence graph · collapsed by default and bounded', () => {
  it('opens on the experiment with EVERY run collapsed', () => {
    const graph = buildOk();
    const state = initialEvidenceGraphState(graph);

    expect(graph.anchorId).toBe(graph.rootId);
    expect(state.expanded).toEqual([graph.rootId]);

    const visible = new Set(visibleEvidenceNodeIds(state, graph));
    // Both runs are on screen…
    expect(visible.has(nodeIds.run(RUN_A))).toBe(true);
    expect(visible.has(nodeIds.run(RUN_B))).toBe(true);
    // …and NOTHING underneath either of them is, which is what "collapsed"
    // means here. (The experiment's OWN evidence groups are visible beside the
    // runs — they are direct children of the expanded anchor and are real
    // recorded state, so they are drawn where they belong.)
    for (const runNode of [nodeIds.run(RUN_A), nodeIds.run(RUN_B)]) {
      for (const child of graph.childrenOf.get(runNode) ?? []) {
        expect(visible.has(child)).toBe(false);
      }
    }
    // Every drawn node is the root or a DIRECT child of it — depth one, exactly.
    for (const id of visible) {
      if (id === graph.rootId) continue;
      expect(graph.byId.get(id)?.parentId).toBe(graph.rootId);
    }
  });

  it('expanding ONE run reveals that run’s children and nobody else’s', () => {
    const graph = buildOk();
    const state = initialEvidenceGraphState(graph);
    const opened = { ...state, expanded: [graph.rootId, nodeIds.run(RUN_A)] };

    const visible = new Set(visibleEvidenceNodeIds(opened, graph));
    for (const child of graph.childrenOf.get(nodeIds.run(RUN_A)) ?? []) {
      expect(visible.has(child)).toBe(true);
    }
    // Run B stays a single node…
    for (const child of graph.childrenOf.get(nodeIds.run(RUN_B)) ?? []) {
      expect(visible.has(child)).toBe(false);
    }
    // …and Run A's GRANDchildren stay closed: expansion is one level, not a
    // cascade of every descendant.
    const firstChild = (graph.childrenOf.get(nodeIds.run(RUN_A)) ?? [])[0];
    for (const grandchild of graph.childrenOf.get(firstChild) ?? []) {
      expect(visible.has(grandchild)).toBe(false);
    }
  });

  it('says when the run list it drew was bounded, rather than implying it is complete', () => {
    const graph = buildOk({ runsMeta: { total: 320, matched: 320, returned: 2, offset: 0 } });
    const note = graph.notes.find((n) => n.kind === 'runs_bounded');
    expect(note?.text).toContain('320');
  });

  it('states an empty run list instead of inventing a run to fill the shape', () => {
    const graph = buildOk({ runs: [], runsMeta: { total: 0, matched: 0, returned: 0, offset: 0 } });
    expect(graph.nodes.filter((n) => n.kind === 'run')).toEqual([]);
    expect(graph.notes.map((n) => n.kind)).toContain('no_runs');
  });

  it('states a focus run that is not loaded rather than guessing which one was meant', () => {
    const graph = buildOk({ focusRunId: '01SYNTHNOTLOADEDRUN0000000' });
    expect(graph.anchorId).toBe(graph.rootId);
    expect(graph.notes.map((n) => n.kind)).toContain('focus_run_unknown');
  });

  it('anchors on the focused run when that run IS loaded', () => {
    const graph = buildOk({ focusRunId: RUN_B });
    expect(graph.anchorId).toBe(nodeIds.run(RUN_B));
  });
});

// ===========================================================================
// 4 · the non-visual equivalent
// ===========================================================================

describe('evidence graph · the tree carries the same model as the canvas', () => {
  it('tree rows and drawn nodes agree over the anchor’s subtree', () => {
    const graph = buildOk({ checks: { [RUN_A]: checkFixture() } });
    const state = { ...initialEvidenceGraphState(graph), expanded: [graph.rootId, nodeIds.run(RUN_A)] };

    const rows = evidenceTreeRows(state, graph);
    const visible = visibleEvidenceNodeIds(state, graph);

    // The tree is not a second traversal free to disagree with the first.
    expect(rows.map((r) => r.id)).toEqual(visible);
    // Depth is real depth, so `aria-level` means something.
    expect(rows.find((r) => r.id === graph.rootId)?.level).toBe(1);
    expect(rows.find((r) => r.id === nodeIds.run(RUN_A))?.level).toBe(2);
  });
});

// ===========================================================================
// 5 · freshness — the one cache is keyed on the authoritative version token
// ===========================================================================

describe('evidence graph · freshness', () => {
  it('keys on the workspace scope and the experiment’s own version token', () => {
    expect(evidenceGraphFreshnessKey(null, '1.0')).toBe('|1.0');
    expect(evidenceGraphFreshnessKey('sess', '1.0')).not.toBe(evidenceGraphFreshnessKey(null, '1.0'));
    expect(evidenceGraphFreshnessKey(null, '1.1')).not.toBe(evidenceGraphFreshnessKey(null, '1.0'));
  });

  it('EVICTS every cached check when the key moves — it does not serve them', () => {
    let store = emptyRunCheckStore('|1.0');
    store = writeRunCheck(store, RUN_A, 'rA.0', checkFixture());
    expect(readRunCheck(store, RUN_A, 'rA.0')).not.toBeNull();

    const rekeyed = rekeyRunCheckStore(store, '|1.1');
    expect(rekeyed.entries).toEqual({});
    expect(readRunCheck(rekeyed, RUN_A, 'rA.0')).toBeNull();
    // Same key → the same object, so an unchanged record costs nothing.
    expect(rekeyRunCheckStore(store, '|1.0')).toBe(store);
  });

  it('refuses a cached check whose RUN version moved, even under the same key', () => {
    let store = emptyRunCheckStore('|1.0');
    store = writeRunCheck(store, RUN_A, 'rA.0', checkFixture());
    // The run advanced. The cached verdict describes a document that no longer
    // exists, so the read is null rather than a stale verdict.
    expect(readRunCheck(store, RUN_A, 'rA.1')).toBeNull();
  });

  it('carries its freshness key on the built graph, so it can be rendered', () => {
    const graph = buildOk();
    expect(graph.freshnessKey).toBe(evidenceGraphFreshnessKey(null, detailFixture().version));
  });

  it('refuses to render a graph read in a different workspace', () => {
    const result = buildEvidenceGraph(inputFixture(), { readIn: 'tutorial', current: null });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe('workspace_scope_changed');
  });
});

// ===========================================================================
// 6 · the rendered panel
// ===========================================================================

function renderPanel(
  over: {
    runs?: ApiRunView[];
    detail?: ApiExperimentDetail;
    focusRunId?: string | null;
    onRequestRunCheck?: (runId: string) => Promise<ApiRunCheckResponse>;
  } = {},
) {
  const onRequestRunCheck =
    over.onRequestRunCheck ?? vi.fn(async () => checkFixture());
  const onFocusRun = vi.fn();
  const runs = over.runs ?? [runA(), runB()];
  const utils = render(
    <EvidenceGraphPanel
      experimentId={GRAPH_EXP}
      detail={over.detail ?? detailFixture()}
      evidence={evidenceFixture}
      classification={classificationFixture()}
      runs={runs}
      runsMeta={{ total: runs.length, matched: runs.length, returned: runs.length, offset: 0 }}
      readInScope={null}
      currentScope={null}
      focusRunId={over.focusRunId ?? null}
      onFocusRun={onFocusRun}
      onRequestRunCheck={onRequestRunCheck}
    />,
  );
  return { ...utils, onRequestRunCheck, onFocusRun };
}

const row = (container: HTMLElement, nodeId: string) =>
  container.querySelector<HTMLLIElement>(`[data-node-id="${CSS.escape(nodeId)}"][role="treeitem"]`);

describe('evidence graph · the rendered panel', () => {
  it('shows the disclosure verbatim', () => {
    /*
     * TWO assertions, because one of them alone tests nothing.
     *
     * Comparing the rendered text to the CONSTANT only proves the component
     * renders whatever the constant says — edit the constant to a paraphrase
     * and both move together, green. So the literal sentence is pinned here as
     * well. A future slice may reword it only by rewording this line too, which
     * is exactly the deliberate act that should be required.
     */
    expect(EVIDENCE_GRAPH_DISCLOSURE).toBe(
      'Edges show recorded schema, evidence, and provenance relationships — not inferred scientific causality.',
    );
    const { getByTestId } = renderPanel();
    expect(getByTestId('evgraph-disclosure').textContent).toBe(EVIDENCE_GRAPH_DISCLOSURE);
  });

  it('renders the runs collapsed, and fetches NO run check on first paint', () => {
    const { container, onRequestRunCheck } = renderPanel();

    expect(row(container, nodeIds.run(RUN_A))).not.toBeNull();
    expect(row(container, nodeIds.run(RUN_B))).not.toBeNull();
    expect(row(container, nodeIds.run(RUN_A))?.getAttribute('aria-expanded')).toBe('false');
    expect(row(container, nodeIds.run(RUN_B))?.getAttribute('aria-expanded')).toBe('false');

    // Nothing on screen is deeper than one level below the experiment.
    const levels = [...container.querySelectorAll<HTMLLIElement>('[role="treeitem"]')].map((r) =>
      r.getAttribute('aria-level'),
    );
    expect(levels.every((l) => l === '1' || l === '2')).toBe(true);

    // And no validation check has been asked for.
    expect(onRequestRunCheck).not.toHaveBeenCalled();
  });

  it('expanding ONE run asks for that run’s findings and nobody else’s', async () => {
    const { container, onRequestRunCheck } = renderPanel();
    const runRow = row(container, nodeIds.run(RUN_A))!;

    fireEvent.keyDown(runRow, { key: 'Enter' });

    await waitFor(() => expect(onRequestRunCheck).toHaveBeenCalledTimes(1));
    expect(onRequestRunCheck).toHaveBeenCalledWith(RUN_A);
    // Run B was never asked about — expansion is progressive, not a prefetch.
    expect(onRequestRunCheck).not.toHaveBeenCalledWith(RUN_B);
  });

  it('does not re-fetch a check it already holds at the same run version', async () => {
    const { container, onRequestRunCheck } = renderPanel();
    const runRow = () => row(container, nodeIds.run(RUN_A))!;

    fireEvent.keyDown(runRow(), { key: 'Enter' });
    await waitFor(() => expect(onRequestRunCheck).toHaveBeenCalledTimes(1));

    fireEvent.keyDown(runRow(), { key: 'Enter' }); // collapse
    fireEvent.keyDown(runRow(), { key: 'Enter' }); // expand again
    await waitFor(() => expect(onRequestRunCheck).toHaveBeenCalledTimes(1));
  });

  it('drops the cached check when the experiment version moves', async () => {
    const { container, rerender, onRequestRunCheck } = renderPanel();
    fireEvent.keyDown(row(container, nodeIds.run(RUN_A))!, { key: 'Enter' });
    await waitFor(() => expect(onRequestRunCheck).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(container.textContent).toContain('This run has no measurement series recorded.'),
    );

    // The record moved. A verdict computed against the previous version does not
    // describe this one, so it is evicted rather than shown.
    rerender(
      <EvidenceGraphPanel
        experimentId={GRAPH_EXP}
        detail={detailFixture({ version: '1.1' })}
        evidence={evidenceFixture}
        classification={classificationFixture()}
        runs={[runA(), runB()]}
        runsMeta={{ total: 2, matched: 2, returned: 2, offset: 0 }}
        readInScope={null}
        currentScope={null}
        focusRunId={null}
        onFocusRun={() => {}}
        onRequestRunCheck={onRequestRunCheck}
      />,
    );

    expect(container.textContent).not.toContain('This run has no measurement series recorded.');
    expect(container.textContent).toContain('1.1');
  });

  it('is navigable by keyboard: roving tab stop, arrows move, Right opens', async () => {
    const { container } = renderPanel();

    const rows = () => [...container.querySelectorAll<HTMLLIElement>('[role="treeitem"]')];
    // Exactly ONE tab stop into the whole graph.
    expect(rows().filter((r) => r.getAttribute('tabindex') === '0').length).toBe(1);

    const first = rows()[0];
    expect(first.getAttribute('aria-level')).toBe('1');
    fireEvent.keyDown(first, { key: 'ArrowDown' });
    await waitFor(() =>
      expect(rows()[1].getAttribute('aria-selected')).toBe('true'),
    );

    // Right opens a collapsed node rather than moving past it.
    const runRow = row(container, nodeIds.run(RUN_A))!;
    fireEvent.keyDown(runRow, { key: 'ArrowRight' });
    await waitFor(() =>
      expect(row(container, nodeIds.run(RUN_A))?.getAttribute('aria-expanded')).toBe('true'),
    );
  });

  it('announces expansion and selection in a live region', async () => {
    const { container, getByTestId } = renderPanel();
    fireEvent.keyDown(row(container, nodeIds.run(RUN_A))!, { key: 'Enter' });
    await waitFor(() => expect(getByTestId('evgraph-live').textContent).toContain('expanded'));
    expect(getByTestId('evgraph-live').getAttribute('aria-live')).toBe('polite');
  });

  it('keeps the canvas out of the accessibility tree, so nothing is announced twice', () => {
    const { container } = renderPanel();
    const svg = container.querySelector('svg.evgraph-canvas');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('aria-hidden')).toBe('true');
    // No second tab stop hiding inside the picture.
    expect(svg?.querySelectorAll('[tabindex="0"]').length).toBe(0);
  });

  it('reaches a non-containment relationship through the details pane', async () => {
    // `conflicts_with` cannot be an edge of a tree. It must still be reachable
    // without seeing the layout.
    const { container } = renderPanel();
    const graph = buildOk();
    const conflict = graph.edges.find((e) => e.kind === 'conflicts_with')!;

    expect(conflict).toBeTruthy();

    // `ex_situ` is quoted by exactly one stored entry — the second of the two
    // that the server classified as conflicting. Search reveals its ancestors
    // and selects it, which is the keyboard-reachable route to a node several
    // levels down.
    const search = container.querySelector<HTMLInputElement>('#evgraph-search-input')!;
    fireEvent.change(search, { target: { value: 'ex_situ' } });
    const option = await waitFor(() => {
      const el = container.querySelector<HTMLButtonElement>('.evgraph-result');
      if (!el) throw new Error('no search result yet');
      return el;
    });
    fireEvent.click(option);

    // The relationship that cannot be a tree edge is nonetheless listed, named,
    // and explained — reachable without seeing the layout.
    const rel = await waitFor(() => {
      const el = container.querySelector('.evgraph-conn-rel[data-edge-kind="conflicts_with"]');
      if (!el) throw new Error('no conflicts_with relationship listed yet');
      return el;
    });
    expect(rel.textContent).toMatch(/conflicts with/i);

    const conn = rel.closest('.evgraph-conn');
    expect(conn?.querySelector('.evgraph-conn-cross')?.textContent).toBe('not in the tree');
    // It says WHY, in the server's own terms, and picks no winner.
    expect(conn?.querySelector('.evgraph-conn-why')?.textContent).toContain(
      'conflicting_evidence',
    );
  });

  it('offers Fit to View, Reset, Search, Focus on Run and the kind filters', () => {
    const { container, getByLabelText } = renderPanel();
    const buttons = [...container.querySelectorAll('button')].map((b) => b.textContent ?? '');
    expect(buttons.some((t) => t.includes('Fit to View'))).toBe(true);
    expect(buttons.some((t) => t.includes('Reset'))).toBe(true);
    expect(getByLabelText('Search this experiment')).toBeTruthy();
    expect(getByLabelText('Focus on run')).toBeTruthy();
    expect(container.querySelectorAll('.evgraph-kind-chip').length).toBeGreaterThan(0);
  });

  it('focusing a run is a URL action, so the view can be linked', () => {
    const { container, onFocusRun } = renderPanel();
    const select = container.querySelector<HTMLSelectElement>('#evgraph-focus-select')!;
    fireEvent.change(select, { target: { value: RUN_B } });
    expect(onFocusRun).toHaveBeenCalledWith(RUN_B);
  });

  it('refuses to draw a graph read in another workspace', () => {
    const { container } = render(
      <EvidenceGraphPanel
        experimentId={GRAPH_EXP}
        detail={detailFixture()}
        evidence={evidenceFixture}
        classification={classificationFixture()}
        runs={[runA()]}
        runsMeta={{ total: 1, matched: 1, returned: 1, offset: 0 }}
        readInScope="tutorial-session"
        currentScope={null}
        focusRunId={null}
        onFocusRun={() => {}}
        onRequestRunCheck={async () => checkFixture()}
      />,
    );
    expect(container.querySelector('.evgraph-refusal')).not.toBeNull();
    expect(container.querySelectorAll('[role="treeitem"]').length).toBe(0);
  });
});

// ===========================================================================
// 7 · the screen — an ADDITION beside the Evidence List
// ===========================================================================

describe('Evidence screen · Evidence List | Evidence Graph', () => {
  const routes = (over: Record<string, unknown> = {}) => ({
    ...evidenceBundleRoutes(EXP_ID),
    [`GET /api/experiments/${EXP_ID}/runs`]: {
      body: {
        runs: [runA({ experiment_id: EXP_ID }), runB({ experiment_id: EXP_ID })],
        experiment_version: '1.0',
        total: 2,
        matched: 2,
        returned: 2,
        offset: 0,
      },
    },
    ...over,
  });

  const renderAt = (path: string) =>
    render(
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );

  it('offers both views, with the Evidence List selected by default', async () => {
    stubFetchRoutes(routes() as never);
    const { findByRole, getByRole } = renderAt(`/record/${EXP_ID}/evidence`);

    const list = await findByRole('tab', { name: 'Evidence List' });
    expect(list.getAttribute('aria-selected')).toBe('true');
    expect(getByRole('tab', { name: 'Evidence Graph' }).getAttribute('aria-selected')).toBe(
      'false',
    );
  });

  it('PRESERVES the existing Evidence List — the trail and the panels are untouched', async () => {
    stubFetchRoutes(routes() as never);
    const { findByText, container } = renderAt(`/record/${EXP_ID}/evidence`);

    // The trail rail, the classification panel and the source preview are all
    // still the default view. The graph is an addition, not a replacement.
    await findByText(/Evidence Trail/i);
    expect(container.querySelector('.evclass')).not.toBeNull();
    expect(container.querySelector('.evgraph')).toBeNull();
  });

  it('switches to the graph, and the graph is deep-linkable', async () => {
    stubFetchRoutes(routes() as never);
    const { findByRole, findByTestId } = renderAt(
      `/record/${EXP_ID}/evidence?view=graph`,
    );

    const tab = await findByRole('tab', { name: 'Evidence Graph' });
    expect(tab.getAttribute('aria-selected')).toBe('true');
    expect((await findByTestId('evgraph-disclosure')).textContent).toBe(
      EVIDENCE_GRAPH_DISCLOSURE,
    );
  });

  it('an unrecognised view falls back to the list, so no bookmark is dead', async () => {
    stubFetchRoutes(routes() as never);
    const { findByRole } = renderAt(`/record/${EXP_ID}/evidence?view=nonsense`);
    expect((await findByRole('tab', { name: 'Evidence List' })).getAttribute('aria-selected')).toBe(
      'true',
    );
  });
});

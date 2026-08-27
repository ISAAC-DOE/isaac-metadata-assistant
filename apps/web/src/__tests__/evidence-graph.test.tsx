import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { EvidenceGraphPanel, LABEL_WIDTH_RATIO } from '../screens/graph/EvidenceGraphPanel';
import {
  EDGE_PRODUCERS,
  EVIDENCE_EDGE_KINDS,
  EVIDENCE_GRAPH_DISCLOSURE,
  NODE_PRODUCERS,
  buildEvidenceGraph,
  emptyRunCheckStore,
  evidenceGraphFreshnessKey,
  evidenceTreeRows,
  initialEvidenceGraphState,
  nodeIds,
  readRunCheck,
  rekeyRunCheckStore,
  viewBoxFor,
  viewRectFor,
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
  // The canvas-bounds test spies on `getBoundingClientRect`; a spy that
  // outlived its test would silently give every later render a phone-width
  // canvas.
  vi.restoreAllMocks();
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
 *
 * BOTH of those two are `user_confirmation` entries carrying DISTINCT `answer`s,
 * and that shape is not decoration — it is the only shape the server can classify
 * this way. `evidence_classify._asserted_values` collects each entry's `answer`
 * and rule 1 fires on two DISTINCT ones; `quote` is never read. An earlier
 * version of this fixture gave two entries differing `quote`s, no `answer` at
 * all, and then hand-labelled the classification `conflicting_evidence` — a
 * response the backend cannot emit, so every conflict assertion below was being
 * checked against an impossible input. `answer` appears on `user_confirmation`
 * entries and on nothing else in this repository's real drafts, so two
 * confirmations that disagree (the same question asked twice, answered
 * differently) is the honest realisation of it.
 *
 * The negative controls are only as strong as the positive fixture is real.
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
        source_type: 'user_confirmation',
        question: 'Was this measurement in situ or ex situ?',
        answer: 'in_situ',
        timestamp: '2099-04-02T12:00:00Z',
      },
      {
        source_type: 'user_confirmation',
        question: 'Confirm the environment for the second scan set.',
        answer: 'ex_situ',
        timestamp: '2099-04-02T13:30:00Z',
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
      // NOTE: `edge.kind` is typed by `EvidenceEdgeKind`, so asserting that it is
      // in `EVIDENCE_EDGE_KINDS` is a tautology the compiler already enforces —
      // it used to be here and has been removed rather than left to read as a
      // check. The PRODUCER is the part TypeScript cannot police: it is a plain
      // string, so only this assertion (and `Builder.addEdge`'s own refusal)
      // stops a future slice writing a plausible-sounding provenance.
      expect(
        EDGE_PRODUCERS[edge.kind],
        `${edge.kind} carried an undeclared producer: ${edge.producer}`,
      ).toContain(edge.producer);
      // An edge that cannot say WHY it exists is an edge a reader cannot check.
      expect(edge.why.trim().length).toBeGreaterThan(0);
    }
  });

  it('EVERY emitted node carries THE declared producer for its kind', () => {
    /*
     * This used to assert `node.producer.trim().length > 0`, which
     * `producer: 'inferred from the sample name'` would have satisfied — the
     * module header meanwhile claimed a test checked membership in
     * `NODE_PRODUCERS`. It now does, and `Builder.addNode` refuses at
     * construction, so the claim and the code agree.
     *
     * A node kind has exactly ONE producer (unlike an edge kind, two of which
     * carry several), so this is an equality rather than a membership test.
     */
    const graph = buildOk({ checks: { [RUN_A]: checkFixture() } });
    expect(graph.nodes.length).toBeGreaterThan(0);

    const declared = new Set(Object.values(NODE_PRODUCERS));
    for (const node of graph.nodes) {
      expect(declared, `${node.kind} carried an undeclared producer: ${node.producer}`).toContain(
        node.producer,
      );
      expect(
        node.producer,
        `${node.id} carried ${node.kind === 'run' ? 'another kind’s' : 'the wrong kind’s'} producer`,
      ).toBe(NODE_PRODUCERS[node.kind]);
    }

    // Every kind the fixture actually exercises, so the assertion above is not
    // passing merely because few kinds were built.
    const kinds = new Set(graph.nodes.map((n) => n.kind));
    for (const kind of [
      'experiment',
      'run',
      'sample',
      'context',
      'measurement',
      'asset',
      'descriptor',
      'evidence_entry',
      'evidence_source',
      'validation_finding',
    ]) {
      expect(kinds, `no ${kind} node was produced`).toContain(kind);
    }
  });

  it('both endpoints of every edge exist as nodes', () => {
    const graph = buildOk({ checks: { [RUN_A]: checkFixture() } });
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
    // (`for (const kind of kinds) expect(EVIDENCE_EDGE_KINDS).toContain(kind)`
    // used to close this test. It compared a value against the union that
    // already types it, so it could not fail; removed rather than left to look
    // like coverage. The list above is the real assertion — it names all ten and
    // fails if a producer stops firing.)
    expect(kinds.size).toBe(EVIDENCE_EDGE_KINDS.length);
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

  /*
   * WHOSE FINDING A GRAPH NODE SAYS IT IS.
   *
   * `FINDING_ORIGINS` carried a CONSTANT `label: 'Official schema check'` for the
   * `official` channel with no `dry_run` branch anywhere, so every element of
   * `check.official.errors` became a node whose `Reported by` line, and whose
   * incoming `validated_by` edge label and `why`, attributed it to the official
   * ISAAC schema. On a dry run that attribution is unsupported: `_validate_unit`
   * returns `export_draft`'s result, and `export.py` returns
   * `official_report=None` before `validate_official` is called on two paths —
   * a failed no-guessing report (`export.py:305`) and a failed anchored-pattern
   * EXACTNESS gate, folded into `draft_report` (`:339-343`). `CLAUDE.md` §12: no
   * surface may report an exactness refusal as an official-schema error, and a
   * graph node is such a surface. There was no test here at all before, which is
   * how this module ended up the ONE consumer of the payload with no branch.
   */
  const officialFinding = (official: Record<string, unknown>) => {
    const graph = buildOk({
      checks: {
        [RUN_A]: checkFixture({
          blockers: [],
          // `as unknown as` deliberately: the fixtures below include `schema`,
          // which `post_run_check` DOES send and `ApiRunCheckVerdict` does not
          // declare — the reason no surface has ever rendered the label.
          official: official as unknown as ApiRunCheckResponse['official'],
        }),
      },
    });
    const node = graph.nodes.find((n) => n.kind === 'validation_finding');
    if (!node) throw new Error('no validation_finding node was produced');
    const edge = graph.edges.find((e) => e.target === node.id);
    if (!edge) throw new Error('the finding node has no incoming edge');
    return { node, edge };
  };

  it('an EXACTNESS finding on a dry run is NOT labelled an official-schema check', () => {
    const message =
      "value is accepted by the schema pattern '^[A-Za-z0-9_.-]+$' only because " +
      "Python's '$' also matches before a trailing newline";
    const { node, edge } = officialFinding({
      ok: false,
      dry_run: true,
      schema: 'ISAAC v1.05',
      errors: [{ path: 'descriptors.outputs.0.name', message }],
    });
    const reportedBy = node.detail.find((d) => d.term === 'Reported by');
    expect(reportedBy?.value).toBe('Check finding — source not named');
    expect(edge.label).toBe('Check finding — source not named');
    // Every string the node and its edge carry, checked at once — the attribution
    // must not survive anywhere, including in `why`.
    //
    // `node.producer` WAS NOT IN THIS LIST, and that omission is why the correction
    // above shipped directly beneath the uncorrected claim it contradicts.
    // `NODE_PRODUCERS.validation_finding` read "… blockers, draft errors,
    // official-schema errors", and `EvidenceGraphPanel.tsx:1228` renders it verbatim
    // under the heading "Where this came from" — on the SAME details pane as
    // `Reported by`. A guard that joins four of the five strings a pane shows is a
    // guard that says nothing about the fifth, and the fifth is where the defect was.
    const all = [
      ...node.detail.map((d) => `${d.term}: ${d.value}`),
      node.label,
      node.producer,
      edge.label ?? '',
      edge.why,
    ].join(' | ');
    expect(all).not.toContain('Official schema');
    expect(all).not.toContain('ISAAC v1.05');
    // The finding's own text is still carried verbatim. Withholding the
    // attribution must never withhold the finding.
    expect(all).toContain(message);
    // And the `Dry run` line that already existed is still there beside it.
    expect(node.detail.find((d) => d.term === 'Dry run')?.value).toBe(
      'yes — an in-memory candidate record, nothing written',
    );
  });

  it('names the official schema only when the server said dry_run: false', () => {
    const { node, edge } = officialFinding({
      ok: false,
      dry_run: false,
      errors: [{ path: 'timestamps', message: "'acquired_start_utc' is required" }],
    });
    // The one branch where the label is EARNED: `_validate_unit` validated the
    // record already written, through `validate_official` and nothing else.
    expect(node.detail.find((d) => d.term === 'Reported by')?.value).toBe(
      'Official ISAAC schema check',
    );
    expect(edge.label).toBe('Official ISAAC schema check');
  });

  it('a NO-VERDICT unit is attributed to no validator at all', () => {
    /*
     * THE CASE THIS MODULE COULD NOT SEE. `findingOriginLabel` took `(key, dryRun)` —
     * two parameters — so `unavailable` was unreachable from it, and
     * `_validate_unit`'s materialised-unreadable branch carries `dry_run: false`
     * beside `unavailable: true` under its own comment "no verdict, not a schema
     * violation". The `false` branch therefore matched, and every node and edge read
     *
     *     Official schema check on Run 1 (run version ra.0): Validation could not be
     *     completed.
     *
     * — the server's refusal to produce a verdict, rendered as the official ISAAC
     * schema having produced one. There was no `unavailable` case in this file at all,
     * which is how a module that had just been given a `dry_run` branch shipped
     * without the branch that outranks it.
     */
    const { node, edge } = officialFinding({
      ok: false,
      dry_run: false,
      unavailable: true,
      errors: [{ path: '$', message: 'Validation could not be completed.' }],
    });
    expect(node.detail.find((d) => d.term === 'Reported by')?.value).toBe(
      'No verdict — not a schema failure',
    );
    expect(edge.label).toBe('No verdict — not a schema failure');
    // The `Dry run` row is on the same pane and must not re-state the claim the label
    // just withheld: `dry_run: false` here means NO DRY RUN HAPPENED, not that a
    // written record was read.
    expect(node.detail.find((d) => d.term === 'Dry run')?.value).toBe(
      'neither — no verdict could be produced',
    );
    const all = [
      ...node.detail.map((d) => `${d.term}: ${d.value}`),
      node.label,
      node.producer,
      edge.label ?? '',
      edge.why,
    ].join(' | ');
    expect(all).not.toContain('Official schema');
    expect(all).not.toContain('already written');
    // And the finding itself survives, as on every other branch.
    expect(all).toContain('Validation could not be completed.');
  });

  it('the producer names WHERE the lists came from, never which validator spoke', () => {
    /*
     * I5 — the `Reported by` line was corrected and `node.producer`, rendered on the
     * same pane under "Where this came from", was not. It is a constant, so one
     * assertion covers every branch: it must name the response's own keys and no
     * validator. The `Reported by` label is the ONLY place in this module allowed to
     * name the official schema, and only on the one branch that earns it.
     */
    expect(NODE_PRODUCERS.validation_finding).not.toContain('official-schema');
    expect(NODE_PRODUCERS.validation_finding).not.toContain('Official schema');
    expect(NODE_PRODUCERS.validation_finding).toContain('official.errors');
    expect(NODE_PRODUCERS.validation_finding).toContain('draft.errors');
    expect(NODE_PRODUCERS.validation_finding).toContain('blockers');
  });

  it('claims neither source nor document when dry_run is absent', () => {
    const { node, edge } = officialFinding({
      ok: false,
      errors: [{ path: '$', message: 'boom' }],
    });
    expect(node.detail.find((d) => d.term === 'Reported by')?.value).toBe(
      'Check finding — source not named',
    );
    expect(edge.label).toBe('Check finding — source not named');
    expect(node.detail.find((d) => d.term === 'Dry run')?.value).toBe(
      'the server did not say',
    );
  });

  it('the blocker and draft channels keep their own labels, unaffected by dry_run', () => {
    // The fix must not spread: those two channels have one producer each and never
    // carried a claim about the schema, so their labels are unchanged in every
    // `dry_run` state.
    for (const dryRun of [true, false, undefined]) {
      const graph = buildOk({
        checks: {
          [RUN_A]: checkFixture({
            blockers: ['This run has no measurement series recorded.'],
            draft: { ok: false, errors: [{ path: 'context.temperature_K', message: 'no evidence' }] },
            official: { ok: true, dry_run: dryRun, errors: [] },
          }),
        },
      });
      const labels = graph.nodes
        .filter((n) => n.kind === 'validation_finding')
        .map((n) => n.detail.find((d) => d.term === 'Reported by')?.value);
      expect(labels).toContain('Blocker');
      expect(labels).toContain('Draft check');
    }
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

  /*
   * ── The drop guard, which is the SAME refusal reached by a different road ───
   *
   * The `> 2` rule above protects against inventing WHICH PAIR disagrees. It is
   * defeated if the count it tests is the count of entries this module managed to
   * DRAW rather than the count the server RECORDED, because the two differ:
   * `attachEvidence` drops an item `readEvidenceItem` cannot narrow and an item
   * the node cap refuses, and the backend does neither — `serialize`'s
   * readable-evidence projection keeps any dict, and `evidence_classify`
   * classifies over the unfiltered list.
   *
   * These three cases are negative controls in the strict sense: each one leaves
   * a surviving set that a naive `entries.length` test would happily draw from.
   */
  it('refuses `conflicts_with` when THREE are recorded and only two could be read', () => {
    // The exact defect: three stored entries, one unreadable, so the client's
    // surviving set is TWO. Joining those two would pick a pair by array
    // position out of three AND state a count from the wrong set. The server's
    // number is 3, so this takes the `> 2` route.
    const threeWithOneUnreadable: ApiEvidenceEntry[] = [
      {
        ...evidenceFixture[1],
        evidence: [
          ...evidenceFixture[1].evidence,
          // No `source_type`: `readEvidenceItem` returns null and the item is
          // counted as unreadable rather than drawn.
          { source_file: 'third_note.txt' } as never,
        ],
      },
    ];
    const graph = buildOk({ evidence: threeWithOneUnreadable });

    // Two evidence-entry nodes exist at the experiment level…
    expect(graph.nodes.filter((n) => n.kind === 'evidence_entry' && n.runId === null).length).toBe(
      2,
    );
    // …and NO pair is drawn between them.
    expect(graph.edges.filter((e) => e.kind === 'conflicts_with')).toEqual([]);
    expect(graph.notes.map((n) => n.kind)).toContain('conflict_pair_unknown');
    expect(graph.notes.map((n) => n.kind)).toContain('unreadable_evidence');

    // And no surface anywhere states the client's count as if it were the
    // record's. The only number said about this address is the server's 3.
    const said = graph.nodes
      .flatMap((n) => n.detail)
      .filter((l) => l.term.startsWith('Conflicting evidence'))
      .map((l) => l.value);
    expect(said.length).toBe(1);
    expect(said[0]).toContain('3 entries');
    expect(said[0]).not.toContain('2 entries');
  });

  it('refuses `conflicts_with` when TWO are recorded and only one could be read', () => {
    // The server's count IS two, so the `> 2` rule alone would not fire here —
    // only the size-match condition refuses this one. Under the old code the
    // surviving set was 1 and nothing at all was said; now the shortfall is
    // stated rather than silently producing an unexplained gap.
    const twoWithOneUnreadable: ApiEvidenceEntry[] = [
      {
        ...evidenceFixture[1],
        evidence: [evidenceFixture[1].evidence[0], {} as never],
      },
    ];
    const graph = buildOk({ evidence: twoWithOneUnreadable });

    expect(graph.edges.filter((e) => e.kind === 'conflicts_with')).toEqual([]);
    expect(graph.notes.map((n) => n.kind)).toContain('conflict_pair_unknown');
    const said = graph.nodes
      .flatMap((n) => n.detail)
      .find((l) => l.term.startsWith('Conflicting evidence'));
    expect(said?.value).toContain('2 entries');
    expect(said?.value).toContain('only 1 of them could be read');
  });

  it('refuses `conflicts_with` when the server itself flagged the entry unreadable', () => {
    // `unavailable` means the SERVER could not read part or all of the stored
    // evidence. Whatever survived on the wire is by definition not the whole
    // recorded set, so no pair may be taken from it.
    const graph = buildOk({
      evidence: [
        {
          ...evidenceFixture[1],
          unavailable: true,
          unavailable_reason: 'the stored evidence could not be decoded',
        },
      ],
    });

    expect(graph.edges.filter((e) => e.kind === 'conflicts_with')).toEqual([]);
    expect(graph.notes.map((n) => n.kind)).toContain('conflict_pair_unknown');
  });

  it('states the SERVER’s count, not its own, in the `why` of the pair it does draw', () => {
    const graph = buildOk();
    const conflict = graph.edges.find((e) => e.kind === 'conflicts_with');
    expect(conflict).toBeTruthy();
    // Two recorded, two drawn — and the sentence says both halves, so a reader
    // can check the claim against the record rather than against the picture.
    expect(conflict!.why).toContain('records exactly two entries there and both are drawn');
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

  it('the rectangle labels are bounded against IS the rectangle the SVG shows', () => {
    /*
     * `viewRectFor` exists because label placement needs the four numbers
     * `viewBoxFor` formats into a string. Two functions computing the same
     * rectangle can drift; this is the only thing stopping them, and a drift
     * here would bound labels against a canvas the browser is not drawing.
     */
    for (const view of [
      { cx: 0, cy: 0, scale: 1 },
      { cx: -140.5, cy: 62, scale: 0.37 },
      { cx: 900, cy: -20, scale: 4 },
    ]) {
      for (const box of [{ width: 827, height: 420 }, { width: 295, height: 520 }]) {
        const r = viewRectFor(view, box);
        expect(viewBoxFor(view, box)).toBe(`${r.x} ${r.y} ${r.width} ${r.height}`);
      }
    }
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

  /*
   * ── The announced NUMBER, which is the only report a screen-reader user gets ─
   *
   * The test above asserts `toContain('expanded')` and would pass against any
   * number at all, which is how "N items revealed" came to announce
   * `childrenOf(id).length` — the CONTAINMENT count — while what actually appears
   * is `evidenceTreeRows`, filtered by the hidden kinds and sliced at the visible
   * cap. Hide a kind and the live region reported an effect the keystroke did not
   * have. These two pin the number to the rows.
   */
  it('announces the number of rows that ACTUALLY appeared, not the child count', async () => {
    /*
     * A CLEAN check on purpose. Opening a run also fetches its findings, and a
     * finding arrives ASYNCHRONOUSLY as an extra node — so a check with blockers
     * would leave the row count one higher than the announcement by the time
     * `waitFor` settles, and the test would be measuring the fetch rather than
     * the keystroke. The announcement is honest about the action it describes;
     * the later arrival is a different event.
     */
    const { container, getByTestId } = renderPanel({
      onRequestRunCheck: vi.fn(async () =>
        checkFixture({ ok: true, blockers: [], official: { ok: true, errors: [], dry_run: true } }),
      ),
    });
    const before = container.querySelectorAll('[role="treeitem"]').length;

    fireEvent.keyDown(row(container, nodeIds.run(RUN_A))!, { key: 'Enter' });
    await waitFor(() => expect(getByTestId('evgraph-live').textContent).toContain('expanded'));

    const after = container.querySelectorAll('[role="treeitem"]').length;
    const appeared = after - before;
    expect(appeared).toBeGreaterThan(0);
    expect(getByTestId('evgraph-live').textContent).toContain(`${appeared} items revealed`);
  });

  it('announces NO number when a kind filter means nothing was revealed', async () => {
    const { container, getByTestId } = renderPanel({
      // Clean, for the same reason as the test above: an arriving finding would
      // add a row that has nothing to do with the keystroke being measured.
      onRequestRunCheck: vi.fn(async () =>
        checkFixture({ ok: true, blockers: [], official: { ok: true, errors: [], dry_run: true } }),
      ),
    });

    /*
     * Run B carries exactly ONE grouped child, a Sample, and nothing else — so
     * hiding "Sample" makes opening it reveal nothing at all. (Run A would not
     * do: it carries five kinds, so hiding one still reveals four.)
     *
     * The chip is pressed BEFORE the expansion, which is the order a reader
     * would use, and is also the order that makes the old code wrong: the
     * containment count is 1 either way.
     */
    // By class + `data-kind` rather than by accessible name: "Sample" also names
    // tree rows and details-pane controls, and `getByRole` finds several.
    fireEvent.click(
      container.querySelector<HTMLButtonElement>('.evgraph-kind-chip[data-kind="sample"]')!,
    );
    const before = container.querySelectorAll('[role="treeitem"]').length;

    fireEvent.keyDown(row(container, nodeIds.run(RUN_B))!, { key: 'Enter' });
    await waitFor(() => expect(getByTestId('evgraph-live').textContent).toContain('expanded'));

    // Nothing appeared…
    expect(container.querySelectorAll('[role="treeitem"]').length).toBe(before);
    // …and the announcement says so instead of claiming one item.
    const said = getByTestId('evgraph-live').textContent ?? '';
    expect(said).toContain('Nothing is shown beneath it');
    expect(said).not.toMatch(/\d+ items? revealed/);
  });

  it('labels a row’s badge with what the number MEANS, open or closed', async () => {
    const { container } = renderPanel();
    const badgeOf = (nodeId: string) =>
      row(container, nodeId)?.querySelector('.evgraph-row-count')?.textContent ?? '';

    // Closed: the children the record holds — a claim about the data.
    expect(badgeOf(nodeIds.run(RUN_A))).toContain('recorded beneath');

    fireEvent.keyDown(row(container, nodeIds.run(RUN_A))!, { key: 'Enter' });
    await waitFor(() =>
      expect(row(container, nodeIds.run(RUN_A))?.getAttribute('aria-expanded')).toBe('true'),
    );

    // Open: the rows on screen beneath it — a claim about the screen. And the
    // number matches the rows the tree actually renders below this one.
    const badge = badgeOf(nodeIds.run(RUN_A));
    expect(badge).toContain('shown beneath');
    const rowsNow = [...container.querySelectorAll<HTMLLIElement>('[role="treeitem"]')];
    const at = rowsNow.findIndex((r) => r.getAttribute('data-node-id') === nodeIds.run(RUN_A));
    const level = Number(rowsNow[at].getAttribute('aria-level'));
    let deeper = 0;
    for (let i = at + 1; i < rowsNow.length; i += 1) {
      if (Number(rowsNow[i].getAttribute('aria-level')) <= level) break;
      deeper += 1;
    }
    expect(badge).toContain(String(deeper));
  });

  it('keeps the canvas out of the accessibility tree, so nothing is announced twice', () => {
    const { container } = renderPanel();
    const svg = container.querySelector('svg.evgraph-canvas');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('aria-hidden')).toBe('true');
    // No second tab stop hiding inside the picture.
    expect(svg?.querySelectorAll('[tabindex="0"]').length).toBe(0);
  });

  /*
   * The roles ARIA lets an `<li>` carry — transcribed from the vendored
   * `axe-core/axe.js`, `htmlElms.li.allowedRoles`, which is the table the
   * `aria-allowed-role` rule consults. `note` is NOT among them, and the panel
   * shipped `<li role="note">` on the notes list: three nodes, at every one of
   * the seven scanned viewports.
   */
  const LI_ALLOWED_ROLES = [
    'menuitem',
    'menuitemcheckbox',
    'menuitemradio',
    'option',
    'none',
    'presentation',
    'radio',
    'separator',
    'tab',
    'treeitem',
    'doc-biblioentry',
    'doc-endnote',
  ];

  it('gives no element a role its own tag may not carry, and still announces the notes', () => {
    // `runs: []` guarantees at least one note (`no_runs`) is on screen.
    const { container } = renderPanel({ runs: [] });

    const notes = [...container.querySelectorAll('.evgraph-notes > li')];
    expect(notes.length).toBeGreaterThan(0);
    for (const li of notes) {
      // The invalid override is gone…
      expect(li.getAttribute('role')).toBeNull();
      // …and what it was FOR is not: the whole of the note is still a note.
      expect(li.querySelector('[role="note"]')?.textContent).toBe(li.textContent);
      // The list still says how many advisories there are.
      expect(li.parentElement?.tagName).toBe('UL');
    }

    // Nowhere in the panel — not just in the notes list.
    for (const li of container.querySelectorAll('li[role]')) {
      expect(LI_ALLOWED_ROLES).toContain(li.getAttribute('role'));
    }
    // `note` is valid on the elements axe records as taking any role.
    for (const el of container.querySelectorAll('[role="note"]')) {
      expect(['SPAN', 'P', 'DIV']).toContain(el.tagName);
    }
  });

  it('draws no canvas label outside the canvas, at a phone-width viewport', async () => {
    /*
     * THE DEFECT THIS PINS. At 375 px the canvas is ~295 px wide and a
     * 26-character label estimated at ~165 px, so a label on any node away from
     * the middle hung over the edge and was cut off by the SVG — CI measured
     * `text "processing_notebook"` at 214..336 against a 40..335 container,
     * eight instances on `/record/<id>/evidence?view=graph`.
     *
     * jsdom performs no layout, so the panel's ONE measurement — the canvas's
     * own `getBoundingClientRect` — is stubbed at phone width and the rest of
     * the geometry follows deterministically from the model.
     *
     * What is checked here is the ESTIMATED box, with the estimator the
     * placement itself uses, because that is exactly the guarantee the code
     * makes. Real glyph geometry is CI's to measure, on the Linux face, in a
     * browser that has one.
     */
    const NARROW = { width: 295, height: 420 };
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: Element,
    ) {
      const canvas = this.classList?.contains('evgraph-canvas') ?? false;
      const width = canvas ? NARROW.width : 0;
      const height = canvas ? NARROW.height : 0;
      return {
        x: 0,
        y: 0,
        top: 0,
        left: 0,
        right: width,
        bottom: height,
        width,
        height,
        toJSON: () => ({}),
      } as DOMRect;
    });

    const { container } = renderPanel();

    /*
     * OPEN EVERYTHING, THEN FRAME IT. This is what makes the test bite, and it
     * was arrived at by measurement rather than by taste: with the runs merely
     * collapsed the canvas draws five nodes named `Run 1`, `Sample`, `Context`,
     * all short enough to sit anywhere, and the assertion below passed with the
     * clamp deliberately removed. The long names are leaves — `raw_scan_listing
     * .txt`, `Your confirmation · …` — and a leaf is where CI found
     * `processing_notebook`. Expanding does not refit, so `Fit to View` is what
     * puts them all on one narrow canvas at once. With the clamp removed, two
     * of the sixteen labels then land outside the viewBox.
     */
    for (let pass = 0; pass < 4; pass += 1) {
      for (const r of [...container.querySelectorAll('[role="treeitem"][aria-expanded="false"]')]) {
        fireEvent.keyDown(r, { key: 'Enter' });
      }
    }
    const fit = [...container.querySelectorAll('button')].find((b) =>
      (b.textContent ?? '').includes('Fit to View'),
    )!;
    fireEvent.click(fit);
    await waitFor(() => {
      if (container.querySelectorAll('text.evgraph-node-label').length < 12) {
        throw new Error('the expansion has not painted yet');
      }
    });

    const svg = container.querySelector<SVGSVGElement>('svg.evgraph-canvas')!;
    const [vx, , vw, vh] = svg.getAttribute('viewBox')!.split(' ').map(Number);
    // The canvas was measured at the narrow width, not left on the default box.
    expect(vw / vh).toBeCloseTo(NARROW.width / NARROW.height, 6);

    const labels = [...svg.querySelectorAll<SVGTextElement>('text.evgraph-node-label')];
    // A canvas that drew nothing would satisfy the bound vacuously.
    expect(labels.length).toBeGreaterThan(0);

    for (const label of labels) {
      const group = label.closest('g[data-node-id]')!;
      const at = /translate\((-?[\d.]+) (-?[\d.]+)\)/.exec(group.getAttribute('transform') ?? '')!;
      const font = Number(label.getAttribute('font-size'));
      const centre = Number(at[1]) + Number(label.getAttribute('x'));
      const half = ((label.textContent ?? '').length * font * LABEL_WIDTH_RATIO) / 2;
      const where = `${group.getAttribute('data-node-id')} — “${label.textContent}”`;
      expect(centre - half, `${where} starts left of the canvas`).toBeGreaterThanOrEqual(vx);
      expect(centre + half, `${where} runs past the right edge`).toBeLessThanOrEqual(vx + vw);
      /*
       * And the string itself is cut to the canvas. The clamp alone satisfies
       * the two bounds above — verified by removing the cap and watching them
       * still pass — so without this line nothing would hold the narrow-width
       * truncation in place. It is not decoration: a label wider than the space
       * between its node and the edge is DROPPED rather than detached from its
       * mark, so an uncut 26-character label at 295 px costs visible labels.
       */
      expect(half * 2, `${where} takes more than half the canvas`).toBeLessThanOrEqual(vw / 2);
    }

    // The full name is still reachable from the picture itself.
    for (const group of svg.querySelectorAll('g[data-node-id]')) {
      expect(group.querySelector('title')?.textContent).toBeTruthy();
    }
    // …and nothing here is in the accessibility tree; the tree beside it is.
    expect(svg.getAttribute('aria-hidden')).toBe('true');
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

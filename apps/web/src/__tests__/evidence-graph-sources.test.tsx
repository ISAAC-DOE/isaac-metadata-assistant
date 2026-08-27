import { describe, it, expect, afterEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, fireEvent } from '@testing-library/react';
import { EvidenceGraphPanel } from '../screens/graph/EvidenceGraphPanel';
import {
  EDGE_PRODUCERS,
  EVIDENCE_GRAPH_DISCLOSURE,
  MAX_CONFLICT_CANDIDATES,
  MAX_EVIDENCE_GRAPH_NODES,
  MAX_EVIDENCE_SEARCH_RESULTS,
  MAX_GRAPH_ASSET_REFS,
  MAX_GRAPH_CONFLICTS,
  MAX_GRAPH_NOTES,
  MAX_VISIBLE_EVIDENCE_NODES,
  NODE_PRODUCERS,
  buildEvidenceGraph,
  initialEvidenceGraphState,
  nodeIds,
  searchEvidenceGraph,
  subFetchFreshness,
  visibleEvidenceNodeIds,
  type EvidenceGraph,
  type EvidenceGraphInput,
  type EvidenceGraphNoteKind,
  type EvidenceNodeKind,
  type EvidenceSubFetch,
} from '../lib/evidenceGraph';
import type { ApiProvenanceResponse } from '../lib/api';
import { experimentDetail } from '../test/apiFixtures';
import type {
  ApiAsset,
  ApiAssetsResponse,
  ApiConflict,
  ApiConflictResolution,
  ApiConflictsResponse,
  ApiEvidenceClassification,
  ApiEvidenceEntry,
  ApiExperimentDetail,
  ApiLifecycle,
  ApiNote,
  ApiNotesResponse,
  ApiRevisionHistory,
  ApiRunView,
} from '../lib/types';

/*
 * THE FOUR ROUTES THE EVIDENCE GRAPH DID NOT READ.
 *
 * `evidence-graph.test.tsx` holds the spine — the experiment, its runs, the
 * evidence trail, the classification and the one cached run check. This file
 * holds what was added when the view stopped reading only that bundle:
 * `GET .../conflicts` (and the recorded DECISION about each), `GET .../notes`,
 * `GET .../provenance` and `GET .../assets`, plus the one question the revision
 * history is read for.
 *
 * What it exists to hold in place, in the order it matters:
 *
 *  · a node or an edge appears when the DATA says so and is ABSENT when it does
 *    not — every new kind is tested in both directions, because a kind that
 *    always appears is not reading anything;
 *  · a decision that is CURRENT, one that is SUPERSEDED and an address with NO
 *    decision are three distinguishable things, in the model and on screen;
 *  · an unreadable entry produces a SENTENCE, never a missing node that reads as
 *    "there is none";
 *  · the four bounds still hold with four more sources feeding them, and each
 *    new source says what it withheld;
 *  · a sub-fetch that describes a DIFFERENT version of the record says so;
 *  · the disclosure is still on screen verbatim, from the constant, twice;
 *  · and the negative controls have the right POLARITY — this repository has a
 *    documented case of a parity test passing an INVERTED disclosure, so every
 *    "X is not drawn" here is paired with a case where X IS drawn.
 */

vi.setConfig({ testTimeout: 30000 });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// --- fixtures (synthetic, unmistakably fake) --------------------------------

const EXP = '01SYNTHEVGSOURCESEXP000000';
const RUN_A = '01SYNTHEVGSOURCESRUNA00000';
const RUN_GONE = '01SYNTHEVGSOURCESRUNGONE00';

/** `experimentDetail` is `rev: 3` / `version: '1.0'`. Both are compared against. */
const detailFixture = (over: Partial<ApiExperimentDetail> = {}): ApiExperimentDetail =>
  ({
    ...experimentDetail,
    id: EXP,
    title: 'Synthetic XANES — extra-source fixture',
    ...over,
  }) as ApiExperimentDetail;

/**
 * The experiment-level trail. `context.environment` is the address every
 * conflict fixture below is about, so the conflict has a real group node to hang
 * under rather than falling back to the experiment.
 *
 * `sample.material.formula` exists so a note can be MAPPED to a real address —
 * and so the negative control about `candidate_field_path` is tested against a
 * path that demonstrably CAN be drawn.
 */
const evidenceFixture: ApiEvidenceEntry[] = [
  {
    path: 'sample.material.formula',
    value: 'CuO2',
    status: 'verified',
    evidence: [
      { source_type: 'spreadsheet', source_file: 'mock_campaign.csv', locator: 'row 2' },
    ],
  },
  {
    path: 'context.environment',
    value: 'in_situ',
    status: 'needs_confirmation',
    evidence: [
      {
        source_type: 'user_confirmation',
        question: 'in situ or ex situ?',
        answer: 'in_situ',
        timestamp: '2099-04-02T12:00:00Z',
      },
      {
        source_type: 'user_confirmation',
        question: 'confirm the environment for the second scan set',
        answer: 'ex_situ',
        timestamp: '2099-04-02T13:30:00Z',
      },
    ],
  },
];

const classificationFixture: ApiEvidenceClassification = {
  record_rev: 3,
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
};

const runFixture = (over: Partial<ApiRunView> = {}): ApiRunView =>
  ({
    id: RUN_A,
    experiment_id: EXP,
    label: 'Run 1',
    ordinal: 1,
    created_utc: '2099-04-02T09:05:00Z',
    updated_utc: '2099-04-02T09:05:00Z',
    rev: 0,
    version: 'rA.0',
    record_id: null,
    fields: {
      'sample.material.name': { value: 'Synthetic CuO powder', status: 'verified', evidence: [] },
    },
    inherited: {},
    ...over,
  }) as unknown as ApiRunView;

// --- conflicts ---------------------------------------------------------------

const resolutionFixture = (
  over: Partial<ApiConflictResolution> = {},
): ApiConflictResolution => ({
  resolution_id: 'res-synthetic-0001',
  address: 'context.environment',
  run_id: null,
  outcome: 'resolved',
  chosen_value: 'in_situ',
  chosen_from: 'candidate',
  // The SERVER's canonical strings — the only two things this module ever
  // compares, and it compares them to each other. See `candidateDecidedLine`.
  competing_values: ['"in_situ"', '"ex_situ"'],
  competing_digest: 'digest-of-two',
  rationale: 'The second scan set was mislabelled in the campaign sheet.',
  subject: null,
  trust_basis: 'unattributed',
  recorded_utc: '2099-04-03T09:00:00Z',
  history: [
    {
      action: 'record',
      at: '2099-04-03T09:00:00Z',
      from_outcome: null,
      to_outcome: 'resolved',
      superseded_chosen_value: null,
      superseded_competing_digest: null,
    },
  ],
  is_field_value: false,
  is_evidence: false,
  state: 'current',
  stale: false,
  attributed: false,
  ...over,
});

const conflictFixture = (over: Partial<ApiConflict> = {}): ApiConflict => ({
  address: 'context.environment',
  run_id: null,
  candidates: [
    {
      canonical: '"in_situ"',
      value: 'in_situ',
      evidence_count: 1,
      uncited_evidence_count: 0,
      sources: [{ source_type: 'user_confirmation' }],
    },
    {
      canonical: '"ex_situ"',
      value: 'ex_situ',
      evidence_count: 1,
      uncited_evidence_count: 0,
      sources: [{ source_type: 'user_confirmation' }],
    },
  ],
  distinct_value_count: 2,
  evidence_count: 2,
  unavailable: false,
  explanation: 'Two recorded entries assert incompatible values.',
  resolution_state: 'absent',
  resolved: false,
  resolution_stale: false,
  resolution: null,
  ...over,
});

const conflictsFixture = (over: Partial<ApiConflictsResponse> = {}): ApiConflictsResponse => ({
  experiment_id: EXP,
  run_id: null,
  record_rev: 3,
  scope: 'record',
  conflicts: [conflictFixture()],
  counts: {
    conflicting_addresses: 1,
    resolved: 0,
    deferred: 0,
    stale: 0,
    unresolved: 1,
  },
  resolutions_without_conflict: [],
  unreadable_resolution_entries: 0,
  outcomes: ['resolved', 'deferred'],
  chosen_from_values: ['candidate', 'edited'],
  states: ['absent', 'current', 'stale', 'deferred'],
  experiment_version: '1.0',
  ...over,
});

// --- notes -------------------------------------------------------------------

const noteFixture = (over: Partial<ApiNote> = {}): ApiNote => ({
  id: 'note-synthetic-0001',
  experiment_id: EXP,
  run_id: null,
  source: 'typed_note',
  text: 'The second scan set was run after the cell was reassembled.',
  revised_text: null,
  captured_utc: '2099-04-03T08:00:00Z',
  state: 'unreviewed',
  candidate_field_path: null,
  candidate_rule: null,
  mapped_field_path: null,
  history: [
    {
      action: 'capture',
      at: '2099-04-03T08:00:00Z',
      from_state: null,
      to_state: 'unreviewed',
      field_path: null,
      superseded_text: null,
      reason: null,
    },
  ],
  status: 'unmapped_note',
  verified: false,
  is_evidence: false,
  is_field_value: false,
  display_text: 'The second scan set was run after the cell was reassembled.',
  ...over,
});

const notesFixture = (over: Partial<ApiNotesResponse> = {}): ApiNotesResponse => ({
  notes: [noteFixture()],
  total: 1,
  returned: 1,
  by_state: { unreviewed: 1, mapped: 0, kept: 0, dismissed: 0 },
  unreadable_entries: 0,
  mappable_field_paths: ['sample.material.formula', 'context.environment'],
  value_writable_field_paths: ['sample.material.formula'],
  sources: ['typed_note'],
  experiment_version: '1.0',
  ...over,
});

// --- assets ------------------------------------------------------------------

const assetFixture = (over: Partial<ApiAsset> = {}): ApiAsset => ({
  asset_id: 'asset-synthetic-0001',
  content_role: 'raw_measurement',
  uri: 'file://synthetic/scan_001.dat',
  sha256: 'a'.repeat(64),
  evidence: [],
  evidence_count: 0,
  sha256_wellformed: true,
  used_by_runs: [{ run_id: RUN_A, label: 'Run 1', ordinal: 1 }],
  export_reach: 'runs',
  ...over,
});

const assetsFixture = (over: Partial<ApiAssetsResponse> = {}): ApiAssetsResponse => ({
  assets: [assetFixture()],
  total: 1,
  unreadable_entries: 0,
  content_roles: ['raw_measurement'],
  runs: [{ id: RUN_A, label: 'Run 1', ordinal: 1 }],
  experiment_version: '1.0',
  ...over,
});

// --- provenance --------------------------------------------------------------

const provenanceFixture = (
  over: Partial<ApiProvenanceResponse> = {},
): ApiProvenanceResponse => ({
  experiment_id: EXP,
  run_id: null,
  record_rev: 3,
  entries: [
    {
      address: 'sample.material.formula',
      origins: ['file'],
      primary_origin: 'file',
      review_state: 'supported',
      evidence_count: 1,
      inherited: false,
      note_refs: [],
      unavailable: false,
      resolution_state: 'absent',
    },
    {
      address: 'context.environment',
      origins: ['manual'],
      primary_origin: 'manual',
      review_state: 'conflict',
      evidence_count: 2,
      inherited: false,
      note_refs: [],
      unavailable: false,
      resolution_state: 'absent',
    },
  ],
  notes_summary: { total: 1, listed_as_unmapped: 1 },
  blocks_not_described: [],
  ...over,
});

// --- revisions ---------------------------------------------------------------

const LIFECYCLE = { state: 'draft', label: 'Draft' } as unknown as ApiLifecycle;

const revisionsFixture = (over: Partial<ApiRevisionHistory> = {}): ApiRevisionHistory => ({
  experiment_id: EXP,
  record_rev: 3,
  current_content_signature: 'sig-current',
  signature_scope: 'record',
  limit: 50,
  availability: { state: 'available', reason: null, message: 'History is available.' },
  lifecycle: LIFECYCLE,
  revisions: [
    {
      revision_no: 2,
      revision_id: 'rev-2',
      reason: 'edit',
      created_utc: '2099-04-03T07:00:00Z',
      experiment_rev: 3,
      content_signature: 'sig-current',
      actor: { subject: null, trust_basis: null, attributed: false },
      change_counts: { modified: 2 },
      submission: null,
    },
  ],
  total: 2,
  returned: 1,
  current_submission: null,
  ...over,
});

// --- input -------------------------------------------------------------------

const data = <T,>(value: T): EvidenceSubFetch<T> => ({ state: 'data', data: value });

const inputFixture = (over: Partial<EvidenceGraphInput> = {}): EvidenceGraphInput => ({
  detail: detailFixture(),
  runs: [runFixture()],
  runsMeta: { total: 1, matched: 1, returned: 1, offset: 0 },
  evidence: evidenceFixture,
  classification: classificationFixture,
  checks: {},
  focusRunId: null,
  ...over,
});

function buildOk(over: Partial<EvidenceGraphInput> = {}): EvidenceGraph {
  const result = buildEvidenceGraph(inputFixture(over));
  if (!result.ok) throw new Error(`expected a graph, got ${result.reason}`);
  return result.graph;
}

/** Every source with data — the fully-loaded shape most assertions run against. */
const everySource = (): Partial<EvidenceGraphInput> => ({
  // A DECIDED conflict, so all five new kinds are exercised at once — an
  // undecided one produces no `conflict_decision` and would let the
  // every-kind-appears assertion below pass while checking four of five.
  conflicts: data(
    conflictsFixture({
      conflicts: [
        conflictFixture({
          resolution: resolutionFixture(),
          resolved: true,
          resolution_state: 'current',
        }),
      ],
      counts: {
        conflicting_addresses: 1,
        resolved: 1,
        deferred: 0,
        stale: 0,
        unresolved: 0,
      },
    }),
  ),
  notes: data(notesFixture()),
  provenance: data(provenanceFixture()),
  assets: data(assetsFixture()),
  revisions: data(revisionsFixture()),
});

const kindsOf = (graph: EvidenceGraph): Set<EvidenceNodeKind> =>
  new Set(graph.nodes.map((n) => n.kind));

const noteKinds = (graph: EvidenceGraph): Set<EvidenceGraphNoteKind> =>
  new Set(graph.notes.map((n) => n.kind));

const noteText = (graph: EvidenceGraph, kind: EvidenceGraphNoteKind): string =>
  graph.notes.find((n) => n.kind === kind)?.text ?? '';

const detailValues = (graph: EvidenceGraph, nodeId: string): string =>
  (graph.byId.get(nodeId)?.detail ?? []).map((l) => `${l.term}: ${l.value}`).join('\n');

// ===========================================================================
// 1 · each new kind appears from data — and is ABSENT without it
// ===========================================================================

describe('evidence graph · the four extra sources produce their own kinds', () => {
  it('produces all five new node kinds when every source has data', () => {
    const kinds = kindsOf(buildOk(everySource()));
    for (const kind of [
      'conflict',
      'conflict_candidate',
      'conflict_decision',
      'note',
      'asset_reference',
    ] as const) {
      expect(kinds, `no ${kind} node was produced`).toContain(kind);
    }
  });

  it('produces NONE of them when no source is supplied at all', () => {
    /*
     * THE OTHER HALF OF THE TEST ABOVE, and the half that makes it mean
     * something. A kind that appears whatever the input is not reading anything;
     * this is the same fixture with the five sources removed.
     */
    const kinds = kindsOf(buildOk());
    for (const kind of [
      'conflict',
      'conflict_candidate',
      'conflict_decision',
      'note',
      'asset_reference',
    ] as const) {
      expect(kinds, `${kind} appeared with no source to produce it`).not.toContain(kind);
    }
  });

  it('drops exactly the kinds whose own source is missing, and keeps the others', () => {
    // Conflicts only. The three conflict kinds appear; note and asset do not.
    const conflictsOnly = kindsOf(buildOk({ conflicts: data(conflictsFixture({
      conflicts: [conflictFixture({ resolution: resolutionFixture(), resolved: true, resolution_state: 'current' })],
    })) }));
    expect(conflictsOnly).toContain('conflict');
    expect(conflictsOnly).toContain('conflict_decision');
    expect(conflictsOnly).not.toContain('note');
    expect(conflictsOnly).not.toContain('asset_reference');

    // Notes only. The mirror image.
    const notesOnly = kindsOf(buildOk({ notes: data(notesFixture()) }));
    expect(notesOnly).toContain('note');
    expect(notesOnly).not.toContain('conflict');
    expect(notesOnly).not.toContain('asset_reference');
  });

  it('every new node and every new edge carries the declared producer for its kind', () => {
    const graph = buildOk({
      conflicts: data(
        conflictsFixture({
          conflicts: [
            conflictFixture({
              resolution: resolutionFixture(),
              resolved: true,
              resolution_state: 'current',
            }),
          ],
          resolutions_without_conflict: [
            {
              address: 'sample.material.formula',
              run_id: RUN_GONE,
              outcome: 'deferred',
              resolution_id: 'res-synthetic-orphan',
              orphaned_run: true,
            },
          ],
        }),
      ),
      notes: data(
        notesFixture({
          notes: [noteFixture({ mapped_field_path: 'sample.material.formula', state: 'mapped' })],
        }),
      ),
      assets: data(assetsFixture()),
    });

    const newNodeKinds: EvidenceNodeKind[] = [
      'conflict',
      'conflict_candidate',
      'conflict_decision',
      'note',
      'asset_reference',
    ];
    const newNodes = graph.nodes.filter((n) => newNodeKinds.includes(n.kind));
    expect(newNodes.length).toBeGreaterThan(0);
    for (const node of newNodes) {
      expect(node.producer, `${node.id} carried the wrong producer`).toBe(
        NODE_PRODUCERS[node.kind],
      );
      // A producer that names no route is a producer a reader cannot check.
      expect(node.producer).toMatch(/GET \/api\/experiments\/\{id\}\//);
    }

    const newEdgeKinds = ['has_conflict', 'competing_value', 'has_decision', 'has_note', 'mapped_to'];
    const newEdges = graph.edges.filter((e) => newEdgeKinds.includes(e.kind));
    expect(newEdges.map((e) => e.kind).sort()).toEqual(
      ['competing_value', 'competing_value', 'has_conflict', 'has_decision', 'has_decision', 'has_note', 'mapped_to'].sort(),
    );
    for (const edge of newEdges) {
      expect(
        EDGE_PRODUCERS[edge.kind],
        `${edge.kind} carried an undeclared producer: ${edge.producer}`,
      ).toContain(edge.producer);
      expect(edge.why.trim().length).toBeGreaterThan(0);
    }
  });

  it('draws the asset library under the experiment and links every run that uses it', () => {
    const graph = buildOk({ assets: data(assetsFixture()) });
    const assetId = nodeIds.assetReference('asset-synthetic-0001');
    expect(graph.byId.get(assetId)?.parentId).toBe(nodeIds.experiment(EXP));

    const crossLink = graph.edges.find(
      (e) => e.kind === 'references' && e.source === nodeIds.run(RUN_A) && e.target === assetId,
    );
    expect(crossLink, 'the run that uses this asset should be joined to it').toBeTruthy();
    // A run is not the asset's PARENT — several runs can use one asset, so the
    // link is a cross-link and the tree keeps one home for it.
    expect(crossLink?.containment).toBe(false);
  });

  it('says out loud when an asset reference reaches no exported record', () => {
    const graph = buildOk({
      assets: data(
        assetsFixture({
          assets: [assetFixture({ used_by_runs: [], export_reach: 'none' })],
        }),
      ),
    });
    const text = detailValues(graph, nodeIds.assetReference('asset-synthetic-0001'));
    expect(text).toContain('NO — this reference is associated with no run');

    // Polarity: an asset that DOES reach a record must not carry that sentence.
    const reached = buildOk({ assets: data(assetsFixture()) });
    expect(detailValues(reached, nodeIds.assetReference('asset-synthetic-0001'))).not.toContain(
      'NO — this reference is associated with no run',
    );
  });
});

// ===========================================================================
// 2 · a decision: current, superseded, deferred, and none at all
// ===========================================================================

describe('evidence graph · which conflict was decided, and whether the decision still holds', () => {
  const withResolution = (over: Partial<ApiConflictResolution>, conflictOver: Partial<ApiConflict> = {}) =>
    buildOk({
      conflicts: data(
        conflictsFixture({
          conflicts: [
            conflictFixture({
              resolution: resolutionFixture(over),
              ...conflictOver,
            }),
          ],
        }),
      ),
    });

  it('a CURRENT decision, a SUPERSEDED one and a DEFERRED one are three different labels', () => {
    const current = withResolution({ state: 'current' }, { resolved: true, resolution_state: 'current' });
    const stale = withResolution(
      { state: 'stale', stale: true },
      { resolution_stale: true, resolution_state: 'stale' },
    );
    const deferred = withResolution(
      { state: 'deferred', outcome: 'deferred', chosen_value: null, chosen_from: null },
      { resolution_state: 'deferred' },
    );

    const labelOf = (g: EvidenceGraph) =>
      g.byId.get(nodeIds.decision('res-synthetic-0001'))?.label;

    expect(labelOf(current)).toBe('Decision — current');
    expect(labelOf(stale)).toBe('Decision — superseded');
    expect(labelOf(deferred)).toBe('Deferred — nobody chose');
    // Three different things, said three different ways.
    expect(new Set([labelOf(current), labelOf(stale), labelOf(deferred)]).size).toBe(3);
  });

  it('a STALE decision explains that more evidence arrived, and a current one does not', () => {
    const stale = withResolution({ state: 'stale', stale: true }, { resolution_stale: true });
    const staleText = detailValues(stale, nodeIds.decision('res-synthetic-0001'));
    expect(staleText).toContain('MORE competing evidence has been recorded since');
    expect(staleText).toContain('no longer covers this disagreement');

    const current = withResolution({ state: 'current' }, { resolved: true });
    const currentText = detailValues(current, nodeIds.decision('res-synthetic-0001'));
    expect(currentText).not.toContain('MORE competing evidence has been recorded since');
    expect(currentText).toContain('still the answers recorded here');
  });

  it('an address with NO decision says so, and draws no decision node', () => {
    const graph = buildOk({ conflicts: data(conflictsFixture()) });
    expect(kindsOf(graph)).not.toContain('conflict_decision');
    expect(detailValues(graph, nodeIds.conflict(null, 'context.environment'))).toContain(
      'No decision is on record for this address',
    );
  });

  it('a competing answer recorded AFTER the decision is marked as such — and one present is not', () => {
    /*
     * The staleness explanation made concrete, and the ONE comparison this module
     * performs: the server's `candidates[].canonical` against the server's
     * `resolution.competing_values`. Both are produced by the same function on the
     * same side of the wire; nothing here canonicalises anything.
     */
    const graph = buildOk({
      conflicts: data(
        conflictsFixture({
          conflicts: [
            conflictFixture({
              candidates: [
                ...conflictFixture().candidates,
                {
                  canonical: '"quasi_in_situ"',
                  value: 'quasi_in_situ',
                  evidence_count: 1,
                  uncited_evidence_count: 0,
                  sources: [{ source_type: 'user_confirmation' }],
                },
              ],
              distinct_value_count: 3,
              evidence_count: 3,
              resolution: resolutionFixture({ state: 'stale', stale: true }),
              resolution_stale: true,
              resolution_state: 'stale',
            }),
          ],
        }),
      ),
    });

    const present = detailValues(
      graph,
      nodeIds.conflictCandidate(nodeIds.conflict(null, 'context.environment'), '"in_situ"'),
    );
    expect(present).toContain('Yes — this answer was among the ones the recorded decision');

    const arrivedLater = detailValues(
      graph,
      nodeIds.conflictCandidate(nodeIds.conflict(null, 'context.environment'), '"quasi_in_situ"'),
    );
    expect(arrivedLater).toContain('No — this answer was recorded AFTER the decision');
  });

  it('NO candidate is ever marked as the one that was chosen', () => {
    /*
     * NEGATIVE CONTROL, with its polarity established by the test above: the
     * "present when the decision was made" line demonstrably DOES appear, so this
     * is not passing because candidates carry no lines at all.
     *
     * Matching `chosen_value` to a candidate would need this application to
     * reproduce the server's own canonicalisation, which `api.resolveConflict`
     * records as a second definition of "the same value".
     */
    const graph = buildOk({
      conflicts: data(
        conflictsFixture({
          conflicts: [conflictFixture({ resolution: resolutionFixture(), resolved: true })],
        }),
      ),
    });
    for (const node of graph.nodes.filter((n) => n.kind === 'conflict_candidate')) {
      const text = node.detail.map((l) => `${l.term} ${l.value}`).join(' ');
      expect(text, `${node.id} claimed to be the chosen answer`).not.toMatch(
        /this is the (one|answer) that was chosen|chosen answer|the chosen one/i,
      );
      // And the standing statement IS there — the polarity pair for the line above.
      expect(text).toContain('The record holds all of them and accepts none');
    }
  });

  it('a decision states that it is not the value and not a citation', () => {
    const graph = buildOk({
      conflicts: data(
        conflictsFixture({
          conflicts: [conflictFixture({ resolution: resolutionFixture(), resolved: true })],
        }),
      ),
    });
    const text = detailValues(graph, nodeIds.decision('res-synthetic-0001'));
    expect(text).toContain('Recording a decision changes no scientific content');
    // Nobody is on record, and that is said rather than filled in.
    expect(text).toContain('nobody — no trusted identity was established');
  });

  it('a decision whose conflict is gone — and whose run is gone — is still drawn', () => {
    const graph = buildOk({
      conflicts: data(
        conflictsFixture({
          conflicts: [],
          resolutions_without_conflict: [
            {
              address: 'sample.material.formula',
              run_id: RUN_GONE,
              outcome: 'deferred',
              resolution_id: 'res-synthetic-orphan',
              orphaned_run: true,
            },
          ],
        }),
      ),
    });
    const id = nodeIds.decision('res-synthetic-orphan');
    expect(graph.byId.get(id)?.kind).toBe('conflict_decision');
    expect(graph.byId.get(id)?.parentId).toBe(nodeIds.experiment(EXP));
    expect(detailValues(graph, id)).toContain('belongs to a run that has since been removed');
  });

  it('claims record scope only when the response actually IS record-scoped', () => {
    // The view asks without `?run=`, so the claim is true of what it does. It is
    // guarded on the RESPONSE's own `run_id` all the same: printing "this is the
    // record's own fields" over a run-scoped answer is the same class of defect as
    // printing a version a fetch did not read.
    expect(noteKinds(buildOk({ conflicts: data(conflictsFixture()) }))).toContain(
      'conflicts_record_scope',
    );
    expect(
      noteKinds(buildOk({ conflicts: data(conflictsFixture({ run_id: RUN_A, conflicts: [] })) })),
    ).not.toContain('conflicts_record_scope');
  });

  it('keeps the classification-derived conflicts_with pair rule exactly as it was', () => {
    // The `conflicts` route does not relax it: `candidates` groups by VALUE, so it
    // still does not say which two ENTRIES disagree.
    const withRoute = buildOk({ conflicts: data(conflictsFixture()) });
    const without = buildOk();
    const pairsOf = (g: EvidenceGraph) => g.edges.filter((e) => e.kind === 'conflicts_with').length;
    expect(pairsOf(withRoute)).toBe(pairsOf(without));
    expect(pairsOf(withRoute)).toBe(1);
  });
});

// ===========================================================================
// 3 · unreadable entries produce a sentence, never a silent absence
// ===========================================================================

describe('evidence graph · what could not be read is stated', () => {
  it('counts unreadable conflict decisions, notes and asset references in ONE note', () => {
    const graph = buildOk({
      conflicts: data(conflictsFixture({ unreadable_resolution_entries: 2 })),
      notes: data(notesFixture({ unreadable_entries: 3 })),
      assets: data(assetsFixture({ unreadable_entries: 1 })),
    });
    const text = noteText(graph, 'unreadable_entries');
    expect(text).toContain('2 recorded conflict decisions');
    expect(text).toContain('3 captured notes');
    expect(text).toContain('1 asset references');
    expect(text).toContain('preserved in the record and counted here');
  });

  it('says NOTHING about unreadable entries when there are none', () => {
    // POLARITY. Without this, the assertion above would pass against a note that
    // is emitted unconditionally.
    expect(noteKinds(buildOk(everySource()))).not.toContain('unreadable_entries');
  });

  it('a conflict whose stored evidence is partly unreadable says the picture is incomplete', () => {
    const graph = buildOk({
      conflicts: data(
        conflictsFixture({ conflicts: [conflictFixture({ unavailable: true })] }),
      ),
    });
    expect(detailValues(graph, nodeIds.conflict(null, 'context.environment'))).toContain(
      'not the whole picture',
    );
    expect(detailValues(buildOk({ conflicts: data(conflictsFixture()) }), nodeIds.conflict(null, 'context.environment'))).not.toContain(
      'not the whole picture',
    );
  });

  it('a failed sub-fetch produces a note, and an absent one produces none', () => {
    const failed = buildOk({
      conflicts: { state: 'error', message: 'HTTP 503' },
      notes: { state: 'loading' },
    });
    const text = noteText(failed, 'sub_fetch_unavailable');
    expect(text).toContain('The conflicting evidence could not be read (HTTP 503)');
    expect(text).toContain('not read yet: The unmapped notes');
    expect(text).toContain('is NOT a statement that this record has none');

    // POLARITY, and the fourth state: a source this mount never asked for says
    // nothing at all — "could not be read" would be false of it.
    expect(noteKinds(buildOk())).not.toContain('sub_fetch_unavailable');
    expect(noteKinds(buildOk(everySource()))).not.toContain('sub_fetch_unavailable');
  });
});

// ===========================================================================
// 4 · freshness — the same version-token mechanism, extended
// ===========================================================================

describe('evidence graph · a sub-fetch that describes a different version says so', () => {
  it('subFetchFreshness earns `fresh` and defaults to `unknown`', () => {
    expect(subFetchFreshness('1.0', '1.0')).toBe('fresh');
    expect(subFetchFreshness('1.0', '2.0')).toBe('stale');
    expect(subFetchFreshness('1.0', null)).toBe('unknown');
    expect(subFetchFreshness('1.0', '')).toBe('unknown');
    expect(subFetchFreshness('', '1.0')).toBe('unknown');
  });

  it('names both tokens when a sub-fetch read an older version', () => {
    const graph = buildOk({
      conflicts: data(conflictsFixture({ experiment_version: '0.9' })),
      notes: data(notesFixture()),
    });
    const text = noteText(graph, 'sub_fetch_stale');
    expect(text).toContain('The conflicting evidence was read at version 0.9');
    expect(text).toContain('this record is at 1.0');
    expect(text).toContain('a re-read has not landed since');
    // The data it DID contribute is still drawn — stated, not dropped.
    expect(kindsOf(graph)).toContain('conflict');
  });

  it('compares provenance and revisions on `record_rev`, which is the token they publish', () => {
    const graph = buildOk({
      provenance: data(provenanceFixture({ record_rev: 2 })),
      revisions: data(revisionsFixture({ record_rev: 2 })),
    });
    const text = noteText(graph, 'sub_fetch_stale');
    expect(text).toContain('Where the values came from was read at version 2');
    expect(text).toContain('The submission history was read at version 2');
    expect(text).toContain('this record is at 3');
  });

  it('says nothing when every sub-fetch agrees with the record', () => {
    // POLARITY for both tests above.
    expect(noteKinds(buildOk(everySource()))).not.toContain('sub_fetch_stale');
  });

  it('a source that publishes no version is `unknown`, not `fresh`', () => {
    const graph = buildOk({
      notes: data(notesFixture({ experiment_version: '' })),
    });
    expect(noteText(graph, 'sub_fetch_stale')).toContain(
      'The unmapped notes reported no version',
    );
  });

  /*
   * THE SAME GUARANTEE FOR THE TWO SOURCES THAT PUBLISH A NUMBER, where it was
   * defeated by the rendering rather than by the comparison.
   *
   * `provenance` and `revisions` publish `record_rev`, a NUMBER, so it has to be
   * rendered before `subFetchFreshness` can compare it. Rendered with a bare
   * `String()`, a MISSING rev became the non-empty string `"undefined"` on both
   * sides — and two of those compare EQUAL, so a record and a response that each
   * published no token were drawn as `fresh`, which is the one answer that must be
   * earned. `revToken` returns `null` instead, and `null` reaches the `unknown`
   * arm. Found by review; the string-valued sources above were never affected.
   */
  it('a NUMBER-token source that publishes no rev is `unknown`, not `fresh`', () => {
    const noRev = { ...detailFixture() } as Record<string, unknown>;
    delete noRev.rev;
    const result = buildEvidenceGraph({
      ...inputFixture({
        provenance: data(
          { ...provenanceFixture(), record_rev: undefined } as unknown as ApiProvenanceResponse,
        ),
      }),
      detail: noRev as unknown as ApiExperimentDetail,
    });
    if (!result.ok) throw new Error('expected a graph');
    expect(noteText(result.graph, 'sub_fetch_stale')).toContain(
      'Where the values came from reported no version',
    );
  });

  it('POLARITY: a NUMBER-token source that agrees still says nothing', () => {
    expect(
      noteKinds(buildOk({ provenance: data(provenanceFixture()), revisions: data(revisionsFixture()) })),
    ).not.toContain('sub_fetch_stale');
  });
});

// ===========================================================================
// 5 · the bounds still hold, and each source says what it withheld
// ===========================================================================

describe('evidence graph · four more sources did not turn a bounded read unbounded', () => {
  const manyConflicts = (n: number): ApiConflict[] =>
    Array.from({ length: n }, (_, i) =>
      conflictFixture({ address: `context.synthetic_${String(i).padStart(3, '0')}` }),
    );

  const manyNotes = (n: number): ApiNote[] =>
    Array.from({ length: n }, (_, i) =>
      noteFixture({
        id: `note-synthetic-${String(i).padStart(4, '0')}`,
        captured_utc: `2099-04-03T08:${String(i % 60).padStart(2, '0')}:00Z`,
      }),
    );

  const manyAssets = (n: number): ApiAsset[] =>
    Array.from({ length: n }, (_, i) =>
      assetFixture({ asset_id: `asset-synthetic-${String(i).padStart(4, '0')}` }),
    );

  it('bounds conflicts, candidates, notes and asset references — and names each withholding', () => {
    const graph = buildOk({
      conflicts: data(
        conflictsFixture({
          conflicts: [
            conflictFixture({
              candidates: Array.from({ length: MAX_CONFLICT_CANDIDATES + 4 }, (_, i) => ({
                canonical: `"answer_${i}"`,
                value: `answer_${i}`,
                evidence_count: 1,
                uncited_evidence_count: 0,
                sources: [],
              })),
              distinct_value_count: MAX_CONFLICT_CANDIDATES + 4,
            }),
            ...manyConflicts(MAX_GRAPH_CONFLICTS + 5),
          ],
        }),
      ),
      notes: data(notesFixture({ notes: manyNotes(MAX_GRAPH_NOTES + 7) })),
      assets: data(assetsFixture({ assets: manyAssets(MAX_GRAPH_ASSET_REFS + 3) })),
    });

    const count = (kind: EvidenceNodeKind) =>
      graph.nodes.filter((n) => n.kind === kind).length;

    expect(count('conflict')).toBe(MAX_GRAPH_CONFLICTS);
    expect(count('note')).toBe(MAX_GRAPH_NOTES);
    expect(count('asset_reference')).toBe(MAX_GRAPH_ASSET_REFS);
    // Candidates are bounded PER conflict, so the drawn conflicts each contribute
    // at most `MAX_CONFLICT_CANDIDATES`.
    expect(count('conflict_candidate')).toBeLessThanOrEqual(
      MAX_GRAPH_CONFLICTS * MAX_CONFLICT_CANDIDATES,
    );

    const text = noteText(graph, 'source_bounded');
    expect(text).toContain('conflicting address(es)');
    expect(text).toContain('captured note(s)');
    expect(text).toContain('asset reference(s)');
    expect(text).toContain('competing answer(s)');
    expect(text).toContain('withheld rather than silently dropped');
  });

  it('says nothing about bounds when nothing was withheld', () => {
    // POLARITY.
    expect(noteKinds(buildOk(everySource()))).not.toContain('source_bounded');
  });

  /*
   * THE FIFTH LIST ON THIS ROUTE, WHICH HAD NO BOUND AT ALL.
   *
   * `resolutions_without_conflict[]` is a SECOND unbounded array in the same
   * response as `conflicts[]`, and it grows monotonically — nothing deletes a
   * decision, so every settled address and every decision belonging to a removed
   * run lands there forever. Found by review: 300 of them drew 300 nodes with no
   * `source_bounded` clause, and 2,000 filled the shared node cap so that the
   * notes read AFTER them drew nothing, disclosed only by the generic `node_cap`
   * note, which names no source. That is exactly the silent truncation the
   * per-source bounds exist to end.
   */
  const manyOrphans = (n: number) =>
    Array.from({ length: n }, (_, i) => ({
      address: `context.synthetic_orphan_${String(i).padStart(4, '0')}`,
      run_id: null,
      outcome: 'deferred' as const,
      resolution_id: `res-synthetic-orphan-${String(i).padStart(4, '0')}`,
      orphaned_run: false,
    }));

  it('bounds recorded decisions whose address no longer conflicts — and says what it withheld', () => {
    const graph = buildOk({
      conflicts: data(
        conflictsFixture({
          conflicts: [],
          resolutions_without_conflict: manyOrphans(MAX_GRAPH_CONFLICTS + 9) as never,
        }),
      ),
    });
    expect(graph.nodes.filter((n) => n.kind === 'conflict_decision')).toHaveLength(
      MAX_GRAPH_CONFLICTS,
    );
    const text = noteText(graph, 'source_bounded');
    expect(text).toContain(`9 of ${MAX_GRAPH_CONFLICTS + 9} recorded decision(s)`);
    expect(text).toContain('carries no conflict now');
    expect(text).toContain('withheld rather than silently dropped');
  });

  it('says nothing about that bound when every recorded decision is drawn', () => {
    // POLARITY, and it is the half that makes the test above mean something: a
    // clause emitted unconditionally would satisfy the assertion either way.
    const graph = buildOk({
      conflicts: data(
        conflictsFixture({
          conflicts: [],
          resolutions_without_conflict: manyOrphans(3) as never,
        }),
      ),
    });
    expect(graph.nodes.filter((n) => n.kind === 'conflict_decision')).toHaveLength(3);
    expect(noteKinds(graph)).not.toContain('source_bounded');
  });

  it('a great many recorded decisions do not displace the sources read after them', () => {
    const graph = buildOk({
      conflicts: data(
        conflictsFixture({
          conflicts: [],
          resolutions_without_conflict: manyOrphans(2000) as never,
        }),
      ),
      notes: data(notesFixture()),
      assets: data(assetsFixture()),
    });
    expect(graph.truncated).toBe(false);
    expect(graph.nodes.filter((n) => n.kind === 'note')).toHaveLength(1);
    expect(graph.nodes.filter((n) => n.kind === 'asset_reference')).toHaveLength(1);
    expect(noteKinds(graph)).not.toContain('node_cap');
  });

  it('the global node cap still holds when the extra sources are large', () => {
    const graph = buildOk({
      conflicts: data(conflictsFixture({ conflicts: manyConflicts(MAX_GRAPH_CONFLICTS + 50) })),
      notes: data(notesFixture({ notes: manyNotes(MAX_GRAPH_NOTES + 400) })),
      assets: data(assetsFixture({ assets: manyAssets(MAX_GRAPH_ASSET_REFS + 400) })),
    });
    expect(graph.nodes.length).toBeLessThanOrEqual(MAX_EVIDENCE_GRAPH_NODES);
  });

  it('the extra sources never displace the spine — the experiment and its runs', () => {
    /*
     * The reason the four sources are read AFTER the runs. A record holding a
     * great many notes must not fill the node cap with them and leave the reader
     * without the runs they came for.
     */
    const graph = buildOk({
      notes: data(notesFixture({ notes: manyNotes(MAX_GRAPH_NOTES + 900) })),
    });
    expect(graph.byId.has(nodeIds.experiment(EXP))).toBe(true);
    expect(graph.runOrder).toEqual([nodeIds.run(RUN_A)]);
  });

  it('the visible bound and the search bound are unchanged', () => {
    const graph = buildOk({
      conflicts: data(conflictsFixture({ conflicts: manyConflicts(MAX_GRAPH_CONFLICTS) })),
      notes: data(notesFixture({ notes: manyNotes(MAX_GRAPH_NOTES) })),
      assets: data(assetsFixture({ assets: manyAssets(MAX_GRAPH_ASSET_REFS) })),
    });
    const state = initialEvidenceGraphState(graph);
    expect(visibleEvidenceNodeIds(state, graph).length).toBeLessThanOrEqual(
      MAX_VISIBLE_EVIDENCE_NODES,
    );
    expect(searchEvidenceGraph('synthetic', graph).length).toBeLessThanOrEqual(
      MAX_EVIDENCE_SEARCH_RESULTS,
    );
  });
});

// ===========================================================================
// 6 · notes — placed where a person placed them, and nowhere else
// ===========================================================================

describe('evidence graph · a note is placed by a person, never by a proposal', () => {
  it('draws `mapped_to` for a path a PERSON named', () => {
    const graph = buildOk({
      notes: data(
        notesFixture({
          notes: [noteFixture({ mapped_field_path: 'sample.material.formula', state: 'mapped' })],
        }),
      ),
    });
    const edge = graph.edges.find((e) => e.kind === 'mapped_to');
    expect(edge, 'a mapped note should be joined to the address it was placed at').toBeTruthy();
    expect(edge?.containment).toBe(false);
    expect(edge?.why).toContain('writes no value, mints no evidence and confirms nothing');
  });

  it('draws NO relationship for a path a MACHINE merely proposed', () => {
    /*
     * NEGATIVE CONTROL. Its polarity is established by the test above: the very
     * same path, named by a person, demonstrably DOES produce an edge — so this is
     * not passing because `sample.material.formula` has no node to point at.
     */
    const graph = buildOk({
      notes: data(
        notesFixture({
          notes: [
            noteFixture({
              candidate_field_path: 'sample.material.formula',
              candidate_rule: 'a header in the campaign sheet matched this path',
            }),
          ],
        }),
      ),
    });
    expect(graph.edges.filter((e) => e.kind === 'mapped_to')).toHaveLength(0);
    // And the proposal is not hidden — it is shown, labelled as a proposal.
    const text = detailValues(graph, nodeIds.note('note-synthetic-0001'));
    expect(text).toContain('Proposed home (nobody has accepted this)');
    expect(text).toContain('A proposal, not a decision; no line is drawn for it');
  });

  it('hangs a note on the run it names, and says so when that run is not loaded', () => {
    const onRun = buildOk({
      notes: data(notesFixture({ notes: [noteFixture({ run_id: RUN_A })] })),
    });
    expect(onRun.byId.get(nodeIds.note('note-synthetic-0001'))?.parentId).toBe(
      nodeIds.run(RUN_A),
    );

    const offPage = buildOk({
      notes: data(notesFixture({ notes: [noteFixture({ run_id: RUN_GONE })] })),
    });
    expect(offPage.byId.get(nodeIds.note('note-synthetic-0001'))?.parentId).toBe(
      nodeIds.experiment(EXP),
    );
    expect(detailValues(offPage, nodeIds.note('note-synthetic-0001'))).toContain(
      'this run is not on the page of runs loaded here',
    );
  });

  it('keeps the verbatim capture beside a corrected wording', () => {
    const graph = buildOk({
      notes: data(
        notesFixture({
          notes: [
            noteFixture({
              revised_text: 'The second scan set ran after the cell was REASSEMBLED.',
              display_text: 'The second scan set ran after the cell was REASSEMBLED.',
            }),
          ],
        }),
      ),
    });
    const text = detailValues(graph, nodeIds.note('note-synthetic-0001'));
    expect(text).toContain('As originally captured');
    expect(text).toContain('The second scan set was run after the cell was reassembled.');
  });

  it('states on every note that it is not evidence and not a value', () => {
    const graph = buildOk({ notes: data(notesFixture()) });
    expect(detailValues(graph, nodeIds.note('note-synthetic-0001'))).toContain(
      'A note is not evidence, not a field value and not verified',
    );
  });
});

// ===========================================================================
// 7 · provenance — two dimensions, on the node that owns the address
// ===========================================================================

describe('evidence graph · where a value came from, and what establishes it', () => {
  it('puts both dimensions on the node that owns the address, and creates no node', () => {
    const without = buildOk();
    const withProv = buildOk({ provenance: data(provenanceFixture()) });
    // NO NODE IS CREATED — this route describes addresses this view already draws.
    expect(withProv.nodes.length).toBe(without.nodes.length);

    const sample = withProv.nodes.find((n) => n.kind === 'sample' && n.runId === null);
    const text = (sample?.detail ?? []).map((l) => `${l.term}: ${l.value}`).join('\n');
    expect(text).toContain('Where this came from · sample.material.formula: From a file');
    expect(text).toContain('Review state · sample.material.formula: Supported');
  });

  it('renders an origin by LOOKUP, so an origin the data does not carry never appears', () => {
    /*
     * `provenance.py:86-94`: `assistant` is a member of the dimension that NOTHING
     * IN THIS BUILD PRODUCES, and no surface may list it as an available
     * capability. This module therefore has no origin legend, no origin filter and
     * no origin inventory — an origin reaches the screen only attached to an
     * address that reported it. The positive half is the test above: "From a file"
     * DOES appear when the data says `file`.
     */
    const graph = buildOk({ provenance: data(provenanceFixture()) });
    const everyValue = graph.nodes
      .flatMap((n) => n.detail)
      .map((l) => l.value)
      .join('\n');
    expect(everyValue).toContain('From a file');
    expect(everyValue).not.toContain('From an assistant');
    expect(everyValue).not.toContain('From a transcript');
  });

  it('states what the route itself did not describe', () => {
    const graph = buildOk({
      provenance: data(
        provenanceFixture({ blocks_not_described: ['block:attribution', 'block:qc'] }),
      ),
    });
    const text = noteText(graph, 'provenance_undescribed');
    expect(text).toContain('block:attribution, block:qc');
    expect(text).toContain('counted rather than hidden');

    // POLARITY: nothing undescribed, no note.
    expect(noteKinds(buildOk({ provenance: data(provenanceFixture()) }))).not.toContain(
      'provenance_undescribed',
    );
  });

  it('does not draw a note twice — the notes route owns them', () => {
    const graph = buildOk({
      notes: data(notesFixture()),
      provenance: data(
        provenanceFixture({
          entries: [
            ...provenanceFixture().entries,
            {
              address: 'note:note-synthetic-0001',
              origins: ['manual'],
              primary_origin: 'manual',
              review_state: 'unmapped',
              evidence_count: 0,
              inherited: false,
              note_refs: ['note-synthetic-0001'],
              unavailable: false,
              resolution_state: 'absent',
            },
          ],
        }),
      ),
    });
    expect(graph.nodes.filter((n) => n.kind === 'note')).toHaveLength(1);
  });
});

// ===========================================================================
// 8 · historical versus current
// ===========================================================================

describe('evidence graph · what is historical versus current', () => {
  it('says the drawn content is on record as a revision, and draws no historical node', () => {
    const without = buildOk();
    const withRevs = buildOk({ revisions: data(revisionsFixture()) });
    // Not one node comes from the history. It is read for a SENTENCE.
    expect(withRevs.nodes.length).toBe(without.nodes.length);
    expect(noteText(withRevs, 'revision_state')).toContain(
      'on record as revision 2 of 2',
    );
    expect(noteText(withRevs, 'revision_state')).toContain('No earlier revision is drawn');
  });

  it('says the draft has moved when the whole history was read and none matches', () => {
    const graph = buildOk({
      revisions: data(
        revisionsFixture({ current_content_signature: 'sig-moved', total: 1, returned: 1 }),
      ),
    });
    expect(noteText(graph, 'revision_state')).toContain(
      'the draft has changed since the last one was recorded',
    );
  });

  it('refuses to conclude anything when the revision list is BOUNDED and none matches', () => {
    const graph = buildOk({
      revisions: data(
        revisionsFixture({ current_content_signature: 'sig-moved', total: 9, returned: 1 }),
      ),
    });
    const text = noteText(graph, 'revision_state');
    expect(text).toContain('9 revision(s) are recorded and 1 were read');
    expect(text).toContain('is not known from this page, so it is not stated');
    expect(text).not.toContain('the draft has changed since the last one was recorded');
  });

  it('says "no revision has been recorded yet" rather than "the draft has changed"', () => {
    // Zero is its own answer: with no revisions there is no "last one" for the
    // draft to have changed since, and the bounded-list branch below must not
    // reach it either.
    const graph = buildOk({
      revisions: data(revisionsFixture({ revisions: [], total: 0, returned: 0 })),
    });
    const text = noteText(graph, 'revision_state');
    expect(text).toContain('no revision of it has been recorded yet');
    expect(text).not.toContain('the draft has changed since the last one was recorded');
  });

  /*
   * THE CERTIFICATION IS ONLY VALID INSIDE ONE READ, and it was being made across
   * two. Found by independent review of the slice that added this file.
   *
   * Every branch above turns on whether `current_content_signature` — the signature
   * of the record AS THE HISTORY RESPONSE READ IT — appears among the revisions. On
   * a STALE read that signature belongs to a different version from the one every
   * node above was drawn from, so a match certifies content this response never saw
   * and a miss reports a divergence that may not exist. Measured before the fix, at
   * `record_rev: 2` against a record at `rev: 3`, the graph printed:
   *
   *     Everything drawn here is the record's CURRENT content, and that content is
   *     on record as revision 3 of 3.
   *
   * — i.e. "your changes are recorded" over a draft that has since moved. The
   * `sub_fetch_stale` note sat BELOW it and does not un-say it; this repository's
   * own rule is that a neighbouring worried note does not correct a claim.
   *
   * `unknown` takes the same arm as `stale`: a response that publishes no token has
   * not been SHOWN to describe this version, and `fresh` has to be earned.
   */
  it('refuses to certify — either way — when the history describes a DIFFERENT read', () => {
    for (const over of [
      { record_rev: 2 }, // stale: a real, different version
      { record_rev: undefined as unknown as number }, // unknown: no token at all
    ]) {
      const matching = buildOk({ revisions: data(revisionsFixture(over)) });
      const text = noteText(matching, 'revision_state');
      expect(text).toContain('could not be established');
      expect(text).toContain('read at a different version of this record');
      // Neither positive claim may be made from a read of another version.
      expect(text).not.toContain('on record as revision');
      expect(text).not.toContain('the draft has changed since the last one was recorded');
      // The staleness itself is still disclosed by the mechanism that owns it.
      expect(noteKinds(matching)).toContain('sub_fetch_stale');

      // …and the MISS arm is refused for the same reason, not just the match arm.
      const moved = buildOk({
        revisions: data(
          revisionsFixture({ ...over, current_content_signature: 'sig-moved', total: 1, returned: 1 }),
        ),
      });
      expect(noteText(moved, 'revision_state')).toContain('could not be established');
      expect(noteText(moved, 'revision_state')).not.toContain(
        'the draft has changed since the last one was recorded',
      );
    }
  });

  it('POLARITY: a history read at THIS version still certifies, and still says which', () => {
    // The half that makes the test above mean something. `revisionsFixture` is
    // `record_rev: 3`, which is `experimentDetail`'s own rev — so this is a fresh
    // read and every branch above stays reachable.
    const fresh = buildOk({ revisions: data(revisionsFixture()) });
    expect(noteText(fresh, 'revision_state')).toContain('on record as revision 2 of 2');
    expect(noteText(fresh, 'revision_state')).not.toContain('could not be established');
    expect(noteKinds(fresh)).not.toContain('sub_fetch_stale');

    const movedFresh = buildOk({
      revisions: data(
        revisionsFixture({ current_content_signature: 'sig-moved', total: 1, returned: 1 }),
      ),
    });
    expect(noteText(movedFresh, 'revision_state')).toContain(
      'the draft has changed since the last one was recorded',
    );
  });

  it("quotes the server's own sentence when the history is unavailable", () => {
    const graph = buildOk({
      revisions: data(
        revisionsFixture({
          availability: {
            state: 'unavailable',
            reason: 'tables_absent',
            message: 'Revision history tables are not present in this deployment.',
          },
          revisions: undefined,
        }),
      ),
    });
    expect(noteText(graph, 'revision_state')).toContain(
      'Revision history tables are not present in this deployment.',
    );
  });
});

// ===========================================================================
// 9 · the surface — scope, disclosure, and the unaccepted statement
// ===========================================================================

describe('evidence graph panel · the extra sources on screen', () => {
  const renderPanel = (over: Partial<Parameters<typeof EvidenceGraphPanel>[0]> = {}) =>
    render(
      <EvidenceGraphPanel
        experimentId={EXP}
        detail={detailFixture()}
        evidence={evidenceFixture}
        classification={classificationFixture}
        runs={[runFixture()]}
        runsMeta={{ total: 1, matched: 1, returned: 1, offset: 0 }}
        readInScope={null}
        currentScope={null}
        focusRunId={null}
        onFocusRun={() => {}}
        onRequestRunCheck={() => Promise.resolve({} as never)}
        {...over}
      />,
    );

  it('renders the disclosure VERBATIM from the constant, in both places', () => {
    const { container, getByTestId, getByText } = renderPanel(everySource());
    expect(getByTestId('evgraph-disclosure').textContent).toBe(EVIDENCE_GRAPH_DISCLOSURE);
    // The second rendering lives in the "what this graph will not draw" details.
    const legend = container.querySelector('.evgraph-legend');
    expect(legend?.textContent).toContain(EVIDENCE_GRAPH_DISCLOSURE);
    // …and the expansion now covers the relationships the new vocabulary adds.
    expect(legend?.textContent).toContain('no line marks one as the one a decision picked');
    expect(legend?.textContent).toContain('no earlier revision is drawn at all');
    expect(getByText(EVIDENCE_GRAPH_DISCLOSURE, { selector: '.evgraph-disclosure' })).toBeTruthy();
  });

  it('says conflicts were read for the record, not per run', () => {
    const { container } = renderPanel({ conflicts: data(conflictsFixture()) });
    const note = container.querySelector('[data-note="conflicts_record_scope"]');
    expect(note?.textContent).toContain('This view does not ask per run');

    // POLARITY: no conflicts read, no claim about their scope.
    const { container: bare } = renderPanel();
    expect(bare.querySelector('[data-note="conflicts_record_scope"]')).toBeNull();
  });

  it('offers a filter chip for every new kind that has members, and none for kinds that do not', () => {
    const { container } = renderPanel(everySource());
    const chipKinds = [...container.querySelectorAll('.evgraph-kind-chip')].map((el) =>
      el.getAttribute('data-kind'),
    );
    for (const kind of ['conflict', 'conflict_candidate', 'conflict_decision', 'note', 'asset_reference']) {
      expect(chipKinds, `no chip for ${kind}`).toContain(kind);
    }
    // Each chip is a real toggle with an accessible name and a pressed state.
    for (const chip of container.querySelectorAll('.evgraph-kind-chip')) {
      expect(chip.getAttribute('aria-pressed')).toBe('true');
      expect((chip.textContent ?? '').trim().length).toBeGreaterThan(0);
    }

    const { container: bare } = renderPanel();
    const bareKinds = [...bare.querySelectorAll('.evgraph-kind-chip')].map((el) =>
      el.getAttribute('data-kind'),
    );
    expect(bareKinds).not.toContain('conflict');
    expect(bareKinds).not.toContain('note');
  });

  it('every drawn node is in the accessible tree, including the new kinds', () => {
    const { container } = renderPanel(everySource());
    const rows = [...container.querySelectorAll('[role="treeitem"]')];
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row.getAttribute('aria-level')).toBeTruthy();
      expect((row.textContent ?? '').trim().length).toBeGreaterThan(0);
    }
    // The canvas is a picture and stays out of the accessibility tree.
    expect(container.querySelector('.evgraph-canvas')?.getAttribute('aria-hidden')).toBe('true');
  });

  it('gives no element a role its own tag may not carry, with every source loaded', () => {
    /*
     * The same structural check `evidence-graph.test.tsx` runs, re-run over the
     * shape THIS file adds — four more note kinds in the advisory list and a
     * `role="note"` lede in the details pane. `<li role="note">` shipped once
     * here and axe reported it at every scanned viewport; `note` is not one of
     * the roles ARIA lets an `<li>` take, and a `<p>` is.
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
    const { container } = renderPanel({
      ...everySource(),
      conflicts: { state: 'error', message: 'HTTP 503' },
      notes: data(notesFixture({ unreadable_entries: 2 })),
    });

    const advisories = [...container.querySelectorAll('.evgraph-notes > li')];
    expect(advisories.length).toBeGreaterThan(0);
    for (const li of advisories) {
      expect(li.getAttribute('role')).toBeNull();
      expect(li.querySelector('[role="note"]')?.textContent).toBe(li.textContent);
    }
    for (const li of container.querySelectorAll('li[role]')) {
      expect(LI_ALLOWED_ROLES).toContain(li.getAttribute('role'));
    }
    for (const el of container.querySelectorAll('[role="note"]')) {
      expect(['SPAN', 'P', 'DIV']).toContain(el.tagName);
    }
  });

  it('leads the details pane with what an unaccepted thing IS', () => {
    const { container } = renderPanel(everySource());
    const noteRow = container.querySelector('[role="treeitem"][data-kind="note"]');
    expect(noteRow, 'the note should be reachable in the tree').toBeTruthy();
    fireEvent.click(noteRow as HTMLElement);

    const lede = container.querySelector('.evgraph-detail-unaccepted');
    expect(lede?.textContent).toContain('Not a value, not evidence, not verified');

    // POLARITY: an ordinary node carries no such statement.
    const runRow = container.querySelector('[role="treeitem"][data-kind="run"]');
    fireEvent.click(runRow as HTMLElement);
    expect(container.querySelector('.evgraph-detail-unaccepted')).toBeNull();
  });
});

// ===========================================================================
// 10 · the panel's memo actually holds
// ===========================================================================

/*
 * WHY A SOURCE-SHAPE GUARD, AND WHAT IT DOES AND DOES NOT PROVE.
 *
 * `EvidenceGraphPanel` calls `buildEvidenceGraph` — and through it `computeLayout`,
 * an O(n²) relaxation over 240 passes, synchronously on the render path, for a
 * graph bounded at `MAX_EVIDENCE_GRAPH_NODES` — inside a `useMemo`. That memo is
 * only worth anything if EVERY member of its dependency array is referentially
 * stable across a render that changed none of them.
 *
 * It was not. `runsMeta` was built as an object literal in `EvidenceExplorer`'s
 * JSX, so the array changed on every render and the memo missed unconditionally.
 * MEASURED with a counting wrapper around `buildEvidenceGraph`: three parent
 * renders produced THREE builds with the literal and ONE with a stable object.
 * The slice that added the four extra sources made that deficit worse rather than
 * causing it — five more `useFetch` hooks are five more state transitions on that
 * component, and each one was a whole rebuild and a fresh layout.
 *
 * This guard is over the SHAPE of the call site rather than over a render count,
 * because counting renders means mounting the whole Evidence screen with its
 * bundle, its runs, its five sub-reads and its record-session poller — a fixture
 * whose failure mode is its own. So: no dependency of that memo may be handed to
 * the panel as an inline object or array literal.
 *
 * WHAT IT CANNOT SEE, stated rather than implied: a prop that is stable-looking at
 * the JSX but computed unmemoised one line above (`foo={makeIt()}`), and any
 * instability in a value the panel derives internally. It catches the established
 * shape — a literal in the JSX — which is the drift that actually happened.
 */
describe('evidence graph panel · every memo dependency arrives referentially stable', () => {
  it('EvidenceExplorer hands the panel no inline object or array literal', () => {
    const source = readFileSync(
      resolve(__dirname, '..', 'screens/EvidenceExplorer.tsx'),
      'utf8',
    );
    const open = source.indexOf('<EvidenceGraphPanel');
    expect(open, 'the panel should be mounted in EvidenceExplorer.tsx').toBeGreaterThan(-1);
    const jsx = source.slice(open, source.indexOf('/>', open));

    // Exactly the props that reach `buildEvidenceGraph`'s useMemo dependency array.
    const MEMO_DEPS = [
      'detail',
      'runs',
      'runsMeta',
      'evidence',
      'classification',
      'focusRunId',
      'readInScope',
      'currentScope',
      'conflicts',
      'notes',
      'provenance',
      'assets',
      'revisions',
    ];
    for (const prop of MEMO_DEPS) {
      const m = new RegExp(`\\b${prop}=\\{(.)`).exec(jsx);
      expect(m, `${prop} is not passed to the panel at all`).toBeTruthy();
      expect(
        m![1],
        `${prop} is passed as an inline ${m![1] === '{' ? 'object' : 'array'} literal, so the panel's useMemo misses on every render and the whole graph is rebuilt`,
      ).not.toBe('{');
      expect(m![1]).not.toBe('[');
    }
  });
});

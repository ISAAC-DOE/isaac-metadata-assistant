import { describe, it, expect } from 'vitest';

import {
  ALL_COMPLETE_STAGE_ID,
  EVIDENCE_CLASSES,
  UNRECOGNIZED_STAGE_ID,
  deriveApiSurface,
  deriveEvidenceTotals,
  deriveExportGate,
  deriveMemoryFacts,
  deriveOpenQuestions,
  deriveSchemaFacts,
  deriveWorkflowStages,
  deriveWorkspaceTotals,
} from '../lib/statisticsModel';
import { CANONICAL_STEPS } from '../lib/workflowSteps';
import { flattenOpenApi } from '../lib/apiDocsModel';
import { buildSchemaFieldTree, flattenFieldTree } from '../lib/schemaBrowser';
import type { RuntimeRecord } from '../lib/crossRecordTriage';
import type { ApiGraphStatus, ApiOpenApiResponse, ApiSchemaResponse } from '../lib/types';
import { openApiFixture, schemaBrowserFixture } from '../test/apiFixtures';

/**
 * The Statistics dashboard's derivation layer, tested WITHOUT React.
 *
 * Three properties carry most of the weight here, because they are the ones a
 * plausible-looking dashboard gets wrong:
 *
 *   1. EXCLUSIVITY. Status buckets and stage buckets each sum to the number of
 *      records, so no record can be counted twice or dropped. A future status or
 *      a future workflow step must surface in its own bucket rather than being
 *      folded into a known one.
 *   2. SCOPE. `GET /api/graph/status` carries two different served-file counts
 *      (the PATH SET and the CONTENT MANIFEST, deliberately different sets — see
 *      `CLAUDE.md` §17). A test passes a body where they differ and pins which
 *      one surfaces, because substituting one for the other is invisible in a
 *      body where they happen to agree.
 *   3. PRIVACY. Every derivation emits counts and provenance strings only. The
 *      adversarial fixture below hides an email address, a bearer token, a
 *      filesystem path and an IP address inside the INPUT; if any derivation
 *      ever widened to carry a title, an id or a field value, the privacy test
 *      fails on the output.
 *
 * Expected figures are computed from the fixtures rather than transcribed, and
 * no test asserts UI copy — these functions produce no sentences.
 */

/** One projected record, defaulted to a boring shape so each fixture row states
 *  only what it is about. Mirrors `runtime_records._project_one`'s allow-set. */
function rec(over: Partial<RuntimeRecord> & { experiment_id: string }): RuntimeRecord {
  return {
    title: 'Synthetic XANES — CuO (Cu K-edge)',
    status: 'needs_attention',
    pending_count: 0,
    exported: false,
    record_id: null,
    workflow: { current_step: 'complete_metadata', blocked: false, reopened: false },
    evidence_counts: {
      supported: 0,
      inferred_candidate: 0,
      insufficient_evidence: 0,
      conflicting_evidence: 0,
      unknown: 0,
      unreadable: 0,
    },
    artifact_state: 'none',
    record_rev: 1,
    updated_utc: '2026-07-01T00:00:00Z',
    navigate_to: `/record/${over.experiment_id}`,
    ...over,
  };
}

/**
 * The real canonical distribution of the synthetic seed set: five records —
 * 2 needs_attention, 1 ready_to_export, 1 in_review, 1 done/exported (the same
 * distribution `apiFixtures.RESET_STATE_COUNTS` pins for the demo reset).
 */
const SEEDS: RuntimeRecord[] = [
  rec({
    experiment_id: 'SEED-A',
    status: 'needs_attention',
    pending_count: 5,
    workflow: { current_step: 'complete_metadata', blocked: true, reopened: false },
    evidence_counts: {
      supported: 4,
      inferred_candidate: 2,
      insufficient_evidence: 5,
      conflicting_evidence: 0,
      unknown: 1,
      // NON-ZERO on purpose: with every seed at 0 the sixth class would be
      // summed into `totalFields` as nothing, and the exhaustiveness assertions
      // below would pass just as well with the class dropped entirely.
      unreadable: 2,
    },
  }),
  rec({
    experiment_id: 'SEED-B',
    status: 'needs_attention',
    pending_count: 2,
    workflow: { current_step: 'complete_metadata', blocked: true, reopened: false },
    evidence_counts: {
      supported: 6,
      inferred_candidate: 1,
      insufficient_evidence: 2,
      conflicting_evidence: 1,
      unknown: 0,
      unreadable: 0,
    },
  }),
  rec({
    experiment_id: 'SEED-C',
    status: 'ready_to_export',
    workflow: { current_step: 'export', blocked: false, reopened: false },
    evidence_counts: {
      supported: 9,
      inferred_candidate: 0,
      insufficient_evidence: 0,
      conflicting_evidence: 0,
      unknown: 0,
      unreadable: 0,
    },
  }),
  rec({
    experiment_id: 'SEED-D',
    status: 'in_review',
    workflow: { current_step: 'review_export_readiness', blocked: false, reopened: true },
    evidence_counts: {
      supported: 7,
      inferred_candidate: 0,
      insufficient_evidence: 1,
      conflicting_evidence: 2,
      unknown: 0,
      unreadable: 0,
    },
  }),
  rec({
    experiment_id: 'SEED-E',
    status: 'done',
    exported: true,
    record_id: '01SYNTHRECORD00000000000000',
    workflow: { current_step: null, blocked: false, reopened: false },
    evidence_counts: {
      supported: 9,
      inferred_candidate: 0,
      insufficient_evidence: 0,
      conflicting_evidence: 0,
      unknown: 0,
      unreadable: 0,
    },
    artifact_state: 'stale',
  }),
];

const SEED_BODY = { records: SEEDS, total: SEEDS.length };
const EMPTY_BODY: { records: RuntimeRecord[]; total: number } = { records: [], total: 0 };

/** Sum one evidence class straight off the fixture, so no expectation is typed twice. */
function seedSum(key: keyof RuntimeRecord['evidence_counts'], rows = SEEDS): number {
  return rows.reduce((n, r) => n + r.evidence_counts[key], 0);
}

function graphStatus(over: Partial<ApiGraphStatus> = {}): ApiGraphStatus {
  return {
    plane: 'memory',
    availability: 'available',
    integrity: 'verified',
    provider: 'sanitized-snapshot',
    memory_policy: 'current',
    indexed_sources: 'current',
    policy_fingerprint: 'sha256:fakepolicyfingerprint0000000000000000000000000000',
    served_manifest_fingerprint: 'sha256:fakemanifestfingerprint00000000000000000000000000',
    served_file_count: 200,
    freshness_scope: 'served_files_only',
    freshness_basis: 'ci_content_manifest',
    source_graph_commit: '5b08ce5aaaa1111',
    snapshot_schema_version: 1,
    deployed_app_commit: '5b08ce5aaaa1111',
    note: 'Project memory returns leads to verify — never a validation verdict.',
    node_count: 220,
    edge_count: 508,
    community_count: 17,
    file_count: 201,
    concept_count: 19,
    graph_mtime: null,
    ...over,
  };
}

const OPENAPI = openApiFixture as unknown as ApiOpenApiResponse;

// --- workspace totals --------------------------------------------------------

describe('deriveWorkspaceTotals', () => {
  it('reports the canonical seed distribution (2 / 1 / 1 / 1)', () => {
    const t = deriveWorkspaceTotals(SEED_BODY);
    expect(t.needsAttention).toBe(2);
    expect(t.readyToExport).toBe(1);
    expect(t.inReview).toBe(1);
    expect(t.exported).toBe(1);
    expect(t.unknownStatus).toBe(0);
  });

  it('reports the SERVER denominator, not the length of the page it received', () => {
    // A truncated page must never be presented as the whole workspace.
    const t = deriveWorkspaceTotals({ records: SEEDS.slice(0, 2), total: 5 });
    expect(t.total).toBe(5);
    expect(t.needsAttention + t.inReview + t.readyToExport + t.exported + t.unknownStatus).toBe(2);
  });

  it('status buckets are exclusive and sum to records.length', () => {
    const t = deriveWorkspaceTotals(SEED_BODY);
    expect(t.needsAttention + t.inReview + t.readyToExport + t.exported + t.unknownStatus).toBe(
      SEEDS.length,
    );
  });

  it('an unknown/future status lands in unknownStatus, never folded into a known bucket', () => {
    const body = {
      records: [...SEEDS, rec({ experiment_id: 'SEED-F', status: 'awaiting_mentor_review' })],
      total: 6,
    };
    const t = deriveWorkspaceTotals(body);
    expect(t.unknownStatus).toBe(1);
    // Every known bucket is unchanged by the unknown row.
    const base = deriveWorkspaceTotals(SEED_BODY);
    expect(t.needsAttention).toBe(base.needsAttention);
    expect(t.inReview).toBe(base.inReview);
    expect(t.readyToExport).toBe(base.readyToExport);
    expect(t.exported).toBe(base.exported);
    // and the invariant still holds with it counted.
    expect(t.needsAttention + t.inReview + t.readyToExport + t.exported + t.unknownStatus).toBe(6);
  });

  it('the exclusivity invariant survives an unknown status carrying exported: true', () => {
    // `status === 'done'` iff `exported === true` for every body the backend
    // produces; bucketing on the exclusive status is what keeps the sum exact
    // even when a row does not follow that rule.
    const body = {
      records: [rec({ experiment_id: 'ODD', status: 'archived', exported: true, record_id: 'R' })],
      total: 1,
    };
    const t = deriveWorkspaceTotals(body);
    expect(t.exported).toBe(0);
    expect(t.unknownStatus).toBe(1);
    expect(t.needsAttention + t.inReview + t.readyToExport + t.exported + t.unknownStatus).toBe(1);
  });

  it('empty input yields all-zero totals and does not throw', () => {
    expect(deriveWorkspaceTotals(EMPTY_BODY)).toEqual({
      total: 0,
      needsAttention: 0,
      inReview: 0,
      readyToExport: 0,
      exported: 0,
      unknownStatus: 0,
    });
  });
});

// --- workflow stages ---------------------------------------------------------

describe('deriveWorkflowStages', () => {
  it('emits all six buckets, in canonical order, including the zeros', () => {
    const buckets = deriveWorkflowStages(SEEDS);
    expect(buckets.map((b) => b.id)).toEqual([
      ...CANONICAL_STEPS.map((s) => s.id),
      ALL_COMPLETE_STAGE_ID,
    ]);
    // Zero-count stages are present, so the axis does not reshape as records move.
    expect(buckets.filter((b) => b.count === 0).length).toBeGreaterThan(0);
    expect(buckets.every((b) => b.label.length > 0)).toBe(true);
  });

  it('labels each canonical step with the backend’s own label', () => {
    const buckets = deriveWorkflowStages(SEEDS);
    for (const step of CANONICAL_STEPS) {
      expect(buckets.find((b) => b.id === step.id)?.label).toBe(step.label);
    }
  });

  it('distributes records by current_step, with null in the all-complete bucket', () => {
    const byId = new Map(deriveWorkflowStages(SEEDS).map((b) => [b.id, b.count]));
    expect(byId.get('complete_metadata')).toBe(2);
    expect(byId.get('review_export_readiness')).toBe(1);
    expect(byId.get('export')).toBe(1);
    expect(byId.get(ALL_COMPLETE_STAGE_ID)).toBe(1);
    expect(byId.get('load_record')).toBe(0);
    expect(byId.get('review_evidence')).toBe(0);
  });

  it('stage buckets are exclusive and sum to records.length', () => {
    const total = deriveWorkflowStages(SEEDS).reduce((n, b) => n + b.count, 0);
    expect(total).toBe(SEEDS.length);
  });

  it('never counts a record twice via the blocked/reopened OR-reductions', () => {
    // Both booleans true on one record: those are OR-reductions over all five
    // steps and are not mutually exclusive, so counting by them would inflate
    // the distribution. Only `current_step` may be read.
    const rows = [
      rec({
        experiment_id: 'BOTH',
        workflow: { current_step: 'review_evidence', blocked: true, reopened: true },
      }),
    ];
    const buckets = deriveWorkflowStages(rows);
    expect(buckets.reduce((n, b) => n + b.count, 0)).toBe(1);
    expect(buckets.find((b) => b.id === 'review_evidence')?.count).toBe(1);
  });

  it('an unrecognized step id is surfaced in its own bucket, never dropped or guessed', () => {
    const rows = [...SEEDS, rec({ experiment_id: 'FUTURE', workflow: { current_step: 'mentor_sign_off', blocked: false, reopened: false } })];
    const buckets = deriveWorkflowStages(rows);
    expect(buckets.reduce((n, b) => n + b.count, 0)).toBe(rows.length);
    expect(buckets.find((b) => b.id === UNRECOGNIZED_STAGE_ID)?.count).toBe(1);
    // No canonical bucket absorbed it.
    for (const step of CANONICAL_STEPS) {
      const before = deriveWorkflowStages(SEEDS).find((b) => b.id === step.id)?.count;
      expect(buckets.find((b) => b.id === step.id)?.count).toBe(before);
    }
  });

  it('emits no unrecognized bucket for a body the current backend produces', () => {
    expect(deriveWorkflowStages(SEEDS).map((b) => b.id)).not.toContain(UNRECOGNIZED_STAGE_ID);
  });

  it('empty input yields six zero buckets and does not throw', () => {
    const buckets = deriveWorkflowStages([]);
    expect(buckets).toHaveLength(CANONICAL_STEPS.length + 1);
    expect(buckets.every((b) => b.count === 0)).toBe(true);
  });
});

// --- evidence ----------------------------------------------------------------

describe('deriveEvidenceTotals', () => {
  it('sums each of the five classes across every record', () => {
    const t = deriveEvidenceTotals(SEEDS);
    expect(t.supported).toBe(seedSum('supported'));
    expect(t.inferredCandidate).toBe(seedSum('inferred_candidate'));
    expect(t.insufficientEvidence).toBe(seedSum('insufficient_evidence'));
    expect(t.conflictingEvidence).toBe(seedSum('conflicting_evidence'));
    expect(t.unknown).toBe(seedSum('unknown'));
    expect(t.unreadable).toBe(seedSum('unreadable'));
  });

  it('totalFields is the sum of the six, and is FIELDS — not records', () => {
    const t = deriveEvidenceTotals(SEEDS);
    const expected =
      t.supported +
      t.inferredCandidate +
      t.insufficientEvidence +
      t.conflictingEvidence +
      t.unknown +
      t.unreadable;
    expect(t.totalFields).toBe(expected);
    expect(t.recordsCounted).toBe(SEEDS.length);
    // The unit distinction is the point: many fields per record.
    expect(t.totalFields).toBeGreaterThan(t.recordsCounted);
  });

  it('carries the six classes in the backend’s display precedence, not by count', () => {
    expect(EVIDENCE_CLASSES.map((c) => c.key)).toEqual([
      'supported',
      'inferred_candidate',
      'insufficient_evidence',
      'conflicting_evidence',
      'unknown',
      // `unreadable` — a READ FAILURE, never folded into `unknown`, which claims
      // nothing defensible is recorded. Listed here because `deriveEvidenceTotals`
      // sums only what this array names, so an omission is a silent undercount of
      // `totalFields`, i.e. of the stacked bar's own denominator.
      'unreadable',
    ]);
    // Precedence is fixed, so it must NOT track the fixture's counts.
    const t = deriveEvidenceTotals(SEEDS);
    const counts = EVIDENCE_CLASSES.map((c) => t[c.field]);
    expect([...counts].sort((a, b) => b - a)).not.toEqual(counts);
  });

  it('empty input yields all-zero totals and does not throw', () => {
    expect(deriveEvidenceTotals([])).toEqual({
      supported: 0,
      inferredCandidate: 0,
      insufficientEvidence: 0,
      conflictingEvidence: 0,
      unknown: 0,
      unreadable: 0,
      totalFields: 0,
      recordsCounted: 0,
    });
  });
});

// --- export gate -------------------------------------------------------------

describe('deriveExportGate', () => {
  it('reports where each record stands right now', () => {
    const g = deriveExportGate(SEEDS);
    expect(g.exported).toBe(1);
    expect(g.readyNow).toBe(1);
    expect(g.blockedByGate).toBe(1);
    expect(g.blockedByQuestions).toBe(2);
    expect(g.staleArtifacts).toBe(1);
  });

  it('never produces a passed / failed / not_run field — no such state is stored', () => {
    const g = deriveExportGate(SEEDS);
    const keys = Object.keys(g);
    for (const forbidden of ['passed', 'failed', 'notRun', 'not_run', 'valid', 'invalid', 'verdict']) {
      expect(keys).not.toContain(forbidden);
    }
    expect(JSON.stringify(g)).not.toMatch(/pass|fail|not.?run|verdict/i);
  });

  it('staleArtifacts is a separate axis that overlaps the status buckets', () => {
    // The one stale record is also the exported one, so the counts deliberately
    // do not partition the workspace and must never be summed.
    const g = deriveExportGate(SEEDS);
    expect(g.exported + g.readyNow + g.blockedByGate + g.blockedByQuestions).toBe(SEEDS.length);
    expect(g.staleArtifacts).toBe(1);
  });

  it('empty input yields all-zero counts and does not throw', () => {
    expect(deriveExportGate([])).toEqual({
      exported: 0,
      readyNow: 0,
      blockedByGate: 0,
      blockedByQuestions: 0,
      staleArtifacts: 0,
    });
  });

  /*
   * ONE FIELD FOR ONE WORD.
   *
   * The page renders `deriveWorkspaceTotals().exported` as the "Exported" card
   * and `deriveExportGate().exported` as the "Exported" row, on the same screen,
   * from the same body. They used to read DIFFERENT fields — the exclusive
   * `status` and the `exported` boolean — which agree for every body the backend
   * produces but not for an inconsistent one, and the row below is exactly such a
   * row (it is the same shape as the adversarial case in the totals suite above).
   * Two numbers under one word is the defect; this pins the fix, without asking
   * `deriveWorkspaceTotals` to give up the exact-sum invariant that made it read
   * the status in the first place.
   */
  it('agrees with deriveWorkspaceTotals on "Exported" even for an INCONSISTENT row', () => {
    const inconsistent = [
      rec({ experiment_id: 'ODD', status: 'archived', exported: true, record_id: 'R' }),
    ];
    const gate = deriveExportGate(inconsistent);
    const totals = deriveWorkspaceTotals({ records: inconsistent, total: 1 });

    // The row claims `exported: true` under a status this client cannot place, so
    // neither derivation may count it as exported — and neither may disagree.
    expect(gate.exported).toBe(totals.exported);
    expect(gate.exported).toBe(0);
    expect(totals.unknownStatus).toBe(1);
  });

  it('agrees with deriveWorkspaceTotals on "Exported" for every consistent body too', () => {
    // The property, not just the adversarial case: the seeds are a normal body.
    expect(deriveExportGate(SEEDS).exported).toBe(deriveWorkspaceTotals(SEED_BODY).exported);
    expect(deriveExportGate(SEEDS).exported).toBe(1);
  });
});

// --- Project Memory ----------------------------------------------------------

describe('deriveMemoryFacts', () => {
  it('reads file_count (the served PATH SET) and NOT served_file_count (the content manifest)', () => {
    // The two are deliberately different sets and differ by exactly one in the
    // real snapshot; a body where they agree could not detect a substitution.
    const facts = deriveMemoryFacts(graphStatus({ file_count: 201, served_file_count: 200 }));
    expect(facts.servedFiles).toBe(201);
    expect(facts.servedFiles).not.toBe(200);
  });

  it('carries the counts the live response returned', () => {
    const g = graphStatus();
    const facts = deriveMemoryFacts(g);
    expect(facts.nodes).toBe(g.node_count);
    expect(facts.edges).toBe(g.edge_count);
    expect(facts.concepts).toBe(g.concept_count);
    expect(facts.communities).toBe(g.community_count);
    expect(facts.snapshotSchemaVersion).toBe(g.snapshot_schema_version);
  });

  it('a null count stays null — never defaulted to zero', () => {
    const facts = deriveMemoryFacts(
      graphStatus({
        node_count: null,
        edge_count: null,
        community_count: null,
        file_count: null,
        concept_count: null,
        snapshot_schema_version: null,
      }),
    );
    for (const value of [
      facts.nodes,
      facts.edges,
      facts.communities,
      facts.servedFiles,
      facts.concepts,
      facts.snapshotSchemaVersion,
    ]) {
      expect(value).toBeNull();
    }
  });

  it('equal-prefix commits ⇒ current', () => {
    const facts = deriveMemoryFacts(
      graphStatus({ source_graph_commit: '5b08ce5aaaa1111', deployed_app_commit: '5b08ce5' }),
    );
    expect(facts.freshness).toBe('current');
  });

  it('differing commits ⇒ point_in_time', () => {
    const facts = deriveMemoryFacts(
      graphStatus({ source_graph_commit: '5b08ce5aaaa1111', deployed_app_commit: '9999999bbbb2222' }),
    );
    expect(facts.freshness).toBe('point_in_time');
  });

  it('a null deployed commit ⇒ undetermined, and is NOT reported as current', () => {
    const facts = deriveMemoryFacts(graphStatus({ deployed_app_commit: null }));
    expect(facts.freshness).toBe('undetermined');
    expect(facts.freshness).not.toBe('current');
    expect(facts.deployedAppCommit).toBeNull();
  });

  it('a null source commit ⇒ undetermined, and is NOT reported as current', () => {
    const facts = deriveMemoryFacts(graphStatus({ source_graph_commit: null }));
    expect(facts.freshness).toBe('undetermined');
    expect(facts.freshness).not.toBe('current');
  });

  it('a shared prefix too short to compare ⇒ undetermined, never current', () => {
    const facts = deriveMemoryFacts(
      graphStatus({ source_graph_commit: '5b08ce5aaaa1111', deployed_app_commit: '5b08c' }),
    );
    expect(facts.freshness).toBe('undetermined');
  });

  it('is pure: the same body derives the same facts', () => {
    const g = graphStatus();
    expect(deriveMemoryFacts(g)).toEqual(deriveMemoryFacts(g));
  });
});

// --- API surface -------------------------------------------------------------

describe('deriveApiSurface', () => {
  it('counts operations from the document, never from a hand-maintained catalog', () => {
    const surface = deriveApiSurface(OPENAPI);
    expect(surface.operationCount).toBe(flattenOpenApi(OPENAPI).length);
    expect(surface.operationCount).toBeGreaterThan(0);
  });

  it('byMethod sums to operationCount and orders GET before POST', () => {
    const surface = deriveApiSurface(OPENAPI);
    expect(surface.byMethod.reduce((n, m) => n + m.count, 0)).toBe(surface.operationCount);
    const methods = surface.byMethod.map((m) => m.method);
    expect(methods.indexOf('get')).toBeLessThan(methods.indexOf('post'));
    // Only methods the contract documents appear — no invented zero rows.
    expect(surface.byMethod.every((m) => m.count > 0)).toBe(true);
  });

  it('byGroup sums to operationCount and follows the document’s tag registration order', () => {
    const surface = deriveApiSurface(OPENAPI);
    expect(surface.byGroup.reduce((n, g) => n + g.count, 0)).toBe(surface.operationCount);
    expect(surface.groupCount).toBe(surface.byGroup.length);

    // Registration order comes from the document's own `tags` array — the same
    // ordering the Endpoint Explorer uses, because it is the same code.
    const registered = (OPENAPI.tags ?? []).map((t) => t.name);
    const derived = surface.byGroup.map((g) => g.group);
    const registeredInOrder = derived.filter((g) => registered.includes(g));
    expect(registeredInOrder).toEqual(registered.filter((g) => derived.includes(g)));
    // The fixture's registration order is deliberately non-alphabetical.
    expect([...registeredInOrder].sort()).not.toEqual(registeredInOrder);
    // A registered tag no operation uses must not conjure an empty group.
    expect(surface.byGroup.every((g) => g.count > 0)).toBe(true);
  });

  it('an empty document yields zero counts and does not throw', () => {
    const surface = deriveApiSurface({ openapi: '3.1.0', paths: {} });
    expect(surface).toEqual({ operationCount: 0, groupCount: 0, byMethod: [], byGroup: [] });
  });
});

// --- privacy -----------------------------------------------------------------

describe('privacy — derivations emit counts and provenance strings only', () => {
  /** Sensitive-looking material planted in the INPUT. If any derivation ever
   *  widened to carry a title, an id, or a field value, it would show up in the
   *  serialized output below. */
  const ADVERSARIAL: RuntimeRecord[] = [
    rec({
      experiment_id: '01SECRETEXPERIMENTID0000000',
      title: 'ops@example.com Bearer sk-token secret /Users/someone/data 10.0.0.5 — 8979 eV',
      status: 'needs_attention',
      pending_count: 3,
      record_id: '01SECRETRECORDID000000000000',
      navigate_to: '/record/01SECRETEXPERIMENTID0000000',
    }),
    ...SEEDS,
  ];

  const outputs: unknown[] = [
    deriveWorkspaceTotals({ records: ADVERSARIAL, total: ADVERSARIAL.length }),
    deriveWorkflowStages(ADVERSARIAL),
    deriveEvidenceTotals(ADVERSARIAL),
    deriveExportGate(ADVERSARIAL),
    deriveOpenQuestions(ADVERSARIAL),
    deriveMemoryFacts(
      graphStatus({
        note: 'ops@example.com Bearer secret cookie authorization /Users/someone 10.0.0.5',
      }),
    ),
    deriveApiSurface(OPENAPI),
  ];

  const FORBIDDEN: readonly (string | RegExp)[] = [
    '@',
    'Bearer',
    /authorization/i,
    /cookie/i,
    /token/i,
    /secret/i,
    '/Users/',
    /\b\d{1,3}(?:\.\d{1,3}){3}\b/, // an IP-address-shaped substring
  ];

  it('no derivation output contains a credential, a path, an address, or an email', () => {
    for (const output of outputs) {
      const serialized = JSON.stringify(output);
      for (const needle of FORBIDDEN) {
        if (typeof needle === 'string') {
          expect(serialized.includes(needle), `${needle} leaked into ${serialized}`).toBe(false);
        } else {
          expect(needle.test(serialized), `${needle} leaked into ${serialized}`).toBe(false);
        }
      }
    }
  });

  it('no derivation output contains a record title, an id, or a scientific value', () => {
    for (const output of outputs) {
      const serialized = JSON.stringify(output);
      for (const record of ADVERSARIAL) {
        expect(serialized).not.toContain(record.title);
        expect(serialized).not.toContain(record.experiment_id);
        if (record.record_id) expect(serialized).not.toContain(record.record_id);
        expect(serialized).not.toContain(record.navigate_to);
        expect(serialized).not.toContain(record.updated_utc);
      }
      expect(serialized).not.toContain('8979');
      expect(serialized).not.toMatch(/\beV\b/);
    }
  });

  it('no derivation output carries a telemetry-shaped field', () => {
    for (const output of outputs) {
      const serialized = JSON.stringify(output);
      expect(serialized).not.toMatch(
        /request|visit|session|user|latency|uptime|database|hostname|origin/i,
      );
    }
  });
});

// --- open questions -----------------------------------------------------------

describe('deriveOpenQuestions', () => {
  it('sums the seed set\'s question counts and reports the three record tallies', () => {
    /* SEEDS carry pending_count 5, 2, 0, 0, 0 and workflow flags blocked on the
       first two, reopened on the fourth. Transcribed by hand from the fixture
       above, not recomputed, so a change to either would have to be noticed. */
    expect(deriveOpenQuestions(SEEDS)).toEqual({
      recordsCounted: 5,
      recordsWithUnreadableCount: 0,
      totalOpenQuestions: 7,
      recordsWithOpenQuestions: 2,
      mostOnOneRecord: 5,
      recordsWithBlockedStep: 2,
      recordsWithReopenedStep: 1,
    });
  });

  it('an empty set yields zeros without inventing a maximum', () => {
    expect(deriveOpenQuestions([])).toEqual({
      recordsCounted: 0,
      recordsWithUnreadableCount: 0,
      totalOpenQuestions: 0,
      recordsWithOpenQuestions: 0,
      mostOnOneRecord: 0,
      recordsWithBlockedStep: 0,
      recordsWithReopenedStep: 0,
    });
  });

  it('a non-numeric pending_count is counted as UNREADABLE, never as zero', () => {
    /* The distinction that matters: treating it as zero shrinks a total a reader
       would take as complete. `recordsWithUnreadableCount` makes the shortfall
       statable, and the record still contributes its workflow flags. */
    const broken = [
      rec({ experiment_id: 'X', pending_count: undefined as unknown as number }),
      rec({ experiment_id: 'Y', pending_count: 4, workflow: { current_step: null, blocked: true, reopened: true } }),
    ];
    const questions = deriveOpenQuestions(broken);
    expect(questions.recordsWithUnreadableCount).toBe(1);
    expect(questions.totalOpenQuestions).toBe(4);
    expect(questions.recordsWithOpenQuestions).toBe(1);
    expect(questions.recordsCounted).toBe(2);
    expect(questions.recordsWithBlockedStep).toBe(1);
    expect(questions.recordsWithReopenedStep).toBe(1);
  });

  it('blocked and reopened are SEPARATE axes, and one record may be in both', () => {
    const both = [
      rec({
        experiment_id: 'BOTH',
        pending_count: 1,
        workflow: { current_step: 'export', blocked: true, reopened: true },
      }),
    ];
    const questions = deriveOpenQuestions(both);
    expect(questions.recordsWithBlockedStep).toBe(1);
    expect(questions.recordsWithReopenedStep).toBe(1);
    // …so the two must never be added: their sum exceeds the record count.
    expect(
      questions.recordsWithBlockedStep + questions.recordsWithReopenedStep,
    ).toBeGreaterThan(questions.recordsCounted);
  });
});

// --- the official schema's own shape -----------------------------------------

/*
 * NOT swept by the record-privacy block above, and deliberately so: this
 * derivation never sees a record. Its input is the vendored PUBLIC schema and
 * the committed vocabulary files, so there is no title, id or scientific value
 * in scope for it to leak. What it CAN get wrong is a count, which is what these
 * assert.
 */
describe('deriveSchemaFacts', () => {
  const SCHEMA = schemaBrowserFixture as unknown as ApiSchemaResponse;

  /*
   * Every literal below is derived BY HAND from `schemaBrowserFixture`:
   *
   *   top-level: isaac_record_version · record_id · record_type · descriptors ·
   *              sample · tags                                              = 6
   *   required (root): isaac_record_version, record_id, record_type         = 3
   *   all depths: the three scalars (3) + descriptors > outputs > descriptors
   *               > name (4) + sample > {sample_form, material > formula} (4)
   *               + tags (1)                                                = 12
   *   enums: record_type only                                               = 1
   *   allOf rules: one at the root, one under `sample`                      = 2
   *   vocabularies: descriptor_class, whose entries are
   *                 classes.spectroscopy (2) + products (2)                 = 4
   */
  it('counts the fixture schema the way the Schema Reference browser walks it', () => {
    expect(deriveSchemaFacts(SCHEMA)).toEqual({
      schemaTitle: 'ISAAC AI-Ready Scientific Record v1.05 (fixture)',
      schemaVersion: '1.05',
      topLevelFields: 6,
      totalFields: 12,
      requiredTopLevelFields: 3,
      fieldsWithEnumeratedValues: 1,
      conditionalRules: 2,
      bySection: [
        { section: 'isaac_record_version', count: 1 },
        { section: 'record_id', count: 1 },
        { section: 'record_type', count: 1 },
        { section: 'descriptors', count: 4 },
        { section: 'sample', count: 4 },
        { section: 'tags', count: 1 },
      ],
      vocabularyFiles: 1,
      vocabularyTerms: 4,
      byVocabulary: [{ name: 'descriptor_class', entryCount: 4 }],
    });
  });

  it('the section counts partition the field total, by construction', () => {
    const facts = deriveSchemaFacts(SCHEMA);
    expect(facts.bySection.reduce((n, s) => n + s.count, 0)).toBe(facts.totalFields);
  });

  it('the field total agrees with the browser\'s own traversal, not with a second walker', () => {
    /* The point of reusing `buildSchemaFieldTree`/`flattenFieldTree`: this
       assertion could only fail if Statistics grew a walker of its own. */
    const facts = deriveSchemaFacts(SCHEMA);
    expect(facts.totalFields).toBe(flattenFieldTree(buildSchemaFieldTree(SCHEMA.schema)).length);
  });

  it('an empty document yields zeros and a null title, and does not throw', () => {
    expect(
      deriveSchemaFacts({ schema_title: null, schema_version: '', schema: {}, vocabularies: {} }),
    ).toEqual({
      schemaTitle: null,
      schemaVersion: null,
      topLevelFields: 0,
      totalFields: 0,
      requiredTopLevelFields: 0,
      fieldsWithEnumeratedValues: 0,
      conditionalRules: 0,
      bySection: [],
      vocabularyFiles: 0,
      vocabularyTerms: 0,
      byVocabulary: [],
    });
  });

  it('a malformed body degrades to zeros rather than throwing during render', () => {
    /* There is no ErrorBoundary in this app, so a throw here would blank the
       whole SPA rather than one section. The types say these fields exist; the
       wire does not. */
    const facts = deriveSchemaFacts({} as unknown as ApiSchemaResponse);
    expect(facts.totalFields).toBe(0);
    expect(facts.schemaVersion).toBeNull();
    expect(facts.byVocabulary).toEqual([]);
  });
});

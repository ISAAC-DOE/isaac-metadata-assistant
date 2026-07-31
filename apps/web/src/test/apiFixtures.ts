/*
 * Test doubles for the FastAPI backend: realistic response fixtures (shapes
 * verbatim from apps/api/isaac_api/{routes,serialize}.py — see
 * .superpowers/sdd/task-1-report.md) + a tiny route-keyed fetch stub.
 * Values are unmistakably synthetic.
 */

import { vi } from 'vitest';

import type { ApiWorkflow } from '../lib/types';

// --- backend-derived workflow (P28.1) -----------------------------------
// Mirrors apps/api/isaac_api/workflow.py `derive_workflow` so detail fixtures
// carry the same shape the real backend ships. Kept here (not re-derived in the
// app) because the app renders the workflow verbatim; only fixtures synthesize it.
const WF_ORDER = [
  'load_record',
  'complete_metadata',
  'review_evidence',
  'review_export_readiness',
  'export',
] as const;
const WF_LABELS: Record<string, string> = {
  load_record: 'Load Record',
  complete_metadata: 'Complete Metadata',
  review_evidence: 'Review Evidence',
  review_export_readiness: 'Review Export Readiness',
  export: 'Export',
};
const WF_REOPENED_REASON =
  'An upstream change reopened this step; it no longer reflects the current record.';

export function fixtureWorkflow(s: {
  pending_count: number;
  draft_ok: boolean;
  ready: boolean;
  exported: boolean;
  rev: number;
}): ApiWorkflow {
  const satisfied: Record<string, boolean> = {
    load_record: true,
    complete_metadata: s.pending_count === 0,
    review_evidence: s.pending_count === 0 && s.draft_ok,
    review_export_readiness: s.ready,
    export: s.exported,
  };
  const currentStep = WF_ORDER.find((id) => !satisfied[id]) ?? null;
  const currentLabel = currentStep ? WF_LABELS[currentStep] : null;
  const ordered_steps = WF_ORDER.map((id, i) => {
    if (satisfied[id]) {
      return { id, label: WF_LABELS[id], state: 'completed' as const, current: false, reopened: false, blocked: false, reason: null };
    }
    const current = id === currentStep;
    const reopened = WF_ORDER.slice(i + 1).some((later) => satisfied[later]);
    const blocked = !current && !reopened;
    const state = current ? ('current' as const) : reopened ? ('reopened' as const) : ('blocked' as const);
    const reason = current ? null : reopened ? WF_REOPENED_REASON : `Complete '${currentLabel}' first.`;
    return { id, label: WF_LABELS[id], state, current, reopened, blocked, reason };
  });
  return { ordered_steps, current_step: currentStep, record_rev: s.rev };
}

// --- fetch stub ---------------------------------------------------------

export interface StubbedRoute {
  status?: number;
  body: unknown;
  /** Optional `ETag` response header (P27.6 conditional GET). */
  etag?: string;
}

/** The per-call descriptor a route-thunk resolves to (P27.6 conditional GET). */
export interface RouteResult {
  status?: number;
  body?: unknown;
  etag?: string;
}

/**
 * A route may be a static {@link StubbedRoute} OR a thunk called ONCE per fetch
 * (with that request's `RequestInit`) that returns the response descriptor for
 * that call — the latter lets a test sequence a record's conditional GET (e.g.
 * 304, 304, then 200-with-new-version) with the status, body and ETag advancing
 * in lockstep, and branch on the `If-None-Match` header so the SAME endpoint can
 * serve a plain GET (no token) and a conditional GET (token) differently.
 */
export type RouteEntry = StubbedRoute | ((init?: RequestInit) => RouteResult);

/**
 * Stub `fetch` with a `"METHOD /api/path" -> response` map. Returns the list of
 * keys actually requested (for asserting which endpoints were hit). Unknown
 * routes reject like a network error so tests fail loudly.
 */
export function stubFetchRoutes(routes: Record<string, RouteEntry>): string[] {
  const calls: string[] = [];
  const impl = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url =
      typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    const key = `${method} ${url.replace(/^https?:\/\/[^/]+/, '')}`;
    calls.push(key);
    const hit = routes[key];
    if (!hit) throw new TypeError(`fetch stub: no route for ${key}`);
    // A whole-route thunk resolves the descriptor once per fetch (status/body/etag
    // in sync); a plain StubbedRoute is used as-is, and its `body` may itself be a
    // thunk re-evaluated per hit (e.g. the experiment list before/after a reset).
    const resolved: RouteResult = typeof hit === 'function' ? hit(init) : hit;
    const status = resolved.status ?? 200;
    const body =
      typeof resolved.body === 'function' ? (resolved.body as () => unknown)() : resolved.body;
    const etag = resolved.etag;
    // A minimal Headers-like shape: real fetch exposes `headers.get('ETag')` and
    // a 304 carries no body (ok:false, status 304). checkRecordVersion branches
    // on status before reading json(), so a 304 body is never consumed.
    const headers = {
      get: (name: string) => (name.toLowerCase() === 'etag' ? (etag ?? null) : null),
    };
    return {
      ok: status < 400,
      status,
      headers,
      json: async () => body,
    } as unknown as Response;
  };
  vi.stubGlobal('fetch', vi.fn(impl));
  return calls;
}

/** Stub `fetch` as a dead backend: every call fails at the network level. */
export function stubFetchDown(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      throw new TypeError('connect ECONNREFUSED 127.0.0.1:8000');
    }),
  );
}

// --- fixtures (synthetic, shape-faithful) --------------------------------

export const EXP_ID = '01SYNTHTESTEXP000000000000';

export const experimentSummary = {
  id: EXP_ID,
  title: 'Synthetic XANES — CuO (Cu K-edge) Demo',
  status: 'needs_attention',
  created_utc: '2099-04-02T09:00:00Z',
  pending_count: 5,
  evidenced_field_count: 26,
  exported: false,
  record_id: null,
};

export const exportedSummary = {
  id: '01SYNTHTESTDONE00000000000',
  title: 'Synthetic XANES — CuO baseline (exported)',
  status: 'done',
  created_utc: '2099-01-15T09:00:00Z',
  pending_count: 0,
  evidenced_field_count: 26,
  exported: true,
  record_id: '01SYNTHTESTRECORD000000000',
};

// P27.5 — the optimistic-concurrency version triplet the backend returns on
// record detail + every accepted mutation. `version` is the opaque If-Match
// token the client echoes back on the next mutation.
export const VERSION_FIELDS = {
  rev: 3,
  updated_utc: '2099-04-02T09:15:00Z',
  version: '1.0',
};

export const experimentDetail = {
  ...experimentSummary,
  ...VERSION_FIELDS,
  draft_ok: true,
  artifact_refs: { record_filename: null, sidecar_filename: null },
  source_files: ['mock_campaign.csv', 'raw_scan_listing.txt'],
  // needs_attention: load_record completed, complete_metadata current, rest blocked.
  workflow: fixtureWorkflow({
    pending_count: experimentSummary.pending_count,
    draft_ok: true,
    ready: false,
    exported: false,
    rev: VERSION_FIELDS.rev,
  }),
  // P28.2 — nothing exported yet, so there is no artifact to be fresh/stale.
  artifact: { state: 'none', reason: null } as const,
};

export const draftResponse = {
  groups: [
    {
      title: 'System & Instrument',
      fields: [
        {
          path: 'system.technique',
          label: 'Technique',
          value: 'HERFD-XAS',
          status: 'verified',
          evidence_count: 1,
          source_types: ['spreadsheet'],
        },
        {
          path: 'system.domain',
          label: 'Domain',
          value: 'experimental',
          status: 'inferred',
          evidence_count: 1,
          source_types: ['derivation'],
        },
      ],
    },
    {
      title: 'Sample',
      fields: [
        {
          path: 'sample.material.formula',
          label: 'Formula',
          value: 'CuO2',
          status: 'verified',
          evidence_count: 1,
          source_types: ['spreadsheet'],
        },
      ],
    },
  ],
};

export const pendingResponse = {
  pending: [
    {
      id: 'ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb',
      kind: 'asset',
      question: 'What is the sha256 of the processing notebook?',
      about: 'ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb',
      demo_answer: { value: 'c3b0c442…', label: 'Demo answer (synthetic)' },
    },
    {
      id: 'ssrl-archive://BL15-2/2099_run_000/raw/scan_0044.dat',
      kind: 'asset',
      question: 'What is the sha256 of the raw scan file?',
      about: 'ssrl-archive://BL15-2/2099_run_000/raw/scan_0044.dat',
      demo_answer: null,
    },
    {
      id: 'ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi',
      kind: 'asset',
      question: 'What is the sha256 of the merged spectrum file?',
      about: 'ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi',
      demo_answer: null,
    },
    {
      id: 'series',
      kind: 'series',
      question: 'Which reduced spectrum should this record point to?',
      about: 'reduced_spectrum',
      demo_answer: { value: 'CuO2_merged.xdi', label: 'Demo answer (synthetic)' },
    },
    {
      id: 'descriptor',
      kind: 'descriptor',
      question: 'What is the XANES inflection-point energy and its uncertainty?',
      about: 'required_for_evidence_record',
      demo_answer: null,
    },
  ],
};

export const validateDryRun = {
  ok: false,
  errors: [
    { path: '$.assets', message: 'assets is a required property' },
    { path: '$.measurement.series', message: 'series is a required property' },
  ],
  schema: 'ISAAC v1.05',
  dry_run: true,
};

// --- P36.3 standalone validator fixtures (POST /api/validate/record) --------
// Shapes verbatim from apps/api/isaac_api/routes.py `post_validate_record` —
// a DIFFERENT envelope from `validateDryRun` above (`summary` + `schema_version`
// instead of `schema` + `dry_run`), since it has no experiment/draft context.

export const validateRecordPass = {
  ok: true,
  summary: 'PASS — valid against official ISAAC schema v1.05',
  errors: [],
  schema_version: '1.05',
};

export const validateRecordFail = {
  ok: false,
  summary:
    "✗ system.technique — 'telepathy' is not one of ['XAS', 'XRD', 'HERFD-XAS']\nFAIL (1 schema errors)",
  errors: [
    { path: 'system.technique', message: "'telepathy' is not one of ['XAS', 'XRD', 'HERFD-XAS']" },
  ],
  schema_version: '1.05',
};

/** A minimal, unmistakably-synthetic candidate record for the standalone validator UI tests. */
export const syntheticCandidateRecord = {
  isaac_record_version: '1.05',
  record_id: '01SYNTHSTANDALONEVALID0001',
  record_type: 'evidence',
  system: { technique: 'XAS' },
};

export const auditNotExported = {
  records: [],
  text: 'No records found.',
  message: 'Nothing exported yet — export this experiment before auditing.',
};

export const warningsDryRun = {
  advisory: true,
  gating: false,
  warnings: [
    { code: 'NO_LINKS', where: 'record.links', message: 'no relationships declared' },
  ],
  dry_run: true,
};

export const evidenceResponse = {
  evidence: [
    {
      path: 'system.technique',
      value: 'HERFD-XAS',
      status: 'verified',
      evidence: [
        {
          source_type: 'spreadsheet',
          source_file: 'mock_campaign.csv',
          locator: "Sheet 'Campaign Info', field=technique",
          quote: 'HERFD-XAS',
        },
      ],
    },
    {
      path: 'system.domain',
      value: 'experimental',
      status: 'inferred',
      evidence: [
        {
          source_type: 'derivation',
          rule: 'system.domain = experimental for a facility-source record',
        },
      ],
    },
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
      path: 'implicit:absorbing_element',
      value: 'Cu',
      status: 'inferred',
      evidence: [
        {
          source_type: 'derivation',
          rule: 'absorbing element = sole non-oxygen element in sample.material.formula',
        },
      ],
    },
  ],
};

// --- GET /api/graph/status fixtures (P24.10 separated-freshness contract) ---
// The old single conflated `status` verdict is gone. The body now carries
// individually-honest axes: availability (primary), integrity, memory_policy,
// indexed_sources — plus provenance and additive counts. Shapes mirror
// apps/api/isaac_api/routes.py `graph_status()` 1:1.

const AVAILABLE_NOTE =
  'Project Memory provides leads and provenance, never a correctness ruling — ' +
  'confirm every lead against the cited files.';
const UNAVAILABLE_NOTE =
  'Project Memory is unavailable, so no leads can be served. It provides leads and ' +
  'provenance, never a correctness ruling — confirm against the cited files.';

/** Fully current: available, integrity verified, policy + indexed sources current. */
export const graphStatusAvailable = {
  plane: 'memory',
  availability: 'available',
  integrity: 'verified',
  provider: 'sanitized-snapshot',
  memory_policy: 'current',
  indexed_sources: 'current',
  policy_fingerprint: 'sha256:fakepolicyfingerprintp2410aaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  served_manifest_fingerprint: 'sha256:fakemanifestfingerprintp2410bbbbbbbbbbbbbbbbbbbbbbbb',
  served_file_count: 190,
  freshness_scope: 'served_files_only',
  freshness_basis: 'ci_content_manifest',
  source_graph_commit: 'ab12cd34ef567890',
  snapshot_schema_version: 1,
  deployed_app_commit: 'deadbee0cafe0001',
  note: AVAILABLE_NOTE,
  node_count: 2296,
  edge_count: 3447,
  community_count: 214,
  file_count: 190,
  concept_count: 19,
  graph_mtime: null,
};

/** The REAL pre-regen snapshot state: available, integrity verified, but policy
 * and indexed-sources currency cannot yet be proven (unknown), and the served
 * file count is not yet embedded (null). Real counts still render. */
export const graphStatusPreRegen = {
  plane: 'memory',
  availability: 'available',
  integrity: 'verified',
  provider: 'sanitized-snapshot',
  memory_policy: 'unknown',
  indexed_sources: 'unknown',
  policy_fingerprint: null,
  served_manifest_fingerprint: null,
  served_file_count: null,
  freshness_scope: 'served_files_only',
  freshness_basis: 'ci_content_manifest',
  source_graph_commit: '86c25c586b3f9c104b087ba1be3db5486347cb81',
  snapshot_schema_version: 1,
  deployed_app_commit: null,
  note: AVAILABLE_NOTE,
  node_count: 42,
  edge_count: 17,
  community_count: 5,
  file_count: 9,
  concept_count: 3,
  graph_mtime: null,
};

/** A shipped-but-malformed artifact: unavailable + integrity malformed. Quiet
 * degrade, never an error state; no counts. */
export const graphStatusMalformed = {
  plane: 'memory',
  availability: 'unavailable',
  integrity: 'malformed',
  provider: 'unavailable',
  memory_policy: 'unknown',
  indexed_sources: 'unknown',
  policy_fingerprint: null,
  served_manifest_fingerprint: null,
  served_file_count: null,
  freshness_scope: 'served_files_only',
  freshness_basis: 'ci_content_manifest',
  source_graph_commit: null,
  snapshot_schema_version: null,
  deployed_app_commit: 'deadbee0cafe0001',
  note: UNAVAILABLE_NOTE,
  node_count: null,
  edge_count: null,
  community_count: null,
  file_count: null,
  concept_count: null,
  graph_mtime: null,
};

/** No artifact present at all: unavailable + integrity unknown. */
export const graphStatusUnavailable = {
  plane: 'memory',
  availability: 'unavailable',
  integrity: 'unknown',
  provider: 'unavailable',
  memory_policy: 'unknown',
  indexed_sources: 'unknown',
  policy_fingerprint: null,
  served_manifest_fingerprint: null,
  served_file_count: null,
  freshness_scope: 'served_files_only',
  freshness_basis: 'ci_content_manifest',
  source_graph_commit: null,
  snapshot_schema_version: null,
  deployed_app_commit: 'deadbee0cafe0001',
  note: UNAVAILABLE_NOTE,
  node_count: null,
  edge_count: null,
  community_count: null,
  file_count: null,
  concept_count: null,
  graph_mtime: null,
};

// --- P24.4 Source Index fixtures (memory plane; synthetic, shape-faithful
// to apps/api/isaac_api/routes.py "16. memory" / memory.py) --------------

const MEMORY_NOTE = 'Project memory returns leads to verify — never a validation verdict.';

/** GET /api/memory/files — available, 4 served rows across code/document/null groups. */
export const memoryFilesAvailable = {
  plane: 'memory' as const,
  note: MEMORY_NOTE,
  available: true,
  files: [
    {
      path: 'src/fake_mod.py',
      file_type: 'code',
      community_id: '131',
      community_name: 'Export Pipeline',
      node_count: 42,
      on_disk: true,
    },
    {
      path: 'src/other_mod.py',
      file_type: 'code',
      community_id: '55',
      community_name: null,
      node_count: 3,
      on_disk: true,
    },
    {
      path: 'docs/fake-note.md',
      file_type: 'document',
      community_id: null,
      community_name: null,
      node_count: 1,
      on_disk: false,
    },
    {
      path: '.github/workflows/fake-ci.yml',
      file_type: null,
      community_id: null,
      community_name: null,
      node_count: 0,
      on_disk: true,
    },
  ],
};

/** GET /api/memory/files — degraded (graph absent). */
export const memoryFilesUnavailable = {
  plane: 'memory' as const,
  note: MEMORY_NOTE,
  available: false,
  reason: 'graph_absent' as const,
  files: [],
};

/** GET /api/memory/file?path=src/fake_mod.py — real leads (rationale + related files/concepts). */
export const memoryFileDetailWithLeads = {
  plane: 'memory' as const,
  note: MEMORY_NOTE,
  available: true,
  file: {
    path: 'src/fake_mod.py',
    file_type: 'code',
    community_id: '131',
    community_name: 'Export Pipeline',
    node_count: 42,
    on_disk: true,
    local_reference: 'src/fake_mod.py',
  },
  related: {
    files: [{ path: 'src/other_mod.py', relation: 'imports', file_type: 'code' }],
    concepts: [{ id: 'concept-provenance', label: 'Provenance', relation: 'relates_to' }],
  },
  rationales: ['Deterministic, doubly-gated export transform.'],
};

/** GET /api/memory/file?path=docs/fake-note.md — on_disk:false, no leads. */
export const memoryFileDetailEmptyLeads = {
  plane: 'memory' as const,
  note: MEMORY_NOTE,
  available: true,
  file: {
    path: 'docs/fake-note.md',
    file_type: 'document',
    community_id: null,
    community_name: null,
    node_count: 1,
    on_disk: false,
    local_reference: 'docs/fake-note.md',
  },
  related: { files: [], concepts: [] },
  rationales: [],
};

// --- P24.5 Concept Lookup fixtures (memory plane; synthetic, shape-faithful
// to apps/api/isaac_api/routes.py "16. memory" / memory.py) --------------

/** GET /api/memory/concepts — available, 3 concepts (name / id-fallback / no-community). */
export const memoryConceptsAvailable = {
  plane: 'memory' as const,
  note: MEMORY_NOTE,
  available: true,
  concepts: [
    {
      id: 'concept-provenance',
      label: 'Provenance',
      community_id: '131',
      community_name: 'Export Pipeline',
      source_file: 'src/fake_mod.py',
      on_disk: true,
    },
    {
      id: 'concept-governance',
      label: 'Governance allowlist',
      community_id: '55',
      community_name: null,
      source_file: 'docs/fake-note.md',
      on_disk: false,
    },
    {
      id: 'concept-two-layer',
      label: 'Two-layer architecture',
      community_id: null,
      community_name: null,
      source_file: 'README.md',
      on_disk: true,
    },
  ],
};

/** GET /api/memory/concepts — degraded (graph absent). */
export const memoryConceptsUnavailable = {
  plane: 'memory' as const,
  note: MEMORY_NOTE,
  available: false,
  reason: 'graph_absent' as const,
  concepts: [],
};

/** GET /api/memory/concepts/concept-provenance — real leads (related file + related concept). */
export const memoryConceptDetailWithLeads = {
  plane: 'memory' as const,
  note: MEMORY_NOTE,
  available: true,
  concept: {
    id: 'concept-provenance',
    label: 'Provenance',
    community_id: '131',
    community_name: 'Export Pipeline',
    source_file: 'src/fake_mod.py',
    on_disk: true,
  },
  related: {
    files: [{ path: 'src/other_mod.py', relation: 'imports', file_type: 'code' }],
    concepts: [
      { id: 'concept-governance', label: 'Governance allowlist', relation: 'relates_to' },
    ],
  },
};

/** GET /api/memory/concepts/concept-governance — on_disk:false, no leads (matches real-graph reality). */
export const memoryConceptDetailEmptyLeads = {
  plane: 'memory' as const,
  note: MEMORY_NOTE,
  available: true,
  concept: {
    id: 'concept-governance',
    label: 'Governance allowlist',
    community_id: '55',
    community_name: null,
    source_file: 'docs/fake-note.md',
    on_disk: false,
  },
  related: { files: [], concepts: [] },
};

/** GET /api/memory/concepts/concept-governance — P24.9: the graph anchor points
 * at a governance-excluded source, so `source_file` is null (withheld). The
 * concept is still surfaced; the UI must render an honest note, not an empty
 * mono span. */
export const memoryConceptDetailWithheldAnchor = {
  plane: 'memory' as const,
  note: MEMORY_NOTE,
  available: true,
  concept: {
    id: 'concept-governance',
    label: 'Governance allowlist',
    community_id: '55',
    community_name: null,
    source_file: null,
    on_disk: false,
  },
  related: { files: [], concepts: [] },
};

// --- P36.2 Graph tab fixtures (memory plane; synthetic, shape-faithful to
// apps/api/isaac_api/memory_graph.py `build_graph_projection`) -------------
// Deliberately reuses the SAME synthetic paths/concepts as the Source Index /
// Concept Lookup fixtures above (src/fake_mod.py, docs/fake-note.md,
// concept-provenance, concept-governance) so a cross-tab deep-link test can
// select a node here and land on the SAME row in Sources/Concepts.

const MEMORY_GRAPH_NOTE =
  'Project memory returns leads to verify — never a validation verdict. ' +
  'This is a served-file reference graph, not the full (un-embedded) source graph.';

/** GET /api/memory/graph — available: 3 files, 2 concepts, 1 real edge
 * (relation "imports"), 2 communities, honest un-embedded-source disclosure. */
export const memoryGraphAvailable = {
  plane: 'memory' as const,
  note: MEMORY_GRAPH_NOTE,
  available: true,
  truncated: false,
  nodes: [
    {
      id: 'src/fake_mod.py',
      kind: 'file' as const,
      label: 'src/fake_mod.py',
      file_type: 'code',
      community_id: '131',
      community_name: 'Export Pipeline',
      node_count: 42,
      on_disk: true,
    },
    {
      id: 'src/other_mod.py',
      kind: 'file' as const,
      label: 'src/other_mod.py',
      file_type: 'code',
      community_id: '55',
      community_name: null,
      node_count: 3,
      on_disk: true,
    },
    {
      id: 'docs/fake-note.md',
      kind: 'file' as const,
      label: 'docs/fake-note.md',
      file_type: 'document',
      community_id: null,
      community_name: null,
      node_count: 1,
      on_disk: false,
    },
    {
      id: 'concept-provenance',
      kind: 'concept' as const,
      label: 'Provenance',
      community_id: '131',
      community_name: 'Export Pipeline',
      on_disk: true,
      source_file: 'src/fake_mod.py',
    },
    {
      id: 'concept-governance',
      kind: 'concept' as const,
      label: 'Governance allowlist',
      community_id: '55',
      community_name: null,
      on_disk: false,
      source_file: 'docs/fake-note.md',
    },
  ],
  edges: [
    { source: 'src/fake_mod.py', target: 'src/other_mod.py', relations: ['imports'] },
  ],
  communities: [
    { id: '131', name: 'Export Pipeline', file_count: 1 },
    { id: '55', name: null, file_count: 1 },
  ],
  meta: {
    counts: {
      files: 3,
      concepts: 2,
      reference_edges: 1,
      files_with_references: 2,
      isolated_files: 1,
      communities_rendered: 2,
    },
    underlying_graph: {
      embedded: false as const,
      node_count: 2988,
      edge_count: 4465,
      community_count: 257,
      note: 'full source graph not embedded; this is the served-content reference projection',
    },
    provenance: {
      built_at_commit: 'caab1d0a69c1733524bda5dde495623bc4b7bad1',
      source_graph_sha256: '0cfccb9f77893363ecfb467e129014d751bf16a76b2b37be990af9f263f4b432',
      snapshot_schema_version: 1,
      provider: 'sanitized-snapshot',
      integrity: 'verified' as const,
    },
  },
};

/** GET /api/memory/graph — degraded (graph absent): zero fabricated nodes. */
export const memoryGraphUnavailable = {
  plane: 'memory' as const,
  note: MEMORY_GRAPH_NOTE,
  available: false,
  reason: 'graph_absent' as const,
  truncated: false,
  nodes: [],
  edges: [],
  communities: [],
  meta: {
    counts: {
      files: 0,
      concepts: 0,
      reference_edges: 0,
      files_with_references: 0,
      isolated_files: 0,
      communities_rendered: 0,
    },
    underlying_graph: {
      embedded: false as const,
      node_count: null,
      edge_count: null,
      community_count: null,
      note: 'full source graph not embedded; this is the served-content reference projection',
    },
    provenance: {
      built_at_commit: null,
      source_graph_sha256: null,
      snapshot_schema_version: null,
      provider: 'unavailable',
      integrity: 'unknown' as const,
    },
  },
};

/** Artifacts before export: all null (200, not an error). */
export const artifactsNull = {
  record: null,
  sidecar: null,
  record_filename: null,
  sidecar_filename: null,
};

export const demoRunDraftOnly = {
  experiment_id: EXP_ID,
  steps: [
    {
      name: 'build_draft',
      detail: '26 evidenced fields, 5 pending blocker(s)',
      ok: true,
    },
    { name: 'validate_draft', detail: 'draft ok: true', ok: true },
  ],
  status: 'needs_attention',
};

export const uploadsBlocked = {
  blocked: true,
  // Verbatim from `_UPLOAD_BLOCKED` in `apps/api/isaac_api/routes.py` (Slice 2A).
  reason: 'Real or private data upload is approval-gated and not enabled in this workspace.',
};

// --- P26.0b guarded synthetic-demo reset fixtures ------------------------
// Shapes verbatim from DemoResetResponse (apps/api/isaac_api/routes.py); the
// five canonical scenarios use the fixed ids from workspace.py (SEED_*).

/** GET /api/health — authoritative synthetic-mode signal the Reset control gates on. */
export const healthSynthetic = {
  status: 'ok',
  mode: 'synthetic-only',
  core: 'isaac_records',
  version: '0.1.0',
};

/** A non-synthetic health body — the Reset control must NOT render for this. */
export const healthNonSynthetic = { ...healthSynthetic, mode: 'production' };

export const CANONICAL_RESET_IDS = [
  '01SYNTHXANESSEED0000000001',
  '01SYNTHXANESSEED0000000002',
  '01SYNTHXANESSEED0000000003',
  '01SYNTHXANESSEED0000000004',
  '01SYNTHXANESSEED0000000005',
];

const RESET_TITLE_BASE = 'Synthetic XANES — CuO (Cu K-edge)';

/** The five derived scenario labels the API serves for the canonical seed ids
 * (mirrors `workspace.SEED_SCENARIOS`; derived server-side, never stored). Each
 * names how that fixture was MATERIALISED at setup, in the past tense, so a later
 * mutation cannot falsify it. */
export const CANONICAL_SCENARIO_LABELS = [
  'Scenario 1 · seeded: extraction only',
  'Scenario 2 · seeded: partial answers applied',
  'Scenario 3 · seeded: all answers applied',
  'Scenario 4 · seeded: descriptor uncertainty omitted',
  'Scenario 5 · seeded: export run at setup',
];

/** The five canonical scenarios as a summary list (post-reset dashboard).
 * Distribution: needs_attention:2, ready_to_export:1, in_review:1, done:1. */
export const canonicalFiveSummaries = [
  { id: CANONICAL_RESET_IDS[0], title: `${RESET_TITLE_BASE} · New Draft`, scenario: CANONICAL_SCENARIO_LABELS[0], status: 'needs_attention', created_utc: '2026-07-12T00:00:01Z', pending_count: 5, evidenced_field_count: 26, exported: false, record_id: null },
  { id: CANONICAL_RESET_IDS[1], title: `${RESET_TITLE_BASE} · Partially Completed`, scenario: CANONICAL_SCENARIO_LABELS[1], status: 'needs_attention', created_utc: '2026-07-12T00:00:02Z', pending_count: 2, evidenced_field_count: 30, exported: false, record_id: null },
  { id: CANONICAL_RESET_IDS[2], title: `${RESET_TITLE_BASE} · Ready to Export`, scenario: CANONICAL_SCENARIO_LABELS[2], status: 'ready_to_export', created_utc: '2026-07-12T00:00:03Z', pending_count: 0, evidenced_field_count: 33, exported: false, record_id: null },
  { id: CANONICAL_RESET_IDS[3], title: `${RESET_TITLE_BASE} · Export Review Required`, scenario: CANONICAL_SCENARIO_LABELS[3], status: 'in_review', created_utc: '2026-07-12T00:00:04Z', pending_count: 0, evidenced_field_count: 33, exported: false, record_id: null },
  { id: CANONICAL_RESET_IDS[4], title: `${RESET_TITLE_BASE} · Exported Record`, scenario: CANONICAL_SCENARIO_LABELS[4], status: 'done', created_utc: '2026-07-12T00:00:05Z', pending_count: 0, evidenced_field_count: 33, exported: true, record_id: CANONICAL_RESET_IDS[4] },
];

/** Two managed-legacy demo records (random ids + the committed demo marker). */
const LEGACY_REMOVABLE = [
  { id: '01SYNTHLEGACYDEMORUN0000001', title: `${RESET_TITLE_BASE} Demo (demo/run)` },
  { id: '01SYNTHLEGACYDEMORUN0000002', title: `${RESET_TITLE_BASE} Demo (demo/run)` },
];

const RESET_STATE_COUNTS = { needs_attention: 2, ready_to_export: 1, in_review: 1, done: 1 };

/** POST /api/demo/reset {mode:'preview'} — 5 canonical + 2 legacy present, 0 ambiguous. */
export const demoResetPreviewClean = {
  status: 'ok' as const,
  mode: 'preview' as const,
  previous_count: 7,
  canonical_count: 5,
  legacy_count: 2,
  ambiguous_count: 0,
  removed_count: 0,
  final_count: 5,
  canonical_ids: CANONICAL_RESET_IDS,
  removable: LEGACY_REMOVABLE,
  state_counts: RESET_STATE_COUNTS,
};

/** POST /api/demo/reset {mode:'execute', confirmation:'RESET SYNTHETIC DEMO'} — success. */
export const demoResetExecuteOk = {
  ...demoResetPreviewClean,
  mode: 'execute' as const,
  previous_count: 7,
  removed_count: 2,
  final_count: 5,
};

/** Preview when an ambiguous (unmanaged) record is present — refused (HTTP 200). */
export const demoResetPreviewAmbiguous = {
  status: 'refused' as const,
  mode: 'preview' as const,
  previous_count: 8,
  canonical_count: 5,
  legacy_count: 2,
  ambiguous_count: 1,
  removed_count: 0,
  final_count: 8,
  canonical_ids: CANONICAL_RESET_IDS,
  removable: LEGACY_REMOVABLE,
  state_counts: RESET_STATE_COUNTS,
};

/**
 * Route map for the My Experiments page with the Reset Demo control wired.
 * `experiments` defaults to a thunk that returns 7 rows (5 canonical + 2 legacy)
 * until `flipToFive()` is called, then the canonical five — so a test can prove
 * the list is re-fetched from the backend after a successful reset.
 */
export function resetDemoRoutes(
  opts: {
    mode?: string;
    preview?: unknown;
    execute?: unknown;
    executeStatus?: number;
  } = {},
): { routes: Record<string, StubbedRoute>; flipToFive: () => void } {
  const legacySummaries = LEGACY_REMOVABLE.map((r, i) => ({
    id: r.id,
    title: r.title,
    status: 'needs_attention',
    created_utc: `2025-01-0${i + 1}T00:00:00Z`,
    pending_count: 5,
    evidenced_field_count: 26,
    exported: false,
    record_id: null,
  }));
  let five = false;
  const flipToFive = () => {
    five = true;
  };
  // The dialog issues the preview POST on open, then the execute POST on submit —
  // same METHOD+path, so the body is served by call order: 1st = preview, 2nd+ =
  // execute (which also flips the list to the canonical five, mirroring the real
  // backend so a subsequent GET /experiments reflects the reset).
  const previewBody = opts.preview ?? demoResetPreviewClean;
  const executeBody = opts.execute ?? demoResetExecuteOk;
  let postCalls = 0;
  const routes: Record<string, StubbedRoute> = {
    'GET /api/health': { body: { ...healthSynthetic, mode: opts.mode ?? 'synthetic-only' } },
    'GET /api/experiments': {
      body: () => ({
        experiments: five ? canonicalFiveSummaries : [...canonicalFiveSummaries, ...legacySummaries],
      }),
    },
    'POST /api/demo/reset': {
      status: opts.executeStatus,
      body: () => {
        postCalls += 1;
        if (postCalls === 1) return previewBody;
        five = true;
        return executeBody;
      },
    },
  };
  return { routes, flipToFive };
}

/** The full route map for one S3 record bundle (plus S1's list) for `id`. */
export function bundleRoutes(id: string = EXP_ID): Record<string, StubbedRoute> {
  const base = `/api/experiments/${encodeURIComponent(id)}`;
  return {
    'GET /api/experiments': { body: { experiments: [experimentSummary] } },
    [`GET ${base}`]: { body: { ...experimentDetail, id } },
    [`GET ${base}/draft`]: { body: draftResponse },
    [`GET ${base}/pending`]: { body: pendingResponse },
    [`POST ${base}/validate`]: { body: validateDryRun },
    [`POST ${base}/audit`]: { body: auditNotExported },
    [`GET ${base}/warnings`]: { body: warningsDryRun },
    [`GET ${base}/evidence`]: { body: evidenceResponse },
    // P29.4 — the AgentContext evidence-support input the shared record-session
    // owner fetches on every record screen (not just S5).
    [`GET ${base}/evidence-classification`]: { body: evidenceClassificationResponse },
    [`GET ${base}/artifacts`]: { body: artifactsNull },
    'GET /api/graph/status': { body: graphStatusUnavailable },
  };
}

// --- S4/S6 completion + export fixtures ----------------------------------

const SYNTH_SHA = 'c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345';

/** POST /answers response after confirming the processing-notebook sha256. The
 *  version triplet advances (rev 3 → 4, new token) — the client adopts it as the
 *  If-Match token for the next submit. */
export const answersAfterNotebook = {
  pending: pendingResponse.pending.slice(1),
  status: 'needs_attention',
  rev: 4,
  updated_utc: '2099-04-02T09:16:00Z',
  version: '1.1',
};

/** POST /edit response after correcting the processing-notebook sha256 (P28.3).
 *  Same bundle shape as /answers (pending/status/version/workflow/invalidation);
 *  the version advances (the client adopts it) and the invalidation reports a real
 *  change with no downstream reopen. */
export const editApplied = {
  pending: [],
  status: 'ready_to_export',
  rev: 4,
  updated_utc: '2099-04-02T09:18:00Z',
  version: '1.1',
  workflow: fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: false, rev: 4 }),
  invalidation: {
    changed: true,
    rev: 4,
    changed_fields: ['ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb'],
    reopened_steps: [],
    artifact: { state: 'none', reason: null },
    reason: 'Updated 1 field(s); no downstream steps reopened.',
  },
};

/** POST /edit 412 stale_write payload (verbatim backend contract shape). */
export const editStaleWrite = {
  error: 'stale_write',
  experiment_id: EXP_ID,
  expected_rev: 3,
  current_rev: 7,
  expected_version: '1.0',
  current_version: '2.0',
};

/** POST /answers 412 stale_write payload (verbatim backend contract shape). */
export const answersStaleWrite = {
  error: 'stale_write',
  experiment_id: EXP_ID,
  expected_rev: 3,
  current_rev: 7,
  expected_version: '1.0',
  current_version: '2.0',
};

/** Structured demo answer for the series blocker (shape-faithful, synthetic). */
export const seriesDemoValue = [
  {
    series_id: 'averaged_spectrum',
    independent_variables: [{ name: 'incident_energy', unit: 'eV', values: [8970, 9000] }],
    channels: [
      { name: 'absorption', unit: 'mu_normalized', role: 'primary_signal', values: [0.02, 1.05] },
    ],
  },
];

/** Dry-run validation that WOULD pass (0 pending, pre-export). */
export const validateReadyDryRun = {
  ok: true,
  errors: [],
  schema: 'ISAAC v1.05',
  dry_run: true,
};

/** Real (post-export) validation of the written record. */
export const validateExported = {
  ok: true,
  errors: [],
  schema: 'ISAAC v1.05',
  dry_run: false,
};

export const auditExported = {
  records: [
    {
      name: `${EXP_ID}.json`,
      ok: true,
      schema_errors: [],
      evidence_present: 33,
      evidence_expected: 33,
      uncovered: [],
      dangling: [],
    },
  ],
  text: `${EXP_ID}.json: schema OK, evidence 33/33`,
};

export const exportSuccess = {
  ok: true,
  draft_report: { ok: true, errors: [], warnings: [] },
  official_report: { ok: true, errors: [] },
  record: { record_id: EXP_ID, schema_version: '1.05', assets: [{ sha256: SYNTH_SHA }] },
  sidecar: { record_id: EXP_ID, schema_version: '1.05', evidence: {} },
  record_id: EXP_ID,
  // P30.6 — safe basenames only, never an absolute server/mount path.
  artifact_refs: {
    record_filename: `${EXP_ID}.json`,
    sidecar_filename: `${EXP_ID}.evidence.json`,
  },
  // P27.5 — the post-export version triplet the client adopts.
  rev: 4,
  updated_utc: '2099-04-02T09:20:00Z',
  version: '2.0',
};

/** POST /export 412 stale_write payload (verbatim backend contract shape). */
export const exportStaleWrite = {
  error: 'stale_write',
  experiment_id: EXP_ID,
  expected_rev: 3,
  current_rev: 7,
  expected_version: '1.0',
  current_version: '2.0',
};

export const exportConflict = {
  error: 'record_exists',
  message: `${EXP_ID}.json already exists; records are immutable.`,
  record_id: EXP_ID,
};

/** S6 routes: all blockers resolved, dry-run would pass, nothing exported yet. */
export function exportReadyRoutes(id: string = EXP_ID): Record<string, StubbedRoute> {
  const base = `/api/experiments/${encodeURIComponent(id)}`;
  return {
    [`GET ${base}`]: {
      body: {
        ...experimentDetail,
        id,
        status: 'ready_to_export',
        pending_count: 0,
        workflow: fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: false, rev: VERSION_FIELDS.rev }),
      },
    },
    [`GET ${base}/pending`]: { body: { pending: [] } },
    [`POST ${base}/validate`]: { body: validateReadyDryRun },
    [`POST ${base}/audit`]: { body: auditNotExported },
    [`GET ${base}/warnings`]: { body: warningsDryRun },
    // P29.4 — the shared record-session owner's AgentContext evidence input.
    [`GET ${base}/evidence-classification`]: { body: evidenceClassificationResponse },
    [`GET ${base}/artifacts`]: { body: artifactsNull },
    'GET /api/graph/status': { body: graphStatusUnavailable },
  };
}

// --- S5 evidence explorer fixtures (post-export) -------------------------

const NOTEBOOK_SHA = 'c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345';

/** Live /evidence for an exported experiment: dotted CSV field + asset + implicit. */
export const evidenceExported = {
  evidence: [
    {
      path: 'system.technique',
      value: 'HERFD-XAS',
      status: 'verified',
      evidence: [
        {
          source_type: 'spreadsheet',
          source_file: 'mock_campaign.csv',
          locator: "Sheet 'Campaign Info', field=technique",
          quote: 'HERFD-XAS',
        },
      ],
    },
    {
      path: 'assets:processing_notebook',
      value: NOTEBOOK_SHA,
      status: 'verified',
      evidence: [
        {
          source_type: 'file_listing',
          source_file: 'raw_scan_listing.txt',
          locator: 'line 16, ssrl-archive://BL15-2/2099_run_000/notebooks/',
          quote: 'xanes_reduction_v2.ipynb',
        },
        {
          source_type: 'user_confirmation',
          question:
            'What is the sha256 of ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb?',
          answer: NOTEBOOK_SHA,
          timestamp: '2099-03-05T21:00:00Z',
        },
      ],
    },
    {
      path: 'implicit:absorbing_element',
      value: 'Cu',
      status: 'inferred',
      evidence: [
        {
          source_type: 'derivation',
          rule: 'absorbing element = sole non-oxygen element in sample.material.formula',
        },
      ],
    },
  ],
};

// P28.5 — the evidence-support classification for the S5 record. `record_rev`
// matches the rev encoded in `experimentDetail.version` ('1.0' → last segment 0),
// so the default view is coherent (never falsely "stale"). One field per class so
// all five render and `counts` sums to field_results.length.
export const evidenceClassificationResponse = {
  record_rev: Number(VERSION_FIELDS.version.split('.').pop()),
  field_results: [
    {
      field: 'system.technique',
      classification: 'supported' as const,
      value_state: 'confirmed' as const,
      explanation: 'Backed by observed evidence.',
      sources: [
        { source_type: 'spreadsheet' as const, locator: "Sheet 'Campaign Info', field=technique" },
      ],
    },
    {
      field: 'implicit:edge',
      classification: 'inferred_candidate' as const,
      value_state: 'candidate' as const,
      explanation: 'Proposed by a derivation rule; unconfirmed — not entered as fact.',
      sources: [{ source_type: 'derivation' as const }],
    },
    {
      field: 'measurement.reduced_spectrum',
      classification: 'insufficient_evidence' as const,
      value_state: 'none' as const,
      explanation: 'Evidence present but the value is not established.',
      sources: [{ source_type: 'user_confirmation' as const }],
    },
    {
      field: 'sample.material.formula',
      classification: 'conflicting_evidence' as const,
      value_state: 'candidate' as const,
      explanation: 'Evidence asserts incompatible values; needs human resolution.',
      sources: [
        { source_type: 'user_confirmation' as const },
        { source_type: 'spreadsheet' as const, locator: "Sheet 'Sample', field=formula" },
      ],
    },
    {
      field: 'sample.notes',
      classification: 'unknown' as const,
      value_state: 'none' as const,
      explanation: 'No defensible value.',
      sources: [],
    },
  ],
  counts: {
    supported: 1,
    inferred_candidate: 1,
    insufficient_evidence: 1,
    conflicting_evidence: 1,
    unknown: 1,
  },
};

export const artifactsExported = {
  record: {
    record_id: EXP_ID,
    schema_version: '1.05',
    system: { technique: 'HERFD-XAS' },
    assets: [{ asset_id: 'processing_notebook', sha256: NOTEBOOK_SHA }],
  },
  sidecar: {
    record_id: EXP_ID,
    schema_version: '1.05',
    generated_utc: '2099-03-05T21:05:48Z',
    evidence: { 'system.technique': [{ source_type: 'spreadsheet' }] },
  },
  // P30.6 — safe basenames only, never an absolute server/mount path.
  record_filename: `${EXP_ID}.json`,
  sidecar_filename: `${EXP_ID}.evidence.json`,
};

export const sourcePreviewListing = {
  name: 'raw_scan_listing.txt',
  media_type: 'text/plain',
  lines: [
    { n: 14, text: '2099-03-15 09:20 1.1M raw/scan_0045.dat' },
    { n: 15, text: '2099-03-15 09:21 240K notebooks/' },
    { n: 16, text: '2099-03-15 09:22  88K notebooks/xanes_reduction_v2.ipynb' },
    { n: 17, text: '2099-03-15 09:40 240K reduced/CuO2_merged.xdi' },
    { n: 18, text: '2099-03-15 09:41 4.0K raw/ (directory)' },
  ],
  cited_lines: [16, 18],
};

export const sourcePreviewCsv = {
  name: 'mock_campaign.csv',
  media_type: 'text/csv',
  lines: [
    { n: 1, text: 'section,field,value' },
    { n: 2, text: 'Campaign Info,technique,HERFD-XAS' },
  ],
  cited_lines: [],
};

/** S5 routes for an exported experiment (evidence + artifacts + both source previews). */
export function evidenceBundleRoutes(id: string = EXP_ID): Record<string, StubbedRoute> {
  const base = `/api/experiments/${encodeURIComponent(id)}`;
  return {
    [`GET ${base}`]: {
      body: {
        ...experimentDetail,
        id,
        status: 'done',
        pending_count: 0,
        exported: true,
        record_id: id,
        artifact_refs: {
          record_filename: artifactsExported.record_filename,
          sidecar_filename: artifactsExported.sidecar_filename,
        },
        workflow: fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: true, rev: VERSION_FIELDS.rev }),
        artifact: { state: 'current', reason: null },
      },
    },
    [`GET ${base}/evidence`]: { body: evidenceExported },
    [`GET ${base}/evidence-classification`]: { body: evidenceClassificationResponse },
    // P29.4 — the shared record-session owner's AgentContext pending input.
    [`GET ${base}/pending`]: { body: { pending: [] } },
    [`GET ${base}/artifacts`]: { body: { ...artifactsExported, record: { ...artifactsExported.record, record_id: id }, sidecar: { ...artifactsExported.sidecar, record_id: id } } },
    [`GET ${base}/source-preview?source=mock_campaign.csv`]: { body: sourcePreviewCsv },
    [`GET ${base}/source-preview?source=raw_scan_listing.txt`]: { body: sourcePreviewListing },
    'GET /api/graph/status': { body: graphStatusUnavailable },
  };
}

// --- P26.4 grouped search fixtures (reused by the P26.5 SearchDialog slice) ---
// Shapes verbatim from the P26.3 backend envelope (GET /api/search): two
// independently-honest groups, `workspace` (truth plane) and `memory`
// (advisory leads) — neither group's availability affects the other.

/** GET /api/search?q=xanes — one workspace hit + one memory hit, both available. */
export const searchResponse = {
  query: 'xanes',
  normalized_query: 'xanes',
  scope: 'all' as const,
  workspace: {
    plane: 'truth' as const,
    provider: 'workspace-store',
    available: true,
    reason: null,
    total: 1,
    returned: 1,
    limit: 10,
    offset: 0,
    results: [
      {
        kind: 'experiment' as const,
        experiment_id: EXP_ID,
        record_id: null,
        title: experimentSummary.title,
        label: experimentSummary.title,
        status: 'needs_attention',
        match: {
          field: 'title',
          snippet: experimentSummary.title,
          reason: 'matched experiment title',
          tier: 'substring' as const,
          offsets: [[10, 15]] as [number, number][],
        },
        navigate_to: `/record/${EXP_ID}`,
        plane: 'truth' as const,
        source: 'workspace-store',
      },
    ],
  },
  memory: {
    plane: 'memory' as const,
    provider: 'memory:sanitized-snapshot',
    note: MEMORY_NOTE,
    available: true,
    reason: null,
    total: 1,
    returned: 1,
    limit: 10,
    offset: 0,
    results: [
      {
        kind: 'concept' as const,
        id: 'concept-provenance',
        path: null,
        label: 'Provenance',
        community_name: 'Export Pipeline',
        match: {
          field: 'concept.label',
          snippet: 'Provenance',
          reason: 'matched concept label',
          tier: 'token' as const,
          offsets: [[0, 10]] as [number, number][],
        },
        navigate_to: '/memory?concept=concept-provenance',
        plane: 'memory' as const,
        source: 'memory:sanitized-snapshot',
      },
    ],
  },
};

/** Same query, but the memory graph is absent — workspace stays available (P26.5). */
export const searchResponseMemoryDown = {
  ...searchResponse,
  memory: {
    ...searchResponse.memory,
    available: false,
    reason: 'graph_absent' as const,
    total: 0,
    returned: 0,
    results: [],
  },
};

/**
 * Route map for `GET /api/search` keyed exactly like `api.search` builds its
 * query string (q, then scope, then limit, then offset — only when given).
 * Defaults to the `q=xanes` case with the fully-available envelope; pass
 * `query`/`scope`/`limit`/`offset` to match a different call, and `body` to
 * serve a different envelope (e.g. `searchResponseMemoryDown`).
 */
export function searchRoutes(
  opts: {
    query?: string;
    scope?: 'all' | 'workspace' | 'memory';
    limit?: number;
    offset?: number;
    body?: unknown;
  } = {},
): Record<string, StubbedRoute> {
  const query = opts.query ?? 'xanes';
  let key = `GET /api/search?q=${encodeURIComponent(query)}`;
  if (opts.scope !== undefined) key += `&scope=${encodeURIComponent(opts.scope)}`;
  if (opts.limit !== undefined) key += `&limit=${opts.limit}`;
  if (opts.offset !== undefined) key += `&offset=${opts.offset}`;
  return { [key]: { body: opts.body ?? searchResponse } };
}

// --- P30.3 cross-record runtime-record projection fixtures ------------------
// Shapes verbatim from apps/api/isaac_api/runtime_records.py `_project_one` (the
// SAFE allow-set: confirmed facts + freshness only). Values are unmistakably
// synthetic. Consumed by the deterministic crossRecordTriage + the SearchDialog
// triage surface. These are LEADS (Workspace-derived), never record truth.

const TRIAGE_IDS = [
  '01SYNTHTRIAGE00000000000001',
  '01SYNTHTRIAGE00000000000002',
  '01SYNTHTRIAGE00000000000003',
  '01SYNTHTRIAGE00000000000004',
];

/** Four projected records spanning the triage states (needs-attention+blocked,
 * ready-to-export, in-review-with-conflict, exported/done). */
export const runtimeRecords = [
  {
    experiment_id: TRIAGE_IDS[0],
    title: 'Synthetic XANES — Needs Attention',
    status: 'needs_attention',
    pending_count: 5,
    exported: false,
    record_id: null,
    workflow: { current_step: 'complete_metadata', blocked: true, reopened: false },
    evidence_counts: { supported: 3, inferred_candidate: 1, insufficient_evidence: 0, conflicting_evidence: 0, unknown: 2 },
    artifact_state: 'none',
    record_rev: 4,
    updated_utc: '2099-07-01T00:00:00Z',
    navigate_to: `/record/${TRIAGE_IDS[0]}`,
  },
  {
    experiment_id: TRIAGE_IDS[1],
    title: 'Synthetic XANES — Ready to Export',
    status: 'ready_to_export',
    pending_count: 0,
    exported: false,
    record_id: null,
    workflow: { current_step: 'export', blocked: false, reopened: false },
    evidence_counts: { supported: 9, inferred_candidate: 0, insufficient_evidence: 0, conflicting_evidence: 0, unknown: 0 },
    artifact_state: 'none',
    record_rev: 7,
    updated_utc: '2099-07-02T00:00:00Z',
    navigate_to: `/record/${TRIAGE_IDS[1]}`,
  },
  {
    experiment_id: TRIAGE_IDS[2],
    title: 'Synthetic XANES — Conflicting Evidence',
    status: 'in_review',
    pending_count: 0,
    exported: false,
    record_id: null,
    workflow: { current_step: 'review_export_readiness', blocked: false, reopened: true },
    evidence_counts: { supported: 5, inferred_candidate: 0, insufficient_evidence: 1, conflicting_evidence: 2, unknown: 0 },
    artifact_state: 'none',
    record_rev: 11,
    updated_utc: '2099-07-03T00:00:00Z',
    navigate_to: `/record/${TRIAGE_IDS[2]}`,
  },
  {
    experiment_id: TRIAGE_IDS[3],
    title: 'Synthetic XANES — Exported Record',
    status: 'done',
    pending_count: 0,
    exported: true,
    record_id: TRIAGE_IDS[3],
    workflow: { current_step: null, blocked: false, reopened: false },
    evidence_counts: { supported: 9, inferred_candidate: 0, insufficient_evidence: 0, conflicting_evidence: 0, unknown: 0 },
    artifact_state: 'stale',
    record_rev: 13,
    updated_utc: '2099-07-04T00:00:00Z',
    navigate_to: `/record/${TRIAGE_IDS[3]}`,
  },
];

/**
 * Route map for GET /api/runtime/records keyed exactly as `api.getRuntimeRecords`
 * builds each chip's query string. Each body is pre-filtered to mirror the real
 * backend's server-side filter (so the fixture is faithful, not a merged blob).
 */
export function runtimeRecordsRoutes(): Record<string, StubbedRoute> {
  const body = (rows: typeof runtimeRecords) => ({ records: rows, total: rows.length });
  return {
    'GET /api/runtime/records?status=needs_attention': {
      body: body(runtimeRecords.filter((r) => r.status === 'needs_attention')),
    },
    'GET /api/runtime/records?workflow_state=blocked': {
      body: body(runtimeRecords.filter((r) => r.workflow.blocked)),
    },
    'GET /api/runtime/records?has_conflict=true': {
      body: body(runtimeRecords.filter((r) => r.evidence_counts.conflicting_evidence >= 1)),
    },
    'GET /api/runtime/records?status=ready_to_export': {
      body: body(runtimeRecords.filter((r) => r.status === 'ready_to_export')),
    },
  };
}

/** S6 routes for an ALREADY-exported experiment on fresh load (View/Download live). */
export function exportedReadyRoutes(id: string = EXP_ID): Record<string, StubbedRoute> {
  const base = `/api/experiments/${encodeURIComponent(id)}`;
  return {
    [`GET ${base}`]: {
      body: {
        ...experimentDetail,
        id,
        status: 'done',
        pending_count: 0,
        exported: true,
        record_id: id,
        artifact_refs: {
          record_filename: artifactsExported.record_filename,
          sidecar_filename: artifactsExported.sidecar_filename,
        },
        workflow: fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: true, rev: VERSION_FIELDS.rev }),
        artifact: { state: 'current', reason: null },
      },
    },
    [`GET ${base}/pending`]: { body: { pending: [] } },
    [`POST ${base}/validate`]: { body: validateExported },
    [`POST ${base}/audit`]: { body: auditExported },
    [`GET ${base}/warnings`]: { body: warningsDryRun },
    // P29.4 — the shared record-session owner's AgentContext evidence input.
    [`GET ${base}/evidence-classification`]: { body: evidenceClassificationResponse },
    [`GET ${base}/artifacts`]: { body: artifactsExported },
    'GET /api/graph/status': { body: graphStatusUnavailable },
  };
}

// --- P27.6 conditional-GET (revision-aware live-sync) fixtures ---------------
//
// The backend now honours `If-None-Match` on GET /api/experiments/{id}: 304 (no
// body) when unchanged, 200 + fresh detail + new ETag when changed. These model
// the client half's poll of that one endpoint.

/** The record AFTER a change elsewhere: a bumped rev + a NEW version/ETag. */
export const experimentDetailChanged = {
  ...experimentDetail,
  rev: 9,
  updated_utc: '2099-04-02T10:00:00Z',
  version: '2.0',
};

/**
 * A GET /api/experiments/{id} route-thunk that models a conditional GET: it
 * answers 304 (unchanged, no body) for the first `unchangedTicks` polls, then
 * 200 with a changed detail carrying a NEW version + ETag on every poll after.
 * The client keeps sending its OLD If-None-Match token, so once the record has
 * changed it keeps reading "changed" until the screen adopts the fresh version —
 * which is exactly why the hook's stale-guard + onChanged-once wiring matters.
 */
export function conditionalGetSequence(
  id: string = EXP_ID,
  opts: { unchangedTicks?: number; newVersion?: string } = {},
): () => RouteResult {
  const unchanged = opts.unchangedTicks ?? 2;
  const newVersion = opts.newVersion ?? experimentDetailChanged.version;
  const changed = { ...experimentDetailChanged, id, version: newVersion };
  let call = 0;
  return () => {
    call += 1;
    if (call <= unchanged) return { status: 304, etag: `"${experimentDetail.version}"` };
    return { status: 200, body: changed, etag: `"${newVersion}"` };
  };
}

/**
 * A stateful GET /api/experiments/{id} route that models real ETag semantics for
 * live-sync integration tests. It serves BOTH the bundle's plain GET (no token →
 * always the current detail) and the poller's conditional GET (token → 304 iff
 * the token equals the current server version, else 200 + the fresh detail). Call
 * `bump()` to simulate a change elsewhere: the version advances to `experiment
 * DetailChanged.version`, so a poller still holding the old token next reads 200.
 */
export function liveDetailRoute(id: string = EXP_ID): {
  route: (init?: RequestInit) => RouteResult;
  bump: () => void;
} {
  let version = experimentDetail.version;
  const detailFor = () => ({
    ...experimentDetail,
    id,
    version,
    rev: version === experimentDetail.version ? experimentDetail.rev : experimentDetailChanged.rev,
  });
  const bump = () => {
    version = experimentDetailChanged.version;
  };
  const route = (init?: RequestInit): RouteResult => {
    const inm = (init?.headers as Record<string, string> | undefined)?.['If-None-Match'];
    if (inm) {
      return inm === `"${version}"`
        ? { status: 304, etag: `"${version}"` }
        : { status: 200, body: detailFor(), etag: `"${version}"` };
    }
    return { status: 200, body: detailFor(), etag: `"${version}"` };
  };
  return { route, bump };
}

// --- P36.4 Settings: Help / About + API Documentation fixtures --------------
// Shapes verbatim from apps/api/isaac_api/routes.py `about()` / `api_openapi()`.
// `aboutResponse` mirrors the real non-sensitive envelope (no hostnames, no
// secrets, no absolute paths). `openApiFixture` is a small, hand-built SUBSET
// of a real generated OpenAPI document — just enough shape (multiple groups,
// one path with parameters, one without) to exercise grouping/search/expand.

export const aboutResponse = {
  app_version: '0.1.0',
  build_commit: 'fakecommit0000settingsp364',
  record_schema_version: '1.05',
  runtime_mode: 'synthetic-only',
  persistence: 'ephemeral',
  data_regime: 'synthetic-only',
  core: 'isaac_records',
};

/** Same shape, but no deploy identity was injected (the honest null case). */
export const aboutResponseNoCommit = {
  ...aboutResponse,
  build_commit: null,
};

// --- P36.6 / P36R S8 Schema Reference browser fixture (GET /api/schema) -----
// A small, hand-built SUBSET of the real vendored schema (schema/isaac_
// record_v1.json) — just enough shape (required + optional top-level fields, a
// const-typed field, an enum with a description, a multi-level nested object
// with its OWN nested `required`, an array-of-string field, and the SAME
// `record_type=evidence -> descriptors required` allOf conditional the real
// schema encodes) to exercise required/optional derivation, enum rendering,
// nested expand, array typing, and relationship rendering — without needing
// the full ~1700-line document. Shape mirrors apps/api/isaac_api/routes.py
// `get_schema()`: {schema_title, schema_version, schema, vocabularies}.

export const schemaBrowserFixture = {
  schema_title: 'ISAAC AI-Ready Scientific Record v1.05 (fixture)',
  schema_version: '1.05',
  schema: {
    title: 'ISAAC AI-Ready Scientific Record v1.05 (fixture)',
    type: 'object',
    required: ['isaac_record_version', 'record_id', 'record_type'],
    allOf: [
      {
        if: { properties: { record_type: { const: 'evidence' } } },
        then: { required: ['descriptors'] },
      },
    ],
    properties: {
      isaac_record_version: { type: 'string', const: '1.05' },
      record_id: {
        type: 'string',
        pattern: '^[0-9A-Z]{26}$',
        description: 'ULID identifier for the record.',
      },
      record_type: {
        type: 'string',
        enum: ['evidence', 'intent', 'synthesis'],
        description: 'Fundamental nature of the record.',
      },
      descriptors: {
        type: 'object',
        description: 'Extracted scientific descriptors — required for an evidence record.',
        required: ['outputs'],
        properties: {
          outputs: {
            type: 'array',
            description: 'One or more descriptor output batches.',
            items: {
              type: 'object',
              required: ['descriptors'],
              properties: {
                descriptors: {
                  type: 'array',
                  description: 'The descriptor rows in this batch.',
                  items: {
                    type: 'object',
                    required: ['name'],
                    properties: {
                      // Pattern-constrained, NOT enumerated inline, and its
                      // description cites the vocabulary source slug — the
                      // exact shape the real schema uses for descriptors[].name,
                      // so the Vocabulary ↔ schema link renders in tests.
                      //
                      // The cited slug ("Zebra-Terms") deliberately shares NO
                      // substring with the production slug
                      // ("Controlled-Vocabulary"): a hard-coded needle would
                      // find nothing here, so these tests can only pass if the
                      // link is genuinely derived from the vocabulary file's
                      // own `source`.
                      name: {
                        type: 'string',
                        pattern: '^[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)*$',
                        description:
                          'Descriptor name. See Zebra-Terms for the canonical class list.',
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
      sample: {
        type: 'object',
        description: 'The physical sample under study.',
        required: ['sample_form'],
        allOf: [
          {
            if: { properties: { sample_form: { const: 'powder' } } },
            then: { required: ['material'] },
          },
        ],
        properties: {
          sample_form: { type: 'string', description: 'Physical form of the sample.' },
          material: {
            type: 'object',
            description: 'Chemical/material identity of the sample.',
            properties: {
              formula: {
                type: 'string',
                description: 'Chemical formula, e.g. CuO2.',
                examples: ['CuO2', 'Fe2O3'],
              },
            },
          },
        },
      },
      tags: {
        type: 'array',
        items: { type: 'string' },
        description: 'Free-form, user-assigned grouping labels.',
      },
    },
  },
  vocabularies: {
    descriptor_class: {
      field: 'descriptor_class',
      note: 'Fixture vocabulary note (synthetic, for tests).',
      source: 'https://example.invalid/wiki/Zebra-Terms',
      classes: {
        spectroscopy: ['white_line_energy', 'edge_shift'],
      },
      products: ['H2', 'CO'],
    },
  },
};

export const openApiFixture = {
  openapi: '3.1.0',
  info: {
    title: 'ISAAC Metadata Assistant — local UI backend',
    version: '0.1.0',
    // Verbatim from `apps/api/isaac_api/app.py` (Slice 2A).
    summary:
      'FastAPI wrapper over the deterministic isaac_records core: a synthetic-only workspace plus one read-only, aggregate-only database diagnostic.',
  },
  // P36V PR3 slice C — the document now REGISTERS tags, and grouping is derived
  // from them (`lib/apiDocsModel.ts`). Four properties are covered on purpose:
  //   · registration order is NOT alphabetical, so a test on group order can
  //     only pass if the order comes from this array;
  //   · `Experiments` is registered with NO description (the group chip must
  //     render without inventing one);
  //   · `Schema & Vocabulary` is registered but used by no operation below (a
  //     registered tag must not conjure an empty group);
  //   · `Validation` is used by an operation but NOT registered here (it must
  //     still render, sorted after every registered tag).
  tags: [
    {
      name: 'Health & Meta',
      description: "Liveness, deployment identity, and this API's own machine-readable description.",
    },
    { name: 'Experiments' },
    {
      name: 'Drafts & Answers',
      description: "Reading a record's draft fields and answering its blocking questions.",
    },
    {
      name: 'Uploads',
      description: 'The governance seam for file upload. It always refuses.',
    },
    {
      name: 'Schema & Vocabulary',
      description: 'Registered here but carried by no operation in this subset.',
    },
  ],
  paths: {
    '/api/health': {
      get: {
        tags: ['Health & Meta'],
        summary: 'Report Liveness and Deploy Identity',
        description: 'Liveness, runtime mode, core, version, and build commit.',
        parameters: [],
        // The ONLY operation with no documented 401 — so it is the one Quick
        // Start may honestly propose as a first request.
        responses: { '200': { description: 'The liveness banner.' } },
      },
    },
    '/api/about': {
      get: {
        tags: ['Health & Meta'],
        summary: 'Get App and Provenance Metadata',
        description: 'Non-sensitive app/provenance metadata for Settings.',
        parameters: [],
        responses: {
          '200': { description: 'The app and provenance metadata.' },
          '401': { description: 'The deployment requires an API key and none was presented.' },
        },
      },
    },
    '/api/experiments/{id}': {
      get: {
        tags: ['Experiments'],
        summary: 'Get Experiment',
        description: 'Fetch one experiment detail by id.',
        parameters: [
          { name: 'id', in: 'path', required: true, description: 'The id of an experiment.' },
        ],
        responses: {
          '200': { description: 'The experiment detail bundle.' },
          '401': { description: 'The deployment requires an API key and none was presented.' },
          '404': { description: 'No experiment in this workspace has that id.' },
        },
      },
    },
    '/api/experiments/{id}/answers': {
      post: {
        tags: ['Drafts & Answers'],
        summary: 'Submit Answers',
        description: 'Apply confirmed answers to pending blockers.',
        parameters: [
          { name: 'id', in: 'path', required: true },
          // Declared OPTIONAL even though its own wording says otherwise — the
          // renderer reports the DECLARED flag and the wording verbatim, and
          // never overrides one with the other.
          {
            name: 'If-Match',
            in: 'header',
            required: false,
            description: "Required. The record's current ETag.",
          },
        ],
        // P36R S9 — request/response detail the master-detail browser renders
        // when the contract supplies it. Two `$ref` cases on purpose: the 422
        // names a schema that IS in `components` (one-level resolution), the
        // 404 names one that is DELIBERATELY ABSENT, so the fallback that shows
        // the raw `$ref` verbatim is covered and a synthesized placeholder
        // shape would fail the suite.
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: { type: 'object', title: 'SyntheticAnswersBody' },
              example: { answers: [{ id: 'series', value: 'CuO2_merged.xdi' }] },
            },
          },
        },
        responses: {
          '200': {
            description: 'Successful Response',
            content: {
              'application/json': { schema: { type: 'object', title: 'SyntheticAnswersResult' } },
            },
          },
          '401': { description: 'The deployment requires an API key and none was presented.' },
          '404': {
            description: 'Not Found',
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/SyntheticFixtureAbsentTarget' },
              },
            },
          },
          '422': {
            description: 'Validation Error',
            content: {
              'application/json': { schema: { $ref: '#/components/schemas/SyntheticFixtureError' } },
            },
          },
        },
      },
    },
    // A documented 200 that the handler NEVER produces. The document says so in
    // its own words, and the browser must render that wording rather than
    // presenting the 200 as an achievable outcome.
    '/api/uploads': {
      post: {
        tags: ['Uploads'],
        summary: 'Refuse a File Upload (Governance Seam)',
        description: 'Always refuses. No file is read, parsed, or stored.',
        responses: {
          '200': {
            description: 'Not produced by this operation — every request is refused with the 403.',
          },
          '401': { description: 'The deployment requires an API key and none was presented.' },
          '403': { description: 'The refusal, with its reason. This is the only outcome.' },
        },
      },
    },
    // A write operation that reads the RAW request and therefore declares no
    // `requestBody` — its expected body is described in prose only. The browser
    // must say so instead of fabricating a schema. Its tag is deliberately not
    // registered in `tags` above.
    '/api/validate/record': {
      post: {
        tags: ['Validation'],
        summary: 'Validate a Supplied Candidate Record',
        description: 'Send the record as a raw JSON body. It is read in memory under a size limit.',
        responses: {
          '200': { description: 'The official-schema verdict and the errors.' },
          '401': { description: 'The deployment requires an API key and none was presented.' },
          '413': { description: 'The body exceeds the request size limit.' },
          '422': { description: 'The body is not well-formed JSON, or is not a JSON object.' },
        },
      },
    },
    // NO tags at all — the deterministic untagged fallback bucket, sorted last.
    // Its `q` is declared REQUIRED (the real one is not) so the generated
    // samples' required-query-parameter placeholder is covered.
    '/api/search': {
      get: {
        summary: 'Search the Workspace and Project Memory',
        description: 'One grouped envelope with a workspace group and a memory group.',
        parameters: [
          { name: 'q', in: 'query', required: true, description: 'The search text.' },
          { name: 'limit', in: 'query', required: false, description: 'Rows per group.' },
        ],
        responses: {
          '200': { description: 'The normalised query and the two plane groups.' },
          '401': { description: 'The deployment requires an API key and none was presented.' },
        },
      },
    },
  },
  components: {
    // `SyntheticFixtureAbsentTarget` is intentionally NOT declared here.
    schemas: {
      SyntheticFixtureError: {
        type: 'object',
        title: 'SyntheticFixtureError',
        properties: { detail: { type: 'string' } },
      },
    },
  },
};

// --- P36V.1 — the REAL generated contract's operation descriptions -----------
/**
 * Every operation description in the REAL `GET /api/openapi` document, verbatim,
 * for the ONE property no hand-built fixture could ever check: that the Endpoint
 * Explorer's `Full Description` disclosure never hides this API's own
 * boundary/honesty copy.
 *
 * Regenerated on 2026-07-31 with:
 *
 *   PYTHONPATH=apps/api .venv/bin/python -c \
 *     "from isaac_api.app import create_app; import json; \
 *      print(json.dumps(create_app().openapi()))"
 *
 * 36 operations · 20,915 description characters · 43 post-lead paragraphs · lead
 * paragraphs 78–594 characters · remainders 0–1,740. The 36th is
 * `GET /api/runtime/database/recon`; `GET /api/health` also gained a paragraph
 * about the database block it now reports, and this copy had gone stale on it.
 *
 * This fixture is what caught the original defect: the first version of the
 * disclosure had NO length threshold and so collapsed 31 of the then-35
 * operations, hiding 8,568 of that contract's 18,314 characters (47%) —
 * including the "There is no language model" refusal caveat, the graph
 * structural-staleness disclosure, and "never a correctness ruling. Read-only."
 *
 * `openApiFixture` above cannot substitute: it carries no multi-paragraph
 * description at all (`grep -c '\n\n'` → 0), which is precisely why every test in
 * the suite passed while half the contract text was hidden.
 *
 * HONEST LIMIT: this is a point-in-time COPY. Nothing in CI regenerates it, so a
 * new backend docstring will not appear here until someone re-runs the command
 * above. What the tests over it establish is that the RULE
 * (`splitPurpose` = length threshold AND no boundary marker) holds over this
 * API's real prose — not that the copy is current. The rule itself is what
 * protects a description added later.
 */
export const REAL_CONTRACT_DESCRIPTIONS: readonly { op: string; description: string }[] = [
  { op: "GET /api/health", description: "Liveness banner for platform and container probes: the service status, the runtime data mode, the name of the deterministic core package the app calls in process, the app version, and the build commit when the deployment supplies one (otherwise `null` — it is never guessed). This is the one operation that stays reachable without credentials when the deployment enables authentication. Read-only.\n\nIt also states whether this deployment has an application database configured, how that database is classified, whether hosted display of its per-record content is open, and the outcome of the most recent reconnaissance scan in this process. That block is derived from configuration alone: this operation never opens a database connection, issues a query, or waits on one, so a database problem can never change its result and can never fail a container probe." },
  { op: "POST /api/demo/run", description: "Runs the committed synthetic demo pipeline and returns the ordered steps it executed together with the resulting experiment id and status. `mode: \"draft_only\"` (the default) extracts a draft from the committed fixtures and runs the no-guessing draft checks; `mode: \"full\"` additionally applies the committed simulated answers and exports an official record. It writes into one fixed canonical experiment id per mode, overwriting it in place, so re-running never adds a record and never increases the record count. It reads only the two committed synthetic fixtures and accepts no uploaded data.\n\nA body other than `draft_only` or `full` for `mode` is rejected and nothing runs." },
  { op: "POST /api/demo/reset", description: "Restores the workspace to exactly the canonical synthetic demo scenarios and reports the before/after counts, the removable set, and a state histogram. `mode: \"preview\"` classifies only and mutates nothing; `mode: \"execute\"` additionally requires the exact confirmation phrase and refuses without it. It accepts no caller-supplied ids or paths — any extra field is rejected — it removes only records it can classify as managed synthetic-demo records, and it refuses to remove anything at all if any record is ambiguous. No filesystem path appears in the response.\n\nThere is deliberately no general per-experiment delete operation." },
  { op: "GET /api/experiments", description: "One summary row per experiment currently in the workspace: its id, title, derived status, creation time, how many blocking questions are still open, how many fields carry evidence, whether it has been exported, and the exported record id when there is one. Rows for the five canonical synthetic seeds also carry a derived, never-stored `scenario` label naming which seeded fixture they are; it is null for any other record. Read-only, and it states no validity verdict." },
  { op: "GET /api/experiments/{experiment_id}", description: "The full detail bundle for one experiment: its summary row plus whether the draft passes the no-guessing checks, the exported artifact filenames (basenames only, never a server path), the source files it was extracted from, the derived workflow progression, the exported-artifact freshness state, and the current revision metadata.\n\nThe response carries the record's current `ETag`. Send it back as `If-None-Match` to receive `304` while the record is unchanged. Read-only." },
  { op: "GET /api/experiments/{experiment_id}/draft", description: "This record's draft fields, grouped into the stable sections the record review screen renders. Each field carries its label, official path, current value, the status derived from its evidence, and the kinds of source that evidence came from. Read-only; the response carries the record's current `ETag`." },
  { op: "GET /api/experiments/{experiment_id}/pending", description: "The questions that are still blocking this draft, each with the stable key an answer must be submitted under, what the question is about, and — for the committed synthetic demo only — a clearly labelled suggested answer that is never applied automatically. Read-only; the response carries the record's current `ETag`." },
  { op: "POST /api/experiments/{experiment_id}/answers", description: "Applies caller-supplied answers to this draft's open blocking questions and returns the refreshed question list, the record's status, its new revision metadata, the derived workflow, and which downstream steps the change reopened.\n\nRequires `confirmed_by_user: true` and the record's current `ETag` in `If-Match`. Blank and unrecognised answers are dropped rather than invented, so a submission that changes nothing is a no-op: it is not logged and does not advance the revision." },
  { op: "POST /api/experiments/{experiment_id}/edit", description: "Overwrites the current value of a field that has already been answered, recording a fresh user confirmation, and returns the same refreshed bundle as the answers operation.\n\nRequires `confirmed_by_user: true` and the record's current `ETag` in `If-Match`. A body that names no recognised editable field is rejected with `422` rather than silently doing nothing, and a value that fails the core's own checks leaves the stored value unchanged. It never reopens or creates a blocking question." },
  { op: "POST /api/experiments/{experiment_id}/export", description: "Runs the schema-gated export for this record. On success it writes the official ISAAC record and its evidence sidecar into the workspace and returns the record id, the two artifact filenames (basenames only, never a server path), the refreshed revision metadata, the workflow, and the downstream invalidation.\n\nA gated failure also returns `200`, with `ok: false`, the failing draft and official reports, and a flat `errors` list — decide by reading `ok`, not the status code. Nothing is written in that case.\n\nRequires the record's current `ETag` in `If-Match`. Exported records are immutable: exporting a record that already has one is refused." },
  { op: "POST /api/experiments/{experiment_id}/ingestion/csv/preview", description: "Read-only preview of a campaign-sheet CSV, reconciled field by field against this record's current authoritative values. Returns the row and candidate counts, the mapped candidate fields with their reconciliation outcome, and non-actionable warnings for unrecognised columns.\n\nSend the CSV as a raw `text/csv` request body, not as a multipart form. The body is read in memory under a hard size limit and is never written anywhere: no draft change, no revision bump, no export, no indexing, and no retained upload. Only outcome metadata is logged — never the rows, the candidate values, or the filename.\n\nRequires the record's current `ETag` in `If-Match`, which is checked before the body is read. Available only while the deployment is in synthetic-only data mode.\n\nA malformed CSV — unreadable, an empty or duplicated header column, a missing required column, or a row, column, cell, or candidate count over the limit — is rejected with `422` and a stable error code." },
  { op: "POST /api/experiments/{experiment_id}/validate", description: "Checks this record against the vendored official ISAAC schema and returns `ok`, a list of `{path, message}` errors, the schema label, and whether the check was a dry run.\n\nFor an already-exported record the written record is validated (`dry_run: false`). Otherwise the export is run in memory and the resulting candidate record is validated without writing anything (`dry_run: true`). Read-only in both cases. The verdict comes from the same deterministic core function the command line uses." },
  { op: "POST /api/validate/record", description: "Standalone validator for a candidate official ISAAC record supplied directly as a JSON request body — no experiment, no draft, and no workspace involved. Returns `ok`, a rendered summary line, the `{path, message}` errors, and the schema version checked against.\n\nIt calls the same authoritative validator over the same vendored schema that the per-experiment validation operation uses, so the two verdicts agree by construction. The body is never written anywhere and its content is never logged; only the outcome and error count are.\n\nSend the record as a raw JSON body. The body is read in memory under a hard size limit." },
  { op: "POST /api/experiments/{experiment_id}/audit", description: "Runs the deterministic audit over the official record and evidence sidecar this record's export wrote, returning the per-record official-schema report, its evidence-coverage counts, and the rendered text report.\n\nA record that has not been exported yet returns `200` with no rows and a message saying so, rather than an error. Read-only." },
  { op: "GET /api/experiments/{experiment_id}/warnings", description: "Advisory, non-gating warnings for this record. For an already-exported record the written record is checked (`dry_run: false`); otherwise the in-memory export candidate is checked (`dry_run: true`).\n\nThis channel deliberately carries no pass, fail, or validity field, and it never blocks an export — read it as advice for a human, alongside the official-schema verdict, not instead of it. The `GET` and `POST` forms are equivalent: both are read-only and return the same payload." },
  { op: "POST /api/experiments/{experiment_id}/warnings", description: "Advisory, non-gating warnings for this record. For an already-exported record the written record is checked (`dry_run: false`); otherwise the in-memory export candidate is checked (`dry_run: true`).\n\nThis channel deliberately carries no pass, fail, or validity field, and it never blocks an export — read it as advice for a human, alongside the official-schema verdict, not instead of it. The `GET` and `POST` forms are equivalent: both are read-only and return the same payload." },
  { op: "GET /api/experiments/{experiment_id}/evidence", description: "The field-by-field evidence trail for this record: each official path, its value, the kind of support behind it, and the source file and locator cited.\n\nFor an already-exported record the trail is read from the evidence sidecar written alongside the official record; otherwise it is read from the draft's own evidence envelopes. Read-only." },
  { op: "GET /api/experiments/{experiment_id}/evidence-classification", description: "Per-field evidence-support classification for this record's current state, plus a histogram over the five classes — `supported`, `inferred_candidate`, `insufficient_evidence`, `conflicting_evidence` and `unknown` — bound to the authoritative `record_rev` so a client can tell when its view is stale.\n\nThis carries the evidence-support axis only. It deliberately reports no validity, completion, exportability, or advisory verdict; those live in their own operations. Read-only, and it takes no lock." },
  { op: "GET /api/experiments/{experiment_id}/source-preview", description: "The text of one committed synthetic source fixture, line by line, together with the one-based line numbers this record's evidence actually cites in it. Read-only.\n\nOnly the two committed synthetic fixtures may be previewed. A name containing a path separator or a traversal fragment is rejected, and any other filename is refused with the allowed names listed in the response. The fixture that cites fields rather than lines yields no cited line numbers, which is expected rather than an error." },
  { op: "GET /api/experiments/{experiment_id}/artifacts", description: "The official ISAAC record and the evidence-sidecar JSON that this record's export wrote, plus their filenames as bare basenames — never a server path.\n\nBoth files are resolved from the record id, never from a caller-supplied path. A record that has not been exported yet returns `200` with null payloads rather than an error. Read-only." },
  { op: "GET /api/graph/status", description: "Provider-agnostic status for the Project Memory plane: whether it is available, the integrity of its artifact, the provider serving it, whether its indexing policy is consistent, the freshness of its indexed sources together with the scope and basis of that judgement, the policy and served-manifest fingerprints, the served file count, and the snapshot schema version. Node, edge, community, file and concept counts are included when a graph is readable and are explicit nulls otherwise, so the response shape never changes.\n\nThe deployed app commit is reported as version metadata only and is never an input to any freshness judgement. A freshness status that cannot be proven is reported as unknown rather than assumed current.\n\nProject Memory provides leads and provenance to confirm against the cited files, never a correctness ruling. Read-only." },
  { op: "POST /api/uploads", description: "Always refuses with `403`. This is the write side of the synthetic-only governance boundary: no multipart form is declared or parsed, and no file is read, inspected, or stored. The refusal carries the reason and the current synthetic-only flag so a client can explain the boundary to a user.\n\nReal or private data ingestion is approval-gated and is not enabled in this prototype." },
  { op: "GET /api/memory/concepts", description: "The concepts Project Memory has indexed, each with the label and summary metadata the reader exposes.\n\nWhen no graph is readable this returns `200` with `available: false`, a stable machine-readable reason, and an empty list — never an error status and never a fabricated concept. Read-only. Project Memory returns leads to verify, never a validation verdict." },
  { op: "GET /api/memory/concepts/{concept_id}", description: "One concept's detail together with the files and other concepts related to it.\n\nWhen no graph is readable this returns `200` with `available: false` and a null concept: availability is reported before identity, because the set of valid ids cannot be known without a graph, so an unknown id is only ever reported once the graph is known to be readable. Read-only; leads to verify, never a verdict." },
  { op: "GET /api/memory/files", description: "The repository files Project Memory has indexed and is allowed to serve, each with the metadata the reader exposes for it.\n\nWhen no graph is readable this returns `200` with `available: false`, a stable reason, and an empty list. Read-only; leads to verify, never a verdict." },
  { op: "GET /api/memory/file", description: "One indexed file's detail, the files and concepts related to it, and the rationales recorded for those relationships.\n\nAn unsafe path is rejected regardless of whether a graph is readable, because that guard is deterministic and does not depend on the graph. A safe path that is simply not indexed is reported as not found once the graph is known to be readable. Read-only; leads to verify, never a verdict." },
  { op: "GET /api/memory/graph", description: "A deterministic, capped projection of the served-file reference graph: nodes, undirected deduplicated edges, communities, and the provenance of the projection. Every element is derived from the Project Memory reader's public surface, so it describes the same graph the status operation reports on.\n\nWhen no graph is readable it returns an honest envelope with `available: false` and zero nodes and edges rather than a fabricated graph. Read-only; leads to verify, never a verdict." },
  { op: "GET /api/memory/graph/detail", description: "The symbol-level structure of the source graph: the individual symbols, document sections, and recorded rationales inside each served file, the relations between them, and their community grouping. Every node, relation, and direction is the source graph's own value, passed through verbatim.\n\nThis is a point-in-time index, not a map of today's code. The structure describes the commit reported as `built_at_commit`, which is generally **not** the current repository head, and the response says so machine-readably with `is_point_in_time: true` and `describes_current_head: false`. Content freshness and structural freshness are separate axes: the served-file content manifest is kept current, while this structure stays pinned to the commit that was indexed, and `served_set_consistency` reports whether the two still describe the same set of served files.\n\nScoped to served files only — a symbol whose owning file is not served is absent, never partially disclosed. Served separately from the graph projection operation because it is much larger and is fetched only on demand; that operation's own response is unaffected by this one.\n\nWhen the artifact is absent or unreadable it returns an honest envelope with `available: false` and zero nodes and edges rather than a fabricated graph, and its provenance collapses to nulls rather than to plausible-looking defaults. Read-only; leads to verify, never a verdict." },
  { op: "GET /api/search", description: "One grouped envelope with two independently reported groups: `workspace` (truth-plane leads from the experiment snapshot) and `memory` (advisory Project Memory leads). Each group carries its own plane label, provider, availability, reason, totals and pagination, so a memory lead can never be mistaken for a truth-plane ruling, and one group's failure never affects the other.\n\nThe envelope computes no verdict, and a plane that cannot answer degrades inside the `200` body rather than returning an error status. Read-only; it reshapes only content the read operations already expose." },
  { op: "GET /api/runtime/records", description: "A derived read model over the same experiment snapshot the search operation uses, for triaging many records at once. Each row carries only a fixed safe set of confirmed facts: the experiment id, title, derived status, open-question count, exported flag, exported record id, a minimal workflow summary, the five-class evidence histogram as counts only, the exported-artifact freshness state, the current revision, the last update time, and a client route to open the record. No field value, evidence body, source locator, or filesystem path appears.\n\n`total` is the filtered count taken before pagination, so a client can page without losing the denominator. Rows are ordered deterministically. Computed fresh on every call — no index, no cache, no lock, and no mutation." },
  { op: "POST /api/experiments/{experiment_id}/assistant/query", description: "Answers a free-form question about this record by classifying it against a fixed, finite intent catalog and answering from grounding assembled read-only from what the API already exposes for the record: its summary, open blocking questions, evidence trail, workflow, revision, an in-memory validation dry run, and Project Memory search.\n\nThere is no language model. A question outside the catalog, or one too ambiguous to route, is refused honestly rather than answered — it never guesses a scientific value.\n\nRead-only and advisory: it never changes the record, its revision, its workflow, its evidence, its validation, its export, Project Memory, or any file, and it never states a pass, fail, valid, or invalid conclusion. The response carries the record's unchanged `ETag`." },
  { op: "POST /api/assistant/memory/query", description: "The record-agnostic counterpart of the per-record assistant operation, for surfaces that have no record open. The same fixed classifier is applied: a project-memory question is answered purely from the Project Memory reader as leads to verify, and any other question is refused honestly with a pointer to open a record first.\n\nThere is no language model, no record is loaded or created, and nothing is mutated. It never states a pass, fail, valid, or invalid conclusion." },
  { op: "GET /api/about", description: "Non-sensitive identity and provenance for this deployment: the app version, the build commit when the deployment supplies one (otherwise `null` — it is never guessed), the official ISAAC record-schema version this build validates against, the runtime data mode, the persistence model, the data regime, and the name of the deterministic core package.\n\nEvery value is reused from the same authoritative source `GET /api/health` reads, so the two can never disagree. Read-only." },
  { op: "GET /api/openapi", description: "This application's own generated OpenAPI document — the same document served at the root `/openapi.json`, but reachable under the deployment's base path so a browser client can fetch it without knowing the root.\n\nIt is generated from the live routes, never hand-maintained, so it cannot drift from what a caller can actually reach. It describes route signatures and documentation only: no runtime state and no configuration values. Read-only." },
  { op: "GET /api/schema", description: "The vendored official ISAAC record schema verbatim, its title and the version this build validates against, plus every controlled vocabulary in the repository keyed by its filename stem.\n\nEvery field, type, required flag, enumeration, description and composition relationship a client renders comes straight from these two sources; the schema is loaded through the same path resolver the validator uses, never a hardcoded copy. This is a read-only reference view of the public canonical schema — there is no propose, review, approve, or edit affordance." },
  { op: "GET /api/runtime/database/recon", description: "A sanitized, aggregate-only reconnaissance report over this deployment's own application database. It answers one question — do the stored records validate against the vendored official ISAAC schema — and reports the answer as counts.\n\nThe scan is strictly read-only, and no write is possible: the transaction is set AND verified read-only server-side, every statement is checked against a SELECT-only allowlist before it is issued, and values are always bound as parameters. The row count is also compared before and after, but that is a concurrency check rather than a mutation proof — a row-count equality cannot detect an update and cannot distinguish this scan's writes from a concurrent writer's, so it is the verified read-only transaction and the allowlist that carry the guarantee. The statement counters report every statement this service issues through a cursor; they are not a wire-level record, because the driver's own transaction framing never passes through one.\n\nThe response carries aggregates only: record totals, counts by type and domain, validation totals by rule family and by schema path, and the gate results. It never carries a record id, a title, a scientific value, a stored document, a connection detail, or a credential; per-record content stays closed. A serialized-output scan runs over every response shape before it is returned and replaces it with a sanitized failure if it trips. Every shape also carries a fixed `limitations` list saying what the gates cannot establish — in particular that the production-isolation gate is a tripwire rather than proof, and that the confirmed transport encryption does not verify the server certificate.\n\nWhen the deployment has no database configured, the operation reports that and connects to nothing. Repeat calls inside a short window are served from memory, and a scan already in progress is reported as a conflict rather than opening a second connection. The operation takes no parameters and no body." },
];

// --- Statistics dashboard fixtures (the four page-level reads) ---------------
//
// The Statistics page reads `GET /api/runtime/records` with NO filters, so its
// route key is the BARE path. `runtimeRecordsRoutes()` above serves only the four
// FILTERED keys the triage chips build, and none of them matches — hence the
// separate bundle below rather than a widening of that helper.

/** The one extra row's id. Unmistakably synthetic, like every id in this file. */
const STATS_EXTRA_ID = '01SYNTHSTATS00000000000005';

/**
 * The five projected rows the Statistics page is exercised against.
 *
 * `runtimeRecords` above carries 1 needs_attention / 1 ready_to_export /
 * 1 in_review / 1 done, which is NOT the real canonical distribution of the
 * synthetic seed set (2 / 1 / 1 / 1 — the same distribution `RESET_STATE_COUNTS`
 * pins for the demo reset). It is consumed by the triage suites, so it is reused
 * VERBATIM here and extended by one row rather than altered.
 *
 * The extra row's `current_step` is `review_evidence`, which no `runtimeRecords`
 * row occupies, so the five rows span five of the six canonical workflow buckets
 * and leave `load_record` at ZERO — the empty bucket a distribution must still
 * draw. Its evidence histogram is deliberately spread across four of the five
 * classes so no class total is a coincidence of a single row.
 */
export const statisticsRuntimeRecords = [
  ...runtimeRecords,
  {
    experiment_id: STATS_EXTRA_ID,
    title: 'Synthetic XANES — Second Needs Attention',
    status: 'needs_attention',
    pending_count: 2,
    exported: false,
    record_id: null,
    workflow: { current_step: 'review_evidence', blocked: false, reopened: false },
    evidence_counts: { supported: 4, inferred_candidate: 2, insufficient_evidence: 1, conflicting_evidence: 0, unknown: 1 },
    artifact_state: 'none',
    record_rev: 2,
    updated_utc: '2099-07-05T00:00:00Z',
    navigate_to: `/record/${STATS_EXTRA_ID}`,
  },
];

/** The body `GET /api/runtime/records` serves for the five rows above. */
export const statisticsRecordsBody = {
  records: statisticsRuntimeRecords,
  total: statisticsRuntimeRecords.length,
};

/**
 * EXACTLY the four route keys the Statistics page requests, in the order the
 * page issues them. Exported so a test can assert the request set itself instead
 * of restating four literals it might mistype.
 */
export const STATISTICS_ROUTE_KEYS = [
  'GET /api/runtime/records',
  'GET /api/graph/status',
  'GET /api/about',
  'GET /api/openapi',
] as const;

/**
 * The Statistics page's four page-level reads, keyed exactly as `lib/api` builds
 * them.
 *
 * Any source may be replaced with any `RouteEntry`, which is how a test fails ONE
 * of the four (`statisticsRoutes({ records: { status: 500, body: {} } })`) or
 * swaps in a different graph body, without disturbing the other three.
 */
export function statisticsRoutes(
  over: Partial<Record<'records' | 'graph' | 'about' | 'openapi', RouteEntry>> = {},
): Record<string, RouteEntry> {
  return {
    'GET /api/runtime/records': over.records ?? { body: statisticsRecordsBody },
    'GET /api/graph/status': over.graph ?? { body: graphStatusAvailable },
    'GET /api/about': over.about ?? { body: aboutResponse },
    'GET /api/openapi': over.openapi ?? { body: openApiFixture },
  };
}

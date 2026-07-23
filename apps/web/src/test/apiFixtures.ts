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
  artifact_refs: { record_path: null, sidecar_path: null },
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

/** Artifacts before export: all null (200, not an error). */
export const artifactsNull = {
  record: null,
  sidecar: null,
  record_path: null,
  sidecar_path: null,
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
  reason:
    'Real or private data upload is approval-gated and not enabled in this synthetic prototype.',
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

/** The five canonical scenarios as a summary list (post-reset dashboard).
 * Distribution: needs_attention:2, ready_to_export:1, in_review:1, done:1. */
export const canonicalFiveSummaries = [
  { id: CANONICAL_RESET_IDS[0], title: `${RESET_TITLE_BASE} · New Draft`, status: 'needs_attention', created_utc: '2026-07-12T00:00:01Z', pending_count: 5, evidenced_field_count: 26, exported: false, record_id: null },
  { id: CANONICAL_RESET_IDS[1], title: `${RESET_TITLE_BASE} · Partially Completed`, status: 'needs_attention', created_utc: '2026-07-12T00:00:02Z', pending_count: 2, evidenced_field_count: 30, exported: false, record_id: null },
  { id: CANONICAL_RESET_IDS[2], title: `${RESET_TITLE_BASE} · Ready to Export`, status: 'ready_to_export', created_utc: '2026-07-12T00:00:03Z', pending_count: 0, evidenced_field_count: 33, exported: false, record_id: null },
  { id: CANONICAL_RESET_IDS[3], title: `${RESET_TITLE_BASE} · Export Review Required`, status: 'in_review', created_utc: '2026-07-12T00:00:04Z', pending_count: 0, evidenced_field_count: 33, exported: false, record_id: null },
  { id: CANONICAL_RESET_IDS[4], title: `${RESET_TITLE_BASE} · Exported Record`, status: 'done', created_utc: '2026-07-12T00:00:05Z', pending_count: 0, evidenced_field_count: 33, exported: true, record_id: CANONICAL_RESET_IDS[4] },
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
  artifact_refs: {
    record_path: `/tmp/isaac-ui-workspace/${EXP_ID}/records/${EXP_ID}.json`,
    sidecar_path: `/tmp/isaac-ui-workspace/${EXP_ID}/records/${EXP_ID}.evidence.json`,
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
  record_path: `/tmp/isaac-ui-workspace/${EXP_ID}/records/${EXP_ID}.json`,
  sidecar_path: `/tmp/isaac-ui-workspace/${EXP_ID}/records/${EXP_ID}.evidence.json`,
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
          record_path: artifactsExported.record_path,
          sidecar_path: artifactsExported.sidecar_path,
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
          record_path: artifactsExported.record_path,
          sidecar_path: artifactsExported.sidecar_path,
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

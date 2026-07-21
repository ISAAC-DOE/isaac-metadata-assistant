/*
 * Test doubles for the FastAPI backend: realistic response fixtures (shapes
 * verbatim from apps/api/isaac_api/{routes,serialize}.py — see
 * .superpowers/sdd/task-1-report.md) + a tiny route-keyed fetch stub.
 * Values are unmistakably synthetic.
 */

import { vi } from 'vitest';

// --- fetch stub ---------------------------------------------------------

export interface StubbedRoute {
  status?: number;
  body: unknown;
}

/**
 * Stub `fetch` with a `"METHOD /api/path" -> response` map. Returns the list of
 * keys actually requested (for asserting which endpoints were hit). Unknown
 * routes reject like a network error so tests fail loudly.
 */
export function stubFetchRoutes(routes: Record<string, StubbedRoute>): string[] {
  const calls: string[] = [];
  const impl = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url =
      typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    const key = `${method} ${url.replace(/^https?:\/\/[^/]+/, '')}`;
    calls.push(key);
    const hit = routes[key];
    if (!hit) throw new TypeError(`fetch stub: no route for ${key}`);
    const status = hit.status ?? 200;
    // A `body` may be a thunk, re-evaluated on every hit, so a test can model an
    // endpoint whose response changes over time (e.g. the experiment list before
    // vs. after a reset). Plain-object bodies (the common case) are unaffected.
    const body = typeof hit.body === 'function' ? (hit.body as () => unknown)() : hit.body;
    return {
      ok: status < 400,
      status,
      json: async () => body,
    } as Response;
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

export const experimentDetail = {
  ...experimentSummary,
  draft_ok: true,
  artifact_refs: { record_path: null, sidecar_path: null },
  source_files: ['mock_campaign.csv', 'raw_scan_listing.txt'],
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
    [`GET ${base}/artifacts`]: { body: artifactsNull },
    'GET /api/graph/status': { body: graphStatusUnavailable },
  };
}

// --- S4/S6 completion + export fixtures ----------------------------------

const SYNTH_SHA = 'c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345';

/** POST /answers response after confirming the processing-notebook sha256. */
export const answersAfterNotebook = {
  pending: pendingResponse.pending.slice(1),
  status: 'needs_attention',
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
    [`GET ${base}`]: { body: { ...experimentDetail, id, status: 'ready_to_export', pending_count: 0 } },
    [`GET ${base}/pending`]: { body: { pending: [] } },
    [`POST ${base}/validate`]: { body: validateReadyDryRun },
    [`POST ${base}/audit`]: { body: auditNotExported },
    [`GET ${base}/warnings`]: { body: warningsDryRun },
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
      },
    },
    [`GET ${base}/evidence`]: { body: evidenceExported },
    [`GET ${base}/artifacts`]: { body: { ...artifactsExported, record: { ...artifactsExported.record, record_id: id }, sidecar: { ...artifactsExported.sidecar, record_id: id } } },
    [`GET ${base}/source-preview?source=mock_campaign.csv`]: { body: sourcePreviewCsv },
    [`GET ${base}/source-preview?source=raw_scan_listing.txt`]: { body: sourcePreviewListing },
    'GET /api/graph/status': { body: graphStatusUnavailable },
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
      },
    },
    [`GET ${base}/pending`]: { body: { pending: [] } },
    [`POST ${base}/validate`]: { body: validateExported },
    [`POST ${base}/audit`]: { body: auditExported },
    [`GET ${base}/warnings`]: { body: warningsDryRun },
    [`GET ${base}/artifacts`]: { body: artifactsExported },
    'GET /api/graph/status': { body: graphStatusUnavailable },
  };
}

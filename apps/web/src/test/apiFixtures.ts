/*
 * Test doubles for the FastAPI backend: realistic response fixtures (shapes
 * verbatim from apps/api/isaac_api/{routes,serialize}.py — see
 * .superpowers/sdd/task-1-report.md) + a tiny route-keyed fetch stub.
 * Values are unmistakably synthetic.
 */

import { vi } from 'vitest';

import type { ApiWorkflow } from '../lib/types';
// The verification report bodies live in their own module, with the rest of the
// Record Verification wire fixtures. Imported rather than duplicated so one
// contract has one fixture.
import { verificationReportOk } from './verificationFixtures';

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
 *
 * AN ASYNC THUNK IS ALLOWED, AND SAYING SO IS THE FIX FOR A SILENTLY INERT TEST.
 * `RouteResult` alone excluded `Promise<RouteResult>`, so a handler written
 * `async () => { await gate; return … }` type-errored at the call site — and the one
 * test that needed it silenced that with `as Record<string, RouteEntry>` rather than
 * being told it was unsupported. `stubFetchRoutes` then did not await the thunk:
 * `resolved` was the pending Promise, `resolved.status` was `undefined` (so 200) and
 * the stub answered IMMEDIATELY. The gate blocked nothing, and the regression guard
 * built on it passed with the defect it was written to catch reintroduced. A route
 * that means to hold a response open must be able to, and must be able to say so in
 * the type.
 */
export type RouteEntry =
  | StubbedRoute
  | ((init?: RequestInit) => RouteResult | Promise<RouteResult>);

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
    //
    // `await` is load-bearing, not defensive. Without it an async thunk's Promise WAS
    // the descriptor: every field read off it was `undefined`, so the stub replied 200
    // with an undefined body the instant it was called, and a test holding a response
    // open to assert ordering was asserting nothing. `await` on a non-Promise is a
    // no-op, so the synchronous thunks (the conditional-GET sequencers) are unaffected
    // in value — they now resolve a microtask later, which no assertion depends on
    // because every caller already awaits through `waitFor`/`findBy*`.
    const resolved: RouteResult = typeof hit === 'function' ? await hit(init) : hit;
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

/**
 * A synthetic worked-example session id, shaped like the real thing.
 *
 * The backend mints these with `secrets.token_urlsafe(16)` and validates them
 * against `^[A-Za-z0-9_-]{16,64}$`, so a fixture id must satisfy that pattern —
 * a test that used a friendly string like `'test-session'` (12 chars) would be
 * rejected as malformed by the real API and would prove nothing about the path
 * it claims to cover.
 */
export const TUTORIAL_SESSION_ID = 'fixtureSessionId0000000';

/**
 * The two worked-example session routes, for any test that starts the
 * walkthrough.
 *
 * Needed because starting is no longer a UI-only act: it opens a server-side
 * session, and the fetch stub throws on an unrouted call — so a tutorial test
 * without these routes exercises the CREATE-FAILED path rather than the
 * walkthrough, which is a real state but not the one it means to assert.
 *
 * `record_ids` deliberately echoes the canonical five: the backend materialises
 * exactly those inside a new session, and the walkthrough resolves its targets
 * from the list it then reads.
 */
export function tutorialSessionRoutes(
  sessionId: string = TUTORIAL_SESSION_ID,
): Record<string, StubbedRoute> {
  return {
    'POST /api/tutorial/sessions': {
      status: 201,
      body: {
        session_id: sessionId,
        record_ids: [...CANONICAL_RESET_IDS],
        ttl_hours: 24,
      },
    },
    [`DELETE /api/tutorial/sessions/${sessionId}`]: { status: 204, body: undefined },
  };
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
  // P4 — nulls because nothing was exported, NOT because a file went missing.
  artifact: { state: 'none' as const, reason: null },
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

/**
 * The shared scientific title base every canonical seed carries.
 *
 * MUST equal `workspace._SEED_TITLE_BASE`. It had drifted: this file held
 * `'Synthetic XANES — CuO (Cu K-edge)'` while the backend had already been renamed
 * to `'XANES Example — CuO (Cu K-edge)'`, and nothing caught it — the frontend suite
 * cannot import Python, and the backend suite did not read this file. Pinned now
 * from the side that can see both, by
 * `apps/api/tests/test_seed_fixture_parity.py`.
 */
export const RESET_TITLE_BASE = 'XANES Example — CuO (Cu K-edge)';

/** The five derived scenario labels the API serves for the canonical seed ids
 * (mirrors `workspace.SEED_SCENARIOS`; derived server-side, never stored). Each
 * names how that fixture was MATERIALISED at setup, in the past tense, so a later
 * mutation cannot falsify it.
 *
 * These had drifted too, to a retired `'Scenario N · seeded: …'` wording — the
 * development jargon the backend replaced with `'Example N · at setup: …'`. Pinned
 * by the same backend test as the title base above. */
export const CANONICAL_SCENARIO_LABELS = [
  'Example 1 · at setup: extraction only',
  'Example 2 · at setup: some answers confirmed',
  'Example 3 · at setup: all answers confirmed',
  'Example 4 · at setup: descriptor uncertainty omitted',
  'Example 5 · at setup: export run',
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

/** R1 — the plan digest a preview returns and an execute must carry back. Opaque and
 *  shape-faithful to `workspace._plan_digest` ("rp1." + 32 lowercase hex). */
export const RESET_PLAN_DIGEST = 'rp1.0f1e2d3c4b5a69788796a5b4c3d2e1f0';
/** A DIFFERENT digest — what a preview returns after the workspace has moved on. */
export const RESET_PLAN_DIGEST_FRESH = 'rp1.a1b2c3d4e5f60718293a4b5c6d7e8f90';

/** R1 — a workspace with no operator progress at all (the post-reset baseline). */
export const RESET_AT_RISK_NONE = {
  confirmed_answers: 0,
  examples_with_progress: 0,
  exported_artifacts: 0,
};
/** R1 — a workspace someone has actually worked in. */
export const RESET_AT_RISK_SOME = {
  confirmed_answers: 3,
  examples_with_progress: 2,
  exported_artifacts: 1,
};

/** POST /api/demo/reset {mode:'preview'} — 5 canonical + 2 legacy present, 0 ambiguous. */
export const demoResetPreviewClean = {
  status: 'ok' as const,
  mode: 'preview' as const,
  refusal_reason: null,
  previous_count: 7,
  canonical_count: 5,
  legacy_count: 2,
  ambiguous_count: 0,
  removed_count: 0,
  final_count: 5,
  canonical_ids: CANONICAL_RESET_IDS,
  removable: LEGACY_REMOVABLE,
  state_counts: RESET_STATE_COUNTS,
  plan_digest: RESET_PLAN_DIGEST,
  at_risk: RESET_AT_RISK_SOME,
};

/** POST /api/demo/reset {mode:'execute', confirmation:RESET_CONFIRMATION} — success. */
export const demoResetExecuteOk = {
  ...demoResetPreviewClean,
  mode: 'execute' as const,
  previous_count: 7,
  removed_count: 2,
  final_count: 5,
  plan_digest: RESET_PLAN_DIGEST_FRESH,
  at_risk: RESET_AT_RISK_NONE,
};

/** Preview when an ambiguous (unmanaged) record is present — refused (HTTP 200). */
export const demoResetPreviewAmbiguous = {
  status: 'refused' as const,
  mode: 'preview' as const,
  refusal_reason: 'ambiguous_records_present' as const,
  previous_count: 8,
  canonical_count: 5,
  legacy_count: 2,
  ambiguous_count: 1,
  removed_count: 0,
  final_count: 8,
  canonical_ids: CANONICAL_RESET_IDS,
  removable: LEGACY_REMOVABLE,
  state_counts: RESET_STATE_COUNTS,
  plan_digest: RESET_PLAN_DIGEST,
  at_risk: RESET_AT_RISK_SOME,
};

/** R1 — the stale-precondition refusal (HTTP 412). Nothing was written; the body
 *  carries the CURRENT digest and refreshed figures, which is what lets the dialog
 *  explain what changed instead of reporting a failure. */
export const demoResetExecuteStale = {
  ...demoResetPreviewClean,
  status: 'refused' as const,
  mode: 'execute' as const,
  refusal_reason: 'plan_digest_stale' as const,
  previous_count: 8,
  legacy_count: 3,
  removed_count: 0,
  final_count: 8,
  plan_digest: RESET_PLAN_DIGEST_FRESH,
  at_risk: { confirmed_answers: 4, examples_with_progress: 2, exported_artifacts: 1 },
};

/** R1 — the missing-precondition refusal (HTTP 428). */
export const demoResetExecuteDigestRequired = {
  ...demoResetPreviewClean,
  status: 'refused' as const,
  mode: 'execute' as const,
  refusal_reason: 'plan_digest_required' as const,
  removed_count: 0,
  final_count: 7,
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
    /**
     * R1: applies to the EXECUTE only, never to the preview that precedes it. The
     * two used to share one `status`, which made it impossible to stub the case that
     * matters most — a 200 preview followed by a 412 execute — without also breaking
     * the preview the dialog needs in order to open at all.
     */
    executeStatus?: number;
    /** Body for the SECOND and later executes (a re-attempt after a stale refusal). */
    executeRetry?: unknown;
    /** Body for the SECOND and later previews (the refreshed figures after a stale
     *  refusal). Defaults to the first preview body. */
    previewRefresh?: unknown;
  } = {},
): { routes: Record<string, RouteEntry>; flipToFive: () => void } {
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
  // same METHOD+path. R1 made the sequence longer than "1st then 2nd": a stale
  // refusal is followed by ANOTHER preview (the refresh) and possibly another
  // execute. So the stub branches on the request BODY's `mode` rather than on call
  // order, which is both more faithful to the real backend and immune to a component
  // that legitimately previews more than once.
  const previewBody = opts.preview ?? demoResetPreviewClean;
  const previewRefreshBody = opts.previewRefresh ?? previewBody;
  const executeBody = opts.execute ?? demoResetExecuteOk;
  const executeRetryBody = opts.executeRetry ?? executeBody;
  let previews = 0;
  let executes = 0;
  const routes: Record<string, RouteEntry> = {
    'GET /api/health': { body: { ...healthSynthetic, mode: opts.mode ?? 'synthetic-only' } },
    'GET /api/experiments': {
      body: () => ({
        experiments: five ? canonicalFiveSummaries : [...canonicalFiveSummaries, ...legacySummaries],
      }),
    },
    'POST /api/demo/reset': (init?: RequestInit) => {
      const mode = (JSON.parse(String(init?.body ?? '{}')) as { mode?: string }).mode;
      if (mode === 'execute') {
        executes += 1;
        const status = opts.executeStatus ?? 200;
        // Only a 200 execute actually reset anything, so only a 200 flips the list.
        if (status === 200) five = true;
        return { status, body: executes === 1 ? executeBody : executeRetryBody };
      }
      previews += 1;
      return { status: 200, body: previews === 1 ? previewBody : previewRefreshBody };
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
 *  If-Match token for the next submit.
 *
 *  `invalidation` is part of the response the real handler ALWAYS sends
 *  (`routes.py::post_answers` sets `result["invalidation"]` unconditionally, and
 *  `ApiAnswersResponse.invalidation` is non-optional), and it is what tells a client
 *  whether the answer was applied at all — a 200 does not, since
 *  `_answers_to_apply_shape` drops what it cannot interpret. This fixture omitted it,
 *  so it modelled an APPLIED answer with a response shape the server never sends. */
export const answersAfterNotebook = {
  pending: pendingResponse.pending.slice(1),
  status: 'needs_attention',
  rev: 4,
  updated_utc: '2099-04-02T09:16:00Z',
  version: '1.1',
  workflow: fixtureWorkflow({
    pending_count: pendingResponse.pending.length - 1,
    draft_ok: false,
    ready: false,
    exported: false,
    rev: 4,
  }),
  invalidation: {
    changed: true,
    rev: 4,
    changed_fields: [pendingResponse.pending[0].id],
    reopened_steps: [],
    artifact: { state: 'none' as const, reason: null },
    reason: 'Updated 1 field(s); no downstream steps reopened.',
  },
};

/** POST /answers response for an answer the backend DROPPED: 200, the blocker still
 *  open in the recomputed list, `rev` unmoved and `changed:false`. This is what
 *  `_answers_to_apply_shape` (unrecognised key) or `apply_answers` (malformed sha256,
 *  wrong-typed structured value, off-enum qc) actually produces — `rev` equals the
 *  loaded fixture's `rev 3`, and `pending` is returned intact.
 *
 *  NOTE the `reason`: the backend words its no-op reason as "the submitted value was
 *  identical", which is NOT what happened here. It is shared with /edit and /export
 *  and is pinned as known-wrong-but-unchanged by
 *  `apps/api/tests/test_export_recovery.py:1361`, so it is reproduced verbatim — a
 *  client must not render it. */
export const answersDropped = {
  pending: pendingResponse.pending,
  status: 'needs_attention',
  rev: 3,
  updated_utc: '2099-04-02T09:16:00Z',
  version: '1.0',
  workflow: fixtureWorkflow({
    pending_count: pendingResponse.pending.length,
    draft_ok: false,
    ready: false,
    exported: false,
    rev: 3,
  }),
  invalidation: {
    changed: false,
    rev: 3,
    changed_fields: [],
    reopened_steps: [],
    artifact: { state: 'none' as const, reason: null },
    reason: 'No change — the submitted value was identical; nothing was invalidated.',
  },
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
    artifact: { state: 'none' as const, reason: null },
    reason: 'Updated 1 field(s); no downstream steps reopened.',
  },
};

/** POST /edit response for a correction `apply_corrections` REFUSED — the shape a
 *  malformed sha256 actually produces. The key was recognised (an unrecognised one is
 *  a 422, not this), so the request reaches `apply_corrections`, which "never
 *  overwrit[es] with a bad value": the draft does not move, `rev` stays put and
 *  `changed` is false. `pending` is unchanged because `apply_corrections` never
 *  touches it, which is exactly why it carries no signal on this path.
 *
 *  The same shape is what an IDENTICAL re-submit produces. The response cannot tell
 *  the two apart, and its `reason` asserts the second for both — reproduced verbatim
 *  so a test can prove the client never renders it. */
export const editRefused = {
  // `apply_corrections` never touches `pending`, so a refusal returns the SAME list the
  // record already had. Paired with `answersAfterNotebook` (which resolves the first of
  // the five blockers) that is the remaining four — not `[]`. The distinction is
  // load-bearing: an empty list would put the screen into its all-resolved branch,
  // which is a different render tree, and a correction that was refused must not move
  // the record to "ready".
  pending: pendingResponse.pending.slice(1),
  status: 'needs_attention',
  rev: 4,
  updated_utc: '2099-04-02T09:18:00Z',
  version: '1.1',
  workflow: fixtureWorkflow({
    pending_count: pendingResponse.pending.length - 1,
    draft_ok: false,
    ready: false,
    exported: false,
    rev: 4,
  }),
  invalidation: {
    changed: false,
    rev: 4,
    changed_fields: [],
    reopened_steps: [],
    artifact: { state: 'none' as const, reason: null },
    reason: 'No change — the submitted value was identical; nothing was invalidated.',
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
  // P4 — both files read cleanly and match the current draft.
  artifact: { state: 'current' as const, reason: null },
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
        artifact: { state: 'current' as const, reason: null },
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
        artifact: { state: 'current' as const, reason: null },
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

/**
 * The FAN-OUT shape: `exported: true` beside a null singular `record_id` and a null
 * `artifact_refs` pair, which every other `exported: true` fixture pairs with a
 * non-null id.
 *
 * That gap is why two screens shipped rendering the literal string `null`
 * (`Exported · null`, `null.json`, `null.evidence.json`) with a full green suite: no
 * fixture in this file could produce the combination, so no test could see it. The
 * backend produces it for a record whose runs each export their own official record.
 *
 * `reason` is the server-authored explanation the screens render in place of the two
 * artifact cards; it is what `routes.FAN_OUT_ARTIFACT_REASON` serves.
 */
export const FAN_OUT_REASON =
  "This record's runs each export their own official record, so there is no single record file. The export response lists each run's record and sidecar filename; no read operation lists them yet.";

export function fanOutExportedRoutes(id: string = EXP_ID): Record<string, StubbedRoute> {
  const base = `/api/experiments/${encodeURIComponent(id)}`;
  return {
    ...bundleRoutes(id),
    [`GET ${base}`]: {
      body: {
        ...experimentDetail,
        id,
        status: 'done',
        pending_count: 0,
        exported: true,
        // SINGULAR fields, and this record has several of each.
        record_id: null,
        artifact_refs: {
          record_filename: null,
          sidecar_filename: null,
          reason: FAN_OUT_REASON,
        },
        workflow: fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: true, rev: VERSION_FIELDS.rev }),
        artifact: { state: 'current' as const, reason: null },
      },
    },
    [`GET ${base}/pending`]: { body: { pending: [] } },
    [`POST ${base}/validate`]: { body: validateExported },
    [`POST ${base}/audit`]: { body: auditExported },
    [`GET ${base}/warnings`]: { body: warningsDryRun },
    [`GET ${base}/evidence-classification`]: { body: evidenceClassificationResponse },
    [`GET ${base}/evidence`]: { body: evidenceResponse },
    [`GET ${base}/draft`]: { body: draftResponse },
    // The experiment's OWN pair does not exist; `/artifacts` says so rather than
    // reporting `none`, and its `artifact.state` is `current` (measured backend-side).
    [`GET ${base}/artifacts`]: {
      body: {
        record: null,
        sidecar: null,
        record_filename: null,
        sidecar_filename: null,
        artifact: { state: 'current' as const, reason: null },
        reason: FAN_OUT_REASON,
      },
    },
    'GET /api/graph/status': { body: graphStatusUnavailable },
  };
}

/** The two run record ids a fan-out export writes, shaped like real ULIDs. */
export const FAN_OUT_RUN_IDS = ['01JQZ0FIXTURERUNONE000001', '01JQZ0FIXTURERUNTWO000001'];

/**
 * The FAN-OUT EXPORT RESPONSE — the SUCCESS one, which is the shape no fixture in
 * this file could produce before.
 *
 * `routes.post_export` POPS `record` and `sidecar` for a fan-out and nulls both
 * singular fields, while `ok` stays true; `records[]` carries what was written. The
 * screen tested `resp.ok && resp.record && resp.sidecar` and therefore routed a
 * SUCCESSFUL export — N immutable official ISAAC records on disk — to its `failed`
 * phase, which says "nothing was written".
 */
export const fanOutExportSuccess = {
  ok: true,
  draft_report: { ok: true, errors: [], warnings: [] },
  official_report: { ok: true, errors: [] },
  record_id: null,
  artifact_refs: null,
  records: FAN_OUT_RUN_IDS.map((runId, i) => ({
    run_id: runId,
    run_label: `Run ${i + 1}`,
    record_id: runId,
    record_filename: `${runId}.json`,
    sidecar_filename: `${runId}.evidence.json`,
  })),
  pruned_record_ids: [],
  protected_record_ids: [],
  prune_declined: false,
  rev: 4,
  updated_utc: '2099-04-02T09:20:00Z',
  version: '2.0',
};

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
    title: 'ISAAC Metadata Assistant API',
    version: '0.1.0',
    // Verbatim from `apps/api/isaac_api/app.py` (Slice 2A; title + summary
    // re-synced by P1, which dropped the false "local" from the hosted title).
    summary:
      'FastAPI wrapper over the deterministic isaac_records core: a synthetic-only workspace, isolated worked-example sessions holding the built-in example records, and one read-only, aggregate-only database diagnostic.',
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
 * Regenerated on 2026-07-31, re-measured 2026-08-06, FULLY RE-TRANSCRIBED
 * 2026-08-07, with:
 *
 *   PYTHONPATH=apps/api .venv/bin/python -c \
 *     "from isaac_api.app import create_app; import json; \
 *      print(json.dumps(create_app().openapi()))"
 *
 * 40 operations · 61 post-lead paragraphs · lead paragraphs 78–548 characters ·
 * remainders 0–2,223. The newest is `POST /api/experiments`, the first
 * record-creation operation this API has published; before it came
 * `GET /api/runtime/verification` and the worked-example session lifecycle
 * (`POST /api/tutorial/sessions`, `DELETE /api/tutorial/sessions/{session_id}`).
 *
 * THE 2026-08-07 RE-TRANSCRIPTION WAS A REPAIR, AND SAYING SO IS THE POINT.
 * A merge resolved by "keep both sides" left `GET /api/runtime/verification` and
 * `GET /api/health` in this array TWICE EACH — 42 entries for 40 operations — and
 * the guard in `settings-api.test.tsx` was then RAISED to 42 / 32,174 / 67 to
 * match, each number honestly measured from the broken array. Both directions of
 * `apps/api/tests/test_contract_description_parity.py` are blind to a duplicate
 * (one looks each entry up in the spec; the other compares SETS), so nothing
 * failed. `settings-api.test.tsx` now also asserts `contains each operation
 * exactly once`. If you are about to raise a number in that file, check FIRST
 * that the array it measures is well-formed.
 *
 * TWO CHARACTER COUNTS, DIFFERING BY EXACTLY THE SEPARATORS, and this comment
 * used to state one of them unlabelled — which is how it drifted 675 characters
 * from the assertion it looks like it describes:
 *
 *   · 29,052 — `lead.length + rest.join('').length` after `splitPurpose` has
 *     consumed the blank lines. THIS is what `settings-api.test.tsx` pins.
 *   · 29,174 — the raw `description.length` sum, i.e. the same text plus the 61
 *     `\n\n` separators (61 x 2 = 122).
 *
 * Quote the metric with the number, or the next reader re-measures the other one
 * and concludes the fixture is stale when it is not.
 *
 * THE "POINT-IN-TIME COPY" CAVEAT BELOW IS NOW WEAKER THAN IT READS, and that is
 * worth stating rather than leaving as a stale warning. Since
 * `apps/api/tests/test_contract_description_parity.py` this array IS checked
 * character-for-character against the generated document in both directions — a
 * changed description and a NEW operation both fail CI. The counts in this comment
 * are still hand-measured and can go stale; the strings themselves cannot.
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
  { op: "GET /api/runtime/verification", description: "Aggregate results of three programs run over a corpus of official ISAAC records: official schema validation, a stricter format-aware shadow validation, and a deterministic mutation harness that deep-clones each record before mutating it. **Which** corpus is selected by `mode`, and a completed report names it in `metadata.verification_mode`.\n\nAggregate only. No record id, title, field value, evidence entry or per-record outcome appears, and every histogram is projected through a minimum-cell-size floor so a category with few occurrences is withheld rather than named.\n\n**Two corpora, selected by `mode`. A completed report names the one it read; a status envelope (`running`, `refused`, `unavailable`, `error`) carries no `metadata` at all, so it names no corpus and reports no figures.**\n\n* `public_reference` (default) — the ten public upstream ISAAC example records vendored in this repository. Already published, so reading them needs no approval, and a run in `public_reference` mode does not open a database connection to reach them.\n* `authorized_private_sample` — a bounded, read-only, aggregate-only pass over the records this application holds in its own datastore, under the approval recorded on 2026-08-05. This mode **does** open one short-lived read-only connection — to whatever host the process's own libpq environment names, which in the deployed configuration is the in-cluster database reached from the pod. Nothing on this path checks where the process is running; that it runs in the pod is how the deployment is configured, not something this operation enforces. Each record is deep-copied in memory, mutated only as a copy, and discarded; no identifier, title, field value, evidence entry or per-record outcome is retained or returned.\n\nAn unknown mode is **refused**, never silently served the other one. For the private mode the two failure words are not interchangeable, and each has its own cause. `refused` means an environment gate rejected the run before anything was opened — in practice that `PGDATABASE` is not exactly the expected database name, and absent counts as not exactly. `unavailable` means that gate passed but no connection was obtained: the driver would not import, or one of the remaining libpq connection variables (`PGHOST`, `PGUSER`, or the credential variable beside them) is missing or empty, or the attempt itself failed. So a deployment with `PGDATABASE` set and `PGHOST` unset reports `unavailable`, not `refused`.\n\nThe sweep runs off the request path. The first call returns `running`; poll until `status` is `ok`." },
  { op: "GET /api/health", description: "Liveness banner for platform and container probes: the service status, the runtime data mode, the name of the deterministic core package the app calls in process, the app version, and the build commit when the deployment supplies one (otherwise `null` — it is never guessed). This is the one operation that stays reachable without credentials when the deployment enables authentication. Read-only.\n\nIt also states whether this deployment has an application database configured, how that database is classified, whether hosted display of its per-record content is open, and the outcome of the most recent reconnaissance scan in this process. That block is derived from configuration alone: this operation never opens a database connection, issues a query, or waits on one, so a database problem can never change its result and can never fail a container probe.\n\nIt states, in `experiment_storage`, whether an experiment created here is stored durably, stored only for as long as this server runs, or not being stored at all because a database this deployment is configured to use is not answering. The first two are read from configuration. The third is an observation, recorded when a real read or write against that database failed — so this operation still opens no connection of its own, and it reports what has already happened rather than testing anything now." },
  // RE-TRANSCRIBED from `create_app().openapi()` after both descriptions were
  // corrected: the `X-Isaac-Tutorial-Session` REQUIREMENT was stated only in each
  // operation's `409` sub-description, and `/demo/reset` said "the workspace"
  // throughout for a scope it cannot reach (it refuses when `scope is None`, and
  // `reset_to_canonical_seed(session_id=scope)` only ever addresses
  // `scope_root(scope)`). `apps/api/tests/test_contract_description_parity.py` compares
  // these strings byte for byte against the served document, so the two sides were
  // updated together.
  { op: "POST /api/demo/run", description: "REQUIRES the `X-Isaac-Tutorial-Session` header. The built-in example records are created only inside a worked-example session, so without one there is nothing for this operation to run over: it refuses with `409` (`tutorial_scope_required`) and writes nothing. Everything below describes what it does inside the session that header names — it addresses no other scope, and it can neither read nor write a record in the ordinary workspace.\n\nRuns the committed worked-example pipeline and returns the ordered steps it executed together with the resulting experiment id and status. `mode: \"draft_only\"` (the default) extracts a draft from the committed reference files and runs the no-guessing draft checks; `mode: \"full\"` additionally applies the committed simulated answers and exports an official record. It targets one fixed canonical experiment id per mode, so re-running never adds a record and never increases that session's record count. It reads only the two committed reference files and accepts no uploaded data.\n\nIt never overwrites your work. The target must still hold exactly its original example content: when it does, running the pipeline would reproduce that content byte for byte, so nothing at all is written and the record's version is untouched. If the target has been changed — an answer confirmed, a field edited, a record exported — the run is refused with `409` and nothing is written.\n\nA body other than `draft_only` or `full` for `mode` is rejected and nothing runs." },
  { op: "POST /api/demo/reset", description: "REQUIRES the `X-Isaac-Tutorial-Session` header, and refuses with `409` (`tutorial_scope_required`) without one, mutating nothing. Everything it classifies, reports and restores is the worked-example session that header names; it addresses no other scope and cannot remove, restore or modify a record in the ordinary workspace.\n\nRestores that session to exactly the five canonical built-in example records and reports the before/after counts, the removable set, a state histogram, and a derived summary of the confirmed work the reset would discard. `mode: \"preview\"` classifies only and mutates nothing; `mode: \"execute\"` additionally requires the exact confirmation phrase and the `plan_digest` the preview returned. It accepts no caller-supplied ids or paths — any extra field is rejected — it removes only records it can classify as records this application itself created, and it refuses to remove anything at all if any record is ambiguous. No filesystem path appears in the response.\n\n**The `plan_digest` precondition.** `preview` returns an opaque digest of the session it classified. `execute` must send it back, and the reset runs only if that session still matches it. Without this, a client that previewed, showed a confirmation dialog, and executed a while later would destroy anything committed in between — the operator would have approved a classification that no longer held. A missing digest is `428` and mutates nothing; a stale one is `412`. Every response carries the CURRENT digest, so a `412` can be recovered from in one further request.\n\nThe digest is also re-checked PER RECORD, inside that record's own lock and immediately before it is touched, because a per-record write can otherwise land between the first check and the mutation. A write in that window is therefore never destroyed: the reset refuses instead. That is the one refusal that can leave earlier records already reset, and the response's measured counts say so — see the `412` description.\n\nThere is deliberately no general per-experiment delete operation." },
  { op: "GET /api/experiments", description: "One summary row per experiment currently in the workspace: its id, title, derived status, creation time, how many blocking questions are still open, how many fields carry evidence, whether it has been exported, and the exported record id when there is one. Rows for the five built-in example records also carry a derived, never-stored `scenario` label naming which example the row is; it is null for any other record. Read-only, and it states no validity verdict." },
  { op: "POST /api/experiments", description: "Creates a new, empty experiment in the ordinary workspace and returns its full detail bundle, so a client can go straight to it.\n\nIt takes a title and an optional note, and nothing else. No scientific value is invented: the new record starts with every scientific field genuinely empty and with the blocking questions an ISAAC record has to answer already open, which is what the guided completion workflow then works through. The record id is always minted by the server — a caller-supplied id is rejected, as is any other unrecognised field.\n\nIt refuses with `409` when the `X-Isaac-Tutorial-Session` header is present, and writes nothing. A worked-example session is temporary and is discarded on a timer; a record you created must not inherit that, and it must not be written into a workspace you are not currently looking at either.\n\nWhether the new experiment is stored durably depends on this deployment. `GET /api/health` reports which, in `experiment_storage`, and the reader is told the same thing before they create anything.\n\nWhere this deployment stores experiments in a database and that database does not accept the write, the request fails with `503` and nothing is created. It is never quietly written somewhere temporary instead: you have been told your work is kept, and a create that could not keep it says so rather than looking like it succeeded." },
  { op: "GET /api/experiments/{experiment_id}", description: "The full detail bundle for one experiment: its summary row plus whether the draft passes the no-guessing checks, the exported artifact filenames (basenames only, never a server path), the source files it was extracted from, the derived workflow progression, the exported-artifact freshness state, and the current revision metadata.\n\nThe response carries the record's current `ETag`. Send it back as `If-None-Match` to receive `304` while the record is unchanged. Read-only." },
  { op: "GET /api/experiments/{experiment_id}/draft", description: "This record's draft fields, grouped into the stable sections the record review screen renders. Each field carries its label, official path, current value, the status derived from its evidence, and the kinds of source that evidence came from. Read-only; the response carries the record's current `ETag`." },
  { op: "GET /api/experiments/{experiment_id}/pending", description: "The questions that are still blocking this draft, each with the stable key an answer must be submitted under, what the question is about, and — for the built-in examples only — a clearly labelled suggested answer that is never applied automatically. Read-only; the response carries the record's current `ETag`." },
  { op: "POST /api/experiments/{experiment_id}/answers", description: "Applies caller-supplied answers to this draft's open blocking questions and returns the refreshed question list, the record's status, its new revision metadata, the derived workflow, and which downstream steps the change reopened.\n\nRequires `confirmed_by_user: true` and the record's current `ETag` in `If-Match`. Blank and unrecognised answers are dropped rather than invented, so a submission that changes nothing is a no-op: it is not logged and does not advance the revision." },
  { op: "POST /api/experiments/{experiment_id}/edit", description: "Overwrites the current value of a field that has already been answered, recording a fresh user confirmation, and returns the same refreshed bundle as the answers operation.\n\nRequires `confirmed_by_user: true` and the record's current `ETag` in `If-Match`. A body that names no recognised editable field is rejected with `422` rather than silently doing nothing, and a value that fails the core's own checks leaves the stored value unchanged. It never reopens or creates a blocking question." },
  { op: "POST /api/experiments/{experiment_id}/export", description: "Runs the schema-gated export for this record. On success it writes the official ISAAC record and its evidence sidecar into the workspace and returns the record id, the two artifact filenames (basenames only, never a server path), the refreshed revision metadata, the workflow, and the downstream invalidation.\n\nA record with **runs** exports one official record per run (`record_id = run.id`), not one per record. In that case `record_id` and `artifact_refs` are `null` — they are singular and a fan-out has several — and `records[]` carries one entry per run instead. A record with no runs, which is every record this API can currently create, exports exactly one record with `record_id` equal to its own id, unchanged.\n\n**What is guaranteed if something fails part-way.** Every run is validated before any file is written, so a validation failure on one run means no file is written for any of them. The state is saved once, after every file. It is NOT atomic across the individual file writes: a fault between them can leave some records on disk with the state still saying they were not exported. That is the same half-written shape a single-record export has always been able to produce, and the same repair applies — retry the export and every not-yet-exported run is republished from its current draft.\n\nA gated failure also returns `200`, with `ok: false`, the failing draft and official reports, and a flat `errors` list — decide by reading `ok`, not the status code. With runs, `runs[]` carries each run's own verdict and `failed_run_ids` names the ones that refused. Nothing is written in that case.\n\n**What happens to the records of runs that have been removed.** When a record with runs exports, artifact pairs in its own records directory that no current run claims are removed, and `pruned_record_ids` names them. Two things stop that removal, and they are reported separately because an empty `pruned_record_ids` would otherwise mean three different things. A pair a surviving record still links to is kept and named in `protected_record_ids` — records are immutable, so removing it would leave that link pointing at nothing. And if a record being kept cannot be read at all, nothing is removed and `prune_declined` is `true`, because a record whose links are unknown may reference anything.\n\nRequires the record's current `ETag` in `If-Match`. Exported records are immutable: exporting a record whose runs have all already been exported is refused, and a run that is already exported is never rewritten when a sibling run is exported alongside it. An export is also refused with `sibling_link_conflict` when it would rewrite a record that an already-exported record links to as sharing its sample id, with a different sample id — the link could not be corrected afterwards, so one of the two records would be false. Nothing is written in that case." },
  { op: "POST /api/experiments/{experiment_id}/ingestion/csv/preview", description: "Read-only preview of a campaign-sheet CSV, reconciled field by field against this record's current authoritative values. Returns the row and candidate counts, the mapped candidate fields with their reconciliation outcome, and non-actionable warnings for unrecognised columns.\n\nSend the CSV as a raw `text/csv` request body, not as a multipart form. The body is read in memory under a hard size limit and is never written anywhere: no draft change, no revision bump, no export, no indexing, and no retained upload. Only outcome metadata is logged — never the rows, the candidate values, or the filename.\n\nRequires the record's current `ETag` in `If-Match`, which is checked before the body is read. Available only while the deployment is in synthetic-only data mode.\n\nA malformed CSV — unreadable, an empty or duplicated header column, a missing required column, or a row, column, cell, or candidate count over the limit — is rejected with `422` and a stable error code." },
  { op: "POST /api/experiments/{experiment_id}/validate", description: "Checks this record against the vendored official ISAAC schema and returns `ok`, a list of `{path, message}` errors, the schema label, and whether the check was a dry run.\n\nFor an already-exported record the written record is validated (`dry_run: false`). Otherwise the export is run in memory and the resulting candidate record is validated without writing anything (`dry_run: true`). Read-only in both cases. The verdict comes from the same deterministic core function the command line uses.\n\nA record with **runs** exports one official record per run, so it is checked per run: `runs[]` carries each run's own verdict, its errors and its own `dry_run`, and the top-level `ok` is true only when every run passes. The top-level `dry_run` is `true` if any run's verdict came from an in-memory candidate rather than a written record.\n\nIf the written record cannot be read at all, no verdict is invented: the operation reports `ok: false` with the single fixed error `Validation could not be completed.` and `dry_run: false`. Read that as *no verdict*, not as a schema violation — the artifacts operation reports why the file could not be read." },
  { op: "POST /api/validate/record", description: "Standalone validator for a candidate official ISAAC record supplied directly as a JSON request body — no experiment, no draft, and no workspace involved. Returns `ok`, a rendered summary line, the `{path, message}` errors, and the schema version checked against.\n\nIt calls the same authoritative validator over the same vendored schema that the per-experiment validation operation uses, so the two verdicts agree by construction. The body is never written anywhere and its content is never logged; only the outcome and error count are.\n\nSend the record as a raw JSON body. The body is read in memory under a hard size limit." },
  { op: "POST /api/experiments/{experiment_id}/audit", description: "Runs the deterministic audit over the official record and evidence sidecar this record's export wrote, returning the per-record official-schema report, its evidence-coverage counts, and the rendered text report.\n\nA record that has not been exported yet returns `200` with no rows and a message saying so, rather than an error. Read-only." },
  { op: "GET /api/experiments/{experiment_id}/warnings", description: "Advisory, non-gating warnings for this record. For an already-exported record the written record is checked (`dry_run: false`); otherwise — including when that written record cannot be read — the in-memory export candidate is checked (`dry_run: true`). Always read `dry_run` to know which document the advice describes.\n\nThis channel deliberately carries no pass, fail, or validity field, and it never blocks an export — read it as advice for a human, alongside the official-schema verdict, not instead of it. The `GET` and `POST` forms are equivalent: both are read-only and return the same payload.\n\nA record with **runs** exports one official record per run, so it is advised on per run: `runs[]` carries each run's own warnings and its own `dry_run`. The top-level `warnings` is the deduplicated union over the runs — advice, unlike a verdict, is safe to aggregate — and the top-level `dry_run` is `true` if any run's advice came from an in-memory candidate rather than a written record." },
  { op: "POST /api/experiments/{experiment_id}/warnings", description: "Advisory, non-gating warnings for this record. For an already-exported record the written record is checked (`dry_run: false`); otherwise — including when that written record cannot be read — the in-memory export candidate is checked (`dry_run: true`). Always read `dry_run` to know which document the advice describes.\n\nThis channel deliberately carries no pass, fail, or validity field, and it never blocks an export — read it as advice for a human, alongside the official-schema verdict, not instead of it. The `GET` and `POST` forms are equivalent: both are read-only and return the same payload.\n\nA record with **runs** exports one official record per run, so it is advised on per run: `runs[]` carries each run's own warnings and its own `dry_run`. The top-level `warnings` is the deduplicated union over the runs — advice, unlike a verdict, is safe to aggregate — and the top-level `dry_run` is `true` if any run's advice came from an in-memory candidate rather than a written record." },
  { op: "GET /api/experiments/{experiment_id}/evidence", description: "The field-by-field evidence trail for this record: each official path, its value, the kind of support behind it, and the source file and locator cited.\n\nFor an already-exported record the trail is read from the evidence sidecar written alongside the official record; otherwise — including when that sidecar or record cannot be read — it is read from the draft's own evidence envelopes, which are the sidecar's own source. Read-only." },
  { op: "GET /api/experiments/{experiment_id}/evidence-classification", description: "Per-field evidence-support classification for this record's current state, plus a histogram over the five classes — `supported`, `inferred_candidate`, `insufficient_evidence`, `conflicting_evidence` and `unknown` — bound to the authoritative `record_rev` so a client can tell when its view is stale.\n\nThis carries the evidence-support axis only. It deliberately reports no validity, completion, exportability, or advisory verdict; those live in their own operations. Read-only, and it takes no lock." },
  { op: "GET /api/experiments/{experiment_id}/source-preview", description: "The text of one committed reference source file, line by line, together with the one-based line numbers this record's evidence actually cites in it. Read-only.\n\nOnly the two committed reference files may be previewed. A name containing a path separator or a traversal fragment is rejected, and any other filename is refused with the allowed names listed in the response. The file that cites fields rather than lines yields no cited line numbers, which is expected rather than an error." },
  { op: "GET /api/experiments/{experiment_id}/artifacts", description: "The official ISAAC record and the evidence-sidecar JSON that this record's export wrote, plus their filenames as bare basenames — never a server path.\n\nBoth files are resolved from the record id, never from a caller-supplied path. A record that has not been exported yet returns `200` with null payloads rather than an error. Read-only.\n\nA record with **runs** exports one official record per run and has no single pair of its own, so this operation returns null payloads for it together with a `reason` saying why. Those per-run files are not listed here yet." },
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
  { op: "POST /api/tutorial/sessions", description: "Creates an isolated worked-example workspace containing the five built-in example records, and returns its id together with the record ids actually materialised in it. Send that id as the `X-Isaac-Tutorial-Session` header on the record and example-workspace operations to work inside the session.\n\nThe examples exist only inside a session: the ordinary workspace contains none of them, and nothing here writes to it. Two sessions are completely independent — the same example record can be answered, edited and exported in one without being visible from the other.\n\nThe returned record ids are read back from the session that was just created, so they state what is there rather than what was intended. Each session expires after the reported number of hours; expired sessions are cleaned up whenever a new one is opened." },
  { op: "DELETE /api/tutorial/sessions/{session_id}", description: "Discards a worked-example session and everything in it, including any answers, edits and exported artifacts produced inside it. Nothing outside the session is touched.\n\nDiscarding a session that no longer exists succeeds: the outcome the caller asked for — that this session is gone — already holds, so repeating the request is safe and a client never has to know whether it is retrying. A malformed id is rejected instead, because it names no session at all." },
  { op: "GET /api/runtime/database/recon", description: "A sanitized, aggregate-only reconnaissance report over this deployment's own application database. It answers one question — do the stored records validate against the vendored official ISAAC schema — and reports the answer as counts.\n\nThe scan is strictly read-only, and no write is possible: the transaction is set AND verified read-only server-side, every statement is checked against a SELECT-only allowlist before it is issued, and values are always bound as parameters. The row count is also compared before and after, but that is a concurrency check rather than a mutation proof — a row-count equality cannot detect an update and cannot distinguish this scan's writes from a concurrent writer's, so it is the verified read-only transaction and the allowlist that carry the guarantee. The statement counters report every statement this service issues through a cursor; they are not a wire-level record, because the driver's own transaction framing never passes through one.\n\nThe response carries aggregates only: record totals, counts by type and domain, validation totals by rule family and by schema path, and the gate results. It never carries a record id, a title, a scientific value, a stored document, a connection detail, or a credential; per-record content stays closed. A serialized-output scan runs over every response shape before it is returned and replaces it with a sanitized failure if it trips. Every shape also carries a fixed `limitations` list saying what the gates cannot establish — in particular that the production-isolation gate is a tripwire rather than proof, and that the confirmed transport encryption does not verify the server certificate.\n\nWhen the deployment has no database configured, the operation reports that and connects to nothing. Repeat calls inside a short window are served from memory, and a scan already in progress is reported as a conflict rather than opening a second connection. The operation takes no parameters and no body." },
];

// --- Statistics dashboard fixtures (the five page-level reads) --------------
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
 * EXACTLY the five route keys the Statistics page requests, in the order the
 * page issues them. Exported so a test can assert the request set itself instead
 * of restating five literals it might mistype.
 */
export const STATISTICS_ROUTE_KEYS = [
  'GET /api/runtime/records',
  'GET /api/graph/status',
  'GET /api/about',
  'GET /api/openapi',
  'GET /api/schema',
] as const;

/**
 * The SIXTH read, kept OUT of `STATISTICS_ROUTE_KEYS` on purpose.
 *
 * Record Verification reads this once on mount and refreshes it with its own
 * Retry; the page's Refresh button deliberately does not re-issue it (see
 * `StatisticsPage.tsx`'s header). So the mount round is these six and the
 * Refresh round is the five above, and a single constant covering both would
 * hide exactly that distinction.
 */
export const STATISTICS_VERIFICATION_ROUTE_KEY = 'GET /api/runtime/verification';

/**
 * The Statistics page's five page-level reads plus the verification read, keyed
 * exactly as `lib/api` builds them.
 *
 * Any source may be replaced with any `RouteEntry`, which is how a test fails ONE
 * of them (`statisticsRoutes({ records: { status: 500, body: {} } })`) or
 * swaps in a different graph body, without disturbing the others.
 *
 * `schema` reuses `schemaBrowserFixture` — the same body the Schema Reference
 * suite browses — so the two screens are asserted against ONE document and a
 * count derived here can be checked against the fields that browser renders.
 */
export function statisticsRoutes(
  over: Partial<
    Record<
      'records' | 'graph' | 'about' | 'openapi' | 'schema' | 'verification',
      RouteEntry
    >
  > = {},
): Record<string, RouteEntry> {
  return {
    'GET /api/runtime/records': over.records ?? { body: statisticsRecordsBody },
    'GET /api/graph/status': over.graph ?? { body: graphStatusAvailable },
    'GET /api/about': over.about ?? { body: aboutResponse },
    'GET /api/openapi': over.openapi ?? { body: openApiFixture },
    'GET /api/schema': over.schema ?? { body: schemaBrowserFixture },
    [STATISTICS_VERIFICATION_ROUTE_KEY]: over.verification ?? { body: verificationReportOk },
  };
}

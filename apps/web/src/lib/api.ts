/*
 * Typed fetch client for the ISAAC FastAPI backend (apps/api).
 *
 * Thin client: it fetches server-derived truth (validation / coverage / advisory /
 * field status / evidence / status) and never computes any of it. Every verdict
 * comes from an endpoint; this module only parses envelopes and unwraps arrays.
 *
 * Base URL comes from `VITE_API_BASE` (default `http://127.0.0.1:8000/api`).
 * A network failure surfaces as an `ApiError` with `unreachable: true` so screens
 * can render the "Backend Not Running" state — never fabricated data.
 */

import type { RuntimeRecord } from './crossRecordTriage';
import type {
  ApiAnswersResponse,
  ApiArtifactsResponse,
  ApiAuditResponse,
  AssistantQueryResponse,
  ApiCsvPreview,
  ApiDraftResponse,
  ApiEvidenceClassification,
  ApiEvidenceEntry,
  ApiEvidenceResponse,
  ApiExperimentDetail,
  ApiExperimentSummary,
  ApiExportResponse,
  ApiGraphStatus,
  ApiHealth,
  ApiMemoryConceptResponse,
  ApiMemoryConceptsResponse,
  ApiMemoryFileResponse,
  ApiMemoryFilesResponse,
  ApiMemoryGraphResponse,
  ApiPendingResponse,
  ApiSearchResponse,
  ApiSearchScope,
  ApiSourcePreview,
  ApiDemoRunResponse,
  ApiDemoResetResult,
  ApiUploadsBlocked,
  ApiValidateResult,
  ApiWarningsResponse,
  EvidenceBundle,
  ExportReadinessBundle,
  RecordBundle,
} from './types';

const RAW_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://127.0.0.1:8000/api';

export const API_BASE = RAW_BASE.replace(/\/+$/, '');

/**
 * Optional shared-secret for the deployed demo backend. Read lazily per request
 * (not a module constant) so tests can stub the env. Unset locally → no header,
 * matching the auth-disabled local backend.
 */
function apiKey(): string | undefined {
  const key = (import.meta.env.VITE_API_KEY as string | undefined)?.trim();
  return key ? key : undefined;
}

/**
 * The exact phrase the backend requires to EXECUTE a synthetic-demo reset. Sent
 * verbatim on execute only; the operator types the shorter "RESET" gate in the UI
 * and never sees or re-types this phrase (no auto-fill of the typed gate).
 */
export const RESET_CONFIRMATION = 'RESET SYNTHETIC DEMO';

/** The exact command that starts the local backend (shown in the down state). */
export const RUN_COMMAND =
  '.venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000';

/** A fetch/HTTP failure. `unreachable` distinguishes "backend down" from an HTTP status. */
export class ApiError extends Error {
  readonly status?: number;
  readonly unreachable: boolean;
  /** The parsed error body, when the caller read it (e.g. the P27.5 412
   *  `stale_write` payload carrying `current_version`). Undefined otherwise. */
  readonly body?: unknown;

  constructor(
    message: string,
    opts: { status?: number; unreachable?: boolean; body?: unknown } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status;
    this.unreachable = opts.unreachable ?? false;
    this.body = opts.body;
  }
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const key = apiKey();
  try {
    return await fetch(`${API_BASE}${path}`, {
      ...init,
      // Thread the optional AbortSignal through so a caller (e.g. the P27.6 poller)
      // can cancel an in-flight request. `...init` already carries it, but we make
      // it explicit so the intent is obvious and existing callers stay unaffected.
      signal: init?.signal,
      headers: {
        Accept: 'application/json',
        ...(key !== undefined ? { Authorization: `Bearer ${key}` } : {}),
        ...(init?.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    });
  } catch {
    // Network-level failure (server not started, connection refused, CORS reject).
    throw new ApiError('The local backend is not reachable.', { unreachable: true });
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await request(path);
  if (!res.ok) throw new ApiError(`Request failed (${res.status}).`, { status: res.status });
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await request(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(`Request failed (${res.status}).`, { status: res.status });
  return (await res.json()) as T;
}

/**
 * Build the ApiError for a non-OK mutation response. On a 412 (`stale_write`) or
 * 400 (`malformed_if_match`) the JSON body is read and attached — it carries the
 * P27.5 conflict payload (`current_version`, `current_rev`, …) the screen needs.
 * A 409 (export immutability) and every other status keep the plain-error shape,
 * so existing callers (e.g. the export 409 branch) are unaffected.
 */
async function mutationError(res: Response): Promise<ApiError> {
  if (res.status === 412 || res.status === 400) {
    const body = await res.json().catch(() => undefined);
    return new ApiError(`Request failed (${res.status}).`, { status: res.status, body });
  }
  return new ApiError(`Request failed (${res.status}).`, { status: res.status });
}

const enc = encodeURIComponent;

export const api = {
  health(): Promise<ApiHealth> {
    return getJson<ApiHealth>('/health');
  },

  // S1 — the experiment queue.
  async listExperiments(): Promise<ApiExperimentSummary[]> {
    const body = await getJson<{ experiments: ApiExperimentSummary[] }>('/experiments');
    return body.experiments;
  },

  getExperiment(id: string): Promise<ApiExperimentDetail> {
    return getJson<ApiExperimentDetail>(`/experiments/${enc(id)}`);
  },

  // P27.6 — the client half of revision-aware live-sync. A conditional GET sends
  // the held ETag as `If-None-Match: "<version>"`; the backend answers 304 (no
  // body) when the record is unchanged or 200 + the fresh detail (+ new ETag)
  // when it changed. We call request() directly — getJson throws on any non-2xx,
  // and a 304 is deliberately non-ok. Branch on status: 304 → not changed; 200 →
  // changed, hand back the fresh detail (the caller decides whether to refetch);
  // anything else is a genuine error. A network failure from request() is already
  // an ApiError({unreachable:true}) and simply propagates. `signal` lets the
  // poller abort an in-flight check on unmount / record / version change.
  async checkRecordVersion(
    id: string,
    version: string,
    signal?: AbortSignal,
  ): Promise<{ changed: boolean; detail?: ApiExperimentDetail }> {
    const res = await request(`/experiments/${enc(id)}`, {
      headers: { 'If-None-Match': `"${version}"` },
      signal,
    });
    if (res.status === 304) return { changed: false };
    if (res.ok) return { changed: true, detail: (await res.json()) as ApiExperimentDetail };
    throw new ApiError('unexpected status', { status: res.status });
  },

  async getDraftGroups(id: string) {
    return (await getJson<ApiDraftResponse>(`/experiments/${enc(id)}/draft`)).groups;
  },

  async getPending(id: string) {
    return (await getJson<ApiPendingResponse>(`/experiments/${enc(id)}/pending`)).pending;
  },

  // S4 — apply a confirmed answer to one blocker. The user has explicitly
  // confirmed (`confirmed_by_user:true`); the backend recomputes and returns the
  // remaining pending list + fresh status. Never called for "leave missing".
  // P27.5: when a `version` token is threaded, it is sent as the optimistic-
  // concurrency `If-Match: "<version>"` header (byte-identical to the ETag). A
  // stale write returns 412 (or a malformed token 400) — the body carrying
  // `current_version` is read and attached to the thrown ApiError so the screen
  // can show the conflict; other non-OK statuses keep the plain-error behavior.
  async submitAnswer(
    id: string,
    answersById: Record<string, unknown>,
    version?: string,
  ): Promise<ApiAnswersResponse> {
    const res = await request(`/experiments/${enc(id)}/answers`, {
      method: 'POST',
      body: JSON.stringify({ answers: answersById, confirmed_by_user: true }),
      // Truthiness guard: never send an empty `If-Match: ""` for a blank token.
      ...(version ? { headers: { 'If-Match': `"${version}"` } } : {}),
    });
    if (res.ok) return (await res.json()) as ApiAnswersResponse;
    throw await mutationError(res);
  },

  // P28.3 — correct/re-confirm an ALREADY-answered field. Same wire shape and
  // optimistic-concurrency contract as submitAnswer (`{answers, confirmed_by_user}`
  // + `If-Match: "<version>"`), but hits POST /edit, which OVERWRITES the current
  // value (rather than filling a pending blocker) and returns the same
  // pending/status/version/workflow/invalidation bundle. A 412 stale write (or 400
  // malformed token) is thrown with the parsed body attached; an unchanged submit
  // is a backend-guaranteed no-op (200, invalidation.changed:false).
  async editField(
    id: string,
    answersById: Record<string, unknown>,
    version?: string,
  ): Promise<ApiAnswersResponse> {
    const res = await request(`/experiments/${enc(id)}/edit`, {
      method: 'POST',
      body: JSON.stringify({ answers: answersById, confirmed_by_user: true }),
      ...(version ? { headers: { 'If-Match': `"${version}"` } } : {}),
    });
    if (res.ok) return (await res.json()) as ApiAnswersResponse;
    throw await mutationError(res);
  },

  // P31.3 — CSV reconciliation preview (RECONCILIATION-ONLY). Uploads the raw
  // CSV text (Content-Type: text/csv) and reconciles every mapped value against
  // the CURRENT record; the backend NEVER mutates the record. Same optimistic-
  // concurrency contract as editField: `If-Match: "<version>"` is REQUIRED
  // (missing → 428). The header spread puts `Content-Type: text/csv` last so it
  // overrides request()'s default JSON content-type. Non-OK responses are thrown
  // via mutationError (identical error handling to editField).
  async previewCsv(
    id: string,
    csvText: string,
    opts: { version: string; filename?: string },
  ): Promise<ApiCsvPreview> {
    const res = await request(`/experiments/${enc(id)}/ingestion/csv/preview`, {
      method: 'POST',
      body: csvText,
      headers: {
        'Content-Type': 'text/csv',
        'If-Match': `"${opts.version}"`,
        ...(opts.filename ? { 'X-Filename': opts.filename } : {}),
      },
    });
    if (res.ok) return (await res.json()) as ApiCsvPreview;
    throw await mutationError(res);
  },

  // S6 — the schema-gated export. A 409 (record already exists) is thrown as an
  // ApiError(status:409); records are immutable and never overwritten. P27.5: a
  // threaded `version` is sent as `If-Match: "<version>"`; a 412 stale write (or
  // 400 malformed token) is thrown as an ApiError carrying the parsed body.
  async exportRecord(id: string, version?: string): Promise<ApiExportResponse> {
    const res = await request(`/experiments/${enc(id)}/export`, {
      method: 'POST',
      // Truthiness guard: never send an empty `If-Match: ""` for a blank token.
      ...(version ? { headers: { 'If-Match': `"${version}"` } } : {}),
    });
    if (res.ok) return (await res.json()) as ApiExportResponse;
    throw await mutationError(res);
  },

  // The three signals — each fetched from its own endpoint, never merged here.
  validate(id: string): Promise<ApiValidateResult> {
    return postJson<ApiValidateResult>(`/experiments/${enc(id)}/validate`);
  },

  audit(id: string): Promise<ApiAuditResponse> {
    return postJson<ApiAuditResponse>(`/experiments/${enc(id)}/audit`);
  },

  getWarnings(id: string): Promise<ApiWarningsResponse> {
    return getJson<ApiWarningsResponse>(`/experiments/${enc(id)}/warnings`);
  },

  async getEvidence(id: string) {
    return (await getJson<ApiEvidenceResponse>(`/experiments/${enc(id)}/evidence`)).evidence;
  },

  // P28.5 — the typed evidence-SUPPORT classification for the current record,
  // bound to `record_rev`. A separate axis from validation/audit/advisory; the
  // client parses it, it never computes a class or a verdict.
  getEvidenceClassification(id: string): Promise<ApiEvidenceClassification> {
    return getJson<ApiEvidenceClassification>(
      `/experiments/${enc(id)}/evidence-classification`,
    );
  },

  // S5 — one cited source fixture, read-only (governance-gated to the allowlist).
  getSourcePreview(id: string, source: string): Promise<ApiSourcePreview> {
    return getJson<ApiSourcePreview>(
      `/experiments/${enc(id)}/source-preview?source=${enc(source)}`,
    );
  },

  // S5/S6 — the written record + sidecar content (null before export). Read-only:
  // the backend reads only the two files export wrote inside the workspace.
  getArtifacts(id: string): Promise<ApiArtifactsResponse> {
    return getJson<ApiArtifactsResponse>(`/experiments/${enc(id)}/artifacts`);
  },

  // P34.2 — the READ-ONLY grounded assistant resolver. A non-mutating POST (a
  // GET-like query carrying a JSON body): it resolves a free-form question
  // against the current record context and returns a source-labeled answer. It
  // sends NO If-Match (nothing is written) and inherits the optional Bearer auth
  // via request(). A non-2xx (empty/too-long question, unknown experiment) or a
  // network failure throws ApiError, which the caller renders as unavailable —
  // never a fabricated answer. It touches no mutation endpoint.
  askAssistant(
    id: string,
    body: { question: string; grounded_rev?: string },
  ): Promise<AssistantQueryResponse> {
    return postJson<AssistantQueryResponse>(`/experiments/${enc(id)}/assistant/query`, body);
  },

  // P34.4 — the RECORD-AGNOSTIC grounded resolver for the Project Memory surface,
  // which has NO record (so it has no experiment id and cannot use askAssistant —
  // that would 404). A non-mutating POST with NO experiment path param: a
  // project-memory question is answered from the memory reader (leads to verify,
  // never a verdict); any record question is honestly refused server-side. Inherits
  // the optional Bearer auth via request() and sends no If-Match (nothing is
  // written). The response carries a null `record_rev`/`version` (no record). A
  // non-2xx or network failure throws ApiError, rendered as unavailable — never a
  // fabricated answer. It touches no mutation endpoint and loads/creates no record.
  askMemory(body: { question: string }): Promise<AssistantQueryResponse> {
    return postJson<AssistantQueryResponse>('/assistant/memory/query', body);
  },

  // Memory plane (advisory only; never gates).
  getGraphStatus(): Promise<ApiGraphStatus> {
    return getJson<ApiGraphStatus>('/graph/status');
  },

  // P24.4 — Source Index: the served-allowlist file list + one file's
  // provenance detail. Metadata/provenance only — never file content.
  getMemoryFiles(): Promise<ApiMemoryFilesResponse> {
    return getJson<ApiMemoryFilesResponse>('/memory/files');
  },

  getMemoryFile(path: string): Promise<ApiMemoryFileResponse> {
    return getJson<ApiMemoryFileResponse>(`/memory/file?path=${enc(path)}`);
  },

  // P24.5 — Concept Lookup: the 19 curated concepts + one concept's anchor
  // provenance and leads. Metadata/provenance only — never file content.
  getMemoryConcepts(): Promise<ApiMemoryConceptsResponse> {
    return getJson<ApiMemoryConceptsResponse>('/memory/concepts');
  },

  getMemoryConcept(id: string): Promise<ApiMemoryConceptResponse> {
    return getJson<ApiMemoryConceptResponse>(`/memory/concepts/${enc(id)}`);
  },

  // P36.2 — the Project Memory "Graph" tab: a deterministic, capped,
  // served-file reference projection (nodes/edges/communities). Metadata/
  // provenance only — never file content, never the full un-embedded source
  // graph. One fetch; the screen does all search/filter/select client-side.
  getMemoryGraph(): Promise<ApiMemoryGraphResponse> {
    return getJson<ApiMemoryGraphResponse>('/memory/graph');
  },

  // P26.4 — grouped truth+memory search. One query fans out to the workspace
  // (truth plane) and memory (advisory) groups server-side; this method only
  // builds the query string and parses the envelope, never merges/ranks the
  // two groups itself. Options are appended in a fixed order, and only when
  // the caller actually provided them (the frozen contract test asserts the
  // exact URL for both the full-options and q-only calls).
  search(
    q: string,
    opts?: { scope?: ApiSearchScope; limit?: number; offset?: number },
  ): Promise<ApiSearchResponse> {
    let path = `/search?q=${enc(q)}`;
    if (opts?.scope !== undefined) path += `&scope=${enc(opts.scope)}`;
    if (opts?.limit !== undefined) path += `&limit=${opts.limit}`;
    if (opts?.offset !== undefined) path += `&offset=${opts.offset}`;
    return getJson<ApiSearchResponse>(path);
  },

  // P30.3 — the cross-record runtime projection consumer (client half of the
  // P30.1 provider). Fetches the SAFE, current-by-construction projection of
  // ALL records (confirmed facts + freshness only — no draft values, evidence
  // bodies, or per-field classifications) so the deterministic crossRecordTriage
  // function can answer "which records need attention / are blocked / have
  // conflicts / are exportable now". This is a LEAD surface, not record truth —
  // opening a match hands off to a direct Workspace load. The typed filters map
  // 1:1 to the backend query params; each is appended only when provided, in a
  // fixed order, and this method only parses the {records,total} envelope (it
  // never computes triage or a verdict itself).
  getRuntimeRecords(filters?: {
    status?: string;
    workflow_state?: 'blocked' | 'reopened' | 'current';
    artifact?: 'none' | 'current' | 'stale';
    has_conflict?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<{ records: RuntimeRecord[]; total: number }> {
    let path = '/runtime/records';
    const params: string[] = [];
    if (filters?.status !== undefined) params.push(`status=${enc(filters.status)}`);
    if (filters?.workflow_state !== undefined)
      params.push(`workflow_state=${enc(filters.workflow_state)}`);
    if (filters?.artifact !== undefined) params.push(`artifact=${enc(filters.artifact)}`);
    if (filters?.has_conflict) params.push('has_conflict=true');
    if (filters?.limit !== undefined) params.push(`limit=${filters.limit}`);
    if (filters?.offset !== undefined) params.push(`offset=${filters.offset}`);
    if (params.length > 0) path += `?${params.join('&')}`;
    return getJson<{ records: RuntimeRecord[]; total: number }>(path);
  },

  // S2 — run the synthetic pipeline; `draft_only` stops at the blockers.
  runDemo(mode: 'draft_only' | 'full' = 'draft_only'): Promise<ApiDemoRunResponse> {
    return postJson<ApiDemoRunResponse>('/demo/run', { mode });
  },

  // P26.0b — the guarded synthetic-demo reset. Preview (200) and both safe
  // refusals (403 not-synthetic / 409 wrong-confirmation or ambiguous) all carry
  // the SAME typed body, so — like blockUpload — we read the JSON on those
  // statuses instead of throwing. Only a status OUTSIDE {200,403,409} (or a
  // network failure, which request() already turns into an unreachable ApiError)
  // is a genuine error. Preview sends only { mode }; execute adds the phrase.
  async resetDemo(
    mode: 'preview' | 'execute',
    confirmation?: string,
  ): Promise<ApiDemoResetResult> {
    const payload =
      mode === 'execute' ? { mode, confirmation } : { mode };
    const res = await request('/demo/reset', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (res.status === 200 || res.status === 403 || res.status === 409) {
      return (await res.json()) as ApiDemoResetResult;
    }
    throw new ApiError(`Request failed (${res.status}).`, { status: res.status });
  },

  // S2 — governance seam. Always 403; we read the verbatim reason from the body.
  async blockUpload(): Promise<ApiUploadsBlocked> {
    const res = await request('/uploads', { method: 'POST' });
    return (await res.json()) as ApiUploadsBlocked;
  },

  // S3 — the full record bundle in one concurrent load. The eight endpoints stay
  // separate values in the result; nothing is merged into a single verdict.
  async getRecordBundle(id: string): Promise<RecordBundle> {
    const [detail, groups, pending, validate, audit, warnings, evidence, graph] =
      await Promise.all([
        this.getExperiment(id),
        this.getDraftGroups(id),
        this.getPending(id),
        this.validate(id),
        this.audit(id),
        this.getWarnings(id),
        this.getEvidence(id),
        this.getGraphStatus(),
      ]);
    return { detail, groups, pending, validate, audit, warnings, evidence, graph };
  },

  // S6 — the export readiness view: the three signals + the gate inputs, each
  // from its own endpoint, fetched together but kept separate (never merged).
  // `artifacts` lets View/Download work on a fresh load of an exported record.
  async getExportReadiness(id: string): Promise<ExportReadinessBundle> {
    const [detail, pending, validate, audit, warnings, graph, artifacts] =
      await Promise.all([
        this.getExperiment(id),
        this.getPending(id),
        this.validate(id),
        this.audit(id),
        this.getWarnings(id),
        this.getGraphStatus(),
        this.getArtifacts(id),
      ]);
    return { detail, pending, validate, audit, warnings, graph, artifacts };
  },

  // S5 — the evidence explorer: the trail + the exported artifacts + memory
  // freshness, then the previews of every source fixture the evidence cites
  // (fetched after so we know which fixtures are actually referenced).
  async getEvidenceBundle(id: string): Promise<EvidenceBundle> {
    const [detail, evidence, artifacts, graph, classification] = await Promise.all([
      this.getExperiment(id),
      this.getEvidence(id),
      this.getArtifacts(id),
      this.getGraphStatus(),
      this.getEvidenceClassification(id),
    ]);
    const files = citedSourceFiles(evidence);
    const previews = await Promise.all(files.map((f) => this.getSourcePreview(id, f)));
    const sourcePreviews: Record<string, ApiSourcePreview> = {};
    files.forEach((f, i) => {
      sourcePreviews[f] = previews[i];
    });
    return { detail, evidence, artifacts, graph, sourcePreviews, classification };
  },
} as const;

/** Distinct source-file basenames referenced by any evidence entry (order kept). */
function citedSourceFiles(evidence: ApiEvidenceEntry[]): string[] {
  const seen: string[] = [];
  for (const entry of evidence) {
    for (const ev of entry.evidence ?? []) {
      const file = ev.source_file;
      if (file && !seen.includes(file)) seen.push(file);
    }
  }
  return seen;
}

export type IsaacApi = typeof api;

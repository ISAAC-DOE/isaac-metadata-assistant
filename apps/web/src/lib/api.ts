/*
 * Typed fetch client for the ISAAC FastAPI backend (apps/api).
 *
 * Thin client: it fetches server-derived truth (validation / coverage / advisory /
 * field status / evidence / status) and never computes any of it. Every verdict
 * comes from an endpoint; this module only parses envelopes and unwraps arrays.
 *
 * Base URL comes from `VITE_API_BASE` (default `http://127.0.0.1:8000/api`),
 * which also decides `isHostedBuild` — the one place the app knows whether it is
 * a hosted deployment or a local dev build.
 *
 * Every failure surfaces as a typed `ApiError` carrying what was actually
 * OBSERVED — `unreachable` (the request never completed), an HTTP `status`, and
 * `htmlIntercept` (an `/api/*` path answered with HTML, i.e. an authenticating
 * edge served a sign-in page). Screens render the honest down state from those
 * signals and never fabricate data — or a cause.
 */

import type { RuntimeRecord } from './crossRecordTriage';
// P36V.1 Unit F — the deep graph layer's wire contract lives in `graphDeep.ts`
// (with its decoder), not in `types.ts`, so the graph's deep layer stays one
// self-contained module.
import type { ApiGraphDetailResponse } from './graphDeep';
import type {
  ApiAboutResponse,
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
  ApiOpenApiResponse,
  ApiPendingResponse,
  ApiSchemaResponse,
  ApiSearchResponse,
  ApiSearchScope,
  ApiSourcePreview,
  ApiDemoRunResponse,
  ApiDemoResetResult,
  ApiUploadsBlocked,
  ApiValidateRecordError,
  ApiValidateRecordResult,
  ApiValidateResult,
  ApiWarningsResponse,
  EvidenceBundle,
  ExportReadinessBundle,
  RecordBundle,
} from './types';

/**
 * The base a build with no `VITE_API_BASE` falls back to — the local FastAPI
 * dev server. Kept as a named literal because `isHostedBuild` compares against
 * it (see below).
 */
const LOCAL_API_BASE = 'http://127.0.0.1:8000/api';

const RAW_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? LOCAL_API_BASE;

export const API_BASE = RAW_BASE.replace(/\/+$/, '');

/**
 * Hosted vs. local, decided ONCE here — never sniffed per component.
 *
 * A hosted image is built with an explicit `VITE_API_BASE` (`/krish/api` for
 * the S3DF deployment); a local build leaves it unset and falls back to
 * `LOCAL_API_BASE`. Vite substitutes `import.meta.env.VITE_API_BASE` with a
 * string LITERAL at build time, so this is a comparison of two compile-time
 * literals: a hosted bundle folds it to `true` and can then drop every
 * local-only branch — including `RUN_COMMAND`, which must never ship in a
 * hosted build (telling a hosted user to start a server on their laptop is
 * both unactionable and false).
 *
 * Consequence worth stating: a developer who points `VITE_API_BASE` at some
 * other base (e.g. `http://localhost:8000/api`) is treated as "hosted" — i.e.
 * we stop claiming the local run command is the remedy. That is the safe
 * direction: we withhold an instruction we cannot justify rather than assert
 * one we cannot support.
 */
export const isHostedBuild = RAW_BASE !== LOCAL_API_BASE;

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

/**
 * The exact command that starts the local backend (shown in the LOCAL down
 * state only). Every render site guards it with `!isHostedBuild` so a hosted
 * bundle constant-folds the branch away and never ships this string.
 */
export const RUN_COMMAND =
  '.venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000';

/**
 * A fetch/HTTP failure. `unreachable` distinguishes "the request never
 * completed" from "the server answered with a status"; `htmlIntercept`
 * distinguishes "an authenticating edge answered instead of our JSON API"
 * from either. Screens branch on these to say something TRUE about the
 * cause instead of a single guessed one.
 */
export class ApiError extends Error {
  readonly status?: number;
  readonly unreachable: boolean;
  /** The parsed error body, when the caller read it (e.g. the P27.5 412
   *  `stale_write` payload carrying `current_version`). Undefined otherwise. */
  readonly body?: unknown;
  /**
   * The API path that failed (as passed to `request`, without the base). Safe
   * to display: this client puts credentials in the `Authorization` HEADER and
   * never in a URL, so a path can never carry a token.
   */
  readonly path?: string;
  /** The response `Content-Type`, when the response reported one. */
  readonly contentType?: string;
  /**
   * True when a response to an `/api/*` path carried `text/html`. Our API only
   * ever answers JSON, so HTML on an API path is an edge/proxy intercept — in
   * this deployment, the identity provider's sign-in page. That is observed
   * evidence of an authentication redirect, not an inference.
   */
  readonly htmlIntercept: boolean;

  constructor(
    message: string,
    opts: {
      status?: number;
      unreachable?: boolean;
      body?: unknown;
      path?: string;
      contentType?: string;
      htmlIntercept?: boolean;
    } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status;
    this.unreachable = opts.unreachable ?? false;
    this.body = opts.body;
    this.path = opts.path;
    this.contentType = opts.contentType;
    this.htmlIntercept = opts.htmlIntercept ?? false;
  }
}

/** `text/html`, with or without a charset parameter. */
const HTML_CONTENT_TYPE = /^\s*text\/html\b/i;

const HTML_INTERCEPT_MESSAGE =
  'The API path returned an HTML page instead of JSON (an edge intercept).';

/** The response `Content-Type`, tolerating a stub/response without headers. */
function contentTypeOf(res: Response): string | undefined {
  const raw = res.headers?.get?.('content-type');
  return raw ?? undefined;
}

function isHtml(contentType: string | undefined): boolean {
  return contentType !== undefined && HTML_CONTENT_TYPE.test(contentType);
}

/** The typed error for a non-OK response, carrying every observable signal. */
function httpError(res: Response, path: string): ApiError {
  const contentType = contentTypeOf(res);
  const htmlIntercept = isHtml(contentType);
  return new ApiError(
    htmlIntercept ? HTML_INTERCEPT_MESSAGE : `Request failed (${res.status}).`,
    { status: res.status, path, contentType, htmlIntercept },
  );
}

/**
 * Read a response body as JSON — the ONE place this module parses a body.
 *
 * `res.json()` REJECTS on a non-JSON body, and the case that matters is not
 * hypothetical: an authenticating edge can answer an `/api/*` request with its
 * sign-in HTML and HTTP **200**. Before this was centralized, that rejection
 * escaped every reader as a raw `SyntaxError` — not an `ApiError` — so screens
 * rendered a generic crash instead of the honest down state. Here the HTML case
 * is detected from the `Content-Type` first (so the caller learns it was an
 * intercept, not corrupt JSON), and any other parse failure still becomes a
 * typed `ApiError`.
 */
async function readJson<T>(res: Response, path: string): Promise<T> {
  const contentType = contentTypeOf(res);
  if (isHtml(contentType)) {
    throw new ApiError(HTML_INTERCEPT_MESSAGE, {
      status: res.status,
      path,
      contentType,
      htmlIntercept: true,
    });
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError(`The API response was not valid JSON (${res.status}).`, {
      status: res.status,
      path,
      contentType,
    });
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
    // Deliberately does NOT name a cause: from here the two are indistinguishable.
    throw new ApiError('The ISAAC API could not be reached.', { unreachable: true, path });
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await request(path);
  if (!res.ok) throw httpError(res, path);
  return readJson<T>(res, path);
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await request(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw httpError(res, path);
  return readJson<T>(res, path);
}

/**
 * Build the ApiError for a non-OK mutation response. On a 412 (`stale_write`) or
 * 400 (`malformed_if_match`) the JSON body is read and attached — it carries the
 * P27.5 conflict payload (`current_version`, `current_rev`, …) the screen needs.
 * A 409 (export immutability) and every other status keep the plain-error shape,
 * so existing callers (e.g. the export 409 branch) are unaffected. An HTML
 * intercept short-circuits: there is no conflict payload in a sign-in page.
 */
async function mutationError(res: Response, path: string): Promise<ApiError> {
  const err = httpError(res, path);
  if (!err.htmlIntercept && (res.status === 412 || res.status === 400)) {
    const body = await res.json().catch(() => undefined);
    return new ApiError(err.message, {
      status: res.status,
      path,
      contentType: err.contentType,
      body,
    });
  }
  return err;
}

const enc = encodeURIComponent;

export const api = {
  health(): Promise<ApiHealth> {
    return getJson<ApiHealth>('/health');
  },

  // P36.4 — Settings "Help / About": non-sensitive app/provenance metadata.
  getAbout(): Promise<ApiAboutResponse> {
    return getJson<ApiAboutResponse>('/about');
  },

  // P36.4 — Settings "API Documentation": the app's own generated OpenAPI
  // schema, fetched base-path-correctly via this router (not the root
  // /openapi.json, which is unprefixed and would be wrong under a deployed
  // base path).
  getOpenApi(): Promise<ApiOpenApiResponse> {
    return getJson<ApiOpenApiResponse>('/openapi');
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
    const path = `/experiments/${enc(id)}`;
    const res = await request(path, {
      headers: { 'If-None-Match': `"${version}"` },
      signal,
    });
    if (res.status === 304) return { changed: false };
    if (res.ok) return { changed: true, detail: await readJson<ApiExperimentDetail>(res, path) };
    throw httpError(res, path);
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
    const path = `/experiments/${enc(id)}/answers`;
    const res = await request(path, {
      method: 'POST',
      body: JSON.stringify({ answers: answersById, confirmed_by_user: true }),
      // Truthiness guard: never send an empty `If-Match: ""` for a blank token.
      ...(version ? { headers: { 'If-Match': `"${version}"` } } : {}),
    });
    if (res.ok) return readJson<ApiAnswersResponse>(res, path);
    throw await mutationError(res, path);
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
    const path = `/experiments/${enc(id)}/edit`;
    const res = await request(path, {
      method: 'POST',
      body: JSON.stringify({ answers: answersById, confirmed_by_user: true }),
      ...(version ? { headers: { 'If-Match': `"${version}"` } } : {}),
    });
    if (res.ok) return readJson<ApiAnswersResponse>(res, path);
    throw await mutationError(res, path);
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
    const path = `/experiments/${enc(id)}/ingestion/csv/preview`;
    const res = await request(path, {
      method: 'POST',
      body: csvText,
      headers: {
        'Content-Type': 'text/csv',
        'If-Match': `"${opts.version}"`,
        ...(opts.filename ? { 'X-Filename': opts.filename } : {}),
      },
    });
    if (res.ok) return readJson<ApiCsvPreview>(res, path);
    throw await mutationError(res, path);
  },

  // S6 — the schema-gated export. A 409 (record already exists) is thrown as an
  // ApiError(status:409); records are immutable and never overwritten. P27.5: a
  // threaded `version` is sent as `If-Match: "<version>"`; a 412 stale write (or
  // 400 malformed token) is thrown as an ApiError carrying the parsed body.
  async exportRecord(id: string, version?: string): Promise<ApiExportResponse> {
    const path = `/experiments/${enc(id)}/export`;
    const res = await request(path, {
      method: 'POST',
      // Truthiness guard: never send an empty `If-Match: ""` for a blank token.
      ...(version ? { headers: { 'If-Match': `"${version}"` } } : {}),
    });
    if (res.ok) return readJson<ApiExportResponse>(res, path);
    throw await mutationError(res, path);
  },

  // The three signals — each fetched from its own endpoint, never merged here.
  validate(id: string): Promise<ApiValidateResult> {
    return postJson<ApiValidateResult>(`/experiments/${enc(id)}/validate`);
  },

  // P36.3 — the standalone Governance & Safety validator. No experiment id:
  // a candidate record (already parsed client-side) is POSTed as-is and
  // checked against the official schema server-side. Unlike `postJson`, a
  // non-OK response's typed body (`{error, message}` — non-object / invalid
  // JSON / oversized) is parsed and attached to the thrown ApiError so the
  // screen can show the server's exact reason instead of a generic status.
  async validateRecord(json: unknown): Promise<ApiValidateRecordResult> {
    const path = '/validate/record';
    const res = await request(path, {
      method: 'POST',
      body: JSON.stringify(json),
    });
    if (!res.ok) {
      const err = httpError(res, path);
      // An intercepted sign-in page carries no typed {error,message} body.
      if (err.htmlIntercept) throw err;
      const typed = (await res.json().catch(() => undefined)) as
        | ApiValidateRecordError
        | undefined;
      throw new ApiError(typed?.message ?? err.message, {
        status: res.status,
        path,
        contentType: err.contentType,
        body: typed,
      });
    }
    // Previously an unparseable 200 body silently resolved to `undefined` and
    // was cast to a result; now it is a typed ApiError like every other read.
    return readJson<ApiValidateRecordResult>(res, path);
  },

  // P36.6 — the read-only Schema Reference browser (renamed from "Schema &
  // Vocabulary" by P36R S8). Serves the vendored
  // official schema + vocabulary/*.json verbatim (reference plane, never truth
  // enforcement) — this client only parses the envelope, it never re-derives
  // or projects any part of it.
  getSchema(): Promise<ApiSchemaResponse> {
    return getJson<ApiSchemaResponse>('/schema');
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

  // P36V.1 Unit F — the DEEP (symbol-level) layer behind the Explore canvas's
  // semantic zoom. A SEPARATE route from `/memory/graph` on purpose: it is
  // ~500 kB of columnar rows, so it is fetched LAZILY — only once the reader
  // has actually zoomed past the first level-of-detail threshold — and never on
  // a plain visit to Project Memory. Metadata/provenance only, never file
  // content; its structure is a point-in-time index of the snapshot's
  // `built_at_commit`, which the surface states explicitly.
  getMemoryGraphDetail(): Promise<ApiGraphDetailResponse> {
    return getJson<ApiGraphDetailResponse>('/memory/graph/detail');
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
  //
  // The backend now REFUSES (409 `demo_target_drifted`) rather than re-seeding
  // over a canonical scenario a user has edited, and its refusal body names the
  // reason and the scenario. `postJson` would have discarded that body —
  // `httpError` never reads one — leaving the screen with a bare "Request failed
  // (409)." and no way to tell a protective refusal from a broken backend. So
  // the 409 body is attached to the thrown ApiError, exactly as `mutationError`
  // does for the 412 stale-write payload; `mutationError` itself is deliberately
  // untouched, since its 409 (export immutability) callers expect the plain
  // shape. An HTML intercept is excluded: an edge sign-in page carries no
  // refusal payload. Every other status keeps the previous behaviour.
  async runDemo(mode: 'draft_only' | 'full' = 'draft_only'): Promise<ApiDemoRunResponse> {
    const path = '/demo/run';
    const res = await request(path, { method: 'POST', body: JSON.stringify({ mode }) });
    if (res.ok) return readJson<ApiDemoRunResponse>(res, path);
    const err = httpError(res, path);
    if (err.htmlIntercept || res.status !== 409) throw err;
    throw new ApiError(err.message, {
      status: res.status,
      path,
      contentType: err.contentType,
      body: await res.json().catch(() => undefined),
    });
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
      // readJson still guards the HTML-intercept case: an edge sign-in page can
      // carry any status, and it is never a typed reset result.
      return readJson<ApiDemoResetResult>(res, '/demo/reset');
    }
    throw httpError(res, '/demo/reset');
  },

  // S2 — governance seam. Always 403; we read the verbatim reason from the body.
  async blockUpload(): Promise<ApiUploadsBlocked> {
    const res = await request('/uploads', { method: 'POST' });
    return readJson<ApiUploadsBlocked>(res, '/uploads');
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

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

import type {
  ApiAnswersResponse,
  ApiAuditResponse,
  ApiDraftResponse,
  ApiEvidenceResponse,
  ApiExperimentDetail,
  ApiExperimentSummary,
  ApiExportResponse,
  ApiGraphStatus,
  ApiHealth,
  ApiPendingResponse,
  ApiDemoRunResponse,
  ApiUploadsBlocked,
  ApiValidateResult,
  ApiWarningsResponse,
  ExportReadinessBundle,
  RecordBundle,
} from './types';

const RAW_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://127.0.0.1:8000/api';

export const API_BASE = RAW_BASE.replace(/\/+$/, '');

/** The exact command that starts the local backend (shown in the down state). */
export const RUN_COMMAND =
  '.venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000';

/** A fetch/HTTP failure. `unreachable` distinguishes "backend down" from an HTTP status. */
export class ApiError extends Error {
  readonly status?: number;
  readonly unreachable: boolean;

  constructor(message: string, opts: { status?: number; unreachable?: boolean } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status;
    this.unreachable = opts.unreachable ?? false;
  }
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
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

  async getDraftGroups(id: string) {
    return (await getJson<ApiDraftResponse>(`/experiments/${enc(id)}/draft`)).groups;
  },

  async getPending(id: string) {
    return (await getJson<ApiPendingResponse>(`/experiments/${enc(id)}/pending`)).pending;
  },

  // S4 — apply a confirmed answer to one blocker. The user has explicitly
  // confirmed (`confirmed_by_user:true`); the backend recomputes and returns the
  // remaining pending list + fresh status. Never called for "leave missing".
  submitAnswer(
    id: string,
    answersById: Record<string, unknown>,
  ): Promise<ApiAnswersResponse> {
    return postJson<ApiAnswersResponse>(`/experiments/${enc(id)}/answers`, {
      answers: answersById,
      confirmed_by_user: true,
    });
  },

  // S6 — the schema-gated export. A 409 (record already exists) is thrown as an
  // ApiError(status:409); records are immutable and never overwritten.
  exportRecord(id: string): Promise<ApiExportResponse> {
    return postJson<ApiExportResponse>(`/experiments/${enc(id)}/export`);
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

  // Memory plane (advisory only; never gates).
  getGraphStatus(): Promise<ApiGraphStatus> {
    return getJson<ApiGraphStatus>('/graph/status');
  },

  // S2 — run the synthetic pipeline; `draft_only` stops at the blockers.
  runDemo(mode: 'draft_only' | 'full' = 'draft_only'): Promise<ApiDemoRunResponse> {
    return postJson<ApiDemoRunResponse>('/demo/run', { mode });
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
  async getExportReadiness(id: string): Promise<ExportReadinessBundle> {
    const [detail, pending, validate, audit, warnings, graph] = await Promise.all([
      this.getExperiment(id),
      this.getPending(id),
      this.validate(id),
      this.audit(id),
      this.getWarnings(id),
      this.getGraphStatus(),
    ]);
    return { detail, pending, validate, audit, warnings, graph };
  },
} as const;

export type IsaacApi = typeof api;

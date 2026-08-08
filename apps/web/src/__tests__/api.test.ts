import { describe, it, expect, afterEach, vi } from 'vitest';
import { api, ApiError, API_BASE, RUN_COMMAND, isHostedBuild } from '../lib/api';
import {
  EXP_ID,
  answersAfterNotebook,
  answersStaleWrite,
  bundleRoutes,
  demoResetPreviewClean,
  demoRunDraftOnly,
  draftResponse,
  experimentSummary,
  exportStaleWrite,
  exportSuccess,
  pendingResponse,
  stubFetchDown,
  stubFetchRoutes,
  uploadsBlocked,
  validateDryRun,
} from '../test/apiFixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('typed API client — parses the real backend shapes', () => {
  it('targets the FastAPI default base and knows the exact run command', () => {
    expect(API_BASE).toBe('http://127.0.0.1:8000/api');
    expect(RUN_COMMAND).toBe(
      '.venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000',
    );
  });

  it('listExperiments unwraps the {experiments: []} envelope', async () => {
    stubFetchRoutes({ 'GET /api/experiments': { body: { experiments: [experimentSummary] } } });
    const list = await api.listExperiments();
    expect(list).toHaveLength(1);
    expect(list[0]).toMatchObject({
      id: EXP_ID,
      status: 'needs_attention',
      pending_count: 5,
      exported: false,
      record_id: null,
    });
  });

  it('getDraftGroups unwraps {groups} and keeps official dotted paths verbatim', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}/draft`]: { body: draftResponse },
    });
    const groups = await api.getDraftGroups(EXP_ID);
    expect(groups.map((g) => g.title)).toEqual(['System & Instrument', 'Sample']);
    expect(groups[0].fields[0]).toMatchObject({
      path: 'system.technique',
      value: 'HERFD-XAS',
      status: 'verified',
      source_types: ['spreadsheet'],
    });
  });

  it('getPending unwraps {pending}; asset blockers keyed by uri, labeled demo answers only', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP_ID}/pending`]: { body: pendingResponse },
    });
    const pending = await api.getPending(EXP_ID);
    expect(pending).toHaveLength(5);
    expect(pending[0].id).toMatch(/^ssrl-archive:\/\//);
    expect(pending[0].demo_answer?.label).toBe('Demo answer (synthetic)');
    expect(pending.map((p) => p.kind)).toEqual([
      'asset',
      'asset',
      'asset',
      'series',
      'descriptor',
    ]);
  });

  it('validate POSTs and returns the dry-run result untouched (no local verdict)', async () => {
    const calls = stubFetchRoutes({
      [`POST /api/experiments/${EXP_ID}/validate`]: { body: validateDryRun },
    });
    const result = await api.validate(EXP_ID);
    expect(calls).toContain(`POST /api/experiments/${EXP_ID}/validate`);
    expect(result).toEqual(validateDryRun);
  });

  it('getRecordBundle hits all eight endpoints and keeps the three signals separate', async () => {
    const calls = stubFetchRoutes(bundleRoutes());
    const bundle = await api.getRecordBundle(EXP_ID);
    expect(calls).toHaveLength(8);
    // three signals arrive as three distinct values…
    expect(bundle.validate.dry_run).toBe(true);
    expect(bundle.audit.records).toEqual([]);
    expect(bundle.warnings.warnings[0].code).toBe('NO_LINKS');
    // …and the advisory channel carries no verdict field (mirrors PortalWarningReport)
    expect('ok' in bundle.warnings).toBe(false);
    expect(bundle.warnings).toMatchObject({ advisory: true, gating: false });
  });

  it('a dead backend raises ApiError{unreachable} — callers show the run command, not fake data', async () => {
    stubFetchDown();
    await expect(api.listExperiments()).rejects.toMatchObject({
      name: 'ApiError',
      unreachable: true,
    });
  });

  it('an HTTP error carries its status (404 → record not found state)', async () => {
    stubFetchRoutes({ 'GET /api/experiments/nope': { status: 404, body: { error: 'x' } } });
    await expect(api.getExperiment('nope')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      unreachable: false,
    });
  });

  it('blockUpload surfaces the 403 governance refusal verbatim', async () => {
    stubFetchRoutes({ 'POST /api/uploads': { status: 403, body: uploadsBlocked } });
    const body = await api.blockUpload();
    expect(body.blocked).toBe(true);
    expect(body.reason).toBe(uploadsBlocked.reason);
  });

  it('runDemo POSTs the mode and returns the real pipeline steps', async () => {
    const calls = stubFetchRoutes({ 'POST /api/demo/run': { body: demoRunDraftOnly } });
    const run = await api.runDemo('draft_only');
    expect(calls).toEqual(['POST /api/demo/run']);
    expect(run.experiment_id).toBe(EXP_ID);
    expect(run.steps.map((s) => s.name)).toEqual(['build_draft', 'validate_draft']);
    expect(run.status).toBe('needs_attention');
  });
});

describe('ApiError', () => {
  it('defaults to reachable (HTTP-level) unless marked unreachable', () => {
    expect(new ApiError('x').unreachable).toBe(false);
    expect(new ApiError('x', { unreachable: true }).unreachable).toBe(true);
    expect(new ApiError('x', { status: 409 }).status).toBe(409);
  });
});

describe('bearer auth header', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  function captureFetch(): RequestInit[] {
    const seen: RequestInit[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        seen.push(init ?? {});
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }),
    );
    return seen;
  }

  // The inverted form of the test that used to live here. It asserted that a set
  // VITE_API_KEY produced `Authorization: Bearer <key>` — i.e. it pinned the
  // footgun in place. A `VITE_*` value is substituted by Vite at BUILD time and
  // compiled into the bundle served to every visitor, so that header was a
  // shared secret published as public JavaScript.
  //
  // This test now pins the opposite, and does it with the key PLANTED rather
  // than absent: absence would pass just as well against a client that still
  // read the variable, so only the planted form can detect a reintroduction.
  it('sends no Authorization header even when VITE_API_KEY is set', async () => {
    vi.stubEnv('VITE_API_KEY', 'planted-secret-that-must-never-be-sent');
    const seen = captureFetch();
    await api.health();
    const headers = seen[0].headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    // Not merely absent from `Authorization` — absent from the request entirely,
    // so a future rename of the header cannot smuggle it back.
    expect(JSON.stringify(seen[0])).not.toContain('planted-secret-that-must-never-be-sent');
  });

  it('sends no Authorization header when VITE_API_KEY is unset', async () => {
    const seen = captureFetch();
    await api.health();
    const headers = seen[0].headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });
});

// --- P27.5: optimistic-concurrency If-Match on the two mutations -------------
//
// submitAnswer / exportRecord take an optional `version` token. When threaded it
// is sent as `If-Match: "<version>"` (byte-identical to the ETag); when omitted
// no If-Match is sent. A 412 stale_write (and 400 malformed) is thrown as an
// ApiError carrying the parsed body so the screen can read `current_version`.

describe('P27.5 · If-Match send + 412 body handling', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function captureFetch(response: { ok?: boolean; status?: number; body?: unknown }): RequestInit[] {
    const seen: RequestInit[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        seen.push(init ?? {});
        return {
          ok: response.ok ?? true,
          status: response.status ?? 200,
          json: async () => response.body ?? {},
        } as Response;
      }),
    );
    return seen;
  }

  it('submitAnswer sends If-Match: "<version>" when a version is threaded', async () => {
    const seen = captureFetch({ body: answersAfterNotebook });
    await api.submitAnswer(EXP_ID, { 'asset://x': 'deadbeef' }, '1.0');
    const headers = seen[0].headers as Record<string, string>;
    expect(headers['If-Match']).toBe('"1.0"');
  });

  it('submitAnswer omits If-Match when no version is threaded (compat grace)', async () => {
    const seen = captureFetch({ body: answersAfterNotebook });
    await api.submitAnswer(EXP_ID, { 'asset://x': 'deadbeef' });
    const headers = (seen[0].headers ?? {}) as Record<string, string>;
    expect(headers['If-Match']).toBeUndefined();
  });

  it('exportRecord sends If-Match: "<version>" when a version is threaded', async () => {
    const seen = captureFetch({ body: exportSuccess });
    await api.exportRecord(EXP_ID, '2.0');
    const headers = seen[0].headers as Record<string, string>;
    expect(headers['If-Match']).toBe('"2.0"');
  });

  it('a 412 stale_write on submitAnswer throws ApiError{status:412} carrying current_version', async () => {
    captureFetch({ ok: false, status: 412, body: answersStaleWrite });
    await expect(api.submitAnswer(EXP_ID, { 'asset://x': 'v' }, '1.0')).rejects.toMatchObject({
      name: 'ApiError',
      status: 412,
      body: { error: 'stale_write', current_version: '2.0', current_rev: 7 },
    });
  });

  it('a 412 stale_write on exportRecord likewise carries the parsed body', async () => {
    captureFetch({ ok: false, status: 412, body: exportStaleWrite });
    await expect(api.exportRecord(EXP_ID, '1.0')).rejects.toMatchObject({
      name: 'ApiError',
      status: 412,
      body: { current_version: '2.0' },
    });
  });

  it('a 400 malformed If-Match also carries the parsed body', async () => {
    captureFetch({ ok: false, status: 400, body: { error: 'malformed_if_match' } });
    await expect(api.submitAnswer(EXP_ID, { x: 1 }, 'bad')).rejects.toMatchObject({
      status: 400,
      body: { error: 'malformed_if_match' },
    });
  });

  it('keeps the existing 409 export behavior — status only, no body plumbing', async () => {
    captureFetch({ ok: false, status: 409, body: { error: 'record_exists' } });
    await expect(api.exportRecord(EXP_ID, '1.0')).rejects.toMatchObject({
      status: 409,
      body: undefined,
    });
  });
});

// --- P26.4: api.search — grouped truth+memory search envelope ----------------
//
// The client is thin: it forwards q + optional scope/limit/offset and parses the
// GET /api/search envelope verbatim (two self-labeled plane groups). It computes
// nothing and must faithfully surface a degraded memory plane. Inline fixtures keep
// this contract self-contained (independent of any shared apiFixtures entry).

describe('api.search — grouped truth+memory search client (P26.4)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const envelope = {
    query: 'cu k-edge',
    normalized_query: 'cu k-edge',
    scope: 'all',
    workspace: {
      plane: 'truth',
      provider: 'workspace-store',
      available: true,
      reason: null,
      total: 1,
      returned: 1,
      limit: 10,
      offset: 0,
      results: [
        {
          kind: 'experiment',
          experiment_id: '01SYNTHXANESSEED0000000001',
          record_id: null,
          title: 'Synthetic XANES — New Draft',
          label: 'Synthetic XANES — New Draft',
          status: 'needs_attention',
          match: {
            field: 'title',
            snippet: 'Synthetic XANES — New Draft',
            reason: 'matched experiment title',
            tier: 'substring',
            offsets: [[10, 15]],
          },
          navigate_to: '/record/01SYNTHXANESSEED0000000001',
          plane: 'truth',
          source: 'workspace-store',
        },
      ],
    },
    memory: {
      plane: 'memory',
      provider: 'memory:sanitized-snapshot',
      note: 'Project memory returns leads to verify — never a validation verdict.',
      available: true,
      reason: null,
      total: 1,
      returned: 1,
      limit: 10,
      offset: 0,
      results: [
        {
          kind: 'concept',
          id: 'concept_alpha',
          path: null,
          label: 'Alpha concept',
          community_name: 'Alpha community',
          match: {
            field: 'concept.label',
            snippet: 'Alpha concept',
            reason: 'matched concept label',
            tier: 'token',
            offsets: [[0, 5]],
          },
          navigate_to: '/memory?concept=concept_alpha',
          plane: 'memory',
          source: 'memory:sanitized-snapshot',
        },
      ],
    },
  };

  it('encodes q + scope + limit + offset into the query string (stable order)', async () => {
    const calls = stubFetchRoutes({
      'GET /api/search?q=cu%20k-edge&scope=workspace&limit=5&offset=10': { body: envelope },
    });
    await api.search('cu k-edge', { scope: 'workspace', limit: 5, offset: 10 });
    expect(calls).toContain('GET /api/search?q=cu%20k-edge&scope=workspace&limit=5&offset=10');
  });

  it('sends only q when no options are given', async () => {
    const calls = stubFetchRoutes({ 'GET /api/search?q=xanes': { body: envelope } });
    await api.search('xanes');
    expect(calls).toContain('GET /api/search?q=xanes');
  });

  it('parses both plane groups from the envelope', async () => {
    stubFetchRoutes({ 'GET /api/search?q=cu%20k-edge': { body: envelope } });
    const res = await api.search('cu k-edge');
    expect(res.scope).toBe('all');
    expect(res.normalized_query).toBe('cu k-edge');
    expect(res.workspace.plane).toBe('truth');
    expect(res.workspace.provider).toBe('workspace-store');
    expect(res.workspace.results[0].kind).toBe('experiment');
    expect(res.workspace.results[0].navigate_to).toBe('/record/01SYNTHXANESSEED0000000001');
    expect(res.workspace.results[0].match.reason).toBe('matched experiment title');
    expect(res.memory.plane).toBe('memory');
    expect(res.memory.note).toBeTruthy();
    expect(res.memory.results[0].kind).toBe('concept');
    expect(res.memory.results[0].navigate_to).toBe('/memory?concept=concept_alpha');
  });

  it('surfaces a degraded memory group honestly (workspace still available)', async () => {
    const down = {
      ...envelope,
      memory: {
        ...envelope.memory,
        available: false,
        reason: 'graph_absent',
        total: 0,
        returned: 0,
        results: [],
      },
    };
    stubFetchRoutes({ 'GET /api/search?q=cu%20k-edge': { body: down } });
    const res = await api.search('cu k-edge');
    expect(res.memory.available).toBe(false);
    expect(res.memory.reason).toBe('graph_absent');
    expect(res.memory.results).toEqual([]);
    expect(res.workspace.available).toBe(true);
    expect(res.workspace.results).toHaveLength(1);
  });

  it('propagates a query_too_short envelope (both groups)', async () => {
    const short = {
      query: 'a',
      normalized_query: 'a',
      scope: 'all',
      workspace: { ...envelope.workspace, reason: 'query_too_short', total: 0, returned: 0, results: [] },
      memory: { ...envelope.memory, reason: 'query_too_short', total: 0, returned: 0, results: [] },
    };
    stubFetchRoutes({ 'GET /api/search?q=a': { body: short } });
    const res = await api.search('a');
    expect(res.workspace.reason).toBe('query_too_short');
    expect(res.memory.reason).toBe('query_too_short');
  });
});

/*
 * P36V.2 — what the client can OBSERVE about a failure.
 *
 * The hosted deployment sits behind an authenticating edge. When a session
 * expires that edge answers an /api/* request with its sign-in HTML — often
 * with HTTP 200 — and `res.json()` REJECTS. That rejection used to escape as a
 * raw SyntaxError (not an ApiError), so screens rendered a crash instead of the
 * honest down state. Every body read now goes through one guarded reader.
 */
describe('typed API client — edge intercepts and non-JSON bodies', () => {
  /** A fetch stub with real response headers and a caller-chosen body. */
  function stubRawResponse(opts: {
    status?: number;
    contentType?: string | null;
    text: string;
  }): void {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        const status = opts.status ?? 200;
        return {
          ok: status < 400,
          status,
          headers: {
            get: (name: string) =>
              name.toLowerCase() === 'content-type' ? (opts.contentType ?? null) : null,
          },
          json: async () => JSON.parse(opts.text) as unknown,
        } as unknown as Response;
      }),
    );
  }

  const LOGIN_PAGE = '<!doctype html><title>Sign in</title>';

  it('an HTML sign-in page with HTTP 200 becomes a typed ApiError, never a SyntaxError', async () => {
    stubRawResponse({ status: 200, contentType: 'text/html; charset=utf-8', text: LOGIN_PAGE });
    const error = await api.listExperiments().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).not.toBeInstanceOf(SyntaxError);
    const api_error = error as ApiError;
    expect(api_error.htmlIntercept).toBe(true);
    expect(api_error.status).toBe(200);
    expect(api_error.contentType).toBe('text/html; charset=utf-8');
    expect(api_error.path).toBe('/experiments');
    expect(api_error.unreachable).toBe(false);
  });

  it('an unparseable body with no content-type is still a typed ApiError', async () => {
    stubRawResponse({ status: 200, contentType: null, text: 'not json at all' });
    const error = await api.health().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(200);
    expect((error as ApiError).htmlIntercept).toBe(false);
    expect((error as ApiError).path).toBe('/health');
  });

  it('flags the intercept on a non-OK HTML response too (a redirected 401/403 page)', async () => {
    stubRawResponse({ status: 403, contentType: 'text/html', text: LOGIN_PAGE });
    const error = (await api.getSchema().catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(403);
    expect(error.htmlIntercept).toBe(true);
  });

  it('guards POST readers as well (postJson)', async () => {
    stubRawResponse({ status: 200, contentType: 'text/html', text: LOGIN_PAGE });
    const error = (await api.validate(EXP_ID).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.htmlIntercept).toBe(true);
    expect(error.path).toBe(`/experiments/${EXP_ID}/validate`);
  });

  it('guards the bespoke readers: validateRecord, blockUpload, resetDemo', async () => {
    stubRawResponse({ status: 200, contentType: 'text/html', text: LOGIN_PAGE });
    for (const call of [
      () => api.validateRecord({}),
      () => api.blockUpload(),
      () => api.resetDemo('preview'),
    ]) {
      const error = (await call().catch((e: unknown) => e)) as ApiError;
      expect(error).toBeInstanceOf(ApiError);
      expect(error.htmlIntercept).toBe(true);
    }
  });

  /*
   * `resetDemo` FAILS CLOSED on a body it cannot interpret as a reset plan.
   *
   * It decodes five statuses — 200/403/409/412/428 — as a typed `ApiDemoResetResult`,
   * and every genuine one is built by the backend's single `_reset_response` helper,
   * which always sets `status` to `"ok"` or `"refused"`. But 409 is not exclusively
   * that helper's: `POST /api/demo/reset` also answers 409
   * `{"error": "tutorial_scope_required", …}` when the request carries no
   * worked-example session, and that body has no `status`, no counts and no
   * `plan_digest`.
   *
   * Read as a result it produced a HALF-BUILT object whose `status` and
   * `ambiguous_count` were both `undefined` — and `ResetDemoDialog` computes
   * `refused` from exactly those two fields, so it evaluated to `false` and left a
   * DESTRUCTIVE control armable. Rejecting is the only safe reading.
   *
   * The three cases below are the discriminator's boundary: the real refusal body,
   * a body with a `status` this client does not know, and a JSON non-object. Each
   * must reject; none may return.
   */
  it('resetDemo rejects a 409 body that is not a reset result (fail closed)', async () => {
    stubFetchRoutes({
      'POST /api/demo/reset': {
        status: 409,
        body: {
          error: 'tutorial_scope_required',
          operation: 'POST /api/demo/reset',
          header: 'X-Isaac-Tutorial-Session',
          message: 'This operation works on the built-in example records. Nothing was written.',
        },
      },
    });
    const error = (await api.resetDemo('preview').catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.path).toBe('/demo/reset');
    expect(error.htmlIntercept).toBe(false);
    expect(error.message).toMatch(/not a reset result/i);
  });

  it('resetDemo rejects an unknown status value and a non-object body alike', async () => {
    for (const body of [{ status: 'partially_ok' }, { mode: 'preview' }, [], 'ok', 7, null]) {
      stubFetchRoutes({ 'POST /api/demo/reset': { status: 200, body } });
      const error = (await api.resetDemo('preview').catch((e: unknown) => e)) as ApiError;
      expect(error, `body ${JSON.stringify(body)} must be refused`).toBeInstanceOf(ApiError);
      expect(error.message).toMatch(/not a reset result/i);
      vi.unstubAllGlobals();
    }
  });

  it('resetDemo still returns every typed refusal it already handled', async () => {
    // The guard tests ONLY the discriminator, so each existing refusal arm — and the
    // 200 preview — must come back as a value, not as a throw.
    for (const [status, refusal] of [
      [200, null],
      [403, 'not_synthetic_only'],
      [409, 'ambiguous_records_present'],
      [412, 'plan_digest_stale'],
      [428, 'plan_digest_required'],
    ] as [number, string | null][]) {
      stubFetchRoutes({
        'POST /api/demo/reset': {
          status,
          body: {
            ...demoResetPreviewClean,
            status: refusal === null ? 'ok' : 'refused',
            refusal_reason: refusal,
          },
        },
      });
      const result = await api.resetDemo('preview');
      expect(result.status, `status ${status}`).toBe(refusal === null ? 'ok' : 'refused');
      expect(result.refusal_reason).toBe(refusal);
      vi.unstubAllGlobals();
    }
  });

  it('a network-level failure carries the path and asserts no cause', async () => {
    stubFetchDown();
    const error = (await api.listExperiments().catch((e: unknown) => e)) as ApiError;
    expect(error.unreachable).toBe(true);
    expect(error.status).toBeUndefined();
    expect(error.htmlIntercept).toBe(false);
    expect(error.path).toBe('/experiments');
    expect(error.message).toBe('The ISAAC API could not be reached.');
  });

  it('an ordinary JSON error keeps its status and gains the path, with no intercept', async () => {
    stubFetchRoutes({ 'GET /api/experiments': { status: 500, body: { error: 'boom' } } });
    const error = (await api.listExperiments().catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(500);
    expect(error.htmlIntercept).toBe(false);
    expect(error.path).toBe('/experiments');
  });

  it('the local build is the default; hosted is decided by VITE_API_BASE alone', () => {
    expect(isHostedBuild).toBe(false);
  });
});

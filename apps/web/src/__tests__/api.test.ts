import { describe, it, expect, afterEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { api, ApiError, API_BASE, RUN_COMMAND, isHostedBuild } from '../lib/api';
import { mutationFailureCopy } from '../lib/mutationErrors';
// `downCopy` is the pure branch table `BackendDown` renders from, so the signal
// and the screen it produces can be asserted in one place: a test that pinned
// only `htmlIntercept` would not notice a branch table that stopped reading it.
import { downCopy } from '../components/FetchStates';
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

  /*
   * IT NO LONGER UNWRAPS TO A BARE ARRAY, and this test was rewritten rather than
   * relaxed. `GET /api/experiments` degrades instead of failing when the server
   * cannot restore its working copies, so the rows alone cannot be told apart from
   * a smaller workspace; the completeness answer travels beside them and
   * unwrapping discarded it. Every assertion the old version made about the rows
   * is still made below, with `incomplete` added.
   */
  it('listExperiments returns the rows and NO completeness claim when the server makes none', async () => {
    stubFetchRoutes({ 'GET /api/experiments': { body: { experiments: [experimentSummary] } } });
    const list = await api.listExperiments();
    expect(list.experiments).toHaveLength(1);
    expect(list.experiments[0]).toMatchObject({
      id: EXP_ID,
      status: 'needs_attention',
      pending_count: 5,
      exported: false,
      record_id: null,
    });
    // The response the server sends for a WHOLE list carries no `incomplete` key
    // at all, and that absence must decode to `null` — never to a truthy object
    // that would raise a "may be missing records" banner over a complete list.
    expect(list.incomplete).toBeNull();
  });

  it('listExperiments decodes the incomplete block the server sends for a SHORT list', async () => {
    stubFetchRoutes({
      'GET /api/experiments': {
        body: {
          experiments: [],
          incomplete: {
            reason: 'restore_failed',
            missing_count: null,
            message: 'The database answered, but this server could not finish restoring.',
          },
        },
      },
    });
    const list = await api.listExperiments();
    expect(list.experiments).toEqual([]);
    expect(list.incomplete).toEqual({
      reason: 'restore_failed',
      missing_count: null,
      message: 'The database answered, but this server could not finish restoring.',
    });
  });

  /*
   * THE DECODER FAILS TOWARDS SILENCE, and the direction is the assertion. Each
   * of these shapes is something a broken server, a proxy error page, or a future
   * contract could produce; none of them is a server SAYING the list is short, so
   * none of them may put a warning on the primary screen. The last case is the one
   * that matters most: a `missing_count` that arrives as a number must not be
   * turned into a rendered figure by the client — but it must also not suppress a
   * disclosure that is otherwise well formed.
   */
  it.each([
    ['absent', undefined],
    ['null', null],
    ['a bare true', true],
    ['a string', 'restore_failed'],
    ['no reason', { message: 'something' }],
    ['an empty reason', { reason: '', message: 'something' }],
    ['no message', { reason: 'restore_failed' }],
    ['a non-string message', { reason: 'restore_failed', message: 7 }],
  ])('listExperiments treats %s as no completeness claim', async (_label, incomplete) => {
    stubFetchRoutes({
      'GET /api/experiments': { body: { experiments: [], incomplete } },
    });
    expect((await api.listExperiments()).incomplete).toBeNull();
  });

  it('listExperiments never invents missing_count, and never drops a real disclosure over it', async () => {
    stubFetchRoutes({
      'GET /api/experiments': {
        body: {
          experiments: [],
          incomplete: { reason: 'store_unavailable', message: 'x' },
        },
      },
    });
    // `missing_count` absent -> `null` ("unknown"), never 0.
    expect((await api.listExperiments()).incomplete).toEqual({
      reason: 'store_unavailable',
      missing_count: null,
      message: 'x',
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

  it('getRecordBundle hits all nine endpoints and keeps the three signals separate', async () => {
    const calls = stubFetchRoutes(bundleRoutes());
    const bundle = await api.getRecordBundle(EXP_ID);
    // NINE since the record-identity sections. The ninth is `/artifacts`, the
    // EXISTING route the export-readiness, evidence and experiment-graph bundles
    // already read — it is the only thing that serves an official record's own
    // top-level values and its `links` block. No route was added for it.
    expect(calls).toHaveLength(9);
    expect(calls).toContain(`GET /api/experiments/${EXP_ID}/artifacts`);
    // …and it stays a SEPARATE value, merged into no verdict, like the other eight.
    expect(bundle.artifacts.record).toBeNull();
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

  it('now carries a 409 body too, because two refusals explain themselves in it', async () => {
    /* THIS TEST IS INVERTED. It read "keeps the existing 409 export behavior — status
       only, no body plumbing" and asserted `body: undefined`, which was a correct
       description of a deliberate scoping decision at the time: no caller read a 409
       body, so none was parsed.

       Two refusals since then DO explain themselves in one — `belongs_to_a_run` names
       the run and the route that can take the answer, `already_exported_without_runs`
       says why adding a run would publish a second official record — and an independent
       review measured what a scientist saw instead: "That answer could not be applied
       (409). Nothing was changed — try again", whose advice is false because retrying
       always 409s.

       The change is ADDITIVE in exactly the way the 422 case was: it only POPULATES
       `err.body` where it was `undefined`. `status` is unchanged, and the one caller
       that writes its own 409 copy (`RunsSection`'s Remove flow, which does so because
       that route has exactly one 409) is unaffected — asserted below. */
    captureFetch({ ok: false, status: 409, body: { error: 'record_exists' } });
    await expect(api.exportRecord(EXP_ID, '1.0')).rejects.toMatchObject({
      status: 409,
      body: { error: 'record_exists' },
    });
  });

  it('a 409 whose body will not parse still yields an ApiError, not a crash', async () => {
    // NEGATIVE CONTROL: the parse is `.catch(() => undefined)`, so a non-JSON 409 must
    // degrade to no body rather than throw a second error over the first. `captureFetch`
    // cannot express this — its `json` returns `response.body ?? {}` — so the stub is
    // inline, which is the point: a helper that cannot fail cannot test failing.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 409,
        json: async () => {
          throw new SyntaxError('not JSON');
        },
      }) as unknown as Response),
    );
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

/*
 * THE SECOND INTERCEPT CONDITION — a request that LEFT the API.
 *
 * The infrastructure owner confirmed (2026-08-12) that an expired or
 * unauthenticated `/krish/*` request gets a 302 to Authentik, and that a browser
 * `fetch` follows it and lands on the login response. The content-type test alone
 * catches that only when the login page is labelled `text/html`. Served as
 * `application/xhtml+xml`, or with no content type at all, it fell through to "The
 * API response was not valid JSON (200)" — and `FetchStates` then rendered "ISAAC
 * Returned an Error — the API was reached but answered with HTTP 200", which is
 * absurd for a 200 and points the reader at the wrong remedy.
 *
 * The second condition is `redirected === true && the final URL is outside
 * API_BASE`. It is a CONJUNCTION on purpose: it states where the answer came from,
 * which is checkable, rather than guessing why a parse failed, which is not.
 *
 * THE FIRST TEST IN THIS BLOCK IS THE ONE THAT MATTERS MOST. It is the negative
 * control, and it exists to stop a future slice widening this into "any non-JSON
 * failure means the session ended" — which would tell a scientist to sign in again
 * to fix a truncated response from a healthy, authenticated backend.
 */
describe('typed API client — a redirect that left the API', () => {
  const OFF_BASE = 'https://auth.example.org/if/flow/default/?next=%2Fapi';

  /** A response stub that can model provenance: content type, redirect, final URL. */
  function stubResponse(opts: {
    status?: number;
    contentType?: string | null;
    redirected?: boolean;
    url?: string;
    text: string;
  }): void {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const requested = typeof input === 'string' ? input : String(input);
        const status = opts.status ?? 200;
        return {
          ok: status < 400,
          status,
          redirected: opts.redirected ?? false,
          url: opts.url ?? requested,
          headers: {
            get: (name: string) =>
              name.toLowerCase() === 'content-type' ? (opts.contentType ?? null) : null,
          },
          json: async () => JSON.parse(opts.text) as unknown,
        } as unknown as Response;
      }),
    );
  }

  it('THE NEGATIVE CONTROL: a parse failure that never left the API is NOT expiry', async () => {
    // 200, ISAAC's own content type, ISAAC's own URL, no redirect — and a body
    // that will not parse. That is a backend or transport defect, and signing in
    // again cannot fix it, so the client must not say the session ended.
    stubResponse({
      status: 200,
      contentType: 'application/json',
      redirected: false,
      text: '{"experiments": [',
    });
    const error = (await api.listExperiments().catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.htmlIntercept).toBe(false);
    expect(error.message).toMatch(/not valid JSON/i);
    // ...and the screen this produces is not the sign-in one.
    expect(downCopy(error, true).kind).not.toBe('auth');
  });

  it('an XHTML sign-in page reached by a redirect off the API is an intercept', async () => {
    stubResponse({
      status: 200,
      contentType: 'application/xhtml+xml',
      redirected: true,
      url: OFF_BASE,
      text: '<html/>',
    });
    const error = (await api.listExperiments().catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.htmlIntercept).toBe(true);
    expect(error.status).toBe(200);
    expect(error.path).toBe('/experiments');
    expect(downCopy(error, true).kind).toBe('auth');
  });

  it('a redirect to a login page with NO content type at all is still an intercept', async () => {
    // The condition deliberately does not depend on what the edge labelled its
    // own body — an unlabelled response is the case `isHtml` can never catch.
    stubResponse({ status: 200, contentType: null, redirected: true, url: OFF_BASE, text: '<html/>' });
    const error = (await api.health().catch((e: unknown) => e)) as ApiError;
    expect(error.htmlIntercept).toBe(true);
    expect(error.contentType).toBeUndefined();
    expect(error.message).toMatch(/redirected away from the ISAAC API/i);
  });

  it('a BENIGN redirect that stays under API_BASE is not an intercept', async () => {
    // ISAAC's own normalisation (a trailing slash, a moved route) redirects
    // within the API. Nothing about that says the session ended, and treating it
    // as expiry would sign the reader out on a successful request.
    stubResponse({
      status: 200,
      contentType: 'application/json',
      redirected: true,
      url: `${API_BASE}/experiments/`,
      text: '{"experiments": [], "incomplete": null}',
    });
    const list = await api.listExperiments();
    expect(list.experiments).toEqual([]);
  });

  it('a benign in-API redirect on a FAILING response keeps its ordinary status copy', async () => {
    stubResponse({
      status: 500,
      contentType: 'application/json',
      redirected: true,
      url: `${API_BASE}/experiments/`,
      text: '{"error": "boom"}',
    });
    const error = (await api.listExperiments().catch((e: unknown) => e)) as ApiError;
    expect(error.htmlIntercept).toBe(false);
    expect(error.status).toBe(500);
    expect(downCopy(error, true).kind).toBe('http_error');
  });

  it('`redirected` alone proves nothing without a readable final URL', async () => {
    // We would be guessing, and the guess would run in the over-claiming
    // direction, so the honest answer is "not observed".
    stubResponse({ status: 200, contentType: 'application/json', redirected: true, url: '', text: 'nope' });
    const error = (await api.health().catch((e: unknown) => e)) as ApiError;
    expect(error.htmlIntercept).toBe(false);
    expect(error.message).toMatch(/not valid JSON/i);
  });

  it('the intercept is flagged on a non-OK redirected response too', async () => {
    stubResponse({
      status: 403,
      contentType: 'application/xhtml+xml',
      redirected: true,
      url: OFF_BASE,
      text: '<html/>',
    });
    const error = (await api.getSchema().catch((e: unknown) => e)) as ApiError;
    expect(error.htmlIntercept).toBe(true);
    expect(error.status).toBe(403);
  });

  it('a mutation reader flags it as well, so write surfaces see the same signal', async () => {
    stubResponse({
      status: 200,
      contentType: 'application/xhtml+xml',
      redirected: true,
      url: OFF_BASE,
      text: '<html/>',
    });
    const error = (await api
      .createExperiment({ title: 'T', description: '' })
      .catch((e: unknown) => e)) as ApiError;
    expect(error.htmlIntercept).toBe(true);
  });
});

/*
 * THE SHARED WRITE-FAILURE COPY.
 *
 * Five mutation surfaces rendered `err.message` raw, and one of them —
 * `CsvReconcilePanel` — rendered "check the file and try again", blaming the
 * scientist's file for an expired session. `mutationFailureCopy` is the single
 * definition of "this failed because the session ended"; everything else keeps the
 * caller's own sentence, unchanged.
 */
describe('mutationFailureCopy — names one cause and no others', () => {
  const FALLBACK = 'The thing could not be done.';

  it('names the session for an intercept, a 401 and a 403', () => {
    for (const err of [
      new ApiError('x', { status: 200, htmlIntercept: true }),
      new ApiError('x', { status: 401 }),
      new ApiError('x', { status: 403 }),
    ]) {
      const copy = mutationFailureCopy(err, FALLBACK);
      expect(copy).not.toBe(FALLBACK);
      expect(copy).toMatch(/sign in again/i);
      expect(copy).toMatch(/nothing was changed/i);
    }
  });

  /*
   * A SITE-COVERAGE GUARD, not a behaviour test, and it is honest about that.
   *
   * Six surfaces rendered a raw `err.message` (or, on the CSV path, a sentence
   * blaming the file). Two of them — Create Experiment and CsvReconcilePanel —
   * have real behavioural tests elsewhere in the suite; driving the other four to
   * a failed write through their full record screens costs far more than it
   * proves. What this pins instead is that none of the six can silently STOP
   * consulting the shared helper, which is the regression that would return the
   * defect. It cannot tell whether the call site is on the right branch, so it is
   * a floor and not a ceiling.
   */
  it('every write surface that rendered a raw message consults the helper', () => {
    const sites = [
      'src/components/RecordValidator.tsx',
      'src/components/CsvReconcilePanel.tsx',
      'src/components/RunCard.tsx',
      'src/components/RunInheritedPanel.tsx',
      'src/components/RunsSection.tsx',
      'src/screens/ExperimentsHome.tsx',
    ];
    for (const site of sites) {
      const source = readFileSync(resolve(__dirname, '../..', site), 'utf8');
      expect(source, `${site} must import the shared helper`).toContain(
        "from '../lib/mutationErrors'",
      );
      expect(source, `${site} must call it`).toMatch(/mutationFailureCopy\(/);
    }
  });

  it('returns the caller’s own sentence for every other failure', () => {
    for (const err of [
      new ApiError('x', { status: 500 }),
      new ApiError('x', { status: 412 }),
      new ApiError('x', { status: 422 }),
      new ApiError('x', { unreachable: true }),
      new Error('plain'),
      'a string',
      null,
      undefined,
    ]) {
      expect(mutationFailureCopy(err, FALLBACK)).toBe(FALLBACK);
    }
  });
});

/*
 * THE BACKEND'S TYPED 404 REASON, plumbed onto `ApiError.reason`.
 *
 * `routes.py` deliberately answers a 404 under `/experiments/{id}` with FOUR
 * different bodies — `experiment_not_found`, `run_not_found` ("the record exists and
 * was read successfully and simply holds no run under that id"; collapsing them
 * "would tell a client to go looking in the wrong place"), `source_not_allowed`, and
 * `tutorial_session_not_found` from the scope dependency. `httpError` copies the
 * status and nothing else, so all four arrived at the UI identical and
 * `FetchStates.downCopy` reported every one of them as a missing record.
 *
 * `getJson` now reads that reason. The rules below are each a defect this module has
 * already had at least once, so they are pinned rather than assumed.
 */
describe('typed API client — the typed 404 reason', () => {
  /** A fetch stub whose body text and content-type the caller chooses. */
  function stub404(text: string, contentType: string | null = 'application/json'): void {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        let consumed = false;
        return {
          ok: false,
          status: 404,
          headers: {
            get: (name: string) =>
              name.toLowerCase() === 'content-type' ? contentType : null,
          },
          json: async () => {
            // A body can be consumed ONCE. If anything reads it twice this throws,
            // which is the point — `readJson` must not also run on the failure path.
            if (consumed) throw new TypeError('body stream already read');
            consumed = true;
            return JSON.parse(text) as unknown;
          },
        } as unknown as Response;
      }),
    );
  }

  it('run_not_found reaches the client as a reason, alongside the status and path', async () => {
    stub404(
      JSON.stringify({ error: 'run_not_found', experiment_id: EXP_ID, id: 'RUN-1' }),
    );
    const error = (await api.getRun(EXP_ID, 'RUN-1').catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.reason).toBe('run_not_found');
    expect(error.path).toBe(`/experiments/${EXP_ID}/runs/RUN-1`);
    expect(error.htmlIntercept).toBe(false);
  });

  it('source_not_allowed reaches the client — the reachable Evidence-screen case', async () => {
    stub404(
      JSON.stringify({
        error: 'source_not_allowed',
        message: 'Only the two committed reference files may be previewed.',
        allowed: ['a.csv', 'b.csv'],
      }),
    );
    const error = (await api
      .getSourcePreview(EXP_ID, 'outside.csv')
      .catch((e: unknown) => e)) as ApiError;
    expect(error.reason).toBe('source_not_allowed');
  });

  it('experiment_not_found reaches the client, so the record claim rests on evidence', async () => {
    stub404(JSON.stringify({ error: 'experiment_not_found', id: EXP_ID }));
    const error = (await api.getExperiment(EXP_ID).catch((e: unknown) => e)) as ApiError;
    expect(error.reason).toBe('experiment_not_found');
  });

  /*
   * THE LOAD-BEARING REFUSAL. An authenticating edge answers `/api/*` with its
   * sign-in page; a "reason" parsed out of that would be fabricated, and
   * `downCopy`'s `interceptedByEdge` guard must keep winning over the reason
   * branches. Asserted in BOTH directions.
   */
  it('an HTML-bodied 404 yields NO reason, and is still flagged as an intercept', async () => {
    stub404('<!doctype html><title>Sign in</title>', 'text/html; charset=utf-8');
    const error = (await api.getExperiment(EXP_ID).catch((e: unknown) => e)) as ApiError;
    expect(error.htmlIntercept).toBe(true);
    expect(error.reason).toBeUndefined();
  });

  it('an unreadable, empty or untyped 404 body yields NO reason rather than a wrong one', async () => {
    for (const body of [
      'not json at all', // parse rejects
      '{}', // JSON, no `error`
      JSON.stringify({ detail: 'Not Found' }), // FastAPI's shape for an unrouted path
      JSON.stringify({ error: 42 }), // present but not a string
      JSON.stringify({ error: { code: 'nested' } }),
    ]) {
      stub404(body);
      const error = (await api.getExperiment(EXP_ID).catch((e: unknown) => e)) as ApiError;
      expect(error).toBeInstanceOf(ApiError);
      expect(error.status).toBe(404);
      expect(error.reason).toBeUndefined();
    }
  });

  it('only 404 is widened — another status keeps its body unread', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        return {
          ok: false,
          status: 500,
          headers: { get: () => 'application/json' },
          json: async () => ({ error: 'experiment_not_found' }),
        } as unknown as Response;
      }),
    );
    const error = (await api.getExperiment(EXP_ID).catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(500);
    // Reading a reason here would let a 500 masquerade as a missing record.
    expect(error.reason).toBeUndefined();
  });

  /*
   * POST IS WIDENED TOO, and this test exists because leaving it out was a measured
   * bug rather than a hypothetical one. The record screen fetches seven requests for
   * one route, two of them POSTs (`/validate`, `/audit`). With only `getJson`
   * widened, a POST rejection winning that race left `reason === undefined` and the
   * copy fell back to the path rule — which, for a sub-resource path, is NOT the
   * record claim. `tutorial-session-lifecycle`'s deep-link test caught exactly that.
   */
  it('postJson is widened too, so a bundle cannot depend on which member lost the race', async () => {
    stub404(JSON.stringify({ error: 'experiment_not_found', id: EXP_ID }));
    const error = (await api.validate(EXP_ID).catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(404);
    expect(error.reason).toBe('experiment_not_found');
    expect(error.path).toBe(`/experiments/${EXP_ID}/validate`);
  });

  /*
   * A MIXED-STATUS BUNDLE — the one behaviour change reading the body causes, pinned
   * so that changing it later is loud rather than silent.
   *
   * Only the 404 path awaits `res.json()`, so a 404 rejects one `await` LATER than
   * any other failing status. When two members of a `Promise.all` fail with DIFFERENT
   * statuses the non-404 therefore wins deterministically, where before this change
   * the winner was whatever the network delivered first.
   *
   * THIS IS ORDERING, NOT INFORMATION, AND BOTH OUTCOMES ARE HONEST. The 500 renders
   * `http_error` ("the API was reached but answered with HTTP 500"), which is true of
   * that response; a 404 that does reach the panel still carries its reason. It is
   * pinned rather than compensated for: adding a delay to even the tie-break up would
   * be complexity in service of cosmetics. Asserted with the 404 FIRST in the array
   * and then LAST, so the result is shown to depend on the status rather than on
   * argument order.
   */
  it('a mixed-status bundle rejects with the non-404, whichever order it is listed in', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const is404 = url.endsWith(`/experiments/${EXP_ID}`);
        return {
          ok: false,
          status: is404 ? 404 : 500,
          headers: { get: () => 'application/json' },
          json: async () => (is404 ? { error: 'experiment_not_found', id: EXP_ID } : { detail: 'x' }),
        } as unknown as Response;
      }),
    );
    for (const order of ['404-first', '404-last'] as const) {
      const reads = [api.getExperiment(EXP_ID), api.getWarnings(EXP_ID)];
      const error = (await Promise.all(
        order === '404-first' ? reads : [...reads].reverse(),
      ).catch((e: unknown) => e)) as ApiError;
      expect(error).toBeInstanceOf(ApiError);
      expect(error.status).toBe(500);
      expect(error.reason).toBeUndefined();
    }
  });
});

/*
 * THE OVERRIDE CLIENT DOES NOT CONFIRM ON ANYBODY'S BEHALF.
 *
 * `updateRun` and `editField` send `confirmed_by_user: true` unconditionally, and
 * that is defensible for them: their only caller is a box the reader typed into.
 * The two override operations are different — recording one displaces a value the
 * RECORD supplied, and the route makes it an explicitly confirmed act — so the flag
 * is an ARGUMENT, and these tests pin that it is passed through rather than
 * manufactured. The `false` case cannot occur through the panel (its submit stays
 * disabled until the box is ticked), and that is exactly why it is pinned HERE: a
 * future caller that forgets the gesture must reach the server's own refusal, not a
 * `true` this module supplied for it.
 */
describe("per-run override client — confirmation and the RUN's If-Match", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function captureFetch(response: { ok?: boolean; status?: number; body?: unknown }) {
    const seen: { url: string; init: RequestInit }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        seen.push({ url: String(input), init: init ?? {} });
        return {
          ok: response.ok ?? true,
          status: response.status ?? 200,
          json: async () => response.body ?? {},
        } as Response;
      }),
    );
    return seen;
  }

  const bodyOf = (init: RequestInit) => JSON.parse(String(init.body)) as Record<string, unknown>;

  it('setRunOverride sends exactly the confirmation it was given — true', async () => {
    const seen = captureFetch({
      body: { run: {}, override: { address: 'field:a', recorded_utc: 'Z' } },
    });
    await api.setRunOverride(
      EXP_ID,
      'RUN-1',
      { address: 'field:sample.material.name', payload: { value: 'x' }, confirmedByUser: true },
      'ra.3',
    );
    expect(seen[0].url).toContain(`/experiments/${EXP_ID}/runs/RUN-1/overrides`);
    expect(bodyOf(seen[0].init)).toEqual({
      confirmed_by_user: true,
      address: 'field:sample.material.name',
      payload: { value: 'x' },
    });
    // THE RUN'S token, not the record's.
    expect((seen[0].init.headers as Record<string, string>)['If-Match']).toBe('"ra.3"');
  });

  it("setRunOverride sends FALSE unchanged, so the server's own refusal is what is seen", async () => {
    const seen = captureFetch({ body: {} });
    await api.setRunOverride(
      EXP_ID,
      'RUN-1',
      { address: 'field:a', payload: { value: 'x' }, confirmedByUser: false },
      'ra.3',
    );
    expect(bodyOf(seen[0].init).confirmed_by_user).toBe(false);
  });

  it('clearRunOverride likewise passes the confirmation through, both ways', async () => {
    const yes = captureFetch({ body: { run: {}, cleared: true } });
    await api.clearRunOverride(
      EXP_ID,
      'RUN-1',
      { address: 'field:a', confirmedByUser: true },
      'ra.4',
    );
    expect(bodyOf(yes[0].init)).toEqual({ confirmed_by_user: true, address: 'field:a' });
    expect((yes[0].init.headers as Record<string, string>)['If-Match']).toBe('"ra.4"');
    vi.unstubAllGlobals();

    const no = captureFetch({ body: { run: {}, cleared: false } });
    await api.clearRunOverride(
      EXP_ID,
      'RUN-1',
      { address: 'field:a', confirmedByUser: false },
      'ra.4',
    );
    expect(bodyOf(no[0].init).confirmed_by_user).toBe(false);
  });

  it('omits If-Match entirely for a blank token, so the server answers 428 rather than 400', async () => {
    // An empty `If-Match: ""` is a MALFORMED token (400) and would report a client
    // bug as a precondition failure. Absent is the honest refusal.
    const seen = captureFetch({ body: { run: {}, cleared: false } });
    await api.clearRunOverride(EXP_ID, 'RUN-1', { address: 'field:a', confirmedByUser: true }, '');
    expect((seen[0].init.headers ?? {}) as Record<string, string>).not.toHaveProperty('If-Match');
  });

  it('a 412 on an override throws ApiError{status:412} carrying the conflict body', async () => {
    captureFetch({
      ok: false,
      status: 412,
      body: { error: 'stale_write', current_version: 'ra.9' },
    });
    await expect(
      api.setRunOverride(
        EXP_ID,
        'RUN-1',
        { address: 'field:a', payload: {}, confirmedByUser: true },
        'ra.3',
      ),
    ).rejects.toMatchObject({
      status: 412,
      body: { error: 'stale_write', current_version: 'ra.9' },
    });
  });

  it("a 422 refusal carries the server's typed body so the screen can quote it", async () => {
    captureFetch({
      ok: false,
      status: 422,
      body: {
        error: 'not_overridable',
        address: 'field:system.domain',
        message: 'This address cannot hold a run override.',
      },
    });
    await expect(
      api.setRunOverride(
        EXP_ID,
        'RUN-1',
        { address: 'field:system.domain', payload: {}, confirmedByUser: true },
        'ra.3',
      ),
    ).rejects.toMatchObject({
      status: 422,
      body: { error: 'not_overridable', address: 'field:system.domain' },
    });
  });
});

describe('createProposal — the create that lands with its producer', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function captureFetch(response: { ok?: boolean; status?: number; body?: unknown }) {
    const seen: { url: string; init: RequestInit }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        seen.push({ url: String(input), init: init ?? {} });
        return {
          ok: response.ok ?? true,
          status: response.status ?? 200,
          json: async () => response.body ?? {},
        } as Response;
      }),
    );
    return seen;
  }

  const bodyOf = (init: RequestInit) => JSON.parse(String(init.body)) as Record<string, unknown>;

  const CREATED = {
    proposal: { proposal_id: 'p1', state: 'open' },
    deduplicated: false,
    experiment_version: 'g1.6',
  };

  it('sends exactly the four required fields and nothing it was not given', async () => {
    const seen = captureFetch({ body: CREATED });
    await api.createProposal(EXP_ID, {
      experimentVersion: 'g1.5',
      noteId: 'n1',
      targetFieldPath: 'context.temperature_K',
      proposedValue: 300,
      rule: 'the sentence that produced it',
    });
    expect(seen[0].url).toContain(`/experiments/${EXP_ID}/proposals`);
    expect(seen[0].init.method).toBe('POST');
    // NOTHING IS DEFAULTED. No `run_id`, no span, no key — a client that filled any
    // of them in would be deciding something a scientist has to.
    expect(bodyOf(seen[0].init)).toEqual({
      note_id: 'n1',
      target_field_path: 'context.temperature_K',
      proposed_value: 300,
      rule: 'the sentence that produced it',
    });
    // THE RECORD'S token, not a run's: a proposal lives in the record's own document.
    expect((seen[0].init.headers as Record<string, string>)['If-Match']).toBe('"g1.5"');
  });

  it('carries the run, the span and the key when — and only when — it is given them', async () => {
    const seen = captureFetch({ body: CREATED });
    await api.createProposal(EXP_ID, {
      experimentVersion: 'g1.5',
      noteId: 'n1',
      targetFieldPath: 'context.temperature_K',
      proposedValue: 300,
      rule: 'r',
      runId: 'run-1',
      startChar: 0,
      endChar: 22,
      clientRequestKey: 'transcript-capture:n1:0',
    });
    expect(bodyOf(seen[0].init)).toEqual({
      note_id: 'n1',
      target_field_path: 'context.temperature_K',
      proposed_value: 300,
      rule: 'r',
      run_id: 'run-1',
      start_char: 0,
      end_char: 22,
      client_request_key: 'transcript-capture:n1:0',
    });
  });

  it('sends HALF a span as no span at all, rather than letting the server refuse it', async () => {
    // `start_char` and `end_char` travel together; the server refuses half a span.
    // Sending one would turn a client bug into a `422` the caller has to interpret.
    const seen = captureFetch({ body: CREATED });
    await api.createProposal(EXP_ID, {
      experimentVersion: 'g1.5',
      noteId: 'n1',
      targetFieldPath: 'context.temperature_K',
      proposedValue: 300,
      rule: 'r',
      startChar: 4,
    });
    expect(Object.keys(bodyOf(seen[0].init))).not.toContain('start_char');
    expect(Object.keys(bodyOf(seen[0].init))).not.toContain('end_char');
  });

  it('returns `deduplicated` so a caller cannot report a create off the status', async () => {
    // `200` is BOTH outcomes. A caller reading the status alone would announce a
    // create that may not have happened, which is why the flag is on the body.
    const seen = captureFetch({
      body: { ...CREATED, deduplicated: true, proposal: { proposal_id: 'p-first' } },
    });
    const created = await api.createProposal(EXP_ID, {
      experimentVersion: 'g1.5',
      noteId: 'n1',
      targetFieldPath: 'context.temperature_K',
      proposedValue: 300,
      rule: 'r',
      clientRequestKey: 'k',
    });
    expect(created.deduplicated).toBe(true);
    expect(created.proposal.proposal_id).toBe('p-first');
    expect(seen).toHaveLength(1);
  });

  it('omits If-Match entirely for a blank token, so the server answers 428 not 400', async () => {
    const seen = captureFetch({ body: CREATED });
    await api.createProposal(EXP_ID, {
      experimentVersion: '',
      noteId: 'n1',
      targetFieldPath: 'context.temperature_K',
      proposedValue: 300,
      rule: 'r',
    });
    // `request()` supplies the Content-Type header for a body; what must be absent is
    // the precondition, and asserting the whole `headers` object would be asserting
    // against the transport rather than against this function's one decision.
    expect((seen[0].init.headers as Record<string, string>)['If-Match']).toBeUndefined();
  });

  it('a refusal reaches the caller as an ApiError carrying the typed body', async () => {
    // `no_write_path_for_field` and `target_requires_a_run` have different remedies,
    // so this function relays the body rather than composing one sentence for both.
    captureFetch({
      ok: false,
      status: 422,
      body: { error: 'no_write_path_for_field', key: 'system.configuration.beamline' },
    });
    await expect(
      api.createProposal(EXP_ID, {
        experimentVersion: 'g1.5',
        noteId: 'n1',
        targetFieldPath: 'system.configuration.beamline',
        proposedValue: 'x',
        rule: 'r',
      }),
    ).rejects.toMatchObject({ status: 422 });
  });
});

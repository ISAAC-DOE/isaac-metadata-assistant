import { describe, it, expect, afterEach, vi } from 'vitest';
import { api, ApiError, API_BASE, RUN_COMMAND } from '../lib/api';
import {
  EXP_ID,
  bundleRoutes,
  demoRunDraftOnly,
  draftResponse,
  experimentSummary,
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

  it('attaches Authorization: Bearer when VITE_API_KEY is set', async () => {
    vi.stubEnv('VITE_API_KEY', 'demo-secret');
    const seen = captureFetch();
    await api.health();
    const headers = seen[0].headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer demo-secret');
  });

  it('sends no Authorization header when VITE_API_KEY is unset', async () => {
    const seen = captureFetch();
    await api.health();
    const headers = seen[0].headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
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

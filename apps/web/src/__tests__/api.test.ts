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

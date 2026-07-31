/**
 * Global setup — run ONCE before any project, any worker, any spec.
 *
 * Two jobs, both deliberately narrow:
 *
 *   1. Assert the backend precondition. Playwright does NOT start the FastAPI
 *      server (it needs the repo's Python venv, which is outside `apps/web`),
 *      so if it is missing we fail here with the exact command to run instead
 *      of letting 200 specs quietly assert against the "Backend Not Running"
 *      screen.
 *   2. Seed the synthetic workspace ONCE, via `POST /api/demo/run`. That route
 *      is idempotent by construction — it upserts a FIXED canonical id rather
 *      than appending — so re-running never changes the record count.
 *
 * What it deliberately does NOT do: create records, delete records, reset the
 * workspace, upload anything, or touch a database. The whole suite is
 * read-only against the workspace; that is what lets the five viewport
 * projects run in parallel against one backend without racing.
 */

import { request } from '@playwright/test';
import { API_BASE } from './env';

const HOW_TO_START_BACKEND = [
  'Start it from the repository root (no database, no credentials, synthetic only):',
  '',
  '  ISAAC_UI_CORS_ORIGINS="http://127.0.0.1:5173,http://localhost:5173" \\',
  '    .venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000',
  '',
  'Then re-run:  npm run test:e2e   (from apps/web)',
].join('\n');

export default async function globalSetup(): Promise<void> {
  // No `baseURL` here on purpose: a baseURL of `http://host:8000/api` plus a
  // path of `/health` resolves to `http://host:8000/health` (absolute-path
  // semantics), silently dropping the `/api` prefix. Full URLs are unambiguous.
  const ctx = await request.newContext();
  try {
    let health;
    try {
      health = await ctx.get(`${API_BASE}/health`, { timeout: 10_000 });
    } catch (cause) {
      throw new Error(
        `[e2e] The ISAAC backend at ${API_BASE} is not reachable.\n\n${HOW_TO_START_BACKEND}\n\n` +
          `Underlying error: ${(cause as Error).message}`
      );
    }
    if (!health.ok()) {
      throw new Error(
        `[e2e] GET ${API_BASE}/health returned ${health.status()}.\n\n${HOW_TO_START_BACKEND}`
      );
    }

    const body = (await health.json()) as { mode?: string; status?: string };
    if (body.mode && body.mode !== 'synthetic-only') {
      // Refuse to run browser tests against anything but the synthetic
      // workspace. `mode` describes the WORKSPACE (uploads refused, seeding
      // from committed fixtures only) — see CLAUDE.md §15.
      throw new Error(
        `[e2e] Refusing to run: backend reports mode="${body.mode}", expected "synthetic-only".`
      );
    }

    // Idempotent seed. `draft_only` overwrites exactly one canonical id in
    // place; the other four canonical seeds are materialised by `ensure_seeded`
    // inside the same call.
    const seeded = await ctx.post(`${API_BASE}/demo/run`, {
      data: { mode: 'draft_only' },
      timeout: 60_000,
    });
    if (!seeded.ok()) {
      throw new Error(`[e2e] POST ${API_BASE}/demo/run returned ${seeded.status()}.`);
    }

    const list = await ctx.get(`${API_BASE}/experiments`, { timeout: 20_000 });
    const experiments = ((await list.json()) as { experiments?: unknown[] }).experiments ?? [];
    if (experiments.length < 5) {
      throw new Error(
        `[e2e] Expected at least the 5 canonical synthetic seeds after /demo/run, got ${experiments.length}.`
      );
    }
    // eslint-disable-next-line no-console
    console.log(`[e2e] backend ok at ${API_BASE} — ${experiments.length} synthetic experiments seeded.`);
  } finally {
    await ctx.dispose();
  }
}

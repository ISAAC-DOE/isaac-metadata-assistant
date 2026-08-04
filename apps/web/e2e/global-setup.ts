/**
 * Global setup — run ONCE before any project, any worker, any spec.
 *
 * Four jobs, each of which fails with a message naming the STEP that failed:
 *
 *   1. Assert the backend precondition. Playwright does NOT start the FastAPI
 *      server (it needs the repo's Python venv, which is outside `apps/web`),
 *      so if it is missing we fail here with the exact command to run instead
 *      of letting 200 specs quietly assert against the "Backend Not Running"
 *      screen.
 *   2. Refuse to run against anything but `mode: synthetic-only`. Kept exactly
 *      as it was — it is the one governance gate in this file.
 *   3. Assert the ORDINARY workspace is EMPTY. It is a permanent property of
 *      this build (`ensure_seeded()` no longer materialises the examples into
 *      it, and there is no `POST /experiments` anywhere), and a non-zero count
 *      means the seed has leaked back into the shared scope — which would make
 *      the ordinary-scope specs pass against records that should not exist.
 *   4. Open ONE worked-example session for the whole read-only run, verify by
 *      MEASUREMENT that the five examples are in it, and publish its id to the
 *      workers.
 *
 * ── What this file no longer does, and why ──────────────────────────────────
 *
 * It used to "seed via a read": `GET /api/experiments` ran `ensure_seeded()` and
 * materialised the canonical five into the ordinary workspace, and the setup then
 * hard-threw unless the list held at least 5. Both halves are now wrong by
 * design. The examples live only inside a worked-example session, the ordinary
 * list is empty, and asserting `>= 5` on it fails at setup and takes the entire
 * suite with it. The 5-record assertion is not weakened — it MOVED, to the
 * session, where the records actually are, and it is checked against the ids the
 * backend reports as materialised rather than against a bare count.
 *
 * ── Read-only, and how that survives the session ────────────────────────────
 *
 * The whole read-only suite remains read-only *against the workspaces it
 * shares*, which is what lets the five viewport projects run in parallel against
 * one backend. Creating the shared session is the one write here, it happens once
 * before any worker starts, and nothing in the suite writes INTO that session:
 * `surfaces.ts` marks the record surfaces `scope: 'example'` and the `app`
 * fixture enters the scope read-only. The tutorial-behaviour specs deliberately
 * do NOT use this session — each one starts the real walkthrough, which mints a
 * session of its own, and disposes it — so a spec that mutates can never be
 * sharing a scope with a spec that measures. See `specs/tutorial.spec.ts`.
 */

import { request } from '@playwright/test';
import { API_BASE } from './env';
import {
  TUTORIAL_SESSION_HEADER,
  publishWorkedExampleSession,
  unpublishWorkedExampleSession,
} from './worked-example';

const HOW_TO_START_BACKEND = [
  'Start it from the repository root (no database, no credentials, synthetic only):',
  '',
  '  ISAAC_UI_CORS_ORIGINS="http://127.0.0.1:5173,http://localhost:5173" \\',
  '    .venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000',
  '',
  'Then re-run:  npm run test:e2e   (from apps/web)',
].join('\n');

/** The five ids the backend is expected to materialise into a fresh session
 *  (`apps/api/isaac_api/workspace.py` → `CANONICAL_IDS`). Compared as a SET, so
 *  a session holding four of them plus something else fails loudly instead of
 *  passing a count check. */
const EXPECTED_EXAMPLE_IDS = [
  '01SYNTHXANESSEED0000000001',
  '01SYNTHXANESSEED0000000002',
  '01SYNTHXANESSEED0000000003',
  '01SYNTHXANESSEED0000000004',
  '01SYNTHXANESSEED0000000005',
];

export default async function globalSetup(): Promise<void> {
  // A stale handoff file from an interrupted run must never be inherited: a spec
  // would enter a session that no longer exists and get a 404 that looks like a
  // UI regression. Removed BEFORE anything can fail, so an early throw below
  // leaves no misleading file behind either.
  unpublishWorkedExampleSession();

  // No `baseURL` here on purpose: a baseURL of `http://host:8000/api` plus a
  // path of `/health` resolves to `http://host:8000/health` (absolute-path
  // semantics), silently dropping the `/api` prefix. Full URLs are unambiguous.
  const ctx = await request.newContext();
  try {
    // ── 1. the backend is there ──────────────────────────────────────────────
    let health;
    try {
      health = await ctx.get(`${API_BASE}/health`, { timeout: 10_000 });
    } catch (cause) {
      throw new Error(
        `[e2e setup · step 1/4 backend reachable] The ISAAC backend at ${API_BASE} is not ` +
          `reachable.\n\n${HOW_TO_START_BACKEND}\n\nUnderlying error: ${(cause as Error).message}`
      );
    }
    if (!health.ok()) {
      throw new Error(
        `[e2e setup · step 1/4 backend reachable] GET ${API_BASE}/health returned ` +
          `${health.status()}.\n\n${HOW_TO_START_BACKEND}`
      );
    }

    // ── 2. synthetic-only, or nothing ───────────────────────────────────────
    const body = (await health.json()) as { mode?: string; status?: string };
    if (body.mode && body.mode !== 'synthetic-only') {
      // Refuse to run browser tests against anything but the synthetic
      // workspace. `mode` describes the WORKSPACE (uploads refused, seeding
      // from committed fixtures only) — see CLAUDE.md §15.
      throw new Error(
        `[e2e setup · step 2/4 synthetic-only gate] Refusing to run: backend reports ` +
          `mode="${body.mode}", expected "synthetic-only".`
      );
    }

    // ── 3. the ordinary workspace is empty ──────────────────────────────────
    const ordinary = await ctx.get(`${API_BASE}/experiments`, { timeout: 30_000 });
    if (!ordinary.ok()) {
      throw new Error(
        `[e2e setup · step 3/4 ordinary scope empty] GET ${API_BASE}/experiments returned ` +
          `${ordinary.status()}.`
      );
    }
    const ordinaryRows = ((await ordinary.json()) as { experiments?: unknown[] }).experiments ?? [];
    if (ordinaryRows.length !== 0) {
      throw new Error(
        `[e2e setup · step 3/4 ordinary scope empty] The ordinary workspace holds ` +
          `${ordinaryRows.length} experiment(s); this build's ordinary scope is permanently ` +
          `EMPTY (the built-in examples exist only inside a worked-example session, and there ` +
          `is no record-creation route). Either the workspace directory at ISAAC_UI_WORKSPACE ` +
          `carries records from an older build — start the backend on a fresh directory — or ` +
          `seeding has leaked back into the shared scope, which is a regression.`
      );
    }

    // ── 4. one worked-example session for the whole run ─────────────────────
    const created = await ctx.post(`${API_BASE}/tutorial/sessions`, { timeout: 60_000 });
    if (created.status() !== 201) {
      throw new Error(
        `[e2e setup · step 4/4 open worked-example session] POST ` +
          `${API_BASE}/tutorial/sessions returned ${created.status()}, expected 201.\n` +
          `Body: ${await created.text()}\n` +
          `Every record surface in this suite lives inside such a session; without one the ` +
          `suite cannot reach a single record.`
      );
    }
    const session = (await created.json()) as {
      session_id?: string;
      record_ids?: string[];
      ttl_hours?: number;
    };
    const sessionId = session.session_id;
    if (typeof sessionId !== 'string' || sessionId === '') {
      throw new Error(
        `[e2e setup · step 4/4 open worked-example session] The 201 response carried no ` +
          `session_id: ${JSON.stringify(session)}`
      );
    }

    // MEASURED, not trusted. `record_ids` in the response is itself read back
    // from the session by the backend, but this suite navigates by URL, so what
    // matters is that a scoped LIST answers with the five ids.
    const scoped = await ctx.get(`${API_BASE}/experiments`, {
      headers: { [TUTORIAL_SESSION_HEADER]: sessionId },
      timeout: 30_000,
    });
    if (!scoped.ok()) {
      throw new Error(
        `[e2e setup · step 4/4 verify session contents] GET ${API_BASE}/experiments in session ` +
          `${sessionId} returned ${scoped.status()}. A 404 here means the session the backend ` +
          `just minted does not resolve — the scope dependency is failing closed on a live id.`
      );
    }
    const ids = (((await scoped.json()) as { experiments?: { id: string }[] }).experiments ?? []).map(
      (e) => e.id
    );
    const missing = EXPECTED_EXAMPLE_IDS.filter((id) => !ids.includes(id));
    if (missing.length > 0 || ids.length !== EXPECTED_EXAMPLE_IDS.length) {
      throw new Error(
        `[e2e setup · step 4/4 verify session contents] The worked-example session holds ` +
          `${ids.length} record(s) (${ids.join(', ') || 'none'}); expected exactly the five ` +
          `canonical examples. Missing: ${missing.join(', ') || 'none'}.`
      );
    }

    publishWorkedExampleSession({ sessionId, recordIds: ids });

    // eslint-disable-next-line no-console
    console.log(
      `[e2e] backend ok at ${API_BASE} — ordinary workspace empty; worked-example session ` +
        `opened with ${ids.length} examples (ttl ${session.ttl_hours ?? '?'}h).`
    );
  } finally {
    await ctx.dispose();
  }
}

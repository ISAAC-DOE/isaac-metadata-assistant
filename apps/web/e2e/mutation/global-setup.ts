/**
 * Make the mutation suite HERMETIC, and open the scope its records live in.
 *
 * ── Why the wipe ────────────────────────────────────────────────────────────
 *
 * The bug this exists to prevent, found while writing the suite: with a fixed
 * workspace directory and `reuseExistingServer` locally, a run inherited the
 * previous run's mutations. Record 1 came back with `rev=1, answer_log=1` before a
 * single test had touched it, so "this spec needs an open question" and "rev must
 * advance" asserted against a baseline that silently differed from the seed. A
 * mutation suite that is not hermetic does not fail loudly — it drifts, and its
 * assertions slowly become statements about accumulated history.
 *
 * The wipe now also removes the worked-example namespace (`<workspace>/_tutorial`),
 * since that lives inside the workspace directory — so a previous run's sessions
 * cannot survive either, and the fresh session below is the only one on this
 * backend.
 *
 * WHY DELETING THE DIRECTORY IS SAFE while the backend is already running (Playwright
 * starts `webServer` before `globalSetup`): the workspace layer is not an in-memory
 * cache. `_load_all_experiments()` reads the directory on every request and
 * `ensure_tutorial_seeded()` re-materialises any missing canonical id lazily. So the
 * first read after this wipe rebuilds the canonical five from committed seed content.
 *
 * WHY NOT `POST /api/demo/reset`: it is the destructive admin path, it is
 * confirmation- and precondition-gated, and using it here would make the suite that
 * TESTS reset depend on reset working. A directory wipe depends on nothing.
 *
 * WHY NOT A UNIQUE DIRECTORY PER RUN: the config is loaded in worker processes too,
 * so anything that mutates a module-level path risks a mid-run surprise. A wipe in
 * `globalSetup` runs exactly once, in one process, at a defined point.
 *
 * ── Why there is now a session ──────────────────────────────────────────────
 *
 * The five canonical records used to be materialised into the ORDINARY workspace by
 * `ensure_seeded()` on the first read, and this setup asserted `rows.length === 5`
 * there. That assertion now reads 0 by design and would abort the whole suite. The
 * records exist only inside a worked-example session, so the setup opens ONE for the
 * run and publishes its id; the scope fixture in `fixtures.ts` puts every page and
 * every direct API read into it.
 *
 * The baseline check is NOT weakened by the move — it is stricter. It still requires
 * the five ids and `rev === 0` for each, and it additionally requires the ordinary
 * workspace to be empty, which is where a leaked seed would show up.
 */

import { rmSync } from 'node:fs';
import { request } from '@playwright/test';
import { MUT_API_BASE, MUT_SESSION_FILE, MUT_WORKSPACE, SEED } from './env';
import {
  TUTORIAL_SESSION_HEADER,
  publishWorkedExampleSession,
  unpublishWorkedExampleSession,
} from '../worked-example';

export default async function globalSetup() {
  unpublishWorkedExampleSession(MUT_SESSION_FILE);
  rmSync(MUT_WORKSPACE, { recursive: true, force: true });

  const api = await request.newContext();
  try {
    // 1. The ordinary workspace must be empty — this build cannot create a record
    //    and no longer seeds into that scope, so anything here is a leak.
    const ordinary = await api.get(`${MUT_API_BASE}/experiments`);
    if (!ordinary.ok()) {
      throw new Error(`[mutation-setup · step 1/3] GET /experiments failed: ${ordinary.status()}`);
    }
    const ordinaryRows = ((await ordinary.json()) as { experiments?: unknown[] }).experiments ?? [];
    if (ordinaryRows.length !== 0) {
      throw new Error(
        `[mutation-setup · step 1/3 ordinary scope empty] expected 0 experiments in the ordinary ` +
          `workspace, got ${ordinaryRows.length}. The workspace at ${MUT_WORKSPACE} may not be the ` +
          `one the backend is using — check that ISAAC_UI_WORKSPACE reached the uvicorn process — ` +
          `or seeding has leaked back into the ordinary scope.`
      );
    }

    // 2. Open the session this run's records live in.
    const created = await api.post(`${MUT_API_BASE}/tutorial/sessions`);
    if (created.status() !== 201) {
      throw new Error(
        `[mutation-setup · step 2/3 open session] POST /tutorial/sessions returned ` +
          `${created.status()}, expected 201. Body: ${await created.text()}`
      );
    }
    const sessionId = ((await created.json()) as { session_id?: string }).session_id;
    if (typeof sessionId !== 'string' || sessionId === '') {
      throw new Error(`[mutation-setup · step 2/3 open session] the 201 carried no session_id.`);
    }
    const scoped = { [TUTORIAL_SESSION_HEADER]: sessionId };

    // 3. The canonical five are in it, and each is at its BASELINE — because a
    //    wipe that silently failed would otherwise look exactly like a successful
    //    one until an assertion downstream got strange.
    const res = await api.get(`${MUT_API_BASE}/experiments`, { headers: scoped });
    if (!res.ok()) {
      throw new Error(
        `[mutation-setup · step 3/3 verify session] GET /experiments in session ${sessionId} ` +
          `failed: ${res.status()}`
      );
    }
    const body = await res.json();
    const rows = Array.isArray(body) ? body : (body.experiments ?? []);
    if (rows.length !== 5) {
      throw new Error(
        `[mutation-setup · step 3/3 verify session] expected the canonical five inside the ` +
          `worked-example session, got ${rows.length}.`
      );
    }

    for (const id of Object.values(SEED)) {
      const d = await api.get(`${MUT_API_BASE}/experiments/${id}`, { headers: scoped });
      if (!d.ok()) throw new Error(`[mutation-setup] ${id} missing from the fresh session`);
      const detail = await d.json();
      if (detail.rev !== 0) {
        throw new Error(
          `[mutation-setup] ${id} is at rev=${detail.rev}, not 0. The wipe did not take, ` +
            `so this run would inherit a previous run's mutations — the exact drift this ` +
            `setup exists to stop.`
        );
      }
    }

    publishWorkedExampleSession({ sessionId, recordIds: rows.map((r: { id: string }) => r.id) }, MUT_SESSION_FILE);

    // eslint-disable-next-line no-console
    console.log(
      `[mutation-setup] hermetic: ordinary workspace empty; worked-example session with ` +
        `5 canonical records, all at rev 0.`
    );
  } finally {
    await api.dispose();
  }
}

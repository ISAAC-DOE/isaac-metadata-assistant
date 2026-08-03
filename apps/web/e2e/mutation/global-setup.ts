/**
 * Make the mutation suite HERMETIC.
 *
 * The bug this exists to prevent, found while writing the suite: with a fixed
 * workspace directory and `reuseExistingServer` locally, a run inherited the
 * previous run's mutations. Record 1 came back with `rev=1, answer_log=1` before a
 * single test had touched it, so "this spec needs an open question" and "rev must
 * advance" asserted against a baseline that silently differed from the seed. A
 * mutation suite that is not hermetic does not fail loudly — it drifts, and its
 * assertions slowly become statements about accumulated history.
 *
 * WHY DELETING THE DIRECTORY IS SAFE while the backend is already running (Playwright
 * starts `webServer` before `globalSetup`): the workspace layer is not an in-memory
 * cache. `_load_all_experiments()` reads the directory on every request and
 * `ensure_seeded()` re-materialises any missing canonical id lazily. So the first
 * read after this wipe rebuilds the canonical five from committed seed content.
 *
 * WHY NOT `POST /api/demo/reset`: it is the destructive admin path, it is
 * confirmation- and precondition-gated, and using it here would make the suite that
 * TESTS reset depend on reset working. A directory wipe depends on nothing.
 *
 * WHY NOT A UNIQUE DIRECTORY PER RUN: the config is loaded in worker processes too,
 * so anything that mutates a module-level path risks a mid-run surprise. A wipe in
 * `globalSetup` runs exactly once, in one process, at a defined point.
 */

import { rmSync } from 'node:fs';
import { request } from '@playwright/test';
import { MUT_API_BASE, MUT_WORKSPACE, SEED } from './env';

export default async function globalSetup() {
  rmSync(MUT_WORKSPACE, { recursive: true, force: true });

  const api = await request.newContext();
  try {
    // The first read re-seeds. Assert the canonical five are back AND that each is
    // at its baseline, because a wipe that silently failed would otherwise look
    // exactly like a successful one until an assertion downstream got strange.
    const res = await api.get(`${MUT_API_BASE}/experiments`);
    if (!res.ok()) {
      throw new Error(`[mutation-setup] GET /experiments failed: ${res.status()}`);
    }
    const body = await res.json();
    const rows = Array.isArray(body) ? body : (body.experiments ?? []);
    if (rows.length !== 5) {
      throw new Error(
        `[mutation-setup] expected the canonical five after the wipe, got ${rows.length}. ` +
          `The workspace at ${MUT_WORKSPACE} may not be the one the backend is using — ` +
          `check that ISAAC_UI_WORKSPACE reached the uvicorn process.`
      );
    }

    for (const id of Object.values(SEED)) {
      const d = await api.get(`${MUT_API_BASE}/experiments/${id}`);
      if (!d.ok()) throw new Error(`[mutation-setup] ${id} missing after re-seed`);
      const detail = await d.json();
      if (detail.rev !== 0) {
        throw new Error(
          `[mutation-setup] ${id} is at rev=${detail.rev}, not 0. The wipe did not take, ` +
            `so this run would inherit a previous run's mutations — the exact drift this ` +
            `setup exists to stop.`
        );
      }
    }
    // eslint-disable-next-line no-console
    console.log(`[mutation-setup] hermetic: 5 canonical records, all at rev 0.`);
  } finally {
    await api.dispose();
  }
}

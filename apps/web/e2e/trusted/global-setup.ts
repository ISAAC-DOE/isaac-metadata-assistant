/**
 * Make the trusted-identity suite HERMETIC, and ASSERT ITS PREMISE BEFORE IT RUNS.
 *
 * ── Why the wipe ────────────────────────────────────────────────────────────
 *
 * The same bug the mutation suite's setup exists to prevent: with a fixed workspace
 * directory and `reuseExistingServer` locally, a run inherits the previous run's
 * records, and assertions about "a record with two runs" quietly become assertions
 * about accumulated history. Deleting the directory while the backend is already
 * running is safe because the workspace layer is not an in-memory cache —
 * `_load_all_experiments()` reads the directory on every request.
 *
 * ── Why the ORDINARY scope, and no worked-example session ───────────────────
 *
 * This suite's subject is a record the PRODUCT created. `POST /api/experiments` is
 * the product's own creation path and it works in the ordinary scope; a record made
 * that way takes runs. The five canonical examples are irrelevant here and are
 * deliberately not materialised — no session is opened, so no session header is
 * attached anywhere and a stray one would 404 loudly rather than reading from the
 * wrong scope.
 *
 * There is a second, load-bearing reason. `identity.stamp_actor` returns `None`
 * **unconditionally and first** inside a worked-example session, so an acceptance
 * there is recorded UNATTRIBUTED even under the fixture verifier
 * (`test_ingestion_proposals.py::test_I7_an_acceptance_inside_a_tutorial_session_is_unattributed`).
 * Attribution is one of the things this suite measures, so a session would have made
 * the measurement impossible.
 *
 * ── Why the premise is asserted from the server ─────────────────────────────
 *
 * Every acceptance below depends on the backend having been started with
 * `ISAAC_EDGE_TRUST_VERIFIER=test_fixture`. If that variable ever failed to reach
 * the uvicorn process, every accept would answer `409 human_actor_required` and the
 * specs would fail on a button that stayed put — which reads exactly like a product
 * defect and is a wiring error. So the configuration is read back off
 * `/api/health`, from the server's own report, and a mismatch aborts the run with a
 * sentence naming the cause.
 */

import { rmSync } from 'node:fs';
import { request } from '@playwright/test';
import { FIXTURE_TRUST_BASIS, TRUSTED_API_BASE, TRUSTED_WORKSPACE } from './env';

export default async function globalSetup() {
  rmSync(TRUSTED_WORKSPACE, { recursive: true, force: true });

  const api = await request.newContext();
  try {
    // 1. THE PREMISE. Asserted first, because everything else depends on it.
    const health = await api.get(`${TRUSTED_API_BASE}/health`);
    if (!health.ok()) {
      throw new Error(`[trusted-setup · 1/2] GET /health failed: ${health.status()}`);
    }
    const body = (await health.json()) as {
      submission?: { verifier_id?: string; actor_trust_basis?: string };
    };
    const verifier = body.submission?.verifier_id;
    if (verifier !== FIXTURE_TRUST_BASIS) {
      throw new Error(
        `[trusted-setup · 1/2 premise] the backend reports verifier_id=${JSON.stringify(
          verifier
        )}, expected ${JSON.stringify(FIXTURE_TRUST_BASIS)}. Acceptance would answer ` +
          `409 human_actor_required and every spec here would fail on a button that ` +
          `did not move — which reads like a product defect and is a wiring error. ` +
          `Check that ISAAC_EDGE_TRUST_VERIFIER reached the uvicorn process.`
      );
    }
    if (body.submission?.actor_trust_basis !== FIXTURE_TRUST_BASIS) {
      throw new Error(
        `[trusted-setup · 1/2 premise] verifier_id is right but actor_trust_basis is ` +
          `${JSON.stringify(body.submission?.actor_trust_basis)}; ` +
          `ISAAC_FIXTURE_ACTOR_SUBJECT is probably unset.`
      );
    }

    // 2. HERMETIC. The ordinary workspace holds nothing; every record these specs
    //    reason about is one they create. A leftover would make "the record with two
    //    runs" ambiguous on a screen that lists them all.
    const listed = await api.get(`${TRUSTED_API_BASE}/experiments`);
    if (!listed.ok()) {
      throw new Error(`[trusted-setup · 2/2] GET /experiments failed: ${listed.status()}`);
    }
    const rows = ((await listed.json()) as { experiments?: unknown[] }).experiments ?? [];
    if (rows.length !== 0) {
      throw new Error(
        `[trusted-setup · 2/2 empty scope] expected 0 experiments in the ordinary ` +
          `workspace, got ${rows.length}. The workspace at ${TRUSTED_WORKSPACE} may not ` +
          `be the one the backend is using — check that ISAAC_UI_WORKSPACE reached the ` +
          `uvicorn process.`
      );
    }

    // eslint-disable-next-line no-console
    console.log(
      `[trusted-setup] hermetic: ordinary workspace empty; backend attributes through ` +
        `the ${FIXTURE_TRUST_BASIS} verifier, so acceptance is reachable.`
    );
  } finally {
    await api.dispose();
  }
}

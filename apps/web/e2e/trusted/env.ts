/**
 * Ports, paths and constants for the TRUSTED-IDENTITY browser suite.
 *
 * Every port differs from the read-only suite's (5173/8000) and from the mutation
 * suite's (5274/8100), so all three can run side by side on one machine without one
 * silently answering another's requests — which looks like a mysterious data bug
 * rather than a port collision.
 */

import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const TRUSTED_WEB_PORT = process.env.E2E_TRUSTED_WEB_PORT ?? '5275';
export const TRUSTED_API_PORT = process.env.E2E_TRUSTED_API_PORT ?? '8101';

export const TRUSTED_BASE_URL = `http://127.0.0.1:${TRUSTED_WEB_PORT}`;
export const TRUSTED_API_BASE = `http://127.0.0.1:${TRUSTED_API_PORT}/api`;

/**
 * A fixed directory, not a random one: it lets `reuseExistingServer` reuse a warm
 * backend locally, and a failed run leaves an INSPECTABLE workspace behind instead
 * of one whose name died with the process. `globalSetup` wipes it, which is what
 * makes the suite hermetic.
 */
export const TRUSTED_WORKSPACE =
  process.env.E2E_TRUSTED_WORKSPACE ?? join(tmpdir(), 'isaac-e2e-trusted-workspace');

/** Allow a venv uvicorn locally; CI installs it on PATH. */
export const UVICORN = process.env.E2E_UVICORN ?? 'uvicorn';

/**
 * WHO THE BACKEND VOUCHES FOR, and why a browser suite may say this at all.
 *
 * `POST .../proposals/{id}/review` with `action: "accept"` answers **409
 * `human_actor_required`** in every default-configured deployment, because no
 * verifier in this build reads a request and the trusted authentication boundary
 * has not been built (`CLAUDE.md` §15; contract §5 **I4**). That is a fact about
 * CONFIGURATION, not about the build: a deployment setting
 * `ISAAC_EDGE_TRUST_VERIFIER=test_fixture` and `ISAAC_FIXTURE_ACTOR_SUBJECT`
 * selects `FixtureEdgeVerifier` and acceptance succeeds.
 *
 * `apps/web/e2e/mutation/proposals.spec.ts` states why it cannot cover both legs:
 * *"The verifier is chosen from the BACKEND PROCESS's environment, and this suite
 * starts exactly one backend … One process has one configuration, so the refusal
 * leg and the success leg cannot both be measured in one run of one suite."* This
 * is the second process. The mutation suite is UNCHANGED and still measures the
 * refusal that every shipped deployment produces; this one measures the success
 * leg, and its `globalSetup` asserts which configuration it is running under before
 * a single spec runs.
 *
 * NO SHIPPED DEPLOY ARTIFACT SETS THESE TWO VARIABLES — `test_deploy_config.py`
 * pins that — so nothing here makes acceptance reachable in any real deployment.
 */
export const FIXTURE_ACTOR_SUBJECT =
  process.env.E2E_TRUSTED_ACTOR ?? 'synthetic.browser.reviewer';

/** The trust basis `FixtureEdgeVerifier` labels everything it attributes with. */
export const FIXTURE_TRUST_BASIS = 'test_fixture';

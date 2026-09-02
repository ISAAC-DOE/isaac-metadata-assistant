/**
 * THE TRUSTED-IDENTITY BROWSER SUITE — a third config, and the separation is the
 * whole design.
 *
 * WHY IT CANNOT LIVE IN THE MUTATION SUITE. `apps/web/e2e/mutation/proposals.spec.ts`
 * measures that an acceptance is REFUSED — `409 human_actor_required` — and asserts
 * that premise from the server before it does so, because that refusal is what every
 * shipped deployment produces and is the behaviour a scientist meets. The verifier
 * is chosen from the BACKEND PROCESS's environment, and that suite starts exactly one
 * backend. One process has one configuration, so the refusal leg and the success leg
 * cannot both be measured in one run of one suite. That spec says so itself.
 *
 * So this is the second process: its own backend, on its own port, with its own
 * `ISAAC_UI_WORKSPACE`, started with `ISAAC_EDGE_TRUST_VERIFIER=test_fixture` and
 * `ISAAC_FIXTURE_ACTOR_SUBJECT`. THE MUTATION SUITE IS UNCHANGED — its refusal test
 * still runs, against a backend that still refuses.
 *
 * NOTHING HERE MAKES ACCEPTANCE REACHABLE IN A DEPLOYMENT. No shipped deploy artifact
 * sets either variable (`apps/api/tests/test_deploy_config.py` pins that, scanning the
 * `Dockerfile`, `build-push.yaml` and `pr-docker-smoke.yml`), and this config is not
 * one: it starts a local uvicorn for the duration of a test run. MEASURED, rather than
 * assumed, because this file DOES contain the literal: the `Dockerfile` copies
 * `apps/web/` only into the web BUILD stage (`COPY apps/web/ ./`, line 19) and the
 * final stage takes `--from=web /web/dist` alone (line 63), so this file reaches no
 * runtime image — and Vite bundles nothing outside `src/` in any case.
 *
 * ORDINARY SCOPE, NO WORKED-EXAMPLE SESSION. `identity.stamp_actor` returns `None`
 * unconditionally and first inside a tutorial session, so an acceptance there is
 * unattributed even under the fixture verifier. Attribution is one of the things this
 * suite measures, so its records are ordinary ones — created by the product's own
 * Create Experiment path, which is also what makes a record with two runs reachable
 * at all (an exported canonical example refuses `POST .../runs`).
 *
 * ONE viewport project, `workers: 1`, `retries: 0` — the mutation config's reasons,
 * unchanged: these specs assert BEHAVIOUR rather than layout, they mutate shared
 * records, and a retry would re-run a mutation against a workspace the first attempt
 * already changed.
 */

import { defineConfig, devices } from '@playwright/test';
import {
  FIXTURE_ACTOR_SUBJECT,
  TRUSTED_API_BASE,
  TRUSTED_API_PORT,
  TRUSTED_BASE_URL,
  TRUSTED_WEB_PORT,
  TRUSTED_WORKSPACE,
  UVICORN,
} from './e2e/trusted/env';

export default defineConfig({
  testDir: './e2e/trusted',
  globalSetup: './e2e/trusted/global-setup.ts',
  globalTeardown: './e2e/trusted/global-teardown.ts',
  testMatch: /.*\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : [['line']],

  use: {
    baseURL: TRUSTED_BASE_URL,
    ...devices['Desktop Chrome'],
    viewport: { width: 1280, height: 800 },
    // A browser-CONTEXT option, not a top-level test option — the mutation config
    // records paying for that mistake with a comment that claimed an animation kill
    // it never applied.
    contextOptions: { reducedMotion: 'reduce' },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  projects: [{ name: 'trusted-1280x800' }],

  webServer: [
    {
      // `--app-dir apps/api` mirrors the CI step exactly, so a divergence between
      // this suite and CI cannot come from how the backend is launched.
      command: `${UVICORN} isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port ${TRUSTED_API_PORT}`,
      cwd: '../..',
      url: `${TRUSTED_API_BASE}/health`,
      env: {
        ISAAC_UI_WORKSPACE: TRUSTED_WORKSPACE,
        // REQUIRED: the backend's CORS allowlist defaults to the standard Vite dev
        // origins, and this suite runs on neither. Without it every fetch from the
        // page is blocked and the app renders its honest "ISAAC Is Not Responding"
        // panel — which fails as "heading not found" and reads like a UI regression.
        ISAAC_UI_CORS_ORIGINS: TRUSTED_BASE_URL,
        // THE TWO VARIABLES THIS SUITE EXISTS FOR. `globalSetup` reads the resulting
        // configuration back off `/api/health` and aborts the run if it did not
        // arrive, because the symptom otherwise is a button that does not move.
        ISAAC_EDGE_TRUST_VERIFIER: 'test_fixture',
        ISAAC_FIXTURE_ACTOR_SUBJECT: FIXTURE_ACTOR_SUBJECT,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${TRUSTED_WEB_PORT} --strictPort`,
      url: TRUSTED_BASE_URL,
      env: {
        // THE app-side wiring. Without this the page talks to the default
        // 127.0.0.1:8000 and every spec fails with "Backend Not Running".
        VITE_API_BASE: TRUSTED_API_BASE,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
  ],
});

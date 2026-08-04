/**
 * R3 · the MUTATION browser suite — deliberately a separate config from
 * `playwright.config.ts`, and the separation is the whole design.
 *
 * WHY NOT JUST ADD SPECS TO THE EXISTING SUITE. That suite is read-only by
 * contract: `e2e/global-setup.ts` opens ONE worked-example session and never
 * writes into it (it never resets, never creates a record, never deletes one), and
 * five viewport projects then read that one session in parallel. Its assertions
 * are about canonical seed CONTENT — a pending count, a specific answered value,
 * an export state. A spec that answers a question or exports a record changes
 * exactly those things, so adding mutation specs there would make the read-only
 * specs fail depending on scheduling. That is not a flaky test; it is two suites
 * with incompatible requirements sharing state.
 *
 * SO THIS SUITE GETS ITS OWN EVERYTHING:
 *
 *   · its own backend process, on its own port,
 *   · its own `ISAAC_UI_WORKSPACE` directory, wiped by `globalSetup`,
 *   · its own WORKED-EXAMPLE SESSION inside that workspace — which is where the
 *     canonical five now live at all, the ordinary workspace being permanently
 *     empty. `globalSetup` opens it and publishes its id; `globalTeardown`
 *     discards it; the auto-use `scope` fixture puts every page and every direct
 *     API read into it,
 *   · its own Vite dev server, built with `VITE_API_BASE` pointing at that
 *     backend — this is load-bearing and easy to get wrong: the APP reads
 *     `VITE_API_BASE`, while `E2E_API_BASE` only configures the test harness. Set
 *     only the latter and the page silently talks to port 8000 and renders
 *     "Backend Not Running".
 *   · `workers: 1` and `fullyParallel: false`, because these specs mutate shared
 *     records and their assertions depend on order within a file.
 *
 * ONE viewport project, not five. These specs assert BEHAVIOUR (a request went out,
 * a value survived a reload, a stale precondition was refused) — none of which is
 * viewport-dependent. Layout and accessibility at five widths are the other
 * suite's job, and duplicating mutation flows across widths would quintuple the
 * slowest tests in the repo to re-prove the same backend contract.
 *
 * `retries: 0` ON PURPOSE. A retry re-runs a mutation against a workspace the
 * first attempt already changed, so a "flaky pass" here would be meaningless — and
 * worse, it would hide a real ordering bug. If one of these fails, it must fail.
 */

import { defineConfig, devices } from '@playwright/test';
import { MUT_API_BASE, MUT_API_PORT, MUT_BASE_URL, MUT_WEB_PORT, MUT_WORKSPACE, UVICORN } from './e2e/mutation/env';

export default defineConfig({
  testDir: './e2e/mutation',
  // Wipes the isolated workspace so a run cannot inherit the previous run's
  // mutations, then opens the worked-example session the canonical records live
  // in. See the file for why a directory wipe rather than the reset route.
  globalSetup: './e2e/mutation/global-setup.ts',
  globalTeardown: './e2e/mutation/global-teardown.ts',
  testMatch: /.*\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : [['line']],

  use: {
    baseURL: MUT_BASE_URL,
    ...devices['Desktop Chrome'],
    viewport: { width: 1280, height: 800 },
    /*
     * Same animation kill as the read-only suite: a measurement or a click taken
     * mid-transition is the classic source of flaky browser assertions.
     *
     * IT WAS WRITTEN AS A BARE `reducedMotion: 'reduce'` AND SILENTLY DID NOTHING.
     * `reducedMotion` is not a top-level test option in @playwright/test 1.62 (only
     * `colorScheme`, `deviceScaleFactor`, `hasTouch`, `isMobile`, `locale` and
     * `timezoneId` are) — it is a browser-CONTEXT option, which is why
     * `playwright.config.ts` sets it under `contextOptions` and says so in a
     * comment. An unknown key in `use` is not a runtime error, so the comment above
     * claimed an animation kill that was never applied.
     *
     * It surfaced the moment this config was added to `e2e/tsconfig.json`'s
     * `include` (it was the one Playwright config the typecheck did not see):
     * TS2769, "'reducedMotion' does not exist in type 'UseOptions<…>'".
     */
    contextOptions: { reducedMotion: 'reduce' },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  projects: [{ name: 'mutation-1280x800' }],

  // Two servers, started in order. Playwright waits for each `url` to answer
  // before starting the tests, so no spec can race the backend's first boot.
  webServer: [
    {
      // `--app-dir apps/api` mirrors the CI step exactly, so a divergence between
      // this suite and CI cannot come from how the backend is launched.
      command: `${UVICORN} isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port ${MUT_API_PORT}`,
      cwd: '../..',
      url: `${MUT_API_BASE}/health`,
      env: {
        // Isolated workspace. `ensure_seeded()` fills it on first read.
        ISAAC_UI_WORKSPACE: MUT_WORKSPACE,
        // REQUIRED, and the failure it prevents is very confusing without this
        // comment. The backend's CORS allowlist defaults to the standard Vite dev
        // origins (5173/5174); this suite deliberately runs on a different port, so
        // without an override every fetch from the page is blocked and the app
        // renders its honest "ISAAC Is Not Responding" panel. The test then fails
        // with "heading not found", which reads like a UI regression rather than a
        // network policy. `ISAAC_UI_CORS_ORIGINS` is the backend's own supported
        // override — no production code changes to accommodate the tests.
        ISAAC_UI_CORS_ORIGINS: MUT_BASE_URL,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${MUT_WEB_PORT} --strictPort`,
      url: MUT_BASE_URL,
      env: {
        // THE app-side wiring. Without this the page talks to the default
        // 127.0.0.1:8000 and every spec fails with "Backend Not Running".
        VITE_API_BASE: MUT_API_BASE,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
  ],
});

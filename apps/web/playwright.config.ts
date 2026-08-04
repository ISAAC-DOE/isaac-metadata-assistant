/**
 * Real-browser accessibility + responsive baseline for the ISAAC SPA.
 *
 * Chromium only. Nothing in this suite is picked up by vitest: `vite.config.ts`
 * scopes vitest to `include: ['src/**\/*.{test,spec}.{ts,tsx}']`, and every file
 * here lives under `apps/web/e2e/`. Keep it that way — moving a `*.spec.ts`
 * into `src/` would have vitest try to run Playwright specs in jsdom.
 *
 * ── The five dimensions ─────────────────────────────────────────────────────
 *
 *   desktop-1280x800   the reference layout
 *   laptop-1024x768    the first sidebar/grid reflow
 *   tablet-768x1024    portrait tablet
 *   mobile-375x812     phone; crosses the `max-width: 640px` breakpoint
 *   zoom-200           the LAYOUT-LEVEL EQUIVALENT of 200% browser zoom — see below
 *
 * ── How 200% zoom is emulated, exactly ──────────────────────────────────────
 *
 * A user who presses Cmd/Ctrl-+ twice in a 1280x800 window gets, in the page:
 *
 *   * a CSS LAYOUT VIEWPORT of 640x400 CSS px — every `@media (max-width: …)`
 *     query, every `vw`/`vh` unit and every flex/grid reflow sees 640, and
 *   * `window.devicePixelRatio` DOUBLED (1 → 2), because one CSS px now covers
 *     two device px.
 *
 * So the project is `{ viewport: { width: 640, height: 400 }, deviceScaleFactor: 2 }`.
 * That is genuinely distinct from the other projects: it is NOT the 375px phone
 * case (different breakpoint, different DPR) and it is NOT "a 640px window",
 * which would have DPR 1. `specs/zoom-200.spec.ts` asserts both numbers in the
 * live page, so the emulation's PARAMETERS are proved rather than assumed.
 * (Proving the parameters is not the same as proving fidelity: DPR contributes
 * nothing to CSS layout — 640x400@DPR2 and 640x400@DPR1 measure byte-identical
 * innerWidth, clientWidth and media-query state. The reflow under test comes
 * entirely from the 640px width; the DPR assertion is a fidelity guard against
 * someone quietly dropping it, not a source of layout signal.)
 *
 * `document.body.style.zoom` is deliberately NOT used. It is a non-standard
 * rendering quirk that scales a subtree without changing the layout viewport,
 * so media queries do not fire — the opposite of what browser zoom does.
 *
 * CDP `Emulation.setPageScaleFactor` was evaluated and rejected: it is
 * PINCH zoom (a visual-viewport transform). It magnifies without reflowing and
 * without changing `devicePixelRatio`, so it would test even less than the
 * `zoom` property does.
 *
 * HONEST LIMITS of this emulation, all of which belong in any report that
 * cites it:
 *   * `window.outerWidth` stays 640 here; under real zoom it would still read
 *     1280 while `innerWidth` read 640. A page that measured `outerWidth` would
 *     behave differently.
 *   * Real zoom also scales the browser's own scrollbar and chrome; headless
 *     Chromium has neither.
 *   * Real zoom applies a `visualViewport.scale`; here the scale stays 1 and
 *     the effect is reproduced through viewport size + DPR.
 *   * Font boundary effects differ slightly: a real zoom rounds text metrics at
 *     the zoomed scale, and DPR-2 rasterisation is close but not identical.
 *   * It does not test OS-level text scaling, browser minimum-font-size, or
 *     `text-size-adjust` — those are separate settings a user can also change.
 *
 * ── Determinism ─────────────────────────────────────────────────────────────
 * Fixed locale, fixed timezone, forced light color-scheme (the app declares
 * `<meta name="color-scheme" content="light">`), and `reducedMotion: 'reduce'`
 * so the app's own reduced-motion CSS (`src/styles/base.css:258`) applies. The
 * `fixtures.ts` `app` helper additionally injects a stylesheet that zeroes any
 * animation that media query does not reach.
 *
 * ── Servers ─────────────────────────────────────────────────────────────────
 * Playwright starts the VITE server. It does NOT start the FastAPI backend —
 * that needs the repo's Python venv, which lives outside `apps/web`. The
 * backend is an asserted external precondition; `global-setup.ts` fails fast
 * with the exact command if it is missing. It runs with no database and no
 * credentials.
 *
 * ── Workspace scopes ────────────────────────────────────────────────────────
 * TWO scopes are in play and the suite is explicit about which one each spec is
 * in. The ordinary workspace is permanently EMPTY; the five built-in example
 * records exist only inside a worked-example session. `global-setup.ts` opens
 * ONE such session for the whole run and `global-teardown.ts` discards it, and
 * the suite stays read-only against BOTH — which is what still lets the five
 * viewport projects share one backend. See `e2e/worked-example.ts`.
 */

import { defineConfig, type PlaywrightTestConfig, type Project } from '@playwright/test';
import { BASE_URL, MANAGE_WEB_SERVER, WEB_HOST, WEB_PORT } from './e2e/env';

/** Tag → which viewport projects a spec runs in. See the spec headers. */
const ALL_VIEWPORTS = /@responsive/;
const INTERACTION = /@interaction/;
const ZOOM_ONLY = /@zoom/;

const viewportProject = (
  name: string,
  width: number,
  height: number,
  deviceScaleFactor: number,
  grep: RegExp
): Project => ({
  name,
  grep,
  use: {
    browserName: 'chromium',
    viewport: { width, height },
    deviceScaleFactor,
    // Keep these as plain desktop Chromium: `isMobile`/`hasTouch` would change
    // the input model as well as the size, and this suite is about layout and
    // accessibility at a width, not about touch emulation. Stated so nobody
    // reads "mobile-375x812" as "tested on a phone".
    isMobile: false,
    hasTouch: false,
  },
});

const REPORTER: PlaywrightTestConfig['reporter'] = process.env.CI
  ? [
      ['github'],
      ['list'],
      ['html', { open: 'never' }],
      ['json', { outputFile: 'test-results/e2e-results.json' }],
    ]
  : [['list'], ['html', { open: 'never' }]];

export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.spec\.ts$/,
  // Setup opens the ONE worked-example session this run's record surfaces live
  // in and publishes its id; teardown discards it. Teardown is idempotent and
  // never fails the run — see the two files.
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',

  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  timeout: 60_000,
  expect: { timeout: 10_000 },

  reporter: REPORTER,

  use: {
    baseURL: BASE_URL,
    locale: 'en-US',
    timezoneId: 'UTC',
    colorScheme: 'light',
    // `reducedMotion` is not a top-level test option in @playwright/test 1.62
    // (only `colorScheme`, `deviceScaleFactor`, `hasTouch`, `isMobile`,
    // `locale` and `timezoneId` are) — it is a browser-context option, so it
    // is set here. Effect is identical: the context reports
    // `prefers-reduced-motion: reduce`, which engages the app's own
    // reduced-motion CSS in `src/styles/base.css:258`.
    contextOptions: { reducedMotion: 'reduce' },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },

  projects: [
    // Reference desktop also carries the interaction specs (dialogs, tabs,
    // keyboard, states) — running those five times would multiply runtime for
    // very little extra signal.
    viewportProject('desktop-1280x800', 1280, 800, 1, new RegExp(`${ALL_VIEWPORTS.source}|${INTERACTION.source}`)),
    viewportProject('laptop-1024x768', 1024, 768, 1, ALL_VIEWPORTS),
    viewportProject('tablet-768x1024', 768, 1024, 1, ALL_VIEWPORTS),
    // Phone width ALSO runs the interaction specs: the `max-width: 640px`
    // breakpoint changes the chrome, so dialog/keyboard behaviour there is not
    // implied by the desktop run.
    viewportProject('mobile-375x812', 375, 812, 1, new RegExp(`${ALL_VIEWPORTS.source}|${INTERACTION.source}`)),
    // 200% browser zoom of a 1280x800 window. See the header comment.
    viewportProject('zoom-200', 640, 400, 2, new RegExp(`${ALL_VIEWPORTS.source}|${ZOOM_ONLY.source}`)),
  ],

  webServer: MANAGE_WEB_SERVER
    ? {
        command: `npx vite --host ${WEB_HOST} --port ${WEB_PORT} --strictPort`,
        url: BASE_URL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        stdout: 'ignore',
        stderr: 'pipe',
      }
    : undefined,
});

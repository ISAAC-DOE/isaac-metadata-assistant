/**
 * Shared fixtures.
 *
 * The synthetic workspace is seeded ONCE, in `global-setup.ts`, before any
 * worker starts — not per test, and not per file. Every spec in this suite is
 * read-only against that workspace, so no fixture needs to re-seed or reset,
 * and the five viewport projects can run in parallel without racing each other.
 *
 * What this file adds on top of the stock `test`:
 *
 *   * `app.open(surface)` — navigate and wait for the surface's `ready`
 *     locator, so no spec ever scans a loading skeleton.
 *   * a hard stop on animation: `reducedMotion: 'reduce'` in the config makes
 *     the app's own `@media (prefers-reduced-motion: reduce)` rules apply
 *     (`src/styles/base.css:258`), and the injected stylesheet below zeroes
 *     everything those rules do not reach. Layout measurements taken mid
 *     transition are the classic source of flaky responsive assertions.
 *   * `consoleErrors` — page errors collected for the specs that care.
 */

import { test as base, expect, type Locator, type Page } from '@playwright/test';
import type { Surface } from './surfaces';

/**
 * Belt-and-braces animation kill. `reducedMotion: 'reduce'` is the honest
 * mechanism (it is what a real user with that OS setting gets); this stylesheet
 * exists only so that a component which forgot to honour the media query
 * cannot make a measurement flaky.
 */
const NO_MOTION_CSS = `
*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  animation-iteration-count: 1 !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
  scroll-behavior: auto !important;
  caret-color: transparent !important;
}`;

/**
 * The shared loading panel (`components/FetchStates.tsx` → `LoadingPanel`).
 * `.fetch-state.error` is the failure state and carries `role="alert"`, so
 * pinning the role to `status` keeps the two apart.
 */
export const LOADING_PANEL = 'div.fetch-state[role="status"]';

export interface AppHelper {
  /** Navigate to a catalogued surface and wait until its data has landed. */
  open(surface: Surface): Promise<void>;
  /** Navigate to an arbitrary in-app path and wait for `<main>`. */
  goto(path: string): Promise<void>;
  /** The app's `<main>` landmark. */
  main(): Locator;
  /** True while any `LoadingPanel` is on screen. */
  isLoading(): Promise<boolean>;
}

function makeApp(page: Page): AppHelper {
  return {
    async goto(path: string) {
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await page.addStyleTag({ content: NO_MOTION_CSS });
      await expect(page.locator('main#main')).toBeVisible();
    },
    async open(surface: Surface) {
      await this.goto(surface.path);
      await expect(page.getByRole(surface.ready.role, { name: surface.ready.name }).first()).toBeVisible({
        timeout: 20_000,
      });
      // Wait the loading panel out rather than sleeping. Match on the CLASS,
      // not the text: `LoadingPanel` takes a per-call label ("Loading your
      // experiments…", "Loading the API contract…", …), so an exact-text wait
      // on "Loading…" silently matched nothing and did no waiting at all.
      await expect(page.locator(LOADING_PANEL)).toHaveCount(0, { timeout: 20_000 });
      // Several surfaces mount a second pane from a follow-up fetch (Assistant,
      // evidence trail, the Endpoint Explorer detail). Scanning between the two
      // renders produced intermittent heading-order failures, so settle first.
      // Bounded and non-fatal: a page with a long-poll would otherwise hang here.
      await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => undefined);
    },
    main() {
      return page.locator('main#main');
    },
    async isLoading() {
      return (await page.locator(LOADING_PANEL).count()) > 0;
    },
  };
}

export const test = base.extend<{ app: AppHelper; consoleErrors: string[] }>({
  app: async ({ page }, use) => {
    await use(makeApp(page));
  },
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    page.on('pageerror', (err) => errors.push(String(err)));
    await use(errors);
  },
});

export { expect };

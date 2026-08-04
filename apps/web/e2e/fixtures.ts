/**
 * Shared fixtures.
 *
 * ── Scope, in one line per spec ─────────────────────────────────────────────
 *
 * The five built-in example records exist only inside a worked-example session.
 * `global-setup.ts` opens ONE session for the whole read-only run and publishes
 * its id; `app.open(surface)` enters that scope automatically when the surface
 * declares `scope: 'example'`, before it navigates, because `lib/api.ts` fixes
 * the scope at module load and anything later 404s. A spec that navigates by
 * hand instead of by surface calls `app.gotoExample(path)`.
 *
 * So no spec repeats an `addInitScript`/`page.route` incantation, and no spec is
 * silently in a scope it did not ask for: `app.goto()` stays ORDINARY, which is
 * the empty workspace, which is what the ordinary-scope specs assert.
 *
 * ── Read-only, and how the parallel projects stay safe ──────────────────────
 *
 * Every spec reached through this fixture is read-only against both shared
 * scopes: no fixture seeds, resets, answers, exports or deletes, so the five
 * viewport projects can run against one backend without racing. Entering the
 * example scope adds a request HEADER; it writes nothing.
 *
 * The specs that DO mutate a session (`specs/tutorial.spec.ts`) never touch the
 * shared session. They use the `tutorial` fixture below, which mints a session
 * per test through the real UI and disposes every session that test created —
 * so a mutation can never be scheduled against a scope another project is
 * measuring.
 *
 * ── What else this file adds on top of the stock `test` ─────────────────────
 *
 *   * `app.open(surface)` — enter the surface's scope, navigate, and wait for
 *     the surface's `ready` locator, so no spec ever scans a loading skeleton.
 *   * a hard stop on animation: `reducedMotion: 'reduce'` in the config makes
 *     the app's own `@media (prefers-reduced-motion: reduce)` rules apply
 *     (`src/styles/base.css:258`), and the injected stylesheet below zeroes
 *     everything those rules do not reach. Layout measurements taken mid
 *     transition are the classic source of flaky responsive assertions.
 *   * `consoleErrors` — page errors collected for the specs that care.
 *   * `tutorial` — real-walkthrough helpers plus guaranteed session disposal.
 */

import { test as base, expect, type Locator, type Page } from '@playwright/test';
import { API_BASE } from './env';
import type { Surface } from './surfaces';
import {
  TUTORIAL_SESSION_HEADER,
  disposeWorkedExampleSession,
  enterWorkedExample,
  markTutorialCompletedInBrowser,
} from './worked-example';

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
  /** Navigate to a catalogued surface, in ITS declared scope, and wait until its
   *  data has landed. */
  open(surface: Surface): Promise<void>;
  /** Navigate to an arbitrary in-app path in the ORDINARY scope and wait for
   *  `<main>`. The ordinary workspace is empty, so this reaches no record. */
  goto(path: string): Promise<void>;
  /** Navigate to an arbitrary in-app path inside the run's shared worked-example
   *  session. Use for the record paths a surface does not cover. */
  gotoExample(path: string): Promise<void>;
  /** Enter the shared worked-example scope WITHOUT navigating — for a spec that
   *  drives `page.goto` itself (e.g. one asserting a loading state). */
  enterExampleScope(): Promise<string>;
  /** The app's `<main>` landmark. */
  main(): Locator;
  /** True while any `LoadingPanel` is on screen. */
  isLoading(): Promise<boolean>;
}

function makeApp(page: Page): AppHelper {
  const settle = async (path: string) => {
    await page.goto(path, { waitUntil: 'domcontentloaded' });
    await page.addStyleTag({ content: NO_MOTION_CSS });
    await expect(page.locator('main#main')).toBeVisible();
  };

  return {
    async goto(path: string) {
      await settle(path);
    },
    async enterExampleScope() {
      return enterWorkedExample(page);
    },
    async gotoExample(path: string) {
      await enterWorkedExample(page);
      await settle(path);
    },
    async open(surface: Surface) {
      // BEFORE the navigation, always. The scope is applied to the page's
      // requests, and the first request the app makes is issued during its
      // initial render.
      if (surface.scope === 'example') await enterWorkedExample(page);
      await settle(surface.path);
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

/**
 * Real-walkthrough support.
 *
 * `sessionsCreated` is observed from the wire rather than from anything the test
 * declares: every `201` from `POST /api/tutorial/sessions` is recorded, whoever
 * caused it. That is what makes two of the guarantees testable —
 * "Replay creates exactly ONE session" is an assertion about this list, and
 * "no session is left behind" is enforced by disposing every id in it after the
 * test, whether or not the test reached an exit path.
 *
 * Disposal is idempotent (204 for an absent session), so cleaning up a session
 * the UI already discarded is a no-op rather than an error.
 */
export interface TutorialHelper {
  /** Session ids the PAGE caused the backend to mint, in order. */
  sessionsCreated(): string[];
  /** Suppress the first-run offer, as a browser that finished the walkthrough
   *  would. Must be called before the first navigation. */
  markCompleted(): Promise<void>;
  /** Read a record from a session out of band — INDEPENDENT verification only. */
  readRecordInSession(sessionId: string, recordId: string): Promise<{ status: number; rev?: number }>;
  /** List a session's records out of band. */
  listInSession(sessionId: string): Promise<{ status: number; ids: string[] }>;
}

export const test = base.extend<{ app: AppHelper; consoleErrors: string[]; tutorial: TutorialHelper }>({
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
  tutorial: async ({ page, request }, use) => {
    const created: string[] = [];
    page.on('response', (res) => {
      if (res.status() !== 201) return;
      if (!/\/api\/tutorial\/sessions$/.test(new URL(res.url()).pathname)) return;
      void res
        .json()
        .then((body: { session_id?: string }) => {
          if (typeof body.session_id === 'string') created.push(body.session_id);
        })
        .catch(() => undefined);
    });

    await use({
      sessionsCreated: () => [...created],
      markCompleted: () => markTutorialCompletedInBrowser(page),
      readRecordInSession: async (sessionId, recordId) => {
        const res = await request.get(`${API_BASE}/experiments/${recordId}`, {
          headers: { [TUTORIAL_SESSION_HEADER]: sessionId },
          failOnStatusCode: false,
        });
        if (!res.ok()) return { status: res.status() };
        const body = (await res.json()) as { rev?: number };
        return { status: res.status(), rev: body.rev };
      },
      listInSession: async (sessionId) => {
        const res = await request.get(`${API_BASE}/experiments`, {
          headers: { [TUTORIAL_SESSION_HEADER]: sessionId },
          failOnStatusCode: false,
        });
        if (!res.ok()) return { status: res.status(), ids: [] };
        const body = (await res.json()) as { experiments?: { id: string }[] };
        return { status: res.status(), ids: (body.experiments ?? []).map((e) => e.id) };
      },
    });

    // Dispose everything this test caused to exist, in reverse order. Failures
    // are swallowed: the backend's TTL sweep reclaims a session, and a cleanup
    // error must not turn a passing test red.
    for (const id of [...created].reverse()) {
      await disposeWorkedExampleSession(id).catch(() => undefined);
    }
  },
});

export { expect };

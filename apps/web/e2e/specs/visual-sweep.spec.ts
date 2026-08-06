/**
 * VISUAL STATE SWEEP — the application's real rendered states, at every width
 * the product claims to support, captured as reviewable CI artifacts with real
 * assertions attached.
 * @responsive
 *
 * ── What this file is for, and what it deliberately is NOT ───────────────────
 *
 * It exists because the suite could prove a great deal ABOUT the layout and
 * could show a human almost NONE of it. `layout-widths.spec.ts` measures seven
 * widths and reports numbers; `states.spec.ts` drives the loading / error /
 * refused / empty states and asserts their semantics; nothing produced an image
 * anyone could look at. This does: every state below is reached through the real
 * UI against the real backend, screenshotted, and ATTACHED to the Playwright
 * report, so the `playwright-report` artifact is a per-width contact sheet of
 * the product.
 *
 * IT IS NOT A PIXEL BASELINE. `toHaveScreenshot` is not used and no PNG is
 * committed, for three separate reasons, each sufficient on its own:
 *
 *   * there is no webfont, so `--font-ui` resolves to SF Pro on macOS and to a
 *     DejaVu/Liberation face on `ubuntu-latest` (the same fact that forces the
 *     per-platform columns in `layout-baseline.ts`). A committed baseline would
 *     be permanently, unfixably flaky across the two;
 *   * CLAUDE.md §9 forbids committing generated or derived artifacts;
 *   * a pixel diff answers "did anything change?", which is not the question a
 *     visual review asks. The assertions below answer the questions that have
 *     objective answers, and the images are for the ones that do not.
 *
 * ── Where the images actually come from, stated so nobody over-reads them ────
 *
 * `fullPage: true` is passed, and on most of these screens it captures exactly
 * the visible frame — because THIS APP'S SCROLL CONTAINER IS NOT THE DOCUMENT.
 * `div.screen-card` is `overflow: hidden` and `main#main` is `overflow: auto`
 * (see the `findClippedText` note in `helpers/layout.ts` about that nesting), so
 * the document's scrollHeight equals its clientHeight and "full page" and "the
 * frame" are the same picture. The viewport is therefore 900px tall rather than
 * the 812 `layout-widths.spec.ts` uses, purely to put more of each screen in the
 * shot. A reviewer must not read an attachment as "the whole screen"; it is the
 * first screenful, which is what a reader sees before scrolling.
 *
 * ── One project, seven widths ───────────────────────────────────────────────
 *
 * Same mechanism and the same reason as `layout-widths.spec.ts`: adding
 * Playwright projects multiplies the WHOLE suite (axe scans included) and
 * perturbs the count-based ratchet in `e2e/a11y-baseline.ts`, so this file runs
 * inside ONE project and moves the viewport itself with `page.setViewportSize`.
 * It is tagged `@responsive` only because that is the tag
 * `playwright.config.ts` maps to more than one project, and then skips
 * everywhere except the host project. The skipped entries are visible in the
 * report on purpose: the restriction is stated, not hidden.
 *
 * 1440 is NEW HERE and in `layout-widths.spec.ts`. No sweep in this suite went
 * above 1280 before, so the widest layout the product renders on an ordinary
 * modern laptop screen was measured by nothing at all.
 *
 * ── The state list is a SET, not a count ────────────────────────────────────
 *
 * `EXPECTED_STATE_IDS` is the declared set and the test asserts that the ids it
 * actually captured EQUAL it. A count could not tell "I captured fewer" from
 * "there was less to capture", and a silent omission is the one outcome this
 * sweep must not be able to produce. A state that cannot be reached fails the
 * test with the reason; nothing is skipped quietly.
 *
 * ── Read-only, including inside the walkthrough ──────────────────────────────
 *
 * Nothing here writes to the shared worked-example session the five viewport
 * projects read (`global-setup.ts` opens it; the `app` fixture enters it
 * read-only). The three walkthrough states and the reset dialog run inside a
 * session this test starts FOR ITSELF through the real UI, which the `tutorial`
 * fixture disposes afterwards — the same arrangement `specs/tutorial.spec.ts`
 * and `specs/dialogs.spec.ts` already use. The reset dialog's preview is a
 * read-only `mode: 'preview'` POST and the typed phrase is never entered. The
 * export CONFLICT state is produced by fulfilling the export POST in the BROWSER
 * with a 409: the request never leaves the page, so no record is written.
 */

import { currentPlatform } from '../a11y-baseline';
import { API_BASE, SEED } from '../env';
import { LOADING_PANEL, expect, test, type AppHelper, type TutorialHelper } from '../fixtures';
import { findClippedText, horizontalPageScroll, render, renderedFontFamily } from '../helpers/layout';
import { SURFACES } from '../surfaces';
import { TUTORIAL_SESSION_STORAGE_KEY } from '../worked-example';
import type { Locator, Page } from '@playwright/test';

/** The single project this file runs in. See the header. */
const HOST_PROJECT = 'desktop-1280x800';

/**
 * The widths swept. 1440 is new (see the header); 320 is the WCAG 1.4.10 reflow
 * width and the narrowest the product claims to support; 390 is the modern
 * iPhone width and sits between the configured 375 and 640.
 *
 * Deliberately the same list as `layout-widths.spec.ts`'s `WIDTHS` MINUS 640:
 * 640 is already a Playwright project of its own (`zoom-200` is 640x400 at DPR
 * 2) and every state below is reached at 768 and 390, which bracket it. Stated
 * rather than left as an apparent oversight.
 */
const WIDTHS = [1440, 1280, 1024, 768, 390, 375, 320] as const;

/** See the header: taller than the width sweep's 812, to show more per shot. */
const VIEWPORT_HEIGHT = 900;

/**
 * THE DECLARED SET. Every id here must be captured at every width, and nothing
 * outside it may be captured. Ordering in `STATES` matters (see the comments
 * there); ordering here does not — the comparison is on sorted sets.
 */
const EXPECTED_STATE_IDS = [
  'tutorial-start',
  'experiments-empty',
  'loading',
  'error',
  'settings',
  'settings-replay',
  'endpoint-explorer',
  'statistics-general',
  'statistics-mine',
  'validator',
  'record-edit',
  'record-confirmation',
  'record-evidence',
  'record-validation',
  'export-blocked',
  'export-success',
  'export-conflict',
  'assistant-answer',
  'tutorial-coach-mark',
  'reset-warning',
  'tutorial-completion',
] as const;

interface Ctx {
  page: Page;
  app: AppHelper;
  tutorial: TutorialHelper;
  width: number;
}

interface VisualState {
  readonly id: (typeof EXPECTED_STATE_IDS)[number];
  /** One line for the report annotation — what a reviewer is looking at. */
  readonly what: string;
  /**
   * Reach the state and return its PRIMARY element: the action the state offers,
   * or — for a state that offers none — the heading or region that IS the state.
   * Must throw (never silently return something else) if the state is not
   * reachable.
   */
  readonly reach: (ctx: Ctx) => Promise<Locator>;
  /**
   * Clean up anything that would leak into the next state (a `page.route`, an
   * open overlay). Runs even when `reach` threw.
   */
  readonly cleanup?: (ctx: Ctx) => Promise<void>;
}

const experimentsSurface = SURFACES.find((s) => s.id === 'experiments')!;

/** Wait out the shared loading panel and any second-pane fetch. Mirrors what
 *  `app.open` does for catalogued surfaces, for the paths that are not one. */
async function settled(page: Page): Promise<void> {
  await expect(page.locator(LOADING_PANEL)).toHaveCount(0, { timeout: 20_000 });
  await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => undefined);
}

/**
 * Open the Assistant, dealing with BOTH shapes it has.
 *
 * COPIED from the private helper in `specs/states.spec.ts` rather than extracted
 * into `e2e/helpers/`, deliberately: that file is the `@interaction` suite's and
 * this is a `@responsive` sweep, and moving a helper out of it would edit a spec
 * this workstream does not own for no behavioural gain. The duplication is ten
 * lines and the reason for both shapes is documented there:
 * `AssistantDrawer` renders ONE `<aside>` that is a static `complementary`
 * landmark at >=1024px and a CSS-hidden slide-over below it.
 */
async function openAssistantPanel(page: Page): Promise<Locator> {
  const trigger = page.locator('button.assistant-drawer-trigger');
  const panel = page.locator('aside.assistant-drawer-panel');
  await expect(panel).toHaveCount(1, { timeout: 20_000 });
  if (await trigger.isVisible()) {
    await trigger.click();
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  }
  await expect(panel).toBeVisible({ timeout: 10_000 });
  return panel;
}

/**
 * The animation kill `fixtures.ts` injects on every `app` navigation. Needed
 * again after a bare `page.reload()`, which `tutorial-completion` uses.
 */
const NO_MOTION_CSS = `
*, *::before, *::after {
  animation-duration: 0s !important;
  transition-duration: 0s !important;
  scroll-behavior: auto !important;
}`;

/**
 * ── THE STATES, in the order they must run ──────────────────────────────────
 *
 * Two ordering constraints, both irreversible-within-a-test:
 *
 *  1. `tutorial-start` is FIRST. It is the first-run offer, and the state after
 *     it calls `tutorial.markCompleted()`, which installs an `addInitScript`
 *     that cannot be uninstalled — from then on the offer never renders again on
 *     this page.
 *  2. the three walkthrough states and `reset-warning` are LAST. A running
 *     walkthrough mounts a coach mark whose second effect NAVIGATES to the
 *     current step's own path (`GuidedTutorial.tsx:137-141`), so any state
 *     measured after it would be a measurement of the overlay's chosen surface
 *     rather than of itself.
 */
const STATES: readonly VisualState[] = [
  {
    id: 'tutorial-start',
    what: 'My Experiments, first visit — the guided-walkthrough offer',
    async reach({ page, app }) {
      await app.open(experimentsSurface);
      const start = page.getByRole('button', { name: 'Start Tutorial' });
      await expect(start).toBeVisible({ timeout: 20_000 });
      return start;
    },
  },
  {
    id: 'experiments-empty',
    what: 'My Experiments in the ordinary workspace — permanently empty, offer already answered',
    async reach({ page, app, tutorial }) {
      // The real mechanism (`localStorage`), so this is the state a reader who
      // finished the walkthrough actually sees — not a hidden test flag.
      await tutorial.markCompleted();
      await app.open(experimentsSurface);
      await expect(page.locator('section.tutorial-offer')).toHaveCount(0);
      await expect(page.locator('.exp-row')).toHaveCount(0);
      const heading = page.getByRole('heading', { name: 'My Experiments' });
      await expect(heading).toBeVisible();
      return heading;
    },
  },
  {
    id: 'loading',
    what: 'A pending fetch — the polite status panel, not a blank screen',
    async reach({ page }) {
      // The request is HELD, not broken: the shared backend is being read by the
      // other viewport projects in parallel and must not be disturbed.
      let release!: () => void;
      const gate = new Promise<void>((r) => (release = r));
      await page.route(`${API_BASE}/experiments`, async (route) => {
        await gate;
        await route.continue();
      });
      // Released on a timer so the route handler cannot outlive the state and
      // hang the navigation the NEXT state performs.
      setTimeout(release, 30_000);

      await page.goto('/experiments', { waitUntil: 'domcontentloaded' });
      const loading = page.locator(LOADING_PANEL);
      await expect(loading).toBeVisible({ timeout: 20_000 });
      await expect(loading).toContainText(/Loading/i);
      return loading;
    },
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'error',
    what: 'An unreachable API — the failure is stated and a retry is offered',
    async reach({ page }) {
      await page.route(`${API_BASE.replace(/\/api$/, '')}/api/**`, (route) =>
        route.abort('connectionrefused')
      );
      await page.goto('/experiments', { waitUntil: 'domcontentloaded' });
      const alert = page.getByRole('alert');
      await expect(alert).toBeVisible({ timeout: 20_000 });
      const retry = page.getByRole('button', { name: /Retry/i });
      await expect(retry).toBeVisible();
      return retry;
    },
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'settings',
    what: 'Settings & API → Overview — runtime status and the boundaries',
    async reach({ page, app }) {
      await app.goto('/settings');
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Runtime Status' });
      await expect(heading).toBeVisible({ timeout: 20_000 });
      return heading;
    },
  },
  {
    id: 'settings-replay',
    what: 'Settings & API → Help & Tutorial — the one permanent home of the replay control',
    async reach({ page, app }) {
      await app.goto('/settings?tab=help');
      await settled(page);
      const replay = page.getByRole('button', { name: 'Replay Tutorial' });
      await expect(replay).toBeVisible({ timeout: 20_000 });
      return replay;
    },
  },
  {
    id: 'endpoint-explorer',
    what: 'Settings & API → Endpoint Explorer — the OpenAPI browser, master + detail',
    async reach({ page, app }) {
      await app.goto('/settings?tab=explorer');
      // The DETAIL pane, not the group list: the list heading renders first and
      // the detail mounts from a follow-up fetch (see `surfaces.ts`).
      await expect(page.getByRole('heading', { name: /\/api\/about/ })).toBeVisible({ timeout: 20_000 });
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Endpoint Explorer' }).first();
      await expect(heading).toBeVisible();
      return heading;
    },
  },
  {
    id: 'statistics-general',
    what: 'Statistics → General ISAAC, ordinary workspace — every figure derived from an empty list',
    async reach({ page, app }) {
      await app.goto('/statistics');
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Workspace at a Glance' });
      await expect(heading).toBeVisible({ timeout: 20_000 });
      return heading;
    },
  },
  {
    id: 'statistics-mine',
    what: 'Statistics → My Stats — the honest UNAVAILABLE gate, no figure invented',
    async reach({ page, app }) {
      await app.goto('/statistics?tab=mine');
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Personal Statistics' });
      await expect(heading).toBeVisible({ timeout: 20_000 });
      return heading;
    },
  },
  {
    id: 'validator',
    what: 'Governance & Safety → Standalone Validator — schema validation of a pasted record',
    async reach({ page, app }) {
      await app.goto('/governance?tab=validator');
      await settled(page);
      const validate = page.getByRole('button', { name: 'Validate', exact: true });
      await expect(validate).toBeVisible({ timeout: 20_000 });
      return validate;
    },
  },
  {
    /*
     * THE FOUR "record" STATES, and a correction to the brief that asked for
     * them. There is no Edit route, no Confirmation route and no Validation
     * route: `routes.ts` defines exactly four record paths — `/record/:id`,
     * `…/complete`, `…/evidence`, `…/export` — and `workflowSteps.ts` names five
     * workflow steps, none of which is "validate". So the four are mapped onto
     * what the app really has, and the mapping is written down rather than
     * implied:
     *
     *   record Edit         → `/record/:id`            the review workbench
     *   record Confirmation → `/record/:id/complete`   the guided question
     *   record Evidence     → `/record/:id/evidence`   the evidence trail
     *   record Validation   → `/record/:id/export` for the record whose official
     *                         DRY RUN passes — i.e. the screen where validation
     *                         is shown and export has not happened yet.
     *
     * Three different records are used and that is the point: the state depends
     * on the record, not on the route. SEED.partial has 2 pending blockers,
     * SEED.ready passes the dry run, SEED.review fails it, SEED.done is exported.
     */
    id: 'record-edit',
    what: 'Record workbench (needs attention) — field groups and the confirmation banner',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.partial}`);
      await settled(page);
      const cta = page.getByRole('button', { name: /Review & Answer/ });
      await expect(cta).toBeVisible({ timeout: 20_000 });
      return cta;
    },
  },
  {
    id: 'record-confirmation',
    what: 'Guided completion — one question, with "I don\'t know" as a first-class answer',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.partial}/complete`);
      await settled(page);
      const confirm = page.getByRole('button', { name: 'Confirm', exact: true });
      await expect(confirm).toBeVisible({ timeout: 20_000 });
      return confirm;
    },
  },
  {
    id: 'record-evidence',
    what: 'Evidence & file preview — the trail, the classification, the sidecar disclosure',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.partial}/evidence`);
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Evidence Trail' });
      await expect(heading).toBeVisible({ timeout: 20_000 });
      return heading;
    },
  },
  {
    id: 'record-validation',
    what: 'Export readiness, dry run PASSES — validation shown, export offered, nothing written',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.ready}/export`);
      await settled(page);
      const exportBtn = page.getByRole('button', { name: /Export Official Record \+ Sidecar/ });
      await expect(exportBtn).toBeVisible({ timeout: 20_000 });
      return exportBtn;
    },
  },
  {
    id: 'export-blocked',
    what: 'Export BLOCKED — the official dry run does not pass, so the gate stays closed',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.review}/export`);
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Would Not Validate Yet' });
      await expect(heading).toBeVisible({ timeout: 20_000 });
      return heading;
    },
  },
  {
    id: 'export-success',
    what: 'Export SUCCEEDED (seeded exported record) — the PASS verdict and the two artifacts',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.done}/export`);
      await settled(page);
      // The verdict is the state; the download is its primary action.
      await expect(page.locator('[role="status"]').filter({ hasText: 'PASS' }).first()).toBeVisible({
        timeout: 20_000,
      });
      const download = page.getByRole('button', { name: 'Download' }).first();
      await expect(download).toBeVisible();
      return download;
    },
  },
  {
    id: 'export-conflict',
    what: 'Export refused as a CONFLICT — official records are immutable, nothing was written',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.ready}/export`);
      await settled(page);
      /*
       * The 409 is fulfilled IN THE BROWSER. The POST never leaves the page, so
       * no record is written and the shared session this test is reading is
       * untouched — which is what makes a conflict state reachable at all from a
       * read-only suite. Registered AFTER the worked-example scope route, and
       * Playwright runs the most recently added handler first, so this one wins
       * for the export POST and everything else falls through to the scope
       * handler via `route.fallback()`.
       */
      await page.route(
        (url) => /\/api\/experiments\/[^/]+\/export$/.test(url.pathname),
        async (route) => {
          if (route.request().method() !== 'POST') {
            await route.fallback();
            return;
          }
          await route.fulfill({
            status: 409,
            contentType: 'application/json',
            body: JSON.stringify({ error: 'record_exists' }),
          });
        }
      );

      await page.getByRole('button', { name: /Export Official Record \+ Sidecar/ }).click();
      const conflict = page.locator('div.export-conflict[role="alert"]');
      await expect(conflict).toBeVisible({ timeout: 20_000 });
      await expect(conflict).toContainText(/immutable/i);
      return conflict;
    },
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'assistant-answer',
    what: 'The Assistant with an ANSWER in the log — a deterministic reply to a suggested question',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.partial}`);
      await settled(page);
      const aside = await openAssistantPanel(page);
      const log = aside.getByRole('log');
      await expect(log.locator('.assistant-msg')).toHaveCount(0);
      // Read-only: the assistant query endpoint is advisory and non-mutating.
      await aside.getByRole('button', { name: /What still needs me\?/i }).click();
      await expect(log.locator('.assistant-msg')).not.toHaveCount(0, { timeout: 25_000 });
      return log.locator('.assistant-msg').first();
    },
  },
  {
    /*
     * ── FROM HERE ON A REAL WALKTHROUGH IS RUNNING ─────────────────────────
     *
     * Started from the Replay control this sweep photographed two states ago,
     * because `tutorial.markCompleted()` has already retired the first-run
     * offer. It mints a session of ITS OWN; the `tutorial` fixture disposes
     * every session the page caused to exist, whether or not a test reaches an
     * exit path.
     */
    id: 'tutorial-coach-mark',
    what: 'A coach mark, step 1 — pointing at a real control on the surface that control lives on',
    async reach({ page, app, tutorial }) {
      await app.goto('/settings?tab=help');
      await settled(page);
      await page.getByRole('button', { name: 'Replay Tutorial' }).click();

      const mark = page.locator('.tutorial-mark');
      await expect(mark).toBeVisible({ timeout: 25_000 });
      // The walkthrough navigates itself to step one's own surface.
      await expect(mark).toHaveAttribute('data-tutorial-step', 'experiments-overview', {
        timeout: 25_000,
      });
      // Measured, not assumed: exactly one session exists for this test.
      expect(
        tutorial.sessionsCreated().length,
        'Replay must mint exactly one worked-example session'
      ).toBe(1);
      const next = mark.getByRole('button', { name: 'Next', exact: true });
      await expect(next).toBeVisible();
      return next;
    },
  },
  {
    id: 'reset-warning',
    what: 'The destructive reset confirmation — figures previewed, action disabled behind a typed gate',
    async reach({ page }) {
      const bar = page.getByRole('complementary', { name: 'Worked example session' });
      await expect(bar).toBeVisible({ timeout: 20_000 });
      const trigger = bar.getByRole('button', { name: /Reset Worked Example/i });
      await expect(
        trigger,
        'the Reset Worked Example trigger is absent from the worked-example bar — either it ' +
          'was rehomed again or the backend is not reporting mode: synthetic-only. Both are ' +
          'failures, not reasons to skip.'
      ).toBeVisible();
      await trigger.click();

      // `getByRole('dialog')` would be ambiguous: the coach mark is a dialog
      // too. `aria-modal` is the discriminator the app itself keys off — the
      // mark deliberately does not set it.
      const dialog = page.locator('[role="dialog"][aria-modal="true"]');
      await expect(dialog).toHaveCount(1, { timeout: 20_000 });
      await expect(dialog).toContainText(/Reset the Worked Example/i);
      // The preview has settled and the gate is closed. The phrase is NEVER typed.
      const action = dialog.getByRole('button', { name: 'Reset Example Records' });
      await expect(action).toBeDisabled();
      return action;
    },
    async cleanup({ page }) {
      // Escape cancels the dialog and — per the app's own capture-phase guard —
      // leaves the walkthrough running, which the next state needs.
      if ((await page.locator('[role="dialog"][aria-modal="true"]').count()) > 0) {
        await page.keyboard.press('Escape');
        await expect(page.locator('[role="dialog"][aria-modal="true"]')).toHaveCount(0);
      }
    },
  },
  {
    id: 'tutorial-completion',
    what: 'The completion panel — the walkthrough finished, its session discarded',
    async reach({ page }) {
      /*
       * A SHORTCUT, DISCLOSED. Reaching the last of sixteen steps by pressing
       * Next fifteen times costs ~7 navigations per width and 105 clicks across
       * the sweep. Instead this advances the app's OWN persisted step pointer
       * and lets `main.tsx`'s `resumeTutorialSession()` resume there — the same
       * mechanism a reader's browser uses after a refresh mid-walkthrough, which
       * `specs/tutorial.spec.ts` asserts works. It is not a hidden test hook and
       * it fabricates no state: the session is the live one the Replay control
       * just minted, and the total is READ FROM THE SCREEN rather than imported
       * from `src/`, so a step added to the walkthrough cannot make this stale.
       */
      const progress = await page.locator('.tutorial-progress').first().innerText();
      const match = /Step\s+(\d+)\s+of\s+(\d+)/i.exec(progress);
      expect(
        match,
        `could not read the step counter from the coach mark; it said "${progress}"`
      ).toBeTruthy();
      const total = Number(match![2]);
      expect(total, 'the walkthrough must have at least two steps').toBeGreaterThan(1);

      await page.evaluate(
        ([key, index]) => {
          const raw = sessionStorage.getItem(key as string);
          if (raw === null) throw new Error(`no persisted tutorial session under ${key}`);
          const held = JSON.parse(raw) as Record<string, unknown>;
          sessionStorage.setItem(key as string, JSON.stringify({ ...held, index }));
        },
        [TUTORIAL_SESSION_STORAGE_KEY, total - 1] as const
      );
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.addStyleTag({ content: NO_MOTION_CSS });

      const mark = page.locator('.tutorial-mark');
      await expect(mark).toBeVisible({ timeout: 25_000 });
      const finish = mark.getByRole('button', { name: 'Finish', exact: true });
      await expect(
        finish,
        `resuming at step ${total} of ${total} must show Finish rather than Next`
      ).toBeVisible({ timeout: 25_000 });
      await finish.click();

      const done = page.locator('.tutorial-mark[data-tutorial-step="complete"]');
      await expect(done).toBeVisible({ timeout: 25_000 });
      const back = done.getByRole('button', { name: 'Go to My Experiments' });
      await expect(back).toBeVisible();
      return back;
    },
  },
];

/** Compile-time + run-time proof that `STATES` and `EXPECTED_STATE_IDS` agree on
 *  MEMBERSHIP before a single browser is launched. The per-width assertion below
 *  is about what was actually CAPTURED; this is about what was declared. */
const DECLARED = [...EXPECTED_STATE_IDS].sort();

test.describe('visual state sweep', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(
      testInfo.project.name !== HOST_PROJECT,
      `runs only in ${HOST_PROJECT}; it moves the viewport itself rather than adding projects`
    );
  });

  test('@responsive the declared state set and the implemented state list agree', () => {
    expect(
      STATES.map((s) => s.id).sort(),
      'EXPECTED_STATE_IDS is the contract; STATES implements it. A mismatch means a state was ' +
        'added to one and not the other, which is exactly the silent omission this set exists ' +
        'to prevent.'
    ).toEqual(DECLARED);
    expect(new Set(STATES.map((s) => s.id)).size, 'duplicate state id').toBe(STATES.length);
  });

  for (const width of WIDTHS) {
    test(`@responsive width ${width}: capture every state, and assert each one`, async (
      { page, app, tutorial },
      testInfo
    ) => {
      // ~21 states, several of which drive a multi-step interaction. The
      // project-wide 60s timeout is for a single-surface test.
      test.setTimeout(900_000);

      await page.setViewportSize({ width, height: VIEWPORT_HEIGHT });
      const platform = currentPlatform();
      const ctx: Ctx = { page, app, tutorial, width };

      const captured: string[] = [];
      /** id → the reason it could not be captured. Failed at the end, all at
       *  once, so one broken state does not hide the other twenty. */
      const unreachable: string[] = [];
      const pageScroll: string[] = [];
      const primaryFailures: string[] = [];
      const clippedFailures: string[] = [];
      let font = '(not measured)';

      for (const state of STATES) {
        try {
          const primary = await state.reach(ctx);

          // The viewport is set before the first navigation, but a surface that
          // mounts a second pane can settle after it; re-assert so every
          // measurement below is taken at the width in the test title.
          await page.setViewportSize({ width, height: VIEWPORT_HEIGHT });
          if (font === '(not measured)') font = await renderedFontFamily(page);

          // ── 1. no PAGE-LEVEL horizontal scroll ────────────────────────────
          // Nested overflow is `layout-widths.spec.ts`'s job and is not
          // duplicated here; this is the cheapest falsification and the one the
          // brief names. A wide table may scroll inside its own box; the page
          // may not.
          const doc = await horizontalPageScroll(page);
          if (doc.docScrollWidth > doc.docClientWidth + 1) {
            pageScroll.push(
              `${state.id}: document scrolls horizontally — ${doc.docScrollWidth} > ${doc.docClientWidth}`
            );
          }

          // ── 2. the state's primary element is really there ────────────────
          const health = await primaryHealth(primary);
          if (health !== 'ok') primaryFailures.push(`${state.id}: ${health}`);

          // ── 3. no text clipped away entirely ──────────────────────────────
          // The two CONTENT-LOSS tiers only (`total-loss` includes zero-width
          // elements, which is the case the brief names). Deliberately NOT
          // baseline-filtered, for the same reason `layout-widths.spec.ts` does
          // not filter this tier: it answers "can the user read this at all?",
          // and nothing in it is recorded as tolerable debt.
          const clipped = await findClippedText(page);
          const lost = clipped.filter((c) => c.kind === 'total-loss' || c.kind === 'critical-loss');
          if (lost.length) clippedFailures.push(`${state.id}:\n${render(lost)}`);

          // ── 4. the artifact ──────────────────────────────────────────────
          const shot = await page.screenshot({ fullPage: true, animations: 'disabled' });
          await testInfo.attach(`${width}px · ${state.id} — ${state.what}`, {
            body: shot,
            contentType: 'image/png',
          });
          captured.push(state.id);
        } catch (err) {
          unreachable.push(`${state.id}: ${(err as Error).message.split('\n')[0]}`);
        } finally {
          if (state.cleanup) await state.cleanup(ctx).catch(() => undefined);
        }
      }

      testInfo.annotations.push({
        type: 'visual-sweep',
        description:
          `width ${width} on ${platform} — font: ${font}; ` +
          `${captured.length}/${STATES.length} states captured as attachments; ` +
          `${unreachable.length} unreachable, ${pageScroll.length} page-scroll, ` +
          `${primaryFailures.length} primary-element, ${clippedFailures.length} content-loss finding(s).`,
      });
      // eslint-disable-next-line no-console
      console.log(
        `[visual-sweep] ${width}px — font: ${font}; captured ${captured.length}/${STATES.length}` +
          (unreachable.length ? `; UNREACHABLE: ${unreachable.join(' | ')}` : '')
      );

      // THE SET, not a count. Reported before the layout assertions because an
      // uncaptured state makes the others' silence meaningless.
      expect(
        [...captured].sort(),
        unreachable.length
          ? `States that could not be reached at ${width}px. Each one is a FINDING — either the ` +
            `state is genuinely broken at this width, or this spec's route to it is wrong. ` +
            `Nothing is skipped silently:\n${unreachable.join('\n')}`
          : `The captured set must equal the declared set at ${width}px.`
      ).toEqual(DECLARED);

      expect(
        pageScroll,
        pageScroll.length
          ? `Page-level horizontal scrolling at ${width}px (font: ${font}, platform: ${platform}). ` +
            `The document must never scroll sideways — a reader has to pan the whole app to read ` +
            `one line:\n${pageScroll.join('\n')}`
          : undefined
      ).toEqual([]);

      expect(
        primaryFailures,
        primaryFailures.length
          ? `A state's primary control or heading is present in the DOM but not usable at ` +
            `${width}px (font: ${font}, platform: ${platform}). A screenshot of a screen whose ` +
            `main action cannot be hit is a screenshot of a broken screen:\n${primaryFailures.join('\n')}`
          : undefined
      ).toEqual([]);

      expect(
        clippedFailures,
        clippedFailures.length
          ? `Text present in the DOM but not readable on screen at ${width}px (font: ${font}, ` +
            `platform: ${platform}). Truncation is allowed only while a meaningful fragment ` +
            `survives; this tier is deliberately NOT baseline-filtered:\n${clippedFailures.join('\n')}`
          : undefined
      ).toEqual([]);
    });
  }
});

/**
 * The smallest box a real control or heading in this app occupies on either
 * axis, used as the "is this a real box or an accessible-name carrier?" line.
 *
 * 8 rather than `helpers/layout.ts`'s `MIN_USABLE_TARGET_PX` (24), and the
 * difference is deliberate: 24 is a TOUCH-TARGET rule and would false-positive on
 * a legitimate `<h2>`, which at 320px is around 20px tall. What this number has
 * to separate is a genuine box from the `.sr-only` clip-rect pattern
 * (`base.css:293-302` — `width: 1px; height: 1px; clip: rect(0,0,0,0)`), and 1
 * versus 8 is not a close call. Case V1 below proves the separation instead of
 * asserting it.
 */
const MIN_PRIMARY_BOX_PX = 8;

/**
 * Is this element genuinely usable — laid out, painted, and hittable?
 *
 * Four checks, because each one alone passes something broken:
 *
 *   * `count === 0` — not rendered at all;
 *   * Playwright `toBeVisible()` accepts a 1x1 `clip-rect` box, which is exactly
 *     what every `.sr-only` accessible-name carrier is, and four of this app's
 *     screens make their `<h1>` one. `MIN_PRIMARY_BOX_PX` is the line;
 *   * a full-size box can still sit outside the viewport (the measured
 *     4.9px-of-128px sliver `layout-widths.spec.ts` case I1 exists for);
 *   * a fully laid-out, on-screen box can be painted over by an overlay.
 *
 * The hit test is the centre of the element's INTENDED box and accepts any node
 * in its ancestor/descendant chain — a label's text node, an icon inside a
 * button. Anything else at that point means something is on top.
 *
 * Returns `'ok'` or a one-line, MEASURED reason. Falsified by the four injected
 * cases in the `probe self-check` block below: a probe that reports nothing and a
 * screen with nothing wrong look identical from the outside, and 147 clean
 * captures is exactly the result a broken probe would produce.
 */
async function primaryHealth(locator: Locator): Promise<string> {
  const count = await locator.count();
  if (count === 0) return 'primary element is not in the DOM';
  const el = locator.first();
  if (!(await el.isVisible())) return 'primary element is in the DOM but not visible';
  await el.scrollIntoViewIfNeeded().catch(() => undefined);

  return el.evaluate(
    (node, minBox) => {
      const r = (node as Element).getBoundingClientRect();
      if (r.width < minBox || r.height < minBox) {
        return (
          `primary element has no real hit box: ${Math.round(r.width)}x${Math.round(r.height)} ` +
          `(under ${minBox}px on an axis — the visually-hidden clip-rect pattern, not a control)`
        );
      }
      const vw = document.documentElement.clientWidth;
      const vh = document.documentElement.clientHeight;
      const visibleW = Math.min(r.right, vw) - Math.max(r.left, 0);
      const visibleH = Math.min(r.bottom, vh) - Math.max(r.top, 0);
      if (visibleW < Math.min(r.width, minBox) || visibleH < Math.min(r.height, minBox)) {
        return (
          `primary element is off-screen: ${Math.round(visibleW)}x${Math.round(visibleH)} of ` +
          `${Math.round(r.width)}x${Math.round(r.height)} inside a ${vw}x${vh} viewport`
        );
      }
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      // Centre off-screen while a usable strip is on it: not a finding, and the
      // sliver case above has already rejected the harmful version of this.
      if (cx < 0 || cy < 0 || cx > vw || cy > vh) return 'ok';
      const hit = document.elementFromPoint(cx, cy);
      if (hit === null) return "nothing is hit-testable at the primary element's centre";
      if (hit === node || node.contains(hit) || hit.contains(node)) return 'ok';
      const name = (e: Element) =>
        `${e.tagName.toLowerCase()}${e.id ? `#${e.id}` : ''}${
          typeof e.className === 'string' && e.className.trim()
            ? `.${e.className.trim().split(/\s+/).slice(0, 2).join('.')}`
            : ''
        }`;
      return `primary element is covered at its centre by ${name(hit)}`;
    },
    MIN_PRIMARY_BOX_PX
  );
}

/**
 * ── PROBE SELF-CHECK ────────────────────────────────────────────────────────
 *
 * The sweep above captured 147 states and reported zero primary-element
 * findings. That is the same output a probe with a bug in it would produce, so
 * the probe is falsified here against INJECTED geometry — the technique
 * `self-check.spec.ts` and `layout-widths.spec.ts`'s regression cases already
 * use. All four mutations are browser-side only; nothing is written to the
 * backend.
 *
 * The page-scroll check is deliberately NOT self-checked: it compares
 * `document.documentElement.scrollWidth` with `clientWidth` and there is no
 * intermediate logic to get wrong. The CONTENT-LOSS check is not self-checked
 * here either, because `layout-widths.spec.ts` cases T1/E1/C1/I1 already falsify
 * `findClippedText` and `findOverflowingRegions` against the exact geometry of
 * measured defects, and duplicating them would mean two places to update.
 */
test.describe('probe self-check (injected geometry)', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== HOST_PROJECT, `runs only in ${HOST_PROJECT}`);
  });

  test('@responsive V1: a 1x1 clip-rect carrier is not a usable primary', async ({ page, app }) => {
    await app.open(experimentsSurface);
    await page.evaluate(() => {
      const h = document.createElement('h1');
      h.id = 'visual-selfcheck-v1';
      h.className = 'sr-only';
      h.textContent = 'Review Record';
      document.querySelector('main')!.appendChild(h);
    });
    const el = page.locator('#visual-selfcheck-v1');
    // THE BLIND SPOT, asserted directly: Playwright calls this visible.
    await expect(
      el,
      'if Playwright stopped treating a 1x1 clip-rect box as visible, this self-check no longer ' +
        'reproduces the blind spot and the reason for MIN_PRIMARY_BOX_PX must be re-derived'
    ).toBeVisible();
    expect(await primaryHealth(el)).toMatch(/no real hit box/);
  });

  test('@responsive V2: a 4.9px sliver of a 128px control is not a usable primary', async ({ page, app }) => {
    await app.open(experimentsSurface);
    await page.evaluate(() => {
      const b = document.createElement('button');
      b.id = 'visual-selfcheck-v2';
      b.textContent = 'Open the Worked Example';
      const vw = document.documentElement.clientWidth;
      b.style.cssText = `position: fixed; left: ${vw - 4.9}px; top: 320px; width: 128px; height: 30px; z-index: 5;`;
      document.body.appendChild(b);
    });
    const el = page.locator('#visual-selfcheck-v2');
    await expect(el).toBeVisible();
    expect(await primaryHealth(el)).toMatch(/off-screen: 5x30 of 128x30/);
  });

  test('@responsive V3: a control painted over is not a usable primary', async ({ page, app }) => {
    await app.open(experimentsSurface);
    await page.evaluate(() => {
      const b = document.createElement('button');
      b.id = 'visual-selfcheck-v3';
      b.textContent = 'Export Official Record + Sidecar';
      b.style.cssText = 'position: fixed; left: 40px; top: 320px; width: 200px; height: 30px; z-index: 5;';
      const cover = document.createElement('div');
      cover.id = 'visual-selfcheck-v3-cover';
      cover.style.cssText =
        'position: fixed; left: 40px; top: 320px; width: 200px; height: 30px; z-index: 6; background: #fff;';
      document.body.appendChild(b);
      document.body.appendChild(cover);
    });
    const el = page.locator('#visual-selfcheck-v3');
    expect(await primaryHealth(el)).toMatch(/covered at its centre by div#visual-selfcheck-v3-cover/);
  });

  test('@responsive V4: an ordinary control is still "ok" (guard against over-correction)', async ({
    page,
    app,
  }) => {
    await app.open(experimentsSurface);
    // A real product control, not an injected one — if the probe has become
    // noise, this is where it shows.
    expect(await primaryHealth(page.getByRole('button', { name: 'Start Tutorial' }))).toBe('ok');
    expect(await primaryHealth(page.locator('#no-such-element-anywhere'))).toBe(
      'primary element is not in the DOM'
    );
  });
});

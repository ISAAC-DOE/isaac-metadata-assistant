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
 * ── Where the images come from — AND A MEASURED CORRECTION TO WHAT THIS FILE
 *    USED TO CLAIM THEY WERE ───────────────────────────────────────────────────
 *
 * This section is kept as a correction rather than quietly rewritten, because the
 * claim it replaces was this file's central architectural premise and it was
 * false. It said:
 *
 *     "`fullPage: true` is passed, and on most of these screens it captures
 *      exactly the visible frame — because THIS APP'S SCROLL CONTAINER IS NOT THE
 *      DOCUMENT. `div.screen-card` is `overflow: hidden` and `main#main` is
 *      `overflow: auto`, so the document's scrollHeight equals its clientHeight
 *      and 'full page' and 'the frame' are the same picture … `primaryHealth()`
 *      scrolls [the primary] into view before the shot is taken, which is what
 *      makes the five record-screen SECTIONS below photographable at all."
 *
 * BOTH CSS FACTS ARE TRUE AND THE INFERENCE FROM THEM IS FALSE. `.screen-card`
 * sets `min-height: calc(100vh - 32px)` — NOT `height` (`src/components/
 * chrome.css:13-16`) — so the card GROWS with its content, `.screen-main` is never
 * height-constrained, and `overflow-y: auto` on an unconstrained box scrolls
 * nothing. THE DOCUMENT IS THE SCROLLPORT. Measured at 1280x900 over the nine
 * routes this file opens: the document scrolls on 8 of 9 and `main#main` scrolls
 * on NONE.
 *
 * WHAT THAT COST, measured on the last passing run before this fix (width 1280,
 * host project): 30 attachments were 25 DISTINCT IMAGES.
 * `record-edit`, `record-runs`, `record-validate-review`, `record-unmapped-notes`
 * and `record-asset-references` were ONE byte-identical 416,847-byte PNG — the
 * whole ~2400px document, which already contained all five of those sections in
 * one frame — and `record-validation` and `record-revision-history` were a second
 * such pair. `fullPage` captures the whole document REGARDLESS of scroll position,
 * so the `scrollIntoViewIfNeeded` this header credited with making those sections
 * photographable never affected a single pixel. At width 320 all 30 hashes DID
 * differ, and that MASKED the defect instead of fixing it: the page content was
 * still the entire document every time, and only the `position: fixed` chrome —
 * painted at whatever scroll offset the state happened to leave behind — moved.
 *
 * SO EVERY STATE NOW NAMES THE ELEMENT THAT IS THE STATE, AND THAT ELEMENT IS
 * SCREENSHOTTED (`frame`, below). This is not a new technique: it is exactly what
 * the sibling sweep `specs/statistics-states.spec.ts` does, and this file is
 * following it rather than inventing something. An element shot captures the whole
 * element, above and below the fold, so a section of a long route is a picture of
 * that section and of nothing else. The default frame is the app frame
 * `div.screen-card`; the states that are SECTIONS of a shared route name their own
 * `<section>`; three states whose subject is a `position: fixed` overlay
 * photograph THE VIEWPORT, which is the frame a reader of an overlay actually has.
 *
 * The one guarantee this replaces the old prose with is mechanical rather than
 * argued: every attachment at a width is SHA-256'd and two states attaching the
 * same bytes is a FINDING (`duplicateImages`). The defect above passed every
 * assertion in this file for as long as it existed; it cannot do so again.
 *
 * A reviewer must not read an attachment as "the whole screen" unless its caption
 * is a whole screen: it is the frame the state declared, and nothing more.
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
 * The file lives in `e2e/specs/`, which is the READ-ONLY suite.
 * `playwright.mutation.config.ts` separates the mutating specs by DIRECTORY
 * (`e2e/mutation/`), not by tag, so a tag alone would not have kept this out of
 * the wrong runner — the directory is what does it.
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
 *
 * ── PORTED 2026-08-17, and what the port had to change ──────────────────────
 *
 * This file was written before Unmapped Notes, the Evidence Graph, the
 * Experiment Graph, Validate & Review, the Runs workspace, Compare Runs, Asset
 * References and Connect Your Agent existed, and one of its states had since
 * become unreachable by the route it used. The changes are recorded here rather
 * than applied silently, because "a state this sweep no longer photographs" is
 * exactly the kind of loss the SET discipline exists to make loud:
 *
 *   * `tutorial-start` was reached at `/experiments` in the ORDINARY workspace.
 *     It is no longer reachable there at all: `ExperimentsHome.tsx:457` renders
 *     the offer only when `!queueIsEmpty`, and the ordinary workspace is
 *     permanently empty. The offer is now photographed where it really renders —
 *     the same route inside a worked-example session, where the queue has rows.
 *   * `experiments-empty`'s primary is now the empty state's own
 *     `Launch Guided Demo` control rather than the page heading. That state used
 *     to offer no action and now does, and the `VisualState.reach` contract asks
 *     for the action when there is one.
 *   * eight states were ADDED for surfaces this sweep had never opened. Five of
 *     them are SECTIONS of `/record/:id` rather than routes of their own; see
 *     the note above about why they are separate pictures and not one.
 *
 * Nothing was dropped. Every id in the original 21 is still captured.
 */

import { createHash } from 'node:crypto';
import { currentPlatform } from '../a11y-baseline';
import { API_BASE, API_ROUTE_GLOB, SEED } from '../env';
import { LOADING_PANEL, expect, test, type AppHelper, type TutorialHelper } from '../fixtures';
import { LAYOUT_SWEEP_WIDTHS, layoutWidthId } from '../layout-baseline';
import { findClippedText, horizontalPageScroll, render, renderedFontFamily } from '../helpers/layout';
import { SURFACES } from '../surfaces';
import { TUTORIAL_SESSION_STORAGE_KEY } from '../worked-example';
import type { Locator, Page } from '@playwright/test';

/** The single project this file runs in. See the header. */
const HOST_PROJECT = 'desktop-1280x800';

/**
 * ── THE WIDTH GRID, AND WHY IT IS DERIVED RATHER THAN COPIED OR IMPORTED ─────
 *
 * `main` has since moved the layout sweep's grid into `layout-baseline.ts` as
 * `LAYOUT_SWEEP_WIDTHS`. Three options were on the table and the choice matters
 * enough to write down:
 *
 *  1. IMPORT IT UNCHANGED. Rejected. `LAYOUT_SWEEP_WIDTHS` is not merely a list
 *     of widths — it is the legal `width-<n>` half of every `LAYOUT_BASELINE`
 *     key, validated by `invariants/baseline-aggregate.invariant.test.ts`. This
 *     sweep writes NO baseline key (it deliberately does not baseline-filter its
 *     content-loss tier), so it has no claim on that key space, and adopting the
 *     grid wholesale would also have dropped 1440 — the widest layout an
 *     ordinary modern laptop renders, which no sweep in this suite measured
 *     before this file existed.
 *  2. KEEP AN INDEPENDENT LITERAL LIST, as the original did. Rejected, because
 *     the two lists then drift in the direction that actually hurts: a width
 *     added to the layout sweep is a width nobody photographs, and nothing
 *     fails.
 *  3. DERIVE, and guard the one-way difference. Taken.
 *
 * So: this grid is `LAYOUT_SWEEP_WIDTHS` MINUS 640, PLUS 1440.
 *
 *   * 640 is omitted because it is already a Playwright project of its own
 *     (`zoom-200` is 640x400 at DPR 2) and every state below is reached at 768
 *     and 390, which bracket it. Stated rather than left as an apparent
 *     oversight.
 *   * 1440 is added HERE ONLY, and that placement is the whole point of the
 *     derivation. `LAYOUT_SWEEP_WIDTHS` must NOT gain it: every surface would
 *     immediately acquire `@width-1440` baseline keys with no measured values
 *     behind them, and CI would fail with a large diff that has no explanation
 *     in it. `the width grids agree except where they must not` below asserts
 *     that, so if someone adds 1440 there they get this sentence instead of that
 *     diff.
 *
 * 320 is the WCAG 1.4.10 reflow width and the narrowest the product claims to
 * support; 390 is the modern iPhone width.
 */
const EXTRA_WIDTH = 1440;
const OMITTED_WIDTH = 640;

/**
 * Widened to `readonly number[]` ON PURPOSE, and this is not a convenience cast.
 *
 * `LAYOUT_SWEEP_WIDTHS` is `as const`, so its element type is the literal union
 * `1280 | 1024 | 768 | 640 | 390 | 375 | 320`. Comparing that against 1440 is a
 * TS2367 "no overlap" error — which is TypeScript ALREADY PROVING, at compile
 * time, the very fact the runtime guard below asserts. That is welcome and it is
 * recorded here rather than being the mechanism, because it is the wrong shape
 * of guard: it fails as a type error in the filter expression with no
 * explanation attached, and it would silently STOP holding the moment someone
 * added 1440 to that array — the exact change it is supposed to object to.
 */
const SWEEP_WIDTHS: readonly number[] = LAYOUT_SWEEP_WIDTHS;

const WIDTHS: readonly number[] = [
  EXTRA_WIDTH,
  ...SWEEP_WIDTHS.filter((w) => w !== OMITTED_WIDTH && w !== EXTRA_WIDTH),
];

/**
 * 900 — KEPT, but its REASON IS REPLACED, and 812 was tried and measured first.
 *
 * The reason this file used to give was "taller than the width sweep's 812, to
 * show more per shot", and that was never true of any capture it has ever taken:
 * `fullPage` ignores viewport height for EXTENT, and so does an element shot.
 * Height only ever changed REFLOW. So the honest question is which height serves
 * this file's NON-image findings, and the obvious candidate was 812 — the height
 * at which `specs/layout-widths.spec.ts` measures horizontal page scroll and
 * `findClippedText` (the same two tiers asserted below) and at which every value
 * in `layout-baseline.ts` was recorded. A finding taken at the same geometry as
 * the layout sweep is a finding either sweep can reproduce.
 *
 * IT WAS SET TO 812, RUN, AND REVERTED, on this measurement (host project,
 * width 320):
 *
 *     reset-warning: primary element is covered at its centre by div.tutorial-mark
 *
 * At 320x812 the running walkthrough's coach mark paints OVER the reset dialog's
 * confirm button; at 320x900 it does not, and every other width passes at both
 * heights. That is a REAL, reachable finding — a reader who replays the
 * walkthrough on a phone-height viewport and then opens Reset Worked Example from
 * the session bar meets it — and it is an overlay/z-order question in
 * `GuidedTutorial`/`ResetDemoDialog`, i.e. a PRODUCT change this test-only change
 * is not authorized to make. Adopting 812 here would therefore have left the
 * suite red on a defect this file cannot fix, so the height stays and the finding
 * is written down instead of being silently absorbed by it.
 *
 * Two consequences, both deliberate: this file's content-loss findings are NOT
 * taken at the layout sweep's geometry (so a difference between the two is
 * explained by this comment, not by a bug), and `specs/statistics-states.spec.ts`
 * still sets 900 for the old, false "more per shot" reason — same number,
 * different justification, and its own header now says so.
 */
const VIEWPORT_HEIGHT = 900;

/**
 * The DEFAULT frame — the app frame, which is `AppShell`'s outermost box inside
 * `div.app`: top bar, worked-example bar, sidebar, `<main>` and status bar
 * (`src/components/AppShell.tsx`). It GROWS with content (see the header), so an
 * element shot of it is the whole screen including everything below the fold.
 *
 * It deliberately excludes the walkthrough overlay and the reset dialog, which
 * `AppShell` mounts as SIBLINGS of the card — the three states whose subject is
 * one of those photograph the viewport instead.
 */
const DEFAULT_FRAME = 'div.screen-card';

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
  'settings-connect',
  'statistics-general',
  'statistics-mine',
  'validator',
  'record-edit',
  'record-graph',
  'record-runs',
  'record-compare',
  'record-validate-review',
  'record-unmapped-notes',
  'record-asset-references',
  'record-confirmation',
  'record-evidence',
  'record-evidence-graph',
  'record-validation',
  'record-revision-history',
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
   * WHAT GETS PHOTOGRAPHED: the element that IS this state, or the string
   * `'viewport'`. Omit it for a state whose subject is the whole screen, and the
   * shot is of `DEFAULT_FRAME`.
   *
   * This exists because of the measured defect in the header: a page-level shot
   * of a route that carries several states is the SAME IMAGE for every one of
   * them, and neither the assertions here nor a human reading the report could
   * tell. A state that is a SECTION of a shared route must name its section.
   *
   * `'viewport'` for a state whose subject is `position: fixed` — a coach mark,
   * a modal. An element shot of a fixed overlay inside a document-tall frame
   * paints it once at one scroll offset, which is a picture of an arrangement no
   * reader ever sees; the viewport IS the frame in that case.
   *
   * The primary is passed in so a frame can be derived from it, but no state
   * currently needs to: a primary is a control or a heading, and a picture of a
   * button is not a picture of a state.
   */
  readonly frame?: (ctx: Ctx, primary: Locator) => Promise<Locator | 'viewport'> | Locator | 'viewport';
  /**
   * Clean up anything that would leak into the next state (a `page.route`, an
   * open overlay). Runs even when `reach` threw.
   *
   * NOTE, since the sticky-scope finding: the loop ALSO calls
   * `page.unrouteAll()` after this, unconditionally, so a missing cleanup can no
   * longer leak a route into the next state. The per-state cleanups are kept
   * anyway — they say what a state is responsible for, and a cleanup that closes
   * an overlay (`reset-warning`) is not something the loop can guess.
   */
  readonly cleanup?: (ctx: Ctx) => Promise<void>;
}

/**
 * Surfaces are taken from the catalogue rather than re-spelled as paths, so a
 * route that moves moves in one place. `!` is safe and is checked for real by
 * `the surface catalogue still carries the entries this sweep opens` below —
 * a bare `!` on a missing id would otherwise fail at width 1440 with a
 * `TypeError` on `.path`, twenty minutes into a browser run.
 */
const surface = (id: string) => SURFACES.find((s) => s.id === id)!;

const experimentsSurface = surface('experiments');
const experimentsExampleSurface = surface('experiments-example');
const evidenceGraphSurface = surface('evidence-graph');
const connectSurface = surface('settings-connect');

/**
 * Two run ids that resolve in NO record. Used to photograph the Compare Runs
 * panel — see `record-compare` for why that is the honest read-only route to it,
 * and why it is not a workaround.
 */
const ABSENT_RUN_A = 'RUN-NO-SUCH-RUN-A';
const ABSENT_RUN_B = 'RUN-NO-SUCH-RUN-B';

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
 *     current step's own path (`GuidedTutorial.tsx`), so any state measured
 *     after it would be a measurement of the overlay's chosen surface rather
 *     than of itself.
 */
const STATES: readonly VisualState[] = [
  {
    /*
     * PORTED, AND THE ROUTE MOVED. This was `/experiments` in the ORDINARY
     * workspace and is now the same route inside a worked-example session.
     *
     * Not a cosmetic change and not a workaround: `ExperimentsHome.tsx:457`
     * renders `<TutorialPromotion />` only when `result.status === 'data' &&
     * !queueIsEmpty`, and the ordinary workspace is PERMANENTLY empty, so the
     * first-run offer cannot appear there under any circumstances. Photographing
     * it in the ordinary scope would have been photographing a state the product
     * does not have. Inside a session the queue holds the five example records
     * and `shouldOfferTutorial()` is true, which is where a reader really meets
     * this card.
     *
     * Nothing here clicks it. Starting the walkthrough from this control would
     * mint a session against the SHARED scope; the walkthrough states at the end
     * of this list start one of their own from the Replay control instead.
     */
    id: 'tutorial-start',
    what: 'My Experiments with records on it — the guided-walkthrough offer, before it is answered',
    async reach({ page, app }) {
      await app.open(experimentsExampleSurface);
      await expect(page.locator('section.tutorial-offer')).toHaveCount(1);
      const start = page.getByRole('button', { name: 'Start Tutorial' });
      await expect(start).toBeVisible({ timeout: 20_000 });
      return start;
    },
    /*
     * LEAVE THE SCOPE AGAIN, AND THIS IS NOT HOUSEKEEPING — IT IS THIS STATE'S
     * CONTRACT WITH THE NEXT ONE.
     *
     * `app.open()` ENTERS the worked-example scope for a `scope: 'example'`
     * surface and NOTHING EVER LEAVES IT. `scope: 'ordinary'` does not mean
     * "leave the scope"; it means "do not enter it" — the branch in `fixtures.ts`
     * is `if (surface.scope === 'example') await enterWorkedExample(page)`, with
     * no `else`. What `enterWorkedExample` installs is a `page.route` on
     * `API_ROUTE_GLOB` that attaches the session header to EVERY subsequent API
     * request, so the scope is sticky for the life of the page.
     *
     * That trap was unreachable until this port: the original `tutorial-start`
     * opened the ORDINARY experiments surface, so nothing before
     * `experiments-empty` had ever entered a scope. Moving this state into a
     * session — which the product forced; see the note above — made this file the
     * first caller to hit it. MEASURED at width 1280, on the next state, with the
     * scope still attached:
     *
     *     offers=0 rows=5 startBtn=0 launchBtn=0
     *
     * `.exp-row` was 5 rather than 0, so `experiments-empty` failed — and
     * `Launch Guided Demo`, that state's primary, does not render at all while
     * the queue is non-empty, so it would have failed a second time for a second
     * reason. The screen was the worked example wearing the ordinary workspace's
     * name, which is precisely the kind of thing a sweep that photographs
     * "My Experiments" must not quietly publish.
     *
     * `unrouteAll` rather than `unroute(API_ROUTE_GLOB)`: it is the idiom the
     * three other cleanups in this file already use, and it needs no assumption
     * about pattern identity between this file and `worked-example.ts`. Safe,
     * because every later example-scope state re-enters the scope on its own —
     * `app.gotoExample()` and `app.open()` both call `enterWorkedExample` every
     * time rather than once.
     *
     * WHY THE BLAST RADIUS WAS EXACTLY ONE STATE, stated so nobody reads that as
     * "the leak was harmless": the state after `experiments-empty` is `loading`,
     * whose cleanup already calls `unrouteAll`. The leak was cleared by accident,
     * one state too late, by a cleanup written for an unrelated reason.
     */
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'experiments-empty',
    what: 'My Experiments in the ordinary workspace — permanently empty, with the one action it offers',
    async reach({ page, app, tutorial }) {
      // The real mechanism (`localStorage`), so this is the state a reader who
      // finished the walkthrough actually sees — not a hidden test flag. It is
      // no longer the ONLY reason the offer is absent here (emptiness suppresses
      // it too), so both facts are asserted rather than one being implied.
      await tutorial.markCompleted();
      await app.open(experimentsSurface);
      await expect(page.locator('section.tutorial-offer')).toHaveCount(0);
      await expect(page.locator('.exp-row')).toHaveCount(0);
      await expect(page.getByRole('heading', { name: 'My Experiments' })).toBeVisible();
      // The empty state's own primary. It did not exist when this sweep was
      // written; the heading stood in for it because the screen offered nothing.
      const launch = page.getByRole('button', { name: 'Launch Guided Demo' }).first();
      await expect(launch).toBeVisible({ timeout: 20_000 });
      return launch;
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
      /*
       * WHETHER THE HOLD ACTUALLY FIRED IS ASSERTED, NOT ASSUMED.
       *
       * The route pattern is an EXACT URL and matches only because `lib/api.ts`
       * asks for `/experiments` with no query string today (`api.ts` →
       * `const path = '/experiments'`). Add one parameter — a page size, a sort —
       * and this handler silently stops matching. The panel assertion below would
       * NOT catch that: `toBeVisible` auto-retries, so it can pass on the
       * ordinary navigation's own transient loading panel, and the shot would then
       * be of the LOADED screen under a caption that says "a pending fetch".
       *
       * So the state's real precondition is "our hold is what is keeping this
       * panel up", and that is what is checked.
       */
      let held = false;
      await page.route(`${API_BASE}/experiments`, async (route) => {
        held = true;
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
      await expect
        .poll(() => held, {
          timeout: 10_000,
          message:
            `the held route \`${API_BASE}/experiments\` never fired, so the loading panel on ` +
            'screen is a transient one this state does not control and the screenshot may be of ' +
            'the loaded screen. The request URL has almost certainly gained a query string — ' +
            'match on the pathname rather than loosening this assertion away.',
        })
        .toBe(true);
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
      // `API_ROUTE_GLOB` rather than a locally-rebuilt regex: `env.ts` owns the
      // "which URLs are the API" expression and `states.spec.ts` reads the same
      // one. Two independently-derived copies drift when a port or prefix moves.
      await page.route(API_ROUTE_GLOB, (route) => route.abort('connectionrefused'));
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
    /*
     * NEW. Connect Your Agent shipped after this sweep was written.
     *
     * The `ready` locator is taken from the catalogue rather than re-spelled,
     * and the catalogue's own note on it is the reason it is worth reading
     * before touching this entry: the name is THIS BUILD'S REAL STATE
     * (`MCP_ENDPOINT` is `null`, so `mcpDeploymentState` resolves to
     * `requires-configuration`). The day a deployment publishes an address, the
     * panel renders a different banner and this must be revisited rather than
     * loosened into a regex that matches both — a sweep that photographs
     * "whichever banner is up" cannot tell a reviewer which one it was.
     */
    id: 'settings-connect',
    what: 'Settings & API → Connect Your Agent — the agent interface, stated as unconfigured',
    async reach({ page, app }) {
      await app.open(connectSurface);
      const heading = page.getByRole(connectSurface.ready.role, { name: connectSurface.ready.name }).first();
      await expect(heading).toBeVisible({ timeout: 20_000 });
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
     * THE RECORD STATES, and a correction to the brief that first asked for
     * them, kept because it is still true: there is no Edit route, no
     * Confirmation route and no Validation route. `routes.ts` defines exactly
     * four record paths — `/record/:id`, `…/complete`, `…/evidence`,
     * `…/export` — so the four are mapped onto what the app really has:
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
     *
     * WHAT THE PORT ADDED. `/record/:id` has since grown five more surfaces
     * BELOW the field workbench — the Runs workspace, the Compare Runs panel,
     * Validate & Review, Unmapped Notes and Asset References — plus a `?view=`
     * graph.
     *
     * WHY THEY ARE SEPARATE ENTRIES — CORRECTED, because the reason first given
     * here was measured false and is worth keeping visible. It said: "they are
     * separate screenfuls: each is reached by scrolling its own heading into
     * view, so one picture of this route would have shown none of them." The
     * opposite is true. This route is ONE ~2400px document (see the header), a
     * `fullPage` shot of it contained every one of these sections, and the four
     * that share the URL with `record-edit` attached a BYTE-IDENTICAL image to it
     * — the same 416,847 bytes, five times.
     *
     * What they genuinely add, now that each names its own `<section>` as its
     * frame, is two things per section: a `primaryHealth()` check on a heading
     * nothing else checks, and a CROP a reviewer can actually read — one section
     * rather than a 2400px page in which it is a band. That is worth four
     * ~830ms re-navigations (measured, width 1280); it was not worth them while
     * the images were identical.
     *
     * THE PER-STATE PAGE SCANS ARE DELIBERATELY *NOT* DEDUPLICATED, and this was
     * re-checked rather than assumed. `findClippedText` over this route MEASURES
     * at 4-5ms (width 1280, all five states), so the "redundant full rescan" is
     * ~16ms per width — and skipping it would be wrong, not just unnecessary:
     * these sections mount from their own fetches, so `record-edit`'s scan can
     * legitimately run before a section's text exists, and each section state
     * waits for its own heading first. The rescans cover DOM the first scan may
     * never have seen.
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
    /*
     * NEW. `/record/:id?view=graph` — the experiment-scoped graph.
     *
     * `Experiment Graph` is the primary because `ExperimentGraphPanel` renders
     * that same `<h2>` in BOTH of its branches: the drawn graph and the honest
     * refusal it shows when the bundle cannot be projected. So this state is
     * reachable whichever the backend produces, and the ATTACHMENT is what tells
     * a reviewer which one they got — which is precisely the division of labour
     * this file's header claims between the assertions and the images.
     */
    id: 'record-graph',
    what: 'Record → Graph — the experiment projected as nodes and edges, or its honest refusal',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.partial}?view=graph`);
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Experiment Graph' }).first();
      await expect(heading).toBeVisible({ timeout: 20_000 });
      return heading;
    },
  },
  {
    /*
     * NEW. The Runs workspace, and the state it is really in for every canonical
     * seed: EMPTY. `ValidateReview.tsx` says so in its own words — "every one of
     * the five canonical seeds is such a record" — and this suite is read-only,
     * so it cannot create one. The empty state is therefore not a weaker version
     * of this coverage, it is the only honest version of it; a run list with runs
     * in it belongs to the mutation suite, which owns `e2e/mutation/runs.spec.ts`.
     */
    id: 'record-runs',
    what: 'Record → Runs — the run workspace with no runs recorded, and the invitation to add one',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.partial}`);
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Runs', exact: true }).first();
      await expect(heading).toBeVisible({ timeout: 20_000 });
      await expect(page.locator('.runs-empty')).not.toHaveCount(0, { timeout: 20_000 });
      return heading;
    },
    // `RunsSection.tsx:124`. The section, not the page: this state shares its URL
    // with four others.
    frame: ({ page }) => page.locator('section.runs-section'),
  },
  {
    /*
     * NEW. Compare Runs, reached through a deep link naming two runs the record
     * does not have.
     *
     * THIS IS THE STATE, NOT A SUBSTITUTE FOR ONE. A read-only suite cannot
     * create the two runs a populated comparison needs, and inventing them would
     * mean writing to a scope four other projects are reading. What it CAN do —
     * and what a reader can do, by following a stale or mistyped link — is ask
     * for a comparison of runs that are not there. `RunCompare` renders its panel
     * on `selected.length >= RUN_COMPARE_MAX` alone, then says per id that no
     * such run is in this record. That refusal is a first-class product state and
     * had never been photographed at any width.
     *
     * The `<h3>` is the primary rather than the refusal alert, deliberately: the
     * heading is unconditional inside the panel, while the alert appears only
     * once both `getRun` calls have answered. Making the *slower* of the two the
     * primary would have turned a timing difference into an "unreachable state".
     */
    id: 'record-compare',
    what: 'Record → Compare Runs, deep-linked to two runs this record does not have — refused per id',
    async reach({ page, app }) {
      await app.gotoExample(
        `/record/${SEED.partial}?compare=${ABSENT_RUN_A}&compare=${ABSENT_RUN_B}`
      );
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Comparing two runs' }).first();
      await expect(heading).toBeVisible({ timeout: 20_000 });
      // The panel states that it neither writes nor judges. Asserted because it
      // is the claim a screenshot of a table headed "Comparison" most invites a
      // reviewer to doubt.
      await expect(page.locator('.rc-scope').first()).toContainText(/nothing here changes either run/i);
      return heading;
    },
    // `RunCompare.tsx:276`. The panel is the state; the record page around it is
    // already photographed by `record-edit`.
    frame: ({ page }) => page.locator('section.rc-panel'),
  },
  {
    /*
     * NEW. Validate & Review — the record-level "check it against the same
     * deterministic validators the export gate uses" panel.
     *
     * IDLE, and left that way on purpose. Pressing the button issues
     * `POST …/runs/{id}/check`, which is documented on the panel itself as
     * read-only; but the idle state is the one every reader meets first and the
     * one that carries the panel's scope sentence, and photographing it costs no
     * request against a shared scope at all.
     */
    id: 'record-validate-review',
    what: 'Record → Validate & Review, before it has run — what it checks and what it will not do',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.partial}`);
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Validate & Review' }).first();
      await expect(heading).toBeVisible({ timeout: 20_000 });
      await expect(page.locator('.validate-review .vr-status').first()).toBeVisible();
      return heading;
    },
    // `ValidateReview.tsx:339`. Shares its URL with four other states.
    frame: ({ page }) => page.locator('section.validate-review'),
  },
  {
    /*
     * NEW. Unmapped Notes — content captured against a record that has no
     * confident schema home. Directly a no-guessing surface (CLAUDE.md §5): it
     * exists so that content without a home is neither forced into a field nor
     * dropped, and its own sub-line says nothing here is a field value.
     */
    id: 'record-unmapped-notes',
    what: 'Record → Unmapped Notes — captured content with no confident schema home, kept rather than forced',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.partial}`);
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Unmapped Notes' }).first();
      await expect(heading).toBeVisible({ timeout: 20_000 });
      return heading;
    },
    // `UnmappedNotesPanel.tsx:120`. Shares its URL with four other states.
    frame: ({ page }) => page.locator('section.notes-section'),
  },
  {
    /*
     * NEW. Asset References — the files a record points at. The disclosure under
     * the heading is the load-bearing part and is asserted, not just
     * photographed: ISAAC stores the reference only, so a digest shown here is
     * the one a person entered and has been checked against nothing. A
     * screenshot of a sha256 beside a filename says the opposite unless that
     * sentence is on screen with it.
     */
    id: 'record-asset-references',
    what: 'Record → Asset References — pointers to files, with the "we did not hash this" disclosure',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.partial}`);
      await settled(page);
      const heading = page.getByRole('heading', { name: 'Asset References' }).first();
      await expect(heading).toBeVisible({ timeout: 20_000 });
      await expect(page.locator('.assets-sub').first()).toContainText(/does not upload, open, download or hash/i);
      return heading;
    },
    /*
     * `AssetReferencesPanel.tsx:195`. Shares its URL with four other states — and
     * this is the one where the crop is load-bearing rather than merely tidier:
     * the disclosure asserted above is what stops a sha256 beside a filename
     * reading as a verification, and in a 2400px page shot it is four lines
     * somewhere in the lower third.
     */
    frame: ({ page }) => page.locator('section.assets-section'),
  },
  {
    id: 'record-confirmation',
    what: 'Guided completion — one question, with "I don\'t know" as a first-class answer',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.partial}/complete`);
      await settled(page);
      const confirm = page.getByRole('button', { name: 'Confirm', exact: true });
      await expect(confirm.first()).toBeVisible({ timeout: 20_000 });
      return confirm.first();
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
    /*
     * NEW. The Evidence GRAPH — a `?view=` deep link on the evidence route and
     * NOT the same DOM as the entry above it. The catalogue entry
     * (`surfaces.ts` → `evidence-graph`) records why it had to be added there
     * too: the route DEFAULTS to the list view, so a canvas, a `role="tree"`,
     * the kind-filter chips and the details pane were unmeasured markup on a
     * measured route.
     */
    id: 'record-evidence-graph',
    what: 'Evidence → Graph — evidence, its sources and the runs they belong to, as a graph',
    async reach({ page, app }) {
      await app.open(evidenceGraphSurface);
      const heading = page.getByRole('heading', { name: 'Evidence Graph' }).first();
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
    /*
     * ADDED THE MOMENT IT BECAME PHOTOGRAPHABLE, which is the whole discipline
     * this file exists to enforce.
     *
     * `RevisionHistoryPanel` began mounting UNCONDITIONALLY on
     * `/record/:id/export` when the revision-history slice merged — a route this
     * sweep already visited three times without photographing the new markup.
     * That is exactly the failure mode the header describes: new content on a
     * measured route that the sweep walks past.
     *
     * On this deployment the panel renders its UNAVAILABLE state, because the
     * `0003`/`0004` migrations are not applied here — the panel's own comment
     * says so. That is deterministic and worth a picture: it is the state every
     * reader of this build actually sees, and the one where a careless wording
     * would read as "this record has never been submitted" rather than "this
     * deployment cannot know".
     *
     * The heading is unconditional, so it is the primary; the availability copy
     * below it varies with deployment and is not asserted here.
     */
    id: 'record-revision-history',
    what: 'Submission History on Export Readiness — read-only, and honest about what it cannot read here',
    async reach({ page, app }) {
      await app.gotoExample(`/record/${SEED.ready}/export`);
      await settled(page);
      // `.first()`, because the role query matches TWICE on this screen and a
      // multi-match locator makes `toBeVisible` a strict-mode violation rather
      // than a visibility check — which reports as "expect(locator).toBeVisible()
      // failed" and reads exactly like an unreachable state. Probed rather than
      // assumed: `h2` text is `["Submission History"]` (one), while the heading
      // ROLE resolves to 2. Same treatment `record-confirmation` already uses.
      const heading = page
        .getByRole('heading', { name: 'Submission History' })
        .first();
      await expect(heading).toBeVisible({ timeout: 20_000 });
      return heading;
    },
    // `RevisionHistoryPanel.tsx:91`. This state shares `/record/:id/export` with
    // `record-validation`, and before this frame existed the two attached the
    // same image.
    frame: ({ page }) => page.locator('section.revhist-section'),
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
      await expect(conflict.first()).toBeVisible({ timeout: 20_000 });
      await expect(conflict.first()).toContainText(/immutable/i);
      return conflict.first();
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
    // The drawer IS the state. Below 1024px it is a slide-over that covers the
    // record; at or above it, it is a static column beside it — either way the
    // conversation is what this caption promises.
    frame: ({ page }) => page.locator('aside.assistant-drawer-panel'),
    /*
     * ADDED — this state had NO cleanup, and that was a live sticky-scope leak
     * rather than a tidiness gap.
     *
     * `app.gotoExample()` calls `enterWorkedExample`, which installs a
     * `page.route` attaching the session header to EVERY subsequent API request,
     * and nothing removes it (see the long note on `tutorial-start`'s cleanup for
     * why "ordinary scope" does not mean "leave the scope"). The next state,
     * `tutorial-coach-mark`, then navigated ORDINARY-scope with the header still
     * attached. It was benign only by ordering and luck: move
     * `statistics-general` — whose caption claims "every figure derived from an
     * empty list" — after this state, and it would silently photograph the worked
     * example's five records under that caption.
     */
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    /*
     * ── FROM HERE ON A REAL WALKTHROUGH IS RUNNING ─────────────────────────
     *
     * Started from the Replay control this sweep photographed earlier, because
     * `tutorial.markCompleted()` has already retired the first-run offer. It
     * mints a session of ITS OWN; the `tutorial` fixture disposes every session
     * the page caused to exist, whether or not a test reaches an exit path.
     *
     * `Replay Tutorial` and not the empty state's `Launch Guided Demo`: both
     * call `startTutorial`, but Replay is the walkthrough's documented permanent
     * home (`HelpAndTutorial.tsx`), and reaching it here means the surface that
     * carries it has already been photographed two states before this one.
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
    // THE VIEWPORT, because the claim in the caption is about the RELATIONSHIP
    // between a fixed overlay and the control under it. `.screen-card` would omit
    // the mark entirely (`AppShell` mounts `GuidedTutorial` as its sibling), and
    // an element shot of a fixed mark inside a document-tall frame is a picture
    // of an arrangement no reader ever sees.
    frame: () => 'viewport',
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
      /*
       * The preview has settled and the gate is closed. The typed phrase is
       * NEVER entered — and the phrase the field asks for is `RESET`
       * (`ResetDemoDialog.tsx` → `TYPED_GATE`), which is NOT the backend's
       * `RESET EXAMPLE WORKSPACE` confirmation string. CLAUDE.md §11 records
       * that the two have been conflated before; nothing here types either.
       */
      const action = dialog.getByRole('button', { name: 'Reset Example Records' });
      await expect(action).toBeDisabled();
      return action;
    },
    // The viewport: a modal and its backdrop over the surface it was opened from
    // is what a reader sees, and the dialog is `position: fixed`.
    frame: () => 'viewport',
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
    // Fixed overlay, as above.
    frame: () => 'viewport',
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

  test('@responsive the surface catalogue still carries the entries this sweep opens', () => {
    // `surface()` ends in `!`. Without this, a catalogue id that is renamed or
    // removed surfaces as a `TypeError` reading `.path` of undefined, inside a
    // 20-minute browser run, at whichever width got there first. Here it is a
    // sub-second failure naming the id.
    for (const id of ['experiments', 'experiments-example', 'evidence-graph', 'settings-connect']) {
      expect(
        SURFACES.find((s) => s.id === id),
        `visual-sweep opens the catalogued surface "${id}", which is no longer in SURFACES. ` +
          'Point this sweep at the entry that replaced it rather than inlining a path here.'
      ).toBeDefined();
    }
  });

  test('@responsive the width grids agree except where they must not', () => {
    // See the long note on WIDTHS. 1440 belongs to THIS sweep and to nothing
    // else: adding it to `LAYOUT_SWEEP_WIDTHS` gives every surface a
    // `surfaceId@width-1440` key in `LAYOUT_BASELINE` with no measured value
    // behind it, and the layout sweep then fails with a large diff whose cause is
    // three files away. This assertion is that failure, moved to where the cause
    // is written down.
    expect(
      SWEEP_WIDTHS.includes(EXTRA_WIDTH),
      `${EXTRA_WIDTH} must NOT be in LAYOUT_SWEEP_WIDTHS. It is this sweep's own width. Adding ` +
        `it there gives every surface a "${layoutWidthId(EXTRA_WIDTH)}" baseline key that nothing ` +
        'has ever measured, which fails `specs/layout-widths.spec.ts` with an unexplained diff. ' +
        'If the layout sweep genuinely should measure it, add the baseline entries in the same ' +
        'change and delete EXTRA_WIDTH here.'
    ).toBe(false);
    // The other direction: a width the layout sweep measures is a width this one
    // photographs, so the two cannot silently diverge into "measured but never
    // seen". 640 is the one documented exception.
    for (const w of SWEEP_WIDTHS) {
      if (w === OMITTED_WIDTH) continue;
      expect(WIDTHS, `width ${w} is measured by the layout sweep but photographed by nothing`).toContain(w);
    }
    expect(new Set(WIDTHS).size, 'duplicate width').toBe(WIDTHS.length);
  });

  for (const width of WIDTHS) {
    test(`@responsive width ${width}: capture every state, and assert each one`, async (
      { page, app, tutorial },
      testInfo
    ) => {
      /*
       * A CEILING, NOT A COST, AND NOW A MEASURED ONE. The project-wide 60s
       * timeout is sized for a single-surface test; this drives 30 states,
       * several of them multi-step. A clean width MEASURES at ~26s
       * (width 1280, host project, serial), so this ceiling is roughly 46x the
       * observed time and exists only so that a genuinely stuck state fails with
       * this file's own aggregated report rather than with a bare test timeout
       * that names nothing.
       *
       * It is deliberately NOT tightened to the measurement. An unreachable state
       * burns its own `expect` timeout before the loop moves on, so the run in
       * which this number matters is precisely the run that is already much
       * slower than 26s — and a ceiling that only holds while everything passes
       * is a ceiling that converts findings into timeouts.
       */
      test.setTimeout(1_200_000);

      await page.setViewportSize({ width, height: VIEWPORT_HEIGHT });
      const platform = currentPlatform();
      const ctx: Ctx = { page, app, tutorial, width };

      const captured: string[] = [];
      /** id → the reason it could not be captured. Failed at the end, all at
       *  once, so one broken state does not hide the other twenty-nine. */
      const unreachable: string[] = [];
      const pageScroll: string[] = [];
      const primaryFailures: string[] = [];
      const clippedFailures: string[] = [];
      /**
       * sha256 of every attached image → the FIRST state that attached those
       * bytes. Two states attaching the same image is a finding, not a curiosity:
       * it is the exact defect this file shipped with (see the header), it passed
       * every other assertion here, and at narrow widths it hid itself behind
       * `position: fixed` chrome painted at a different scroll offset.
       */
      const imageOwners = new Map<string, string>();
      const duplicateImages: string[] = [];
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
          // It also scrolls the primary into view. That is for the OFF-SCREEN
          // check's benefit and for nothing else: the header used to credit this
          // scroll with framing the shot, which was measured false — the image
          // comes from `frame` below and does not depend on scroll position.
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
          // THE ELEMENT THAT IS THE STATE, not `fullPage`. See the header for the
          // measurement that forced this, and `VisualState.frame` for the rules.
          const frame = state.frame ? await state.frame(ctx, primary) : page.locator(DEFAULT_FRAME);
          let shot: Buffer;
          if (frame === 'viewport') {
            shot = await page.screenshot({ animations: 'disabled' });
          } else {
            if ((await frame.count()) === 0) {
              // Reached but not photographable. Loud, and honest about which of
              // the two it is — `captured` means "an image is attached".
              throw new Error(
                'state reached, but its declared frame element is not on the page, so there is ' +
                  'no image to attach. Point `frame` at the element that is really this state.'
              );
            }
            const target = frame.first();
            // Playwright scrolls a target into view itself; done explicitly for
            // parity with `specs/statistics-states.spec.ts` and so a failure here
            // names the scroll rather than the screenshot.
            await target.scrollIntoViewIfNeeded().catch(() => undefined);
            shot = await target.screenshot({ animations: 'disabled' });
          }

          const digest = createHash('sha256').update(shot).digest('hex');
          const twin = imageOwners.get(digest);
          if (twin === undefined) imageOwners.set(digest, state.id);
          else duplicateImages.push(`${state.id}: byte-identical to ${twin} (sha256 ${digest.slice(0, 12)})`);

          await testInfo.attach(`${width}px · ${state.id} — ${state.what}`, {
            body: shot,
            contentType: 'image/png',
          });
          captured.push(state.id);
        } catch (err) {
          unreachable.push(`${state.id}: ${(err as Error).message.split('\n')[0]}`);
        } finally {
          if (state.cleanup) await state.cleanup(ctx).catch(() => undefined);
          /*
           * UNCONDITIONAL, and it is a structural fix rather than housekeeping.
           *
           * Two measured problems, one line. (1) A state that forgets a cleanup
           * leaks `enterWorkedExample`'s session-header `page.route` into the next
           * state — `assistant-answer` did exactly that, and the state after it
           * navigated ordinary-scope inside the worked example. (2) Every
           * `gotoExample`/`open` STACKS another handler for the same glob, so by
           * the last state a width had accumulated roughly fifteen of them, each
           * one an extra `route.fallback()` hop on every API request.
           *
           * Safe, for the reason `tutorial-start`'s cleanup already records: every
           * example-scope state re-enters the scope itself, on every navigation.
           * And safe for the walkthrough states that follow, whose session is the
           * APP's own (minted through the Replay control) rather than a header this
           * harness attaches — plus `tutorial.sessionsCreated()` observes
           * `page.on('response')`, not a route, so unrouting cannot blind it or
           * strand a session.
           */
          await page.unrouteAll({ behavior: 'ignoreErrors' }).catch(() => undefined);
        }
      }

      testInfo.annotations.push({
        type: 'visual-sweep',
        description:
          `${layoutWidthId(width)} on ${platform} — font: ${font}; ` +
          `${captured.length}/${STATES.length} states captured as attachments; ` +
          `${unreachable.length} unreachable, ${pageScroll.length} page-scroll, ` +
          `${primaryFailures.length} primary-element, ${clippedFailures.length} content-loss, ` +
          `${duplicateImages.length} duplicate-image finding(s); ` +
          `${imageOwners.size} distinct image(s) for ${captured.length} attachment(s).`,
      });
      // eslint-disable-next-line no-console
      console.log(
        `[visual-sweep] ${width}px — font: ${font}; captured ${captured.length}/${STATES.length}` +
          `; ${imageOwners.size} distinct image(s)` +
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

      /*
       * EVERY ATTACHMENT MUST BE ITS OWN PICTURE. Second, and directly after the
       * set, because "thirty attachments" and "thirty pictures" are different
       * claims and this file used to make the first while the report read as the
       * second: five states shared one image and two more shared another, and
       * nothing failed.
       *
       * Duplicate bytes mean one of two things, and both are findings: two states
       * are photographing the same frame (fix `frame`), or two states are the same
       * state (fix `STATES`).
       */
      expect(
        duplicateImages,
        duplicateImages.length
          ? `Two or more states attached the SAME IMAGE at ${width}px, so the report shows fewer ` +
            `pictures than it appears to. Either a state's \`frame\` is not the element that IS ` +
            `that state — a page-level frame on a route several states share is how this happened ` +
            `before — or two entries in STATES are the same state:\n${duplicateImages.join('\n')}`
          : undefined
      ).toEqual([]);

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
 * (`base.css` — `width: 1px; height: 1px; clip: rect(0,0,0,0)`), and 1
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
 *     what every `.sr-only` accessible-name carrier is, and several of this app's
 *     screens make their `<h1>` one — every record surface does. That is why no
 *     state above uses a record screen's `<h1>` as its primary.
 *     `MIN_PRIMARY_BOX_PX` is the line;
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
 * screen with nothing wrong look identical from the outside, and a clean sweep is
 * exactly the result a broken probe would produce.
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
 * The sweep above takes 210 captures (30 states x 7 widths) and, when the app is
 * healthy, reports zero primary-element findings. That is the same output a probe
 * with a bug in it would produce, so the probe is falsified here against INJECTED
 * geometry —
 * the technique `self-check.spec.ts` and `layout-widths.spec.ts`'s regression
 * cases already use. All four mutations are browser-side only; nothing is
 * written to the backend.
 *
 * The page-scroll check is deliberately NOT self-checked: it compares
 * `document.documentElement.scrollWidth` with `clientWidth` and there is no
 * intermediate logic to get wrong. The CONTENT-LOSS check is not self-checked
 * here either, because `layout-widths.spec.ts` cases T1/E1/C1/I1 already falsify
 * `findClippedText` and `findOverflowingRegions` against the exact geometry of
 * measured defects, and duplicating them would mean two places to update.
 *
 * These four open `experiments` in the ORDINARY scope, whose queue is empty, so
 * V4's real control is the empty state's `Launch Guided Demo` and not the
 * first-run offer's `Start Tutorial` — that card does not render here. See the
 * note on the `tutorial-start` state.
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
    expect(await primaryHealth(page.getByRole('button', { name: 'Launch Guided Demo' }))).toBe('ok');
    expect(await primaryHealth(page.locator('#no-such-element-anywhere'))).toBe(
      'primary element is not in the DOM'
    );
  });
});

/**
 * THE RUN CARD AT NARROW WIDTHS AND AT 200% ZOOM — the one surface the width
 * sweep structurally cannot reach.
 *
 * ── Why this file is in the MUTATION suite, against its config's own header ──
 *
 * `playwright.mutation.config.ts` says, in as many words, "ONE viewport project,
 * not five … Layout and accessibility at five widths are the other suite's job."
 * That was true of every spec in this directory when it was written, and this file
 * is the exception it did not anticipate — so the reasoning is stated here rather
 * than left as a contradiction for the next reader to find.
 *
 * The read-only suite sweeps `e2e/surfaces.ts` at 1280/1024/768/640/390/375/320
 * (`specs/layout-widths.spec.ts`) and at the 640x400@DPR2 zoom project. NOT ONE
 * of those 20 surfaces renders a run card: every one is a read of committed state,
 * and a run only exists after `POST /api/experiments/{id}/runs`. Verified by
 * `rg -l 'run-card|data-run-id|Add Run' apps/web/e2e/`, which names exactly one
 * file — `e2e/mutation/runs.spec.ts`. So the Run vertical slice shipped a new
 * multi-control card that the responsive and zoom sweeps had never measured, and
 * could not measure without a mutation.
 *
 * Making the read-only suite create a run is the alternative, and it is worse: its
 * `globalSetup` opens ONE worked-example session that five viewport projects read
 * in parallel, and its assertions are about canonical seed CONTENT. A run added
 * there is visible to all five projects at once. That is the collision the two
 * suites exist to avoid.
 *
 * ── What is asserted, and what is deliberately NOT ──────────────────────────
 *
 * ASSERTED, scoped to `section.runs-section`: no nested overflow, no clipped
 * text, no obscured control, at six widths and at 200% zoom, with TWO runs open
 * (the pressure case — two expanded cards, each with three fields, a save-status
 * chip, a progress line and a conditions line).
 *
 * NOT asserted here: whole-document horizontal scroll as an absolute number. The
 * record screen ALREADY has recorded document-level offenders at 320/375/390
 * (`e2e/layout-baseline.ts`, `record-detail@width-320` and siblings), inherited
 * from the screen shell rather than from anything in this slice. Asserting
 * `docScrollWidth <= docClientWidth` here would fail for a cause this file cannot
 * fix and does not own, and the honest failure would look like a run-card defect.
 *
 * So the document is measured DIFFERENTIALLY instead: the same page, same width,
 * with zero runs and then with two, and the run cards must not widen the document
 * by a single pixel. That is the claim this slice is actually responsible for, and
 * unlike an absolute threshold it cannot be satisfied by someone else's fix or
 * broken by someone else's regression.
 *
 * NO ALLOWLIST. `layout-allowlist.ts` and `layout-baseline.ts` record measured,
 * argued exceptions for surfaces that already had them; this surface has never
 * been measured, so it starts with none. An offender found here is a defect to
 * fix, not an entry to add.
 *
 * ── The 200% zoom case ─────────────────────────────────────────────────────
 *
 * `{ width: 640, height: 400 }` + `deviceScaleFactor: 2`, which is exactly the
 * `zoom-200` project's emulation. `playwright.config.ts`'s header derives those
 * two numbers and lists the emulation's honest limits (`outerWidth`, scrollbars,
 * `visualViewport.scale`, text-metric rounding, OS text scaling); every one of
 * them applies here too and is not restated. DPR must be set at CONTEXT creation
 * — `page.setViewportSize` cannot change it — so this case runs in its own
 * context via `browser.newContext`, and pays for its own session because the
 * auto-use `scope` fixture only reaches the fixture-provided page.
 */

import { expect as pwExpect, test as base, type BrowserContext, type Page } from '@playwright/test';
import { MUT_API_BASE, MUT_API_ROUTE_GLOB, MUT_BASE_URL, SEED } from './env';
import { applyWorkedExampleScope, disposeWorkedExampleSession } from '../worked-example';
import { activeElementFocusInfo } from '../helpers/focus';
import {
  findClippedText,
  findObscuredControls,
  findOverflowingRegions,
  horizontalPageScroll,
  render,
  renderedFontFamily,
  renderOverflow,
  scrollToBottom,
  scrollToTop,
} from '../helpers/layout';
import { expect, openRecord, test } from './own-session-fixtures';

/** The subtree this file owns. Everything outside it belongs to another suite. */
const RUNS_ROOT = 'section.runs-section';

/**
 * Breakpoint and content-pressure widths. 320 is the WCAG 1.4.10 reflow width and
 * is required; 390 is the modern phone width. 1440 is added above the read-only
 * sweep's 1280 ceiling because the run card's field grid has a wide-screen column
 * treatment that no other measurement in the repository exercises.
 */
const WIDTHS = [1440, 1280, 1024, 768, 390, 320] as const;

/** Where the screenshots for a human sign-off land. Committed nowhere. */
const SHOT_DIR = 'test-results/run-card-responsive';

/* ── the pressure case ─────────────────────────────────────────────────────── */

const addRun = (page: Page) => page.getByRole('button', { name: 'Add Run' });
const runCards = (page: Page) => page.locator('article.run-card');

/**
 * Open the record, add two runs, and leave BOTH expanded.
 *
 * Two, not one: a single card cannot show a run-to-run collision, and the
 * `.run-save-status` chip and the header's controls sit on the same line as the
 * label — which is where a narrow-width collision would appear.
 *
 * A newly added card is expanded by the component (focus moves to its header), so
 * this asserts the expanded state rather than assuming it: if that changes, this
 * spec must fail loudly rather than quietly measure two collapsed strips.
 */
async function twoOpenRuns(page: Page) {
  await openRecord(page, SEED.partial);
  await pwExpect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible();
  await pwExpect(addRun(page)).toBeEnabled();

  await addRun(page).click();
  await pwExpect(runCards(page)).toHaveCount(1);
  await addRun(page).click();
  await pwExpect(runCards(page)).toHaveCount(2);

  // Both cards' bodies present — the state under measurement, asserted not assumed.
  await pwExpect(page.locator('article.run-card .run-card-body')).toHaveCount(2);
  await pwExpect(page.locator('article.run-card .run-field')).not.toHaveCount(0);
}

/* ── the measurement, shared by the width sweep and the zoom case ──────────── */

interface Findings {
  overflow: string;
  clipped: string;
  obscured: string;
}

/**
 * Probe the runs subtree at whatever viewport the page is currently at.
 *
 * `findObscuredControls` is run at BOTH scroll extremes because its own docstring
 * says elements with no visible area are skipped — a control pushed below the fold
 * is invisible to it until scrolled to. Two positions is what that docstring asks
 * of a caller.
 */
async function probeRuns(page: Page): Promise<Findings> {
  const overflow = await findOverflowingRegions(page, []);
  const runsOverflow = overflow.offenders.filter((o) => o.selector.includes('run'));

  const clipped = (await findClippedText(page, RUNS_ROOT, [])).filter((o) => o.text.trim() !== '');

  await scrollToTop(page);
  const obscuredTop = await findObscuredControls(page);
  await scrollToBottom(page);
  const obscuredBottom = await findObscuredControls(page);
  await scrollToTop(page);
  const seen = new Set<string>();
  const obscured = [...obscuredTop, ...obscuredBottom].filter((o) => {
    const key = `${o.selector}::${o.detail}`;
    if (seen.has(key) || !o.selector.includes('run')) return false;
    seen.add(key);
    return true;
  });

  return {
    overflow: runsOverflow.length ? renderOverflow(runsOverflow) : '',
    clipped: clipped.length ? render(clipped) : '',
    obscured: obscured.length ? render(obscured) : '',
  };
}

/** Every control a scientist needs on this card must be operable, not merely present. */
async function assertOperable(page: Page) {
  // Add Run stays discoverable — it is how the workspace grows, and it sits in a
  // toolbar that is the first thing a narrow width compresses.
  await pwExpect(addRun(page)).toBeVisible();
  await pwExpect(addRun(page)).toBeEnabled();

  // The accordion still toggles. Collapse the first card and re-expand it, through
  // the header button a reader would use.
  const first = runCards(page).first();
  const header = first.locator('button.run-card-header');
  await pwExpect(header).toBeVisible();
  await header.click();
  await pwExpect(first.locator('.run-card-body')).toHaveCount(0);
  await header.click();
  await pwExpect(first.locator('.run-card-body')).toHaveCount(1);

  /*
   * Keyboard focus paints something.
   *
   * ARRIVED AT BY PRESSING TAB, and the first version of this did not — it called
   * `locator.focus()` and then asserted an outline, which reported "no visible focus
   * indicator" on a header whose ring is fine. `helpers/focus.ts`'s own header says
   * why: this app's ring lives in a `:focus-visible` rule, and only real keyboard
   * focus engages `:focus-visible`. A programmatic focus after a click leaves the
   * heuristic in mouse mode, so the rule does not match and nothing is painted. That
   * finding was the TEST's defect, and is recorded here so it is not re-introduced.
   *
   * The verdict comes from `activeElementFocusInfo`, which diffs the focused and
   * resting paint on the same element, so "an outline rule exists" cannot pass for
   * "focus changes what the user sees". Its honest limit applies: it proves an
   * indicator exists, not that it meets WCAG 2.4.11 contrast or area.
   */
  const reached = await tabTo(page, 'button.run-card-header');
  pwExpect(reached, 'no number of Tab presses reached a run card header').toBe(true);
  const focus = await activeElementFocusInfo(page);
  pwExpect(focus, 'nothing was focused after tabbing to the run card header').not.toBeNull();
  pwExpect(
    focus!.visible,
    `focused run card header paints no perceptible focus indicator — ` +
      `changed: [${focus!.changed.join(', ')}], perceptible: [${focus!.indicators.join(', ')}], ` +
      `outline: ${focus!.outline}, box-shadow: ${focus!.boxShadow}`
  ).toBe(true);
}

/**
 * Press Tab until the focused element matches `selector`, or give up.
 *
 * Bounded rather than open-ended so a regression that removes the header from the
 * tab order fails in seconds instead of hanging. The bound is generous: the record
 * screen's shell contributes a skip link, a brand link, breadcrumbs, a nav and the
 * record's own controls ahead of the runs section.
 */
async function tabTo(page: Page, selector: string, maxPresses = 80): Promise<boolean> {
  for (let i = 0; i < maxPresses; i += 1) {
    await page.keyboard.press('Tab');
    const hit = await page.evaluate(
      (sel) => document.activeElement instanceof Element && document.activeElement.matches(sel),
      selector
    );
    if (hit) return true;
  }
  return false;
}

/* ── the width sweep ───────────────────────────────────────────────────────── */

test.describe('run card — narrow widths', () => {
  for (const width of WIDTHS) {
    test(`@responsive run card at ${width}: nothing overflows, clips, or is obscured`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 812 });
      await twoOpenRuns(page);

      testInfo.annotations.push({
        type: 'rendered-font',
        description: `${width}px: ${await renderedFontFamily(page)}`,
      });

      const findings = await probeRuns(page);
      await page.screenshot({
        path: `${SHOT_DIR}/run-card-${width}.png`,
        fullPage: true,
      });

      const failures = [
        findings.overflow && `OVERFLOW inside the runs section:\n${findings.overflow}`,
        findings.clipped && `TEXT LOST inside the runs section:\n${findings.clipped}`,
        findings.obscured && `CONTROLS OBSCURED inside the runs section:\n${findings.obscured}`,
      ].filter(Boolean);

      expect(failures.join('\n\n'), `run card at ${width}px`).toBe('');

      await assertOperable(page);
    });
  }

  /**
   * THE SAVE-STATUS CHIP, WHICH THE SWEEP ABOVE CANNOT SEE.
   *
   * `.run-save-status` is rendered only while a save is in flight or after one
   * failed, so every measurement above ran with that element absent — the sweep
   * would pass a chip that collided with the header's controls at 320px. This test
   * puts the card into the state that renders it and re-probes, at the two widths
   * where a chip has least room.
   *
   * The chip is produced by a REAL save: a real keystroke, the component's own
   * debounce, and a real `PATCH` answered by the real backend. Nothing is stubbed,
   * so if the chip stops appearing this fails rather than silently measuring its
   * absence — which is why the visibility of `.run-save-status` is asserted before
   * anything is measured.
   */
  for (const width of [390, 320] as const) {
    test(`@responsive the save-status chip does not collide at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 812 });
      await twoOpenRuns(page);

      const first = runCards(page).first();
      const temperature = first.locator(
        '.run-field:has(.run-field-path:text-is("context.temperature_K")) input'
      );
      await pwExpect(temperature).toBeVisible();
      await temperature.fill('277.15');

      // The chip, in whichever state the save reaches. Asserted present, so an
      // absent chip is a failure rather than a silently empty measurement.
      const chip = first.locator('.run-save-status');
      await pwExpect(chip).toBeVisible({ timeout: 15_000 });

      const findings = await probeRuns(page);
      await page.screenshot({
        path: `${SHOT_DIR}/run-card-save-chip-${width}.png`,
        fullPage: true,
      });

      const failures = [
        findings.overflow && `OVERFLOW with the save chip present:\n${findings.overflow}`,
        findings.clipped && `TEXT LOST with the save chip present:\n${findings.clipped}`,
        findings.obscured && `CONTROLS OBSCURED with the save chip present:\n${findings.obscured}`,
      ].filter(Boolean);

      expect(failures.join('\n\n'), `save-status chip at ${width}px`).toBe('');
    });
  }

  /**
   * THE DIFFERENTIAL DOCUMENT CHECK — the claim this slice owns.
   *
   * Absolute document overflow on this screen is pre-existing and recorded in
   * `layout-baseline.ts`; see the file header. What must hold is that the run
   * cards add nothing to it. Measured at 320, the width where a pixel costs most.
   */
  test('@responsive run cards widen the document by nothing at 320', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 812 });

    await openRecord(page, SEED.partial);
    await pwExpect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible();
    await pwExpect(addRun(page)).toBeEnabled();
    await pwExpect(runCards(page)).toHaveCount(0);
    const before = await horizontalPageScroll(page);

    await addRun(page).click();
    await pwExpect(runCards(page)).toHaveCount(1);
    await addRun(page).click();
    await pwExpect(runCards(page)).toHaveCount(2);
    await pwExpect(page.locator('article.run-card .run-card-body')).toHaveCount(2);
    const after = await horizontalPageScroll(page);

    expect(
      after.docScrollWidth,
      `two open run cards widened the document from ${before.docScrollWidth} to ` +
        `${after.docScrollWidth} at 320px (clientWidth ${after.docClientWidth}). ` +
        'Whatever the screen shell already overflows by, the run card must add nothing.'
    ).toBeLessThanOrEqual(before.docScrollWidth);
  });
});

/* ── 200% zoom ─────────────────────────────────────────────────────────────── */

/**
 * The zoom case needs `deviceScaleFactor`, which is fixed at context creation, so
 * it cannot reuse the fixture page. It therefore builds its own context, its own
 * worked-example session and its own scope — the same escape
 * `tutorial-lifecycle.spec.ts` takes, visible here rather than hidden in an
 * override — and disposes both in a `finally`.
 *
 * It uses the bare `base` test, not the extended one, precisely so the auto-use
 * `scope` fixture does not open a session this test would not use.
 */
base('@responsive run card at 200% zoom (640x400 @ DPR2) stays usable', async ({ browser }) => {
  const context: BrowserContext = await browser.newContext({
    viewport: { width: 640, height: 400 },
    deviceScaleFactor: 2,
    baseURL: MUT_BASE_URL,
  });
  const page = await context.newPage();

  const opened = await context.request.post(`${MUT_API_BASE}/tutorial/sessions`);
  pwExpect(
    opened.status(),
    `could not open a worked-example session for the zoom case: ${await opened.text()}`
  ).toBe(201);
  const sessionId = ((await opened.json()) as { session_id?: string }).session_id;
  pwExpect(typeof sessionId === 'string' && sessionId !== '').toBeTruthy();

  try {
    // Installs the route handler that attaches the session header to every API
    // call this page makes, and survives reloads. Same helper, same glob, same
    // argument order as the `scope` fixture — not a second implementation.
    await applyWorkedExampleScope(page, sessionId!, MUT_API_ROUTE_GLOB);

    // The emulation's PARAMETERS are proved in the live page, exactly as
    // `specs/zoom-200.spec.ts` does — so a silent drop of `deviceScaleFactor`
    // fails here instead of quietly downgrading this to "a 640px window".
    const emulation = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      dpr: window.devicePixelRatio,
    }));
    pwExpect(emulation.innerWidth).toBe(640);
    pwExpect(emulation.dpr).toBe(2);

    await twoOpenRuns(page);

    const findings = await probeRuns(page);
    await page.screenshot({ path: `${SHOT_DIR}/run-card-zoom-200.png`, fullPage: true });

    const failures = [
      findings.overflow && `OVERFLOW inside the runs section:\n${findings.overflow}`,
      findings.clipped && `TEXT LOST inside the runs section:\n${findings.clipped}`,
      findings.obscured && `CONTROLS OBSCURED inside the runs section:\n${findings.obscured}`,
    ].filter(Boolean);

    pwExpect(failures.join('\n\n'), 'run card at 200% zoom').toBe('');

    await assertOperable(page);
  } finally {
    // Idempotent and swallowed, matching the `session` fixture: cleanup must never
    // turn a passing test red.
    await disposeWorkedExampleSession(sessionId!, MUT_API_BASE).catch(() => undefined);
    await context.close();
  }
});

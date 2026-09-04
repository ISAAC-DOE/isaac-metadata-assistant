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
 * (the pressure case — two expanded cards, each with five fields, a save-status
 * chip, a progress line and a conditions line).
 *
 * THE DOCUMENT IS MEASURED BOTH WAYS, and the first version of this file measured
 * only one of them on a premise a reviewer showed to be false. It said an absolute
 * `docScrollWidth <= docClientWidth` "would fail for a cause this file cannot fix",
 * citing `e2e/layout-baseline.ts`'s `record-detail@width-320` and siblings as
 * document-level offenders on this screen. They are not. Those entries are under
 * LAYOUT-04, whose own note reads "NESTED horizontal overflow: regions that scroll
 * or clip sideways INSIDE the page **while the document itself measures clean**",
 * and no document-level finding exists anywhere in that file. Measured on this
 * surface with two open runs, `docScrollWidth == docClientWidth` at all six widths
 * and at the zoom case — so the stronger assertion was available all along, and the
 * paragraph excusing its absence was the only thing standing in its way.
 *
 * Both now run. The DIFFERENTIAL form (zero runs, then two, at 320) is kept because
 * it attributes a regression to this slice rather than to the shell; the ABSOLUTE
 * form is added because it is strictly stronger and passes today.
 *
 * NEITHER OF THEM CAN SEE THE WORST CASE, which is why `cardsTooWide` exists:
 * `main#main.screen-main.pad` is `overflow-x: auto` and absorbs a card wider than
 * the page without the document growing at all.
 *
 * ── The tag is `@runs-layout`, and it MUST NOT be `@responsive` ─────────────
 *
 * These titles were tagged `@responsive` at first, and CI failed in the way that
 * teaches the rule: every test errored with `connect ECONNREFUSED 127.0.0.1:8100`
 * in the `desktop-1280x800` project of the READ-ONLY suite.
 *
 * `playwright.config.ts` sets `testDir: './e2e'` with `testMatch: /.*\.spec\.ts$/`,
 * so the read-only suite COLLECTS every spec under `e2e/` — this directory included.
 * What keeps the other mutation specs out of it is not the directory; it is that no
 * project's `grep` matches their titles. `ALL_VIEWPORTS = /@responsive/` matched
 * these, so the read-only suite ran them against a backend only the mutation
 * config starts — port 8100, which nothing was listening on.
 *
 * So the tag is deliberately one no project in `playwright.config.ts` greps for.
 * Renaming it to `@responsive` "for consistency" would re-break CI in a way that
 * looks like a product failure and is not one.
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
import { hiddenTextMatchersFor, overflowMatchersFor } from '../layout-allowlist';
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
  await openRecord(page, SEED.partial, 'runs');
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
  tooWide: string;
}

/**
 * Does this offender belong to the runs section?
 *
 * ASKED OF THE DOM, NOT OF THE SELECTOR STRING, and the first version of this file
 * asked the string — `o.selector.includes('run')`. A reviewer broke it with two
 * declarations: `min-width: 400px` on `.run-card` at a 320px viewport, a card 160px
 * wider than its container, **and all ten tests passed.**
 *
 * The reason is that `selector` names the CLIPPING ANCESTOR, not the culprit.
 * `.runs-section`, `.runs-list` and `.record-view-panel` are all `overflow-x:
 * visible`, so `findOverflowingRegions` skips them and the chain terminates at
 * `main#main.screen-main.pad` or `div.screen-card` — neither of which contains the
 * substring "run". That is not an edge case: it is the NORMAL termination for "the
 * card is too wide for its container", as opposed to "content is too wide for the
 * card", which is the only sub-class the substring filter ever caught.
 *
 * So membership is decided by containment, evaluated in the page against the same
 * selector strings the report carries — and the offender counts if EITHER it or its
 * culprit is inside the runs section, because the culprit is the thing to fix.
 */
async function belongsToRuns(page: Page, selectors: string[]): Promise<boolean[]> {
  return page.evaluate(
    ({ root, sels }) => {
      const runs = document.querySelector(root);
      if (!runs) return sels.map(() => false);
      // `describe()` renders "a.b < c.d < e.f" innermost-first; the leading term is
      // the element itself, and matching any run-scoped node with that exact class
      // signature is what containment means here.
      const inside = (rendered: string): boolean => {
        const leaf = rendered.split('<')[0].trim();
        if (!leaf) return false;
        try {
          return Array.from(document.querySelectorAll(leaf)).some((el) => runs.contains(el));
        } catch {
          return false; // an unparseable signature is not evidence of membership
        }
      };
      return sels.map(inside);
    },
    { root: RUNS_ROOT, sels: selectors }
  );
}

async function keepRunScoped<T extends { selector: string; culprit?: string | null }>(
  page: Page,
  items: T[]
): Promise<T[]> {
  if (!items.length) return [];
  const own = await belongsToRuns(page, items.map((i) => i.selector));
  const culprits = await belongsToRuns(page, items.map((i) => i.culprit ?? ''));
  return items.filter((_, i) => own[i] || culprits[i]);
}

/**
 * EVERY RUN CARD FITS ITS CONTAINER — the assertion the four probes cannot make.
 *
 * `main#main.screen-main.pad` is `overflow-x: auto`, so it ABSORBS a card wider than
 * the page: nothing clips, no text is lost, no control is obscured, and even the
 * document's own `scrollWidth` stays at the viewport width. Measured — a 400px card
 * at a 320px viewport produced exactly zero findings from the other four probes.
 *
 * A sideways-scrolling main content region is the defect, not the mitigation (see
 * `findObscuredControls`' docstring, which refuses to scroll horizontally to reveal
 * a control for the same reason). So this is measured directly, per card, against
 * the list's own content box.
 */
async function cardsTooWide(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const list = document.querySelector('div.runs-list');
    if (!list) return ['div.runs-list is not present, so no card could be measured'];
    const box = list.getBoundingClientRect();
    const style = getComputedStyle(list);
    const right = box.right - parseFloat(style.paddingRight || '0');
    const out: string[] = [];
    document.querySelectorAll('article.run-card').forEach((card, i) => {
      const rect = card.getBoundingClientRect();
      // 1px of tolerance: sub-pixel layout rounding, not a real overhang.
      if (rect.right > right + 1) {
        out.push(
          `run card ${i + 1} extends to ${Math.round(rect.right)} past its list's content ` +
            `edge at ${Math.round(right)} (card width ${Math.round(rect.width)})`
        );
      }
      if (card.scrollWidth > card.clientWidth + 1) {
        out.push(
          `run card ${i + 1} scrolls or clips its own content: scrollWidth ` +
            `${card.scrollWidth} vs clientWidth ${card.clientWidth}`
        );
      }
    });
    return out;
  });
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
  /*
   * THE ALLOWANCE ARGUMENTS WERE `[]`, WHICH IS NOT "NO EXEMPTIONS NEEDED" — it is
   * "override the repo's own allowlist with an empty one". That was harmless only for
   * as long as the runs subtree contained no visually-hidden text, and it stopped
   * being harmless the moment the inherited panel's override controls carried an
   * `.sr-only` address in their accessible names: every one of them was reported as
   * `scrollWidth 239 vs clientWidth 1` and as `[total-loss] … 1px visible of 239px`,
   * at all six widths and at 200% zoom, drowning any real finding.
   *
   * That is the clip-rect pattern WORKING, not failing. `.sr-only` is the app-wide
   * visually-hidden utility (`styles/base.css`, a 1px box with `clip: rect(0,0,0,0)`),
   * and `layout-allowlist.ts` already carries `ALLOW-SR-ONLY` for `ANY_SURFACE` with
   * its own evidence line — `overflowMatchersFor`'s docstring records that these
   * carriers once produced 84 of 98 overflow findings across seven widths. The
   * read-only width sweep and the statistics probe both exclude them and both
   * SELF-CHECK the exclusion.
   *
   * So this is not a new exemption and not a loosening: it is this file adopting the
   * allowlist every other scanner in the repository already uses, named by the same
   * ids. `'record-detail'` is the surface these runs live on, so any surface-scoped
   * entry is resolved against the right surface rather than being granted globally.
   * The self-check below proves the exclusion did not swallow the probe.
   */
  const overflow = await findOverflowingRegions(page, overflowMatchersFor('record-detail'));
  const runsOverflow = await keepRunScoped(page, overflow.offenders);

  const clipped = (
    await findClippedText(page, RUNS_ROOT, hiddenTextMatchersFor('record-detail'))
  ).filter((o) => o.text.trim() !== '');

  await scrollToTop(page);
  const obscuredTop = await findObscuredControls(page);
  await scrollToBottom(page);
  const obscuredBottom = await findObscuredControls(page);
  await scrollToTop(page);
  const seen = new Set<string>();
  const deduped = [...obscuredTop, ...obscuredBottom].filter((o) => {
    const key = `${o.selector}::${o.detail}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const obscured = await keepRunScoped(page, deduped);

  const tooWide = await cardsTooWide(page);

  return {
    overflow: runsOverflow.length ? renderOverflow(runsOverflow) : '',
    clipped: clipped.length ? render(clipped) : '',
    obscured: obscured.length ? render(obscured) : '',
    tooWide: tooWide.length ? tooWide.map((line) => `  - ${line}`).join('\n') : '',
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
    test(`@runs-layout run card at ${width}: nothing overflows, clips, or is obscured`, async ({
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
        findings.tooWide && `A RUN CARD DOES NOT FIT ITS CONTAINER:\n${findings.tooWide}`,
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
    test(`@runs-layout the save-status chip does not collide at ${width}`, async ({ page }) => {
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
        findings.tooWide && `A RUN CARD DOES NOT FIT ITS CONTAINER:\n${findings.tooWide}`,
      ].filter(Boolean);

      expect(failures.join('\n\n'), `save-status chip at ${width}px`).toBe('');
    });
  }

  /**
   * A COLLAPSED CARD CARRYING EVERY VALUE — the case the sweep above cannot reach.
   *
   * Every measurement in this file so far runs with both cards EXPANDED, so the
   * `.run-card-conditions` line — mono, tabular, on the collapsed header, joined with
   * ` · ` — has never been measured. It is the one element on this surface whose length
   * grows with the field set: widening the workspace from three writable fields to five
   * makes that line up to two segments longer, on the narrowest header in the product.
   *
   * The values are entered through the UI, not the API, because the line is built from
   * what the card holds and a fixture write would prove less. They are typed into ONE
   * card, which is then collapsed — two collapsed cards would only repeat the
   * measurement at the same width.
   */
  test('@runs-layout a collapsed card carrying every value still fits at 320', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 812 });
    await twoOpenRuns(page);

    const first = runCards(page).first();
    const type = async (path: string, value: string) => {
      const box = first.locator(
        `.run-field:has(.run-field-path:text-is("${path}")) input, ` +
          `.run-field:has(.run-field-path:text-is("${path}")) select`,
      );
      await pwExpect(box).toBeVisible();
      const tag = await box.evaluate((el) => el.tagName);
      if (tag === 'SELECT') await box.selectOption(value);
      else await box.fill(value);
    };

    // Every writable path, with the longest plausible values a scientist would enter.
    await type('context.environment', 'operando');
    await type('context.temperature_K', '1273.15');
    await type('context.thermodynamics.atmosphere', '5% H2 in Ar, 1.2 bar');
    await type('timestamps.acquired_start_utc', '2026-01-31T09:00:00Z');
    await type('timestamps.acquired_end_utc', '2026-01-31T17:45:00Z');

    // Let the debounced saves settle, then collapse so the conditions line renders.
    await pwExpect(first.locator('.run-save-status')).toContainText(/Saved/, { timeout: 20_000 });
    await first.locator('button.run-card-header').click();
    await pwExpect(first.locator('.run-card-body')).toHaveCount(0);

    const conditions = first.locator('.run-card-conditions');
    await pwExpect(conditions).toBeVisible();
    // Asserted, not assumed: a line that rendered none of the values would pass every
    // geometric check below while proving nothing.
    await pwExpect(conditions).toContainText('operando');
    await pwExpect(conditions).toContainText('5% H2 in Ar');

    const findings = await probeRuns(page);
    await page.screenshot({ path: `${SHOT_DIR}/run-card-collapsed-full-320.png`, fullPage: true });

    const failures = [
      findings.overflow && `OVERFLOW on a full collapsed card:\n${findings.overflow}`,
      findings.clipped && `TEXT LOST on a full collapsed card:\n${findings.clipped}`,
      findings.obscured && `CONTROLS OBSCURED on a full collapsed card:\n${findings.obscured}`,
      findings.tooWide && `A RUN CARD DOES NOT FIT ITS CONTAINER:\n${findings.tooWide}`,
    ].filter(Boolean);

    expect(failures.join('\n\n'), 'collapsed card with every value at 320px').toBe('');
  });

  /**
   * THE DIFFERENTIAL DOCUMENT CHECK — the claim this slice owns.
   *
   * Absolute document overflow on this screen is pre-existing and recorded in
   * `layout-baseline.ts`; see the file header. What must hold is that the run
   * cards add nothing to it. Measured at 320, the width where a pixel costs most.
   */
  test('@runs-layout run cards widen the document by nothing at 320', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 812 });

    await openRecord(page, SEED.partial, 'runs');
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

    // AND THE ABSOLUTE FORM, which the header's first version wrongly excused. It
    // holds today at every width this file measures; a differential alone would
    // tolerate slack if the shell ever regressed above the viewport width.
    expect(
      after.docScrollWidth,
      `the document scrolls sideways at 320px: scrollWidth ${after.docScrollWidth} vs ` +
        `clientWidth ${after.docClientWidth}. This is the WCAG 1.4.10 reflow width.`
    ).toBeLessThanOrEqual(after.docClientWidth);
  });

  /**
   * THE OVERRIDE FORM AT THE TWO NARROWEST WIDTHS — the densest state this card has.
   *
   * The sweep above measures the inherited panel AT REST: a path, a value, a
   * provenance label and one or two buttons per row. Opening an override adds a
   * label, a context sentence, a text input, a checkbox with a full sentence beside
   * it, two buttons and a note — inside a row that already carries a 40-character
   * official path. None of that existed when the widths above were last measured, and
   * "the resting state fits" is not evidence about the open one.
   *
   * 390 and 320 only: those are the widths where a pixel costs something (320 is the
   * WCAG 1.4.10 reflow width). The wider projects are covered by the sweep, and the
   * form adds no wide-screen treatment of its own.
   */
  for (const width of [390, 320] as const) {
    test(`@runs-layout the override form fits at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 812 });
      await twoOpenRuns(page);

      const row = runCards(page)
        .first()
        .locator('[data-address="field:sample.composition.CuO2_mass_fraction"]');
      // The LONGEST overridable path the canonical record carries — measured against
      // the seed, not assumed, so this is the worst case rather than a typical one.
      await pwExpect(row).toBeVisible();
      await row.getByRole('button', { name: /Override for this run/ }).click();
      await pwExpect(row.getByRole('textbox')).toBeVisible();
      await row.getByRole('textbox').fill('0.4815162342');
      await pwExpect(row.getByRole('checkbox')).toBeVisible();

      const findings = await probeRuns(page);
      await page.screenshot({
        path: `${SHOT_DIR}/run-card-override-form-${width}.png`,
        fullPage: true,
      });

      const failures = [
        findings.overflow && `OVERFLOW with the override form open:\n${findings.overflow}`,
        findings.clipped && `TEXT LOST with the override form open:\n${findings.clipped}`,
        findings.obscured && `CONTROLS OBSCURED with the override form open:\n${findings.obscured}`,
        findings.tooWide && `A RUN CARD DOES NOT FIT ITS CONTAINER:\n${findings.tooWide}`,
      ].filter(Boolean);
      expect(failures.join('\n\n'), `override form at ${width}px`).toBe('');

      // The controls are not merely present: both are reachable and operable at this
      // width, which is what a geometric probe cannot say on its own.
      await pwExpect(row.getByRole('button', { name: 'Record override' })).toBeDisabled();
      await row.getByRole('checkbox').check();
      await pwExpect(row.getByRole('button', { name: 'Record override' })).toBeEnabled();
      await pwExpect(row.getByRole('button', { name: 'Cancel' })).toBeVisible();
    });
  }

  /**
   * THE PROBE'S OWN SELF-CHECK — added with the `.sr-only` allowance, because an
   * exemption nobody re-verifies is indistinguishable from a probe that stopped
   * working.
   *
   * `probeRuns` now passes `layout-allowlist.ts`'s app-wide matchers instead of `[]`,
   * which is what stops the inherited panel's visually-hidden address carriers being
   * reported as 239px of lost text at every width. This test proves the exemption is
   * NARROW: a genuinely clipped element planted in the same subtree, with the same
   * geometry but WITHOUT the `.sr-only` class, is still caught — and the `.sr-only`
   * one still is not.
   *
   * Both are planted in the page and removed again; neither reaches the product.
   */
  test('@runs-layout the clipped-text probe still catches a real clip, and still ignores .sr-only', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 812 });
    await twoOpenRuns(page);

    // Clean to start with — otherwise the assertions below prove nothing.
    expect((await probeRuns(page)).clipped, 'the surface must be clean before planting').toBe('');

    const plant = async (className: string) =>
      page.evaluate(
        ({ root, cls }) => {
          const host = document.querySelector(root);
          if (!host) throw new Error(`${root} is not present`);
          const el = document.createElement('span');
          el.id = 'selfcheck-run-clip';
          if (cls) el.className = cls;
          el.textContent =
            'A sentence far longer than one pixel, planted to prove the probe is awake.';
          // The clip-rect geometry, applied by HAND so the two cases differ ONLY in
          // whether the app's own visually-hidden class is present.
          el.style.cssText =
            'display:inline-block;width:1px;height:1px;overflow:hidden;white-space:nowrap;';
          host.appendChild(el);
        },
        { root: RUNS_ROOT, cls: className }
      );
    const unplant = () =>
      page.evaluate(() => document.getElementById('selfcheck-run-clip')?.remove());

    await plant('');
    const caught = await probeRuns(page);
    await unplant();
    expect(caught.clipped, 'a real clipped element must still be reported').toContain(
      'selfcheck-run-clip'
    );

    await plant('sr-only');
    const ignored = await probeRuns(page);
    await unplant();
    expect(ignored.clipped, 'the .sr-only clip-rect pattern must never be reported').not.toContain(
      'selfcheck-run-clip'
    );
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
base('@runs-layout run card at 200% zoom (640x400 @ DPR2) stays usable', async ({ browser }) => {
  const context: BrowserContext = await browser.newContext({
    viewport: { width: 640, height: 400 },
    deviceScaleFactor: 2,
    baseURL: MUT_BASE_URL,
  });
  /*
   * THE `try` OPENS HERE, BEFORE ANYTHING THAT CAN THROW, and it did not in the first
   * version of this file. The session was opened and two `pwExpect`s were evaluated
   * ABOVE the `try`, so a non-201 — or a body without a `session_id` — threw with the
   * context unclosed and the session undisposed, while this file's header claimed
   * both were disposed in a `finally`. A reviewer found the claim and the code
   * disagreeing.
   *
   * `sessionId` is therefore declared out here and cleaned up conditionally: the
   * failure that leaves it unset is exactly the failure that must still close the
   * context.
   */
  const page = await context.newPage();
  let sessionId: string | undefined;

  try {
    const opened = await context.request.post(`${MUT_API_BASE}/tutorial/sessions`);
    pwExpect(
      opened.status(),
      `could not open a worked-example session for the zoom case: ${await opened.text()}`
    ).toBe(201);
    sessionId = ((await opened.json()) as { session_id?: string }).session_id;
    pwExpect(typeof sessionId === 'string' && sessionId !== '').toBeTruthy();

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
      findings.tooWide && `A RUN CARD DOES NOT FIT ITS CONTAINER:\n${findings.tooWide}`,
    ].filter(Boolean);

    pwExpect(failures.join('\n\n'), 'run card at 200% zoom').toBe('');

    await assertOperable(page);
  } finally {
    // Idempotent and swallowed, matching the `session` fixture: cleanup must never
    // turn a passing test red. Guarded on `sessionId` because the failure that
    // leaves it unset is precisely the one that must still close the context.
    if (sessionId) {
      await disposeWorkedExampleSession(sessionId, MUT_API_BASE).catch(() => undefined);
    }
    await context.close();
  }
});

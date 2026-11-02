/**
 * The Statistics visualization system, in a real browser.
 * @responsive
 *
 * ── Why this cannot be a jsdom test ────────────────────────────────────────
 *
 * Every chart on the Statistics surface measures its own plot column — a direct
 * `getBoundingClientRect()` read at mount, plus a `ResizeObserver` for later
 * changes — and renders SVG at 1:1 pixel scale. jsdom has neither layout (its
 * `getBoundingClientRect` returns 0, which the hook ignores) nor
 * `ResizeObserver`, so the vitest suite necessarily renders at the hook's
 * documented fallback width and can prove nothing about real geometry.
 * Four things are therefore only checkable here, and all four are the ones that
 * actually break:
 *
 *   1. the plot really fills the width it was given, at every viewport;
 *   2. no chart forces two-dimensional scrolling — the page never scrolls
 *      sideways, and a wide block scrolls INSIDE its own container;
 *   3. the axis band is inside the chart's box, so no card grows a tiny nested
 *      vertical scroll around clipped tick labels;
 *   4. the text equivalents survive at 375px and at 200% zoom, where a naive
 *      implementation drops the table or clips the summary.
 *
 * Both Statistics scopes are covered. The ORDINARY workspace is permanently
 * empty, so it draws no chart at all — which is itself an assertion worth making
 * (an empty workspace must not draw an empty axis). The populated charts exist
 * only inside a worked-example session.
 */

import { expect, test } from '../fixtures';
import { SURFACES } from '../surfaces';

/* `STATISTICS_EXAMPLE` REMOVED, 2026-09-15, not silenced: the five tests that
   referenced it now open the BUILD tab, where the charts live. The
   `statistics-example` surface itself still exists and is still scanned by axe —
   it is only this spec that no longer addresses it. */
const STATISTICS_BUILD = SURFACES.find((s) => s.id === 'statistics-build')!;
/* The worked-example OVERVIEW tab — named for the tab, because this spec now
   addresses two different Statistics tabs and `STATISTICS_EXAMPLE` alone no
   longer says which. */
const STATISTICS_EXAMPLE_OVERVIEW = SURFACES.find((s) => s.id === 'statistics-example')!;
const STATISTICS_ORDINARY = SURFACES.find((s) => s.id === 'statistics')!;

/**
 * Open the Technical Details disclosure, which holds two of the four charts, and
 * ASSERT THAT EVERY CHART PLOT IS ON ITS MEASURED WIDTH.
 *
 * ── What the poll is, and what it is NOT ────────────────────────────────────
 *
 * It is not a race-guard. This docstring used to say those two charts mount
 * "inside `display: none`, where `ResizeObserver` reports a content width of 0",
 * and that "on open, the observer fires again with the real width and React
 * re-renders one frame later". All three claims are false, they contradict
 * `StatsCharts.tsx:132-160` — which was right — in the same commit, and a
 * maintainer who trusted them would delete the line that makes these charts work.
 *
 * MEASURED in this suite's own headless Chromium, disclosure CLOSED: the plot
 * computes `display: flex` and `content-visibility: visible`, its
 * `getBoundingClientRect().width` is 918, and the SVG already carries
 * `width="918"` BEFORE any click. Nothing is racing. (What is `content-visibility:
 * hidden` is the UA's `::details-content` pseudo-element, measured on the
 * `<details>` itself — which is why the subtree is skipped by `ResizeObserver`
 * while still having a layout box.)
 *
 * So the poll is an ASSERTION: it says every plot's SVG width equals its column,
 * which is only true because `useChartWidth` reads the box SYNCHRONOUSLY in its
 * ref callback. Negative control, re-measured: delete
 * `apply(node.getBoundingClientRect().width)` and this poll never settles — both
 * SVGs sit at the 560px fallback while their columns measure 918. Across all five
 * viewport projects, 25 of this file's 45 runs fail, i.e. 5 of its 9 tests per
 * project, and the five are exactly the worked-example tests — the only ones that
 * call this function. The four that pass draw no chart (the empty-workspace test
 * and the three My Stats tests).
 *
 * NOT LOAD-DEPENDENT, and this paragraph used to say it was. It read "an isolated
 * single-project run failed 3 of 8, so WHICH of the eight fail is load-dependent".
 * Re-measured three times in isolation — `--project=desktop-1280x800`, twice at
 * the default worker count and once at `--workers=1` — the result is 5 failed /
 * 4 passed every time, the same five. The 3 was a single reading whose conditions
 * were never identified, and the inference drawn from it is withdrawn.
 *
 * WHY THE HOOK'S OBSERVER DOES NOT DELIVER AFTER OPEN IS NOT ISOLATED, and this
 * paragraph used to assert a cause it does not have. It said "The observer alone
 * never delivers, not even 1.5s after the region is opened", chaining that to the
 * skipped-subtree rule stated above. The rule explains the CLOSED state only.
 * Measured on the same node in the same session: a separately hand-installed
 * `ResizeObserver` on that `.stats-chart-plot`, while the `<details>` was still
 * closed, reported `[]` for 1.5s and then DID deliver `[918]` on open. So an
 * observer on that element can receive a post-open observation. The hook's does
 * not, the effect reproduces, and the mechanism is recorded as unidentified —
 * see `StatsCharts.tsx`, "THE POST-OPEN FAILURE IS OBSERVED AND ITS MECHANISM IS
 * NOT ISOLATED".
 *
 * It is spelled as a poll rather than a bare assertion only so that a genuine
 * future re-render (a breakpoint reflow) is tolerated rather than turned into a
 * flake. The value it converges on is fixed at mount.
 */
/*
 * ── 2026-10-12: THERE IS NO `Technical Details` REGION TO OPEN ANY MORE ──────
 *
 * The widget redesign made each build fact a visible widget and put each widget's
 * breakdowns behind its own VIEW tabs (`components/Widget.tsx`), so a chart now
 * sits either in the selected view or in a hidden, still-mounted one. This
 * function therefore REVEALS every widget view for the per-figure battery below —
 * the same test-only state `e2e/helpers/disclosures.ts`'s `openWidgetInfoAndViews`
 * uses for the axe sweep, with the same caveat: all views stacked is a state the
 * product never shows, but each panel's content is exactly what one press of its
 * tab reaches. The REAL interaction is pinned separately, by
 * `a chart in an inactive view is measured when its tab is pressed`, which clicks
 * a tab and asserts the newly shown chart takes its column's width.
 *
 * The poll below is unchanged in meaning: every plot's SVG width equals its
 * column. It used to rely on the synchronous read alone; since 2026-10-12 the
 * hook's ResizeObserver also works under StrictMode (see `StatsCharts.tsx`, "THE
 * POST-OPEN FAILURE, IDENTIFIED"), which is what lets a chart mounted while
 * hidden reach its width once revealed.
 */
async function openTechnicalDetails(page: import('@playwright/test').Page): Promise<void> {
  await page.evaluate(() => {
    for (const panel of document.querySelectorAll('.widget-view-panel[hidden]')) {
      panel.removeAttribute('hidden');
    }
  });
  await expect(page.locator('.widget-view-panel[hidden]')).toHaveCount(0);
  await expect
    .poll(
      () =>
        page.evaluate(() =>
          Array.from(document.querySelectorAll('figure.stats-chart')).filter((figure) => {
            const plot = figure.querySelector('.stats-chart-plot') as HTMLElement | null;
            const svg = figure.querySelector('svg') as SVGSVGElement | null;
            if (!plot || !svg) return false;
            return (
              Math.abs(Number(svg.getAttribute('width')) - plot.getBoundingClientRect().width) > 1
            );
          }).length,
        ),
      { message: 'every chart plot must settle on its measured width' },
    )
    .toBe(0);
}

/**
 * The precondition for the FIFTH figure, asserted where the figure is counted.
 *
 * ── Why a number here was a race, and what fixes it ─────────────────────────
 *
 * Record Verification draws `Official Validation and the Format Shadow, Side by
 * Side` only once `GET /api/runtime/verification` answers `ok`. That sweep runs
 * on a background thread and takes ~15s from the first request
 * (`apps/api/isaac_api/routes.py`; `verification.VerificationState`), so a page
 * opened inside that window renders FOUR figures and one "not ready" panel, and
 * the same page opened afterwards renders FIVE. CI on `17cff95` measured exactly
 * that: 4 at `desktop-1280x800`, which runs first, and 5 at the four later
 * projects. The count was never wrong; it was a clock.
 *
 * `e2e/global-setup.ts` step 5 settles the report before any project starts, so
 * the state is fixed for the whole run. This function does not repeat that work
 * — it ASSERTS the precondition holds at the moment the figures are counted, so
 * that a regression to the unsettled page fails by naming the section that is
 * missing rather than by reporting a chart count nobody can explain.
 *
 * It waits on the SECTION rather than on the network: what the count depends on
 * is what was rendered, and a settled response the component has not yet drawn
 * would satisfy a request-level wait while the figure was still absent.
 */
async function settledVerificationSection(page: import('@playwright/test').Page): Promise<void> {
  /* ~~the `Official Validation and the Format Shadow, Side by Side` heading~~ —
     that `h3` was retired 2026-10-18 when the comparison became two compact
     rows under the widget's own `Validators` tab. The section is settled when
     both validator rows are drawn, which is the same fact the heading stood for. */
  await expect(
    page
      .getByRole('region', { name: 'Record Verification' })
      .locator('.stats-verify-chartgroup')
      .first(),
    'Record Verification must have a settled report before its figure is counted — see ' +
      'e2e/global-setup.ts step 5',
  ).toBeVisible({ timeout: 20_000 });
  await expect(
    page.getByRole('region', { name: 'Record Verification' }).locator('.stats-verify-chartgroup'),
  ).toHaveCount(2);
}

/**
 * The `Build & Verification` tab — where the charts now live.
 *
 * *** FOUR OF THE FIVE CHARTS MOVED, 2026-09-15. *** The Statistics redesign put
 * the engineering content on its own tab so a scientist does not land on it.
 * Measured in Chrome on a populated workspace:
 *
 *              figure.stats-chart   details.stats-technical   Record Verification
 *   Overview            1                     0                      no
 *   ?tab=build          4                     1                     yes
 *
 * So these tests were opening a tab that no longer holds what they assert about,
 * and `openTechnicalDetails` was waiting on a `details.stats-technical` that is
 * not there — which is how they failed in CI.
 *
 * THE ORDINARY SCOPE, NOT THE WORKED EXAMPLE, and that is a correction to my own
 * first attempt. I sent these at the worked-example build tab and three still
 * failed, every one reporting ZERO charts. The reason is what these four charts
 * ARE: they are VERIFICATION-derived, not record-derived, and `global-setup`
 * settles a verification report for the ORDINARY scope (its own log line:
 * "verification report settled to ok"). A worked-example session has no such
 * report, so the tab renders no plot there. Record-derived charts are the
 * separate concern `STATISTICS_ORDINARY`'s "draws no RECORD-derived chart" test
 * already pins.
 *
 * Using the catalogued surface also means no new baseline cells: `statistics-build`
 * was added to `e2e/surfaces.ts` in this same change for axe, in this same scope.
 */
test.describe('@responsive Statistics charts (worked example)', () => {
  test('every chart carries BOTH text equivalents, at this viewport', async ({ page, app }) => {
    await app.open(STATISTICS_BUILD);
    await settledVerificationSection(page);
    await openTechnicalDetails(page);

    const figures = page.locator('figure.stats-chart');
    const count = await figures.count();

    /*
     * THE SET OF CHARTS, NOT THE NUMBER OF THEM.
     *
     * This used to assert `count === 4`. A count cannot tell "one chart was
     * removed and another added" from "nothing changed", and it says nothing
     * about WHICH figures the loop below then walks — so a renamed or replaced
     * chart would keep passing. The captions are compared as a sorted set
     * instead, which pins identity and cardinality at once.
     *
     * The workflow caption carries the record count, so digits are masked: this
     * spec is about which charts exist, and the figures themselves are pinned by
     * `statistics-page.test.tsx` against a fixture it states by hand.
     *
     * SIX captions, not five. Two slices each added one figure to a four-figure
     * page and each therefore measured five: the schema breakdown inside
     * Technical Details, and Record Verification's side-by-side validators
     * (whose precondition `settledVerificationSection` asserts above). They sit
     * in different sections and compose, so the merged page draws six. Record
     * Verification's two `IssueDistribution` charts are deliberately NOT here:
     * on a report with no format issues they render `ChartEmpty`, which is not a
     * `figure.stats-chart` — which is why the verification slice counted one new
     * figure and not three.
     */
    const captions = await figures.locator('figcaption').allInnerTexts();
    /*
     * *** FOUR, NOT SIX — the set SPLIT BY KIND when the charts moved tabs, and
     * the two that left are covered by their own test below rather than dropped. ***
     *
     * ~~'Records by current workflow step, out of <n> counted'~~
     * ~~'Share of classified fields by evidence-support class'~~
     *
     * Those two are RECORD-derived, so they render only where records exist —
     * the worked-example Overview. The four that remain are derived from the
     * schema, the API contract and the validators, which this tab reads
     * regardless of how many records a workspace holds. Measured from this
     * test's own failure output rather than guessed.
     *
     * Deleting the two from this list WITHOUT the sibling test would have been
     * the same coverage loss `openUnreachableDisclosures` caught on the prose
     * disclosures one commit earlier: an assertion made green by narrowing what
     * it looks at.
     */
    expect(captions.map((c) => c.trim().replace(/\d+/g, '<n>')).sort()).toEqual(
      [
        "Fields by top-level section, in the schema's own declaration order",
        'Documented operations by HTTP method',
        "Documented operations by group, in the contract's own tag order",
        'Records passing and not passing, by validator',
      ].sort(),
    );
    /* EVERY FIGURE HAS EXACTLY ONE CAPTION — which is the property this comparison
       actually holds. "Every caption belongs to a figure" was trivially true given
       the locator chain above: `figures.locator('figcaption')` can only ever return
       captions that are already inside a `figure.stats-chart`. What the equality
       rules out is a figure with none and a figure with two. */
    expect(count, 'every figure must have exactly one caption').toBe(captions.length);

    for (let i = 0; i < count; i++) {
      const figure = figures.nth(i);
      const caption = (await figure.locator('figcaption').first().innerText()).trim();

      // 1 · the summary sentence: a real element, present without any interaction,
      // and NOT inside the data-table disclosure (a closed `<details>` is hidden
      // from assistive technology, so the sentence would vanish with it).
      const summary = figure.locator('p.sr-only').first();
      await expect(summary, `${caption}: summary sentence`).toHaveCount(1);
      const summaryText = (await summary.textContent())?.trim() ?? '';
      expect(summaryText.length, `${caption}: summary must not be empty`).toBeGreaterThan(10);
      /*
       * Not inside the chart's OWN data-table disclosure. Scoped to that
       * disclosure rather than to any `<details>`, because two of these charts
       * legitimately live inside the collapsed Technical Details region — and that
       * hides the whole region, chart and text together, which is the reader's own
       * choice. What must never happen is the PICTURE being available while its
       * text equivalent sits behind a second, separate disclosure.
       */
      expect(
        await summary
          .locator('xpath=ancestor::details[contains(@class,"stats-chart-table-wrap")]')
          .count(),
        `${caption}: the summary must not be inside the data-table disclosure`,
      ).toBe(0);

      // 2 · the data table, reachable in one interaction and with real rows.
      const toggle = figure.locator('summary.stats-chart-table-toggle');
      await expect(toggle, `${caption}: data-table toggle`).toBeVisible();
      await toggle.click();
      const rows = figure.locator('table.stats-chart-table tbody tr');
      expect(await rows.count(), `${caption}: table rows`).toBeGreaterThan(0);
      await expect(figure.locator('table.stats-chart-table thead th').first()).toBeVisible();
    }
  });

  test('a chart in an inactive view is measured when its tab is pressed', async ({ page, app }) => {
    await app.open(STATISTICS_BUILD);
    const api = page.getByRole('region', { name: 'API Surface' });
    await api.getByRole('tab', { name: 'By Group' }).click();
    const panel = api.getByRole('tabpanel', { name: 'By Group' });
    await expect(panel).toBeVisible();
    await expect
      .poll(
        () =>
          panel.evaluate((el) => {
            const plot = el.querySelector('.stats-chart-plot') as HTMLElement | null;
            const svg = el.querySelector('svg.stats-chart-track') as SVGSVGElement | null;
            if (!plot || !svg) return Number.NaN;
            return Math.abs(Number(svg.getAttribute('width')) - plot.getBoundingClientRect().width);
          }),
        { message: 'the chart in a newly shown view must take its column\'s width' },
      )
      .toBeLessThanOrEqual(1);
  });

  test('the drawn SVG claims nothing — the text is authoritative', async ({ page, app }) => {
    await app.open(STATISTICS_BUILD);
    await openTechnicalDetails(page);

    const svgs = page.locator('figure.stats-chart svg');
    const count = await svgs.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      await expect(svgs.nth(i)).toHaveAttribute('aria-hidden', 'true');
      await expect(svgs.nth(i)).toHaveAttribute('focusable', 'false');
    }
  });

  test('each plot is measured, fills its column, and includes its axis band', async ({
    page,
    app,
  }) => {
    await app.open(STATISTICS_BUILD);
    await openTechnicalDetails(page);

    const measurements = await page.evaluate(() => {
      const out: {
        caption: string;
        plotWidth: number;
        svgWidth: number;
        viewBox: string;
        svgHeight: number;
        renderedHeight: number;
      }[] = [];
      for (const figure of document.querySelectorAll('figure.stats-chart')) {
        const plot = figure.querySelector('.stats-chart-plot') as HTMLElement | null;
        const svg = figure.querySelector('svg') as SVGSVGElement | null;
        if (!plot || !svg) continue;
        out.push({
          caption: (figure.querySelector('figcaption')?.textContent ?? '').trim().slice(0, 40),
          plotWidth: Math.round(plot.getBoundingClientRect().width),
          svgWidth: Number(svg.getAttribute('width')),
          viewBox: svg.getAttribute('viewBox') ?? '',
          svgHeight: Number(svg.getAttribute('height')),
          renderedHeight: Math.round(svg.getBoundingClientRect().height),
        });
      }
      return out;
    });

    expect(measurements.length).toBeGreaterThan(0);
    for (const m of measurements) {
      // MEASURED, not the fallback: the SVG width tracks the plot column to
      // within a pixel of rounding.
      expect(Math.abs(m.svgWidth - m.plotWidth), `${m.caption}: svg width vs plot`).toBeLessThanOrEqual(1);
      // 1:1 coordinates — the viewBox equals the rendered box, so `<text>` is
      // never scaled down and a hairline is one pixel.
      expect(m.viewBox, `${m.caption}: viewBox`).toBe(`0 0 ${m.svgWidth} ${m.svgHeight}`);
      // The declared height is the height actually taken, so the axis band is
      // inside the box rather than clipped by it.
      expect(Math.abs(m.renderedHeight - m.svgHeight), `${m.caption}: height`).toBeLessThanOrEqual(1);
    }
  });

  test('no chart forces two-dimensional scrolling', async ({ page, app }) => {
    await app.open(STATISTICS_BUILD);
    await openTechnicalDetails(page);
    // Open every data table too: a wide table is the most likely thing to widen
    // the page, so the check is made in the state where it could.
    const toggles = page.locator('summary.stats-chart-table-toggle');
    for (let i = 0; i < (await toggles.count()); i++) await toggles.nth(i).click();

    const overflow = await page.evaluate(() => ({
      docScroll: document.documentElement.scrollWidth,
      docClient: document.documentElement.clientWidth,
      bodyScroll: document.body.scrollWidth,
      // Any chart element whose own box is wider than the plot column it sits in
      // AND that is not inside a declared scroll container.
      escapees: Array.from(document.querySelectorAll('figure.stats-chart *'))
        .filter((el) => {
          const box = el.getBoundingClientRect();
          if (box.width === 0) return false;
          const plot = el.closest('figure.stats-chart') as HTMLElement | null;
          if (!plot) return false;
          if (el.closest('.stats-scroll')) return false; // scrolls inside itself, by design
          return box.right > plot.getBoundingClientRect().right + 1;
        })
        .map((el) => `${el.tagName.toLowerCase()}.${el.className}`),
    }));

    expect(overflow.docScroll, 'the page must not scroll sideways').toBeLessThanOrEqual(
      overflow.docClient,
    );
    expect(overflow.bodyScroll).toBeLessThanOrEqual(overflow.docClient);
    expect(overflow.escapees, 'chart content must stay inside its figure or its own scroller').toEqual([]);
  });

  test('the wide block scrolls inside its own container, not the page', async ({ page, app }) => {
    await app.open(STATISTICS_BUILD);
    await openTechnicalDetails(page);
    await page.locator('summary.stats-chart-table-toggle').first().click();

    // Every data table is wrapped in the surface's declared scroll container, so
    // a long group name can never widen the page.
    const unwrapped = await page.evaluate(
      () =>
        Array.from(document.querySelectorAll('table.stats-chart-table')).filter(
          (t) => t.closest('.stats-scroll') === null,
        ).length,
    );
    expect(unwrapped, 'every chart table must sit in a .stats-scroll container').toBe(0);
  });
});

test.describe('@responsive Statistics charts · the record-derived pair', () => {
  /*
   * *** THE TWO CHARTS THE BUILD-TAB SET NO LONGER NAMES, covered here so that
   * narrowing that set did not narrow the suite. ***
   *
   * `Records by current workflow step` and `Share of classified fields by
   * evidence-support class` are RECORD-derived: they render where records exist,
   * which is the worked-example Overview, not the ordinary build tab where the
   * schema/contract/validator charts live.
   *
   * This asserts the property that matters and that the moved set used to
   * guarantee for all six — every figure carries a caption and a non-empty
   * `p.sr-only` summary, outside its own data-table disclosure, so the text
   * equivalent survives with the `<details>` shut. It deliberately does NOT
   * re-run the whole per-figure battery above: that block's remaining
   * assertions are about axis bands and measured plot widths, which are
   * properties of the chart component rather than of these two instances, and
   * duplicating 100 lines to re-prove them would make both copies harder to
   * trust than one.
   */
  test('each carries a caption and a non-empty summary, at this viewport', async ({ page, app }) => {
    await app.open(STATISTICS_EXAMPLE_OVERVIEW);

    const figures = page.locator('figure.stats-chart');
    const count = await figures.count();
    expect(count, 'the worked-example Overview must draw its record-derived charts').toBeGreaterThan(
      0,
    );

    const captions = await figures.locator('figcaption').allInnerTexts();
    expect(count, 'every figure must have exactly one caption').toBe(captions.length);

    for (let i = 0; i < count; i++) {
      const figure = figures.nth(i);
      const caption = (await figure.locator('figcaption').first().innerText()).trim();
      const summary = figure.locator('p.sr-only').first();
      await expect(summary, `${caption}: summary sentence`).toHaveCount(1);
      const text = (await summary.textContent())?.trim() ?? '';
      expect(text.length, `${caption}: summary must not be empty`).toBeGreaterThan(10);
      /* Outside the chart's own data-table disclosure — a closed `<details>` is
         hidden from assistive technology, so a summary inside it would vanish
         with it. Same reasoning as the build-tab block above. */
      await expect(
        figure.locator('details.stats-chart-table-wrap p.sr-only'),
        `${caption}: summary must not be inside the data-table disclosure`,
      ).toHaveCount(0);
    }
  });
});

test.describe('@responsive Statistics charts (empty ordinary workspace)', () => {
  /*
   * An empty workspace draws NO chart — not an empty axis, not a row of zero
   * bars, not a table of zeros. A zero-filled plot is a measurement claim, and
   * the ordinary workspace of this deployment is permanently empty, so this is
   * the state most readers see.
   */
  test('draws no RECORD-derived chart, no axis and no table', async ({ page, app }) => {
    await app.open(STATISTICS_ORDINARY);

    /*
     * Scoped to the record-derived sections, which is the honest scope. The API
     * surface DOES draw two charts here and should: they describe the build's own
     * contract, not the workspace, so they have real data in every scope. (They
     * also sit inside the collapsed Technical Details region, and a closed
     * `<details>` still holds its children in the DOM — so a page-wide
     * `toHaveCount(0)` would fail for a reason that has nothing to do with the
     * empty workspace.)
     */
    /* ~~'Workflow Distribution', 'Evidence and Validation'~~ — the widgets that
       carry those charts since 2026-10-12. */
    for (const region of ['Records', 'Evidence Support']) {
      const section = page.getByRole('region', { name: region });
      await expect(section.locator('figure.stats-chart'), region).toHaveCount(0);
      await expect(section.locator('.stats-chart-grid'), region).toHaveCount(0);
      await expect(section.locator('table.stats-chart-table'), region).toHaveCount(0);
    }
    // …and it says so in words, rather than leaving a blank card. Since
    // 2026-10-12 the distribution is a VIEW of `Records`, and with no record the
    // widget offers no view at all — so the sentence is the widget's own empty
    // state, and there is no tab leading to an empty plot.
    const records = page.getByRole('region', { name: 'Records' });
    await expect(records.getByText('No Records Yet')).toBeVisible();
    await expect(records.getByRole('tablist')).toHaveCount(0);
  });
});




/*
 * NO STATISTICS TAB SCROLLS SIDEWAYS AT 320px — review fix, 2026-10-18.
 *
 * The density round's headline figure lists (a flex item with a 16rem basis,
 * whose grid columns would not go below 150px) pushed Workspace Activity and
 * Historical Imports to x=378 in a 320px viewport — `main` scrollWidth 367
 * against clientWidth 298 — where the base had not scrolled at all. jsdom
 * computes no layout, so the CSS half is pinned in `statistics-page.test.tsx`
 * and this is the browser half: every tab, at 320px, as shipped AND with every
 * widget view revealed (a view a reader opens must not overflow either).
 *
 * `@interaction`, not `@responsive`: the viewport is set here, so running it in
 * all five projects would measure the same 320px layout five times.
 */
test.describe('@interaction Statistics never scrolls sideways at 320px', () => {
  for (const surface of [STATISTICS_EXAMPLE_OVERVIEW, STATISTICS_ORDINARY, STATISTICS_BUILD]) {
    test(`${surface.name}`, async ({ page, app }) => {
      await page.setViewportSize({ width: 320, height: 800 });
      await app.open(surface);
      const overflow = () =>
        page.evaluate(() => {
          const main = document.querySelector('main#main') as HTMLElement;
          const doc = document.documentElement;
          const mainRight = main.getBoundingClientRect().right;
          return {
            main: main.scrollWidth - main.clientWidth,
            doc: doc.scrollWidth - doc.clientWidth,
            escapees: Array.from(main.querySelectorAll('.widget *'))
              .filter((el) => {
                if (el.closest('.stats-scroll, .sr-only')) return false;
                const box = el.getBoundingClientRect();
                return box.width > 0 && box.right > mainRight + 1;
              })
              .slice(0, 5)
              .map((el) => `${el.tagName.toLowerCase()}.${String((el as HTMLElement).className)}`),
          };
        });
      const shipped = await overflow();
      expect(shipped.escapees, `${surface.name}: nothing may extend past main at 320px`).toEqual([]);
      expect(shipped.main, `${surface.name}: main must not scroll sideways`).toBeLessThanOrEqual(0);
      expect(shipped.doc, `${surface.name}: the page must not scroll sideways`).toBeLessThanOrEqual(0);

      await page.evaluate(() => {
        for (const panel of document.querySelectorAll('.widget-view-panel[hidden]')) {
          panel.removeAttribute('hidden');
        }
      });
      const revealed = await overflow();
      expect(revealed.escapees, `${surface.name}: no revealed view may extend past main`).toEqual([]);
      expect(revealed.main, `${surface.name}: main must not scroll sideways with every view open`).toBeLessThanOrEqual(0);
    });
  }
});

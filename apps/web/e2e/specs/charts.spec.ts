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

const STATISTICS_EXAMPLE = SURFACES.find((s) => s.id === 'statistics-example')!;
const STATISTICS_ORDINARY = SURFACES.find((s) => s.id === 'statistics')!;
const STATISTICS_MINE = SURFACES.find((s) => s.id === 'statistics-mine')!;

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
 * ref callback. Negative control, run 2026-08-04: delete
 * `apply(node.getBoundingClientRect().width)` and this poll never settles — both
 * SVGs sit at the 560px fallback while their columns measure 918, and 5 of the 8
 * tests in this file fail here. The observer alone never delivers, not even 1.5s
 * after the region is opened.
 *
 * It is spelled as a poll rather than a bare assertion only so that a genuine
 * future re-render (a breakpoint reflow) is tolerated rather than turned into a
 * flake. The value it converges on is fixed at mount.
 */
async function openTechnicalDetails(page: import('@playwright/test').Page): Promise<void> {
  const summary = page.locator('details.stats-technical > summary');
  await expect(summary).toBeVisible();
  await summary.click();
  await expect(page.locator('details.stats-technical')).toHaveAttribute('open', '');
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

test.describe('@responsive Statistics charts (worked example)', () => {
  test('every chart carries BOTH text equivalents, at this viewport', async ({ page, app }) => {
    await app.open(STATISTICS_EXAMPLE);
    await openTechnicalDetails(page);

    const figures = page.locator('figure.stats-chart');
    const count = await figures.count();
    // Workflow bars · the evidence stack · operations by method · operations by
    // group. A count is asserted so a chart silently disappearing reads as a
    // failure rather than as a vacuous pass over zero figures.
    expect(count, 'the populated page draws four charts').toBe(4);

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

  test('the drawn SVG claims nothing — the text is authoritative', async ({ page, app }) => {
    await app.open(STATISTICS_EXAMPLE);
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
    await app.open(STATISTICS_EXAMPLE);
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
    await app.open(STATISTICS_EXAMPLE);
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
    await app.open(STATISTICS_EXAMPLE);
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
    for (const region of ['Workflow Distribution', 'Evidence and Validation']) {
      const section = page.getByRole('region', { name: region });
      await expect(section.locator('figure.stats-chart'), region).toHaveCount(0);
      await expect(section.locator('.stats-chart-grid'), region).toHaveCount(0);
      await expect(section.locator('table.stats-chart-table'), region).toHaveCount(0);
    }
    // …and it says so in words, rather than leaving a blank card.
    await expect(page.getByText(/No bar is drawn rather than a row of zeros/)).toBeVisible();
  });
});

test.describe('@responsive Statistics · My Stats', () => {
  test('renders the gate, and no chart, no skeleton and no zero', async ({ page, app }) => {
    await app.open(STATISTICS_MINE);

    await expect(page.getByRole('heading', { name: 'Personal Statistics' })).toBeVisible();
    await expect(page.getByText('Not Available in This Preview')).toBeVisible();

    const panel = page.locator('#statistics-tabpanel-mine');
    await expect(panel.locator('figure.stats-chart')).toHaveCount(0);
    await expect(panel.locator('.stats-chart-grid')).toHaveCount(0);
    await expect(panel.locator('[role="status"]')).toHaveCount(0);

    // No figure at all: a personal tab that cannot attribute a record must not
    // display a count, and "0" is a count.
    const text = (await panel.innerText()).replace(/\s+/g, ' ');
    expect(text, 'no numeral may appear on the personal tab').not.toMatch(/\d/);

    /*
     * …AND NO ZERO IN WORDS. `/\d/` above is digit-shaped, and so was every other
     * emptiness guard on this tab, so an independent reviewer's insertion —
     * "Zero records are attributed to you, and your export count is zero." —
     * passed all 8 tests in this file, INCLUDING THIS ONE, whose title claims to
     * check for "no zero".
     *
     * The rule is checked per sentence with a MODAL escape, because three
     * sentences on this tab legitimately deny a zero ("A count of zero WOULD say
     * you have no records") and a page-wide ban would flag exactly the copy doing
     * the honest work. Plain `not` is deliberately NOT an escape: "you have not
     * exported any records" is an assertion wearing a negation.
     *
     * DUPLICATED FROM `src/__tests__/my-stats.test.tsx`, which is the authority and
     * carries the two-directional polarity table. The two cannot share a module:
     * `tsconfig.app.json` includes only `src`, `e2e/tsconfig.json` is a separate
     * standalone project (see its own header), and the production build must not
     * depend on Playwright types. Keep them in lockstep.
     */
    const COUNT_NOUN =
      'records?|experiments?|exports?|fields?|figures?|activity|drafts?|issues?|questions?|counts?';
    const emptiness = [
      new RegExp(`\\b(?:zero|none|nil|nought|no)\\b(?:\\s+\\S+){0,2}?\\s+\\b(?:${COUNT_NOUN})\\b`, 'i'),
      new RegExp(`\\b(?:${COUNT_NOUN})\\b[^.;]{0,40}?\\b(?:is|are|was|were)\\s+(?:zero|none|nil|nought)\\b`, 'i'),
      new RegExp(`\\byou(?:r|rs)?\\b[^.;]{0,60}?\\b(?:not|never|n't)\\b[^.;]{0,40}?\\bany\\b(?:\\s+\\S+){0,2}?\\s+\\b(?:${COUNT_NOUN})\\b`, 'i'),
    ];
    const modalFrame = /\bwould\b|\bcannot\b|\bcan't\b|\bunable\b|\bno way\b|\brather than\b|\b(?:is|are) absent\b/i;
    const sentences = text.split(/(?<=[.;])\s+/);
    const claims = sentences.filter(
      (s) => emptiness.some((p) => p.test(s)) && !modalFrame.test(s),
    );
    expect(claims, 'a sentence on the personal tab asserts the reader has nothing').toEqual([]);
    // …and the honest zero-denying sentences really do reach the matcher, so
    // "nothing matched" cannot be mistaken for "the rule holds".
    expect(
      sentences.filter((s) => emptiness.some((p) => p.test(s))).length,
      "the tab's own zero-denying sentences must reach the matcher",
    ).toBeGreaterThanOrEqual(3);
  });

  test('lists all eight planned views as headings', async ({ page, app }) => {
    await app.open(STATISTICS_MINE);
    await expect(
      page.locator('#statistics-tabpanel-mine .stats-plan-card h3'),
    ).toHaveCount(8);
  });
});

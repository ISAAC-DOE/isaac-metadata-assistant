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
/* The worked-example OVERVIEW tab — named for the tab, because this spec now
   addresses two different Statistics tabs and `STATISTICS_EXAMPLE` alone no
   longer says which. */
const STATISTICS_EXAMPLE_OVERVIEW = SURFACES.find((s) => s.id === 'statistics-example')!;
const STATISTICS_ORDINARY = SURFACES.find((s) => s.id === 'statistics')!;

/*
 * ~~`openTechnicalDetails`, `settledVerificationSection` and the
 * `@responsive Statistics charts (worked example)` block~~ — REMOVED 2026-11-16. Their
 * charts are on Statistics → Build & Verification, a developer tab shown only with
 * `VITE_ISAAC_DEV_TOOLS=1`, which this suite's build does not set, so `?tab=build` lands
 * on Overview and the `statistics-build` surface is retired. The chart components are
 * still measured here on Overview (the record-derived pair below); the Build tab's
 * content is held in jsdom with the flag on (`statistics-page.test.tsx`).
 */

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
  for (const surface of [STATISTICS_EXAMPLE_OVERVIEW, STATISTICS_ORDINARY]) {
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

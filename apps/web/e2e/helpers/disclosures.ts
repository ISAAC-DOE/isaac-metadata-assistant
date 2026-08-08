/**
 * Open EVERY disclosure on a surface that NO `SURFACES` entry can reach, so
 * their contents are scanned rather than silently exempt.
 *
 * ── Why this is a HELPER and not a private function in one spec ─────────────
 *
 * It lived inside `specs/a11y-axe.spec.ts` until `specs/a11y-narrow.spec.ts` was
 * added. The narrow sweep called `app.open(surface)` and scanned — without this
 * step — so the two sweeps were scanning DIFFERENT DOM on `statistics` and
 * `statistics-example`: five disclosures open at the five Playwright viewports,
 * five disclosures CLOSED at 320 and 390. Two axe baselines whose numbers are
 * compared to each other must come from the same page state, and a spec cannot
 * import a helper out of another spec without re-registering that spec's tests.
 * Hence this file.
 *
 * ── Why it exists at all ────────────────────────────────────────────────────
 *
 * A `<details>` has no URL state, so a surface's `path` cannot open one; and axe
 * does not scan a closed disclosure. When the Statistics slice moved the two
 * `/api/about` cards into a collapsed `Technical Details` region, their two
 * `.stat-card-note` `color-contrast` failures stopped being counted — and the
 * baseline recorded the drop as a coverage gap, with a note claiming the
 * unmeasured instances were only those two and that "not one is a chart".
 *
 * Both halves of that claim were false. Measured by an independent reviewer,
 * opening the region on `statistics-example` raised the failing node count from
 * 9 to 12: the third node was a CHART AXIS TICK, at `--text-tertiary` #78838f /
 * 10.5px — a new WCAG 1.4.3 failure shipping invisibly behind a note asserting
 * it did not exist. (The token has since been darkened to `--text-muted`, which
 * is why the tick no longer appears in the counts; the coverage this restores is
 * what made it visible.)
 *
 * ── AND FOUR MORE, ADDED BY THE VISUAL-FIRST REORGANISATION ─────────────────
 *
 * That slice moved Record Verification to the top of the Statistics General tab
 * and moved its supporting PROSE into four new closed disclosures beside
 * Technical Details. Every one of them is unreachable by URL for exactly the
 * reason above, so they are opened here too.
 *
 * THE RULE THIS ENFORCES IS THE ONE THE HISTORY ABOVE ESTABLISHED: a baseline
 * number that drops because content is now hidden is a COVERAGE LOSS, not an
 * accessibility win. Four disclosures' worth of copy going unscanned while the
 * counts stayed flat would be that same defect at four times the size — and it
 * would look like nothing had happened, which is what makes it worth a helper
 * rather than a comment.
 *
 * ── What it deliberately does NOT open ──────────────────────────────────────
 *
 * Each chart's own data-table `<details class="stats-chart-table-wrap">` stays
 * closed. Those are a per-figure text equivalent whose default state is closed
 * for every reader, and opening four tables at seven widths would move counts
 * for a reason unrelated to this gap. They remain unscanned, which is a real and
 * still-open limitation and is stated here rather than left to be discovered.
 */

import { expect, type Page } from '@playwright/test';

/**
 * How many `details.stats-disclosure` each surface mounts.
 *
 * DECLARED PER SURFACE, not counted and accepted, so that a disclosure appearing
 * or disappearing names itself here instead of moving a scan count that nobody
 * can then explain. Anything absent from this map must mount none.
 *
 * The four are the Statistics General tab's supporting-copy disclosures — How
 * Verification Works, How to Interpret Results, Mutation Methodology, Known
 * Limitations. `statistics-mine` is the My Stats tab, which renders none of them
 * and no `details.stats-technical` either.
 */
export const PROSE_DISCLOSURES: Readonly<Record<string, number>> = Object.freeze({
  statistics: 4,
  'statistics-example': 4,
});

export async function openUnreachableDisclosures(page: Page, surfaceId: string): Promise<void> {
  const technical = page.locator('details.stats-technical');
  const mounted = await technical.count();
  /*
   * ONE, ASSERTED. `technical.locator('> summary').click()` resolves through a
   * strict-mode locator, so a second `details.stats-technical` on any surface
   * would throw "resolved to 2 elements" from inside a helper whose job is
   * coverage — an opaque failure in every a11y scan at every viewport, naming
   * neither the surface nor the cause. Asserted here so the second mount names
   * itself.
   *
   * IT IS STILL ONE, and that is why the four prose disclosures carry their own
   * class (`details.stats-disclosure`, see `StatsCharts.tsx` →
   * `TechnicalDetailsProps.variant`): giving them this class would have turned
   * this locator — and the `toHaveCount(1)` in `statistics-states.spec.ts`, and
   * `openTechnicalDetails` in `charts.spec.ts` — into that same opaque failure.
   */
  if (mounted > 0) {
    expect(mounted, 'a surface must mount exactly one details.stats-technical').toBe(1);
    await technical.locator('> summary').click();
    await expect(technical).toHaveAttribute('open', '');
  }

  /*
   * The prose disclosures, opened one at a time by index — `.nth(i)` rather than
   * a bare locator, because there are legitimately several and a strict-mode
   * click would throw on the second.
   *
   * The count is DECLARED (`PROSE_DISCLOSURES`) and asserted, not measured and
   * accepted: an unopened fifth disclosure would silently exempt its contents
   * from every scan at every viewport, which is precisely the coverage gap this
   * helper exists to close.
   */
  const prose = page.locator('details.stats-disclosure');
  const expectedProse = PROSE_DISCLOSURES[surfaceId] ?? 0;
  const proseCount = await prose.count();
  expect(
    proseCount,
    `surface "${surfaceId}" mounts ${proseCount} details.stats-disclosure; ` +
      `PROSE_DISCLOSURES in e2e/helpers/disclosures.ts declares ${expectedProse}. A disclosure ` +
      'that is not opened here is not scanned by axe at any viewport — update the map in the ' +
      'same change that adds or removes one.'
  ).toBe(expectedProse);
  for (let i = 0; i < proseCount; i++) {
    const one = prose.nth(i);
    await one.locator('> summary').click();
    await expect(one).toHaveAttribute('open', '');
  }
}

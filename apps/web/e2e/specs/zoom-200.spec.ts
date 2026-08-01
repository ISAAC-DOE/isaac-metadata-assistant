/**
 * LAYOUT-EQUIVALENT coverage for 200% browser zoom. NOT browser zoom itself.
 * @zoom
 *
 * ── What this project is, stated exactly ────────────────────────────────────
 *
 * The `zoom-200` project is a 640x400 CSS-px viewport at `deviceScaleFactor: 2`.
 * That is the LAYOUT-EQUIVALENT of a 1280px-wide window at 200% zoom: it
 * reproduces the 200% effective CSS width, so every `@media (max-width: …)`
 * query, every `vw`/`vh` unit and every flex/grid reflow sees what the zoomed
 * user's page sees, and `devicePixelRatio` matches.
 *
 * ── What it does NOT reproduce ──────────────────────────────────────────────
 *
 * Layout equivalence is not zoom. This project does not reproduce:
 *
 *   * browser CHROME scaling (toolbars, tab strip, the omnibox);
 *   * SCROLLBAR scaling — real zoom scales the scrollbar, which eats layout
 *     width; headless Chromium has no scrollbar at all;
 *   * every text-metric ROUNDING effect: real zoom rounds glyph advances at the
 *     zoomed scale, and DPR-2 rasterisation is close but not identical, so a
 *     wrap boundary can differ by a character;
 *   * OS-level text scaling, browser minimum-font-size, or `text-size-adjust`;
 *   * `window.outerWidth`, which stays 640 here and would read 1280 under real
 *     zoom, and `visualViewport.scale`, which stays 1;
 *   * any other page-zoom side effect not listed above. The list is not a
 *     promise that it is complete.
 *
 * So NOTHING in this file may be described as "the suite performs 200% browser
 * zoom", and no result here may be cited as evidence that the app was checked
 * at browser zoom. **Actual browser 200% zoom remains a short human QA gate**,
 * and it is still open.
 *
 * ── Substitutes that were evaluated and REJECTED ────────────────────────────
 *
 * None of these is browser zoom either, and none may be swapped in and then
 * described as one:
 *
 *   * CDP `Emulation.setPageScaleFactor` — that is PINCH zoom. It moves
 *     `visualViewport.scale` and magnifies without reflowing.
 *   * `Emulation.setDeviceMetricsOverride` with only a `scale` — no effect.
 *   * `--force-device-scale-factor` — overridden by Playwright's own metrics
 *     override.
 *   * CSS `zoom` / `document.body.style.zoom` — a non-standard rendering quirk
 *     that scales a subtree without changing the layout viewport, so media
 *     queries never fire. That is the OPPOSITE of what browser zoom does.
 *   * a CSS `transform: scale()` — visual only; no reflow, no media queries.
 *
 * Real Cmd/Ctrl-+ zoom has no automation surface in Chromium, which is exactly
 * why the human gate exists rather than being automated away.
 *
 * ── The rest of this file ───────────────────────────────────────────────────
 *
 * A WCAG-1.4.10-STYLE reflow sweep at the 200% step only. This is NOT WCAG
 * 1.4.10 conformance: that criterion is defined at 400% / 320px, and the test
 * below says so itself. (320px IS swept, at DPR 1, by
 * `specs/layout-widths.spec.ts` — which is likewise not a 1.4.10 conformance
 * claim.)
 *
 * The spec runs ONLY in the `zoom-200` project. Its first job is to make the
 * emulation falsifiable: if someone later "fixes" the config by dropping
 * `deviceScaleFactor: 2`, or swaps the viewport for a plain 640px window, these
 * assertions fail rather than quietly degrading into a narrow-viewport test.
 *
 * Read `playwright.config.ts`'s header for the mechanism in full.
 */

import { expect, test } from '../fixtures';
import { horizontalPageScroll } from '../helpers/layout';
import { SURFACES } from '../surfaces';

test('@zoom the emulation is what it claims: LAYOUT-EQUIVALENT 640 CSS px viewport at DPR 2 (not browser zoom)', async ({
  page,
  app,
}, testInfo) => {
  expect(testInfo.project.name).toBe('zoom-200');
  await app.open(SURFACES.find((s) => s.id === 'experiments')!);

  const metrics = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    dpr: window.devicePixelRatio,
    clientWidth: document.documentElement.clientWidth,
    visualScale: window.visualViewport?.scale ?? null,
    matchesNarrowBreakpoint: window.matchMedia('(max-width: 640px)').matches,
    matchesHiDpi: window.matchMedia('(min-resolution: 2dppx)').matches,
  }));

  // 1280 / 2 = 640, 800 / 2 = 400 — the layout viewport a 1280x800 window has
  // at 200% zoom.
  expect(metrics.innerWidth).toBe(640);
  expect(metrics.innerHeight).toBe(400);
  // DPR doubles under real zoom. This is what separates this project from a
  // plain 640px-wide window, which would report 1.
  expect(metrics.dpr).toBe(2);
  expect(metrics.matchesHiDpi).toBe(true);
  // The app's own `max-width: 640px` breakpoint therefore engages, exactly as
  // it would for the zoomed user.
  expect(metrics.matchesNarrowBreakpoint).toBe(true);
  // And this is emulation, not pinch-zoom: the visual viewport scale stays 1.
  // Stated as an assertion so the distinction is recorded in the suite itself.
  expect(metrics.visualScale).toBe(1);
});

test('@zoom no two-dimensional scrolling at the 200% layout-equivalent width (NB: not WCAG 1.4.10, which is 400%/320px)', async ({
  page,
  app,
}) => {
  // Deliberately NOT titled as a 1.4.10 pass. That success criterion asks for
  // content at 320 CSS px wide — 400% of 1280 — with no two-directional
  // scrolling. This test covers the 200% step, which is the one the project's
  // open human sign-off gate names, and it covers it at the layout-equivalent
  // WIDTH rather than under the browser's zoom command. Nothing here may be
  // cited as WCAG 1.4.10 conformance, and nothing here replaces the human
  // browser-zoom gate.
  const failures: string[] = [];
  for (const surface of SURFACES) {
    await app.open(surface);
    const s = await horizontalPageScroll(page);
    if (s.docScrollWidth > s.docClientWidth + 1) {
      failures.push(`${surface.id}: ${s.docScrollWidth} > ${s.docClientWidth}`);
    }
  }
  expect(failures, failures.length ? `Horizontal scrolling at the 200% layout-equivalent width (640 CSS px):\n  ${failures.join('\n  ')}` : undefined).toEqual(
    []
  );
});

test('@zoom the primary chrome stays operable at the 200% layout-equivalent width', async ({ page, app }) => {
  await app.open(SURFACES.find((s) => s.id === 'experiments')!);

  // The search trigger is still hit-testable at its own centre (i.e. nothing
  // is drawn over it once the topbar has collapsed).
  const trigger = page.locator('button.topbar-search');
  await expect(trigger).toBeVisible();
  const reachable = await trigger.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!hit && (hit === el || el.contains(hit));
  });
  expect(reachable, 'the search trigger is occluded at the 200% layout-equivalent width').toBe(true);

  // It still opens and closes by keyboard.
  await trigger.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('@zoom text is not clamped to an unreadable size by the DPR change', async ({ page, app }) => {
  await app.open(SURFACES.find((s) => s.id === 'experiments')!);
  // CSS px sizes must be unchanged by zoom — a real zoomed browser scales the
  // rendering, not the computed value, and this project reproduces that by
  // holding DPR at 2 rather than by zooming. A stylesheet that shrank text at
  // narrow widths would show up here.
  const smallest = await page.evaluate(() => {
    let min = Infinity;
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('main *'))) {
      const own = Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? '').trim());
      if (!own) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      min = Math.min(min, parseFloat(getComputedStyle(el).fontSize));
    }
    return min;
  });
  expect(smallest, `smallest rendered text is ${smallest}px at the 200% layout-equivalent width`).toBeGreaterThanOrEqual(10);
});

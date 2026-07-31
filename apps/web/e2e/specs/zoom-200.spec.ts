/**
 * 200% browser zoom — proof that the emulation is real, plus the WCAG 1.4.10
 * reflow criterion.
 * @zoom
 *
 * This spec runs ONLY in the `zoom-200` project. Its first job is to make the
 * emulation falsifiable: if someone later "fixes" the config by dropping
 * `deviceScaleFactor: 2`, or swaps the viewport for a plain 640px window, these
 * assertions fail rather than quietly degrading into a narrow-viewport test.
 *
 * Read `playwright.config.ts`'s header for the exact mechanism and its honest
 * limits — in particular, this is viewport-size + device-pixel-ratio emulation,
 * not the browser's own zoom command, and `window.outerWidth` therefore differs
 * from what a real zoomed browser would report.
 */

import { expect, test } from '../fixtures';
import { horizontalPageScroll } from '../helpers/layout';
import { SURFACES } from '../surfaces';

test('@zoom the emulation is what it claims: 640 CSS px layout viewport at DPR 2', async ({ page, app }, testInfo) => {
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

test('@zoom no two-dimensional scrolling at 200% (NB: not WCAG 1.4.10, which is 400%/320px)', async ({
  page,
  app,
}) => {
  // Deliberately NOT titled as a 1.4.10 pass. That success criterion asks for
  // content at 320 CSS px wide — 400% of 1280 — with no two-directional
  // scrolling. This suite tests the 200% step, which is the one the project's
  // open human sign-off gate names. 400% / 320px is NOT covered anywhere in
  // this suite, so nothing here may be cited as WCAG 1.4.10 conformance.
  const failures: string[] = [];
  for (const surface of SURFACES) {
    await app.open(surface);
    const s = await horizontalPageScroll(page);
    if (s.docScrollWidth > s.docClientWidth + 1) {
      failures.push(`${surface.id}: ${s.docScrollWidth} > ${s.docClientWidth}`);
    }
  }
  expect(failures, failures.length ? `Horizontal scrolling at 200% zoom:\n  ${failures.join('\n  ')}` : undefined).toEqual(
    []
  );
});

test('@zoom the primary chrome stays operable at 200%', async ({ page, app }) => {
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
  expect(reachable, 'the search trigger is occluded at 200% zoom').toBe(true);

  // It still opens and closes by keyboard.
  await trigger.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('@zoom text is not clamped to an unreadable size by the DPR change', async ({ page, app }) => {
  await app.open(SURFACES.find((s) => s.id === 'experiments')!);
  // CSS px sizes must be unchanged by zoom — the browser scales the rendering,
  // not the computed value. A stylesheet that shrank text at narrow widths
  // would show up here.
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
  expect(smallest, `smallest rendered text is ${smallest}px at 200% zoom`).toBeGreaterThanOrEqual(10);
});

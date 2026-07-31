/**
 * Document structure — landmarks, heading hierarchy, and non-colour-only status.
 * @responsive
 *
 * These are the checks axe cannot make for us because they depend on knowing
 * what the app *intends*: that there is exactly one main landmark reachable
 * from a skip link, that heading levels do not skip, and that status is never
 * carried by colour alone.
 */

import { expect, test } from '../fixtures';
import { SURFACES } from '../surfaces';

for (const surface of SURFACES) {
  test(`@responsive landmarks: ${surface.name}`, async ({ page, app }) => {
    await app.open(surface);

    // Exactly one main landmark, and the skip link points at it.
    await expect(page.locator('main')).toHaveCount(1);
    await expect(page.locator('main#main')).toHaveCount(1);
    const skip = page.locator('a.skip-link');
    await expect(skip).toHaveCount(1);
    await expect(skip).toHaveAttribute('href', '#main');

    // A banner region exists on every surface (the TopBar).
    await expect(page.locator('header').first()).toBeVisible();

    // At most ONE contentinfo. The comment used to say "at most one" while the
    // assertion allowed two; measured across all 18 surfaces at all 5
    // viewports, the real maximum is 1 — `src/components/StatusBar.tsx:111` is
    // the only `<footer>` in the codebase, and it renders at screen level
    // (`div.app > div.screen-card > footer.statusbar`) on the record surfaces
    // only. Both numbers now say 1.
    const footers = await page.evaluate(() => {
      const all = Array.from(document.querySelectorAll('footer'));
      return {
        total: all.length,
        // A `<footer>` inside main/article/aside/nav/section is NOT a
        // contentinfo landmark, so only the screen-level ones count.
        landmarks: all.filter((f) => !f.closest('main, article, aside, nav, section')).length,
      };
    });
    expect(footers.landmarks, `${surface.path}: more than one contentinfo landmark`).toBeLessThanOrEqual(1);
    expect(footers.total, `${surface.path}: unexpected extra <footer> element(s)`).toBeLessThanOrEqual(1);
  });

  test(`@responsive heading hierarchy: ${surface.name}`, async ({ page, app }, testInfo) => {
    await app.open(surface);

    const headings = await page.evaluate(() =>
      Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
        .filter((h) => {
          const st = getComputedStyle(h);
          return st.display !== 'none' && st.visibility !== 'hidden';
        })
        .map((h) => ({ level: Number(h.tagName[1]), text: (h.textContent ?? '').trim().slice(0, 60) }))
    );

    const h1s = headings.filter((h) => h.level === 1);
    if (surface.expectH1 === false) {
      // Recorded FINDING A11Y-05 rather than silently skipped: assert the known
      // state so that FIXING it (adding an <h1>) makes this test fail loudly and
      // the finding gets closed.
      expect(
        h1s.length,
        `${surface.path} is recorded in surfaces.ts as having no <h1> (FINDING A11Y-05). ` +
          `If an <h1> has been added, drop \`expectH1: false\` and remove the page-has-heading-one baseline entry.`
      ).toBe(0);
    } else {
      expect(h1s.length, `${surface.path} should have exactly one <h1>, found ${h1s.length}`).toBe(1);
    }

    // No skipped levels on the way down (h2 → h4 is a skip; h4 → h2 is not).
    const skips: string[] = [];
    for (let i = 1; i < headings.length; i++) {
      const prev = headings[i - 1];
      const cur = headings[i];
      if (cur.level > prev.level + 1) skips.push(`h${prev.level} "${prev.text}" → h${cur.level} "${cur.text}"`);
    }
    expect(skips, skips.length ? `Skipped heading levels on ${surface.path}:\n  ${skips.join('\n  ')}` : undefined).toEqual(
      []
    );

    // Informational: is the h1 the first heading in DOM order? A complementary
    // landmark that precedes <main> legitimately puts an h2 first, so this is
    // annotated, not asserted.
    if (h1s.length === 1 && headings[0]?.level !== 1) {
      testInfo.annotations.push({
        type: 'heading-dom-order',
        description: `${surface.id}: first heading in DOM order is h${headings[0].level} "${headings[0].text}", before the h1.`,
      });
    }
  });

  test(`@responsive status is not colour-only: ${surface.name}`, async ({ page, app }) => {
    await app.open(surface);

    // Best-effort, and honest about being best-effort: a machine cannot tell
    // "red means bad" from a screenshot. What it CAN tell is whether a
    // status-ish element carries any text or accessible name at all, and
    // whether the coloured dots are correctly marked decorative.
    const colourOnly = await page.evaluate(() => {
      const out: string[] = [];
      const candidates = Array.from(
        document.querySelectorAll<HTMLElement>('[class*="chip"], [class*="status"], [class*="badge"], [class*="verdict"]')
      );
      for (const el of candidates) {
        const st = getComputedStyle(el);
        if (st.display === 'none' || st.visibility === 'hidden') continue;
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        // Containers are not the thing being tested; only leaf-ish status marks.
        if (el.querySelector('[class*="chip"], [class*="status"], [class*="badge"]')) continue;
        // Correctly decorative elements are not a colour-only-meaning defect —
        // e.g. `span.statusbar-sep`, which matches `[class*="status"]` by
        // accident and is already `aria-hidden="true"`.
        if (el.closest('[aria-hidden="true"]')) continue;
        const text = (el.innerText ?? el.textContent ?? '').trim();
        const label = el.getAttribute('aria-label') ?? el.getAttribute('title') ?? '';
        if (!text && !label) {
          const cls = typeof el.className === 'string' ? el.className : '';
          out.push(`${el.tagName.toLowerCase()}.${cls.trim().split(/\s+/).slice(0, 3).join('.')}`);
        }
      }
      return [...new Set(out)];
    });

    expect(
      colourOnly,
      colourOnly.length
        ? `Status-like elements on ${surface.path} with neither text nor an accessible name ` +
            `(state would be conveyed by colour/shape alone):\n  ${colourOnly.join('\n  ')}`
        : undefined
    ).toEqual([]);

    // The decorative dots must be hidden from assistive tech, so a screen
    // reader hears the label rather than an unlabelled graphic.
    const exposedDots = await page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLElement>('span.dot, span[class^="dot-"], span[class*=" dot-"]'))
        .filter((el) => {
          const st = getComputedStyle(el);
          if (st.display === 'none' || st.visibility === 'hidden') return false;
          return el.getAttribute('aria-hidden') !== 'true' && !(el.textContent ?? '').trim();
        })
        .map((el) => (typeof el.className === 'string' ? el.className : 'dot'))
    );
    expect(
      [...new Set(exposedDots)],
      exposedDots.length ? `Empty status dots on ${surface.path} not marked aria-hidden.` : undefined
    ).toEqual([]);
  });
}

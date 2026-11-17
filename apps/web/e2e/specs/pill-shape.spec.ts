/**
 * A PILL-RADIUS CHIP IS NEVER TALLER THAN IT IS WIDE — the invariant behind a
 * defect no mechanical check in this repository could see.
 *
 * ── WHAT WAS BROKEN, AND WHY NOTHING CAUGHT IT ───────────────────────────────
 *
 * `/imports` renders its workflow as `ol.hi-steps > li.hi-step`, each chip with
 * `border-radius: var(--radius-pill)` (999px). `align-items` was unset on the
 * row, so it defaulted to `normal` -> `stretch`, and a flex row stretches every
 * item to the tallest. One chip — the `.unbuilt` step — carries a three-line
 * sentence explaining why that stage does not exist, so it is ~70px tall. The
 * other five hold a single word.
 *
 * Measured in Chromium on `/imports`, by toggling that one property:
 *
 *   align-items: normal (before)   70 70 70 70 70 70
 *   align-items: flex-start         23 23 23 23 23 70
 *
 * A 999px radius on a 23px-tall chip is a correct pill. On a 70px-tall chip only
 * 48px wide (`Parse`) it is an ELLIPSE — and with the label pinned to the top of
 * the stretched box the word appeared to float above its own outline. The strip
 * read as six lozenges of random shape rather than as a workflow.
 *
 * NO EXISTING GUARD COULD HAVE SEEN IT. Nothing was clipped, so
 * `findClippedText` was silent; nothing was covered, so `findObscuredControls`
 * was silent; the contrast baseline counts violating nodes and an ellipse
 * violates no colour rule; and jsdom computes no layout, so no unit test can
 * measure a border radius against a box. It was found by LOOKING at the page.
 *
 * ── WHY THE ASSERTION IS GENERAL RATHER THAN ABOUT `/imports` ────────────────
 *
 * The defect is not "this strip stretched". It is that a pill radius and a
 * multi-line box are incompatible, and this app paints pills in many places. So
 * this walks EVERY element whose computed radius is at least half its own height
 * — the condition under which the radius actually rounds the full side — and
 * requires it to be at least as wide as it is tall. A chip that fails is either
 * an ellipse or a lozenge, whichever way round.
 *
 * Deliberately NOT a check that heights are equal or unequal: a row of equal
 * pills is fine, and so is a row of differing ones. The shape is the thing a
 * reader sees.
 *
 * ── `app.goto`, NOT `app.gotoExample`, AND THAT IS A FIX RATHER THAN A STYLE ──
 *
 * None of these four surfaces needs a record, so none needs a worked-example
 * session. My first version used `gotoExample` anyway, and it FLAKED: with four
 * workers against one backend, a worker can be mid-navigation while another
 * worker's teardown discards the shared session, and the strip then renders
 * against a torn-down scope — one run reported `1 failed / 3 passed` for a file
 * that passes 4/4 alone and 4/4 since. `app.goto` stays in the ORDINARY scope
 * (`fixtures.ts`: "app.goto() stays ORDINARY, which is..."), so this file no
 * longer depends on a lifecycle it never needed.
 */

import { expect, test } from '../fixtures';

/** Surfaces reached without mutating anything, one per layout family. */
const SURFACES: readonly { readonly name: string; readonly path: string }[] = [
  { name: 'Historical Import (the skill guide)', path: '/imports' },
  { name: 'My Experiments', path: '/experiments' },
  { name: 'Governance & Safety', path: '/governance' },
  { name: 'Settings & API', path: '/settings' },
];

/** The widths where wrapping changes a chip's height, plus the shipped desktop. */
const WIDTHS = [1280, 768, 390] as const;

type Offender = {
  selector: string;
  text: string;
  width: number;
  height: number;
  radius: number;
};

for (const width of WIDTHS) {
  test(`@responsive no pill-radius element is taller than it is wide at ${width}px`, async ({
    page,
    app,
  }) => {
    await page.setViewportSize({ width, height: 812 });

    for (const surface of SURFACES) {
      await app.goto(surface.path);
      /*
       * WAIT FOR THE SURFACE, NOT JUST FOR THE APP. `app.goto` settles on
       * `main#main` being visible, which proves React mounted and nothing more —
       * and `surfaces.ts` warns in as many words that a check on `/imports` "would
       * resolve while `role=\"status\"`/`Loading imports…` was still on". Scanning
       * a half-rendered screen would not FAIL here; it would PASS while measuring
       * almost nothing, which is the worse outcome for a guard.
       */
      await expect(page.locator('main#main h1').first()).toBeVisible();

      const offenders: Offender[] = await page.evaluate(() => {
        const out: Offender[] = [];
        for (const el of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
          const box = el.getBoundingClientRect();
          // Invisible or zero-area elements have no shape to get wrong.
          if (box.width < 4 || box.height < 4) continue;
          const style = window.getComputedStyle(el);
          if (style.visibility === 'hidden' || style.display === 'none') continue;
          // Only a radius that reaches half the side actually rounds it fully;
          // anything smaller is an ordinary rounded corner and is not a pill.
          const radius = Number.parseFloat(style.borderTopLeftRadius);
          if (!Number.isFinite(radius) || radius < box.height / 2) continue;
          // A circle is a legitimate shape: an icon button, an avatar, a dot.
          // The defect is a box that is TALLER than it is wide while asking for
          // a fully-rounded side, which no deliberate design in this app does.
          if (box.width >= box.height) continue;
          // One pixel of rounding tolerance, so a 23.4 x 23.0 chip built from a
          // square icon is not reported as a lozenge.
          if (box.height - box.width <= 1) continue;
          const id = el.id ? `#${el.id}` : '';
          const cls = el.className && typeof el.className === 'string'
            ? `.${el.className.trim().split(/\s+/).join('.')}`
            : '';
          out.push({
            selector: `${el.tagName.toLowerCase()}${id}${cls}`,
            text: (el.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 60),
            width: Math.round(box.width),
            height: Math.round(box.height),
            radius: Math.round(radius),
          });
        }
        return out;
      });

      expect(
        offenders,
        `on ${surface.name} at ${width}px, ${offenders.length} element(s) ask for a ` +
          'fully-rounded side while being taller than they are wide, which renders as ' +
          'an ellipse rather than a pill. Either give the element a radius suited to a ' +
          'multi-line box (`--radius-inner`), or stop it being stretched by a taller ' +
          `sibling (\`align-items\`). Offenders: ${JSON.stringify(offenders)}`,
      ).toEqual([]);
    }
  });
}

/*
 * ~~`the /imports strip is SIX circle nodes on a connecting line`~~ — REMOVED 2026-11-16
 * with the in-browser import flow: `/imports` is the skill guide, which has no stepper.
 * The pill-shape sweep above still runs on it.
 */

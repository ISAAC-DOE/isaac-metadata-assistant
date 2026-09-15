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
  { name: 'Historical Import', path: '/imports' },
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

test('@responsive the /imports strip is SIX circle nodes on a connecting line, not pills, and the sentence is not a node', async ({
  page,
  app,
}) => {
  /*
   * THIS TEST PREVIOUSLY PINNED "six uniform pills joined by a chevron", AND
   * IS INVERTED RATHER THAN DELETED -- the established remedy here for a
   * test that pins a superseded design, not only a defect.
   *
   * WHY A SECOND INVERSION OF THE SAME TEST. The pill row itself was already
   * one correction (bordered/filled chips -> a `›`-joined chain of plain
   * words), made because the owner asked "are they supposed to be clickable
   * or something?" of the pill shape. Of THAT chevron-chain shape, the owner
   * said "it should be a little bit cleaner, and I think it should be like a
   * circle-dotted thing instead" -- so the invariant this file protects moves
   * again, from "six uniform pills" to "six circle nodes on one connecting
   * line, the unbuilt one dotted". What survives BOTH corrections, unchanged:
   * no node may hold a sentence, and the unbuilt step's disclosure lives
   * below the row as prose, tied to its step by `aria-describedby` rather
   * than by adjacency.
   *
   * THE STRIP IS NOW BEHIND A COLLAPSED `<details>` ("How Historical Import
   * works", `HistoricalImport.tsx`'s `ImportList`, P3 of the 2026-09-15
   * landing-density slice), so this test opens it before measuring -- a
   * closed `<details>` hides everything but its own `<summary>`, and a probe
   * that skipped this step would silently measure zero nodes rather than
   * six.
   */
  await page.setViewportSize({ width: 1280, height: 812 });
  await app.goto('/imports');
  await page.locator('details.hi-how-it-works > summary').click();
  await expect(page.locator('.hi-steps > .hi-step').first()).toBeVisible();

  const steps = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('.hi-steps > .hi-step')).map((li) => {
      const node = li.querySelector<HTMLElement>('.hi-step-node')!;
      const nodeBox = node.getBoundingClientRect();
      const nodeStyle = window.getComputedStyle(node);
      const liStyle = window.getComputedStyle(li);
      return {
        unbuilt: li.classList.contains('unbuilt'),
        reached: li.classList.contains('reached'),
        text: (li.querySelector('.hi-step-label')?.textContent ?? '').trim(),
        liBorderStyle: liStyle.borderStyle,
        liBackground: liStyle.backgroundColor,
        nodeWidth: Math.round(nodeBox.width),
        nodeHeight: Math.round(nodeBox.height),
        nodeBorderRadius: Math.round(Number.parseFloat(nodeStyle.borderTopLeftRadius)),
        nodeBorderStyle: nodeStyle.borderTopStyle,
        describedBy: li.getAttribute('aria-describedby'),
      };
    }),
  );

  expect(steps.length, 'the workflow strip is missing').toBe(6);

  // (1) EVERY node is a true CIRCLE -- width == height and fully rounded --
  //     which is the shape the owner asked for and the one the app-wide
  //     ellipse guard above explicitly exempts ("a dot").
  for (const step of steps) {
    expect(
      Math.abs(step.nodeWidth - step.nodeHeight),
      `"${step.text}" node is ${step.nodeWidth}x${step.nodeHeight}, not a circle`,
    ).toBeLessThanOrEqual(1);
    expect(
      step.nodeBorderRadius,
      `"${step.text}" node's radius does not reach half its own height`,
    ).toBeGreaterThanOrEqual(step.nodeHeight / 2 - 1);
  }

  // (2) THE ROW ITSELF IS NOT A CONTROL. `<li class="hi-step">` carries no
  //     border and no fill of its own -- only its `.hi-step-node` child does
  //     -- which is the property that keeps this from reading as a button
  //     the way the retired bordered/filled pill did.
  for (const step of steps) {
    expect(step.liBorderStyle, `"${step.text}" row itself has a border`).toBe('none');
  }

  // (3) THE UNBUILT NODE IS DOTTED OR DASHED, NOT A SOLID OUTLINE AND NOT A
  //     FILLED DISC -- the owner's own requested shape for exactly this step,
  //     and no rectangle anywhere.
  const unbuilt = steps.filter((s) => s.unbuilt);
  expect(unbuilt.length, 'no unbuilt step found -- has the fixture changed?').toBe(1);
  expect(['dotted', 'dashed']).toContain(unbuilt[0]!.nodeBorderStyle);

  // (4) No node holds a sentence -- a label, not prose.
  for (const step of steps) {
    expect(step.text.length, `"${step.text}" reads as prose, not a label`).toBeLessThan(40);
    expect(step.text, `"${step.text}" contains sentence punctuation`).not.toMatch(/[.!?]\s/);
  }

  // (5) The unbuilt step still SAYS it is unbuilt -- associated rather than
  //     merely adjacent, and the disclosure is prose in the document, not
  //     another node in the row.
  expect(unbuilt[0]!.describedBy, 'the unbuilt node names no disclosure').toBeTruthy();
  const note = page.locator(`#${unbuilt[0]!.describedBy}`);
  await expect(note).toBeVisible();
  await expect(note).toContainText(/Not built in this build/);
  expect(await note.evaluate((el) => el.classList.contains('hi-step'))).toBe(false);
});

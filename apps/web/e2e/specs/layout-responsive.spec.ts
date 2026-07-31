/**
 * Responsive layout integrity — every surface, every viewport.
 * @responsive
 *
 * Three questions, asked of real rendered geometry:
 *   1. does the PAGE scroll horizontally? (it must never)
 *   2. is any text CLIPPED by an `overflow: hidden` ancestor with no ellipsis?
 *   3. is any interactive control OCCLUDED by something drawn over it?
 *
 * Not a pixel snapshot. See `helpers/layout.ts` for why, and for the exact
 * definition of each probe. Known pre-existing defects are enumerated in
 * `layout-baseline.ts`; anything else fails.
 */

import { applicableLayoutFindings, isKnownLayoutFinding } from '../layout-baseline';
import { expect, test } from '../fixtures';
import {
  findClippedText,
  findObscuredControls,
  horizontalPageScroll,
  render,
  scrollToBottom,
  scrollToTop,
  type Offender,
} from '../helpers/layout';
import { SURFACES } from '../surfaces';

for (const surface of SURFACES) {
  test(`@responsive layout: ${surface.name}`, async ({ page, app }, testInfo) => {
    await app.open(surface);
    const project = testInfo.project.name;

    // 1. The page body must never scroll horizontally. Wide content (tables,
    //    code blocks, the graph canvas) must scroll inside its own container.
    const scroll = await horizontalPageScroll(page);
    expect(
      scroll.docScrollWidth,
      `${surface.path} @ ${project}: documentElement scrolls horizontally ` +
        `(scrollWidth ${scroll.docScrollWidth} > clientWidth ${scroll.docClientWidth}).`
    ).toBeLessThanOrEqual(scroll.docClientWidth + 1);
    expect(
      scroll.bodyScrollWidth,
      `${surface.path} @ ${project}: body scrolls horizontally ` +
        `(scrollWidth ${scroll.bodyScrollWidth} > clientWidth ${scroll.bodyClientWidth}).`
    ).toBeLessThanOrEqual(scroll.bodyClientWidth + 1);

    // 2. Nothing is cut off with no way to read it.
    const clippedAll = await findClippedText(page);
    const clipped = clippedAll.filter((o) => !isKnownLayoutFinding('clipped', o.selector, surface.id, project));
    const clippedKnown = clippedAll.length - clipped.length;

    // 3. Nothing is drawn over a control. Checked at two scroll offsets so the
    //    below-the-fold content is covered too.
    await scrollToTop(page);
    const obscuredTop = await findObscuredControls(page);
    await scrollToBottom(page);
    const obscuredBottom = await findObscuredControls(page);
    const obscuredAll: Offender[] = [...obscuredTop, ...obscuredBottom];
    const obscured = obscuredAll.filter((o) => !isKnownLayoutFinding('obscured', o.selector, surface.id, project));
    const obscuredKnown = obscuredAll.length - obscured.length;

    testInfo.annotations.push({
      type: 'layout',
      description:
        `${surface.id} @ ${project}: ${clippedKnown} known-clipped, ${obscuredKnown} known-occluded ` +
        `(see e2e/layout-baseline.ts); ${clipped.length} new clipped, ${obscured.length} new occluded.`,
    });

    // Staleness signal, annotation only — a finding can legitimately be
    // viewport-conditional and this run only sees one viewport.
    const fired = new Set(
      [...clippedAll.map((o) => `clipped:${o.selector}`), ...obscuredAll.map((o) => `obscured:${o.selector}`)].flatMap(
        (k) => [k]
      )
    );
    const notFired = applicableLayoutFindings(surface.id, project).filter(
      (f) => ![...fired].some((k) => k.startsWith(`${f.kind}:`) && k.includes(f.selector))
    );
    if (notFired.length) {
      testInfo.annotations.push({
        type: 'layout-baseline-not-fired',
        description: `${surface.id} @ ${project}: ${notFired
          .map((f) => f.id)
          .join(', ')} — check whether these are fixed and delete the entry.`,
      });
    }

    expect(
      clipped,
      clipped.length
        ? `Clipped text on ${surface.path} @ ${project} (not in e2e/layout-baseline.ts):\n${render(clipped)}`
        : undefined
    ).toEqual([]);

    expect(
      obscured,
      obscured.length
        ? `Occluded interactive controls on ${surface.path} @ ${project} (not in e2e/layout-baseline.ts):\n${render(
            obscured
          )}`
        : undefined
    ).toEqual([]);
  });
}

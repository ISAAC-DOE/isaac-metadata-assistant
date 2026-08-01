/**
 * Responsive layout integrity — every surface, every viewport.
 * @responsive
 *
 * Four questions, asked of real rendered geometry:
 *   1. does the PAGE scroll horizontally? (it must never)
 *   2. does any REGION INSIDE the page scroll or clip horizontally? (new)
 *   3. is any text CLIPPED, or truncated so hard that nothing readable is left?
 *   4. is any control — or critical label — OCCLUDED or reduced to a sliver?
 *
 * Not a pixel snapshot. See `helpers/layout.ts` for why, and for the exact
 * definition of each probe. Known pre-existing defects are enumerated in
 * `layout-baseline.ts`; anything else fails.
 *
 * These probes measure rendered geometry, and there is no webfont, so two
 * recorded clips exist only under the wider Linux system face. The baseline
 * records an exact offender list per platform and this spec enforces the
 * current one. **CI (Linux) is the authority.**
 *
 * ── Where question 2 is ASSERTED, and why it is only annotated here ─────────
 *
 * Nested horizontal overflow is measured on every surface and every viewport in
 * this file, and reported in the `layout-nested-overflow` annotation — so it is
 * visible in this run and in CI. The ASSERTION lives in
 * `specs/layout-widths.spec.ts`, which sweeps 1280/1024/768/640/390/375/320 —
 * a strict superset of the widths this file runs at, plus 390 and 320, where
 * the defects actually live.
 *
 * The reason for splitting them is ownership, and it is a temporary state, not
 * a design: `layout-baseline.ts` is the file that records tolerated debt, its
 * `kind` union is `'clipped' | 'obscured'`, and it has no `'overflow'` member.
 * Asserting here would produce failures with nowhere to record them. Extending
 * that union and moving the assertion here is a one-line change for whoever
 * owns the baseline. Until then nothing is hidden: the annotation names every
 * offending selector.
 */

import { currentPlatform } from '../a11y-baseline';
import {
  applicableLayoutFindings,
  isKnownLayoutFinding,
  layoutKey,
  platformInstances,
} from '../layout-baseline';
import { overflowMatchersFor, hiddenTextMatchersFor } from '../layout-allowlist';
import { expect, test } from '../fixtures';
import {
  findClippedText,
  findObscuredControls,
  findOverflowingRegions,
  horizontalPageScroll,
  render,
  renderOverflow,
  renderedFontFamily,
  scrollToBottom,
  scrollToTop,
  type Offender,
} from '../helpers/layout';
import { SURFACES } from '../surfaces';

for (const surface of SURFACES) {
  test(`@responsive layout: ${surface.name}`, async ({ page, app }, testInfo) => {
    await app.open(surface);
    const project = testInfo.project.name;
    // Which column of `layout-baseline.ts` is in force. Throws with an
    // explanation on a platform nobody has measured — see `resolvePlatform`.
    const platform = currentPlatform();

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

    // 2. Nothing INSIDE the page scrolls or clips sideways either. The
    //    document-level check above is not sufficient and never was: at
    //    /experiments 375x812 it read 375 == 375 while `main.screen-main.pad`
    //    held 476px of content in a 353px box. Annotated here, asserted in
    //    `specs/layout-widths.spec.ts` — see the header for why.
    const overflow = await findOverflowingRegions(page, overflowMatchersFor(surface.id));
    testInfo.annotations.push({
      type: 'layout-nested-overflow',
      description: overflow.offenders.length
        ? `${surface.id} @ ${project}: ${overflow.offenders.length} region(s) overflow horizontally ` +
          `(asserted in specs/layout-widths.spec.ts):\n${renderOverflow(overflow.offenders)}`
        : `${surface.id} @ ${project}: no nested horizontal overflow ` +
          `(${overflow.allowed.length} allowlisted, ${overflow.ellipsisDeferred.length} ellipsis container(s) ` +
          `deferred to the content-loss tier).`,
    });

    // 3. Nothing is cut off with no way to read it.
    const clippedAll = await findClippedText(page, 'body', hiddenTextMatchersFor(surface.id));
    const clipped = clippedAll.filter(
      (o) => !isKnownLayoutFinding('clipped', o.selector, surface.id, project, platform)
    );
    const clippedKnown = clippedAll.length - clipped.length;

    // 4. Nothing is drawn over a control — or over a critical label, which the
    //    probe now also covers. Checked at two scroll offsets so the
    //    below-the-fold content is covered too.
    await scrollToTop(page);
    const obscuredTop = await findObscuredControls(page);
    await scrollToBottom(page);
    const obscuredBottom = await findObscuredControls(page);
    const obscuredAll: Offender[] = [...obscuredTop, ...obscuredBottom];
    const obscured = obscuredAll.filter(
      (o) => !isKnownLayoutFinding('obscured', o.selector, surface.id, project, platform)
    );
    const obscuredKnown = obscuredAll.length - obscured.length;

    testInfo.annotations.push({
      type: 'layout',
      description:
        `${surface.id} @ ${project} on ${platform} (font: ${await renderedFontFamily(page)}): ` +
        `${clippedKnown} known-clipped, ${obscuredKnown} known-occluded ` +
        `(see e2e/layout-baseline.ts); ${clipped.length} new clipped, ${obscured.length} new occluded.`,
    });

    // Staleness signal, annotation only — a finding can legitimately be
    // viewport-conditional and this run only sees one viewport.
    //
    // Matched PER RECORDED INSTANCE, against the exact selector strings in
    // `layout-baseline.ts`. It used to match by substring against a finding's
    // single human-readable `f.selector` tag, and that was not a style
    // preference — it produced a PERMANENTLY FALSE annotation:
    //
    //   LAYOUT-03's tag is `statusbar-right`, but one of its instances is
    //   `export-readiness-done@mobile-375x812` → `span.statusbar-eyebrow < …`.
    //   No selector containing "statusbar-right" ever fires at that pair, so
    //   the suite reported LAYOUT-03 as not-fired there on every run — while
    //   the occlusion probe was simultaneously reporting that very instance
    //   firing, at 5 of 5 sampled points. The annotation was telling the next
    //   session to delete a LIVE entry.
    //
    // That mattered beyond tidiness: `layout-baseline.ts` cites "this suite's
    // own staleness signal" as evidence for deleting LAYOUT-02's darwin
    // instance. That deletion is independently correct, but a signal used as
    // evidence must not be capable of lying. `layout-widths.spec.ts` already
    // matches per instance for the same reason; this is the same approach.
    //
    // A finding is now reported stale only for the instances that did not
    // fire, and it names them — so the annotation says WHAT to delete, not
    // just which id to go and re-derive.
    const fired = new Set([
      ...clippedAll.map((o) => `clipped:${o.selector}`),
      ...obscuredAll.map((o) => `obscured:${o.selector}`),
    ]);
    const notFired: string[] = [];
    for (const finding of applicableLayoutFindings(surface.id, project, platform)) {
      const recorded = platformInstances(finding.instances[layoutKey(surface.id, project)], platform);
      const missing = recorded.filter((sel) => !fired.has(`${finding.kind}:${sel}`));
      if (missing.length) notFired.push(`${finding.id}: ${missing.join(', ')}`);
    }
    if (notFired.length) {
      testInfo.annotations.push({
        type: 'layout-baseline-not-fired',
        description:
          `${surface.id} @ ${project} on ${platform}: recorded instance(s) that did NOT fire — ` +
          `check whether they are fixed and delete just those instances: ${notFired.join(' | ')}`,
      });
    }

    expect(
      clipped,
      clipped.length
        ? `Clipped text on ${surface.path} @ ${project} (not in the "${platform}" column of ` +
          `e2e/layout-baseline.ts):\n${render(clipped)}`
        : undefined
    ).toEqual([]);

    expect(
      obscured,
      obscured.length
        ? `Occluded interactive controls on ${surface.path} @ ${project} (not in the "${platform}" ` +
          `column of e2e/layout-baseline.ts):\n${render(
            obscured
          )}`
        : undefined
    ).toEqual([]);
  });
}

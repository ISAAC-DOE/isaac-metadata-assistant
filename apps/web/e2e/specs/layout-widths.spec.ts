/**
 * WIDTH SWEEP + regression cases for the three probe blind spots.
 * @responsive
 *
 * ── Why this file exists ────────────────────────────────────────────────────
 *
 * `layout-responsive.spec.ts` runs every surface at five FIXED viewports. That
 * caught nothing at the widths where this app actually breaks, because the
 * defects are BREAKPOINT and CONTENT-PRESSURE defects: they appear between the
 * configured sizes, or below the smallest one. Three measured examples from the
 * `ceea656` build, none of which any configured project would have seen:
 *
 *   * `main.screen-main.pad` scrolling horizontally (476 in a 353px box) at
 *     375 — the DOCUMENT measured 375 == 375, i.e. perfectly clean;
 *   * `a.record-title.record-title-link` painting 0px of 395px of text at 768;
 *   * `div.exp-title` painting 12px of 67px at 320.
 *
 * ── Why widths, and not more Playwright projects ────────────────────────────
 *
 * Adding projects multiplies the WHOLE suite (axe scans included) and perturbs
 * the count-based ratchet in `e2e/a11y-baseline.ts`. So this file runs inside
 * ONE project and moves the viewport itself with `page.setViewportSize`. The
 * cost is that DPR stays at that project's value; these are layout assertions
 * and DPR contributes nothing to CSS layout (see `playwright.config.ts`'s
 * header, which proves the same point for the zoom project).
 *
 * 320 is included and is not optional: it is the WCAG 1.4.10 reflow width and
 * the narrowest width the product claims to support. 390 is included because
 * it is the modern iPhone width and sits between the configured 375 and 640.
 *
 * ── The rendered font is logged on purpose ──────────────────────────────────
 *
 * There is no webfont, so `--font-ui` resolves to SF Pro on macOS and to a
 * DejaVu/Liberation face on `ubuntu-latest`. Those have different advance
 * widths, so a wrap boundary — and therefore a clip — can exist on one and not
 * the other. Every sweep prints the family it measured with, so a CI log can be
 * compared with a laptop log without guessing. **CI (Linux) is the authority.**
 */

import { currentPlatform } from '../a11y-baseline';
import { expect, test } from '../fixtures';
import {
  findClippedText,
  findObscuredControls,
  findOverflowingRegions,
  horizontalPageScroll,
  render,
  renderOverflow,
  renderedFontFamily,
} from '../helpers/layout';
import {
  LAYOUT_SWEEP_WIDTHS,
  applicableLayoutFindings,
  isKnownLayoutFinding,
  layoutKey,
  layoutWidthId,
  platformInstances,
} from '../layout-baseline';
import { hiddenTextMatchersFor, overflowMatchersFor } from '../layout-allowlist';
import { SURFACES } from '../surfaces';

/**
 * The single project this file runs in. `@responsive` is the only tag that
 * reaches more than one project, and `playwright.config.ts` (which this
 * workstream does not own) is where tags are mapped — so the file is tagged
 * `@responsive` for collection and then skipped everywhere except here. The
 * four skipped entries per test are visible in the report, which is the point:
 * the restriction is stated, not hidden.
 */
const HOST_PROJECT = 'desktop-1280x800';

/**
 * Breakpoint and content-pressure widths. 320 is required; see the header.
 *
 * Declared in `../layout-baseline` rather than here, so the fast invariant
 * suite can validate this file's baseline keys without starting a browser.
 * This alias keeps the sweep below reading exactly as it did.
 */
const WIDTHS = LAYOUT_SWEEP_WIDTHS;

/**
 * The "project" component of a `layout-baseline.ts` key for this file.
 *
 * This sweep does not have a Playwright project per measurement — it has a
 * WIDTH per measurement, inside one project — so its baseline pairs are
 * namespaced `surfaceId@width-<n>` rather than `surfaceId@desktop-1280x800`.
 * That keeps them from colliding with the five viewport projects'
 * `layout-responsive.spec.ts` entries, which is not pedantry: this file and
 * that one both measure 1280, 1024, 768 and 640, and a shared key would let a
 * defect recorded for one measurement silently excuse the other.
 *
 * `layoutKey()` already builds `surfaceId@projectId` from any two strings, so
 * nothing in `layout-baseline.ts` needed changing to support this.
 *
 * The definition now lives in `../layout-baseline` beside the widths it is
 * applied to, so a checker that never starts a browser can tell a legal
 * `width-<n>` key from a typo. This alias keeps the sweep's own prose intact.
 */
const widthKey = layoutWidthId;

test.describe('layout width sweep', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(
      testInfo.project.name !== HOST_PROJECT,
      `runs only in ${HOST_PROJECT}; it moves the viewport itself rather than adding projects`
    );
  });

  for (const width of WIDTHS) {
    test(`@responsive width ${width}: no nested overflow, no lost text, nothing obscured`, async ({
      page,
      app,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 812 });

      // Which column of `layout-baseline.ts` is in force. Throws with an
      // explanation on a platform nobody has measured — see `resolvePlatform`.
      const platform = currentPlatform();
      const projectKey = widthKey(width);

      const overflowFailures: string[] = [];
      const clippedFailures: string[] = [];
      const obscuredFailures: string[] = [];
      const staleness: string[] = [];
      let deferred = 0;
      let allowed = 0;
      let contained = 0;
      let knownOverflow = 0;
      let knownObscured = 0;
      let font = '(not measured)';

      for (const surface of SURFACES) {
        await app.open(surface);
        // The viewport is set before navigation, but a surface that mounts a
        // second pane can settle after it; re-assert the size so every
        // measurement below is taken at the width in the test title.
        await page.setViewportSize({ width, height: 812 });
        if (font === '(not measured)') font = await renderedFontFamily(page);

        // 1. The document itself. Kept here as well as in
        //    `layout-responsive.spec.ts` because at these widths it is the
        //    cheapest possible falsification of the nested check below: if the
        //    document scrolls, the nested finding may be a symptom rather than
        //    the cause.
        const doc = await horizontalPageScroll(page);
        if (doc.docScrollWidth > doc.docClientWidth + 1) {
          overflowFailures.push(
            `${surface.id}: DOCUMENT scrolls horizontally — ${doc.docScrollWidth} > ${doc.docClientWidth}`
          );
        }

        // 2. BLIND SPOT 1 — nested horizontal overflow.
        //    Known, enumerated debt (LAYOUT-04) is tolerated; anything else
        //    fails. The selector compared here is `o.selector`, byte-identical
        //    to the string `renderOverflow` prints in the failure message, so a
        //    baseline entry can always be copied verbatim from a failure.
        const overflow = await findOverflowingRegions(page, overflowMatchersFor(surface.id));
        deferred += overflow.ellipsisDeferred.length;
        allowed += overflow.allowed.length;
        contained += overflow.contained.length;
        const newOverflow = overflow.offenders.filter(
          (o) => !isKnownLayoutFinding('overflow', o.selector, surface.id, projectKey, platform)
        );
        knownOverflow += overflow.offenders.length - newOverflow.length;
        if (newOverflow.length) {
          overflowFailures.push(`${surface.id}:\n${renderOverflow(newOverflow)}`);
        }

        // 3. BLIND SPOT 2 — text that is present in the DOM and absent on
        //    screen. Only the content-loss tiers are asserted here; the
        //    `clipped-x` / `clipped-y` tiers stay in `layout-responsive.spec.ts`,
        //    which owns the per-platform baseline that records them.
        //
        //    DELIBERATELY NOT baseline-filtered. Nothing in the content-loss
        //    tier is recorded as debt, and this tier stays strict by decision:
        //    it is the one that answers "can the user read this at all?", so a
        //    finding here is not a tolerable rough edge. If a genuine one ever
        //    needs recording, that is a decision for the baseline's owner, not
        //    a filter to add here quietly.
        const clipped = await findClippedText(page, 'body', hiddenTextMatchersFor(surface.id));
        const lost = clipped.filter((c) => c.kind === 'total-loss' || c.kind === 'critical-loss');
        if (lost.length) clippedFailures.push(`${surface.id}:\n${render(lost)}`);

        // 4. BLIND SPOT 3 — occluded controls AND occluded critical labels.
        //    Known, enumerated debt (LAYOUT-03) is tolerated; anything else
        //    fails. Same exact-string contract as the overflow filter above.
        /*
         * KNOWN, MEASURED LIMITATION — disclosed rather than left implicit.
         *
         * This probes ONE scroll offset (the top). `layout-responsive.spec.ts`
         * deliberately probes two (top and bottom), because
         * `findObscuredControls`'s own contract says callers should. Measured
         * across all 7 sweep widths x 18 surfaces: 1 finding at the top offset,
         * 18 at the bottom — so **17 genuine occlusion instances are invisible
         * to this sweep**. Every one of them is the LAYOUT-03 class already
         * recorded in `layout-baseline.ts` (the floating Assistant trigger over
         * `span.statusbar-right` / `span.statusbar-eyebrow`) at 1024/768/640/
         * 390/375. Nothing NEW is being hidden.
         *
         * Not fixed here on purpose. The one-line fix (scrollToTop -> probe ->
         * scrollToBottom -> probe -> union) would raise 17 failures at
         * `@width-<n>` keys that do not exist in LAYOUT-03 yet, so it is a
         * baseline-authoring decision, not a probe defect — and those instances
         * can only be measured on darwin here, while Linux is the authority.
         * The remediation slice that added this file scoped it out explicitly.
         * Do it in the slice that fixes the trigger, and delete this comment
         * together with the instances rather than growing them.
         */
        const obscured = await findObscuredControls(page);
        const newObscured = obscured.filter(
          (o) => !isKnownLayoutFinding('obscured', o.selector, surface.id, projectKey, platform)
        );
        knownObscured += obscured.length - newObscured.length;
        if (newObscured.length) obscuredFailures.push(`${surface.id}:\n${render(newObscured)}`);

        // STALENESS, annotation only — never a failure. A recorded instance
        // that no longer fires means the CSS was fixed and the entry should be
        // deleted; failing on it would make fixing a defect turn the build red.
        //
        // Matched per RECORDED INSTANCE rather than by the substring heuristic
        // `layout-responsive.spec.ts` uses on `f.selector`. That heuristic
        // cannot work here: LAYOUT-04's human tag is
        // `nested-horizontal-overflow`, which appears in no offender selector,
        // so every applicable entry would be reported stale on every run.
        const fired = new Set([
          ...overflow.offenders.map((o) => `overflow:${o.selector}`),
          ...obscured.map((o) => `obscured:${o.selector}`),
        ]);
        for (const finding of applicableLayoutFindings(surface.id, projectKey, platform)) {
          const recorded = platformInstances(finding.instances[layoutKey(surface.id, projectKey)], platform);
          const missing = recorded.filter((sel) => !fired.has(`${finding.kind}:${sel}`));
          if (missing.length) {
            staleness.push(`${finding.id} @ ${surface.id}: ${missing.join(', ')}`);
          }
        }
      }

      testInfo.annotations.push({
        type: 'layout-width',
        description:
          `width ${width} on ${platform} — font: ${font}; ` +
          `${allowed} allowlisted overflow region(s), ${contained} with no visible source, ` +
          `${deferred} ellipsis container(s) deferred to the content-loss tier; ` +
          `${knownOverflow} known-overflow, ${knownObscured} known-occluded ` +
          `(recorded in e2e/layout-baseline.ts under @${projectKey}); ` +
          `${overflowFailures.length} NEW overflow, ${clippedFailures.length} NEW content-loss ` +
          `(never baseline-filtered), ${obscuredFailures.length} NEW occlusion finding(s).`,
      });
      if (staleness.length) {
        testInfo.annotations.push({
          type: 'layout-baseline-not-fired',
          description:
            `width ${width}: recorded instances that did NOT fire — check whether they are fixed and ` +
            `delete the entry: ${staleness.join(' | ')}`,
        });
      }
      // eslint-disable-next-line no-console
      console.log(
        `[layout-widths] ${width}px — rendered font: ${font}; ` +
          `${knownOverflow} known-overflow, ${knownObscured} known-occluded, ` +
          `${staleness.length} recorded instance(s) not fired`
      );

      expect(
        overflowFailures,
        overflowFailures.length
          ? `Horizontal overflow at ${width}px (font: ${font}, platform: ${platform}). A region that clips ` +
            `or scrolls sideways hides content or forces sideways reading. Deliberate scrollers are listed ` +
            `in e2e/layout-allowlist.ts; known debt is recorded in e2e/layout-baseline.ts under ` +
            `"<surface>@${projectKey}" (${knownOverflow} tolerated here). These are NOT recorded — the ` +
            `selectors below can be pasted verbatim into a baseline entry:\n${overflowFailures.join('\n')}`
          : undefined
      ).toEqual([]);

      expect(
        clippedFailures,
        clippedFailures.length
          ? `Text present in the DOM but not readable on screen at ${width}px (font: ${font}, ` +
            `platform: ${platform}). Truncation is allowed only while a meaningful fragment survives. ` +
            `This tier is deliberately NOT baseline-filtered:\n${clippedFailures.join('\n')}`
          : undefined
      ).toEqual([]);

      expect(
        obscuredFailures,
        obscuredFailures.length
          ? `Controls or critical labels covered / reduced to an unusable sliver at ${width}px ` +
            `(font: ${font}, platform: ${platform}). Known debt is recorded in e2e/layout-baseline.ts ` +
            `under "<surface>@${projectKey}" (${knownObscured} tolerated here). These are NOT recorded — ` +
            `the selectors below can be pasted verbatim into a baseline entry:\n${obscuredFailures.join('\n')}`
          : undefined
      ).toEqual([]);
    });
  }
});

/**
 * ── REGRESSION CASES ────────────────────────────────────────────────────────
 *
 * Each injects the geometry of a MEASURED defect from the `ceea656` build and
 * asserts the hardened probe reports it. They are deliberately independent of
 * whether the application has since been fixed: a live assertion goes green
 * when the CSS is fixed AND when the probe is broken, and those two look
 * identical from the outside. These do not — they are the same technique
 * `self-check.spec.ts` uses, applied to the three closed blind spots.
 *
 * All mutations are browser-side only; nothing is written to the backend.
 */
test.describe('probe regression cases (injected geometry)', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== HOST_PROJECT, `runs only in ${HOST_PROJECT}`);
  });

  const experiments = SURFACES.find((s) => s.id === 'experiments')!;

  test('@responsive E1: nested horizontal overflow the document-level probe cannot see', async ({ page, app }) => {
    await app.open(experiments);

    // The measured `/experiments` @ 375x812 geometry: `main.screen-main.pad`
    // held 476px of content in a 353px box with `overflow-x: auto`, while
    // `document.documentElement` reported 375 == 375.
    await page.evaluate(() => {
      const box = document.createElement('div');
      box.id = 'e2e-regression-e1';
      box.style.cssText = 'width: 353px; overflow-x: auto; overflow-y: hidden; height: 24px;';
      const wide = document.createElement('div');
      wide.style.cssText = 'width: 476px; height: 12px;';
      wide.textContent = 'nested overflow';
      box.appendChild(wide);
      document.querySelector('main')!.appendChild(box);
    });

    // THE BLIND SPOT, asserted directly: the document is still clean.
    const doc = await horizontalPageScroll(page);
    expect(
      doc.docScrollWidth,
      'the injected region is nested, so the DOCUMENT must stay clean — otherwise this ' +
        'regression case is not reproducing the blind spot at all'
    ).toBeLessThanOrEqual(doc.docClientWidth + 1);

    const report = await findOverflowingRegions(page, overflowMatchersFor('experiments'));
    const hit = report.offenders.find((o) => o.selector.includes('e2e-regression-e1'));
    expect(
      hit,
      `the nested-overflow probe missed a 476px-in-353px scroller; it reported:\n${renderOverflow(report.offenders)}`
    ).toBeTruthy();
    expect(hit!.kind).toBe('scroll');
    expect(hit!.scrollWidth).toBeGreaterThan(hit!.clientWidth + 1);
    // The culprit is named, because "screen-card overflows by 123px" is not a
    // fix address and "…because this 476px child does" is.
    expect(hit!.culprit, 'the probe must name the widest overflowing child').not.toBeNull();
  });

  test('@responsive T1: a zero-width ellipsis title is TOTAL content loss, not truncation', async ({ page, app }) => {
    await app.open(experiments);

    // The measured top-bar geometry: `span.record-title`, clientWidth 0,
    // scrollWidth 250, `overflow: hidden`, `text-overflow: ellipsis`. The old
    // probe missed it TWICE over: it skipped zero-width elements before looking
    // at them, and it exempted every `text-overflow: ellipsis` element
    // regardless of magnitude.
    await page.evaluate(() => {
      const row = document.createElement('div');
      row.id = 'e2e-regression-t1-row';
      row.style.cssText = 'display: flex; width: 120px; overflow: hidden;';
      const title = document.createElement('div');
      title.id = 'e2e-regression-t1';
      title.className = 'record-title';
      title.style.cssText =
        'flex: 0 1 0; width: 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
      title.textContent = 'XANES Example — CuO (Cu K-edge) · Partially answered';
      row.appendChild(title);
      document.querySelector('main')!.appendChild(row);
    });

    const geometry = await page.evaluate(() => {
      const el = document.getElementById('e2e-regression-t1')!;
      const st = getComputedStyle(el);
      return {
        rectWidth: el.getBoundingClientRect().width,
        scrollWidth: el.scrollWidth,
        textOverflow: st.textOverflow,
        overflowX: st.overflowX,
      };
    });
    // Prove the fixture really is the old geometry before asserting on it.
    expect(geometry.rectWidth, 'fixture must be zero-width, like the real record title').toBeLessThan(1);
    expect(geometry.scrollWidth, 'fixture must hold real content').toBeGreaterThan(100);
    expect(geometry.textOverflow, 'fixture must claim to be ellipsised — that is the exemption being tested').toBe(
      'ellipsis'
    );

    const clipped = await findClippedText(page);
    const hit = clipped.find((c) => c.selector.includes('e2e-regression-t1'));
    expect(
      hit,
      `the clipping probe missed 100% content loss on an ellipsised, zero-width CRITICAL label. ` +
        `Geometry: ${JSON.stringify(geometry)}. It reported:\n${render(clipped)}`
    ).toBeTruthy();
    // `.record-title` is in the critical-label set, so the stricter tier applies.
    expect(hit!.kind).toBe('critical-loss');

    // THE HAND-OFF, asserted rather than assumed. `findOverflowingRegions`
    // deliberately does not report single-line ellipsis containers (every one of
    // them overflows by definition) — it DEFERS them. That is only safe if the
    // magnitude question is genuinely answered elsewhere, so this checks the
    // same element appears on both sides of the hand-off.
    const overflow = await findOverflowingRegions(page, overflowMatchersFor('experiments'));
    expect(
      overflow.ellipsisDeferred.some((o) => o.selector.includes('e2e-regression-t1')),
      'the overflow probe must DEFER the ellipsis container (not drop it silently)'
    ).toBe(true);
    expect(
      overflow.offenders.some((o) => o.selector.includes('e2e-regression-t1')),
      'and must not double-report it as an overflow defect'
    ).toBe(false);
  });

  test('@responsive C1: a non-interactive label painted over is reported', async ({ page, app }) => {
    await app.open(experiments);

    // The measured top-bar geometry at 375: `span.record-surface` ran
    // 143.6 → 302.9 and `document.elementFromPoint` at five points across it
    // returned record-surface, record-surface, svg, mode-chip, mode-chip — i.e.
    // a non-interactive label genuinely painting over (and being painted over
    // by) the search button and the mode chip. The old probe's selector covered
    // interactive elements ONLY, so the label was outside its universe.
    await page.evaluate(() => {
      const label = document.createElement('span');
      label.id = 'e2e-regression-c1';
      label.className = 'record-surface';
      label.textContent = 'Cu K-edge · surface A';
      label.style.cssText =
        'position: fixed; left: 140px; top: 300px; width: 160px; height: 20px; z-index: 5; background: #fff;';
      const cover = document.createElement('span');
      cover.id = 'e2e-regression-c1-cover';
      cover.textContent = 'chip';
      cover.style.cssText =
        'position: fixed; left: 200px; top: 300px; width: 110px; height: 20px; z-index: 6; background: #eee;';
      document.body.appendChild(label);
      document.body.appendChild(cover);
    });

    const obscured = await findObscuredControls(page);
    const hit = obscured.find((o) => o.selector.includes('e2e-regression-c1') && !o.selector.includes('cover'));
    expect(
      hit,
      `the occlusion probe missed a CRITICAL NON-INTERACTIVE label covered across most of its box. ` +
        `It reported:\n${render(obscured)}`
    ).toBeTruthy();
    // `:label` records that the finding came from the label set, not from the
    // interactive set — so a reviewer can tell the two universes apart.
    expect(hit!.kind).toBe('covered:label');
  });

  test('@responsive I1: a 4.9px sliver of a 128px control is not "visible"', async ({ page, app }) => {
    await app.open(experiments);

    // The measured `/experiments` @ 375x812 geometry: the (since-removed) New
    // Record button ran
    // 359 → 487 in a 375px viewport — 4.9px of a ~128px button. The old probe
    // hit-tested the CENTRE OF THE VISIBLE INTERSECTION, so it tested a point
    // inside the 4.9px sliver, found the button there, and passed. Hit-testing
    // the centre of the INTENDED box returned `DIV.app`.
    await page.evaluate(() => {
      const btn = document.createElement('button');
      btn.id = 'e2e-regression-i1';
      btn.textContent = 'Open the Worked Example';
      const vw = document.documentElement.clientWidth;
      btn.style.cssText =
        `position: fixed; left: ${vw - 4.9}px; top: 320px; width: 128px; height: 30px; z-index: 5;`;
      document.body.appendChild(btn);
    });

    const geometry = await page.evaluate(() => {
      const el = document.getElementById('e2e-regression-i1')!;
      const r = el.getBoundingClientRect();
      const vw = document.documentElement.clientWidth;
      return {
        width: Math.round(r.width),
        visibleWidth: Math.round((Math.min(r.right, vw) - Math.max(r.left, 0)) * 10) / 10,
        // The point the OLD probe tested: the centre of the visible sliver.
        oldProbeHit:
          document.elementFromPoint(Math.max(r.left, 0) + (Math.min(r.right, vw) - Math.max(r.left, 0)) / 2, r.top + 15)
            ?.id ?? null,
      };
    });
    expect(geometry.width, 'fixture must be a full-size control').toBeGreaterThan(100);
    expect(geometry.visibleWidth, 'fixture must show only a sliver').toBeLessThan(6);
    // The falsification: the OLD probe's single hit-test point still finds the
    // button, which is exactly why it passed.
    expect(
      geometry.oldProbeHit,
      'the centre of the VISIBLE sliver still hits the button — this is the measurement that made the ' +
        'old probe report "ok", and it is why the visible-intersection centre alone is not enough'
    ).toBe('e2e-regression-i1');

    const obscured = await findObscuredControls(page);
    const hit = obscured.find((o) => o.selector.includes('e2e-regression-i1'));
    expect(
      hit,
      `the occlusion probe missed a control with ${geometry.visibleWidth}px of ${geometry.width}px visible. ` +
        `It reported:\n${render(obscured)}`
    ).toBeTruthy();
    expect(hit!.kind).toBe('unusable-sliver');
  });

  test('@responsive the hardened probes still tolerate what they always tolerated', async ({ page, app }) => {
    // A guard against over-correction: the three refinements that exist because
    // of REAL false positives must survive the hardening. If any of these starts
    // firing, the probes have become noise and someone will be tempted to
    // weaken them.
    await app.open(experiments);

    // (a) a deliberate `.scroll-x` container is allowlisted, not reported;
    // (b) an `.sr-only` accessible-name carrier is not "lost text";
    // (c) content inside a closed <details> is not measured at all;
    // (d) a container whose only overflowing child is a PARKED OFF-CANVAS panel
    //     (the Assistant drawer's real pattern: fixed, translated out, and
    //     `visibility: hidden`) is `contained`, not an offender.
    await page.evaluate(() => {
      const main = document.querySelector('main')!;

      const scroller = document.createElement('div');
      scroller.id = 'e2e-tolerance-scroll-x';
      scroller.className = 'scroll-x';
      scroller.style.cssText = 'width: 200px; height: 20px;';
      const wide = document.createElement('div');
      wide.style.cssText = 'width: 900px; height: 12px;';
      wide.textContent = 'deliberate horizontal data scroller';
      scroller.appendChild(wide);
      main.appendChild(scroller);

      const sr = document.createElement('span');
      sr.id = 'e2e-tolerance-sr-only';
      sr.className = 'sr-only';
      sr.textContent = 'an accessible name that is never meant to be painted';
      main.appendChild(sr);

      const det = document.createElement('details');
      det.id = 'e2e-tolerance-details';
      const sum = document.createElement('summary');
      sum.textContent = 'closed disclosure';
      const inner = document.createElement('div');
      inner.id = 'e2e-tolerance-details-inner';
      inner.style.cssText = 'width: 40px; overflow: hidden; white-space: nowrap;';
      inner.textContent = 'this text is inside a collapsed details element and is never painted';
      det.appendChild(sum);
      det.appendChild(inner);
      main.appendChild(det);

      const shell = document.createElement('div');
      shell.id = 'e2e-tolerance-parked';
      shell.style.cssText = 'position: relative; width: 200px; height: 40px; overflow: hidden;';
      const parked = document.createElement('div');
      parked.id = 'e2e-tolerance-parked-panel';
      parked.style.cssText =
        'position: absolute; top: 0; left: 0; width: 400px; height: 40px; ' +
        'transform: translateX(100%); visibility: hidden;';
      parked.textContent = 'off-canvas assistant drawer, parked and hidden';
      shell.appendChild(parked);
      main.appendChild(shell);
    });

    const overflow = await findOverflowingRegions(page, [
      ...overflowMatchersFor('evidence'), // brings ALLOW-SCROLL-X into scope
    ]);
    expect(
      overflow.allowed.some((o) => o.selector.includes('e2e-tolerance-scroll-x')),
      'a `.scroll-x` container must land in `allowed`, not in `offenders`'
    ).toBe(true);
    expect(overflow.offenders.some((o) => o.selector.includes('e2e-tolerance-scroll-x'))).toBe(false);
    expect(
      overflow.offenders.some((o) => o.selector.includes('e2e-tolerance-details')),
      'content inside a CLOSED <details> must not be measured — three wrong reports came from ignoring this'
    ).toBe(false);

    // The parked-panel rule, PROVED rather than asserted in a comment. Without
    // it, `div.screen-card` was reported on five record surfaces with the
    // hidden Assistant drawer named as the culprit — an overflow no user can
    // perceive, pointing at the wrong stylesheet.
    const parkedShell = overflow.contained.find((o) => o.selector.includes('e2e-tolerance-parked'));
    expect(
      parkedShell,
      `a container whose only overflowing child is hidden and parked off-canvas must land in ` +
        `\`contained\`; it reported:\n${renderOverflow(overflow.offenders)}`
    ).toBeTruthy();
    expect(parkedShell!.scrollWidth).toBeGreaterThan(parkedShell!.clientWidth + 1);
    expect(
      overflow.offenders.some((o) => o.selector.includes('e2e-tolerance-parked')),
      'and must NOT be an offender'
    ).toBe(false);

    const clipped = await findClippedText(page);
    expect(
      clipped.some((c) => c.selector.includes('e2e-tolerance-sr-only')),
      'an `.sr-only` carrier is doing its job, not losing content'
    ).toBe(false);
    expect(
      clipped.some((c) => c.selector.includes('e2e-tolerance-details')),
      'closed-disclosure content must not be reported as clipped'
    ).toBe(false);
  });
});

/**
 * ── THE `.sr-only` ESCAPE (F1) ──────────────────────────────────────────────
 *
 * A defect class the sweep above could not have found, because the surface it
 * shipped on is not in `../surfaces.ts` and CANNOT BE — see the catalogue note
 * at the bottom of this file.
 *
 * `.sr-only` (`src/styles/base.css`) is `position: absolute` with `left`/`top`
 * at `auto`, so it is laid out at its STATIC position and resolved against its
 * nearest positioned ancestor. `overflow` does not make an element a containing
 * block. So an accessible-name span inside a wide, horizontally-scrolling
 * container resolved against `body`, escaped the scroller, and contributed its
 * own right edge to the DOCUMENT's scrollable overflow — making the whole page
 * scroll sideways to a strip with nothing painted in it.
 *
 * MEASURED on Compare Runs, darwin, at 390 and 320: `documentElement`
 * scrollWidth 417 against a clientWidth of 390 (and of 320), while
 * `document.body.scrollWidth` matched the viewport exactly. Offender:
 * `td.rc-cell > a.rc-open > span.sr-only` at left 416 / right 417, with
 * `offsetParent: body`.
 *
 * Both cases below use the app's REAL classes against the app's REAL stylesheet,
 * so they fail if the `position: relative` on `.rc-tablewrap` is removed.
 */
test.describe('the .sr-only escape (F1)', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== HOST_PROJECT, `runs only in ${HOST_PROJECT}`);
  });

  const experiments = SURFACES.find((s) => s.id === 'experiments')!;

  test('@responsive S1: a real .rc-tablewrap does not let its accessible names escape', async ({ page, app }) => {
    await page.setViewportSize({ width: 320, height: 812 });
    await app.open(experiments);
    await page.setViewportSize({ width: 320, height: 812 });

    const before = await horizontalPageScroll(page);
    expect(
      before.docScrollWidth,
      'the page must be clean BEFORE the fixture is injected, or this case proves nothing'
    ).toBeLessThanOrEqual(before.docClientWidth + 1);

    // The real markup shape: `.rc-tablewrap` (overflow-x: auto) > a table wider
    // than the viewport > an `.sr-only` accessible name near its right edge, as
    // every `.rc-cell > .rc-open` carries.
    const geometry = await page.evaluate(() => {
      const wrap = document.createElement('div');
      wrap.id = 'e2e-regression-s1';
      wrap.className = 'rc-tablewrap';
      const table = document.createElement('table');
      table.className = 'rc-table';
      const row = table.insertRow();
      // The ADDRESS column, which is what makes the table 620px wide at these
      // viewports (`@media (max-width: 720px)` → `.rc-table { min-width: 620px }`).
      // It has to be here, and the link has to be in a LATER cell: the whole
      // defect is that the accessible name ends up to the RIGHT of the viewport.
      const addr = row.insertCell();
      addr.className = 'rc-cell rc-addr';
      addr.style.cssText = 'min-width: 560px;';
      addr.textContent = 'context.temperature_K';
      const cell = row.insertCell();
      cell.className = 'rc-cell';
      const link = document.createElement('a');
      link.className = 'rc-open';
      link.href = '#';
      link.textContent = 'Open';
      const sr = document.createElement('span');
      sr.className = 'sr-only';
      sr.textContent = ' Sweep Run B at context.temperature_K';
      link.appendChild(sr);
      cell.appendChild(link);
      row.appendChild(cell);
      wrap.appendChild(table);
      document.querySelector('main')!.appendChild(wrap);

      const st = getComputedStyle(wrap);
      const r = sr.getBoundingClientRect();
      return {
        wrapPosition: st.position,
        wrapOverflowX: st.overflowX,
        srOffsetParent: sr.offsetParent === document.body ? 'BODY' : (sr.offsetParent as HTMLElement | null)?.id ?? null,
        srRight: Math.round(r.right),
        tableScrolls: wrap.scrollWidth > wrap.clientWidth + 1,
      };
    });

    // Prove the FIXTURE is the real geometry before asserting on the outcome.
    expect(geometry.wrapOverflowX, '.rc-tablewrap must still be a scroller').toBe('auto');
    expect(geometry.tableScrolls, 'the table must be wider than the wrap, as it is at these widths').toBe(true);
    expect(
      geometry.srRight,
      'and the accessible name must sit beyond the viewport, which is the whole premise'
    ).toBeGreaterThan(320);

    // THE FIX, and the exact thing that was missing: `overflow` alone does not
    // establish a containing block, so without `position: relative` the span
    // resolves against `body`.
    expect(
      geometry.wrapPosition,
      '.rc-tablewrap must establish a containing block, or its absolutely-positioned ' +
        'accessible-name spans resolve against `body` and escape the scroller'
    ).toBe('relative');
    expect(
      geometry.srOffsetParent,
      'the span\'s offsetParent must be the wrap, not BODY — that difference IS the defect'
    ).toBe('e2e-regression-s1');

    const after = await horizontalPageScroll(page);
    expect(
      after.docScrollWidth,
      `the whole PAGE now scrolls sideways: ${after.docScrollWidth} > ${after.docClientWidth}. ` +
        `An .sr-only span (right edge ${geometry.srRight}) escaped a scroller whose own overflow ` +
        `is handled. Isolated proof of the mechanism, measured at 390 in one evaluate(): ` +
        `wrap \`static\` -> documentElement 662/390 with offsetParent BODY; ` +
        `wrap \`position: relative\` -> 390/390 with the wrap as offsetParent.`
    ).toBeLessThanOrEqual(after.docClientWidth + 1);
  });

  test('@responsive S2: no catalogued surface lets an .sr-only escape to the document', async ({ page, app }) => {
    /*
     * THE GENERAL GUARD, stated honestly: it passes today on every catalogued
     * surface and passed before the fix too, because the ONE surface that
     * exhibited the defect is not in the catalogue. It is here so the class
     * cannot come back on a surface that IS catalogued — the sweep's per-region
     * overflow probe never looked at where an absolutely-positioned element
     * resolves, so nothing else in this suite asks this question.
     */
    const escapes: string[] = [];
    for (const width of [390, 320]) {
      for (const surface of SURFACES) {
        await page.setViewportSize({ width, height: 812 });
        await app.open(surface);
        await page.setViewportSize({ width, height: 812 });
        const found = await page.evaluate(() => {
          const out: string[] = [];
          const vw = document.documentElement.clientWidth;
          for (const el of Array.from(document.querySelectorAll('.sr-only'))) {
            const e = el as HTMLElement;
            if (getComputedStyle(e).position !== 'absolute') continue;
            // The defect signature: the containing block is the initial one, so
            // the element's own box is part of the DOCUMENT's overflow.
            if (e.offsetParent !== document.body && e.offsetParent !== null) continue;
            const r = e.getBoundingClientRect();
            if (r.right <= vw + 1) continue;
            const owner = e.parentElement;
            const cls =
              owner && typeof owner.className === 'string' && owner.className.trim()
                ? '.' + owner.className.trim().split(/\s+/).slice(0, 2).join('.')
                : (owner?.tagName.toLowerCase() ?? '?');
            out.push(`${cls} > span.sr-only right ${Math.round(r.right)} > viewport ${vw}: "${(e.textContent ?? '').slice(0, 48)}"`);
          }
          return out;
        });
        for (const f of found) escapes.push(`${surface.id}@width-${width}: ${f}`);
      }
    }
    expect(
      escapes,
      `An \`.sr-only\` span resolved against \`body\` while sitting outside the viewport, so it is ` +
        `part of the DOCUMENT's horizontal overflow — the page scrolls sideways to an empty strip. ` +
        `The fix is \`position: relative\` on the nearest scrolling/clipping container, NOT hiding ` +
        `the span (it carries the only accessible name distinguishing one control from ` +
        `another):\n${escapes.join('\n')}`
    ).toEqual([]);
  });
});

/**
 * ── THE CATALOGUE GAP THAT LET F1 SHIP, and why it is still open ────────────
 *
 * `compare-runs` — `/record/<id>?compare=<runA>&compare=<runB>` — is NOT in
 * `../surfaces.ts`, and the sweep above only measures catalogued surfaces. That
 * is how a whole-page sideways scroll at 320 and 390 shipped past a suite that
 * already asserts exactly that at exactly those widths.
 *
 * IT CANNOT SIMPLY BE ADDED, and this test records the reason mechanically so
 * the next reader does not spend the measurement again. None of the five seeded
 * worked-example records has any runs — `GET /api/experiments/<id>/runs` returns
 * `{"runs": [], "total": 0}` for all of them — so the Compare Runs table never
 * mounts in this suite's read-only scope, and a catalogued entry would silently
 * measure the "no such run" state instead of the table. Making it reachable
 * means CREATING a run, which is a mutation, and mutations belong to
 * `playwright.mutation.config.ts` and its own workspace, never to this suite:
 * this one asserts canonical seed CONTENT across five parallel projects.
 *
 * So the geometry is pinned by S1 above (real classes, real stylesheet, injected
 * geometry) and the class is guarded by S2, while the SURFACE stays uncovered.
 */
test.describe('surface catalogue coverage', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== HOST_PROJECT, `runs only in ${HOST_PROJECT}`);
  });

  test('@responsive the Compare Runs table is still unreachable in the read-only scope', async ({ page, app }) => {
    const partial = SURFACES.find((s) => s.id === 'record-detail')!;
    await app.open(partial);
    // No run cards on a seeded example record, therefore no Focus / Compare
    // controls, therefore no `?compare=` table to catalogue. This is the
    // mechanical form of the prose above, so the note cannot rot into a claim
    // nobody re-checks.
    expect(
      await page.locator('.run-card-compare').count(),
      'If run cards now render on a seeded example record, Compare Runs has become reachable ' +
        'read-only and SHOULD be added to `../surfaces.ts` — plus `.run-card-focus` and ' +
        '`.run-card-compare` (measured 52x23 and 69.5x23) become measurable by the target-size ' +
        'probe, which currently cannot see them. Delete this test when that happens.'
    ).toBe(0);
  });
});

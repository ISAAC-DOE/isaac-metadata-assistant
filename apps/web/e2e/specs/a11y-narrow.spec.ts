/**
 * NARROW-WIDTH accessibility scan — axe-core at 390 and 320 CSS px.
 * @responsive
 *
 * ── The gap ─────────────────────────────────────────────────────────────────
 *
 * `specs/a11y-axe.spec.ts` runs once per Playwright project, and the projects are
 * 1280 / 1024 / 768 / 375 / 640@DPR2. The responsive brief named 390 and 320 as
 * required widths, and `specs/layout-widths.spec.ts` has measured LAYOUT at both
 * since it was written — but layout is not accessibility. Contrast, accessible
 * names, focus visibility and heading structure were never scanned below 375,
 * and 320 is where this app is most likely to fail them: it is the WCAG 1.4.10
 * reflow width, it is where text wraps hardest, and it is where controls crowd.
 *
 * This file closes that, at both widths, over every surface.
 *
 * ── Why widths inside one project, and not a sixth project ──────────────────
 *
 * The same trade `specs/layout-widths.spec.ts` made, for the same reason. A
 * sixth Playwright project multiplies EVERY `@responsive` spec — structure,
 * states, long-strings, layout-responsive, charts, tabs, the axe sweep — not
 * just the scan that wanted the width, and it perturbs the count ratchet in
 * `e2e/a11y-baseline.ts` for 26 surfaces in one go. This file adds 26 surfaces ×
 * 2 widths of axe scanning and nothing else, inside one project, by moving the
 * viewport itself with `page.setViewportSize`.
 *
 * The cost of that choice, stated rather than buried: DPR stays at the host
 * project's 1. That is the right call here — `color-contrast`, `button-name`,
 * `label` and `heading-order` are computed from CSS layout and the accessibility
 * tree, and `playwright.config.ts`'s header already proves DPR contributes
 * nothing to CSS layout. A DPR-sensitive defect at 320 would not be caught here,
 * and `zoom-200` is the project that carries the DPR-2 case.
 *
 * ── THE BASELINE NUMBERS ARE NOT IN YET, AND THAT IS DELIBERATE ─────────────
 *
 * `e2e/a11y-baseline.ts` records NO `width-320` or `width-390` pair. Every pair
 * therefore expects 0, so any violation at either width reads as `new` and FAILS
 * — and `auditScan`'s failure message prints the exact line to paste, naming
 * surface, width, rule, platform and count.
 *
 * That is a placeholder that fails loudly, chosen over a placeholder that lies.
 * The numbers MUST come from a **linux CI** run of this spec:
 *
 *   1. push the branch; read the `browser-a11y` job's output;
 *   2. for each `NEW …` line, add `'<surface>@width-<n>': <count>` to the named
 *      rule's `counts` in `e2e/a11y-baseline.ts`, with a note;
 *   3. re-run. A count that differs between macOS and linux becomes
 *      `{ darwin: n, linux: m }` — never a range, never a tolerance.
 *
 * DO NOT transcribe a macOS reading into a bare number. A bare number in that
 * file means "identical on both platforms", and this app ships no webfont: SF Pro
 * and the `ubuntu-latest` DejaVu/Liberation face wrap at different words, which is
 * why 10 of the existing 103 triples already hold two numbers. Ten of ten differ
 * by exactly ±1 — small enough to look like noise and large enough to turn CI
 * red on a number nobody measured. **CI (Linux) is the authority.**
 */

import {
  NARROW_WIDTHS,
  SCAN_PROJECT_IDS,
  applicableEntries,
  baselineKey,
  currentPlatform,
  narrowWidthId,
  platformCount,
} from '../a11y-baseline';
import { auditScan, scan } from '../helpers/axe';
import { expect, test } from '../fixtures';
import { SURFACES } from '../surfaces';

/**
 * The single project this file runs in.
 *
 * `@responsive` is the only tag that reaches more than one project and
 * `playwright.config.ts` maps tags, so the file is tagged for collection and then
 * skipped everywhere except here. The skipped entries are visible in the report,
 * which is the point: the restriction is stated, not hidden.
 *
 * `desktop-1280x800` rather than `mobile-375x812` on purpose — the phone project
 * also carries the `@interaction` specs, and hanging 52 axe scans off the same
 * project would lengthen the slowest one.
 */
const HOST_PROJECT = 'desktop-1280x800';

/** Tall enough that no surface is scanned mid-fold; the width is what is under test. */
const SWEEP_HEIGHT = 900;

test.describe('narrow-width a11y sweep', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(
      testInfo.project.name !== HOST_PROJECT,
      `runs only in ${HOST_PROJECT}; it moves the viewport itself rather than adding projects`
    );
  });

  for (const width of NARROW_WIDTHS) {
    const projectKey = narrowWidthId(width);

    for (const surface of SURFACES) {
      test(`@responsive a11y scan at ${width}px: ${surface.name}`, async ({
        page,
        app,
      }, testInfo) => {
        // BEFORE the surface opens, so the app lays out at the narrow width from
        // the first paint rather than reflowing into it. A component that only
        // measures on mount would otherwise be scanned in a state no reader gets.
        await page.setViewportSize({ width, height: SWEEP_HEIGHT });
        await app.open(surface);

        // Guard against the key vocabulary drifting away from the baseline file's.
        expect(
          SCAN_PROJECT_IDS,
          `"${projectKey}" is not in SCAN_PROJECT_IDS in e2e/a11y-baseline.ts, so no baseline ` +
            `key could ever name it and the well-formedness test could not validate one.`
        ).toContain(projectKey);

        // Which column of the baseline is in force. Throws, loudly and with an
        // explanation, on a platform nobody has measured — see `resolvePlatform`.
        const platform = currentPlatform();

        const results = await scan(page);
        const failures = auditScan(results, surface.id, projectKey, platform);

        const totalNodes = results.violations.reduce((n, v) => n + v.nodes.length, 0);
        const expectedTotal = applicableEntries(surface.id, projectKey, platform).reduce(
          (n, e) => n + platformCount(e.counts[baselineKey(surface.id, projectKey)], platform),
          0
        );
        testInfo.annotations.push({
          type: 'a11y-narrow',
          description:
            `${surface.id} @ ${projectKey} on ${platform}: ${results.violations.length} rule(s) ` +
            `firing, ${totalNodes} failing node(s) — baseline expects ${expectedTotal}; ` +
            `${results.passes.length} rule(s) passed.`,
        });

        expect(
          failures.map((f) => `${f.kind}:${f.rule}`),
          failures.length
            ? `Accessibility baseline mismatch on "${surface.name}" (${surface.path}) at ` +
                `${width}px against the "${platform}" column of e2e/a11y-baseline.ts.\n` +
                `\nTHIS WIDTH HAS NO RECORDED COUNTS YET. Every pair expects 0, so a real, ` +
                `pre-existing defect at ${width}px reads as NEW. Transcribe the numbers from a ` +
                `linux CI run — see this file's header — and never from a macOS run.\n` +
                (platform === 'darwin'
                  ? `NOTE: you are on darwin. CI runs on linux and is the authority; the counts ` +
                    `below are NOT the numbers to commit.\n`
                  : '') +
                `\n` +
                failures.map((f) => f.message).join('\n\n')
            : undefined
        ).toEqual([]);
      });
    }
  }
});

/**
 * The sweep's own shape, checked without a browser.
 *
 * Cheap, and it catches the two ways this file could quietly stop testing what it
 * claims: a width list that no longer contains 320, and a key namespace that has
 * drifted apart from `e2e/a11y-baseline.ts`.
 */
test('@responsive narrow a11y sweep covers 320 and namespaces its keys', async () => {
  // 320 is the WCAG 1.4.10 reflow width and the narrowest the product claims to
  // support. It is not optional; 390 is the modern phone width beside it.
  expect(NARROW_WIDTHS).toContain(320);
  expect(NARROW_WIDTHS).toContain(390);

  for (const width of NARROW_WIDTHS) {
    const id = narrowWidthId(width);
    expect(id).toBe(`width-${width}`);
    expect(SCAN_PROJECT_IDS).toContain(id);
    // The namespace must NOT collide with a real Playwright project: `width-390`
    // and `mobile-375x812` are 15 CSS px apart, and a shared key would let a
    // defect recorded at one silently excuse the other.
    expect(id).not.toMatch(/^(desktop|laptop|tablet|mobile|zoom)/);
  }

  expect(SURFACES.length, 'the sweep must cover every surface').toBeGreaterThan(20);
});

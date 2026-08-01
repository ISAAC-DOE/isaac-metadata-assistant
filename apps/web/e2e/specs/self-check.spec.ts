/**
 * Meta-tests: prove the probes can actually FAIL.
 * @interaction
 *
 * A probe that returns `[]` because it is broken looks exactly like a probe
 * that returns `[]` because the page is fine. These tests inject a known defect
 * into the live page and assert the probe reports it — so a green
 * `layout-responsive.spec.ts` / `a11y-axe.spec.ts` / `keyboard.spec.ts` means
 * something.
 *
 * Coverage, and its honest edges. Self-checked here:
 *
 *   * horizontal page scroll               (`helpers/layout.ts`)
 *   * clipped text                         (`helpers/layout.ts`)
 *   * occluded controls                    (`helpers/layout.ts`)
 *   * focus indicator, missing              (`helpers/focus.ts`)
 *   * focus indicator, faked by a RESTING box-shadow — the case the first
 *     version of the probe passed                       (`helpers/focus.ts`)
 *   * focus indicator, genuinely present — a positive control, so the probe is
 *     not vacuously reporting "no ring" for everything  (`helpers/focus.ts`)
 *   * a11y baseline: a rule firing on a surface it was never recorded on
 *   * a11y baseline: one EXTRA node of a rule that IS recorded here
 *   * a11y baseline: the same node count with a NEW foreground colour
 *   * a11y baseline: the PLATFORM column actually in force — that it is this
 *     machine's, that tampering with it turns the audit red, and that
 *     tampering with the OTHER platform's column does not
 *
 * NOT self-checked, and listed so the gap is visible rather than implied: the
 * heading-hierarchy and colour-only-status probes in `structure.spec.ts`, and
 * the zoom emulation assertions (which are themselves falsifiable by
 * construction — see `specs/zoom-200.spec.ts`).
 *
 * All mutations are browser-side only; nothing is written to the backend.
 */

import {
  BASELINE_PLATFORMS,
  baselineEntryFor,
  baselineKey,
  currentPlatform,
  expectedNodeCount,
  resolvePlatform,
  verdictForCounts,
  type BaselinePlatform,
  type PlatformCount,
} from '../a11y-baseline';
import { expect, test } from '../fixtures';
import { activeElementFocusInfo } from '../helpers/focus';
import { auditScan, scan } from '../helpers/axe';
import { findClippedText, findObscuredControls, horizontalPageScroll } from '../helpers/layout';
import { SURFACES } from '../surfaces';

const experiments = SURFACES.find((s) => s.id === 'experiments')!;

test('@interaction the horizontal-scroll probe detects an injected overflow', async ({ page, app }) => {
  await app.open(experiments);
  const clean = await horizontalPageScroll(page);
  expect(clean.docScrollWidth).toBeLessThanOrEqual(clean.docClientWidth + 1);

  await page.evaluate(() => {
    const d = document.createElement('div');
    d.id = 'e2e-self-check-overflow';
    d.style.cssText = 'width: 4000px; height: 10px; background: red;';
    document.body.appendChild(d);
  });
  const dirty = await horizontalPageScroll(page);
  expect(dirty.docScrollWidth, 'the probe failed to notice a 4000px-wide element').toBeGreaterThan(
    dirty.docClientWidth + 1
  );
});

test('@interaction the clipping probe detects injected clipped text', async ({ page, app }) => {
  await app.open(experiments);
  expect(await findClippedText(page, 'main')).toEqual([]);

  await page.evaluate(() => {
    const box = document.createElement('div');
    box.id = 'e2e-self-check-clip';
    box.style.cssText = 'width: 40px; height: 20px; overflow: hidden; position: relative;';
    const inner = document.createElement('span');
    inner.style.cssText = 'display: block; width: 600px; white-space: nowrap;';
    inner.textContent = 'this text is cut off and unreachable by the user';
    box.appendChild(inner);
    document.querySelector('main')!.appendChild(box);
  });

  const clipped = await findClippedText(page, 'main');
  expect(
    clipped.some((c) => c.text.includes('this text is cut off')),
    `the clipping probe missed an injected clip; it reported ${JSON.stringify(clipped)}`
  ).toBe(true);
});

test('@interaction the occlusion probe detects a control covered by an overlay', async ({ page, app }) => {
  await app.open(experiments);
  expect(await findObscuredControls(page)).toEqual([]);

  await page.evaluate(() => {
    const btn = document.querySelector<HTMLElement>('button.topbar-search');
    if (!btn) throw new Error('no search trigger to cover');
    const r = btn.getBoundingClientRect();
    const veil = document.createElement('div');
    veil.id = 'e2e-self-check-veil';
    veil.style.cssText = `position: fixed; left: ${r.left}px; top: ${r.top}px; width: ${r.width}px; height: ${r.height}px; background: rgba(255,0,0,.3); z-index: 99999;`;
    document.body.appendChild(veil);
  });

  const obscured = await findObscuredControls(page);
  expect(
    obscured.some((o) => o.selector.includes('topbar-search')),
    `the occlusion probe missed a control fully covered by an overlay; it reported ${JSON.stringify(obscured)}`
  ).toBe(true);
});

test('@interaction the focus-indicator probe reports a control with no ring', async ({ page, app }) => {
  await app.open(experiments);

  // Inject a focusable control that explicitly suppresses every focus
  // affordance, place it FIRST in the tab order, and Tab onto it.
  await page.evaluate(() => {
    const btn = document.createElement('button');
    btn.id = 'e2e-self-check-noring';
    btn.textContent = 'no ring';
    btn.setAttribute('style', 'outline: none !important; box-shadow: none !important; position: fixed; top: 0; left: 0;');
    document.body.insertBefore(btn, document.body.firstChild);
    (document.activeElement as HTMLElement | null)?.blur();
  });

  await page.keyboard.press('Tab');
  const info = await activeElementFocusInfo(page);
  expect(info?.key, 'expected the injected button to be the first tab stop').toContain('e2e-self-check-noring');
  expect(
    info?.visible,
    `the focus probe called a ring-less control "visible" (outline: ${info?.outline}; box-shadow: ${info?.boxShadow})`
  ).toBe(false);
});

/**
 * THE regression this probe was rewritten for.
 *
 * `ringPainted = boxShadow !== 'none'` treated any shadow as a focus ring. This
 * control has a permanent resting shadow and NO focus outline — the old check
 * called it visible; the difference-based check must not.
 */
test('@interaction the focus probe is not fooled by a RESTING box-shadow', async ({ page, app }) => {
  await app.open(experiments);

  await page.evaluate(() => {
    const style = document.createElement('style');
    style.id = 'e2e-self-check-shadow-style';
    style.textContent = `
      #e2e-self-check-restingshadow {
        position: fixed; top: 0; left: 0;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4) !important;
      }
      #e2e-self-check-restingshadow:focus,
      #e2e-self-check-restingshadow:focus-visible { outline: none !important; }
      #e2e-self-check-realring { position: fixed; top: 0; left: 120px; }
    `;
    document.head.appendChild(style);

    const faked = document.createElement('button');
    faked.id = 'e2e-self-check-restingshadow';
    faked.textContent = 'resting shadow, no ring';

    const real = document.createElement('button');
    real.id = 'e2e-self-check-realring';
    real.textContent = 'real ring';

    document.body.insertBefore(real, document.body.firstChild);
    document.body.insertBefore(faked, document.body.firstChild);
    (document.activeElement as HTMLElement | null)?.blur();
  });

  // The OLD heuristic's input: there really is a painted shadow here, so
  // `boxShadow !== 'none'` really would have passed this control.
  const restingShadow = await page.evaluate(
    () => getComputedStyle(document.querySelector('#e2e-self-check-restingshadow')!).boxShadow
  );
  expect(restingShadow, 'the fixture must actually paint a resting shadow, or it proves nothing').not.toBe('none');

  await page.keyboard.press('Tab');
  const faked = await activeElementFocusInfo(page);
  expect(faked?.key, 'expected the resting-shadow button to be the first tab stop').toContain(
    'e2e-self-check-restingshadow'
  );
  expect(faked?.restingMeasured, 'the resting reading must have been taken for this to mean anything').toBe(true);
  expect(
    faked?.visible,
    `the focus probe accepted a resting box-shadow as a focus ring (outline: ${faked?.outline}; ` +
      `box-shadow: ${faked?.boxShadow}; indicators: ${JSON.stringify(faked?.indicators)})`
  ).toBe(false);
  expect(faked?.indicators, 'nothing perceptible about this control changes on focus').toEqual([]);
  // The raw diff is NOT empty — the app's global rule still applies
  // `outline-offset: 2px` even though `outline: none` paints nothing. Asserted
  // so the distinction between "changed" and "perceptible" stays honest.
  expect(faked?.changed, 'the outline-offset diff that paints nothing').toEqual(['outlineOffset']);

  // POSITIVE CONTROL: the very next tab stop has the app's real
  // `:focus-visible` outline, and must be reported as visible — otherwise the
  // probe is just failing everything.
  await page.keyboard.press('Tab');
  const real = await activeElementFocusInfo(page);
  expect(real?.key).toContain('e2e-self-check-realring');
  expect(
    real?.visible,
    `the probe missed the app's own :focus-visible ring (outline: ${real?.outline}; indicators: ${JSON.stringify(
      real?.indicators
    )})`
  ).toBe(true);
  expect(real?.indicators, 'the ring comes from the outline').toContain('outline');
});

/* ────────────────────────────────────────────────────────────────────────────
 * a11y BASELINE self-checks.
 *
 * `a11y-baseline.ts` is the piece of this suite most able to fail silently: it
 * decides what is allowed to be broken. Its first version exempted an entire
 * rule while stating three times that it never did, and every test passed. The
 * three tests below inject each way it could go wrong.
 * ──────────────────────────────────────────────────────────────────────────── */

test('@interaction the a11y baseline reports a rule firing where it was never recorded', async ({
  page,
  app,
}, testInfo) => {
  await app.open(experiments);
  const project = testInfo.project.name;

  // Precondition: clean page, clean audit. Without this the test could "pass"
  // on a page that was already failing.
  expect(auditScan(await scan(page), experiments.id, project), 'the unmodified surface must audit clean').toEqual([]);

  // `aria-allowed-attr` used to be a recorded defect on the Evidence trail
  // (FINDING A11Y-03). It is fixed, so it is now baselined NOWHERE and every
  // surface expects 0 — which is exactly the condition this proof needs.
  // Reproduce the old defect verbatim on My Experiments.
  expect(expectedNodeCount('aria-allowed-attr', experiments.id, project)).toBe(0);
  await page.evaluate(() => {
    const b = document.createElement('button');
    b.id = 'e2e-self-check-aria';
    b.setAttribute('role', 'listitem');
    b.setAttribute('aria-pressed', 'true');
    b.textContent = 'not allowed here';
    document.querySelector('main')!.appendChild(b);
  });

  const failures = auditScan(await scan(page), experiments.id, project);
  const aria = failures.filter((f) => f.rule === 'aria-allowed-attr');
  expect(
    aria.map((f) => f.kind),
    `a rule baselined ONLY on Evidence fired on My Experiments and the audit did not report it. ` +
      `Audit returned: ${JSON.stringify(failures.map((f) => `${f.kind}:${f.rule}`))}`
  ).toContain('new');
  expect(aria[0]?.expected).toBe(0);
  expect(aria[0]?.actual).toBeGreaterThan(0);
});

test('@interaction the a11y baseline reports ONE extra node of a rule it does allow here', async ({
  page,
  app,
}, testInfo) => {
  await app.open(experiments);
  const project = testInfo.project.name;

  expect(auditScan(await scan(page), experiments.id, project), 'the unmodified surface must audit clean').toEqual([]);

  // Colour contrast IS a recorded defect on this surface, with an exact count.
  const expectedContrast = expectedNodeCount('color-contrast', experiments.id, project);
  expect(expectedContrast, 'this proof needs colour-contrast to be baselined here').toBeGreaterThan(0);

  await page.evaluate(() => {
    const p = document.createElement('p');
    p.id = 'e2e-self-check-contrast';
    p.textContent = 'one more low-contrast node';
    p.style.cssText =
      'position: fixed; left: 4px; bottom: 4px; z-index: 99999; background: #ffffff; color: #d8dde3; font-size: 12px;';
    document.body.appendChild(p);
  });

  const failures = auditScan(await scan(page), experiments.id, project);
  const contrast = failures.find((f) => f.rule === 'color-contrast');
  expect(
    contrast?.kind,
    `${expectedContrast} baselined contrast nodes became ${expectedContrast + 1} and the audit stayed green. ` +
      `That is the exact hole per-instance counting exists to close. ` +
      `Audit returned: ${JSON.stringify(failures.map((f) => `${f.kind}:${f.rule}`))}`
  ).toBe('grew');
  expect(contrast?.expected).toBe(expectedContrast);
  expect(contrast?.actual).toBe(expectedContrast + 1);
});

test('@interaction the a11y baseline reports a NEW foreground colour at an unchanged node count', async ({
  page,
  app,
}, testInfo) => {
  await app.open(experiments);
  const project = testInfo.project.name;

  const clean = await scan(page);
  expect(auditScan(clean, experiments.id, project), 'the unmodified surface must audit clean').toEqual([]);

  // Recolour an element that ALREADY fails contrast to a colour the baseline
  // has never recorded. The node count is unmoved; only the token changes.
  const victim = clean.violations.find((v) => v.id === 'color-contrast')?.nodes[0]?.target[0];
  expect(typeof victim, 'expected at least one baselined contrast node to recolour').toBe('string');
  await page.evaluate((sel) => {
    const el = document.querySelector<HTMLElement>(sel);
    if (!el) throw new Error(`self-check target vanished: ${sel}`);
    el.style.setProperty('color', '#d8dde3', 'important');
    el.style.setProperty('background-color', '#ffffff', 'important');
  }, victim as string);

  const failures = auditScan(await scan(page), experiments.id, project);
  const contrast = failures.filter((f) => f.rule === 'color-contrast');
  expect(
    contrast.map((f) => f.kind),
    `an unrecorded foreground colour appeared with the node count unchanged and the audit stayed green. ` +
      `Audit returned: ${JSON.stringify(failures.map((f) => `${f.kind}:${f.rule}`))}`
  ).toContain('new-foreground');
});

/* ────────────────────────────────────────────────────────────────────────────
 * PLATFORM RESOLUTION self-checks.
 *
 * Ten a11y counts and two layout clips are recorded per platform, because the
 * app ships no webfont and text wraps differently under SF Pro and under the
 * Linux system face. That mechanism has exactly the same silent-failure shape
 * as the wildcard it replaced: if resolution picked the wrong column, or
 * always picked the same one, or quietly tolerated either number, every test
 * would still be green on ONE of the two platforms and nobody would know which
 * one was being enforced. The two tests below make it observable.
 * ──────────────────────────────────────────────────────────────────────────── */

test('@interaction platform resolution is this machine\'s, is exact, and refuses an unmeasured platform', async () => {
  // 1. The resolver maps each recorded platform to itself, and REFUSES anything
  //    else rather than defaulting. A Windows contributor must get this message,
  //    not a green run measured against somebody else's font.
  expect(resolvePlatform('darwin')).toBe('darwin');
  expect(resolvePlatform('linux')).toBe('linux');
  for (const unmeasured of ['win32', 'freebsd', 'android', '']) {
    expect(
      () => resolvePlatform(unmeasured),
      `resolvePlatform("${unmeasured}") must throw. Silently falling back to darwin or linux would ` +
        `produce a suite that is green because it is comparing against the wrong font metrics.`
    ).toThrow(/no measured numbers for platform/);
  }
  expect(() => resolvePlatform('win32')).toThrow(/win32/);

  // 2. The column in force is THIS process's. Both recorded names are spelled
  //    exactly as `process.platform` reports them, so this is a direct identity
  //    check rather than a mapping the test could get wrong in the same way the
  //    implementation might.
  expect(BASELINE_PLATFORMS as readonly string[]).toContain(currentPlatform());
  expect(
    currentPlatform(),
    `the enforced baseline column must be this machine's; process.platform is "${process.platform}"`
  ).toBe(process.platform);

  // 3. The default argument really does resolve to the current platform, proved
  //    on a triple whose two columns DIFFER — on a triple where they agree the
  //    assertion would pass under a broken resolver too.
  const platform = currentPlatform();
  const other = BASELINE_PLATFORMS.find((p) => p !== platform)!;
  const differing = { rule: 'color-contrast', surface: 'validator', project: 'zoom-200' } as const;
  const mine = expectedNodeCount(differing.rule, differing.surface, differing.project, platform);
  const theirs = expectedNodeCount(differing.rule, differing.surface, differing.project, other);
  expect(
    mine !== theirs,
    `this proof needs ${differing.surface}@${differing.project} to differ between platforms; ` +
      `it currently reads ${mine} on both. Pick another differing triple, or — if the font gap ` +
      `has genuinely closed — collapse the entry to a bare number.`
  ).toBe(true);
  expect(expectedNodeCount(differing.rule, differing.surface, differing.project)).toBe(mine);
  expect(expectedNodeCount(differing.rule, differing.surface, differing.project)).not.toBe(theirs);

  // 4. NO TOLERANCE. The other platform's number is one away from this one, and
  //    one away must still be red. This is the assertion that would fail if
  //    somebody "fixed" CI by allowing a range.
  expect(
    verdictForCounts(mine, theirs),
    `the two platform columns differ by ${Math.abs(mine - theirs)} node(s) and the ratchet called ` +
      `that "ok". A range or a tolerance re-opens exactly the hole per-instance counting closed.`
  ).not.toBe('ok');
});

test('@interaction tampering with THIS platform\'s count fails the audit; tampering with the other does not', async ({
  page,
  app,
}, testInfo) => {
  await app.open(experiments);
  const project = testInfo.project.name;
  const platform = currentPlatform();
  const other = BASELINE_PLATFORMS.find((p) => p !== platform)!;

  // Repeated from the test above on purpose. `experiments` has the SAME count
  // on both platforms — that is what makes it a clean tampering fixture — but
  // it also means everything below would pass unchanged if resolution were
  // hard-wired to the wrong column. Verified by sabotage: replacing
  // `resolvePlatform(process.platform)` with `resolvePlatform('linux')` left
  // this test green until this line was added.
  expect(platform, `the tampering below only proves anything if the column is this machine's`).toBe(process.platform);

  // One scan, reused for all three verdicts: the page is not touched between
  // them, only the baseline is. That keeps the test to a single axe run and
  // makes it unambiguous that the DIFFERENCE comes from the baseline edit.
  const results = await scan(page);
  expect(auditScan(results, experiments.id, project), 'the unmodified surface must audit clean').toEqual([]);

  const entry = baselineEntryFor('color-contrast')!;
  const key = baselineKey(experiments.id, project);
  const recorded = expectedNodeCount('color-contrast', experiments.id, project, platform);
  expect(recorded, 'this proof needs colour-contrast to be baselined here').toBeGreaterThan(0);

  // Written as a per-platform pair with the CURRENT platform's slot named
  // dynamically, so the test reads the same on macOS and on Linux.
  const pair = (forThisPlatform: number, forTheOther: number): PlatformCount =>
    ({ [platform]: forThisPlatform, [other]: forTheOther } as Record<BaselinePlatform, number>);

  // `counts` is `readonly` to TypeScript only. Mutating it is safe here: each
  // Playwright worker is its own process with its own module instance and runs
  // one test at a time, and the original is restored in `finally`.
  const counts = entry.counts as Record<string, PlatformCount>;
  const original = counts[key];

  try {
    // (a) Corrupt the OTHER platform's number badly. Nothing may change —
    //     otherwise the resolution is not selecting a column at all.
    counts[key] = pair(recorded, recorded + 7);
    expect(expectedNodeCount('color-contrast', experiments.id, project, other)).toBe(recorded + 7);
    expect(
      auditScan(results, experiments.id, project),
      `a wrong number in the "${other}" column changed the verdict on "${platform}". The columns ` +
        `must be independent: CI's numbers must not be able to fail a developer's machine, and a ` +
        `developer's must not be able to pass CI.`
    ).toEqual([]);

    // (b) Corrupt THIS platform's number. The audit MUST go red — and must say
    //     `improved`, because the baseline now claims more failing nodes than
    //     the page actually has.
    counts[key] = pair(recorded + 7, recorded);
    const failures = auditScan(results, experiments.id, project);
    const contrast = failures.find((f) => f.rule === 'color-contrast');
    expect(
      contrast?.kind,
      `the "${platform}" count was moved from ${recorded} to ${recorded + 7} and the audit stayed ` +
        `green. The enforced column is then not the one this machine runs on, and every count in ` +
        `e2e/a11y-baseline.ts is decorative. Audit returned: ` +
        `${JSON.stringify(failures.map((f) => `${f.kind}:${f.rule}`))}`
    ).toBe('improved');
    expect(contrast?.expected).toBe(recorded + 7);
    expect(contrast?.actual).toBe(recorded);
    expect(contrast?.platform, 'the failure must name the column it was judged against').toBe(platform);
    expect(contrast?.message, 'and the message must name it too, or the number is unactionable').toContain(platform);
  } finally {
    counts[key] = original;
  }

  // Restored, and green again — so a failure above cannot be an artefact left
  // behind for the next test in this worker.
  expect(expectedNodeCount('color-contrast', experiments.id, project, platform)).toBe(recorded);
  expect(auditScan(results, experiments.id, project), 'the baseline must be restored').toEqual([]);
});

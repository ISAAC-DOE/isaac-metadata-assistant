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
 *
 * NOT self-checked, and listed so the gap is visible rather than implied: the
 * heading-hierarchy and colour-only-status probes in `structure.spec.ts`, and
 * the zoom emulation assertions (which are themselves falsifiable by
 * construction — see `specs/zoom-200.spec.ts`).
 *
 * All mutations are browser-side only; nothing is written to the backend.
 */

import { expectedNodeCount } from '../a11y-baseline';
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

  // `aria-allowed-attr` is a recorded defect on the Evidence trail — and
  // nowhere else. Reproduce that exact defect on My Experiments.
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

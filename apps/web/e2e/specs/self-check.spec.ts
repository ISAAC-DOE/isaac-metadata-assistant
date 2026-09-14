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
import { SURFACES, type Surface } from '../surfaces';

const experiments = SURFACES.find((s) => s.id === 'experiments')!;

/**
 * THE SURFACE THE a11y-BASELINE PROOFS USE, and why it is no longer `experiments`.
 *
 * Three of the proofs below need a surface where `color-contrast` IS baselined with a
 * count > 0 — that is the whole fixture: they add a node, or recolour one, and assert
 * the ratchet notices. `experiments` was that surface until 2026-09-01, when the A3
 * neutral-ink palette took it (and twelve other whole surfaces) to ZERO and its pairs
 * were DELETED from `a11y-baseline.ts`. Each proof's own message said what to do —
 * "this proof needs colour-contrast to be baselined here" — and this is doing it.
 *
 * ~~`experiments-example` is the same screen with the worked-example records in it …
 * it holds 3 nodes at every viewport.~~ — **MOVED AGAIN, 2026-09-13, and this is the
 * SECOND time this constant has migrated for the reason it predicted.** The note above
 * says "if a future fix empties it too, the same message will fire and the same
 * substitution is the answer". A future fix did not empty it; it did something the
 * note did not anticipate — it made the cell a **PLATFORM SPLIT**.
 *
 * ── WHAT HAPPENED, AND WHY A SPLIT BREAKS THE FIXTURE SPECIFICALLY ──────────
 *
 * The Experiment Library added three spans to the queue row. On **linux** those
 * three FAILED contrast (3 -> 6, caught by CI); on **darwin** they PASSED (3 -> 3).
 * The fix raised the dimmed row's text a tier, and darwin then fell to 2 while
 * linux is still to be measured — so `experiments-example` is now
 * `{ darwin: 2, linux: 3 }`.
 *
 * Two of the proofs below **require a SCALAR** and said so in their own failure
 * messages, which is how this was found rather than guessed:
 *
 *   · the platform-resolution proof injects a `{ thisPlatform: n, other: n + 1 }`
 *     pair built from the cell's own measured `n` — it cannot build one from a cell
 *     that is already a pair. Its message: *"this proof needs
 *     experiments-example@desktop-1280x800 to be a recorded SCALAR to build a split
 *     from; it reads {"darwin":2,"linux":3}."*
 *   · the tampering proof states the requirement directly: the fixture must have
 *     "the SAME count on both platforms — that is what makes it a clean tampering
 *     fixture".
 *
 * ── AND THE NEW-FOREGROUND PROOF NEEDED A BIGGER SURFACE, NOT JUST A SCALAR ──
 *
 * It recolours a node that ALREADY fails and asserts the count is unmoved. On a
 * 2-node surface it instead returned **`improved`** — the audit short-circuits on a
 * count change and never reaches the `foregrounds` check (a `continue` right after
 * the `IMPROVED` push), so one node's fate dominated the whole proof. A surface with
 * many failing nodes makes the injection's effect on the count negligible, which is
 * what the proof assumes.
 *
 * ~~`record-detail` is the substitution: 25 nodes, scalar at every viewport …~~ —
 * **TRIED AND REVERTED THE SAME DAY, MEASURED.** `record-detail` is baselined at 25
 * and reported **ZERO** in this fixture: `FIXED? record-detail @ desktop-1280x800 …
 * is baselined at 25 node(s) here on darwin but did not fire at all`. It is
 * `scope: 'example'` at `recordSub(SEED.partial)` — a specific seeded RECORD — and
 * this file's fixture does not bring that record's failing content up, whereas the
 * same surface reports 25 under `a11y-axe.spec.ts`. **A surface's baselined count is
 * a property of the SUITE THAT MEASURED IT, not of the surface**, and borrowing a
 * cell across suites is how you get a proof that audits "clean" against a number
 * nothing produced. Recorded so the third migration does not repeat the second.
 *
 * So the surface stays `experiments-example`, which does open correctly here, and the
 * two genuine fixture requirements the split broke are fixed where they belong —
 * at the two proofs that have them, not by moving everyone. `experiments` stays the
 * fixture for the layout, focus and never-recorded-rule proofs, none of which needs a
 * non-zero count.
 *
 * **ONE CLAIM BELOW IS CORRECTED BY THIS, and it was already false before today:**
 * the tampering proof says "since 2026-09-01 EVERY cell in the file" has the same
 * count on both platforms. `settings-explorer@mobile-375x812` has been
 * `{ darwin: 20, linux: 21 }` since well before this change, so that sentence was
 * stale independently of it.
 */
/*
 * *** NO LONGER HARDCODED, AND THE REASON IS THAT HARDCODING IT BROKE CI. ***
 *
 * This was `experiments-example`. Closing A11Y-01 cause (b) took that surface's
 * `color-contrast` count to ZERO, and the two proofs below need a surface where
 * the rule IS baselined with a non-zero count — so they failed with
 * *"this proof needs colour-contrast to be baselined here"*. Nothing was wrong
 * with the fix or with the baseline; the FIXTURE had been pinned to a defect
 * that got repaired.
 *
 * That is the same hazard `baseline-aggregate.invariant.test.ts` names on its
 * own floor: **a proof that depends on a recorded defect is on a collision
 * course with fixing it.** Choosing the surface at RUN TIME removes the hazard
 * instead of deferring it by one surface — the next contrast fix moves the
 * fixture along rather than turning CI red.
 *
 * Chosen per PROJECT, because a count can be non-zero at one viewport and zero
 * at another. Declaration order, so the choice is deterministic and a failure
 * names the same surface on a re-run.
 */
function pickContrastBaselined(project: string): Surface {
  const surface = SURFACES.find((s) => expectedNodeCount('color-contrast', s.id, project) > 0);
  if (surface === undefined) {
    throw new Error(
      `no surface carries a non-zero color-contrast baseline at ${project}, so the two ` +
        'self-check proofs that inject an extra contrast node have nothing to inject into. ' +
        'That is a GOOD problem — it means the contrast debt is gone. Rewrite those two ' +
        'proofs against a rule that is still baselined somewhere, or against a surface ' +
        'this spec creates itself; do NOT re-introduce a defect to keep them running.'
    );
  }
  return surface;
}

/**
 * THE SURFACE THE **NEW-FOREGROUND** PROOF USES, and why it needs its own.
 *
 * That proof recolours a node which already fails and asserts the node COUNT is
 * unmoved — so it needs a failing node that is **not under an ancestor
 * `opacity`**. A translucent victim makes it vacuous: forcing an opaque
 * `background-color` on one stops axe resolving the composite, the node leaves
 * `violations`, the count MOVES, and `auditScan` short-circuits on the count
 * change before it ever reaches the `foregrounds` check.
 *
 * **MEASURED 2026-09-13: `experiments-example` has no such node left.** After the
 * Experiment Library contrast fix its two remaining failures are BOTH inside
 * `.exp-row.done` (`opacity: 0.82`), and the victim filter says so out loud rather
 * than picking one and proving nothing — which is how this was found.
 *
 * `settings-explorer` is the substitution: `scope: 'ordinary'` (so it renders in
 * this fixture, unlike the `record-detail` attempt — see the note on
 * `contrastBaselined`), and **17 baselined nodes at desktop / 20 at mobile**,
 * which both makes an opacity-free victim likely and makes any single node's fate
 * negligible to the count. A SPLIT is fine here: only the platform-resolution
 * proof needs a scalar, and `expectedNodeCount` resolves a pair per platform.
 */
const newForegroundSurface = SURFACES.find((s) => s.id === 'settings-explorer')!;

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
  const project = testInfo.project.name;
  const contrastBaselined = pickContrastBaselined(project);
  await app.open(contrastBaselined);

  expect(auditScan(await scan(page), contrastBaselined.id, project), 'the unmodified surface must audit clean').toEqual([]);

  // Colour contrast IS a recorded defect on this surface, with an exact count.
  const expectedContrast = expectedNodeCount('color-contrast', contrastBaselined.id, project);
  expect(expectedContrast, 'this proof needs colour-contrast to be baselined here').toBeGreaterThan(0);

  await page.evaluate(() => {
    const p = document.createElement('p');
    p.id = 'e2e-self-check-contrast';
    p.textContent = 'one more low-contrast node';
    p.style.cssText =
      'position: fixed; left: 4px; bottom: 4px; z-index: 99999; background: #ffffff; color: #d8dde3; font-size: 12px;';
    document.body.appendChild(p);
  });

  const failures = auditScan(await scan(page), contrastBaselined.id, project);
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
  await app.open(newForegroundSurface);
  const project = testInfo.project.name;

  const clean = await scan(page);
  expect(
    auditScan(clean, newForegroundSurface.id, project),
    'the unmodified surface must audit clean'
  ).toEqual([]);

  /*
   * Recolour an element that ALREADY fails contrast to a colour the baseline has
   * never recorded. The node count must be UNMOVED; only the token changes.
   *
   * *** THE VICTIM MUST NOT SIT UNDER AN ANCESTOR `opacity`, and that is not a
   * detail — it decides whether this proof proves anything. *** It used to take
   * `nodes[0]` unconditionally. On 2026-09-13, after a contrast fix left this
   * surface with two failing nodes and `nodes[0]` among those inside
   * `.exp-row.done` (`opacity: 0.82`), forcing an opaque `background-color` on it
   * made axe unable to resolve the composite: the node left `violations`
   * altogether, the COUNT fell, and `auditScan` short-circuited on the count
   * change — there is a `continue` right after the `IMPROVED` push — so it never
   * reached the `foregrounds` check and returned `["improved"]` instead of
   * `new-foreground`.
   *
   * That is the same vacuity mechanism `CLAUDE.md` §11 records for this check
   * ("`auditScan` reaches the `foregrounds` check only when a count already
   * MATCHES"), reached from the other side: not a check that never fired, but a
   * fixture that stopped being able to make it fire. Filtering the victim keeps
   * the recolour a PURE colour change, which is what the proof claims to inject.
   */
  const contrastNodes = clean.violations.find((v) => v.id === 'color-contrast')?.nodes ?? [];
  const victim = await page.evaluate((selectors) => {
    for (const sel of selectors) {
      const el = document.querySelector<HTMLElement>(sel);
      if (!el) continue;
      let node: HTMLElement | null = el;
      let translucent = false;
      while (node && node !== document.documentElement) {
        if (Number(getComputedStyle(node).opacity) < 1) {
          translucent = true;
          break;
        }
        node = node.parentElement;
      }
      if (!translucent) return sel;
    }
    return null;
  }, contrastNodes.map((n) => String(n.target[0])));
  expect(
    typeof victim,
    'expected at least one baselined contrast node that is NOT under an ancestor ' +
      'opacity — see the note above for why a translucent victim makes this proof vacuous'
  ).toBe('string');
  await page.evaluate((sel) => {
    const el = document.querySelector<HTMLElement>(sel);
    if (!el) throw new Error(`self-check target vanished: ${sel}`);
    el.style.setProperty('color', '#d8dde3', 'important');
    el.style.setProperty('background-color', '#ffffff', 'important');
  }, victim as string);

  const failures = auditScan(await scan(page), newForegroundSurface.id, project);
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
 * ~~Ten a11y counts and two layout clips are recorded per platform~~ — **ZERO a11y
 * counts are, as of 2026-09-01**: the A3 neutral-ink palette collapsed every split in
 * `a11y-baseline.ts`. The MECHANISM is still there and still has to be proved, which is
 * why step 3 of the first test below now INJECTS a split rather than borrowing one; see
 * the note there. The reason the mechanism exists is unchanged: the app ships no
 * webfont and text wraps differently under SF Pro and under the
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
  //
  //    ── 2026-09-01: THE FIXTURE IS NOW INJECTED, BECAUSE THE FILE HAS NO ──────
  //       DIFFERING TRIPLE LEFT TO BORROW.
  //
  //    This used to read `validator@zoom-200`, which was `{ darwin: 4, linux: 5 }`.
  //    The A3 neutral-ink palette took that cell to 0 on both faces and it is now
  //    DELETED, along with every other split in `a11y-baseline.ts` — the file holds
  //    ZERO per-platform pairs. So the message below ("pick another differing
  //    triple") has no answer: there is no other.
  //
  //    THE PROOF IS NOT WEAKENED, AND THAT MATTERS MORE THAN KEEPING IT SHORT.
  //    Deleting steps 3 and 4 would remove the only assertion that the DEFAULT
  //    `platform` argument resolves to this machine's column rather than to a
  //    hard-wired one, and the comment on the neighbouring test records that
  //    exactly this went undetected once before ("replacing
  //    `resolvePlatform(process.platform)` with `resolvePlatform('linux')` left this
  //    test green"). So the split is CREATED here, in the same
  //    mutate-and-restore-in-`finally` idiom the next test already uses and for the
  //    same reason: each Playwright worker is its own process with its own module
  //    instance and runs one test at a time.
  //
  //    Nothing invented reaches the committed file. The injected pair is
  //    `{ thisPlatform: n, otherPlatform: n + 1 }` built from the cell's OWN
  //    measured `n`, it exists for the length of the `try`, and the restoration is
  //    asserted afterwards on BOTH columns.
  const platform = currentPlatform();
  const other = BASELINE_PLATFORMS.find((p) => p !== platform)!;
  /*
   * *** THE CELL THIS PROOF INJECTS A SPLIT INTO IS NOT `contrastBaselined`, AND
   * SINCE 2026-09-13 IT CANNOT BE. ***
   *
   * This proof builds a synthetic `{ thisPlatform: n, otherPlatform: n + 1 }` pair
   * out of a cell's OWN measured `n`, to prove platform resolution reads this
   * machine's column exactly. **It therefore requires a SCALAR** — you cannot
   * inject a split into a cell that is already one — and its own failure message
   * says so.
   *
   * `experiments-example@*` became `{ darwin: 2, linux: 3 }` on 2026-09-13, so it
   * stopped being usable HERE while remaining the right surface to OPEN (its
   * baselined content renders correctly in this fixture, which `record-detail`'s
   * did not). Those are two different requirements and they are now met
   * separately: the SURFACE is `contrastBaselined`, the CELL is this one.
   *
   * `record-detail@desktop-1280x800` is chosen as the cell because it is a scalar
   * (25) — and note it is used ONLY as a map key here. Nothing opens it, nothing
   * scans it, and the earlier failed migration is exactly why that distinction is
   * spelled out: its 25 is a number `a11y-axe.spec.ts` produced, and borrowing it
   * as a page in THIS fixture measured zero.
   *
   * If this cell ever becomes a split too, the message below fires and any other
   * scalar `color-contrast` cell is the answer.
   */
  const differing = {
    rule: 'color-contrast',
    surface: 'record-detail',
    project: 'desktop-1280x800',
  } as const;
  const probeEntry = baselineEntryFor(differing.rule)!;
  const probeKey = baselineKey(differing.surface, differing.project);
  const probeCounts = probeEntry.counts as Record<string, PlatformCount>;
  const probeOriginal = probeCounts[probeKey];
  expect(
    typeof probeOriginal,
    `this proof needs ${probeKey} to be a recorded SCALAR to build a split from; it reads ` +
      `${JSON.stringify(probeOriginal)}. If it has become a split of its own, use it directly ` +
      `instead of injecting one. If it has been deleted, pick another baselined cell.`
  ).toBe('number');
  const measured = probeOriginal as number;

  try {
    probeCounts[probeKey] = { [platform]: measured, [other]: measured + 1 } as Record<
      BaselinePlatform,
      number
    >;
    const mine = expectedNodeCount(differing.rule, differing.surface, differing.project, platform);
    const theirs = expectedNodeCount(differing.rule, differing.surface, differing.project, other);
    expect(mine, 'the injected split must put the cell\'s own measured number on this platform').toBe(
      measured
    );
    expect(theirs).toBe(measured + 1);
    expect(
      mine !== theirs,
      `the injected split did not take effect at ${probeKey}; both columns read ${mine}, so the ` +
        `resolution assertions below would pass under a broken resolver.`
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
  } finally {
    probeCounts[probeKey] = probeOriginal;
  }

  // Restored on BOTH columns — a `finally` that put back the wrong shape would
  // otherwise leak a split into every later test in this worker.
  expect(expectedNodeCount(differing.rule, differing.surface, differing.project, platform)).toBe(measured);
  expect(expectedNodeCount(differing.rule, differing.surface, differing.project, other)).toBe(measured);
});

test('@interaction tampering with THIS platform\'s count fails the audit; tampering with the other does not', async ({
  page,
  app,
}, testInfo) => {
  const project = testInfo.project.name;
  const contrastBaselined = pickContrastBaselined(project);
  await app.open(contrastBaselined);
  const platform = currentPlatform();
  const other = BASELINE_PLATFORMS.find((p) => p !== platform)!;

  // Repeated from the test above on purpose. `contrastBaselined` has the SAME count
  // on both platforms — that is what makes it a clean tampering fixture, and it is
  // why the constant moved to `record-detail` on 2026-09-13 (see that constant).
  // ~~since 2026-09-01 EVERY cell in the file does~~ — **FALSE, and it was already
  // false when written:** `settings-explorer@mobile-375x812` is
  // `{ darwin: 20, linux: 21 }` and predates that date, and
  // `experiments-example@*` became a split on 2026-09-13. The requirement is a
  // property of THIS FIXTURE, not of the file — which is the whole reason the
  // constant has to be chosen rather than assumed — but
  // it also means everything below would pass unchanged if resolution were
  // hard-wired to the wrong column. Verified by sabotage: replacing
  // `resolvePlatform(process.platform)` with `resolvePlatform('linux')` left
  // this test green until this line was added.
  expect(platform, `the tampering below only proves anything if the column is this machine's`).toBe(process.platform);

  // One scan, reused for all three verdicts: the page is not touched between
  // them, only the baseline is. That keeps the test to a single axe run and
  // makes it unambiguous that the DIFFERENCE comes from the baseline edit.
  const results = await scan(page);
  expect(
    auditScan(results, contrastBaselined.id, project),
    'the unmodified surface must audit clean'
  ).toEqual([]);

  const entry = baselineEntryFor('color-contrast')!;
  const key = baselineKey(contrastBaselined.id, project);
  const recorded = expectedNodeCount('color-contrast', contrastBaselined.id, project, platform);
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
    expect(expectedNodeCount('color-contrast', contrastBaselined.id, project, other)).toBe(recorded + 7);
    expect(
      auditScan(results, contrastBaselined.id, project),
      `a wrong number in the "${other}" column changed the verdict on "${platform}". The columns ` +
        `must be independent: CI's numbers must not be able to fail a developer's machine, and a ` +
        `developer's must not be able to pass CI.`
    ).toEqual([]);

    // (b) Corrupt THIS platform's number. The audit MUST go red — and must say
    //     `improved`, because the baseline now claims more failing nodes than
    //     the page actually has.
    counts[key] = pair(recorded + 7, recorded);
    const failures = auditScan(results, contrastBaselined.id, project);
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
  expect(expectedNodeCount('color-contrast', contrastBaselined.id, project, platform)).toBe(recorded);
  expect(auditScan(results, contrastBaselined.id, project), 'the baseline must be restored').toEqual([]);
});

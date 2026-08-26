/**
 * THE COMPOSER DOCK, AT 200% ZOOM ON A 320px PHONE.
 * @zoom
 *
 * ── The defect ──────────────────────────────────────────────────────────────
 *
 * `.assistant-foot` is the dock: composer, its helper, the no-model claim, the
 * "What Can I Ask?" trigger, the agent controls and the advisory caption. It is
 * `position: sticky; bottom: 0` on an opaque background so that asking another
 * question never requires scrolling in the mounts where an ancestor scrolls —
 * the ≤1024px slide-over drawer, and the memory rail.
 *
 * At 320x568 under 200% browser zoom — a CSS viewport of 160x284, which is
 * `playwright.config.ts`'s own emulation recipe (halve the layout viewport,
 * double the DPR) — the dock measured **545.9 CSS px in a 284 px viewport**
 * (darwin). It cannot fit; that part is arithmetic and pre-dates the claim.
 *
 * The bug was that sticky decided WHICH 284 px you got, and it chose against the
 * one interactive control in the tail. Sticky drags the dock up by a clamped
 * 110 px, so at the bottom of the drawer's scroll — the resting position a reader
 * reaches by scrolling to the end — the trigger sat at -22.9..15.1: 15 px of a
 * 38 px control, clipped by the top edge, with nothing further to scroll.
 *
 * `assistant.css` now releases the dock into normal flow inside
 * `(max-width: 480px) and (max-height: 480px)`. Measured after: the trigger is
 * fully visible for scrollTop 194..430 — 430 being the maximum — and lands at
 * 1..39 at the bottom of the scroll.
 *
 * ── AND THAT WAS NECESSARY AND NOT SUFFICIENT: LINUX CI WAS RED ─────────────
 *
 * `1..39` is ONE PIXEL of slack, and it is a coincidence rather than a fix.
 * In the `zoom-200` project on `ubuntu-latest` the same assertion measured
 * **-17.5..22.5**: this app ships no webfont, the 92-character claim wraps at a
 * different word under DejaVu/Liberation, and the extra line lands BELOW the
 * trigger. Reproduced here by inflating the tail 40px: -39..-1.
 *
 * The scroll range is NOT short — that was the first hypothesis and it is
 * measurably wrong. `.assistant-foot` ends at 283.9 in a 284px scrollport at
 * max scroll, so the container already scrolls its content fully, and bottom
 * padding in the band makes it worse (scrollHeight and max scrollTop grow
 * together). The trigger's top at the end of the scroll is
 * `284 - 38 - tail`, and the tail below it measures 245 — so the whole
 * assertion was hostage to the height of the caption and the agent controls.
 *
 * So the trigger is PINNED rather than scrolled past: `position: sticky;
 * top: 0` on `.assistant-capabilities`, same band. It leaves the scrollport
 * through the TOP, which is why `bottom: 0` would not do it. Measured on darwin
 * at the end of the scroll: 16..54 (16 is the drawer's own top padding), and
 * UNMOVED at 16..54 with the tail inflated 40px. The only height in it is the
 * trigger's own 38 against the viewport's 284 — no font metric participates.
 *
 * THE TRADE, STATED: a pinned box is displaced out of flow and overlays what
 * follows it — 13px of `.assistant-agent-actions` on darwin, 53px with the tail
 * inflated 40px, in both cases the block's padding and its eyebrow rather than
 * any button. Scrolling up a few px un-pins it. A 546px dock in a 284px
 * viewport cannot show everything; what it must not do is put the one
 * interactive control in the tail where scrolling does not reach it.
 *
 * ── What this spec asserts, and why each part is here ───────────────────────
 *
 * 1. the dock is released (computed `position`), and released to `relative`
 *    rather than `static`, so its `z-index: 1` still applies to an opaque box,
 *    AND the capabilities trigger is pinned (`sticky`) so the tail below it
 *    cannot decide whether it is reachable;
 * 2. the trigger is FULLY inside the viewport at the bottom of the drawer's
 *    scroll. This is the assertion that was red before the rule existed;
 * 3. the composer is still fully visible without scrolling at all;
 * 4. the no-model claim is still rendered, still NOT behind a disclosure, and
 *    still the composer's `aria-describedby` target — the three things the
 *    rejected alternatives would each have broken;
 * 5. nothing scrolls sideways, in the document or in the drawer;
 * 6. and — in the LAST describe, at the project's own 640x400 — the dock is
 *    still sticky. That is the guard on the rule's WIDTH bound. Widening the
 *    query to reach 640 would silently move the exact per-instance counts in
 *    `e2e/a11y-baseline.ts` and `e2e/layout-baseline.ts`, which are measured at
 *    the five `playwright.config.ts` projects and at no other size.
 *
 * ── Read-only ───────────────────────────────────────────────────────────────
 *
 * Nothing here answers, edits, exports, resets or deletes. It enters the shared
 * worked-example scope, reads one record, opens a drawer, scrolls, and measures
 * — so it is safe alongside the other projects reading the same session.
 *
 * ── The numbers above are DARWIN ────────────────────────────────────────────
 *
 * They were taken in headless Chromium on macOS. This app ships no webfont, so
 * `--font-ui` is SF Pro here and a DejaVu/Liberation face on `ubuntu-latest`,
 * and the wider Linux glyphs wrap the 92-character claim at a different word.
 * **CI (Linux) is the authority.** That is exactly why no assertion below
 * compares a px literal: every one is a relation (inside the viewport, position
 * released, no sideways scroll) that holds on both platforms, and the recorded
 * measurements stay in prose where they cannot rot into a false ratchet.
 */

import { SEED } from '../env';
import { expect, test } from '../fixtures';

/** 320x568 at 200% browser zoom. Same recipe as the `zoom-200` project, one phone smaller. */
const ZOOMED_PHONE = { width: 160, height: 284 } as const;

/** Fully inside the layout viewport — no part of the box past any edge. */
const FULLY_IN_VIEWPORT = async (page: import('@playwright/test').Page, selector: string) =>
  page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return { found: false, top: null, bottom: null, inside: false };
    const r = el.getBoundingClientRect();
    return {
      found: true,
      top: +r.top.toFixed(1),
      bottom: +r.bottom.toFixed(1),
      inside:
        r.top >= 0 && r.bottom <= window.innerHeight && r.left >= 0 && r.right <= window.innerWidth,
    };
  }, selector);

/** Open the drawer (it is a slide-over at ≤1024px) and settle. */
async function openAssistantDrawer(page: import('@playwright/test').Page) {
  const panel = page.locator('aside.assistant-drawer-panel');
  await expect(panel).toHaveCount(1, { timeout: 20_000 });
  const trigger = page.locator('button.assistant-drawer-trigger');
  await expect(trigger).toBeVisible({ timeout: 20_000 });
  await trigger.click();
  await expect(panel).toHaveAttribute('data-open', 'true');
  await expect(page.locator('.assistant-foot')).toBeVisible({ timeout: 20_000 });
  return panel;
}

test.describe('320x568 @200% zoom — the dock is released into normal flow', () => {
  test.use({ viewport: ZOOMED_PHONE, deviceScaleFactor: 2 });

  test('@zoom the "What Can I Ask?" trigger is fully reachable at the end of the scroll', async ({
    app,
    page,
  }) => {
    await app.gotoExample(`/record/${SEED.partial}`);
    const panel = await openAssistantDrawer(page);

    // The emulation's own parameters, so a future config change cannot quietly
    // turn this into a test of a 160px window at DPR 1.
    expect(await page.evaluate(() => [window.innerWidth, window.innerHeight, devicePixelRatio])).toEqual(
      [ZOOMED_PHONE.width, ZOOMED_PHONE.height, 2],
    );

    // (1) released — and released to a POSITIONED box, so `z-index: 1` still
    //     applies to the opaque dock.
    const dock = await page.evaluate(() => {
      const el = document.querySelector('.assistant-foot')!;
      const cs = getComputedStyle(el);
      return { position: cs.position, zIndex: cs.zIndex, height: +el.getBoundingClientRect().height.toFixed(1) };
    });
    expect(dock.position).toBe('relative');
    expect(dock.zIndex).toBe('1');

    // (1b) …and the trigger's own box is PINNED. Releasing the dock alone left
    //      assertion (2) below depending on the height of everything after the
    //      trigger, which is exactly the quantity that differs between this
    //      platform and CI's.
    expect(
      await page.evaluate(
        () => getComputedStyle(document.querySelector('.assistant-capabilities')!).position,
      ),
    ).toBe('sticky');

    // The precondition for the whole finding: the dock genuinely cannot fit.
    // If a future change makes it fit, this spec should be revisited rather than
    // passing for a reason it was not written for.
    expect(dock.height).toBeGreaterThan(ZOOMED_PHONE.height);

    // (3) the composer is in view before any scrolling.
    const composerAtRest = await FULLY_IN_VIEWPORT(page, '.assistant-composer-input');
    expect(composerAtRest.found).toBe(true);
    expect(
      composerAtRest.inside,
      `the composer must be visible unscrolled; measured ${composerAtRest.top}..${composerAtRest.bottom}`,
    ).toBe(true);

    // (2) THE ASSERTION THAT WAS RED. Scroll the drawer to its end — the
    //     resting position, not a hand-picked offset — and require the whole
    //     control to be inside the viewport.
    const scroll = await panel.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
      return { scrollTop: el.scrollTop, max: el.scrollHeight - el.clientHeight };
    });
    expect(scroll.max, 'the drawer must actually be scrollable here').toBeGreaterThan(0);
    expect(scroll.scrollTop).toBe(scroll.max);

    const triggerAtEnd = await FULLY_IN_VIEWPORT(page, '.assistant-capabilities-trigger');
    expect(triggerAtEnd.found).toBe(true);
    expect(
      triggerAtEnd.inside,
      `the trigger must be fully in view at the end of the scroll; measured ${triggerAtEnd.top}..${triggerAtEnd.bottom} in a ${ZOOMED_PHONE.height}px viewport`,
    ).toBe(true);

    // …and it is a real control there, not merely a visible rectangle.
    await expect(page.locator('.assistant-capabilities-trigger')).toBeEnabled();
    await expect(page.locator('.assistant-capabilities-trigger')).toHaveAttribute(
      'aria-expanded',
      'false',
    );

    // (5) nothing scrolls sideways.
    expect(
      await page.evaluate(() => [
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
        (() => {
          const p = document.querySelector('aside.assistant-drawer-panel')!;
          return p.scrollWidth - p.clientWidth;
        })(),
      ]),
    ).toEqual([0, 0]);
  });

  test('@zoom the no-model claim is still rendered, unhidden, and still describes the composer', async ({
    app,
    page,
  }) => {
    await app.gotoExample(`/record/${SEED.partial}`);
    await openAssistantDrawer(page);

    // (4) The three properties the rejected alternatives would have broken:
    // collapsing the claim behind a control, shortening it, or leaving it
    // rendered but detached from the input it qualifies.
    const claim = await page.evaluate(() => {
      const el = document.querySelector('.assistant-no-model');
      const composer = document.querySelector('.assistant-composer-input');
      if (!el || !composer) return null;
      const described = (composer.getAttribute('aria-describedby') ?? '').split(/\s+/).filter(Boolean);
      return {
        text: (el.textContent ?? '').trim(),
        insideDetails: !!el.closest('details'),
        id: el.id,
        described,
        allDescriptorsResolve: described.every((id) => !!document.getElementById(id)),
        display: getComputedStyle(el).display,
        visibility: getComputedStyle(el).visibility,
      };
    });
    expect(claim).not.toBeNull();
    expect(claim!.text).toBe(
      'There is no language model in this build. Nothing you type here is sent to a model provider.',
    );
    expect(claim!.insideDetails, 'the claim must never sit behind a disclosure').toBe(false);
    expect(claim!.display).not.toBe('none');
    expect(claim!.visibility).toBe('visible');
    expect(claim!.described).toContain(claim!.id);
    expect(claim!.allDescriptorsResolve).toBe(true);
  });
});

test.describe('the rule does NOT reach the zoom-200 project', () => {
  // No `test.use` — this runs at the project's own 640x400 @DPR2, which is the
  // viewport `e2e/a11y-baseline.ts` and `e2e/layout-baseline.ts` recorded exact
  // per-instance numbers at. The dock must be untouched there.
  test('@zoom at 640x400 the dock is still the sticky dock', async ({ app, page }) => {
    await app.gotoExample(`/record/${SEED.partial}`);
    await openAssistantDrawer(page);
    expect(await page.evaluate(() => [window.innerWidth, window.innerHeight])).toEqual([640, 400]);
    expect(
      await page.evaluate(() => getComputedStyle(document.querySelector('.assistant-foot')!).position),
    ).toBe('sticky');
    // …and the trigger is NOT pinned there either. Both declarations live in the
    // same bounded band, so both must be inert at every recorded-baseline size.
    expect(
      await page.evaluate(
        () => getComputedStyle(document.querySelector('.assistant-capabilities')!).position,
      ),
    ).toBe('relative');
  });
});

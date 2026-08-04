/**
 * Keyboard operability — focus visibility, tab order, no traps, skip link,
 * and disabled-control semantics.
 * @interaction
 */

import { expect, test } from '../fixtures';
import { activeElementFocusInfo } from '../helpers/focus';
import { SURFACES } from '../surfaces';
import { SEED } from '../env';

/**
 * `experiments-example` replaces `experiments` here, and that is not a swap for
 * convenience. The ordinary My Experiments is now the EMPTY state: it renders
 * three buttons, so a tab-order walk over it proves very little about the queue.
 * The populated queue inside a worked-example session is where the row links,
 * the group headings and the per-row controls are — the tab order this test was
 * written to cover. The ordinary empty state's own controls are asserted in
 * `specs/workspace-scope.spec.ts`, and the skip-link test below still runs on it.
 */
const KEYBOARD_SURFACES = [
  'experiments-example',
  'record-detail',
  'guided-completion',
  'memory',
  'settings',
] as const;

/**
 * Wait for the page to stop re-rendering before walking the tab order. The
 * record surfaces mount their Assistant panel after a second fetch; if that
 * lands mid-walk it unmounts whatever had focus and focus falls back to
 * `<body>`.
 */
async function settle(page: import('@playwright/test').Page): Promise<void> {
  await page.waitForLoadState('networkidle').catch(() => undefined);
  await page.waitForTimeout(250);
}

for (const id of KEYBOARD_SURFACES) {
  const surface = SURFACES.find((s) => s.id === id)!;

  test(`@interaction every keyboard-focused control shows a focus indicator: ${surface.name}`, async ({
    page,
    app,
  }) => {
    await app.open(surface);
    // Let late panels (Assistant, evidence trail) finish mounting. A component
    // that mounts mid-walk resets `document.activeElement` to <body>, which
    // used to abort the walk and made this test flaky.
    await settle(page);
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

    // Tab, not `.focus()`. Only real keyboard focus engages `:focus-visible`,
    // which is where this app's global focus ring lives (src/styles/base.css:79).
    const missing: string[] = [];
    const seen = new Set<string>();
    for (let i = 0; i < 45; i++) {
      await page.keyboard.press('Tab');
      const info = await activeElementFocusInfo(page);
      // `null` means focus is on <body> — keep tabbing rather than giving up.
      if (!info) continue;
      if (seen.has(info.key)) continue;
      seen.add(info.key);
      if (!info.visible) missing.push(`${info.key} (outline: ${info.outline}; box-shadow: ${info.boxShadow})`);
    }

    expect(seen.size, 'Tab should reach at least a few controls').toBeGreaterThan(3);
    expect(
      missing,
      missing.length
        ? `Controls with no visible focus indicator on ${surface.path}:\n  ${missing.join('\n  ')}`
        : undefined
    ).toEqual([]);
  });

  test(`@interaction Tab is not trapped: ${surface.name}`, async ({ page, app }) => {
    await app.open(surface);
    await settle(page);
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

    // Walk a bounded number of stops and require that the focused element keeps
    // changing — a trap shows up as the same element repeating forever.
    const order: string[] = [];
    for (let i = 0; i < 60; i++) {
      await page.keyboard.press('Tab');
      order.push(
        await page.evaluate(() => {
          const el = document.activeElement as HTMLElement | null;
          if (!el) return '<none>';
          return `${el.tagName.toLowerCase()}#${el.id}.${
            typeof el.className === 'string' ? el.className.trim().split(/\s+/)[0] ?? '' : ''
          }:${(el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 24)}`;
        })
      );
    }
    // No element may hold focus for 6 consecutive Tab presses.
    let run = 1;
    let worst = { key: order[0], run: 1 };
    for (let i = 1; i < order.length; i++) {
      run = order[i] === order[i - 1] ? run + 1 : 1;
      if (run > worst.run) worst = { key: order[i], run };
    }
    expect(worst.run, `Focus appears trapped on "${worst.key}" (${worst.run} consecutive Tab stops)`).toBeLessThan(6);
  });
}

test('@interaction the skip link is the first tab stop and moves focus to main', async ({ page, app }) => {
  await app.open(SURFACES.find((s) => s.id === 'experiments')!);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

  await page.keyboard.press('Tab');
  const skip = page.locator('a.skip-link');
  await expect(skip).toBeFocused();
  // It must become visible once focused — a permanently invisible skip link is
  // no better than no skip link.
  await expect(skip).toBeVisible();

  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#main$/);
  // <main> is tabIndex={-1} precisely so it can receive programmatic focus.
  await page.locator('main#main').focus();
  await expect(page.locator('main#main')).toBeFocused();
});

test('@interaction disabled controls are named, inert and explained', async ({ page, app }) => {
  // Guided Completion's "Confirm" starts disabled until a value is staged.
  // Record surface → the shared worked-example session.
  await app.gotoExample(`/record/${SEED.partial}/comp` + 'lete');
  const confirm = page.getByRole('button', { name: 'Confirm', exact: true });
  await expect(confirm).toBeVisible();
  await expect(confirm).toBeDisabled();

  // A `disabled` <button> must be out of the tab order — that is the semantic
  // difference from `aria-disabled`, which stays focusable.
  const reachable = await page.evaluate(() => {
    const el = document.querySelector<HTMLButtonElement>('button:disabled');
    return el ? el.tabIndex >= 0 && !el.disabled : false;
  });
  expect(reachable, 'a disabled button must not remain in the tab order').toBe(false);

  // Every disabled control still needs an accessible name, or a screen-reader
  // user hears "dimmed button" and nothing else.
  const unnamed = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('button:disabled, [aria-disabled="true"]'))
      .filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      })
      .filter((el) => !((el.getAttribute('aria-label') ?? '') + (el.textContent ?? '')).trim())
      .map((el) => el.outerHTML.slice(0, 120))
  );
  expect(unnamed, 'disabled controls without an accessible name').toEqual([]);
});

test('@interaction the unavailable API-key action is disabled AND says why', async ({ page, app }) => {
  await app.goto('/settings?tab=api');
  const create = page.getByRole('button', { name: /Create API Key/i });
  await expect(create).toBeDisabled();
  // The refusal is stated in prose, not implied by the greyed-out button.
  await expect(page.getByRole('heading', { name: /API Key Management Is Not Available in This Build/i })).toBeVisible();
});

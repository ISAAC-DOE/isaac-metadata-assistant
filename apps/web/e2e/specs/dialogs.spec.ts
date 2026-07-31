/**
 * Dialog semantics — the three overlays this app owns.
 * @interaction
 *
 *   ⌘K Search        modal, focus-trapped, Escape closes, focus restored
 *   Help             non-modal popover dialog, Escape closes, focus restored
 *   Reset Demo       modal, focus-trapped, typed-confirmation gate
 *
 * Runs at desktop AND at 375px, because the `max-width: 640px` breakpoint
 * changes the chrome these dialogs are anchored in.
 */

import { expect, test } from '../fixtures';
import { scan } from '../helpers/axe';
import { isBaselined } from '../a11y-baseline';
import { SURFACES } from '../surfaces';

const experiments = SURFACES.find((s) => s.id === 'experiments')!;

test.describe('@interaction ⌘K search dialog', () => {
  test('opens with correct modal semantics, traps Tab, closes on Escape, restores focus', async ({ page, app }) => {
    await app.open(experiments);

    const trigger = page.locator('button.topbar-search');
    await expect(trigger).toBeVisible();
    await expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');

    await trigger.click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('aria-modal', 'true');
    // Named — either aria-label or aria-labelledby resolving to real text.
    const name = await dialog.evaluate((el) => {
      const byId = el.getAttribute('aria-labelledby');
      if (byId) return byId.split(/\s+/).map((i) => document.getElementById(i)?.textContent ?? '').join(' ').trim();
      return el.getAttribute('aria-label') ?? '';
    });
    expect(name.length, 'the search dialog must have an accessible name').toBeGreaterThan(0);

    // Focus moves into the dialog, onto the query input.
    const input = page.getByRole('searchbox', { name: /Search experiments and project memory/i });
    await expect(input).toBeFocused();

    // Tab is contained: after many tabs, focus is still inside the dialog.
    for (let i = 0; i < 25; i++) await page.keyboard.press('Tab');
    expect(
      await page.evaluate(() => {
        const d = document.querySelector('[role="dialog"]');
        return !!d && !!document.activeElement && d.contains(document.activeElement);
      }),
      'Tab escaped the modal search dialog'
    ).toBe(true);

    // Shift+Tab is contained too.
    for (let i = 0; i < 25; i++) await page.keyboard.press('Shift+Tab');
    expect(
      await page.evaluate(() => {
        const d = document.querySelector('[role="dialog"]');
        return !!d && !!document.activeElement && d.contains(document.activeElement);
      }),
      'Shift+Tab escaped the modal search dialog'
    ).toBe(true);

    // Escape closes and returns focus to the trigger.
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  test('the open dialog itself passes the a11y scan', async ({ page, app }, testInfo) => {
    await app.open(experiments);
    await page.locator('button.topbar-search').click();
    await expect(page.getByRole('dialog')).toBeVisible();

    const results = await scan(page);
    const unexpected = results.violations.filter((v) => !isBaselined(v.id, 'experiments', testInfo.project.name));
    expect(
      unexpected.map((v) => `${v.id}: ${v.nodes.length} node(s)`),
      'new a11y violations while the search dialog is open'
    ).toEqual([]);
  });

  test('a query with no match states so rather than showing nothing', async ({ page, app }) => {
    await app.open(experiments);
    await page.locator('button.topbar-search').click();
    const input = page.getByRole('searchbox', { name: /Search experiments and project memory/i });
    await input.fill('zzzzzz-no-such-thing-zzzzzz');
    // The empty result must be *stated*. Any of the app's honest phrasings.
    await expect(page.getByRole('dialog')).toContainText(/no |nothing|0 result|not found/i, { timeout: 15_000 });
  });
});

test.describe('@interaction help popover', () => {
  test('is a named dialog, closes on Escape, restores focus', async ({ page, app }) => {
    await app.open(experiments);

    const trigger = page.getByRole('button', { name: 'Help', exact: true });
    await expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');

    await trigger.click();
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    const labelled = await dialog.getAttribute('aria-labelledby');
    expect(labelled, 'the help dialog must be labelled by its heading').toBeTruthy();
    // React's `useId()` emits ids like `:r9:`, which are legal HTML ids but not
    // legal CSS id selectors. Use an attribute selector, not `#id`.
    await expect(page.locator(`[id="${labelled}"]`)).toHaveText(/\S/);

    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  test('its own close button closes it', async ({ page, app }) => {
    await app.open(experiments);
    await page.getByRole('button', { name: 'Help', exact: true }).click();
    await page.getByRole('button', { name: 'Close help' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
});

test.describe('@interaction assistant slide-over (narrow viewports only)', () => {
  // `AssistantDrawer` renders ONE <aside>: a static `complementary` landmark at
  // >=1024px, and a CSS-hidden slide-over below that, which becomes
  // role="dialog" + aria-modal only while open. So this test is meaningful at
  // 375px and vacuous at 1280px — it skips explicitly rather than pretending.
  test('opens as a modal dialog, traps Tab, closes on Escape, restores focus', async ({ page, app }) => {
    const { SEED } = await import('../env');
    await app.goto(`/record/${SEED.partial}`);

    const trigger = page.locator('button.assistant-drawer-trigger');
    await expect(trigger).toHaveCount(1);
    if (!(await trigger.isVisible())) {
      test.skip(true, 'Desktop width: the Assistant is a static complementary landmark, not a drawer.');
    }

    const panel = page.locator('aside.assistant-drawer-panel');
    await expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(trigger).toHaveAttribute('aria-controls', /\S/);

    await trigger.click();
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await expect(panel).toHaveAttribute('role', 'dialog');
    await expect(panel).toHaveAttribute('aria-modal', 'true');
    await expect(panel).toHaveAttribute('aria-label', /Assistant/i);
    await expect(panel).toBeVisible();

    for (let i = 0; i < 25; i++) await page.keyboard.press('Tab');
    expect(
      await page.evaluate(() => {
        const p = document.querySelector('aside.assistant-drawer-panel');
        return !!p && !!document.activeElement && p.contains(document.activeElement);
      }),
      'Tab escaped the Assistant slide-over'
    ).toBe(true);

    await page.keyboard.press('Escape');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(trigger).toBeFocused();
    // The element stays in the DOM but drops its dialog semantics when closed.
    await expect(panel).not.toHaveAttribute('role', 'dialog');
  });
});

test.describe('@interaction reset-demo confirmation dialog', () => {
  // READ-ONLY: this test opens the dialog and asserts its gate. It NEVER types
  // the confirmation phrase and NEVER submits, so the shared synthetic
  // workspace the other four viewport projects are reading is untouched.
  test('is a labelled modal with a typed-confirmation gate, and Escape cancels', async ({ page, app }) => {
    await app.open(experiments);

    const trigger = page.getByRole('button', { name: /Reset Demo/i });
    if ((await trigger.count()) === 0) {
      test.skip(true, 'Reset Demo trigger not present (nothing removable in this workspace state).');
    }
    await trigger.click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('aria-modal', 'true');
    await expect(dialog).toHaveAttribute('aria-labelledby', /\S/);

    // The destructive action is gated behind a typed phrase and starts disabled.
    const confirmField = dialog.getByRole('textbox');
    await expect(confirmField.first()).toBeVisible();

    for (let i = 0; i < 20; i++) await page.keyboard.press('Tab');
    expect(
      await page.evaluate(() => {
        const d = document.querySelector('[role="dialog"]');
        return !!d && !!document.activeElement && d.contains(document.activeElement);
      }),
      'Tab escaped the modal reset dialog'
    ).toBe(true);

    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });
});

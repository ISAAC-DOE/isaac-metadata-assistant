/**
 * Tab-widget semantics — the three `role="tablist"` surfaces.
 * @interaction
 *
 * Asserts the WAI-ARIA APG tabs pattern: one selected tab, roving tabindex,
 * arrow-key movement, Home/End, and a tabpanel wired back to its tab.
 */

import { expect, test } from '../fixtures';
import { TABBED_SURFACES } from '../surfaces';

for (const surface of TABBED_SURFACES) {
  test.describe(`@interaction tabs: ${surface.tablistName}`, () => {
    test('exposes the APG tab structure', async ({ page, app }) => {
      await app.goto(surface.path);

      const tablist = page.getByRole('tablist', { name: surface.tablistName });
      await expect(tablist).toBeVisible();

      const tabs = tablist.getByRole('tab');
      await expect(tabs).toHaveCount(surface.tabs.length);
      for (let i = 0; i < surface.tabs.length; i++) {
        await expect(tabs.nth(i)).toHaveAccessibleName(surface.tabs[i]);
      }

      // Exactly one selected.
      const selected = await tablist.evaluate((tl) =>
        Array.from(tl.querySelectorAll('[role="tab"]')).filter((t) => t.getAttribute('aria-selected') === 'true').length
      );
      expect(selected, 'exactly one tab must be aria-selected').toBe(1);

      // Roving tabindex: the selected tab is the only one in the tab order.
      const tabIndexes = await tablist.evaluate((tl) =>
        Array.from(tl.querySelectorAll<HTMLElement>('[role="tab"]')).map((t) => ({
          selected: t.getAttribute('aria-selected') === 'true',
          tabIndex: t.tabIndex,
        }))
      );
      for (const t of tabIndexes) {
        expect(t.tabIndex, `roving tabindex: selected=${t.selected}`).toBe(t.selected ? 0 : -1);
      }

      // The selected tab points at a rendered tabpanel, and the panel points back.
      const controls = await tablist.evaluate(
        (tl) => tl.querySelector('[role="tab"][aria-selected="true"]')?.getAttribute('aria-controls') ?? ''
      );
      expect(controls, 'the selected tab must have aria-controls').toContain(surface.panelIdPrefix);
      const panel = page.locator(`#${controls}`);
      await expect(panel).toHaveAttribute('role', 'tabpanel');
      await expect(panel).toBeVisible();
      const labelledby = await panel.getAttribute('aria-labelledby');
      expect(labelledby, 'the tabpanel must be labelled by its tab').toBeTruthy();
      await expect(page.locator(`#${labelledby}`)).toHaveAttribute('role', 'tab');
    });

    test('is operable with arrow keys, Home and End', async ({ page, app }) => {
      await app.goto(surface.path);
      const tablist = page.getByRole('tablist', { name: surface.tablistName });
      const first = tablist.getByRole('tab').first();
      const last = tablist.getByRole('tab').last();

      await first.focus();
      await expect(first).toBeFocused();

      await page.keyboard.press('ArrowRight');
      await expect(tablist.getByRole('tab').nth(1)).toBeFocused();
      await expect(tablist.getByRole('tab').nth(1)).toHaveAttribute('aria-selected', 'true');

      await page.keyboard.press('ArrowLeft');
      await expect(first).toBeFocused();

      await page.keyboard.press('End');
      await expect(last).toBeFocused();
      await expect(last).toHaveAttribute('aria-selected', 'true');

      await page.keyboard.press('Home');
      await expect(first).toBeFocused();
      await expect(first).toHaveAttribute('aria-selected', 'true');
    });

    test('deep-links: the ?tab= value selects the tab', async ({ page, app }) => {
      // Take the LAST tab so a default-selection bug cannot make this pass.
      await app.goto(surface.path);
      const tablist = page.getByRole('tablist', { name: surface.tablistName });
      const lastLabel = surface.tabs[surface.tabs.length - 1];
      await tablist.getByRole('tab', { name: lastLabel }).click();

      const url = new URL(page.url());
      expect(url.searchParams.get('tab'), 'activating a tab must write ?tab=').toBeTruthy();

      // Reload the deep link and confirm the same tab comes back selected.
      await app.goto(`${url.pathname}${url.search}`);
      await expect(
        page.getByRole('tablist', { name: surface.tablistName }).getByRole('tab', { name: lastLabel })
      ).toHaveAttribute('aria-selected', 'true');
    });
  });
}

test('@interaction the Evidence preview-source tabs expose selection state', async ({ page, app }) => {
  const { SEED } = await import('../env');
  // Record surface → the shared worked-example session. See `e2e/worked-example.ts`.
  await app.gotoExample(`/record/${SEED.partial}/evidence`);
  const tablist = page.getByRole('tablist', { name: 'Preview source' });
  await expect(tablist).toBeVisible();
  const tabs = tablist.getByRole('tab');
  await expect(tabs).toHaveCount(3);
  const selected = await tablist.evaluate(
    (tl) => Array.from(tl.querySelectorAll('[role="tab"]')).filter((t) => t.getAttribute('aria-selected') === 'true').length
  );
  expect(selected).toBe(1);
});

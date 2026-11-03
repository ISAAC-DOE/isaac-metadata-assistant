/**
 * The themed picker (`src/components/Select.tsx`) in a real browser.
 *
 * It replaced the native `<select>`, so Playwright's `selectOption` and `toHaveValue` no longer apply:
 * the trigger is a `<button role="combobox">` and its popup a `role="listbox"` of `role="option"`s. A
 * test drives it the way a person does: click the trigger, then click the option. Each option carries
 * its value as `data-value` and the trigger carries the chosen one, so a test that chose by schema
 * token (as `selectOption(token)` did) still can.
 */
import { expect, type Locator } from '@playwright/test';

/** The open popup of `combobox` (the listbox its `aria-controls` names). */
async function listboxOf(combobox: Locator): Promise<Locator> {
  const id = await combobox.getAttribute('aria-controls');
  if (!id) throw new Error('not a themed Select: the combobox controls no listbox');
  return combobox.page().locator(`[id="${id}"]`);
}

/** Open `combobox` and choose the option whose value is `value`. */
export async function chooseValue(combobox: Locator, value: string): Promise<void> {
  if ((await combobox.getAttribute('aria-expanded')) !== 'true') await combobox.click();
  const listbox = await listboxOf(combobox);
  await expect(listbox).toBeVisible();
  await listbox.locator(`[role="option"][data-value="${value.replace(/"/g, '\\"')}"]`).click();
  await expect(combobox).toHaveAttribute('aria-expanded', 'false');
}

/** Open `combobox` and choose the option whose visible label is `label`. */
export async function chooseLabel(combobox: Locator, label: string | RegExp): Promise<void> {
  if ((await combobox.getAttribute('aria-expanded')) !== 'true') await combobox.click();
  const listbox = await listboxOf(combobox);
  await expect(listbox).toBeVisible();
  await listbox.getByRole('option', { name: label }).first().click();
  await expect(combobox).toHaveAttribute('aria-expanded', 'false');
}

/** Assert the value `combobox` holds (what `toHaveValue` asserted of the native select). */
export async function expectValue(combobox: Locator, value: string): Promise<void> {
  await expect(combobox).toHaveAttribute('data-value', value);
}

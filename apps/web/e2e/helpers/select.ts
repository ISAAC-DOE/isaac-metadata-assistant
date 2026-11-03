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

/**
 * `combobox` narrowed to the trigger itself. While the popup is open, `Select` names its listbox with the
 * same text as the label (`aria-label`), and Playwright's `getByLabel` matches `aria-label` on ANY element:
 * a picker found with `getByLabel(...)` resolves to TWO elements the moment it opens, and every later
 * action on it fails strict mode. Intersecting with `role=combobox` keeps it on the trigger.
 */
function triggerOf(combobox: Locator): Locator {
  return combobox.and(combobox.page().getByRole('combobox'));
}

/**
 * The popup of `trigger` (the listbox its `aria-controls` names). Read while the picker is CLOSED, before
 * anything opens it: see `triggerOf`.
 */
async function listboxOf(trigger: Locator): Promise<Locator> {
  const id = await trigger.getAttribute('aria-controls');
  if (!id) throw new Error('not a themed Select: the combobox controls no listbox');
  return trigger.page().locator(`[id="${id}"]`);
}

async function open(combobox: Locator): Promise<{ trigger: Locator; listbox: Locator }> {
  const trigger = triggerOf(combobox);
  const listbox = await listboxOf(trigger);
  if ((await trigger.getAttribute('aria-expanded')) !== 'true') await trigger.click();
  await expect(listbox).toBeVisible();
  return { trigger, listbox };
}

/** Open `combobox` and choose the option whose value is `value`. */
export async function chooseValue(combobox: Locator, value: string): Promise<void> {
  const { trigger, listbox } = await open(combobox);
  await listbox.locator(`[role="option"][data-value="${value.replace(/"/g, '\\"')}"]`).click();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
}

/** Open `combobox` and choose the option whose visible label is `label`. */
export async function chooseLabel(combobox: Locator, label: string | RegExp): Promise<void> {
  const { trigger, listbox } = await open(combobox);
  await listbox.getByRole('option', { name: label }).first().click();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
}

/** Assert the value `combobox` holds (what `toHaveValue` asserted of the native select). */
export async function expectValue(combobox: Locator, value: string, message?: string): Promise<void> {
  await expect(triggerOf(combobox), message).toHaveAttribute('data-value', value);
}

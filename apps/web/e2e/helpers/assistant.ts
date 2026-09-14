import { expect, type Locator, type Page } from '@playwright/test';

/**
 * Make the Assistant panel USABLE, at any viewport, and return it.
 *
 * WHY THIS HELPER EXISTS, recorded because its absence is what broke six specs
 * at once. `AssistantDrawer` has TWO controls, in two viewport bands, and a spec
 * that knows only one of them is correct at one width and silently wrong at the
 * other:
 *
 *   <= 1024px   `button.assistant-drawer-trigger`  opens a slide-over dialog
 *   >  1024px   `button.assistant-rail-toggle`     expands/collapses the rail
 *
 * `states.spec.ts` and `visual-sweep.spec.ts` each hand-rolled an
 * `openAssistant` that clicked only the FIRST one and, at desktop, simply
 * asserted the panel was visible. That was correct for as long as the desktop
 * rail defaulted to EXPANDED — and `UX-013` flipped that default, because the
 * Assistant is meant to be contextual rather than to consume a 342px column of
 * the scientist's working width before anyone has asked it anything.
 *
 * The failure mode is worth naming because it is not a crash: the `<aside>`
 * stays present and "visible" while its CONTENT is `display: none` inside the
 * collapsed band, so `toBeVisible()` on the panel PASSES and every assertion
 * about what is inside it fails. Six specs reported as six unrelated
 * assistant-state regressions.
 *
 * SO THERE IS NOW ONE DEFINITION of "open the Assistant", and it handles both
 * bands. `keyboard.spec.ts`, `dialogs.spec.ts`, `assistant-dock-short-viewport.spec.ts`
 * and the trusted two-actor walk deliberately do NOT use it: each drives one
 * specific band on purpose (768px or a zoomed phone) and asserts the semantics
 * of that band, so routing them through a band-agnostic helper would make them
 * test something other than what they are named for.
 */
export async function openAssistant(page: Page): Promise<Locator> {
  const panel = page.locator('aside.assistant-drawer-panel');
  await expect(panel).toHaveCount(1, { timeout: 20_000 });

  const drawerTrigger = page.locator('button.assistant-drawer-trigger');
  const railToggle = page.locator('button.assistant-rail-toggle');

  if (await drawerTrigger.isVisible()) {
    // <= 1024px: a slide-over dialog. The dialog semantics are asserted here
    // rather than left to the caller, because they only exist in this band and
    // a caller that checked them unconditionally would fail at desktop.
    await expect(drawerTrigger).toHaveAttribute('aria-haspopup', 'dialog');
    await drawerTrigger.click();
    await expect(drawerTrigger).toHaveAttribute('aria-expanded', 'true');
    await expect(panel).toHaveAttribute('role', 'dialog');
    await expect(panel).toHaveAttribute('aria-modal', 'true');
  } else if (await railToggle.isVisible()) {
    // > 1024px: the rail. It starts COLLAPSED (UX-013), so expand it unless a
    // previous step in the same context already did. Keyed on the control's own
    // `aria-expanded` rather than on a class or a stored preference, so this
    // stays correct if the default ever moves again.
    if ((await railToggle.getAttribute('aria-expanded')) !== 'true') {
      await railToggle.click();
    }
    await expect(railToggle).toHaveAttribute('aria-expanded', 'true');
  }

  await expect(panel).toBeVisible({ timeout: 10_000 });

  /*
   * AND THE CONTENT IS ASSERTED VISIBLE, NOT JUST THE PANEL — this is the whole
   * lesson of the regression this helper fixes. `aside.assistant-drawer-panel`
   * remains present and visible while `.assistant-drawer-content` is
   * `display: none` in the collapsed desktop band, so a panel-only check cannot
   * tell "open" from "collapsed". Without this line the helper would return a
   * locator whose children are all hidden and the caller's failure would name
   * the child, not the cause.
   */
  await expect(panel.locator('.assistant-drawer-content')).toBeVisible({ timeout: 10_000 });
  return panel;
}

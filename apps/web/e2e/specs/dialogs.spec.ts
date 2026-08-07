/**
 * Dialog semantics — the three overlays this app owns.
 * @interaction
 *
 *   ⌘K Search            modal, focus-trapped, Escape closes, focus restored
 *   Help                 non-modal popover dialog, Escape closes, focus restored
 *   Reset Worked Example modal, focus-trapped, typed-confirmation gate — now
 *                        reached from the worked-example bar inside a real
 *                        session, because that is the only place it exists
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
    // Record surface → the shared worked-example session.
    await app.gotoExample(`/record/${SEED.partial}`);

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

test.describe('@interaction reset-worked-example confirmation dialog', () => {
  /*
   * WHERE THIS CONTROL LIVES NOW, because the locator moved and the reason
   * matters more than the new string.
   *
   * It was `Reset Workspace` on `/experiments`. `POST /api/demo/reset` now
   * REQUIRES a worked-example session and refuses without one, writing nothing,
   * so the control was rehomed into the persistent worked-example bar
   * (`TutorialSessionBar`) and renamed `Reset Worked Example` — the old name
   * would have described a scope it cannot reach. On My Experiments it would be
   * a control that looks like it acts and does not, which is exactly the failure
   * the note below was written about, so it is NOT there any more and asserting
   * that it is would be asserting a design the app does not have.
   *
   * The bar renders only while a session is open, and the ONLY way a reader
   * opens one is by starting the walkthrough. So this test starts the real
   * walkthrough — which mints a session of its OWN, not the shared read-only one
   * — and drives the control where it actually is.
   *
   * STILL READ-ONLY over any shared state, and now over a private session too:
   * it opens the dialog (whose preview is a read-only `mode: 'preview'` POST),
   * asserts the gate, and NEVER types the phrase or submits. The `tutorial`
   * fixture disposes the session this test created afterwards.
   */
  test('is a labelled modal with a typed-confirmation gate, and Escape cancels', async ({
    page,
    app,
    tutorial,
  }) => {
    await app.open(experiments);

    /*
     * THE EMPTY STATE'S PRIMARY, not the first-run offer card. `app.open(experiments)`
     * is the ORDINARY workspace, which is permanently empty, and `ExperimentsHome` now
     * suppresses the offer whenever the queue has no rows so that one action is never
     * offered by two primaries at once. `Launch Guided Demo` is therefore the control
     * on this screen; it calls the same `startTutorial`, so the session this test needs
     * is opened by the same code path it always was.
     */
    await page.getByRole('button', { name: 'Launch Guided Demo' }).click();
    // The bar is chrome and appears as soon as the session exists — before any
    // coach mark has settled.
    const bar = page.getByRole('complementary', { name: 'Worked example session' });
    await expect(bar).toBeVisible({ timeout: 20_000 });
    expect(tutorial.sessionsCreated().length, 'starting the walkthrough must mint one session').toBe(1);

    // Asserted, NOT skipped. This used to read
    //   `if ((await trigger.count()) === 0) test.skip(true, 'nothing removable …')`
    // and that escape hatch was actively harmful in two ways. Its stated reason was
    // wrong — the control's visibility is gated on `mode === 'synthetic-only'` from
    // `GET /api/health` (`ResetDemoDialog` returns null otherwise), never on whether
    // anything is removable. And because a missing trigger produced a SKIP rather
    // than a failure, renaming the button from "Reset Demo" to "Reset Workspace"
    // turned this whole test — the only real-browser coverage of the destructive
    // dialog's focus trap and typed-confirmation gate — silently vacuous. The
    // backend this suite asserts as a precondition always runs synthetic-only, so
    // the trigger is always present; if it is not, that is a defect and must fail.
    const trigger = bar.getByRole('button', { name: /Reset Worked Example/i });
    await expect(
      trigger,
      'the Reset Worked Example trigger is absent from the worked-example bar. Either the ' +
        'control was renamed or rehomed again (update this locator) or the app is not ' +
        'reporting mode: synthetic-only. Both are failures, not reasons to skip.'
    ).toBeVisible();
    await trigger.click();

    /*
     * `page.getByRole('dialog')` is deliberately NOT used here any more, and this
     * is not a style change. The coach mark is ALSO a `role="dialog"`
     * (`GuidedTutorial.tsx`), so with the walkthrough running there are two, and a
     * bare role query is a strict-mode violation — or, worse, resolves to the
     * wrong one. `aria-modal="true"` is the exact discriminator the app itself
     * relies on: the coach mark deliberately does not set it (the control it
     * describes must stay operable), and the app's own Escape guard keys off
     * precisely this attribute.
     */
    const MODAL = '[role="dialog"][aria-modal="true"]';
    const dialog = page.locator(MODAL);
    await expect(dialog).toHaveCount(1);
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('aria-labelledby', /\S/);
    // Named by the rescoped title, so a silent revert to workspace-wide wording
    // fails here rather than in a screenshot review.
    await expect(dialog).toContainText(/Reset the Worked Example/i);

    // The destructive action is gated behind a typed phrase and starts disabled.
    const confirmField = dialog.getByRole('textbox');
    await expect(confirmField.first()).toBeVisible();
    await expect(dialog.getByRole('button', { name: 'Reset Example Records' })).toBeDisabled();

    for (let i = 0; i < 20; i++) await page.keyboard.press('Tab');
    expect(
      await page.evaluate((sel) => {
        const d = document.querySelector(sel);
        return !!d && !!document.activeElement && d.contains(document.activeElement);
      }, MODAL),
      'Tab escaped the modal reset dialog'
    ).toBe(true);

    await page.keyboard.press('Escape');
    await expect(page.locator(MODAL)).toHaveCount(0);
    await expect(trigger).toBeFocused();

    // AND the walkthrough is still running. This is the app's own documented
    // guard: the coach mark registers Escape in the CAPTURE phase on `document`
    // and would otherwise see it first, silently leaving the walkthrough while a
    // destructive confirmation was still on screen. The bar's continued presence
    // is proof the session was not discarded by that keystroke.
    await expect(bar).toBeVisible();
  });
});

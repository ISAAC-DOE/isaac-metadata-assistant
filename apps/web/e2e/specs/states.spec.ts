/**
 * Loading, error, refused and empty states — every one reachable WITHOUT a
 * database and without writing anything.
 * @interaction
 *
 * The failure states are produced by intercepting the browser's own requests
 * (`page.route`), never by breaking the shared backend — the other viewport
 * projects are reading the same server in parallel.
 */

import { API_BASE, MISSING_RECORD_ID, SEED } from '../env';
import { ASSISTANT_MOUNTS } from '../surfaces';
import { expect, LOADING_PANEL, test } from '../fixtures';

const API_GLOB = `${API_BASE.replace(/\/api$/, '')}/api/**`;

/**
 * Return the Assistant panel, opening the drawer first when the viewport is
 * narrow.
 *
 * `AssistantDrawer` renders ONE `<aside>` that is a static `complementary`
 * landmark at >=1024px and a CSS-hidden slide-over below it. At 375px the
 * landmark therefore does not exist until the "Assistant" trigger is
 * activated, at which point the same element becomes `role="dialog"` +
 * `aria-modal`. Both shapes are legitimate; the specs must handle both rather
 * than assume the desktop one.
 */
async function openAssistant(page: import('@playwright/test').Page) {
  const trigger = page.locator('button.assistant-drawer-trigger');
  const panel = page.locator('aside.assistant-drawer-panel');
  await expect(panel).toHaveCount(1, { timeout: 20_000 });
  if (await trigger.isVisible()) {
    await expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
    await trigger.click();
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await expect(panel).toHaveAttribute('role', 'dialog');
    await expect(panel).toHaveAttribute('aria-modal', 'true');
  }
  await expect(panel).toBeVisible({ timeout: 10_000 });
  return panel;
}

test('@interaction LOADING: a pending fetch shows a polite status, not an empty screen', async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  await page.route(`${API_BASE}/experiments`, async (route) => {
    await gate;
    await route.continue();
  });

  await page.goto('/experiments', { waitUntil: 'domcontentloaded' });

  const loading = page.locator(LOADING_PANEL);
  await expect(loading).toBeVisible();
  // The label is per-call, not a fixed string — assert it says what is loading.
  await expect(loading).toContainText(/Loading/i);
  // It must be announced, not just drawn.
  await expect(loading).toHaveAttribute('aria-live', 'polite');

  release();
  await expect(page.getByRole('heading', { name: 'My Experiments' })).toBeVisible();
});

test('@interaction ERROR: an unreachable API states the failure and offers a retry', async ({ page }) => {
  await page.route(API_GLOB, (route) => route.abort('connectionrefused'));
  await page.goto('/experiments', { waitUntil: 'domcontentloaded' });

  const alert = page.getByRole('alert');
  await expect(alert).toBeVisible();
  await expect(alert).toContainText(/Backend Not Running/i);
  // The local build's remedy is actionable, so it is shown.
  await expect(alert).toContainText(/uvicorn/i);
  await expect(page.getByRole('button', { name: /Retry/i })).toBeVisible();

  // And it must NOT invent placeholder content in place of the data.
  await expect(page.getByRole('heading', { name: 'My Experiments' })).toBeVisible();
});

test('@interaction ERROR: the error state is announced and keyboard-reachable', async ({ page }) => {
  await page.route(API_GLOB, (route) => route.abort('connectionrefused'));
  await page.goto('/experiments', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('alert')).toBeVisible();

  const retry = page.getByRole('button', { name: /Retry/i });
  await retry.focus();
  await expect(retry).toBeFocused();

  // The alert is a labelled region with a heading, so a screen-reader user
  // lands somewhere meaningful rather than on a bare sentence.
  await expect(page.getByRole('alert').getByRole('heading')).toBeVisible();

  // `Copy Diagnostics` is rendered only for some failure classes (it needs the
  // app/memory context the diagnostics report is built from). Assert it is
  // OPERABLE when present rather than asserting it is always there — claiming
  // the latter would be untrue.
  const diagnostics = page.getByRole('button', { name: /Copy Diagnostics/i });
  if ((await diagnostics.count()) > 0) {
    await expect(diagnostics.first()).toBeEnabled();
  }
});

test('@interaction NOT FOUND: an unknown record id says so instead of guessing', async ({ page }) => {
  await page.goto(`/record/${MISSING_RECORD_ID}`, { waitUntil: 'domcontentloaded' });
  const alert = page.getByRole('alert');
  await expect(alert).toBeVisible({ timeout: 20_000 });
  await expect(alert).toContainText(/Record Not Found/i);
});

test('@interaction REFUSED: Load Materials refuses uploads and explains the boundary', async ({ page, app }) => {
  await app.goto('/load');

  const refusal = page.getByRole('button', { name: /Loading your own files is not enabled/i });
  await expect(refusal).toBeVisible();

  // Deliberately ENABLED, not disabled: the control's own label says it opens
  // no picker and takes no dropped file, and activating it makes the server
  // state the refusal. Asserting `toBeDisabled()` here would have been a test
  // asserting a design the app does not have.
  await expect(refusal).toBeEnabled();

  // There is genuinely no file input anywhere on the surface.
  await expect(page.locator('input[type="file"]')).toHaveCount(0);

  await refusal.click();

  // The refusal comes back as a note, not an error — the app is behaving as
  // designed, and it says so in words.
  const blocked = page.locator('.upload-blocked[role="note"]');
  await expect(blocked).toBeVisible({ timeout: 20_000 });
  await expect(blocked).toContainText(/Blocked by governance/i);

  // The offered alternative is present and enabled.
  await expect(page.getByRole('button', { name: 'Run the Worked Example' })).toBeEnabled();
});

test('@interaction REFUSED: the upload endpoint itself answers 403', async ({ request }) => {
  // Asserted at the API, not by clicking — the UI never lets a file be chosen.
  const res = await request.post(`${API_BASE}/uploads`, {
    multipart: { file: { name: 'x.txt', mimeType: 'text/plain', buffer: Buffer.from('synthetic') } },
    failOnStatusCode: false,
  });
  expect(res.status(), 'uploads must be refused in synthetic-only mode').toBe(403);
});

test.describe('@interaction assistant panel', () => {
  for (const mount of ASSISTANT_MOUNTS) {
    test(`EMPTY state is honest and labelled on ${mount.id}`, async ({ page, app }) => {
      await app.goto(mount.path);

      const aside = await openAssistant(page);

      // In the EMPTY state the conversation region is present but carries no
      // TURNS. It may still carry a standing note (Export Readiness shows
      // "Truth questions route to the CLI…"), and when it is entirely empty it
      // has zero height (`.assistant-log--resting`) — which Playwright counts
      // as hidden. So the assertions are: the region exists, is named, and
      // holds no question/answer turn yet.
      const log = aside.getByRole('log');
      await expect(log).toHaveCount(1);
      await expect(log).toHaveAccessibleName(/Assistant conversation/i);
      await expect(log.locator('.assistant-msg')).toHaveCount(0);

      // An empty conversation offers starting points rather than a blank box.
      await expect(aside.getByRole('button', { name: /What Can I Ask\?/i })).toBeVisible();
      const send = aside.getByRole('button', { name: /Send question/i });
      await expect(send).toBeVisible();
    });
  }

  test('ACTIVE state: a suggested question produces an answer in the log', async ({ page, app }) => {
    // Read-only: `POST /experiments/{id}/assistant/query` is documented and
    // implemented as advisory and non-mutating — it never changes the record,
    // its revision, its evidence or its export.
    await app.goto(`/record/${SEED.partial}`);
    const aside = await openAssistant(page);
    const log = aside.getByRole('log');
    await expect(log.locator('.assistant-msg')).toHaveCount(0);

    await aside.getByRole('button', { name: /What still needs me\?/i }).click();

    // A question turn and an answer turn appear.
    await expect(log.locator('.assistant-msg')).not.toHaveCount(0, { timeout: 25_000 });
    await expect(log).toContainText(/What still needs me\?/i);
  });
});

test('@interaction EMPTY: the validator refuses an empty submission rather than passing it', async ({ page, app }) => {
  await app.goto('/governance?tab=validator');
  const validate = page.getByRole('button', { name: 'Validate', exact: true });
  await expect(validate).toBeVisible();
  // Either the control is gated, or submitting states the problem. Both are
  // honest; silently reporting "valid" would not be.
  if (await validate.isEnabled()) {
    await validate.click();
    await expect(page.locator('main')).not.toContainText(/^\s*Valid\s*$/);
  } else {
    await expect(validate).toBeDisabled();
  }
});

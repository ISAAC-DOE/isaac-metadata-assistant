/**
 * Long, unbreakable strings — the classic responsive break.
 * @responsive
 *
 * Two mechanisms, and the difference matters:
 *
 *   1. REAL USER INPUT — a long token typed into the app's own text controls.
 *      No DOM was tampered with; this is exactly what a user can do.
 *   2. A LABELLED DOM MUTATION — a long token written into an existing text
 *      node via `page.evaluate`. This is NOT something a user can do, and it is
 *      NOT proof that real data of that shape exists (the workspace is
 *      synthetic and its ids/titles are fixed). It tests one thing only: does
 *      the CSS wrap or ellipsise, or does it push the page sideways.
 */

import { expect, test } from '../fixtures';
import { horizontalPageScroll } from '../helpers/layout';
import { SURFACES } from '../surfaces';

const LONG_TOKEN = 'Cu'.repeat(120); // 240 chars, no break opportunity
const LONG_PATH = '/very/long/synthetic/path/' + 'segment-'.repeat(40) + 'file.xdi';

const assertNoPageScroll = async (page: import('@playwright/test').Page, where: string) => {
  const s = await horizontalPageScroll(page);
  expect(
    s.docScrollWidth,
    `${where}: the page scrolls horizontally (${s.docScrollWidth} > ${s.docClientWidth})`
  ).toBeLessThanOrEqual(s.docClientWidth + 1);
};

test('@responsive a long token typed into the ⌘K search box does not push the page sideways', async ({ page, app }) => {
  await app.open(SURFACES.find((s) => s.id === 'experiments')!);
  await page.locator('button.topbar-search').click();
  const input = page.getByRole('searchbox', { name: /Search experiments and project memory/i });
  await input.fill(LONG_TOKEN);
  await page.waitForTimeout(400);
  await assertNoPageScroll(page, 'search dialog with a 240-char token');
  // The dialog itself must stay inside the viewport.
  const box = await page.getByRole('dialog').boundingBox();
  const vw = await page.evaluate(() => document.documentElement.clientWidth);
  expect(box, 'dialog must be laid out').not.toBeNull();
  expect(box!.x + box!.width, 'the dialog overflows the viewport').toBeLessThanOrEqual(vw + 1);
});

test('@responsive a long unbroken paste into the Validator does not push the page sideways', async ({ page, app }) => {
  await app.goto('/governance?tab=validator');
  const box = page.locator('textarea').first();
  if ((await box.count()) === 0) test.skip(true, 'Validator has no free-text area in this build.');
  await box.fill(`{"record_id":"${LONG_TOKEN}","assets":{"raw":"${LONG_PATH}"}}`);
  await page.waitForTimeout(400);
  await assertNoPageScroll(page, 'validator textarea with a 240-char token');
});

test('@responsive an injected long title wraps or ellipsises rather than overflowing', async ({ page, app }) => {
  // The WORKED-EXAMPLE queue, not the ordinary one, and the change is what keeps
  // this test meaningful rather than what makes it pass. The ordinary workspace
  // is permanently empty, so `.exp-row` renders nowhere in it — the
  // `test.skip(!mutated, …)` below would fire on every run and this test would
  // silently stop covering anything. A populated queue exists only inside a
  // worked-example session, so that is where a row is mutated.
  await app.open(SURFACES.find((s) => s.id === 'experiments-example')!);

  // LABELLED SYNTHETIC MUTATION — see the file header. This overwrites the
  // rendered text of one already-present row title in the browser only. It
  // does not touch the backend, the workspace, or any record.
  const mutated = await page.evaluate((token) => {
    const el = document.querySelector<HTMLElement>('.exp-row .exp-main');
    const target = el?.querySelector<HTMLElement>('a, h2, h3, [class*="title"], .exp-title') ?? el;
    if (!target) return false;
    target.textContent = token;
    return true;
  }, LONG_TOKEN);
  // Asserted, not skipped. A missing row now means the worked-example session did
  // not materialise its five records — a real failure, and one a skip would hide.
  expect(
    mutated,
    'no experiment row rendered inside the worked-example session to mutate: the session ' +
      'should hold the five built-in examples (see e2e/global-setup.ts step 4).'
  ).toBe(true);

  await page.waitForTimeout(300);
  await assertNoPageScroll(page, 'experiments list with an injected 240-char title');
});

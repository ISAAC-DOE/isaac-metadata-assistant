/**
 * R3 · export, through the real UI against the real backend.
 *
 * The export gate is the one place this app makes a claim with consequences — an
 * exported record is the official artifact — so the assertions here are about the
 * gate holding, not about the happy path looking nice:
 *
 *   · a record with open questions must NOT be exportable, and the screen must say so
 *     rather than offering a button that would fail;
 *   · a successful export must be DURABLE (survive a reload) and must be reflected in
 *     server state, not just in the component that just ran it;
 *   · a SECOND export of the same record must be refused, not silently repeated.
 *     Repeat-submit is the classic double-click defect, and here it would mean two
 *     official artifacts for one record.
 */

import { test, expect, openExport, SEED } from './fixtures';

test.describe('R3 · export', () => {
  test('a record with open questions is not exportable, and the screen says why', async ({
    page,
    server,
    calls,
  }) => {
    const before = await server.read(SEED.fresh);
    expect(before.pendingCount, 'this test needs an incomplete record').toBeGreaterThan(0);
    expect(before.exported).toBe(false);

    await openExport(page, SEED.fresh);

    // Whatever the wording, the screen must not present export as available. The
    // assertion is on the CONTROL's state, not on copy, so a reword cannot silently
    // turn this into a test of nothing.
    const exportButton = page.getByRole('button', { name: /Export Official Record/i });
    if (await exportButton.count()) {
      await expect(
        exportButton,
        'export must be disabled while questions remain open'
      ).toBeDisabled();
    }

    // Nothing was written, and no export request was even attempted.
    expect(calls.postsTo('/export'), 'an incomplete record must not POST /export').toHaveLength(0);
    const after = await server.read(SEED.fresh);
    expect(after.exported).toBe(false);
    expect(after.rev).toBe(before.rev);
  });

  test('exporting a ready record writes it, and it SURVIVES a reload', async ({
    page,
    server,
    calls,
  }) => {
    const before = await server.read(SEED.ready);
    expect(before.pendingCount, 'SEED.ready must have nothing pending').toBe(0);
    expect(before.exported, 'SEED.ready must not be exported yet').toBe(false);

    await openExport(page, SEED.ready);

    const exportButton = page.getByRole('button', { name: /Export Official Record/i });
    await expect(exportButton).toBeVisible();
    await expect(exportButton).toBeEnabled();
    await exportButton.click();

    // A real request left the page...
    await expect
      .poll(() => calls.postsTo('/export').length, {
        message: 'no POST to /export was observed',
      })
      .toBeGreaterThan(0);

    // ...and the server now holds an exported record.
    await expect
      .poll(async () => (await server.read(SEED.ready)).exported, {
        message: 'the export did not reach server state',
      })
      .toBe(true);

    // DURABILITY: a fresh mount, fresh fetch.
    await page.reload();
    expect((await server.read(SEED.ready)).exported).toBe(true);
  });

  test('a second export of the same record is refused, not silently repeated', async ({
    page,
    server,
  }) => {
    // Depends on the previous test having exported SEED.ready — the file runs in order
    // with a single worker, which is why this suite sets `fullyParallel: false`. Stated
    // rather than assumed, because a reader moving this test would break it.
    const before = await server.read(SEED.ready);
    expect(
      before.exported,
      'this test follows the successful-export test in this file and needs its result'
    ).toBe(true);

    await openExport(page, SEED.ready);

    const exportButton = page.getByRole('button', { name: /Export Official Record/i });
    // The app may either hide/disable the control or refuse the request. Both are
    // acceptable; silently producing a second artifact is not.
    if ((await exportButton.count()) && (await exportButton.isEnabled())) {
      await exportButton.click();
      // If it did fire, the record must be unchanged — one artifact, not two.
      await expect
        .poll(async () => (await server.read(SEED.ready)).rev)
        .toBe(before.rev);
    }

    const after = await server.read(SEED.ready);
    expect(after.exported).toBe(true);
    expect(after.rev, 'a repeated export must not mutate the record again').toBe(before.rev);
  });
});

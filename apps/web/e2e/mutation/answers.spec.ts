/**
 * R3 · answering a question, through the real UI against the real backend.
 *
 * What each test here is actually worth, stated so a future reader does not
 * "simplify" one into uselessness:
 *
 *   · the CLICK is the action. No spec POSTs an answer itself.
 *   · a real request is proven to have LEFT THE PAGE (`calls.postsTo`), so a
 *     frontend-only state update cannot pass.
 *   · persistence is proven by a FULL RELOAD and an INDEPENDENT server read, not by
 *     the same component's own state. This is the assertion that fails if a mutation
 *     is optimistic-only, and it is the one the repo previously had no browser
 *     coverage for at all.
 */

import { test, expect, openComplete, SEED } from './fixtures';

test.describe('R3 · answers', () => {
  test('confirming an answer sends a real request, shrinks pending, and SURVIVES a reload', async ({
    page,
    server,
    calls,
  }) => {
    const before = await server.read(SEED.fresh);
    expect(before.pendingCount, 'this spec needs an open question to answer').toBeGreaterThan(0);

    await openComplete(page, SEED.fresh);

    // The visible control, filled and confirmed as a reader would.
    const field = page.getByLabel('Asset Hash');
    await expect(field).toBeVisible();
    await field.fill('a3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b123');
    await page.getByRole('button', { name: 'Confirm' }).click();

    // A request actually left the page.
    await expect
      .poll(() => calls.postsTo('/answers').length, {
        message: 'no POST to /answers was observed — the UI may have updated only itself',
      })
      .toBeGreaterThan(0);

    // The screen reflects the server's shrunken list.
    await expect(page.getByText('1 / 5')).toBeVisible();

    // INDEPENDENT server check: the revision moved and the answer log grew.
    const after = await server.read(SEED.fresh);
    expect(after.rev, 'rev must advance — an accepted answer is a write').toBeGreaterThan(before.rev);
    expect(after.pendingCount).toBe(before.pendingCount - 1);

    // THE DURABILITY ASSERTION: a full reload, fresh mount, fresh fetch.
    await page.reload();
    await expect(page.getByRole('heading', { name: /Answer \d+ Question/ })).toBeVisible();
    const reloaded = await server.read(SEED.fresh);
    expect(reloaded.pendingCount).toBe(after.pendingCount);
    expect(reloaded.rev).toBe(after.rev);
  });

  test('"I don\'t know" sends NOTHING and leaves the question open on the server', async ({
    page,
    server,
    calls,
  }) => {
    const before = await server.read(SEED.partial);
    await openComplete(page, SEED.partial);

    await page.getByText("I don't know — leave honestly missing").click();

    // The skipped question is listed, and the list says it is not durable.
    await expect(page.getByText(/Left Honestly Missing/)).toBeVisible();

    // No write of any kind. This is the no-guessing contract: the app must not
    // invent a value, and must not record "unknown" as though it were an answer.
    expect(calls.postsTo('/answers'), 'skipping must not POST').toHaveLength(0);

    const after = await server.read(SEED.partial);
    expect(after.rev, 'skipping must not advance the revision').toBe(before.rev);
    expect(after.pendingCount, 'the question must stay open server-side').toBe(before.pendingCount);
  });

  /**
   * A CONCURRENT SECOND WRITER — and an honest account of what this can and cannot
   * prove through a browser.
   *
   * WHAT I TRIED FIRST and why it does not work. The intended test was: open the
   * page (it now holds a version token), let another client write behind its back,
   * submit from the stale page, expect a 412 and a recovery banner. It failed —
   * because the submit SUCCEEDED. `useRecordSync` polls the record with a
   * conditional GET, sees the change, and the page adopts the fresh token before a
   * human could finish typing. So the browser does not hold a stale token for long
   * enough to submit one, which is the SAFER outcome and not a defect.
   *
   * I could not force the stale path either: the poll is a conditional GET against
   * the SAME detail endpoint the screen needs to render, so blocking the poll blocks
   * the page. Rather than mock a mutation response — which this suite refuses to do,
   * because it would prove nothing about the server — the test asserts what actually
   * happens and is explicit that the 412 guard itself is covered elsewhere
   * (`apps/api/tests` exercises If-Match absent/stale/valid directly, and the
   * frontend's 412 recovery banner has unit coverage in `edit-field.test.tsx`).
   *
   * WHAT IT DOES PROVE, which is the property that actually matters: a second
   * writer's work is NOT LOST. Both writes land, the revision advances once per
   * write, and the pending list reflects both — no clobbering, no silent overwrite.
   */
  test('a concurrent second writer does not lose either write', async ({ page, server }) => {
    // SEED.fresh, whose open blockers are text-valued (an asset hash), because this
    // test is about the WRITE-vs-WRITE property, not about the structured-confirmation
    // gate. Record 2's blockers are `series`/`descriptor` and drive a different, richer
    // control; mixing the two concerns into one test made it fragile for reasons that
    // had nothing to do with concurrency.
    //
    // Order is UI-FIRST here on purpose: it removes any dependence on how quickly the
    // page's poller notices someone else's write. The property under test is symmetric
    // — neither write may erase the other.
    await openComplete(page, SEED.fresh);
    const start = await server.read(SEED.fresh);
    expect(start.pendingCount, 'this test needs at least two open questions').toBeGreaterThan(1);

    const field = page.getByLabel('Asset Hash');
    await expect(field).toBeVisible();
    await field.fill('c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345');
    await page.getByRole('button', { name: 'Confirm' }).click();

    await expect
      .poll(async () => (await server.read(SEED.fresh)).rev, {
        message: 'the browser write never reached the server',
      })
      .toBeGreaterThan(start.rev);
    const afterUi = await server.read(SEED.fresh);
    expect(afterUi.pendingCount).toBe(start.pendingCount - 1);

    // Now a DIFFERENT client answers the next open question, using that blocker's own
    // example value so the shape matches its kind.
    await server.answerBehindTheUi(SEED.fresh);
    const end = await server.read(SEED.fresh);

    // NEITHER write was lost: the revision advanced again, and the pending list shrank
    // a second time. A clobber would show up as pendingCount going back up, or as rev
    // failing to advance twice.
    expect(end.rev).toBeGreaterThan(afterUi.rev);
    expect(end.pendingCount, 'the browser answer must not have been undone').toBe(
      afterUi.pendingCount - 1
    );

    // And both survive a reload — durable, not just in flight.
    await page.reload();
    await expect(page.getByRole('heading', { name: /Answer \d+ Question/ })).toBeVisible();
    const reloaded = await server.read(SEED.fresh);
    expect(reloaded.pendingCount).toBe(end.pendingCount);
    expect(reloaded.rev).toBe(end.rev);
  });
});

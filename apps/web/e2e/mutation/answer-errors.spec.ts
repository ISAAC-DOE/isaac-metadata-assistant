/**
 * R4 · ANSWERS — the arms `answers.spec.ts` does not cover: refusing, failing, and
 * recovering.
 *
 * `answers.spec.ts` owns the happy paths (a confirmation writes and survives a
 * reload; "I don't know" writes nothing; two writers do not clobber each other).
 * This file owns what happens when the answer is one the system must NOT take:
 *
 *   · blank            — the control is inert and nothing is sent;
 *   · WRONG-TYPED      — the historical 500, now guarded; must stay a safe status,
 *                        must write nothing, must leave the question open;
 *   · STALE            — the record moved under the form; the write is refused,
 *                        nothing is applied, and Refresh-then-retry works.
 *
 * Every test runs in its own worked-example session and disposes it.
 */

import { SEED, expect, openComplete, test } from './own-session-fixtures';

const HASH = 'a3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b123';
/** A sha256 — the right shape for an ASSET blocker and the wrong shape for a
 *  `series` one. This is the exact confusion that produced the original 500. */
const WRONG_TYPED_SERIES_VALUE =
  'd4c0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b999';

test.describe('R4 · answers that must be refused', () => {
  test('a blank answer cannot be confirmed and no request is sent', async ({
    page,
    server,
    calls,
  }) => {
    const before = await server.read(SEED.fresh);
    await openComplete(page, SEED.fresh);

    const field = page.getByLabel('Asset Hash');
    await expect(field).toHaveValue('');
    await expect(
      page.getByRole('button', { name: 'Confirm' }),
      'an empty field must not be confirmable — the app must never store a blank as an answer'
    ).toBeDisabled();

    // Whitespace is not a value either.
    await field.fill('   ');
    await expect(page.getByRole('button', { name: 'Confirm' })).toBeDisabled();

    expect(calls.postsTo('/answers'), 'nothing may be sent for a blank answer').toHaveLength(0);
    const after = await server.read(SEED.fresh);
    expect(after.rev).toBe(before.rev);
    expect(after.pendingIds).toEqual(before.pendingIds);
  });

  test('a wrong-typed structured answer gets a safe status — never a 5xx — writes nothing, and leaves the question open', async ({
    page,
    server,
    rewriteNextBody,
  }) => {
    /*
     * THE DEFECT THIS GUARDS. Record 2's open blockers are `series` and `descriptor`
     * — STRUCTURED. A caller that sent a sha256 string for `series` used to crash the
     * truth core: `draft["series"]` became the string, was iterated, and
     * `s.get("series_id")` raised — an unhandled 500 out of `complete.py`. It is now
     * type-guarded (`isinstance(series, list)` and friends), and
     * `apps/api/tests/test_answers_wrong_type.py` pins that at the HTTP layer.
     *
     * WHY IT IS WORTH RE-ASSERTING IN A BROWSER, and the honest caveat. THIS UI
     * cannot send a wrong-typed structured value on its own: `GuidedPrompt` submits
     * `demo.value` verbatim for a structured blocker, so the shape is always right.
     * The scenario is therefore reached by REWRITING THE REQUEST BODY on its way out
     * — a stand-in for a client defect or a future refactor. Nothing is mocked: the
     * status and the state assertions below are the real FastAPI reply and real
     * subsequent reads. What this adds over pytest is the whole-stack path — the app's
     * own fetch client, its error handling, and the record's state afterwards as the
     * browser can observe it.
     */
    const before = await server.read(SEED.partial);
    expect(before.pendingIds, 'this test needs record 2 at its structured baseline').toEqual([
      'series',
      'descriptor',
    ]);

    const statuses: number[] = [];
    page.on('response', (res) => {
      if (res.request().method() === 'POST' && res.url().includes('/answers')) {
        statuses.push(res.status());
      }
    });

    await openComplete(page, SEED.partial);
    await rewriteNextBody('/answers', (body) => ({
      ...body,
      answers: { series: WRONG_TYPED_SERIES_VALUE },
    }));

    // The real controls: stage the labelled example value, then confirm it.
    await page.getByRole('button', { name: 'Use This Value' }).first().click();
    await page.getByRole('button', { name: 'Confirm' }).click();

    await expect.poll(() => statuses.length, { message: 'the answer never left the page' }).toBe(1);
    expect(
      statuses[0],
      `a wrong-typed answer returned ${statuses[0]} — malformed input must be refused or ` +
        `ignored, never raise out of the truth core`
    ).toBeLessThan(500);

    // NOTHING WAS WRITTEN and the blocker is still open. `_answers_to_apply_shape`
    // drops what it cannot interpret, so the honest outcome is a no-op, not an answer.
    const after = await server.read(SEED.partial);
    expect(after.rev, 'a value the core could not interpret must not count as a write').toBe(
      before.rev
    );
    expect(after.pendingIds, 'refusing to interpret a value is not the same as answering it').toEqual(
      before.pendingIds
    );

    // AND THE READER IS NOT LEFT WITH A FABRICATED ANSWER once the screen re-reads
    // the server. (What the screen claims BEFORE that re-read is a separate finding,
    // reported rather than asserted here — this test must not encode it as correct.)
    await page.reload();
    await expect(page.getByRole('heading', { name: /Answer 2 Questions/ })).toBeVisible();
    await expect(page.locator('.answered-row')).toHaveCount(0);
    expect((await server.read(SEED.partial)).pendingIds).toEqual(before.pendingIds);
  });

  test('an answer submitted against a record that moved is refused, applies nothing, and Refresh-then-retry succeeds', async ({
    page,
    server,
  }) => {
    /*
     * THE RACE, and why this screen can hold a stale token when the read-only surfaces
     * cannot. `GuidedCompletion` deliberately does NOT auto-refetch on a change signal
     * — it holds STAGED, unsent input, and refetching would discard what the reader
     * typed. It raises a banner and keeps `currentVersion` as it was. So the If-Match
     * it sends is genuinely stale, and the 412 is the hard backstop that stops a
     * concurrent edit being clobbered.
     */
    const start = await server.read(SEED.fresh);
    await openComplete(page, SEED.fresh);

    // Type an answer, so there is unsent input the refusal must preserve.
    await page.getByLabel('Asset Hash').fill(HASH);

    // A DIFFERENT client writes, invalidating the token this page is holding.
    await server.answerBehindTheUi(SEED.fresh);
    const moved = await server.read(SEED.fresh);
    expect(moved.rev).toBeGreaterThan(start.rev);

    await page.getByRole('button', { name: 'Confirm' }).click();

    // The refusal is stated in the reader's terms, and it states the two things that
    // matter: nothing was applied, and their input is still there.
    const banner = page.locator('.completion-submit-error');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('This record changed elsewhere');
    await expect(banner).toContainText('Nothing was applied');
    await expect(
      page.getByLabel('Asset Hash'),
      'a refused write must not throw away what the reader typed'
    ).toHaveValue(HASH);

    // The other client's write is intact and this one applied nothing.
    const afterRefusal = await server.read(SEED.fresh);
    expect(afterRefusal.rev, 'a refused write must not advance the revision').toBe(moved.rev);
    expect(afterRefusal.pendingIds).toEqual(moved.pendingIds);

    // RECOVERY, through the control the banner offers. Refresh re-reads the record and
    // re-adopts the current token; the same answer then lands.
    await banner.getByRole('button', { name: 'Refresh' }).click();
    await expect(page.locator('.completion-submit-error')).toHaveCount(0);

    await page.getByLabel('Asset Hash').fill(HASH);
    await page.getByRole('button', { name: 'Confirm' }).click();

    await expect
      .poll(async () => (await server.read(SEED.fresh)).rev, {
        message: 'the retry after a stale refusal never landed',
      })
      .toBe(moved.rev + 1);
    const end = await server.read(SEED.fresh);
    expect(
      end.pendingIds.length,
      'the retry must close one more question, not re-open the other client’s'
    ).toBe(moved.pendingIds.length - 1);
  });
});

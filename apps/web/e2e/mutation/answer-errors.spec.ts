/**
 * R4 · ANSWERS — the arms `answers.spec.ts` does not cover: refusing, failing, and
 * recovering.
 *
 * `answers.spec.ts` owns the happy paths (a confirmation writes and survives a
 * reload; "I don't know" writes nothing; two writers do not clobber each other).
 * This file owns what happens when the answer is one the system must NOT take:
 *
 *   · blank            — the control is inert and nothing is sent;
 *   · MALFORMED        — a value the truth core drops. 200, nothing written, and the
 *                        screen must not claim it as confirmed;
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
/**
 * NOT 64 lowercase hex characters, so `complete.py`'s `_SHA256_RE` rejects it and
 * `apply_answers` puts the blocker straight back into `remaining_pending`. Nothing is
 * tampered with to reach this: `GuidedPrompt` gates Confirm on `text.trim().length > 0`
 * and nothing else, so a reader can type this and press Confirm.
 *
 * Short on purpose — `answerValuePreview` renders a string of 20 characters or fewer
 * verbatim, so if the screen ever did claim it, the claim would be findable by its
 * exact text rather than as a truncated prefix.
 */
const MALFORMED_HASH = 'not-a-valid-sha256';

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

  test('a malformed hash is dropped by the core, and the screen claims no confirmation, moves no counter, and keeps the question open', async ({
    page,
    server,
  }) => {
    /*
     * THE DEFECT THIS GUARDS, and it needed no tampering to reach. `GuidedCompletion`
     * used to push a field into its `answered` list on any RESOLVED promise — i.e. it
     * read HTTP 200 as proof of a write. `apply_answers` refuses a malformed sha256 and
     * re-adds the blocker, returning 200 with `rev` unmoved, so the row rendered
     * "Asset Hash / you answered not-a-valid-sha256 / Confirmed by You" over a value the
     * truth core had thrown away — a false claim of confirmed authority over a
     * scientific value, which is the worst kind of defect this app can have.
     *
     * Everything below is the real UI against the real FastAPI process: no route
     * interception, no rewritten body, no mocked response.
     */
    const before = await server.read(SEED.fresh);
    await openComplete(page, SEED.fresh);

    const statuses: number[] = [];
    page.on('response', (res) => {
      if (res.request().method() === 'POST' && res.url().includes('/answers')) {
        statuses.push(res.status());
      }
    });

    await page.getByLabel('Asset Hash').fill(MALFORMED_HASH);
    await page.getByRole('button', { name: 'Confirm' }).click();

    // The request really was accepted — this is a 200 the client had to interpret, not
    // an error it could lean on.
    await expect
      .poll(() => statuses.length, { message: 'the answer never left the page' })
      .toBe(1);
    expect(statuses[0], 'the backend accepts and drops; it does not error').toBe(200);

    // The screen says so, and says it without naming a cause the response does not
    // carry.
    const note = page.getByText(/That answer was not applied\./);
    await expect(note).toBeVisible();
    await expect(note).toContainText('nothing was invented in its place');
    await expect(note).not.toContainText(/malformed|invalid|identical/i);

    // NO CONFIRMATION IS CLAIMED, and the value is nowhere on the screen as an answer.
    await expect(page.locator('.answered-row')).toHaveCount(0);
    await expect(page.getByText('Confirmed by You')).toHaveCount(0);
    await expect(page.locator('.answered-stored')).toHaveCount(0);

    // The counter did not move and the question is still question 1 — a field may never
    // be answered and open at the same time.
    await expect(page.locator('.completion-counter')).toHaveText(
      `0 / ${before.pendingIds.length}`
    );
    await expect(page.getByRole('heading', { name: /Answer \d+ Questions/ })).toBeVisible();
    await expect(
      page.locator('.guided-index'),
      'the refused question must still be the open one'
    ).toHaveText(`Question 1 of ${before.pendingIds.length}`);
    // ...and what the reader typed is still there to correct.
    await expect(page.getByLabel('Asset Hash')).toHaveValue(MALFORMED_HASH);

    // INDEPENDENT server read: nothing was written and the question set is untouched.
    const after = await server.read(SEED.fresh);
    expect(after.rev, 'a dropped answer must not advance the revision').toBe(before.rev);
    expect(after.pendingIds).toEqual(before.pendingIds);
    expect(JSON.stringify(await server.evidence(SEED.fresh))).not.toContain(MALFORMED_HASH);

    // AND THE RECOVERY WORKS: a well-formed value on the same visit lands normally, so
    // the guard refuses the bad write without wedging the screen. 64 lowercase hex
    // characters is all `_SHA256_RE` asks for.
    await page.getByLabel('Asset Hash').fill('a1'.repeat(32));
    await page.getByRole('button', { name: 'Confirm' }).click();
    await expect(page.getByText('Confirmed by You')).toBeVisible();
    await expect(page.getByText(/That answer was not applied\./)).toHaveCount(0);
    await expect
      .poll(async () => (await server.read(SEED.fresh)).rev, {
        message: 'the retry after a dropped answer never landed',
      })
      .toBe(before.rev + 1);
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
    // AND IT IS THE REFUSAL, not the absorbed 200. Asserted exactly rather than left at
    // "< 500", because "< 500" was satisfied by the 200 this test was written against and
    // would be satisfied again if that behaviour came back.
    expect(statuses[0], 'a value the record cannot store must be refused by name').toBe(422);

    // NOTHING WAS WRITTEN and the blocker is still open. ~~`_answers_to_apply_shape`
    // drops what it cannot interpret, so the honest outcome is a no-op, not an answer.~~
    // Since 2026-08-25 the honest outcome is a typed REFUSAL, not a no-op: the drop was
    // silent and the `200` beside it said "the submitted value was identical", so one
    // response asserted both that the question was open and that its answer was already
    // stored. The two state assertions below are unchanged and are the point — what
    // changed is which of them the SCREEN learns from.
    const after = await server.read(SEED.partial);
    expect(after.rev, 'a value the core could not interpret must not count as a write').toBe(
      before.rev
    );
    expect(after.pendingIds, 'refusing to interpret a value is not the same as answering it').toEqual(
      before.pendingIds
    );

    // AND THE READER IS NOT LEFT WITH A FABRICATED ANSWER — not after the re-read, and
    // not before it.
    //
    // This block used to say: "What the screen claims BEFORE that re-read is a separate
    // finding, reported rather than asserted here — this test must not encode it as
    // correct." It was right not to encode it, and the finding it deferred was the
    // defect: the screen read the 200 as proof, rendered "Reduced Spectrum / you
    // answered averaged_spectrum · 2 channels / Confirmed by You", advanced the counter
    // to 1 / 3, and re-rendered the same `series` question as "Question 2 of 3". Now
    // that the claim follows the server's report, the pre-reload state is assertable and
    // is asserted here, which is where the regression would first show.
    // ~~`That answer was not applied.`~~ — that note is `answerNotApplied`, which is set
    // only on a `200` the client had to interpret. A refused answer now takes the error
    // path, and the copy it lands on is asserted rather than assumed: the GENERIC notice
    // ends "try again", which is false advice for a value that will be refused every
    // time, so `GuidedCompletion` has its own branch for `invalid_field_value` on this
    // path — worded for an answer rather than borrowing the correction path's "this
    // field still holds the value it held before", which is false when the field never
    // held one.
    const notice = page.getByTestId('answer-unstorable-notice');
    await expect(notice).toBeVisible();
    await expect(notice).toContainText('nothing was invented in its place');
    await expect(notice).toContainText('still');
    await expect(notice, 'no cause may be named that the response does not carry').not.toContainText(
      /identical|malformed|wrong type/i
    );
    await expect(page.locator('.answered-row')).toHaveCount(0);
    await expect(page.getByText('Confirmed by You')).toHaveCount(0);
    await expect(
      page.locator('.completion-counter'),
      'a dropped answer must not inflate the counter'
    ).toHaveText(`0 / ${before.pendingIds.length}`);
    await expect(
      page.locator('.guided-index'),
      'the dropped question must still be the FIRST open one, not the second'
    ).toHaveText(`Question 1 of ${before.pendingIds.length}`);

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

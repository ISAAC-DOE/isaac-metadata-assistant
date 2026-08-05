/**
 * R4 · EDIT — correcting a value that is already confirmed.
 *
 * The edit path is the only place this app OVERWRITES something a human already
 * confirmed, so the properties worth guarding are about restraint rather than
 * throughput: Cancel must write nothing, a stale correction must apply nothing, and
 * an unsaved editor must leave no trace.
 *
 * WHERE THE EDIT AFFORDANCE ACTUALLY IS, because it constrains every test here.
 * `GuidedCompletion` renders an Edit button only for rows in its `answered` list,
 * and that list is CLIENT state for the current visit — it starts empty on every
 * mount. So a field is editable through this UI only in the same visit in which it
 * was answered. Each test therefore answers first, then corrects. (That the list is
 * visit-scoped is not incidental; the "navigating away" test pins it, and the
 * consequence is in the report.)
 *
 * Every test runs in its own worked-example session and disposes it.
 */

import { SEED, expect, openComplete, test } from './own-session-fixtures';

/*
 * Two sha256-shaped values that appear NOWHERE in the committed seed — not as a
 * stored value and not as any blocker's example answer.
 *
 * That matters, and it is recorded because the first draft got it wrong: `HASH_B`
 * was originally the reduced-spectrum blocker's own demo value, so when the
 * concurrent writer in the stale test answered that blocker, "the correction was not
 * written anywhere" found `HASH_B` in the trail and failed — on a write the test
 * itself had caused. A constant that collides with fixture data makes an
 * absence assertion untrustworthy in both directions.
 */
const HASH_A = 'a1'.repeat(32);
const HASH_B = 'b2'.repeat(32);
const NOTEBOOK_PATH = 'assets:processing_notebook';

/**
 * NOT 64 lowercase hex characters, so `apply_corrections` refuses it — "never
 * overwritten with a bad value" — and the record keeps the hash it already had. The
 * request still reaches that function: the key is a recognised asset uri, so it is not
 * the 422 an unrecognised field would get. The reply is a 200 with `rev` unmoved.
 *
 * Short on purpose: `answerValuePreview` renders 20 characters or fewer verbatim, so a
 * false claim would appear as this exact string rather than a truncated prefix.
 */
const MALFORMED_HASH = 'not-a-valid-sha256';

/** Answer the current Asset Hash question, and wait for its answered row. */
async function answerAssetHash(page: import('@playwright/test').Page, hash: string) {
  await page.getByLabel('Asset Hash').fill(hash);
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByRole('button', { name: 'Edit Asset Hash' })).toBeVisible();
}

/** The inline editor for the (single) answered row. Scoped, because the still-open
 *  question below renders its own identically-labelled input. */
const editor = (page: import('@playwright/test').Page) => page.locator('.answered-editing');

test.describe('R4 · edit', () => {
  test('a valid correction is saved, reported as a change, and survives a reload', async ({
    page,
    server,
    calls,
  }) => {
    await openComplete(page, SEED.fresh);
    await answerAssetHash(page, HASH_A);
    const answered = await server.read(SEED.fresh);

    await page.getByRole('button', { name: 'Edit Asset Hash' }).click();
    await editor(page).getByLabel('Asset Hash').fill(HASH_B);
    await editor(page).getByRole('button', { name: 'Save' }).click();
    await expect(editor(page)).toHaveCount(0);

    // A real correction request left the page — the edit route is its own endpoint,
    // not a second answer.
    expect(calls.postsTo('/edit'), 'a correction must go to /edit').not.toHaveLength(0);

    // INDEPENDENT server read: the record moved, the value is the correction, and no
    // question was reopened or invented by the correction.
    await expect
      .poll(async () => (await server.read(SEED.fresh)).rev, {
        message: 'the correction never reached the server',
      })
      .toBe(answered.rev + 1);
    const after = await server.read(SEED.fresh);
    expect(after.pendingIds, 'a correction must never reopen or create a question').toEqual(
      answered.pendingIds
    );
    expect((await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH))?.value).toBe(HASH_B);

    // The screen states the server-reported downstream impact rather than deriving
    // one locally.
    await expect(page.locator('.edit-impact')).toBeVisible();

    // DURABILITY: a full reload, a fresh mount, a fresh fetch.
    await page.reload();
    await expect(page.getByRole('heading', { name: /Answer \d+ Question/ })).toBeVisible();
    const reloaded = await server.read(SEED.fresh);
    expect(reloaded.rev).toBe(after.rev);
    expect((await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH))?.value).toBe(HASH_B);
  });

  test('a correction the core refuses claims no confirmation, keeps the recorded value, and keeps the editor open', async ({
    page,
    server,
  }) => {
    /*
     * THE DEFECT THIS GUARDS, reachable with no tampering at all. `saveEdit` used to
     * rewrite the summary row to the typed value on any RESOLVED promise, i.e. it read
     * HTTP 200 as proof of a write. `apply_corrections` refuses a malformed sha256 and
     * leaves the stored hash alone, returning 200 with `rev` unmoved — so the row read
     * "Asset Hash / you answered not-a-valid-sha256 / Confirmed by You" while the server
     * still held HASH_A. A "Confirmed by You" chip over a value the truth core refused
     * is a false claim of confirmed authority over a scientific value.
     *
     * Real UI, real backend: no route interception and no synthesised response.
     */
    await openComplete(page, SEED.fresh);
    await answerAssetHash(page, HASH_A);
    const answered = await server.read(SEED.fresh);

    const statuses: number[] = [];
    page.on('response', (res) => {
      if (res.request().method() === 'POST' && res.url().includes('/edit')) {
        statuses.push(res.status());
      }
    });

    await page.getByRole('button', { name: 'Edit Asset Hash' }).click();
    await editor(page).getByLabel('Asset Hash').fill(MALFORMED_HASH);
    await editor(page).getByRole('button', { name: 'Save' }).click();

    // The correction was ACCEPTED as a request and applied to nothing — a 200 the client
    // had to interpret, not an error it could lean on.
    await expect
      .poll(() => statuses.length, { message: 'the correction never left the page' })
      .toBe(1);
    expect(statuses[0], 'a recognised key with a refused value is a 200, not a 4xx').toBe(200);

    // The screen says nothing was applied, and names no cause — the response carries
    // none. (`invalidation.reason` claims "the submitted value was identical", which is
    // false here; it must not be surfaced.)
    const note = editor(page).locator('.completion-submit-error');
    await expect(note).toContainText('Nothing was applied');
    await expect(note).toContainText('previously confirmed value');
    await expect(note).not.toContainText(/identical|malformed|invalid/i);

    // The editor stays open with the typed value, as on a 412 — the correction can be
    // retried without retyping — and no impact note claims a downstream change.
    await expect(editor(page)).toHaveCount(1);
    await expect(editor(page).getByLabel('Asset Hash')).toHaveValue(MALFORMED_HASH);
    await expect(page.locator('.edit-impact')).toHaveCount(0);

    // NOTHING WAS WRITTEN: the record still holds the hash it was given.
    const after = await server.read(SEED.fresh);
    expect(after.rev, 'a refused correction must not advance the revision').toBe(answered.rev);
    expect((await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH))?.value).toBe(HASH_A);
    expect(JSON.stringify(await server.evidence(SEED.fresh))).not.toContain(MALFORMED_HASH);

    // Cancel restores the summary, and the confirmation chip sits over the value the
    // SERVER holds — never over the one it refused.
    await editor(page).getByRole('button', { name: 'Cancel' }).click();
    await expect(editor(page)).toHaveCount(0);
    const row = page.locator('.answered-row').first();
    await expect(row.getByText('Confirmed by You')).toBeVisible();
    await expect(row.locator('.answered-stored')).toContainText('a1a1a1a1');
    await expect(row.locator('.answered-stored')).not.toContainText(MALFORMED_HASH);

    // RECOVERY: a well-formed correction on the same visit still lands, so the guard
    // refuses the bad write without wedging the editor.
    await page.getByRole('button', { name: 'Edit Asset Hash' }).click();
    await editor(page).getByLabel('Asset Hash').fill(HASH_B);
    await editor(page).getByRole('button', { name: 'Save' }).click();
    await expect(editor(page)).toHaveCount(0);
    await expect
      .poll(async () => (await server.read(SEED.fresh)).rev, {
        message: 'the retry after a refused correction never landed',
      })
      .toBe(answered.rev + 1);
    expect((await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH))?.value).toBe(HASH_B);
  });

  test('Cancel abandons a correction with no request and no change', async ({
    page,
    server,
    calls,
  }) => {
    await openComplete(page, SEED.fresh);
    await answerAssetHash(page, HASH_A);
    const answered = await server.read(SEED.fresh);

    await page.getByRole('button', { name: 'Edit Asset Hash' }).click();
    await editor(page).getByLabel('Asset Hash').fill(HASH_B);
    // The secondary control in edit mode is Cancel — the SAME button that is
    // "I don't know" when answering, relabelled. It must not write.
    await editor(page).getByRole('button', { name: 'Cancel' }).click();

    await expect(editor(page), 'Cancel must restore the read-only summary').toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Edit Asset Hash' })).toBeVisible();

    expect(calls.postsTo('/edit'), 'Cancel must send nothing').toHaveLength(0);
    const after = await server.read(SEED.fresh);
    expect(after.rev).toBe(answered.rev);
    expect((await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH))?.value).toBe(HASH_A);
  });

  test('a correction against a record that moved is refused, applies nothing, and keeps the typed input', async ({
    page,
    server,
  }) => {
    /*
     * Same mechanism as the stale ANSWER (`answer-errors.spec.ts`): this screen keeps
     * its If-Match token across a change signal on purpose, so the correction carries
     * a genuinely stale validator and the 412 is the backstop.
     *
     * WHAT THIS TEST DOES NOT CLAIM: that the correction can be retried after
     * Refresh. It cannot, in this visit — Refresh remounts the screen, the visit's
     * `answered` list starts empty again, and with it the Edit affordance. That is a
     * product limitation, stated in the report, not something to assert as correct.
     */
    await openComplete(page, SEED.fresh);
    await answerAssetHash(page, HASH_A);
    const answered = await server.read(SEED.fresh);

    await page.getByRole('button', { name: 'Edit Asset Hash' }).click();
    await editor(page).getByLabel('Asset Hash').fill(HASH_B);

    // A different client writes; the token this page holds is now stale.
    await server.answerBehindTheUi(SEED.fresh);
    const moved = await server.read(SEED.fresh);
    expect(moved.rev).toBeGreaterThan(answered.rev);

    await editor(page).getByRole('button', { name: 'Save' }).click();

    // The editor stays mounted with the input, and the refusal says what happened.
    await expect(editor(page), 'a refused correction must not close the editor').toHaveCount(1);
    await expect(editor(page).getByLabel('Asset Hash')).toHaveValue(HASH_B);
    const banner = editor(page).locator('.completion-submit-error');
    await expect(banner).toContainText('This record changed elsewhere');
    await expect(banner).toContainText('Nothing was applied');

    // NOTHING WAS APPLIED: the other client's write stands, the correction did not.
    const after = await server.read(SEED.fresh);
    expect(after.rev).toBe(moved.rev);
    expect((await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH))?.value).toBe(HASH_A);
    expect(JSON.stringify(await server.evidence(SEED.fresh))).not.toContain(HASH_B);

    // Refresh returns the screen to the CURRENT state rather than merging anything.
    await banner.getByRole('button', { name: 'Refresh' }).click();
    await expect(editor(page)).toHaveCount(0);
    const settled = await server.read(SEED.fresh);
    expect(settled.rev, 'Refresh must read, not write').toBe(moved.rev);
  });

  test('navigating away from an open editor discards the unsaved input and persists nothing', async ({
    page,
    server,
    calls,
  }) => {
    await openComplete(page, SEED.fresh);
    await answerAssetHash(page, HASH_A);
    const answered = await server.read(SEED.fresh);

    await page.getByRole('button', { name: 'Edit Asset Hash' }).click();
    await editor(page).getByLabel('Asset Hash').fill(HASH_B);

    // Leave through the screen's own control, then come back.
    await page.getByRole('button', { name: '← Back to Review Record' }).click();
    await expect(page).toHaveURL(new RegExp(`/record/${SEED.fresh}$`));
    await openComplete(page, SEED.fresh);

    // The unsaved correction is gone — not silently saved, and not silently restored
    // as though it had been.
    expect(calls.postsTo('/edit'), 'leaving a screen must not save what was typed on it').toHaveLength(0);
    await expect(editor(page)).toHaveCount(0);
    const after = await server.read(SEED.fresh);
    expect(after.rev).toBe(answered.rev);
    expect((await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH))?.value).toBe(HASH_A);

    // The CONFIRMED answer is still confirmed — a new visit reads it from the server,
    // so the field is no longer among the open questions.
    expect(after.pendingIds).not.toContain(
      'ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb'
    );
    // ...and the visit-scoped answered list starts empty, so the screen makes no
    // claim about a review it cannot keep.
    await expect(page.locator('.answered-row')).toHaveCount(0);
  });
});

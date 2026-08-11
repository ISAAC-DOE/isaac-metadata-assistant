/**
 * R4 · EVIDENCE, through the real UI against the real backend.
 *
 * There is no "add evidence" button in this app, and that is the point: evidence is
 * a CONSEQUENCE of confirming a value. So every test here drives the ordinary
 * completion flow and then asks the evidence plane what it now holds — the trail
 * endpoint, and the Evidence & File Preview screen that renders it.
 *
 * What each test protects, stated so nobody "simplifies" one into uselessness:
 *
 *   · a confirmation must LEAVE A CITATION, and the citation must name the human
 *     confirmation alongside the machine lead rather than replacing it;
 *   · the citation must be DURABLE — proven by a full reload and an independent
 *     server read, never by the component that just wrote it;
 *   · a correction must REPLACE the evidence, so no superseded value survives
 *     anywhere in the trail;
 *   · a value the truth core REFUSES must leave the trail exactly as it was.
 *
 * Every test runs in a worked-example session of its own (see
 * `own-session-fixtures.ts`) and disposes it.
 */

import {
  SEED,
  expect,
  openComplete,
  openEvidence,
  test,
  trailKeys,
} from './own-session-fixtures';

/** The evidence path the FIRST open blocker on `SEED.fresh` writes to. Read off the
 *  live API, not guessed: the first blocker is the processing-notebook asset. */
const NOTEBOOK_PATH = 'assets:processing_notebook';

const HASH_A = 'c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345';
const HASH_B = 'd4c0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b999';

/** Confirm the current Asset Hash question through the visible controls. */
async function confirmAssetHash(page: import('@playwright/test').Page, hash: string) {
  const field = page.getByLabel('Asset Hash');
  await expect(field).toBeVisible();
  await field.fill(hash);
  await page.getByRole('button', { name: 'Confirm' }).click();
}

/** Open the Evidence screen and select one trail entry by its key. */
async function selectTrailEntry(page: import('@playwright/test').Page, key: string) {
  const rail = page.getByRole('complementary', { name: 'Evidence Trail' });
  const entry = rail.getByRole('button').filter({ hasText: key });
  await expect(entry, `no trail entry for ${key}`).toHaveCount(1);
  await entry.click();
  await expect(page.locator('.sidecar-entry-tag')).toHaveText(key);
}

test.describe('R4 · evidence', () => {
  test('confirming an answer adds THAT path to the evidence trail, cited as a human confirmation, and it survives a reload', async ({
    page,
    server,
    calls,
  }) => {
    const start = await server.read(SEED.fresh);
    const before = await server.evidencePaths(SEED.fresh);
    expect(
      before.has(NOTEBOOK_PATH),
      'this test needs the notebook asset to carry NO evidence yet'
    ).toBe(false);

    // The trail on screen agrees with the server before anything is written — so a
    // later difference is a difference the write caused.
    await openEvidence(page, SEED.fresh);
    expect(await trailKeys(page)).not.toContain(NOTEBOOK_PATH);

    await openComplete(page, SEED.fresh);
    await confirmAssetHash(page, HASH_A);
    await expect
      .poll(() => calls.postsTo('/answers').length, {
        message: 'no POST to /answers was observed — the UI may have updated only itself',
      })
      .toBeGreaterThan(0);
    // AND WAIT FOR THE WRITE TO LAND, which the line above does NOT prove: `calls`
    // counts REQUESTS, so reading the trail immediately after it races the response.
    // (Observed as an intermittent failure of the set assertion below during a
    // negative-control run, which is how it was found.)
    await expect
      .poll(async () => (await server.read(SEED.fresh)).rev, {
        message: 'the confirmed answer never reached the server',
      })
      .toBe(start.rev + 1);

    // INDEPENDENT server read: the trail gained exactly this path, and nothing else
    // was disturbed. A SET difference, not a count.
    const after = await server.evidencePaths(SEED.fresh);
    expect([...after].filter((p) => !before.has(p))).toEqual([NOTEBOOK_PATH]);
    expect([...before].filter((p) => !after.has(p)), 'no existing citation may be lost').toEqual([]);

    // The citation names BOTH sources: the machine lead that found the asset, and the
    // human who supplied the hash. Replacing one with the other would be a loss of
    // provenance that no count would notice.
    const entry = await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH);
    expect(entry?.value).toBe(HASH_A);
    const kinds = new Set((entry?.evidence ?? []).map((e) => e.source_type));
    expect(kinds).toEqual(new Set(['file_listing', 'user_confirmation']));
    expect(
      (entry?.evidence ?? []).find((e) => e.source_type === 'user_confirmation')?.answer,
      'the confirmation must record the value the reader actually typed'
    ).toBe(HASH_A);

    // DURABILITY: a fresh navigation, a fresh mount, a fresh fetch.
    await openEvidence(page, SEED.fresh);
    await page.reload();
    await expect(page.getByRole('complementary', { name: 'Evidence Trail' })).toBeVisible();
    expect(await trailKeys(page)).toContain(NOTEBOOK_PATH);

    await selectTrailEntry(page, NOTEBOOK_PATH);
    // The screen states the two-source provenance in words, and shows the confirmed
    // hash in full rather than only a truncated preview.
    await expect(page.locator('.preview-prov-text')).toContainText(
      'Two sources are preserved side by side'
    );
    await expect(page.locator('.sidecar-entry')).toContainText(HASH_A);
    await expect(page.locator('.sidecar-entry .src-token')).toContainText(['file_listing', 'user_confirmation']);
  });

  test("correcting a confirmed value moves the field's VALUE to the correction and keeps the superseded answer only as a dated citation", async ({
    page,
    server,
  }) => {
    /*
     * THE TITLE IS NARROWER THAN THE ONE THIS TEST WAS FIRST GIVEN, because the first
     * one was wrong. It said the superseded value is "nowhere in the trail"; it is in
     * the trail, and deliberately so. `apply_corrections` APPENDS a second
     * `user_confirmation` — worded "Correct the sha256 of …" and separately
     * timestamped — beside the original, so the record keeps a history of who
     * confirmed what and when.
     *
     * So the property that actually matters is not absence but AUTHORITY: exactly one
     * thing may be the field's value, and it must be the correction. The old answer
     * may persist as a citation; it may not persist as the value.
     */
    await openComplete(page, SEED.fresh);
    await confirmAssetHash(page, HASH_A);
    await expect(page.getByRole('button', { name: 'Edit Asset Hash' })).toBeVisible();
    expect((await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH))?.value).toBe(HASH_A);

    // The correction, through the visible controls: Edit re-opens the same card
    // prefilled, and Save writes it.
    await page.getByRole('button', { name: 'Edit Asset Hash' }).click();
    // SCOPED to the inline editor. The record still has open questions, so the
    // unanswered one below renders its own "Asset Hash" input — an unscoped query
    // matches both and would silently be able to edit the wrong field.
    const editor = page.locator('.answered-editing');
    const field = editor.getByLabel('Asset Hash');
    await expect(field, 'the editor must start from the value already confirmed').toHaveValue(HASH_A);
    await field.fill(HASH_B);
    await editor.getByRole('button', { name: 'Save' }).click();
    await expect(editor, 'a saved correction must close the editor').toHaveCount(0);

    await expect
      .poll(async () => (await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH))?.value, {
        message: 'the correction never reached the evidence trail',
      })
      .toBe(HASH_B);

    // THE AUTHORITY ASSERTION. The superseded answer survives as HISTORY — one
    // citation each, distinguishable by their own wording — and the correction is the
    // only one that is also the field's value.
    const entry = await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH);
    const confirmations = (entry?.evidence ?? []).filter(
      (e) => e.source_type === 'user_confirmation'
    ) as { answer?: unknown; question?: string }[];
    expect(
      confirmations.map((c) => c.answer),
      'both confirmations must be kept, in the order they happened'
    ).toEqual([HASH_A, HASH_B]);
    expect(
      confirmations.find((c) => c.answer === HASH_B)?.question,
      'the correction must be recorded AS a correction, not as a second original answer'
    ).toMatch(/^Correct the sha256/);
    expect(entry?.value, 'only the correction may be the value').toBe(HASH_B);

    // No OTHER field picked up the old hash — a correction must not smear across the
    // trail.
    const elsewhere = (await server.evidence(SEED.fresh))
      .filter((e) => e.path !== NOTEBOOK_PATH)
      .filter((e) => JSON.stringify(e).includes(HASH_A));
    expect(elsewhere.map((e) => e.path), 'the superseded hash leaked into another field').toEqual([]);

    // And the screen agrees after a full reload: the rendered VALUE of the entry —
    // the field the sidecar block puts at the top, above the citations — is the
    // correction, never the superseded answer.
    await openEvidence(page, SEED.fresh);
    await page.reload();
    await selectTrailEntry(page, NOTEBOOK_PATH);
    const renderedValue = page.locator('.sidecar-entry > .sidecar-kv .hash');
    await expect(renderedValue).toHaveCount(1);
    await expect(renderedValue).toHaveText(`"${HASH_B}"`);
  });

  test('a correction the truth core refuses writes nothing — the trail still cites the confirmed value', async ({
    page,
    server,
  }) => {
    /*
     * `apply_corrections` never invents: a malformed sha256 leaves the stored value
     * as it was. The property this test pins is the DURABLE one — the record and its
     * evidence are unchanged, and a reader who reloads sees the value that is
     * actually stored.
     *
     * THE WAYPOINT BELOW USED TO BE `expect(getByRole('button', {name: 'Edit Asset
     * Hash'})).toBeVisible()`, with the comment "The editor closes, so the request
     * completed". That was true of the behaviour at the time and was the WRONG thing to
     * wait on: the editor closed because `saveEdit` treated the 200 as proof of a write
     * — the same defect that then rewrote the row to the refused value under a
     * "Confirmed by You" chip. The old note here ("what the screen does BEFORE that
     * reload … is deliberately not asserted here as though it were correct") was
     * pointing at exactly that.
     *
     * The editor now stays open on a refused correction, so the request's completion is
     * waited on through the screen's own report of the outcome, and the pre-reload state
     * is asserted rather than deferred. Strictly stronger: it pins that the request
     * finished AND that nothing was claimed. `edit.spec.ts` owns the full behaviour of
     * that state; this file keeps its focus on the evidence trail.
     *
     * THE WAYPOINT MOVED AGAIN, for the same reason it moved the first time: it was
     * matching a SENTENCE, and the sentence changed when the server started refusing
     * this request with 422 `invalid_field_value` instead of absorbing it with a 200.
     * The durable property under test — the record and its evidence unchanged, the trail
     * still citing HASH_A — never changed and is asserted below unaltered.
     *
     * SO IT NO LONGER MATCHES PROSE. Twice is a pattern, and the third time was
     * predictable: this test does not care what the notice SAYS, only that the refusal
     * has been reported and the request is therefore finished. It now waits on
     * `data-testid="edit-unstorable-notice"`, which is rendered only by the
     * `invalid_field_value` branch — so the waypoint still cannot be satisfied by a
     * generic error, and rewording the copy cannot break this file again.
     * `edit.spec.ts` owns the wording, and asserts it there.
     */
    await openComplete(page, SEED.fresh);
    await confirmAssetHash(page, HASH_A);
    await expect(page.getByRole('button', { name: 'Edit Asset Hash' })).toBeVisible();
    const confirmed = await server.read(SEED.fresh);

    await page.getByRole('button', { name: 'Edit Asset Hash' }).click();
    const editor = page.locator('.answered-editing');
    await editor.getByLabel('Asset Hash').fill('not-a-valid-sha256');
    await editor.getByRole('button', { name: 'Save' }).click();

    await expect(editor.getByTestId('edit-unstorable-notice')).toBeVisible();
    await expect(
      page.locator('.answered-stored'),
      'the refused value must never be shown as an answer'
    ).toHaveCount(0);
    const after = await server.read(SEED.fresh);
    expect(after.rev, 'a refused correction must not count as a write').toBe(confirmed.rev);
    expect(after.pendingIds).toEqual(confirmed.pendingIds);

    const entry = await server.evidenceFor(SEED.fresh, NOTEBOOK_PATH);
    expect(entry?.value, 'the refused value must not have replaced the confirmed one').toBe(HASH_A);
    expect(JSON.stringify(await server.evidence(SEED.fresh))).not.toContain('not-a-valid-sha256');

    // A reader who reloads is shown the stored truth, not the refused input.
    await openEvidence(page, SEED.fresh);
    await selectTrailEntry(page, NOTEBOOK_PATH);
    await expect(page.locator('.sidecar-entry')).toContainText(HASH_A);
    await expect(page.locator('.sidecar-entry')).not.toContainText('not-a-valid-sha256');
  });

  test('a write that never reaches the server leaves no evidence behind and says so', async ({
    page,
    server,
    failNextOnce,
  }) => {
    const before = await server.read(SEED.fresh);
    const beforePaths = await server.evidencePaths(SEED.fresh);

    await openComplete(page, SEED.fresh);
    // A TRANSPORT failure, not a synthesised error body: the condition the real
    // backend cannot be asked to produce, and the one that used to be swallowed.
    await failNextOnce('/answers');
    await confirmAssetHash(page, HASH_A);

    // The screen must SAY the write failed. Either honest form is accepted — the
    // record-level error, or the backend-unreachable panel — but silence is not.
    await expect(
      page.locator('.completion-submit-error, .fetch-state.error').first(),
      'a failed confirmation must be visible to the reader'
    ).toBeVisible();

    // Nothing was written, and no citation was invented for a value that never
    // arrived.
    const after = await server.read(SEED.fresh);
    expect(after.rev).toBe(before.rev);
    expect(after.pendingIds).toEqual(before.pendingIds);
    expect(await server.evidencePaths(SEED.fresh)).toEqual(beforePaths);

    // RECOVERY: the same click, once the transport is healthy again, works — the
    // failure left the form usable rather than wedged.
    await page.getByRole('button', { name: 'Confirm' }).click();
    await expect
      .poll(async () => (await server.evidencePaths(SEED.fresh)).has(NOTEBOOK_PATH), {
        message: 'the retry after a transport failure never landed',
      })
      .toBe(true);
    expect((await server.read(SEED.fresh)).rev).toBe(before.rev + 1);
  });
});

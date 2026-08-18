/**
 * R4 · EXPORT — the arms `export.spec.ts` does not cover: repairing into a valid
 * export, and the two preconditions that must refuse it.
 *
 * `export.spec.ts` owns "an incomplete record is not exportable", "a ready record
 * exports and survives a reload", and "a second export is refused". This file owns:
 *
 *   · the REPAIR — an incomplete record made complete through the visible controls,
 *     after which the gate opens and the artifacts written are the ones the screen
 *     then shows;
 *   · a MISSING precondition — the write refuses (428) and nothing is written;
 *   · a STALE precondition — the write refuses (412), nothing is written, and the
 *     screen's own Refresh-then-export recovery works.
 *
 * ON THE TWO PRECONDITION TESTS. This UI always sends the token it is holding, and
 * the export screen adopts a fresh one within a poll interval of any change, so
 * neither refusal can be produced by clicking alone. Both are reached by rewriting
 * the `If-Match` HEADER of the outgoing request — a stand-in for a client that lost
 * or stale-cached its token. Nothing is mocked: the 428/412 and every state
 * assertion below come from the real backend.
 *
 * NOT COVERED HERE, deliberately: the export crash-wedge (an orphan artifact on disk
 * with the state still saying not-exported). Producing it requires reaching into the
 * workspace filesystem behind the app, which a browser spec has no honest way to do;
 * `apps/api/tests/test_export_recovery.py` pins every state x file combination
 * directly. See the report.
 *
 * Every test runs in its own worked-example session and disposes it.
 */

import { SEED, expect, openExport, test } from './own-session-fixtures';

/**
 * Replace the headers of the next matching request ONCE, then let the real server
 * answer it. `fallback` (not `continue`) so the scope fixture's handler, registered
 * first and therefore running last, still attaches the session header.
 */
async function rewriteNextHeaders(
  page: import('@playwright/test').Page,
  urlFragment: string,
  rewrite: (headers: Record<string, string>) => Record<string, string>
) {
  // (see `setIfMatch` for the case-sensitivity trap this composes with)
  let fired = false;
  await page.route(
    (url) => url.href.includes(urlFragment),
    async (route) => {
      if (fired) return route.fallback();
      if (route.request().method() !== 'POST') return route.fallback();
      fired = true;
      await route.fallback({ headers: rewrite(route.request().headers()) });
    }
  );
}

/**
 * Replace `If-Match` (or remove it, with `null`) in a header map, CASE-INSENSITIVELY.
 *
 * `route.request().headers()` returns lower-cased names. Spreading that map and then
 * adding a canonically-cased `'If-Match'` leaves BOTH keys in the object, the request
 * goes out with two, and the server reads the original — so the tamper silently does
 * nothing and the test passes for the wrong reason. It did exactly that on the first
 * run of the 412 case below (observed: 200, not 412).
 */
function setIfMatch(headers: Record<string, string>, token: string | null): Record<string, string> {
  const next: Record<string, string> = {};
  for (const [k, v] of Object.entries(headers)) {
    if (k.toLowerCase() !== 'if-match') next[k] = v;
  }
  if (token !== null) next['If-Match'] = token;
  return next;
}

const exportButton = (page: import('@playwright/test').Page) =>
  page.getByRole('button', { name: /Export Official Record/i });

test.describe('R4 · export, repaired and refused', () => {
  test('repairing an incomplete record through the UI opens the gate, and the export writes the artifacts the screen then shows', async ({
    page,
    server,
    calls,
  }) => {
    const before = await server.read(SEED.partial);
    expect(before.pendingIds, 'this test needs record 2 at its structured baseline').toEqual([
      'series',
      'descriptor',
    ]);
    expect(before.exported).toBe(false);

    // The gate is shut, and the screen says how many fields are holding it shut.
    await openExport(page, SEED.partial);
    await expect(page.locator('.preexport-gate')).toContainText('2 fields still block export');
    await expect(exportButton(page), 'no export control may exist while the gate is shut').toHaveCount(0);

    // THE REPAIR, through the visible controls. Both remaining blockers are
    // structured, so each is staged from its labelled example value and confirmed —
    // the assistant never types a scientific value.
    await page.locator('.preexport-gate').getByRole('button', { name: 'Back to Complete →' }).click();
    await expect(page.getByRole('heading', { name: /Answer 2 Questions/ })).toBeVisible();
    /*
     * THE LOOP USED TO RACE THE REMOUNT, and it cost a 60-second timeout roughly one
     * run in several — including on two branches whose diffs could not possibly have
     * caused it (a read-only spec file, and a change to the demo-runner stage type).
     * That is what made it look like flake rather than a defect worth reading.
     *
     * The mechanism, from the failure's own call log: after the first `Confirm`,
     * `GuidedPrompt` remounts under a new `key` (the next blocker's id). The next
     * iteration's `Use This Value` click resolves against whichever copy is present
     * at that instant — sometimes the DETACHING one — so the new question is left
     * with nothing staged. `Confirm` is then correctly `disabled`, because
     * `canConfirm` is false with no value staged, and Playwright retries a click on a
     * button the product is right to keep disabled until the 60s ceiling. The log
     * shows exactly that: `<button disabled ...>Confirm</button>`, element not
     * enabled, retried to death.
     *
     * So this is a TEST race, not a product bug — the product's refusal to enable
     * Confirm without a staged value is the behaviour we want. The fix is to wait for
     * each question to actually BE the current one, and for the staging to have
     * taken, before acting. `toBeEnabled()` is the load-bearing wait: it is the
     * observable signal that `Use This Value` reached the component that is now
     * mounted.
     */
    /*
     * WAIT ON THE OBSERVABLES THAT ACTUALLY MOVE — and the previous two attempts at
     * this loop are worth recording, because both were wrong in instructive ways.
     *
     * The race is real. `confirmAnswer` keeps the SAME `GuidedPrompt` mounted
     * (`key={blocker.id}`) for the whole in-flight POST, so `.first()` deterministically
     * resolves to the PREVIOUS prompt while that POST is unresolved. The click re-stages
     * the old value; the remount then resets `staged`, and `Confirm` is disabled forever.
     * Note what this is NOT: not a "detaching copy", which is what the second attempt's
     * comment claimed.
     *
     * ATTEMPT 1 asserted a heading `Answer ${n} Questions`. The heading renders
     * `Answer {total} Questions` and `total` is CONSTANT for the screen's life, so it
     * passed once and failed once. CI caught it.
     *
     * ATTEMPT 2 waited for `Use This Value` and `Confirm` to be enabled, and its comment
     * called `toBeEnabled()` "the observable signal that Use This Value reached the
     * component that is now mounted". THAT WAS FALSE: `Use This Value` has no `disabled`
     * prop at all, so the wait is satisfied the instant the button attaches and signals
     * nothing. An independent review proved it by forcing the window open with a 1000ms
     * route delay on `POST .../answers` — 27 polls against a disabled `Confirm` with
     * nothing staged. It converted a 60s mystery timeout into a 15s named failure, which
     * is a real diagnostic gain and no fix at all.
     *
     * THIS version waits on two things that genuinely move, both proved to pass under
     * that same forced delay:
     *   . `.completion-counter` — counts up as questions close, so it establishes that
     *     the PREVIOUS answer landed and this iteration is acting on a new question.
     *     (The heading does not; the counter does.)
     *   . `.guided-staged` — the "Ready to confirm" status the prompt renders only once
     *     a value is staged. This is the staging observable attempt 2 claimed to use.
     */
    for (let i = 0; i < 2; i++) {
      await expect(page.locator('.completion-counter')).toHaveText(`${i} / 2`);
      await page.getByRole('button', { name: 'Use This Value' }).first().click();
      await expect(
        page.locator('.guided-staged'),
        'a value must be staged before Confirm is pressed: an unstaged Confirm is ' +
          'legitimately disabled, and clicking it proves nothing',
      ).toBeVisible();
      await page.getByRole('button', { name: 'Confirm' }).click();
    }
    await expect(page.getByRole('heading', { name: 'All Fields Resolved' })).toBeVisible();
    expect((await server.read(SEED.partial)).pendingIds, 'the repair must close both questions').toEqual([]);

    // Back to the gate through the screen's own route.
    await page.getByRole('button', { name: 'Go to Ready to Export →' }).click();
    await expect(page.locator('.preexport-ready')).toBeVisible();
    await expect(exportButton(page)).toBeEnabled();
    await exportButton(page).click();

    await expect
      .poll(() => calls.postsTo('/export').length, { message: 'no POST to /export was observed' })
      .toBeGreaterThan(0);
    await expect
      .poll(async () => (await server.read(SEED.partial)).exported, {
        message: 'the export did not reach server state',
      })
      .toBe(true);

    // STATE AND ARTIFACT AGREE. Not just "exported: true" — the pair is on disk, it
    // is not flagged stale, and the record it wrote is this record.
    const written = await server.artifacts(SEED.partial);
    expect(written.record, 'an exported record must have a readable record artifact').toBeTruthy();
    expect(written.sidecar, 'an exported record must have a readable sidecar').toBeTruthy();
    expect(written.artifact.state, 'a just-written artifact must not be stale').not.toBe('stale');
    expect(written.record?.record_id).toBe(SEED.partial);

    // And the screen shows the SAME artifact it just wrote — the reserved verdict,
    // both artifact cards, and the record JSON with the matching id.
    await expect(page.locator('.verdict')).toHaveAttribute('aria-label', 'Validation PASS');
    await expect(page.locator('.artifact-row section.artifact')).toHaveCount(2);
    await page
      .locator('section.artifact')
      .filter({ hasText: `${SEED.partial}.json` })
      .first()
      .getByRole('button', { name: 'View' })
      .click();
    await expect(page.getByRole('dialog')).toContainText(`"record_id": "${SEED.partial}"`);
  });

  test('an export sent without its precondition is refused (428) and writes nothing', async ({
    page,
    server,
  }) => {
    await server.answerEverything(SEED.partial);
    const before = await server.read(SEED.partial);
    expect(before.pendingIds).toEqual([]);
    expect(before.exported).toBe(false);

    const statuses: number[] = [];
    page.on('response', (res) => {
      if (res.request().method() === 'POST' && res.url().includes('/export')) {
        statuses.push(res.status());
      }
    });

    await openExport(page, SEED.partial);
    // Drop the precondition on the way out — a client that lost its token.
    await rewriteNextHeaders(page, '/export', (headers) => setIfMatch(headers, null));

    await expect(exportButton(page)).toBeEnabled();
    await exportButton(page).click();

    await expect.poll(() => statuses.length, { message: 'the export never left the page' }).toBe(1);
    expect(
      statuses[0],
      'an export with no precondition must be refused with 428, never performed'
    ).toBe(428);

    // NOTHING WAS WRITTEN — no record id, no artifact pair, no revision.
    const after = await server.read(SEED.partial);
    expect(after.exported, 'a refused export must not produce an official record').toBe(false);
    expect(after.rev).toBe(before.rev);
    const artifacts = await server.artifacts(SEED.partial);
    expect(artifacts.record, 'a refused export must leave no record artifact').toBeNull();
    expect(artifacts.sidecar, 'a refused export must leave no sidecar').toBeNull();
  });

  test('an export carrying a token from before the record moved is refused (412), writes nothing, and Refresh-then-export succeeds', async ({
    page,
    server,
  }) => {
    // The token as it was BEFORE the record was completed. Nothing synthetic about
    // it — it is the validator the record really had, and it really is superseded by
    // the time the export below is sent.
    const beforeRepair = await server.read(SEED.partial);
    const supersededToken = beforeRepair.version;

    await server.answerEverything(SEED.partial);
    const ready = await server.read(SEED.partial);
    expect(ready.exported).toBe(false);
    expect(
      ready.version,
      'the setup must actually have moved the record, or there is no stale token to send'
    ).not.toBe(supersededToken);

    await openExport(page, SEED.partial);
    await rewriteNextHeaders(page, '/export', (headers) => setIfMatch(headers, `"${supersededToken}"`));

    const statuses: number[] = [];
    page.on('response', (res) => {
      if (res.request().method() === 'POST' && res.url().includes('/export')) {
        statuses.push(res.status());
      }
    });

    await expect(exportButton(page)).toBeEnabled();
    await exportButton(page).click();

    await expect.poll(() => statuses.length).toBe(1);
    expect(statuses[0], 'a stale export must be refused, not performed').toBe(412);

    // The screen states the refusal in the terms that matter: nothing was exported,
    // and no record was written.
    const banner = page.locator('.export-conflict');
    await expect(banner).toContainText('Nothing was exported');
    await expect(banner).toContainText('no record was written');

    const afterRefusal = await server.read(SEED.partial);
    expect(afterRefusal.exported).toBe(false);
    expect((await server.artifacts(SEED.partial)).record).toBeNull();

    // RECOVERY, through the control the banner offers.
    await banner.getByRole('button', { name: 'Refresh' }).click();
    await expect(exportButton(page)).toBeEnabled();
    await exportButton(page).click();

    await expect
      .poll(async () => (await server.read(SEED.partial)).exported, {
        message: 'the export after Refresh never landed',
      })
      .toBe(true);
    expect((await server.artifacts(SEED.partial)).record?.record_id).toBe(SEED.partial);
  });
});

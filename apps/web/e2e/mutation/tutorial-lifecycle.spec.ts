/**
 * The worked-example session LIFECYCLE — the scenarios that WRITE.
 *
 * These live in the mutation suite, not beside the other tutorial specs, for the
 * reason this suite exists at all: reset restores five records, completion
 * discards a session, and replay destroys one session and mints another. None of
 * that can share a backend with a read-only suite whose five viewport projects
 * are asserting canonical record CONTENT in parallel.
 *
 * Inside this suite the isolation goes one step further. This file imports `test`
 * from `lifecycle-fixtures.ts`, NOT from `fixtures.ts`, so it does not inherit the
 * auto-use scope that puts a page into the run's shared session — the one
 * `answers.spec.ts` and `export.spec.ts` are mutating to their own baselines. Every
 * session here is opened by this file, through the app's own controls, and disposed
 * by its fixture.
 *
 * Nothing is mocked. `POST /api/tutorial/sessions`, `DELETE …/{id}` and
 * `POST /api/demo/reset` are all really called, by really clicking the app's own
 * controls.
 */

import { expect, test } from './lifecycle-fixtures';
import { MUT_API_BASE, SEED } from './env';

const bar = (page: import('@playwright/test').Page) =>
  page.getByRole('complementary', { name: 'Worked example session' });
const mark = (page: import('@playwright/test').Page) => page.locator('.tutorial-mark');
/** The reset dialog. Matched on `aria-modal`, which the coach mark deliberately
 *  does NOT set — with the walkthrough running there are two `role="dialog"`
 *  elements and a bare role query is ambiguous. */
const MODAL = '[role="dialog"][aria-modal="true"]';

/**
 * Start the walkthrough from My Experiments.
 *
 * IT IS THE EMPTY STATE'S PRIMARY, NOT THE FIRST-RUN OFFER CARD. This suite's
 * ordinary workspace is empty by construction (`globalSetup` asserts it), and
 * `ExperimentsHome` suppresses the offer card whenever the queue has no rows — so that
 * one action is never offered by two primaries at once. `Launch Guided Demo` is the
 * control that is on this screen, and it calls the same `startTutorial`, so every
 * session below is opened by the same code path it always was.
 */
async function startFromEmptyState(page: import('@playwright/test').Page) {
  await page.goto('/experiments', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Launch Guided Demo' }).click();
  await expect(bar(page)).toBeVisible({ timeout: 20_000 });
  await expect(mark(page)).toBeVisible({ timeout: 20_000 });
}

test.describe('worked-example session lifecycle', () => {
  test('Reset Worked Example restores THIS session only — another session is untouched', async ({
    page,
    lifecycle,
  }) => {
    /*
     * The strongest available statement of the isolation claim. The control's own
     * copy says the scope is "a temporary worked-example workspace, belonging to
     * this walkthrough alone" and that "nothing in My Experiments is in this
     * scope". Both halves are asserted:
     *
     *   · a SECOND session, carrying real progress, must come out of this
     *     unchanged — that is what "belonging to this walkthrough alone" means and
     *     it is not provable by only looking at one session;
     *   · the ordinary workspace must still be empty.
     */
    const other = await lifecycle.openSession();
    await lifecycle.answerFirstBlocker(other, SEED.fresh);
    const otherBefore = await lifecycle.readInSession(other, SEED.fresh);
    expect(otherBefore.rev, 'the control session must carry progress worth protecting').toBeGreaterThan(0);

    await startFromEmptyState(page);
    const mine = lifecycle.sessionsCreated()[0];
    expect(mine, 'starting the walkthrough must open a session').toBeTruthy();

    // Put real progress into MY session too, through the API but inside the scope
    // the UI is in — so the reset has something to discard and the at-risk
    // disclosure has something to report.
    await lifecycle.answerFirstBlocker(mine, SEED.fresh);
    const mineBefore = await lifecycle.readInSession(mine, SEED.fresh);
    expect(mineBefore.rev!).toBeGreaterThan(0);

    await bar(page).getByRole('button', { name: /Reset Worked Example/i }).click();

    const dialog = page.locator(MODAL);
    await expect(dialog).toHaveCount(1);
    await expect(dialog).toContainText(/Reset the Worked Example/i);
    // The preview is server-derived and read-only; the disclosure names what would
    // be lost rather than hedging it.
    await expect(dialog.locator('.reset-at-risk')).toContainText(/confirmed answer/i);
    // The scope claim the dialog makes, asserted as rendered text — it must not
    // reacquire the old "shared, hosted example workspace" wording, which is false
    // of a per-walkthrough session.
    await expect(dialog.locator('.reset-disclosure')).toContainText(/temporary worked-example workspace/i);
    // RE-POINTED, and stronger: "Nothing in My Experiments is in this scope" was
    // FALSE — while a walkthrough is open, My Experiments lists these same five
    // records, because the scope changed rather than the screen. The enforced
    // direction is required, the fact the old sentence hid is required, and the
    // false sentence is forbidden.
    await expect(dialog.locator('.reset-disclosure')).toContainText(
      /the ordinary workspace is not in this scope/i
    );
    await expect(dialog.locator('.reset-disclosure')).toContainText(/so they are what is reset/i);
    await expect(dialog.locator('.reset-disclosure')).not.toContainText(
      /Nothing in My Experiments is in this scope/i
    );

    // The typed gate: the destructive button is inert until the phrase is typed.
    const confirm = dialog.getByRole('button', { name: 'Reset Example Records' });
    await expect(confirm).toBeDisabled();
    await dialog.getByRole('textbox').first().fill('RESET');
    await expect(confirm).toBeEnabled();
    await confirm.click();

    // MY session's record is back at its baseline.
    await expect
      .poll(async () => (await lifecycle.readInSession(mine, SEED.fresh)).rev, { timeout: 20_000 })
      .toBe(0);
    const mineAfter = await lifecycle.readInSession(mine, SEED.fresh);
    expect(mineAfter.pendingCount, 'the reset must reopen the questions it discarded').toBe(5);
    const mineList = await lifecycle.listInSession(mine);
    expect(mineList.ids.slice().sort(), 'all five examples must be back').toEqual(
      Object.values(SEED).slice().sort()
    );

    // THE ISOLATION ASSERTION: the other session is exactly as it was.
    const otherAfter = await lifecycle.readInSession(other, SEED.fresh);
    expect(
      otherAfter.rev,
      'resetting one worked-example session must not touch another — the sessions are ' +
        'independent directories and the reset request is scoped to one of them'
    ).toBe(otherBefore.rev);
    expect(otherAfter.pendingCount).toBe(otherBefore.pendingCount);

    // And the ordinary workspace never had anything to lose.
    const ordinary = await page.request.get(`${MUT_API_BASE}/experiments`);
    expect(((await ordinary.json()) as { experiments?: unknown[] }).experiments ?? []).toEqual([]);
  });

  test('finishing the walkthrough records completion AND discards the session', async ({ page, lifecycle }) => {
    // Sixteen steps, several of which navigate to another surface and wait for its
    // fetch, so the default 60s is not enough for a full walk.
    test.setTimeout(180_000);

    await startFromEmptyState(page);
    const session = lifecycle.sessionsCreated()[0];
    await expect(page.locator('.exp-row')).toHaveCount(5);

    // Walk to the end using the real control. `Next` becomes `Finish` on the last
    // step, which is how the walk knows it is done — no step count is hardcoded.
    const next = page.getByRole('button', { name: 'Next', exact: true });
    const finish = page.getByRole('button', { name: 'Finish', exact: true });
    for (let i = 0; i < 40; i++) {
      if (await finish.count()) break;
      await next.click();
      await page.waitForTimeout(150);
    }
    await expect(finish, 'the walkthrough never reached its last step').toBeVisible();
    await finish.click();

    // The completion panel — exactly two actions, and no "reset the workspace"
    // control gained on the last screen.
    const done = page.locator('[data-tutorial-step="complete"]');
    await expect(done).toBeVisible({ timeout: 20_000 });
    await expect(done.getByRole('button', { name: 'Go to My Experiments' })).toBeVisible();
    await expect(done.getByRole('button', { name: 'Replay Tutorial' })).toBeVisible();
    await expect(done.getByRole('button', { name: /Reset/i })).toHaveCount(0);

    // COMPLETION IS RECORDED — and it is recorded before disposal is attempted, so
    // a failed DELETE cannot cost the reader credit for a walkthrough they finished.
    const stored = await page.evaluate(() => localStorage.getItem('isaac.tutorial.v1'));
    expect(stored, 'finishing must record completion in this browser').toBeTruthy();
    expect(JSON.parse(stored!)).toMatchObject({
      tutorialId: 'isaac-guided-walkthrough',
      version: 1,
      completed: true,
    });

    // THE CLEANUP: the session is gone server-side.
    await expect
      .poll(async () => (await lifecycle.listInSession(session)).status, { timeout: 20_000 })
      .toBe(404);

    // "Go to My Experiments" returns the reader to their own workspace — which is
    // empty, because the examples were never in it.
    await done.getByRole('button', { name: 'Go to My Experiments' }).click();
    await expect(page).toHaveURL(/\/experiments$/);
    await expect(page.getByRole('heading', { name: 'No experiments yet' })).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('.exp-row'), 'no example record may survive completion').toHaveCount(0);
    await expect(bar(page)).toHaveCount(0);
    await expect(page.locator('span.mode-chip')).toHaveText('Workspace');

    // And the offer is gone for good in this browser — the completion flag, not a
    // session-scoped dismissal.
    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: 'No experiments yet' })).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('section.tutorial-offer')).toHaveCount(0);
  });

  test('Replay from Settings opens exactly ONE fresh session, with no duplicated examples', async ({
    page,
    lifecycle,
  }) => {
    /*
     * The defect this exists to catch: `startTutorial` discards any session it is
     * already holding BEFORE opening a new one, so replaying can never leave two
     * sessions open or show ten example rows. Both halves are asserted — the count
     * of sessions minted, and the count of rows rendered — because either one alone
     * would pass a build that got the other wrong.
     */
    await startFromEmptyState(page);
    const first = lifecycle.sessionsCreated()[0];
    await expect(page.locator('.exp-row')).toHaveCount(5);

    // Leave, then replay from the permanent home of the control.
    await page.getByRole('button', { name: 'Close Tutorial' }).click();
    await expect(bar(page)).toHaveCount(0);
    await expect
      .poll(async () => (await lifecycle.listInSession(first)).status, { timeout: 20_000 })
      .toBe(404);

    await page.goto('/settings?tab=help', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Replay Tutorial' }).click();
    await expect(bar(page)).toBeVisible({ timeout: 20_000 });

    const sessions = lifecycle.sessionsCreated();
    expect(sessions.length, `replay must mint exactly one more session, got ${sessions.length} in total`).toBe(2);
    const second = sessions[1];
    expect(second).not.toBe(first);

    // FIVE rows, not ten: the fresh session holds one copy of each example, and the
    // discarded session contributes nothing.
    await page.goto('/experiments', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.exp-row')).toHaveCount(5);
    const list = await lifecycle.listInSession(second);
    expect(list.ids.length).toBe(5);
    expect(new Set(list.ids).size, 'no example may appear twice in one session').toBe(5);

    // The examples in the fresh session are at their BASELINE — a replay reseeds a
    // new scope rather than resurrecting the previous one's state.
    const fresh = await lifecycle.readInSession(second, SEED.fresh);
    expect(fresh.rev).toBe(0);
    expect(fresh.pendingCount).toBe(5);

  });

  test('replaying WHILE a session is open discards it first — still exactly one', async ({ page, lifecycle }) => {
    /*
     * The other half of "exactly one session": `startTutorial` calls
     * `disposeTutorialSession()` BEFORE `createTutorialSession()`, so a replay from
     * inside a running walkthrough must leave one session open, not two.
     *
     * WHY THIS WALKS TO THE LAST STEP INSTEAD OF NAVIGATING TO SETTINGS. The
     * obvious route — `page.goto('/settings?tab=help')` mid-walkthrough, then click
     * Replay — CANNOT BE DRIVEN, and the reason is a product behaviour rather than a
     * harness limitation: while the walkthrough is running, `GuidedTutorial`'s
     * second effect navigates back to the current step's own path whenever
     * `here !== targetPath`, so the arrival at Settings is immediately undone and
     * the button is detached mid-click. (Reported: the same mechanism makes the
     * worked-example bar's "Open the Worked Example" button — which navigates to
     * `/load` — unreachable in practice, since the bar renders only while the
     * walkthrough is running.)
     *
     * The LAST step's own surface IS `/settings?tab=help`, and its anchor is that
     * very Replay button. So the reachable way for a reader to replay from inside a
     * walkthrough is to reach the last step, which is what this test does.
     */
    test.setTimeout(180_000);

    await startFromEmptyState(page);
    const first = lifecycle.sessionsCreated()[0];

    const next = page.getByRole('button', { name: 'Next', exact: true });
    for (let i = 0; i < 40; i++) {
      if ((await mark(page).getAttribute('data-tutorial-step')) === 'replay') break;
      await next.click();
      await page.waitForTimeout(150);
    }
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'replay');
    await expect(page).toHaveURL(/\/settings\?tab=help$/);

    // The step's anchor is the real control, and it is the one clicked.
    const replay = page.locator('[data-tutorial-anchor="tutorial-replay"]');
    await expect(replay).toHaveAttribute('data-tutorial-highlight', 'true');
    await replay.click();

    // Back at step one, in a NEW session, with the old one gone.
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'experiments-overview', { timeout: 20_000 });
    const sessions = lifecycle.sessionsCreated();
    expect(sessions.length, `expected exactly two sessions in total, got ${sessions.length}`).toBe(2);
    expect(sessions[1]).not.toBe(first);
    await expect
      .poll(async () => (await lifecycle.listInSession(first)).status, { timeout: 20_000 })
      .toBe(404);
    expect((await lifecycle.listInSession(sessions[1])).status).toBe(200);

    // One copy of each example, in the one live session.
    await expect(page.locator('.exp-row')).toHaveCount(5);
  });
});

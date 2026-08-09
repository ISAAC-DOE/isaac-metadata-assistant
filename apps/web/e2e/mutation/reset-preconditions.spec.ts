/**
 * R4 · RESET — the `plan_digest` precondition, in a real browser.
 *
 * WHAT PYTEST ALREADY PROVES, so that this file does not pretend to.
 * `apps/api/tests/test_reset_safety.py` pins the server side exhaustively and
 * directly: a preview returns a digest; an execute without one is 428 and mutates
 * nothing; a stale one is 412; a record created, removed or exported after the
 * preview makes the token stale; an unchanged workspace keeps its token; the
 * confirmation phrase is checked first; an ambiguous record still refuses 409; the
 * refusal echoes the current token for a one-hop recovery; managed-legacy removal
 * runs under that record's own lock and never holds two at once; `final_count` is
 * MEASURED after the mutation; and a mid-reset failure never reports success. None
 * of that is re-asserted here.
 *
 * WHAT ONLY A BROWSER CAN SHOW, which is what this file is for. The precondition
 * exists because of a HUMAN gap: an operator reads a classification, thinks, and
 * presses the button some seconds later. So the properties under test are the
 * client's half of the contract —
 *
 *   · the digest the dialog sends is the one ITS OWN preview returned, so a
 *     workspace that moved in that gap really is refused;
 *   · the refusal DISARMS the action and re-reads the figures, rather than retrying
 *     with a fresh digest — an auto-retry would reinstate the exact defect the
 *     precondition removes, and no server test can catch that;
 *   · the operator's work is still there afterwards;
 *   · re-arming deliberately, after reading the new figures, then works.
 *
 * WHY THIS FILE USES `lifecycle-fixtures.ts`. The reset control lives in the
 * persistent worked-example bar, which renders only while the APP holds a session —
 * so the walkthrough has to be really started, through the real control on My
 * Experiments (see `startFromEmptyState`). That is also
 * why it must NOT inherit `fixtures.ts`'s shared scope: it opens and destroys
 * sessions, and the shared one is where `answers.spec.ts` and `export.spec.ts` keep
 * their baselines. The fixture disposes every session this file causes to exist.
 */

import { expect, test } from './lifecycle-fixtures';
import { SEED } from './env';

const MODAL = '[role="dialog"][aria-modal="true"]';

/**
 * Start the walkthrough from My Experiments.
 *
 * IT IS THE EMPTY STATE'S PRIMARY, NOT THE FIRST-RUN OFFER CARD. This suite's ordinary
 * workspace is empty by construction, and `ExperimentsHome` suppresses the offer card
 * whenever the queue has no rows — so that one action is never offered by two primaries
 * at once. `Launch Guided Demo` is the control that is on this screen, and it calls the
 * same `startTutorial`, so the session this file's reset dialog needs is opened by the
 * same code path it always was.
 */
async function startFromEmptyState(page: import('@playwright/test').Page) {
  await page.goto('/experiments', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Launch Guided Demo' }).click();
  await expect(
    page.getByRole('complementary', { name: 'Worked example session' })
  ).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('.tutorial-mark')).toBeVisible({ timeout: 20_000 });
}

/** Record every reset request the PAGE makes, split by mode, read off the wire. */
function watchResetCalls(page: import('@playwright/test').Page) {
  const modes: string[] = [];
  const statuses: { mode: string; status: number }[] = [];
  page.on('request', (req) => {
    if (req.method() !== 'POST' || !req.url().includes('/demo/reset')) return;
    const body = req.postData();
    modes.push(body ? (JSON.parse(body).mode as string) : 'unknown');
  });
  page.on('response', (res) => {
    const req = res.request();
    if (req.method() !== 'POST' || !req.url().includes('/demo/reset')) return;
    const body = req.postData();
    statuses.push({ mode: body ? (JSON.parse(body).mode as string) : 'unknown', status: res.status() });
  });
  return {
    modes: () => [...modes],
    executes: () => statuses.filter((s) => s.mode === 'execute'),
  };
}

async function openResetDialog(page: import('@playwright/test').Page) {
  await page
    .getByRole('complementary', { name: 'Worked example session' })
    .getByRole('button', { name: /Reset Worked Example/i })
    .click();
  const dialog = page.locator(MODAL);
  await expect(dialog).toHaveCount(1);
  await expect(dialog).toContainText(/Reset the Worked Example/i);
  return dialog;
}

test.describe('R4 · reset preconditions', () => {
  test('opening the dialog only PREVIEWS, and Cancel leaves the workspace exactly as it was', async ({
    page,
    lifecycle,
  }) => {
    const calls = watchResetCalls(page);
    await startFromEmptyState(page);
    const mine = lifecycle.sessionsCreated()[0];

    await lifecycle.answerFirstBlocker(mine, SEED.fresh);
    const before = await lifecycle.readInSession(mine, SEED.fresh);
    expect(before.rev, 'this test needs progress that a reset would destroy').toBeGreaterThan(0);

    const dialog = await openResetDialog(page);
    // The disclosure is server-derived and names what would be lost.
    await expect(dialog.locator('.reset-at-risk')).toContainText(/confirmed answer/i);

    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.locator(MODAL)).toHaveCount(0);

    // ONE request, and it was a preview. A classification is read-only; if opening
    // this dialog could execute anything, the confirmation gate would be decoration.
    expect(calls.modes(), 'opening and cancelling must preview once and execute never').toEqual([
      'preview',
    ]);
    const after = await lifecycle.readInSession(mine, SEED.fresh);
    expect(after.rev).toBe(before.rev);
    expect(after.pendingCount).toBe(before.pendingCount);
  });

  test('work committed AFTER the preview makes the reset refuse (412), destroys nothing, disarms the gate, and is not auto-retried', async ({
    page,
    lifecycle,
  }) => {
    const calls = watchResetCalls(page);
    await startFromEmptyState(page);
    const mine = lifecycle.sessionsCreated()[0];

    // Progress that exists BEFORE the operator looks at the figures.
    await lifecycle.answerFirstBlocker(mine, SEED.fresh);
    const dialog = await openResetDialog(page);
    const figuresRead = await lifecycle.readInSession(mine, SEED.fresh);

    // THE GAP. The operator is reading; someone commits more work. This is the exact
    // window the digest exists to close, and it is a window only a real dialog has.
    await lifecycle.answerFirstBlocker(mine, SEED.partial);
    const committedInTheGap = await lifecycle.readInSession(mine, SEED.partial);
    expect(committedInTheGap.rev).toBeGreaterThan(0);

    // The operator arms and confirms what they read a moment ago.
    const confirmBox = dialog.getByRole('textbox').first();
    const destructive = dialog.getByRole('button', { name: 'Reset Example Records' });
    await confirmBox.fill('RESET');
    await expect(destructive).toBeEnabled();
    await destructive.click();

    // REFUSED, in the operator's terms — and the refusal must not read as an error or
    // as an ambiguity, because neither is what happened.
    // C2: the copy no longer claims "Nothing was reset". A per-record precondition
    // abort refuses with this same `plan_digest_stale` after restoring earlier
    // records, and nothing on the response tells the two apart — so the message says
    // what is true in every case and the refreshed figures carry the rest. THIS
    // scenario really did mutate nothing, which the assertions below MEASURE rather
    // than read off a sentence.
    const refusal = dialog.locator('.reset-refused[role="alert"]');
    await expect(refusal).toContainText('Reset refused');
    await expect(refusal).toContainText('this workspace changed');
    await expect(refusal).toContainText('read them again and confirm again');
    await expect(refusal).not.toContainText('Nothing was reset');

    // NOTHING WAS DESTROYED: both the work read in the preview and the work committed
    // in the gap are intact.
    expect((await lifecycle.readInSession(mine, SEED.fresh)).rev).toBe(figuresRead.rev);
    expect((await lifecycle.readInSession(mine, SEED.partial)).rev).toBe(committedInTheGap.rev);

    // THE DISARM. The typed gate is cleared and the destructive control is inert
    // again, so the next attempt requires reading the refreshed figures and arming
    // deliberately.
    await expect(confirmBox, 'a refused reset must clear the typed gate').toHaveValue('');
    await expect(destructive, 'a refused reset must leave the action disarmed').toBeDisabled();

    // NO AUTO-RETRY. Exactly one execute was sent, and it is the one that was
    // refused. A dialog that quietly re-sent with a fresh digest would destroy work
    // against figures nobody approved — and every server-side test would still pass.
    expect(
      calls.executes().map((e) => e.status),
      'the dialog must not retry an execute on its own'
    ).toEqual([412]);

    // RE-ARMING DELIBERATELY, against the refreshed figures, works.
    await confirmBox.fill('RESET');
    await expect(destructive).toBeEnabled();
    await destructive.click();

    await expect
      .poll(async () => (await lifecycle.readInSession(mine, SEED.fresh)).rev, { timeout: 20_000 })
      .toBe(0);
    expect((await lifecycle.readInSession(mine, SEED.partial)).rev).toBe(0);
    const list = await lifecycle.listInSession(mine);
    expect(list.ids.slice().sort(), 'all five examples must be back').toEqual(
      Object.values(SEED).slice().sort()
    );
    expect(
      calls.executes().map((e) => e.status),
      'the second, re-armed execute is the one that proceeds'
    ).toEqual([412, 200]);
  });

  test('an execute that omits the precondition is refused (428) and destroys nothing', async ({
    page,
    lifecycle,
  }) => {
    /*
     * This dialog always sends the digest its own preview returned, so a 428 cannot be
     * produced by clicking. The digest is stripped from the request body on the way
     * out — standing in for an older or broken client — and the REAL server answers.
     * What this adds over pytest is that the UI treats a 428 exactly as it treats a
     * 412: an honest refusal, a disarmed gate, and no auto-retry. The two share one
     * branch in the dialog, and a future refactor could easily split them and get one
     * of them wrong.
     */
    const calls = watchResetCalls(page);
    await startFromEmptyState(page);
    const mine = lifecycle.sessionsCreated()[0];

    await lifecycle.answerFirstBlocker(mine, SEED.fresh);
    const before = await lifecycle.readInSession(mine, SEED.fresh);

    const dialog = await openResetDialog(page);

    let stripped = false;
    await page.route(
      (url) => url.href.includes('/demo/reset'),
      async (route) => {
        const raw = route.request().postData();
        const body = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
        if (stripped || body.mode !== 'execute') return route.fallback();
        stripped = true;
        delete body.plan_digest;
        await route.fallback({ postData: JSON.stringify(body) });
      }
    );

    const confirmBox = dialog.getByRole('textbox').first();
    await confirmBox.fill('RESET');
    await dialog.getByRole('button', { name: 'Reset Example Records' }).click();

    await expect
      .poll(() => calls.executes().map((e) => e.status), { message: 'no execute was observed' })
      .toEqual([428]);

    // The same honest refusal, and the same disarm. (C2: "Nothing was reset" is gone
    // from this copy — see the 412 case above. The no-mutation claim for THIS scenario
    // is made by the measurement at the end of the test, which is where it belongs.)
    await expect(dialog.locator('.reset-refused[role="alert"]')).toContainText('Reset refused');
    await expect(confirmBox).toHaveValue('');
    await expect(dialog.getByRole('button', { name: 'Reset Example Records' })).toBeDisabled();

    // NOTHING WAS DESTROYED.
    const after = await lifecycle.readInSession(mine, SEED.fresh);
    expect(after.rev, 'a reset with no precondition must not run').toBe(before.rev);
    expect(after.pendingCount).toBe(before.pendingCount);
  });
});

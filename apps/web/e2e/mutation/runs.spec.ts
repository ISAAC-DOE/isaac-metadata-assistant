/**
 * R5 · THE RUN WORKSPACE, IN A REAL BROWSER AGAINST A REAL BACKEND.
 *
 * WHY THIS FILE EXISTS AT ALL. The Run vertical slice shipped 6,988 inserted lines
 * with NOT ONE browser test — in a repository whose own instructions make the
 * mutation suite mandatory for a user-facing slice, and after a phase in which real
 * browser testing found defects the unit suites had passed. Its unit coverage was
 * 79 backend tests (`test_run_api.py`, `pytest --collect-only`) and 23 jsdom tests
 * (`run-workspace.test.tsx`, measured by `vitest run`), and no `apps/web/e2e/` file
 * was touched at all.
 *
 * THOSE TWO NUMBERS WERE FIRST WRITTEN HERE AS "1473 backend tests and 1023 jsdom
 * tests", AND BOTH WERE LINE COUNTS. They are the insertion columns of
 * `git diff --stat` for those two files, read off and relabelled as test counts —
 * inflating the coverage this file argues was insufficient by roughly 19x and 44x,
 * and in the direction that made the argument sound stronger. `CLAUDE.md` §12 says
 * "Never report a count you did not just measure. Quote the command." The
 * correction is left visible because this is the exact failure the repository keeps
 * finding, and it was found here by a reviewer pointed at this file.
 *
 * WHAT IS UNDER TEST AND WHAT IS ONLY A WITNESS. The action under test is always
 * performed BY THE PAGE — a click, a keystroke. The `request` context is used to
 * establish starting state, to play a concurrent second client, and to read state
 * back as an INDEPENDENT check. It never performs the action under test, and no
 * mutation's success is ever mocked: every 200 below comes from FastAPI.
 *
 * TWO `page.route` HANDLERS AND ONE OBSERVER, none of them a mock — the distinction
 * matters because "green browser suite over a faked server" is worse than no suite:
 *   · `delayNextPatch` holds a REAL request open so an in-flight window is
 *     observable. The server still answers it.
 *   · `injectUnwritablePathOnce` adds a key to the REQUEST body that this UI cannot
 *     itself produce, and lets the REAL route refuse it. The refusal under
 *     assertion is the server's — though note that no spec here asserts a STATUS
 *     CODE: what is asserted is that the run did not move and the value was not
 *     stored. The 422 itself is pinned by `apps/api/tests/test_run_api.py`.
 *   · `countPatches` uses `page.on('request')`, not `page.route`. It observes only
 *     and cannot alter a request.
 *
 * THREE OF THESE SPECS ARE REGRESSION GUARDS FOR NAMED REVIEW FINDINGS on this
 * branch (`90b432d`), each of which was a real defect that every test then in the
 * repository passed through:
 *   I1 — an edit typed while a save was in flight was destroyed on unmount.
 *   I2 — an invented field path was stored with fabricated evidence.
 *   I3 — a save refused while a card was collapsed was announced nowhere.
 * A fourth spec covers run-to-run isolation, which is NOT one of the named findings
 * — nothing had exercised two runs on one screen, so there was no finding to name.
 */

import { type Locator, type Page } from '@playwright/test';
import { MUT_API_BASE, SEED } from './env';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';
import { expect, openRecord, test } from './own-session-fixtures';

/** The debounce the hook actually uses, plus room for a round trip. */
const SETTLE_MS = 3_000;

/* ── locators ──────────────────────────────────────────────────────────────── */

const addRun = (page: Page) => page.getByRole('button', { name: 'Add Run' });
const runCards = (page: Page) => page.locator('article.run-card');
const runCount = (page: Page) => page.locator('.runs-count');

/** One card, by its position in the list. Position is the reader's mental model. */
const nthCard = (page: Page, n: number) => runCards(page).nth(n);

const header = (card: Locator) => card.locator('button.run-card-header');
const saveStatus = (card: Locator) => card.locator('.run-save-status');
const progress = (card: Locator) => card.locator('.run-card-progress');
const conditions = (card: Locator) => card.locator('.run-card-conditions');

/**
 * A run-level field's control, addressed by the OFFICIAL PATH shown beside it.
 *
 * Deliberately not `getByLabel('Temperature')`: the visible label carries a unit
 * span, and with two runs on screen that name matches twice. The path is the one
 * unambiguous, non-cosmetic handle on the control, and if it stops being rendered
 * that is itself a regression worth failing on.
 */
function fieldControl(card: Locator, path: string): Locator {
  return card.locator(`.run-field:has(.run-field-path:text-is("${path}")) input, ` +
    `.run-field:has(.run-field-path:text-is("${path}")) select`);
}

const fieldError = (card: Locator, path: string) =>
  card.locator(`.run-field:has(.run-field-path:text-is("${path}")) .run-field-error`);

/* ── waiting ───────────────────────────────────────────────────────────────── */

/** Open a record and wait for the Runs section's OWN fetch to have landed. */
async function openRunsSection(page: Page, id: string) {
  await openRecord(page, id);
  await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible();
  await expect(addRun(page)).toBeEnabled();
}

/** Click Add Run and wait for the card the server created. */
async function clickAddRun(page: Page, expectedTotal: number) {
  await addRun(page).click();
  await expect(runCards(page)).toHaveCount(expectedTotal);
  await expect(runCount(page)).toHaveText(
    expectedTotal === 1 ? '1 run' : `${expectedTotal} runs`,
  );
}

/* ── independent server reads (never the action under test) ────────────────── */

interface SeenRun {
  id: string;
  label: string;
  version: string;
  rev: number;
  ordinal: number;
  values: Record<string, unknown>;
}

async function readRuns(
  request: { get: Page['request']['get'] },
  session: string,
  experimentId: string,
): Promise<SeenRun[]> {
  const res = await request.get(`${MUT_API_BASE}/experiments/${experimentId}/runs`, {
    headers: { [TUTORIAL_SESSION_HEADER]: session },
  });
  expect(res.ok(), `GET /runs: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = (await res.json()) as {
    runs: {
      id: string;
      label: string;
      version: string;
      rev: number;
      ordinal: number;
      fields?: Record<string, { value: unknown }>;
    }[];
  };
  return body.runs.map((r) => ({
    id: r.id,
    label: r.label,
    version: r.version,
    rev: r.rev,
    ordinal: r.ordinal,
    values: Object.fromEntries(
      Object.entries(r.fields ?? {}).map(([path, env]) => [path, env?.value ?? null]),
    ),
  }));
}

/** Play a concurrent second client: write a run field out of band. */
async function patchRunBehindTheUi(
  request: { patch: Page['request']['patch'] },
  session: string,
  experimentId: string,
  run: SeenRun,
  fields: Record<string, unknown>,
) {
  const res = await request.patch(
    `${MUT_API_BASE}/experiments/${experimentId}/runs/${run.id}`,
    {
      headers: {
        [TUTORIAL_SESSION_HEADER]: session,
        'content-type': 'application/json',
        // A STRONG QUOTED VALIDATOR. Unquoted is 400 `malformed_if_match`, not
        // 412, and a spec that got this wrong would be asserting the wrong refusal.
        'If-Match': `"${run.version}"`,
      },
      data: { confirmed_by_user: true, fields },
    },
  );
  expect(
    res.ok(),
    `the out-of-band run PATCH must SUCCEED for the race to be real; got ` +
      `${res.status()} ${await res.text()}`,
  ).toBeTruthy();
}

/* ── request-level instruments ─────────────────────────────────────────────── */

/** Count the PATCHes the PAGE sent to the run route. Observes only. */
function countPatches(page: Page, experimentId: string) {
  const seen: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'PATCH' && r.url().includes(`/experiments/${experimentId}/runs/`)) {
      seen.push(r.url());
    }
  });
  return () => [...seen];
}

/**
 * Hold the next run PATCH open for `ms`, then let the REAL server answer it.
 * The only way to make an in-flight window observable from a spec.
 */
async function delayNextPatch(page: Page, ms: number) {
  let fired = false;
  await page.route(
    (url) => url.href.includes('/runs/'),
    async (route) => {
      if (fired || route.request().method() !== 'PATCH') return route.fallback();
      fired = true;
      await new Promise((resolve) => setTimeout(resolve, ms));
      // `fallback`, not `continue`: the scope fixture's handler registered first
      // and therefore runs last, and it is what attaches the session header.
      await route.fallback();
    },
  );
}

/**
 * Add a field path the PATCH allowlist does not contain to the next run PATCH,
 * and let the real route refuse it.
 *
 * THIS IS THE I2 REGRESSION GUARD. Before `90b432d`, `field_level()` was a
 * segment-aware PREFIX test with no check that the key named a real path, so
 * `context.typo_K` was STORED, with a fabricated `user_confirmation` evidence
 * entry, and permanently blocked that run's official export with "Additional
 * properties are not allowed". The UI cannot produce such a key, which is exactly
 * why the guard has to be installed at the request layer.
 */
async function injectUnwritablePathOnce(page: Page, key: string) {
  let fired = false;
  await page.route(
    (url) => url.href.includes('/runs/'),
    async (route) => {
      if (fired || route.request().method() !== 'PATCH') return route.fallback();
      fired = true;
      const raw = route.request().postData();
      const body = raw ? (JSON.parse(raw) as { fields?: Record<string, unknown> }) : {};
      body.fields = { ...(body.fields ?? {}), [key]: 1 };
      await route.fallback({ postData: JSON.stringify(body) });
    },
  );
}

/* ── the specs ─────────────────────────────────────────────────────────────── */

test.describe('R5 · the Run workspace', () => {
  test('Add Run creates a run the SERVER holds, not just a card on screen', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);

    const before = await readRuns(request, session, SEED.fresh);
    expect(before, 'a canonical example record starts with no runs').toHaveLength(0);
    await expect(page.locator('.runs-empty')).toBeVisible();

    await clickAddRun(page, 1);

    // The card on screen and the run on the server are the SAME run — asserted by
    // id, because "a card appeared" and "a run exists" are different claims.
    const after = await readRuns(request, session, SEED.fresh);
    expect(after).toHaveLength(1);
    await expect(nthCard(page, 0)).toHaveAttribute('data-run-id', after[0].id);
    await expect(header(nthCard(page, 0))).toContainText(after[0].label);

    // Nothing is claimed about a run nobody has touched.
    await expect(saveStatus(nthCard(page, 0))).toHaveText('');
    await expect(conditions(nthCard(page, 0))).toContainText('No conditions recorded yet');
    /*
     * The scope is part of the figure — a bare "0 of N" is a completion claim the
     * number is not entitled to make. See the note in RunCard.tsx.
     *
     * THE DENOMINATOR IS MATCHED AS A PATTERN, NOT AS A LITERAL, and it used to be
     * `'0 of 3'`. That literal broke the moment the screen offered the whole writable
     * set (five paths, not three) — a green suite failing on a number it had hardcoded
     * about a set that was always allowed to grow. What this test is about is the
     * NUMERATOR being zero and the SCOPE being stated; the size of the offered set is
     * `runFields.ts`'s business and is asserted against the rendered controls below.
     */
    await expect(progress(nthCard(page, 0))).toHaveText(
      /^\s*0 of \d+\s+run fields on this screen\s*$/,
    );
  });

  test('a typed value says Saved only AFTER the server acknowledges, and survives a reload', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    await clickAddRun(page, 1);
    const card = nthCard(page, 0);

    // Hold the PATCH open, so "Saving…" is observable as a real state rather than
    // inferred from a screenshot taken at a lucky moment.
    await delayNextPatch(page, 1_500);
    await fieldControl(card, 'context.temperature_K').fill('277.15');

    /*
     * THE LOAD-BEARING ASSERTION IS THE FIRST ONE. If the hook set `Saved` when an
     * edit was merely QUEUED, `toHaveText('Saving…')` would never resolve and this
     * line would time out. The `not.toHaveText('Saved')` below is a point-in-time
     * re-check, not a proof that `Saved` never flashed — the text is already
     * `Saving…`, so it passes immediately. It is kept because it fails loudly if the
     * two states are ever made to coexist, and it is described honestly rather than
     * as "the claim under test", which is what an earlier revision called it.
     */
    await expect(saveStatus(card)).toHaveText('Saving…');
    await expect(saveStatus(card)).not.toHaveText('Saved');
    await expect(saveStatus(card)).toHaveText('Saved', { timeout: 10_000 });

    // The server independently holds the value, at an advanced rev.
    const [run] = await readRuns(request, session, SEED.fresh);
    expect(run.values['context.temperature_K']).toBe(277.15);
    // 2, not 1: creating the run was the first write (see the I2 spec below).
    expect(run.rev, 'a write must advance the run rev').toBe(2);

    await expect(progress(card)).toHaveText(/^\s*1 of \d+\s+run fields on this screen\s*$/);
    await expect(conditions(card)).toContainText('277.15 K');

    // The denominator is the number of controls the card actually renders — asserted
    // against the DOM rather than against a constant, so it cannot drift from what a
    // reader sees and cannot be broken by widening the offered set.
    const denominator = Number(
      ((await progress(card).textContent()) ?? '').match(/of (\d+)/)?.[1] ?? '0',
    );
    await expect(card.locator('.run-field')).toHaveCount(denominator);

    // DURABILITY, through the real read path rather than through React state.
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible();
    const reloaded = nthCard(page, 0);
    await expect(conditions(reloaded)).toContainText('277.15 K');
    await expect(progress(reloaded)).toHaveText(/^\s*1 of \d+\s+run fields on this screen\s*$/);
    // And the value is in the box, not merely in the summary line.
    await header(reloaded).click();
    await expect(fieldControl(reloaded, 'context.temperature_K')).toHaveValue('277.15');
  });

  test('two runs are ISOLATED: editing Run 2 leaves Run 1 untouched on the server', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    await clickAddRun(page, 1);
    await clickAddRun(page, 2);

    const seeded = await readRuns(request, session, SEED.fresh);
    expect(seeded).toHaveLength(2);
    const [first, second] = seeded;
    expect(first.ordinal, 'ordinals order the list').toBeLessThan(second.ordinal);
    const firstRevBefore = first.rev;

    // Edit ONLY the second card.
    const card2 = nthCard(page, 1);
    await expect(card2).toHaveAttribute('data-run-id', second.id);
    await fieldControl(card2, 'context.temperature_K').fill('310');
    await expect(saveStatus(card2)).toHaveText('Saved', { timeout: 10_000 });

    const after = await readRuns(request, session, SEED.fresh);
    const a1 = after.find((r) => r.id === first.id)!;
    const a2 = after.find((r) => r.id === second.id)!;
    expect(a2.values['context.temperature_K']).toBe(310);
    // THE ASSERTION THIS SPEC EXISTS FOR. A replace-by-index would have attached
    // the response to whichever card sat in that slot.
    expect(a1.values['context.temperature_K'] ?? null).toBeNull();
    expect(a1.rev, 'Run 1 must not have been written at all').toBe(firstRevBefore);

    // And the screen agrees about both.
    await expect(saveStatus(nthCard(page, 0))).toHaveText('');
    await expect(conditions(nthCard(page, 0))).toContainText('No conditions recorded yet');
    await expect(conditions(card2)).toContainText('310 K');
  });

  test('a value this build cannot shape is NOT sent, and the box says why', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    await clickAddRun(page, 1);
    const card = nthCard(page, 0);
    const patches = countPatches(page, SEED.fresh);
    const before = await readRuns(request, session, SEED.fresh);

    await fieldControl(card, 'context.temperature_K').fill('not a number');

    await expect(fieldError(card, 'context.temperature_K')).toContainText('Enter a number.');
    await expect(fieldControl(card, 'context.temperature_K')).toHaveAttribute(
      'aria-invalid',
      'true',
    );
    // NOT SENT — and the card SAYS SO, at card level, rather than going quiet.
    await page.waitForTimeout(SETTLE_MS);
    expect(patches(), 'a malformed entry must never reach the network').toHaveLength(0);
    await expect(saveStatus(card)).toHaveText('Change not sent');

    /*
     * AND IT SURVIVES COLLAPSING THE CARD. This is the browser half of a review
     * finding: the field error lives inside the expanded panel, so before the fix a
     * reader who typed something unparseable and collapsed the card was left with a
     * card that said nothing at all — or worse, still said "Saved" from a previous
     * successful write, while holding an edit that would never be sent.
     */
    await header(card).click();
    await expect(header(card)).toHaveAttribute('aria-expanded', 'false');
    await expect(saveStatus(card)).toHaveText('Change not sent');
    await expect(header(card)).toContainText('Change not sent');
    await header(card).click();

    const after = await readRuns(request, session, SEED.fresh);
    expect(after[0].rev).toBe(before[0].rev);

    // Correcting it clears the error and sends exactly one write.
    await fieldControl(card, 'context.temperature_K').fill('300');
    await expect(saveStatus(card)).toHaveText('Saved', { timeout: 10_000 });
    await expect(fieldError(card, 'context.temperature_K')).toHaveCount(0);
    expect((await readRuns(request, session, SEED.fresh))[0].values['context.temperature_K']).toBe(
      300,
    );
  });

  test('I2 · a field path outside the allowlist is REFUSED by the server, and the card never claims Saved', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    await clickAddRun(page, 1);
    const card = nthCard(page, 0);

    // The rev the run already has. MEASURED, not assumed to be 0: creating a run
    // is itself a write, so `_bump_changed_runs` has already taken it from 0 to 1
    // by the time the card exists. An earlier draft of this spec asserted 0 here
    // and failed — the app was right and the expectation was wrong, which is worth
    // leaving in the record because "rev starts at 0" is the intuitive guess.
    const created = await readRuns(request, session, SEED.fresh);
    expect(created[0].rev).toBe(1);

    await injectUnwritablePathOnce(page, 'context.typo_K');
    await fieldControl(card, 'context.temperature_K').fill('295');

    // A REFUSAL, not a retry loop: a 422 is the server having read the request and
    // declined it, so the hook must not resend, and must not say Saved.
    // `toContainText`, because the readout now names the CAUSE beside the state —
    // "Save failed · <why>". A bare "Save failed" was a state with no reason, whose
    // only control was a Retry that could loop.
    await expect(saveStatus(card)).toContainText('Save failed', { timeout: 10_000 });
    await expect(card.getByRole('button', { name: 'Retry Save' })).toBeVisible();

    // Nothing was written — neither the invented key nor the legitimate one, and
    // the run did not move at all.
    const during = await readRuns(request, session, SEED.fresh);
    expect(during[0].values['context.typo_K']).toBeUndefined();
    expect(during[0].values['context.temperature_K'] ?? null).toBeNull();
    expect(during[0].rev, 'a refused write must not advance the run').toBe(created[0].rev);

    // The reader's own edit was never lost: Retry sends the held field, which this
    // time is the only key in the body, and it succeeds.
    await card.getByRole('button', { name: 'Retry Save' }).click();
    await expect(saveStatus(card)).toHaveText('Saved', { timeout: 10_000 });
    const after = await readRuns(request, session, SEED.fresh);
    expect(after[0].values['context.temperature_K']).toBe(295);
    expect(after[0].values['context.typo_K']).toBeUndefined();
  });

  test('I3 · a save refused while the card is COLLAPSED is still announced and still recoverable', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    await clickAddRun(page, 1);
    const card = nthCard(page, 0);

    await injectUnwritablePathOnce(page, 'context.typo_K');
    await fieldControl(card, 'context.temperature_K').fill('288');
    // Collapse before the refusal lands. Before `90b432d` the failed state lived
    // only inside the expanded panel, so this reader was told nothing at all.
    await header(card).click();
    await expect(header(card)).toHaveAttribute('aria-expanded', 'false');

    await expect(saveStatus(card)).toContainText('Save failed', { timeout: 10_000 });
    // In the header's ACCESSIBLE NAME, so reaching the collapsed card by keyboard
    // alone says what is wrong with it.
    await expect(header(card)).toContainText('Save failed');
    const retry = card.getByRole('button', { name: 'Retry Save' });
    await expect(retry).toBeVisible();

    await retry.click();
    await expect(saveStatus(card)).toHaveText('Saved', { timeout: 10_000 });
    expect((await readRuns(request, session, SEED.fresh))[0].values['context.temperature_K']).toBe(
      288,
    );
  });

  test('I1 · an edit typed while a save is IN FLIGHT survives the card unmounting', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    await clickAddRun(page, 1);
    const card = nthCard(page, 0);

    /*
     * WAITING FOR THE REQUEST TO HAVE LEFT IS THE WHOLE TEST, and the first version
     * of this spec did not do it — which made the spec pass against the defect it
     * was written to catch. Proven, not suspected: reinstating the pre-`90b432d`
     * teardown (`if (inFlightRef.current) { pendingRef.current = {}; return; }`)
     * left this spec GREEN.
     *
     * (To be unambiguous about which version: it is the FIRST DRAFT of this spec —
     * without the `waitForRequest` below — that stayed green against the defect. The
     * spec as committed FAILS against it, with the message in the poll below, and
     * that was verified by reinstating the old teardown and running it.)
     *
     * The reason is the debounce. `fill` then `expect(…'Saving…')` resolves in a few
     * ms, because the status is set when an edit is QUEUED — long before
     * `AUTOSAVE_DEBOUNCE_MS` (600) elapses and `send()` runs. So both values landed
     * in the same pending map and went out in ONE PATCH, and the window this spec
     * is about — an edit typed AFTER `send()` emptied the map — was never entered.
     *
     * Waiting on the actual PATCH request closes it: after this line the map is
     * empty and `inFlightRef` is true, so the second edit can only survive via the
     * settle handler.
     */
    await delayNextPatch(page, 2_500);
    await fieldControl(card, 'context.temperature_K').fill('301');
    await expect(saveStatus(card)).toHaveText('Saving…');
    await page.waitForRequest(
      (r) => r.method() === 'PATCH' && r.url().includes(`/experiments/${SEED.fresh}/runs/`),
    );

    await fieldControl(card, 'timestamps.acquired_start_utc').fill('2026-01-31T09:00:00Z');

    // Unmount every card while that first PATCH is still open. This is ONE CLICK
    // AWAY in the product: the Runs section lives inside the fields tabpanel.
    await page.getByRole('tab', { name: 'Graph' }).click();
    await expect(page.locator('article.run-card')).toHaveCount(0);

    // The guarantee: every accepted edit is handed to the network exactly once.
    // The second edit could not be sent at unmount — its token was the one the
    // open response was about to establish — so the settle handler sends it.
    await expect
      .poll(
        async () => (await readRuns(request, session, SEED.fresh))[0]?.values[
          'timestamps.acquired_start_utc'
        ],
        {
          message:
            'the edit typed while a PATCH was in flight was lost when the card ' +
            'unmounted — this is review finding I1 reopening',
          timeout: 15_000,
        },
      )
      .toBe('2026-01-31T09:00:00Z');

    const [run] = await readRuns(request, session, SEED.fresh);
    expect(run.values['context.temperature_K'], 'the first edit must also be there').toBe(301);

    /*
     * AND THE OUTCOME SURVIVES THE ROUND TRIP — which is the Phase 2 change, asserted
     * in a browser rather than only in jsdom.
     *
     * This comment used to record the opposite as an honest limit: "Returning to the
     * fields view re-mounts a card whose autosave state is brand new, so the detached
     * write's OUTCOME is reported nowhere … if it had been refused, this card would
     * look exactly the same." That was true of the in-component hook. Save state now
     * lives in `runAutosaveStore`, keyed by experiment and run and disposed at the
     * RECORD screen's boundary rather than the card's, so a verdict that arrives while
     * every card is unmounted is still on screen when one comes back.
     *
     * What is asserted below is the SUCCESS path, because that is what this spec's
     * sequence produces. The refusal path — where the old code was silent and the new
     * code reports — is covered in jsdom by "a save REFUSED while the card was
     * unmounted is reported when it comes back", which fails if the state dies with the
     * card (verified against a reintroduced defect).
     */
    await page.getByRole('tab', { name: 'Record Fields' }).click();
    const remounted = nthCard(page, 0);
    // `Saved`, NOT the empty string this line used to assert. The empty string WAS the
    // old behaviour and was the defect: a card that had just had a write acknowledged
    // for it came back claiming nothing, because the state died with the component.
    await expect(saveStatus(remounted)).toHaveText('Saved');
    // BOTH values, and the timestamp is the one this spec is about — an earlier
    // revision asserted only `301 K`, the ordinary edit, while the comment above
    // talked about the detached one. The server-side poll proved the timestamp
    // landed; this proves the re-mounted card actually shows it.
    await expect(conditions(remounted)).toContainText('301 K');
    await expect(conditions(remounted)).toContainText('2026-01-31T09:00:00Z');
  });

  test('a stale run version is refused, writes nothing, and Refresh adopts the SERVER value', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    await clickAddRun(page, 1);
    const card = nthCard(page, 0);

    // A second client moves the run on. The page's token is now stale.
    const [run] = await readRuns(request, session, SEED.fresh);
    await patchRunBehindTheUi(request, session, SEED.fresh, run, {
      'context.temperature_K': 400,
    });

    await fieldControl(card, 'context.temperature_K').fill('123');
    await expect(saveStatus(card)).toHaveText('Conflict', { timeout: 10_000 });
    await expect(card.getByRole('alert')).toContainText('This run changed somewhere else');
    await expect(card.getByRole('alert')).toContainText('Nothing you typed was written');

    // THE CLAIM THAT MATTERS: the stale write did not land, and the concurrent
    // writer's value is intact.
    const held = await readRuns(request, session, SEED.fresh);
    expect(held[0].values['context.temperature_K']).toBe(400);

    // Nothing further is sent while halted — every send would carry the same
    // refused token.
    const patches = countPatches(page, SEED.fresh);
    await fieldControl(card, 'context.temperature_K').fill('124');
    await page.waitForTimeout(SETTLE_MS);
    expect(patches(), 'a halted card must send nothing').toHaveLength(0);
    expect((await readRuns(request, session, SEED.fresh))[0].values['context.temperature_K']).toBe(
      400,
    );

    // Refresh adopts the server's run WHOLESALE — it does not merge, and it does
    // not post the local value over the top.
    await card.getByRole('button', { name: 'Refresh This Run' }).click();
    await expect(fieldControl(card, 'context.temperature_K')).toHaveValue('400');
    await expect(saveStatus(card)).toHaveText('');
    expect((await readRuns(request, session, SEED.fresh))[0].values['context.temperature_K']).toBe(
      400,
    );
  });

  test('Check Run is READ-ONLY: it reports a verdict and advances nothing', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    await clickAddRun(page, 1);
    const card = nthCard(page, 0);

    const before = await readRuns(request, session, SEED.fresh);
    await card.getByRole('button', { name: 'Check Run' }).click();

    const result = card.getByRole('region', { name: 'Check result' });
    await expect(result).toBeVisible({ timeout: 15_000 });
    // The scope sentence is the honesty claim on this surface, so it is asserted
    // rather than assumed: a check is not an export and not a submission.
    await expect(result).toContainText('Nothing was written, submitted or exported');
    await expect(result).toContainText(`run version ${before[0].version}`);

    const after = await readRuns(request, session, SEED.fresh);
    expect(after[0].rev, 'a check must not advance the run').toBe(before[0].rev);
    expect(after[0].version).toBe(before[0].version);
    await expect(saveStatus(card)).toHaveText('');
  });
});

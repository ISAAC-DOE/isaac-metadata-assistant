/**
 * PER-RUN OVERRIDES, IN A REAL BROWSER AGAINST A REAL BACKEND.
 *
 * WHY THIS IS A MUTATION SPEC AND NOT A `@responsive` ONE. Recording an override
 * WRITES — it advances a run's revision inside a canonical example record — and the
 * read-only suite collects every `*.spec.ts` under `apps/web/e2e/`, filtering only
 * by TITLE TAG. A spec here carrying `@responsive`, `@interaction` or `@zoom` would
 * therefore be picked up by five parallel viewport projects that assert canonical
 * seed CONTENT, against a backend on a port this suite does not start. No title in
 * this file carries any of those tags, which is what keeps it out.
 *
 * WHAT IS UNDER TEST AND WHAT IS ONLY A WITNESS — the same rule the rest of this
 * directory follows. The action under test is always performed BY THE PAGE. The
 * `request` context establishes starting state, plays a concurrent second client,
 * and reads state back as an INDEPENDENT check; it never performs the action under
 * test, and no success below is mocked — every 200 comes from FastAPI.
 *
 * WHAT THIS FILE CANNOT PROVE, said plainly rather than left as a gap a reader has
 * to notice. Three of the ten invariants of this feature turn on the RECORD-level
 * value CHANGING, and **no HTTP operation in this application can change a
 * record-level field by its dotted path** — `POST /answers` fills open blockers and
 * `POST /edit` recognises only asset URIs and four structured keys, refusing
 * `{"sample.material.name": …}` with 422 `unrecognized_field`. That is a recorded
 * product gap (`apps/api/tests/test_run_api.py::_change_record_field` documents it),
 * not something to work around here. So "a record edit flows through to a run that
 * still inherits", "…and leaves an overridden run alone" and the live half of
 * "reverting resumes inheritance" are pinned in the backend suite, which can reach
 * the store directly, and this file asserts the halves a browser genuinely can:
 * that the write happens, that it is confined to one run, that the record's own
 * draft does not move, that a revert leaves the run holding nothing, and that every
 * refusal is reported as one.
 */

import { type Locator, type Page } from '@playwright/test';
import { MUT_API_BASE, SEED } from './env';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';
import { formatViolation, scan } from '../helpers/axe';
import { expect, openRecord, test } from './own-session-fixtures';

/** A record-level address the canonical seed carries, and CAN hold an override. */
const MATERIAL = 'field:sample.material.name';
/**
 * A record-level address the seed carries and CANNOT hold an override.
 *
 * `system.domain` IS reported in a run's `inherited` map and is NOT in
 * `EXPERIMENT_OVERRIDABLE_ADDRESSES`, because the overridable field set is the
 * deterministic extractor's own map of official paths and this one is not in it.
 * That asymmetry is pinned server-side by
 * `test_the_inherited_map_and_the_overridable_set_are_NOT_the_same_set`, and it is
 * what makes the 422 below reachable from a row the panel legitimately renders —
 * rather than from a tampered request.
 */
const NOT_OVERRIDABLE = 'field:system.domain';

/* ── locators ──────────────────────────────────────────────────────────────── */

const addRun = (page: Page) => page.getByRole('button', { name: 'Add Run' });
const runCards = (page: Page) => page.locator('article.run-card');
const nthCard = (page: Page, n: number) => runCards(page).nth(n);
const header = (card: Locator) => card.locator('button.run-card-header');
const panel = (card: Locator) => card.locator('section.run-inherited');
const row = (card: Locator, address: string) =>
  panel(card).locator(`[data-address="${address}"]`);
const outcome = (card: Locator) => panel(card).locator('.run-inherited-outcome');

/* ── waiting ───────────────────────────────────────────────────────────────── */

async function openRunsSection(page: Page, id: string) {
  await openRecord(page, id);
  await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible();
  await expect(addRun(page)).toBeEnabled();
}

/**
 * Add `count` runs and return the FIRST card, with its inherited panel open.
 *
 * A newly added card is expanded BY THE COMPONENT (focus moves to its header), so
 * this asserts the expanded state rather than clicking to reach it — the first
 * version of this helper clicked the header unconditionally and therefore COLLAPSED
 * every card it was supposed to open, which is why it is written this way and said
 * out loud. If that behaviour changes, the fallback click still opens the card and
 * the assertion below is what makes the change visible rather than silent.
 */
async function addAndExpand(page: Page, count: number): Promise<Locator> {
  for (let i = 1; i <= count; i += 1) {
    await addRun(page).click();
    await expect(runCards(page)).toHaveCount(i);
  }
  const card = nthCard(page, 0);
  if ((await header(card).getAttribute('aria-expanded')) !== 'true') {
    await header(card).click();
  }
  await expect(header(card)).toHaveAttribute('aria-expanded', 'true');
  await expect(panel(card)).toBeVisible();
  return card;
}

/* ── independent server reads (never the action under test) ────────────────── */

interface SeenRun {
  id: string;
  label: string;
  version: string;
  rev: number;
  /** `state` per address, exactly as the run view reports it. */
  states: Record<string, string>;
  /** The value this run RESOLVES to per address. */
  resolved: Record<string, unknown>;
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
      inherited?: Record<string, { state: string; payload: { value?: unknown } | null }>;
    }[];
  };
  return body.runs.map((r) => ({
    id: r.id,
    label: r.label,
    version: r.version,
    rev: r.rev,
    states: Object.fromEntries(
      Object.entries(r.inherited ?? {}).map(([a, res_]) => [a, res_.state]),
    ),
    resolved: Object.fromEntries(
      Object.entries(r.inherited ?? {}).map(([a, res_]) => [a, res_.payload?.value ?? null]),
    ),
  }));
}

/** The RECORD's own draft field value, read independently of any run. */
async function readRecordValue(
  request: { get: Page['request']['get'] },
  session: string,
  experimentId: string,
  path: string,
): Promise<unknown> {
  const res = await request.get(`${MUT_API_BASE}/experiments/${experimentId}/evidence`, {
    headers: { [TUTORIAL_SESSION_HEADER]: session },
  });
  expect(res.ok(), `GET /evidence: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = (await res.json()) as { evidence?: { path: string; value: unknown }[] };
  return (body.evidence ?? []).find((f) => f.path === path)?.value ?? null;
}

/** Play a concurrent second client: rename the run out of band, bumping its version. */
async function renameRunBehindTheUi(
  request: { patch: Page['request']['patch'] },
  session: string,
  experimentId: string,
  run: SeenRun,
  label: string,
) {
  const res = await request.patch(
    `${MUT_API_BASE}/experiments/${experimentId}/runs/${run.id}`,
    {
      headers: {
        [TUTORIAL_SESSION_HEADER]: session,
        'content-type': 'application/json',
        // A STRONG QUOTED VALIDATOR. Unquoted is 400 `malformed_if_match`, not 412.
        'If-Match': `"${run.version}"`,
      },
      data: { confirmed_by_user: true, fields: {}, label },
    },
  );
  expect(
    res.ok(),
    `the out-of-band rename must SUCCEED for the race to be real; got ` +
      `${res.status()} ${await res.text()}`,
  ).toBeTruthy();
}

/* ── the gesture under test ────────────────────────────────────────────────── */

/** Record an override on one row, entirely through the page. */
async function recordOverride(card: Locator, address: string, value: string) {
  const target = row(card, address);
  await target.getByRole('button', { name: /Override for this run|Change this run's value/ }).click();
  await target.getByRole('textbox').fill(value);
  // THE CONFIRMATION IS A GESTURE, not a flag this spec sets. The submit is inert
  // until the box is ticked, and that is asserted rather than worked around.
  await expect(target.getByRole('button', { name: 'Record override' })).toBeDisabled();
  await target.getByRole('checkbox').check();
  await target.getByRole('button', { name: 'Record override' }).click();
}

/* ── the specs ─────────────────────────────────────────────────────────────── */

test.describe('per-run overrides of inherited record values', () => {
  test('an override recorded on one run is held by the SERVER, and by that run alone', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    const card = await addAndExpand(page, 2);

    const before = await readRuns(request, session, SEED.fresh);
    expect(before).toHaveLength(2);
    expect(before[0].states[MATERIAL]).toBe('inherited');
    expect(before[1].states[MATERIAL]).toBe('inherited');
    const recordValueBefore = await readRecordValue(
      request,
      session,
      SEED.fresh,
      'sample.material.name',
    );
    expect(recordValueBefore).not.toBeNull();

    await recordOverride(card, MATERIAL, 'Cuprous Oxide');
    await expect(outcome(card)).toContainText('Override recorded for sample.material.name');

    const after = await readRuns(request, session, SEED.fresh);
    // INVARIANT 1 — the sibling is untouched, asserted on the SERVER's own answer.
    expect(after[0].states[MATERIAL]).toBe('overridden');
    expect(after[0].resolved[MATERIAL]).toBe('Cuprous Oxide');
    expect(after[1].states[MATERIAL]).toBe('inherited');
    expect(after[1].resolved[MATERIAL]).toBe(recordValueBefore);
    expect(after[1].rev).toBe(before[1].rev);
    expect(after[1].version).toBe(before[1].version);

    // INVARIANT 2 — the record's own value did not move. An override displaces what a
    // RUN reads; it never rewrites what the record says.
    expect(await readRecordValue(request, session, SEED.fresh, 'sample.material.name')).toBe(
      recordValueBefore,
    );

    // …and the row now reads as overridden, with the record's value still in view.
    await expect(row(card, MATERIAL)).toHaveAttribute('data-state', 'overridden');
    await expect(row(card, MATERIAL)).toContainText('Overridden on this run');
    await expect(row(card, MATERIAL)).toContainText(`The record currently says`);
    await expect(row(card, MATERIAL)).toContainText(String(recordValueBefore));
  });

  test('the override survives a reload — it is stored, not a state in this tab', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.partial);
    const card = await addAndExpand(page, 1);
    await recordOverride(card, MATERIAL, 'Reloaded Oxide');
    await expect(outcome(card)).toContainText('Override recorded');

    await page.reload();
    await openRunsSection(page, SEED.partial);
    const reloaded = nthCard(page, 0);
    await header(reloaded).click();
    await expect(row(reloaded, MATERIAL)).toHaveAttribute('data-state', 'overridden');
    await expect(row(reloaded, MATERIAL)).toContainText('Reloaded Oxide');

    const runs = await readRuns(request, session, SEED.partial);
    expect(runs[0].resolved[MATERIAL]).toBe('Reloaded Oxide');
  });

  test('reverting leaves the run holding NOTHING there, and inheriting again', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.ready);
    const card = await addAndExpand(page, 1);
    await recordOverride(card, MATERIAL, 'Temporary Oxide');
    await expect(row(card, MATERIAL)).toHaveAttribute('data-state', 'overridden');
    const recordValue = await readRecordValue(request, session, SEED.ready, 'sample.material.name');

    // TWO ACTS, because the contract makes a revert an explicitly confirmed one.
    await row(card, MATERIAL).getByRole('button', { name: /Revert to inherited/ }).click();
    await expect(row(card, MATERIAL)).toContainText(
      "read the record's value live again",
    );
    await row(card, MATERIAL).getByRole('button', { name: 'Confirm revert' }).click();

    await expect(outcome(card)).toContainText('Override removed for sample.material.name');
    await expect(row(card, MATERIAL)).toHaveAttribute('data-state', 'inherited');

    // The SERVER's answer: the run resolves from the record again, and what it shows
    // is the record's value rather than a copy left behind by the override.
    const runs = await readRuns(request, session, SEED.ready);
    expect(runs[0].states[MATERIAL]).toBe('inherited');
    expect(runs[0].resolved[MATERIAL]).toBe(recordValue);
  });

  test('re-recording the SAME value reports a no-op, and the run does not advance', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    const card = await addAndExpand(page, 1);
    await recordOverride(card, MATERIAL, 'Idempotent Oxide');
    await expect(outcome(card)).toContainText('Override recorded');
    const afterFirst = (await readRuns(request, session, SEED.fresh))[0];

    // The row now offers "Change this run's value", prefilled with the run's OWN
    // value — so submitting it unchanged is exactly the re-record the route no-ops.
    const target = row(card, MATERIAL);
    await target.getByRole('button', { name: /Change this run's value/ }).click();
    await expect(target.getByRole('textbox')).toHaveValue('Idempotent Oxide');
    await target.getByRole('checkbox').check();
    await target.getByRole('button', { name: 'Record override' }).click();

    await expect(outcome(card)).toContainText('This run already held that value');
    await expect(outcome(card)).toContainText('Nothing was written and nothing changed');
    await expect(outcome(card)).not.toContainText('Override recorded');

    const afterSecond = (await readRuns(request, session, SEED.fresh))[0];
    expect(afterSecond.rev).toBe(afterFirst.rev);
    expect(afterSecond.version).toBe(afterFirst.version);
  });

  test('an address that cannot hold an override is refused in the SERVER\'s own words', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    const card = await addAndExpand(page, 1);

    // Reachable from a row the panel legitimately renders — no request tampering.
    await recordOverride(card, NOT_OVERRIDABLE, 'something else');

    const target = row(card, NOT_OVERRIDABLE);
    await expect(target).toContainText('This address cannot hold this override');
    await expect(target).toContainText(NOT_OVERRIDABLE);
    await expect(target).toContainText('Only a record-level value a run INHERITS can be overridden');
    await expect(target).toContainText('Nothing was written');
    // NOT a success, and not a generic failure.
    await expect(outcome(card)).toHaveText('');
    await expect(target).toHaveAttribute('data-state', 'inherited');

    const runs = await readRuns(request, session, SEED.fresh);
    expect(runs[0].states[NOT_OVERRIDABLE]).toBe('inherited');
  });

  test('a COMPARE-AND-SWAP loser is told the override was not recorded, and it was not', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.partial);
    const card = await addAndExpand(page, 1);
    const before = (await readRuns(request, session, SEED.partial))[0];

    /*
     * A SECOND CLIENT MOVES THE RUN while this page holds the version it read. The
     * page's `If-Match` is now stale, and the route verifies the precondition inside
     * the same critical section that would have written — so the override is not
     * recorded, and the panel must not say it was. This is the one failure mode where
     * a cheerful message would be an outright lie about a scientist's data.
     */
    await renameRunBehindTheUi(request, session, SEED.partial, before, 'Renamed elsewhere');

    await recordOverride(card, MATERIAL, 'Never Recorded Oxide');

    const target = row(card, MATERIAL);
    await expect(target).toContainText('the override was not recorded');
    await expect(target).toContainText('Nothing was written');
    await expect(outcome(card)).toHaveText('');

    const after = (await readRuns(request, session, SEED.partial))[0];
    expect(after.states[MATERIAL]).toBe('inherited');
    expect(after.resolved[MATERIAL]).not.toBe('Never Recorded Oxide');
  });

  test('…and can RECOVER from it on screen: the refresh it names is there, and the retry succeeds', async ({
    page,
    request,
    session,
  }) => {
    /*
     * THE DEFECT THIS EXISTS FOR. The notice above told the reader to "refresh this
     * run", and the app's only refresh was `RunCard`'s conflict banner, gated on
     * `autosave.status === 'conflict'` — a state an override 412 never reaches,
     * because this write never goes through `useRunAutosave`. Measured by driving
     * exactly the scenario above: REFRESH BUTTON COUNT 0, CONFLICT BANNER COUNT 0.
     * `run.version` in the prop could therefore never advance, so every retry 412'd
     * forever and only a full page reload recovered. The test above asserts the
     * message; this one asserts a way out of the state the message describes.
     */
    await openRunsSection(page, SEED.ready);
    const card = await addAndExpand(page, 1);
    const before = (await readRuns(request, session, SEED.ready))[0];
    await renameRunBehindTheUi(request, session, SEED.ready, before, 'Renamed elsewhere');

    await recordOverride(card, MATERIAL, 'Recovered Oxide');
    const target = row(card, MATERIAL);
    await expect(target).toContainText('the override was not recorded');
    // The reader is ON the refusal, not on `<body>`: the submit is disabled for the
    // whole round trip, so focus has to be put somewhere when the answer arrives.
    await expect(target.locator('.run-inherited-failure')).toBeFocused();

    // The card-level banner is still absent — the remedy has to be in the notice.
    await expect(card.locator('.run-conflict')).toHaveCount(0);
    const refresh = target.getByRole('button', {
      name: 'Refresh this run · sample.material.name',
    });
    await expect(refresh).toBeVisible();
    await refresh.click();

    // A RE-READ IS NOT A WRITE, and the panel says which one happened.
    await expect(outcome(card)).toContainText('This run was re-read from the server');
    await expect(outcome(card)).toContainText('is still not recorded');
    await expect(target).not.toContainText('the override was not recorded');
    const runsAfterRefresh = (await readRuns(request, session, SEED.ready))[0];
    expect(runsAfterRefresh.states[MATERIAL]).toBe('inherited');
    // The token the page just adopted is NOT the one it sent — which is the whole
    // reason the retry below can do anything but 412 again.
    expect(runsAfterRefresh.version).not.toBe(before.version);

    // The entry survived the recovery, so the retry is one click rather than a
    // re-type — and focus is already on it.
    await expect(target.getByRole('textbox')).toHaveValue('Recovered Oxide');
    await expect(target.getByRole('checkbox')).toBeChecked();
    const record = target.getByRole('button', { name: 'Record override' });
    await expect(record).toBeFocused();
    await record.click();

    // THE RETRY SUCCEEDS — which is only possible because the refresh really did
    // advance the version this page sends.
    await expect(outcome(card)).toContainText('Override recorded for sample.material.name');
    const after = (await readRuns(request, session, SEED.ready))[0];
    expect(after.states[MATERIAL]).toBe('overridden');
    expect(after.resolved[MATERIAL]).toBe('Recovered Oxide');
    // …and the concurrent client's change is still there: recovering from the refusal
    // did not overwrite what caused it.
    expect(after.label).toBe('Renamed elsewhere');
  });

  test('the panel and its open override form carry no axe violation', async ({ page }) => {
    /*
     * SCOPED TO THE PANEL, and scanned in the state the sweep cannot reach.
     *
     * `section.run-inherited` is a subtree this slice CREATED, so a clean assertion is
     * appropriate here rather than a baseline entry: there is no pre-existing defect to
     * record, and anything axe reports is this slice's. The scan runs with the override
     * form OPEN, because that state adds the label association, the input's
     * `aria-describedby`, the checkbox's own label and the disabled submit — none of
     * which exists at rest.
     *
     * WHAT THIS IS NOT. It is not a substitute for the repository's a11y baseline,
     * which is measured on Linux CI and is the only place a NUMBER may be quoted from
     * (`CLAUDE.md`'s reporting rules, and the baseline's own platform handling). This
     * asserts a property — zero violations inside one subtree — which is
     * platform-independent in a way a node COUNT is not. Nothing here disables a rule.
     */
    await openRunsSection(page, SEED.fresh);
    const card = await addAndExpand(page, 1);
    const target = row(card, MATERIAL);
    await target.getByRole('button', { name: /Override for this run/ }).click();
    await expect(target.getByRole('textbox')).toBeVisible();

    const results = await scan(page, { include: 'section.run-inherited' });
    expect(
      results.violations.map(formatViolation).join('\n\n'),
      'the inherited panel, with an override form open',
    ).toBe('');
  });

  test('the confirmation gate is real: nothing is sent until the box is ticked', async ({
    page,
    request,
    session,
  }) => {
    await openRunsSection(page, SEED.fresh);
    const card = await addAndExpand(page, 1);

    const posted: string[] = [];
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes('/overrides')) posted.push(r.url());
    });

    const target = row(card, MATERIAL);
    await target.getByRole('button', { name: /Override for this run/ }).click();
    await target.getByRole('textbox').fill('Unconfirmed Oxide');
    await expect(target.getByRole('button', { name: 'Record override' })).toBeDisabled();
    // Force the click past the disabled attribute — the point is that even then no
    // request leaves, because the control is genuinely inert rather than styled so.
    await target.getByRole('button', { name: 'Record override' }).click({ force: true });
    await expect(outcome(card)).toHaveText('');
    expect(posted, 'no override request may leave before the reader confirms').toHaveLength(0);

    const runs = await readRuns(request, session, SEED.fresh);
    expect(runs[0].states[MATERIAL]).toBe('inherited');
  });

  test('every control that unmounts itself hands focus on, and none of them drops it on the body', async ({
    page,
  }) => {
    /*
     * MEASURED BEFORE THE FIX, in this browser, on this panel:
     *
     *   BEFORE ACTIVATE: BUTTON.btn.btn-secondary|Override for this run · sample.material.name
     *   AFTER ACTIVATE : BODY|Skip to contentISAAC…
     *   AFTER CANCEL   : BODY|Skip to contentISAAC…
     *
     * Every control here destroys itself when it is activated and nothing moved
     * focus after it, so a keyboard or screen-reader reader on row 9 of 13 landed on
     * `<body>` and had to tab through the skip link, the app shell, the record header
     * and eight rows at two buttons each to reach the box they had just revealed.
     *
     * THIS IS A REAL-FOCUS TEST ON PURPOSE. The panel's axe scan is no evidence
     * either way — axe does not evaluate focus movement — and `document.activeElement`
     * after a React commit in jsdom is a weaker witness than the browser's own.
     */
    await openRunsSection(page, SEED.fresh);
    const card = await addAndExpand(page, 1);
    const target = row(card, MATERIAL);
    const openTrigger = target.getByRole('button', {
      name: 'Override for this run · sample.material.name',
    });

    // OPEN → the box that was just revealed.
    await openTrigger.click();
    await expect(target.getByRole('textbox')).toBeFocused();

    // CANCEL → the control that opened it, which is back in the same place.
    await target.getByRole('button', { name: 'Cancel' }).click();
    await expect(openTrigger).toBeFocused();

    // SUBMIT → the row's own control, which now READS DIFFERENTLY, so focusing it
    // announces the row's new state through the control's own name.
    await recordOverride(card, MATERIAL, 'Focused Oxide');
    await expect(outcome(card)).toContainText('Override recorded');
    const changeTrigger = target.getByRole('button', {
      name: "Change this run's value · sample.material.name",
    });
    await expect(changeTrigger).toBeFocused();

    // REVERT, FIRST CLICK → the confirmation it revealed.
    const revertTrigger = target.getByRole('button', {
      name: 'Revert to inherited · sample.material.name',
    });
    await revertTrigger.click();
    await expect(target.getByRole('button', { name: 'Confirm revert' })).toBeFocused();

    // REVERT, BACKED OUT → the control that opened the confirmation.
    await target.getByRole('button', { name: 'Keep the override' }).click();
    await expect(revertTrigger).toBeFocused();

    // REVERT, CONFIRMED → the row's remaining control. The one the reader started
    // from is gone: there is no override left to revert.
    await revertTrigger.click();
    await target.getByRole('button', { name: 'Confirm revert' }).click();
    await expect(outcome(card)).toContainText('Override removed');
    await expect(openTrigger).toBeFocused();
  });
});

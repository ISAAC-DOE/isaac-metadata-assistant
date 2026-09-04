/**
 * TWO SCIENTISTS, ONE RECORD, THROUGH THE REAL APPLICATION LAYERS — the whole
 * workflow this programme has been building, executed once, end to end, with every
 * step asserted twice: on the SCREEN and, independently, on the SERVER.
 *
 * ── WHO THE TWO ACTORS ARE ──────────────────────────────────────────────────────
 *
 *   · **Scientist A** is a Playwright `page` with the Record Workbench open. Every
 *     act attributed to A happens through a click or a keystroke in that page.
 *   · **Scientist B / an MCP producer** is a Playwright `request` context speaking
 *     HTTP to the SAME backend process. B never touches the DOM, and A never learns
 *     about B's writes by being told to reload — the point of steps 7 and 11 is that
 *     A's already-open page discovers them on its own.
 *
 * ── WHY B IS HTTP AND NOT A SECOND BROWSER ──────────────────────────────────────
 *
 * Not convenience. `lib/api.ts` deliberately ships no `createProposal`, and
 * `routes.py` records that *"NOTHING WAS REWIRED TO FEED THEM. There is no automatic
 * producer"* — so **no surface in this build can create a proposal**, and a second
 * browser would have nothing to click. A proposal arrives over HTTP because that is
 * the only way one can arrive.
 *
 * ── WHAT IS PROVEN HERE, WHAT ONLY IN CI, AND WHAT NOWHERE ──────────────────────
 *
 * Stated up front rather than left to the evidence document, because the difference
 * is the honest part of this file:
 *
 *   · PROVEN HERE, against a real FastAPI process and a real browser: every one of
 *     the 20 steps below.
 *   · PROVEN ONLY IN CI, against a real PostgreSQL: durability across a process
 *     restart. **This backend is FILESYSTEM-BACKED** — `/api/health` reports
 *     `experiment_storage.backend: "filesystem"`, `durable: false`,
 *     `state: "ephemeral"` — so step 18's reload proves the values are re-read FROM
 *     THE SERVER rather than held in the page, and proves nothing at all about
 *     PostgreSQL. That leg is `apps/api/tests/test_proposal_durability.py`'s
 *     real-engine scenarios, and it is CITED here, never claimed.
 *   · PROVEN NOWHERE, and not by this file: anything hosted. `/krish` sits behind an
 *     Authentik edge this environment cannot authenticate to, and the trusted
 *     identity this suite runs under (`ISAAC_EDGE_TRUST_VERIFIER=test_fixture`) is
 *     set by NO shipped deploy artifact — `apps/api/tests/test_deploy_config.py`
 *     pins that. A hosted acceptance would answer `409 human_actor_required`.
 *
 * ── THE ONE RULE, inherited and not weakened ────────────────────────────────────
 *
 * **The reviewed act happens through the visible UI.** B's HTTP calls establish
 * starting state and read server state back as an INDEPENDENT check; they never
 * perform the act under test. A's rejection (step 9) and A's acceptance (step 14)
 * are clicks.
 *
 * ── DETERMINISM ─────────────────────────────────────────────────────────────────
 *
 * No `waitForTimeout`, no sleep, no timing assertion anywhere. Every wait is
 * Playwright's `expect` polling (`toBeVisible`, `toContainText`, `expect.poll`) on a
 * condition that is either true or false. The one place a DURATION appears is
 * `DISCOVERY_DEADLINE`, a bound on how long a background poller may take before this
 * file calls it broken — a deadline, not a measurement, and nothing here passes
 * BECAUSE of a delay. (An earlier revision of this paragraph said the deadline was
 * expressed as `toPass({ timeout })`; it is not — it is the `timeout` option on
 * `toBeVisible`/`toContainText` and on `expect.poll`. Corrected rather than reworded,
 * because a comment naming an API the file does not use is the kind of claim this
 * repository keeps catching.)
 *
 * ── SYNTHETIC ONLY ──────────────────────────────────────────────────────────────
 *
 * Every record, run, note, proposal and value here is created by this file seconds
 * earlier, in a workspace `global-setup` wiped. Nothing production-derived is read.
 */

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import type { APIRequestContext, Page } from '@playwright/test';

import {
  addRunThroughTheUi,
  createExperimentThroughTheUi,
  switchWorkspace,
  expect,
  proposalCard,
  test,
  type ServerApi,
} from './fixtures';
import { FIXTURE_ACTOR_SUBJECT, FIXTURE_TRUST_BASIS, TRUSTED_API_BASE } from './env';

/**
 * The RECORD-level field A fills in and B then proposes a change to.
 *
 * DERIVED, NOT WRITTEN OUT. `system.technique` is the single member of the list
 * operation's own `record_scoped_target_field_paths` at this HEAD — but
 * `deriveRecordTarget` below READS that list and picks from it rather than naming the
 * path, so a server that widens or narrows the set is followed instead of contradicted.
 * The two VALUES come from the vendored official schema's enum at whatever path it
 * picked, served by `GET /api/schema`. A literal here would be a second copy of two
 * documents the server already publishes, free to rot into a spec that passes for the
 * wrong reason.
 */
interface RecordTarget {
  path: string;
  /** What A enters through the website. */
  chosen: string;
  /** What B proposes — different from `chosen`, so a confusion is visible. */
  proposed: string;
}

/** The RUN-level target, and FOUR distinct values so a wrong read or write shows. */
interface RunTarget {
  path: string;
  runOne: string;
  runTwo: string;
  proposed: string;
  /** A fourth value, for the out-of-band write that makes a proposal stale. */
  moved: string;
}

const NOTE_TEXT =
  'SYNTHETIC — the configuration sheet and the second run disagree about how it was held';
const RECORD_RULE = 'SYNTHETIC — the campaign sheet names a different technique';
const RUN_RULE = 'SYNTHETIC — the second run was not held the way the sheet says';

/**
 * The repository root, WALKED UP FROM THE WORKING DIRECTORY.
 *
 * NOT `__dirname` AND NOT `import.meta.url`, and both halves are measured. The first
 * version used `__dirname` and failed at run time with `ReferenceError: __dirname is
 * not defined` — Playwright loads this spec as an ES module, where neither CommonJS
 * global exists. Walking up from `process.cwd()` is also what
 * `e2e/mutation/validator-package-upload.spec.ts` does, and for the reason it states:
 * it holds whether Playwright is invoked from `apps/web` (the documented way) or from
 * the repository root (the way CI does it).
 *
 * A MISS THROWS. A spec that silently found no policy file would report success for
 * zero coverage — which is precisely the failure mode step 20 exists to prevent
 * elsewhere.
 */
function repoRoot(): string {
  const marker = join('apps', 'api', 'isaac_api', 'mcp', 'policy.py');
  let dir = resolve(process.cwd());
  for (;;) {
    if (existsSync(join(dir, marker))) return dir;
    const parent = dirname(dir);
    if (parent === dir) {
      throw new Error(
        `could not find ${marker} in any ancestor of ${process.cwd()}. Step 20 reads the ` +
          'permitted MCP tool set out of that file; without it there is nothing to check.'
      );
    }
    dir = parent;
  }
}

/** Every option the vendored official schema closes this path with. */
async function schemaEnum(api: APIRequestContext, path: string): Promise<string[]> {
  const res = await api.get(`${TRUSTED_API_BASE}/schema`);
  expect(res.ok(), `GET /schema -> ${res.status()}`).toBeTruthy();
  const { schema } = (await res.json()) as { schema: Record<string, unknown> };
  let node: unknown = schema;
  for (const segment of path.split('.')) {
    const properties = (node as { properties?: Record<string, unknown> } | null)?.properties;
    if (!properties) throw new Error(`no schema node at ${path}`);
    node = properties[segment];
    if (node === undefined || node === null) throw new Error(`no schema node at ${path}`);
  }
  const values = (node as { enum?: unknown }).enum;
  if (!Array.isArray(values) || !values.every((v) => typeof v === 'string')) {
    throw new Error(`${path} is not a closed string enum in the vendored schema`);
  }
  return values as string[];
}

async function deriveRecordTarget(
  api: APIRequestContext,
  server: ServerApi,
  id: string
): Promise<RecordTarget> {
  const listed = await server.proposals(id);
  const recordScoped = [...listed.record_scoped_target_field_paths].sort();
  expect(
    recordScoped.length,
    'the server reports no RECORD-scoped proposal target; steps 6-9 have no subject'
  ).toBeGreaterThan(0);
  for (const path of recordScoped) {
    const values = await schemaEnum(api, path).catch(() => null);
    if (values !== null && values.length >= 2) {
      return { path, chosen: values[0], proposed: values[1] };
    }
  }
  throw new Error(
    `no record-scoped target is a schema enum of two or more members. Served: ${JSON.stringify(
      recordScoped
    )}`
  );
}

async function deriveRunTarget(
  api: APIRequestContext,
  server: ServerApi,
  id: string
): Promise<RunTarget> {
  const listed = await server.proposals(id);
  /*
   * RUN-SCOPED IS `target_field_paths` MINUS `record_scoped_target_field_paths` — the
   * application's own answer to "which targets are a run's", computed by
   * `routes._proposal_writer_for`. Four distinct legal values are needed here rather
   * than the three the run-scoped spec needs, because this file additionally moves the
   * target out from under a proposal to make it stale (step 13).
   */
  const runScoped = listed.target_field_paths
    .filter((p) => !listed.record_scoped_target_field_paths.includes(p))
    .sort();
  for (const path of runScoped) {
    const values = await schemaEnum(api, path).catch(() => null);
    if (values !== null && values.length >= 4) {
      const [runOne, runTwo, proposed, moved] = values;
      return { path, runOne, runTwo, proposed, moved };
    }
  }
  throw new Error(
    `no run-scoped target is a schema enum of four or more members. Served: ${JSON.stringify(
      runScoped
    )}`
  );
}

/** A proposal card addressed by path AND state — the card's own accessible name. */
function cardInState(page: Page, path: string, stateLabel: string) {
  return page.getByRole('article', {
    name: new RegExp(`^Proposal for ${path.replace(/\./g, '\\.')} — ${stateLabel}`),
  });
}

/**
 * How long a background poller may take to notice a colleague's write.
 *
 * A DEADLINE, NOT A MEASUREMENT, and the distinction is why this is the only duration
 * in the file. `useRecordSync` and `useChangeFeed` both run on `POLL_INTERVAL_MS`
 * (4,000 ms) with jitter, and `useChangeFeed` adds `CHANGE_FEED_DRAIN_DELAY_MS`
 * between continuation pages. 45 s is comfortably several cycles: it makes "the page
 * never noticed" fail rather than hang, and it asserts nothing about how fast the
 * poller actually is. No assertion in this file passes BECAUSE of a delay.
 */
const DISCOVERY_DEADLINE = 45_000;

test.describe('two scientists, one record, end to end', () => {
  // ONE test, not twenty. The steps are a SEQUENCE — step 15 is a statement about
  // what step 14 did to state that steps 2-4 created — and splitting them would mean
  // either twenty rebuilds of the same record or twenty tests sharing mutable state
  // through a module variable, which is the thing `workers: 1` and `retries: 0` exist
  // to avoid rather than to enable. Each step announces itself in the assertion
  // messages, so a failure names its step.
  test('a colleague’s proposals arrive, are judged, and land on exactly what they named', async ({
    page,
    request,
    server,
  }) => {
    // ── STEP 1 — A creates a record and opens it ─────────────────────────────
    const id = await createExperimentThroughTheUi(page, 'Two-actor workflow');
    const created = await request.get(`${TRUSTED_API_BASE}/experiments/${id}`);
    expect(created.ok(), `step 1: GET /experiments/${id} -> ${created.status()}`).toBeTruthy();
    expect((await created.json()).id, 'step 1: the server holds the record A created').toBe(id);
    expect(page.url(), 'step 1: A is on the Record Workbench for it').toContain(`/record/${id}`);

    // ── STEP 2 — A adds two Runs THROUGH THE WEBSITE ─────────────────────────
    await addRunThroughTheUi(page, 1);
    await addRunThroughTheUi(page, 2);
    const runs = await server.runs(id);
    expect(runs, 'step 2: two Add Run clicks produced two runs on the server').toHaveLength(2);
    const [runOne, runTwo] = runs;
    await expect(page.locator('.run-card'), 'step 2: both are on screen').toHaveCount(2);

    // ── STEP 3 — A enters RECORD-level information through the website ────────
    const recordTarget = await deriveRecordTarget(request, server, id);
    /*
     * A HOP TO RECORD FIELDS FIRST, THROUGH THE SIDEBAR, because that is where this
     * panel lives. The record screen is four lazily-mounted `?view=` workspaces, and
     * step 2 left A on Runs; `RecordDescriptionPanel` is on Record Fields. Clicked
     * rather than navigated so the visit — and everything the page is holding — is
     * one visit, which is what steps 6-7 depend on.
     */
    await switchWorkspace(page, 'fields');
    /*
     * THE RECORD DESCRIPTION PANEL IS COLLAPSED ON FIRST PAINT, so it is opened by
     * its own disclosure header — not by a URL parameter and not by a state poke.
     * It is mounted UNGATED on the Record Fields workspace, which is why a record with
     * no exported artifact and (a moment ago) no runs still offers it.
     */
    const recordPanel = page.getByRole('region', {
      name: 'Record Description (record-level values)',
    });
    await recordPanel.getByRole('button', { name: /^Record Description/ }).click();
    // A closed enum renders a `<select>`, and that is a schema fact rather than a
    // styling choice: a text box at this path could produce a value that cannot export.
    await recordPanel.getByLabel('Technique').selectOption(recordTarget.chosen);
    await recordPanel.getByRole('button', { name: 'Save record description' }).click();
    await expect
      .poll(
        () => server.recordFieldValue(id, recordTarget.path),
        `step 3: the website write of ${recordTarget.path} reached the server`
      )
      .toEqual(recordTarget.chosen);

    // ── STEP 4 — A enters RUN-level variables for run one, through the website ─
    // Back to Runs, where the cards are. The one A typed into in step 3 is still
    // mounted behind this switch — that is the D1 guarantee — but it is not the
    // surface this step acts on.
    await switchWorkspace(page, 'runs');
    const runTarget = await deriveRunTarget(request, server, id);
    expect(
      new Set([runTarget.runOne, runTarget.runTwo, runTarget.proposed, runTarget.moved]).size,
      'step 4: the four run-level values in play must be DISTINCT, or a wrong read passes'
    ).toBe(4);
    /*
     * TYPED INTO THE RUN CARD, WHICH AUTOSAVES. There is no per-field Save button:
     * `RunCard` queues the change and `runAutosaveStore` flushes it after a 600 ms
     * debounce through `PATCH .../runs/{id}`. That is why the confirmation below polls
     * the SERVER rather than reading the box back — reading the box back would confirm
     * only that typing works.
     */
    const runOneCard = page.locator('.run-card').first();
    await runOneCard.getByLabel('Environment').selectOption(runTarget.runOne);
    await expect
      .poll(async () => {
        const body = (await server.runBody(id, runOne.id)) as {
          run: { fields: Record<string, { value: unknown }> };
        };
        return body.run.fields[runTarget.path]?.value;
      }, `step 4: run one's ${runTarget.path} autosaved to the server`)
      .toEqual(runTarget.runOne);
    // Run two gets a DIFFERENT value out of band, so that "the panel read the run the
    // proposal names" is a distinguishable claim rather than a tautology.
    await server.setRunField(id, runTwo.id, runTarget.path, runTarget.runTwo);

    // ── STEP 5 — A opens the proposal-review surface, and it is EMPTY ─────────
    /*
     * AND THIS IS NOW A REAL "OPENS", which the step name always claimed. The
     * proposal-review surface is the Capture & Proposals workspace; it used to be
     * further down the same column, so the step asserted a heading it had not
     * navigated to. A opens it here and STAYS here for steps 6-17 — the live-arrival
     * assertion in step 7 depends on no navigation happening after this point.
     */
    await switchWorkspace(page, 'capture');
    const proposals = page.getByRole('region', { name: 'Ingestion Proposals' });
    await expect(
      page.getByRole('heading', { name: 'Ingestion Proposals' }),
      'step 5: the review surface is on this screen'
    ).toBeVisible();
    await expect(
      proposals.locator('.proposals-empty'),
      'step 5: and it holds nothing yet — no proposal is manufactured by opening it'
    ).toBeVisible();
    await expect(proposals.locator('.proposal-card')).toHaveCount(0);
    expect((await server.proposals(id)).proposals, 'step 5: nor on the server').toHaveLength(0);

    // ── STEP 6 — B creates a RECORD-scoped proposal, with an idempotence key ──
    const noteId = await server.captureNote(id, NOTE_TEXT);
    const RECORD_KEY = 'two-actor-record-1';
    const recordProposal = await server.propose(id, {
      note_id: noteId,
      target_field_path: recordTarget.path,
      proposed_value: recordTarget.proposed,
      rule: RECORD_RULE,
      client_request_key: RECORD_KEY,
    });
    expect(
      recordProposal.run_id,
      'step 6: a RECORD-scoped proposal names no run'
    ).toBeNull();
    expect(recordProposal.client_request_key, 'step 6: the key is stored').toBe(RECORD_KEY);
    /*
     * THE RETRY, ASSERTED RATHER THAN ASSUMED. An MCP producer that never saw the
     * answer to its first request sends the same key again; the route must answer the
     * SAME proposal with `deduplicated: true` rather than mint a second one. Without
     * this, "exactly once" is a property of the docstring.
     */
    const replay = await server.proposeRaw(id, {
      note_id: noteId,
      target_field_path: recordTarget.path,
      proposed_value: recordTarget.proposed,
      rule: RECORD_RULE,
      client_request_key: RECORD_KEY,
    });
    expect(replay.deduplicated, 'step 6: a replayed key is DEDUPLICATED').toBe(true);
    expect(replay.proposal.proposal_id, 'step 6: and returns the SAME proposal').toBe(
      recordProposal.proposal_id
    );
    expect(
      (await server.proposals(id)).proposals,
      'step 6: so the record holds ONE proposal, not two'
    ).toHaveLength(1);

    // ── STEP 7 — A's page discovers it WITHOUT a reload or a navigation ───────
    /*
     * NOTHING IS RELOADED, NAVIGATED, OR CLICKED BETWEEN STEP 6 AND THIS ASSERTION.
     * The page has been open since step 1; the only mechanism that can bring the
     * proposal onto it is the change feed reaching `IngestionProposalsPanel` through
     * `useRecordSession.proposalActivity`. If that wiring were absent this would hang
     * to the deadline and fail — which is the whole reason the step exists.
     */
    const arrivalNote = proposals.locator('.proposals-arrival-note-text');
    await expect(arrivalNote, 'step 7: the arrival note appears on its own').toBeVisible({
      timeout: DISCOVERY_DEADLINE,
    });
    const arrivalText = (await arrivalNote.textContent()) ?? '';
    expect(arrivalText, 'step 7: it says at least one arrived and is ready to review').toBe(
      'At least 1 proposed change arrived and is ready to review.'
    );
    // THE SAME SENTENCE REACHED THE LIVE REGION, so a screen-reader user was told too.
    // A visible note nobody is told about is half a feature.
    await expect(
      proposals.locator('p.sr-only[role="status"]'),
      'step 7: and the sr-only status region received a sentence about it'
    ).toContainText('proposed change');
    /*
     * AND IT LEAKS NO CONTENT. The announcement is built from a COUNT and fixed words
     * — never the proposed value and never the field path — so a live region cannot
     * read out a scientific value nobody asked for.
     */
    expect(arrivalText, 'step 7: the sentence names no proposed value').not.toContain(
      recordTarget.proposed
    );
    expect(arrivalText, 'step 7: and no field path').not.toContain(recordTarget.path);
    /*
     * AND THE SPOKEN SENTENCE IS CHECKED TOO, NOT ONLY THE VISIBLE ONE. They are built
     * by two separate expressions — the visible note is a RUNNING TOTAL since the last
     * dismiss, the announced one is THIS arrival's own delta — so content-freedom
     * established on one is not established on the other. The live region is the half
     * a reader cannot see and cannot un-hear.
     */
    const spokenText = (await proposals.locator('p.sr-only[role="status"]').textContent()) ?? '';
    expect(spokenText, 'step 7: the ANNOUNCED sentence names no proposed value').not.toContain(
      recordTarget.proposed
    );
    expect(spokenText, 'step 7: and no field path').not.toContain(recordTarget.path);

    // ── STEP 8 — the card renders, with current and proposed distinguishable ──
    const recordCard = proposalCard(page, recordTarget.path);
    await expect(recordCard, 'step 8: the card is on screen').toBeVisible();
    await expect(
      recordCard.locator('.proposal-scope'),
      'step 8: and says it is about the record, not a run'
    ).toHaveText('On the record');
    await expect(recordCard.locator('.proposal-value-label').first()).toHaveText('Proposed value');
    await expect(recordCard.locator('.proposal-value-body').first()).toContainText(
      recordTarget.proposed
    );
    // NOTHING IS READ UNTIL A PERSON ASKS — one current-value read per card on mount
    // would be N requests for a question nobody asked.
    await recordCard.getByRole('button', { name: 'Show What the Record Holds Now' }).click();
    const recordCurrent = recordCard.locator('.proposal-current-body .proposal-value-body');
    await expect(recordCurrent, 'step 8: the CURRENT value is what A entered').toContainText(
      recordTarget.chosen
    );
    await expect(recordCurrent, 'step 8: and is NOT the proposed one').not.toContainText(
      recordTarget.proposed
    );

    // ── STEP 9 — A REJECTS it through the UI, with a reason ───────────────────
    const valueBeforeReject = await server.recordFieldValue(id, recordTarget.path);
    await recordCard.getByRole('button', { name: 'Reject…' }).click();
    await recordCard.getByLabel('Reason (optional)').fill('SYNTHETIC — the sheet is the stale one');
    await recordCard.getByRole('button', { name: 'Confirm Reject' }).click();
    await expect(
      cardInState(page, recordTarget.path, 'Rejected'),
      'step 9: the card is rejected on screen'
    ).toBeVisible();
    const rejected = (await server.proposals(id)).proposals.find(
      (p) => p.proposal_id === recordProposal.proposal_id
    );
    expect(rejected?.state, 'step 9: and rejected on the server').toBe('rejected');
    const rejectEntry = rejected?.history.find((h) => h.action === 'reject');
    expect(rejectEntry?.reason, 'step 9: the reason A typed was stored verbatim').toBe(
      'SYNTHETIC — the sheet is the stale one'
    );
    expect(
      await server.recordFieldValue(id, recordTarget.path),
      'step 9: and the canonical record value is UNCHANGED by a rejection'
    ).toEqual(valueBeforeReject);
    expect(rejected?.accepted_value, 'step 9: nothing was written').toBeNull();

    // ── STEP 10 — B creates a RUN-scoped proposal, for the SECOND run ─────────
    /*
     * THE SECOND RUN, DELIBERATELY. A write that defaulted to `runs[0]` would be
     * indistinguishable from a correct one if the target were the first — and that is
     * the exact mutation `test_run_scoped_proposal_lifecycle.py` uses.
     */
    const runsReads: string[] = [];
    /*
     * THE FEED POLLS ARE COUNTED TOO, and they are the SETTLE this step needs rather
     * than a duration. See the quiescence assertion after the count below.
     */
    const feedReads: string[] = [];
    const recordRunsRe = new RegExp(`/experiments/${id}/runs(\\?|$)`);
    const recordChangesRe = new RegExp(`/experiments/${id}/changes(\\?|$)`);
    page.on('request', (req) => {
      if (req.method() !== 'GET') return;
      if (recordRunsRe.test(req.url())) runsReads.push(req.url());
      if (recordChangesRe.test(req.url())) feedReads.push(req.url());
    });
    const runsReadsBefore = runsReads.length;

    const runProposal = await server.propose(id, {
      note_id: noteId,
      run_id: runTwo.id,
      target_field_path: runTarget.path,
      proposed_value: runTarget.proposed,
      rule: RUN_RULE,
      client_request_key: 'two-actor-run-1',
    });
    expect(runProposal.run_id, 'step 10: it names the SECOND run').toBe(runTwo.id);

    // ── STEP 11 — A's page refreshes both surfaces WITHOUT a reload ───────────
    const runCard = proposalCard(page, runTarget.path);
    await expect(runCard, 'step 11: the new card appears with no reload').toBeVisible({
      timeout: DISCOVERY_DEADLINE,
    });
    await expect(runCard.locator('.proposal-scope')).toHaveText(`On run ${runTwo.id}`);
    /*
     * THE DISCLOSED COST OF THE RUNS RE-READ, COUNTED AT THE WIRE.
     *
     * Creating a proposal bumps the RECORD's revision. `RunsSection` therefore sees
     * `recordVersion` move — its COMPLETENESS path, the one that exists because the
     * feed structurally cannot report a run removal — and re-reads its first page
     * once, bounded. That cost is real and is stated rather than hidden: a
     * completeness path that ignored a record-only bump would ignore removals too.
     *
     * The bound is asserted on the URL: `limit` must be present and must be the
     * received count (2), not the page size. An UNBOUNDED re-read would fetch a
     * 1,000-run list because a proposal was filed.
     */
    await expect
      .poll(
        () => runsReads.length - runsReadsBefore,
        'step 11: exactly ONE bounded runs re-read is attributable to the proposal act'
      )
      .toBe(1);
    const attributedRead = runsReads[runsReadsBefore];
    const attributedLimit = new URL(attributedRead).searchParams.get('limit');
    expect(attributedLimit, `step 11: and it is BOUNDED — ${attributedRead}`).toBe('2');
    /*
     * AND IT IS STILL EXACTLY ONE AFTER TWO MORE FEED POLLS.
     *
     * `expect.poll(...).toBe(1)` above establishes only that the count REACHES 1 — it
     * returns the instant it does, so a second, third or tenth re-read arriving a
     * moment later would pass it. A bound that fires once per POLL rather than once
     * per EVENT is exactly the defect `live-refresh-request-graph.test.tsx` exists to
     * catch, and it is invisible to a "reaches" assertion.
     *
     * THE SETTLE IS THE CLIENT'S OWN POLLER, NOT A SLEEP AND NOT A SERVER READ. Two
     * further `GET .../changes` from the PAGE are waited for, because that is the
     * mechanism under suspicion: the feed re-delivers a summary every poll until the
     * screen's own revision catches up, so if the runs re-read were keyed on
     * delivery rather than deduped, more polls would mean more reads. Two is enough
     * for the count to move if it is going to.
     *
     * `DISCOVERY_DEADLINE` IS PASSED EXPLICITLY, because `expect.poll`'s own default
     * is 15 s and two polls of a JITTERED 4 s cadence do not reliably fit inside it
     * under load — measured: `Expected: >= 2 Received: 1`. That is a budget, not a
     * timing assertion; the deadline exists so a poller that has stopped fails
     * instead of hanging.
     *
     * AN EARLIER VERSION POLLED THE SERVER FOR AN EMPTY FEED PAGE and could never
     * pass: `server.changes(id, { limit: 200 })` sends NO CURSOR, so it is a
     * cursorless resync that returns the record's whole entity set every time. It
     * failed `Expected: 0 Received: 5`. A quiescence condition has to be a statement
     * about the CLIENT, which is the thing that might be misbehaving.
     */
    const feedReadsAtCount = feedReads.length;
    await expect
      .poll(
        () => feedReads.length - feedReadsAtCount,
        {
          message: 'step 11: settle — wait for two further feed polls from the page itself',
          timeout: DISCOVERY_DEADLINE,
        }
      )
      .toBeGreaterThanOrEqual(2);
    expect(
      runsReads.length - runsReadsBefore,
      'step 11: and it is STILL exactly one after two further feed polls — the bound ' +
        'fires once per EVENT, not once per poll'
    ).toBe(1);

    // ── STEP 12 — three distinct values, and the label says whose ─────────────
    await runCard.getByRole('button', { name: 'Show What the Record Holds Now' }).click();
    const runCurrentLabel = runCard.locator('.proposal-current-label');
    const runCurrent = runCard.locator('.proposal-current-body .proposal-value-body');
    await expect(runCurrent, 'step 12: the current value is RUN TWO’s').toContainText(
      runTarget.runTwo
    );
    await expect(runCurrent, 'step 12: not run one’s').not.toContainText(runTarget.runOne);
    await expect(runCurrent, 'step 12: and not the proposal’s').not.toContainText(
      runTarget.proposed
    );
    // A correct value under a label claiming it came from the record would still be a
    // false statement about provenance.
    await expect(runCurrentLabel, 'step 12: and the label says it is a RUN’s value').toHaveText(
      /run/i
    );
    await expect(runCard.locator('.proposal-value-body').first()).toContainText(
      runTarget.proposed
    );

    // ── STEP 13 — stale-revision protection, on a THROWAWAY proposal ──────────
    /*
     * A THROWAWAY PROPOSAL ON **RUN ONE**, AND BOTH HALVES OF THAT CHOICE ARE
     * MEASURED RATHER THAN PREFERRED.
     *
     * WHY A THROWAWAY AND NOT STEP 10'S PROPOSAL: because staleness CANNOT BE
     * UNDONE. The first version of this step made step 10's proposal stale and then
     * wrote the old value back, expecting `target_stale` to return to `false`. It
     * stayed `true` — `Timeout 15000ms exceeded while waiting on the predicate ...
     * Expected: false Received: true` — and `proposals.target_digest`'s own docstring
     * says why: the digest is taken over *"the draft field envelope (value AND
     * evidence, which is why an added confirmation moves it)"*. Restoring the value
     * ADDS a confirmation, so the digest moves again and can never return. That is
     * correct behaviour and a fact worth carrying: **a stale proposal is recovered by
     * withdrawing or superseding it, never by restoring the value.**
     *
     * WHY RUN ONE: `context.environment` is the ONLY run-scoped target the vendored
     * schema closes with an enum — measured over all 17 run-scoped paths, the other 16
     * are open strings or numbers — so a throwaway at a DIFFERENT PATH is not
     * available. A different RUN is, and it is strictly better: it makes this step
     * prove that staleness is scoped to the (run, path) pair rather than to the
     * record, which a same-run throwaway could not.
     */
    const throwaway = await server.propose(id, {
      note_id: noteId,
      run_id: runOne.id,
      target_field_path: runTarget.path,
      proposed_value: runTarget.moved,
      rule: `${RUN_RULE} (throwaway, for the staleness check)`,
      client_request_key: 'two-actor-run-throwaway',
    });
    expect(throwaway.run_id, 'step 13: the throwaway names run ONE').toBe(runOne.id);
    // B MOVES THE TARGET out from under it.
    await server.setRunField(id, runOne.id, runTarget.path, runTarget.moved);
    await expect
      .poll(async () => {
        const found = (await server.proposals(id)).proposals.find(
          (p) => p.proposal_id === throwaway.proposal_id
        );
        return found?.target_stale;
      }, 'step 13: the list read reports the throwaway proposal as target_stale')
      .toBe(true);
    /*
     * AND STEP 10'S PROPOSAL IS UNTOUCHED. This is the assertion the run-one choice
     * buys: the record's revision moved, `base_rev` moved with it, and the proposal on
     * RUN TWO is still not stale — because the digest is over the TARGET's content,
     * which is exactly what `target_digest`'s docstring says `base_rev` would get
     * wrong "in both directions".
     */
    const untouched = (await server.proposals(id)).proposals.find(
      (p) => p.proposal_id === runProposal.proposal_id
    );
    expect(
      untouched?.target_stale,
      'step 13: staleness is scoped to the (run, path) pair, not to the record'
    ).toBe(false);
    /*
     * AN ACCEPT OF THE STALE ONE IS REFUSED. Measured over HTTP rather than through
     * the button, because the SERVER's refusal is the guarantee — the panel
     * deliberately still OFFERS Accept on a stale proposal
     * (`acceptUnavailableReason` fails open, since `target_stale` was read a moment ago
     * and the value at the target can move back), and its own copy says the server
     * decides. A UI-only check would be asserting the fail-open, not the gate.
     */
    const refused = await server.review(id, throwaway.proposal_id, {
      action: 'accept',
      accepted_from: 'candidate',
      confirmed_by_user: true,
    });
    expect(refused.status, 'step 13: accepting a stale proposal is REFUSED').toBe(409);
    expect(refused.body.error, 'step 13: and says exactly why').toBe('proposal_stale');
    /*
     * THE SCREEN SAYS THE SAME THING, in a scientist's words. Addressed by the SCOPE
     * line rather than by `.first()`: two open proposals now share `runTarget.path`
     * and differ only in which run they name, so an index would be asserting whichever
     * one the panel happened to order first.
     */
    const throwawayCard = page
      .locator('.proposal-card')
      .filter({ has: page.locator('.proposal-scope', { hasText: `On run ${runOne.id}` }) });
    await expect(
      throwawayCard.locator('.proposal-target-state'),
      'step 13: the stale card tells the reader the value moved'
    ).toContainText(/CHANGED since this proposal was made/, { timeout: DISCOVERY_DEADLINE });
    // WITHDRAWN, NOT DELETED — which is the only recovery there is, per the note above.
    const withdrawn = await server.review(id, throwaway.proposal_id, {
      action: 'withdraw',
      reason: 'SYNTHETIC — made only to measure the stale refusal',
      confirmed_by_user: true,
    });
    expect(withdrawn.status, 'step 13: withdrawing needs no attributable actor').toBe(200);
    await expect(
      cardInState(page, runTarget.path, 'Withdrawn'),
      'step 13: and it stays readable on the record, marked withdrawn'
    ).toBeVisible({ timeout: DISCOVERY_DEADLINE });

    // ── STEP 14 — A ACCEPTS through the UI, under the trusted identity ────────
    const runOneBefore = await server.runBody(id, runOne.id);
    const cursorBeforeAccept = (await server.changes(id, { limit: 200 })).next_cursor;
    /*
     * THE RECORD'S REV AT THE SAME INSTANT AS THE CURSOR — step 17's real floor.
     *
     * It is read here rather than derived in step 17 because the whole claim is
     * "everything the feed reports after this point moved AFTER this point", and that
     * needs the position captured BEFORE the accept. The token is
     * `<generation>.<rev>`; the rev is the half after the last dot, parsed exactly as
     * `useRecordSync` and `RunsSection` parse it.
     */
    const versionBeforeAccept = await server.version(id);
    const revBeforeAccept = Number(
      versionBeforeAccept.slice(versionBeforeAccept.lastIndexOf('.') + 1)
    );
    expect(
      Number.isFinite(revBeforeAccept),
      'step 14: the record version token must carry a numeric rev for step 17 to have a floor'
    ).toBe(true);
    const liveRunCard = cardInState(page, runTarget.path, 'Awaiting your judgement');
    await expect(liveRunCard, 'step 14: the open card is the one A acts on').toBeVisible({
      timeout: DISCOVERY_DEADLINE,
    });
    await liveRunCard.getByRole('button', { name: 'Accept as Proposed' }).click();
    await expect(
      cardInState(page, runTarget.path, 'Accepted'),
      'step 14: the screen shows it accepted'
    ).toBeVisible();
    const accepted = (await server.proposals(id)).proposals.find(
      (p) => p.proposal_id === runProposal.proposal_id
    );
    expect(accepted?.state, 'step 14: the server recorded the acceptance').toBe('accepted');
    expect(accepted?.accepted_value, 'step 14: with the proposed value').toBe(runTarget.proposed);
    expect(accepted?.accepted_from, 'step 14: as proposed, not corrected').toBe('candidate');
    expect(accepted?.applied_run_id, 'step 14: applied to the run it named').toBe(runTwo.id);

    // ── STEP 15 — ONLY run two changed ───────────────────────────────────────
    const runTwoAfter = (await server.runBody(id, runTwo.id)) as {
      run: { fields: Record<string, { value: unknown; evidence: unknown[] }> };
    };
    expect(
      runTwoAfter.run.fields[runTarget.path]?.value,
      'step 15: run two carries the accepted value'
    ).toBe(runTarget.proposed);
    /*
     * THE WHOLE DOCUMENT of the run this proposal did NOT name, not chosen keys —
     * `version`, `rev` and `updated_utc` included. A run's version token is the RUN's
     * own `<generation>.<rev>`, so the RECORD's revision moving does not touch it,
     * which is what makes this comparison meaningful rather than merely lucky.
     *
     * DOCUMENT-IDENTICAL, NOT BYTE-IDENTICAL: `toEqual` compares parsed bodies, so a
     * key reordering would pass. Content is the right claim here.
     */
    expect(
      await server.runBody(id, runOne.id),
      'step 15: the run this proposal did not name was not modified by accepting it'
    ).toEqual(runOneBefore);

    // ── STEP 16 — attribution and audit history ──────────────────────────────
    const acceptEntry = accepted?.history.find((h) => h.action === 'accept');
    expect(acceptEntry, 'step 16: the acceptance is in the history').toBeTruthy();
    expect(acceptEntry?.actor_subject, 'step 16: attributed to the vouched subject').toBe(
      FIXTURE_ACTOR_SUBJECT
    );
    expect(acceptEntry?.actor_trust_basis, 'step 16: on a basis that says what it is worth').toBe(
      FIXTURE_TRUST_BASIS
    );
    /*
     * PROPOSING STAYS UNATTRIBUTED, and that is the boundary rather than a gap:
     * nobody was named when the proposal was made, creating one requires no actor in
     * any deployment, and inventing an actor for it would be the fabrication this
     * programme refuses. Only the JUDGEMENT is attributed.
     */
    const proposeEntry = accepted?.history.find((h) => h.action === 'propose');
    expect(proposeEntry?.actor_subject, 'step 16: proposing named nobody').toBeNull();
    expect(proposeEntry?.actor_trust_basis).toBe('unattributed');
    /*
     * AND THE RUN'S FIELD CARRIES THE WRITER'S OWN CONFIRMATION. Quoted rather than
     * counted: the accepted value arrives as a `user_confirmation` evidence entry
     * whose `answer` IS the value, so the field is evidenced by the act that set it
     * rather than by an assertion that it was set.
     */
    const evidence = runTwoAfter.run.fields[runTarget.path]?.evidence as {
      source_type: string;
      answer: unknown;
    }[];
    const confirmation = evidence.find((e) => e.answer === runTarget.proposed);
    expect(confirmation, 'step 16: the accepted value earned an evidence entry').toBeTruthy();
    expect(confirmation?.source_type, 'step 16: and it is a user confirmation').toBe(
      'user_confirmation'
    );

    // ── STEP 17 — the change feed reports it once, and drains ────────────────
    const page1 = await server.changes(id, { cursor: cursorBeforeAccept, limit: 200 });
    expect(page1.limit, 'step 17: the server used the page size asked for').toBe(200);
    const seen = page1.changes;
    const proposalEntries = seen.filter(
      (c) => c.kind === 'proposal' && c.entity_id === runProposal.proposal_id
    );
    expect(proposalEntries, 'step 17: the accepted proposal appears ONCE').toHaveLength(1);
    expect(proposalEntries[0].state, 'step 17: in its current state').toBe('accepted');
    const runTwoEntries = seen.filter((c) => c.kind === 'run' && c.entity_id === runTwo.id);
    expect(runTwoEntries, 'step 17: run two appears ONCE').toHaveLength(1);
    expect(
      seen.filter((c) => c.kind === 'run' && c.entity_id === runOne.id),
      'step 17: and run one is ABSENT — it did not move'
    ).toHaveLength(0);
    /*
     * ABOVE THE CURSOR, which is the property that makes a cursor a cursor — and
     * measured against the RECORD'S REV AT THE CURSOR, not against zero.
     *
     * `toBeGreaterThan(0)` stood here and was VACUOUS: `change_feed` floors every
     * served position at >= 1 on read, so that assertion could not fail for any entry
     * the feed is capable of returning, while its message claimed a comparison
     * against the pre-accept cursor. It is the exact shape of defect this repository
     * keeps recording — an assertion that reads as a guarantee and is true by
     * construction. `revBeforeAccept` is captured in step 14 beside the cursor itself.
     */
    expect(seen.length, 'step 17: the page reports something, so the loop below is not vacuous')
      .toBeGreaterThan(0);
    for (const entry of seen) {
      expect(
        entry.changed_at_rev,
        `step 17: ${entry.kind} ${entry.entity_id} at rev ${entry.changed_at_rev} must be ` +
          `above the record's rev when the cursor was taken (${revBeforeAccept})`
      ).toBeGreaterThan(revBeforeAccept);
    }
    // DRAINS, AND NO ENTRY IS SERVED TWICE ACROSS PAGES.
    let cursor = page1.next_cursor;
    let guard = 0;
    const allIds = seen.map((c) => `${c.kind}:${c.entity_id}`);
    let pageN = page1;
    while (pageN.has_more) {
      expect(++guard, 'step 17: the drain terminates').toBeLessThan(20);
      pageN = await server.changes(id, { cursor, limit: 200 });
      cursor = pageN.next_cursor;
      allIds.push(...pageN.changes.map((c) => `${c.kind}:${c.entity_id}`));
    }
    expect(pageN.has_more, 'step 17: the feed drains to has_more: false').toBe(false);
    expect(
      allIds.length,
      'step 17: no entity was served twice across the pages'
    ).toBe(new Set(allIds).size);
    const afterDrain = await server.changes(id, { cursor, limit: 200 });
    expect(afterDrain.changes, 'step 17: a drained feed reports nothing further').toHaveLength(0);

    // ── STEP 18 — durability across a RELOAD ────────────────────────────────
    /*
     * WHAT THIS PROVES AND WHAT IT DOES NOT.
     *
     * PROVES: nothing above lived in the page. A reload discards every React state,
     * every ref and every in-memory cache, so each value asserted below was re-read
     * from the server over HTTP.
     *
     * DOES NOT PROVE: PostgreSQL durability. This backend is FILESYSTEM-BACKED —
     * asserted from `/api/health` immediately below rather than assumed, so this
     * caveat cannot quietly become false if the suite is ever pointed at a database.
     * The PostgreSQL leg is `apps/api/tests/test_proposal_durability.py`'s real-engine
     * scenarios, which run in CI against a real `postgres:18`; it is CITED here and
     * not claimed.
     */
    const health = await (await request.get(`${TRUSTED_API_BASE}/health`)).json();
    expect(
      health.experiment_storage.backend,
      'step 18: this backend is filesystem-backed, so PostgreSQL durability is CI’s claim'
    ).toBe('filesystem');

    await page.reload();
    await expect(page.getByRole('heading', { name: 'Ingestion Proposals' })).toBeVisible();
    await expect(
      cardInState(page, runTarget.path, 'Accepted'),
      'step 18: the accepted proposal survives'
    ).toBeVisible();
    await expect(
      cardInState(page, recordTarget.path, 'Rejected'),
      'step 18: and so does the rejected one — a rejection is KEPT, not deleted'
    ).toBeVisible();
    /*
     * THE RUNS ARE READ ON THEIR OWN WORKSPACE, AND THE COUNT IS ASSERTED AS VISIBLE
     * RATHER THAN AS PRESENT.
     *
     * The reload lands on `?view=capture`, where `RunsSection` is not mounted — so
     * this assertion has to switch. It is also strengthened while it moves:
     * `toHaveCount` counts the DOM and would pass over two hidden cards, which is
     * exactly the state a reader would experience as the runs having vanished. Each
     * card is asserted VISIBLE, which is the claim "both runs survive a reload"
     * actually makes.
     */
    await switchWorkspace(page, 'runs');
    const survivingRuns = page.locator('.run-card');
    await expect(survivingRuns, 'step 18: both runs survive a reload').toHaveCount(2);
    await expect(survivingRuns.nth(0)).toBeVisible();
    await expect(survivingRuns.nth(1)).toBeVisible();
    expect(
      await server.recordFieldValue(id, recordTarget.path),
      'step 18: A’s record-level value survives'
    ).toEqual(recordTarget.chosen);

    // ── STEP 19 — validation reads the accepted value ────────────────────────
    const verdict = await server.validate(id);
    expect(verdict.official_validator_ran, 'step 19: the official validator ran').toBe(true);
    /*
     * THE RECORD IS NOT EXPORTABLE, AND THAT IS THE MEASUREMENT RATHER THAN A
     * DISAPPOINTMENT. A record created through the product's own path still owes the
     * blocking questions nothing in this test answered — so the honest assertion is
     * the two-parter the charter asks for: the accepted value IS in the served draft,
     * and the dry run names only OTHER fields.
     *
     * Measured over HTTP at this HEAD, on exactly this record shape, the three
     * top-level refusals are `descriptors`, `context.temperature_K` and
     * `system.domain`. They are asserted as a SET RATHER THAN A LIST OF THREE, because
     * the claim being made is "none of them is the field the proposal wrote", not
     * "there are exactly three".
     */
    expect(verdict.ok, 'step 19: it does not export yet, and says so').toBe(false);
    const messages = verdict.errors.map((e) => `${e.path} ${e.message}`);
    /*
     * NON-VACUITY FIRST. The loop below asserts a property OF EACH refusal, so on an
     * empty `errors` it would assert nothing at all and read as a pass — the same
     * shape as the `toBeGreaterThan(0)` defect corrected in step 17. `ok: false`
     * above guarantees there is SOMETHING wrong; this guarantees the wire actually
     * enumerated it, which is a different claim.
     */
    expect(
      messages.length,
      'step 19: the dry run enumerated its refusals, so the loop below is not vacuous'
    ).toBeGreaterThan(0);
    for (const message of messages) {
      expect(
        message,
        `step 19: no refusal names the accepted value — ${message}`
      ).not.toContain(runTarget.proposed);
      expect(
        message,
        `step 19: nor the record-level value A entered — ${message}`
      ).not.toContain(recordTarget.chosen);
    }
    // The accepted value IS what the served draft holds, so validation was reading it.
    const runTwoDraft = (await server.runBody(id, runTwo.id)) as {
      run: { fields: Record<string, { value: unknown }> };
    };
    expect(
      runTwoDraft.run.fields[runTarget.path]?.value,
      'step 19: what the validator read at the target is the accepted value'
    ).toBe(runTarget.proposed);
    // And the per-run verdicts exist, so the dry run genuinely walked the runs.
    expect(verdict.runs?.length, 'step 19: the dry run judged each run').toBe(2);

    // ── STEP 20 — the tooling cannot Submit, export, or accept ───────────────
    /*
     * TWO HALVES, AND ONLY ONE OF THEM IS MEASURABLE IN THIS PROCESS.
     *
     * (a) NO PERMITTED TOOL CAN ACCEPT, SUBMIT OR EXPORT. `PERMITTED_TOOL_NAMES` is
     *     parsed out of `mcp/policy.py` here rather than fetched, and the reason is
     *     measured: this deployment mounts NO MCP transport at all (asserted below),
     *     so there is no `tools/list` to call. Reading the policy source is the
     *     established precedent in this repository —
     *     `src/__tests__/connect-your-agent.test.tsx:726` does exactly this, and its
     *     own comment records the defect that hardened the parser (a quoted phrase in
     *     a comment INSIDE the literal read as a fifteenth tool). Comment text is
     *     stripped here for the same reason.
     *
     * (b) AN ACCEPT WITHOUT A VERIFIED IDENTITY IS REFUSED. NOT MEASURABLE HERE, and
     *     said plainly rather than skipped: the verifier is chosen from the BACKEND
     *     PROCESS's environment and this suite exists precisely because it sets
     *     `ISAAC_EDGE_TRUST_VERIFIER=test_fixture`. One process has one configuration.
     *     That leg is `apps/web/e2e/mutation/proposals.spec.ts`'s
     *     *"accepting is refused truthfully, and nothing is written"*, which asserts
     *     `409 human_actor_required` against a backend with no verifier. It is CITED,
     *     not reproduced.
     */
    const policySource = readFileSync(
      join(repoRoot(), 'apps/api/isaac_api/mcp/policy.py'),
      'utf8'
    );
    const block = policySource.match(/PERMITTED_TOOL_NAMES = frozenset\(\s*\{([^}]*)\}/);
    expect(block, 'step 20: PERMITTED_TOOL_NAMES is readable in policy.py').toBeTruthy();
    const toolNames = (block as RegExpMatchArray)[1]
      .split('\n')
      .map((line) => line.replace(/#.*$/, '')) // comments cannot inject a tool name
      .join('\n')
      .match(/"([^"]+)"/g)
      ?.map((quoted) => quoted.slice(1, -1)) ?? [];
    expect(toolNames.length, 'step 20: the permitted set is non-empty').toBeGreaterThan(0);
    for (const forbidden of ['accept', 'approve', 'submit', 'export', 'publish', 'delete']) {
      expect(
        toolNames.filter((name) => name.includes(forbidden)),
        `step 20: no permitted tool name contains "${forbidden}" — ${JSON.stringify(toolNames)}`
      ).toEqual([]);
    }
    /*
     * AND THE TRANSPORT IS NOT EVEN MOUNTED. A 404 rather than a 403, deliberately:
     * `mcp_transport_or_none` registers NO ROUTE for an unconfigured deployment,
     * because *"a path that refuses is still a path that says ISAAC speaks MCP, find
     * the credential"*. So in this configuration the permitted tools are not merely
     * unable to accept — they are unreachable.
     */
    const mcp = await request.post(`${TRUSTED_API_BASE}/mcp`, {
      headers: { 'content-type': 'application/json' },
      data: { jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} },
    });
    expect(
      mcp.status(),
      'step 20: this deployment mounts no MCP transport, so there is no route at all'
    ).toBe(404);
  });
});

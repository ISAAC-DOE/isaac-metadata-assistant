/**
 * INGESTION PROPOSALS — the scientist's review workflow, end to end, in a browser.
 *
 * WHAT WAS MISSING AND WHY THIS FILE EXISTS. Four slices built the machinery: the
 * model (`apps/api/isaac_api/proposals.py`), four routes, four MCP tools, the change
 * feed's `proposal` kind, and the review surface
 * (`apps/web/src/components/IngestionProposalsPanel.tsx`). Between them they are
 * covered by 3,127 lines of `apps/api/tests/test_ingestion_proposals.py`, a 14-scenario
 * durability suite against a real PostgreSQL, and 56 component tests
 * (`npx vitest run src/__tests__/ingestion-proposals-panel.test.tsx` — "56 passed").
 * NONE of them shows a person opening a record in a browser, seeing a stored
 * suggestion, and clearing it. That walk is what this file measures.
 *
 * ONE DEFECT WAS FOUND WHILE WRITING IT AND IS REPORTED RATHER THAN FIXED — this is a
 * measurement slice. `IngestionProposalsPanel`'s `activity` prop, the whole point of
 * the slice that mounted `useChangeFeed`, is dead in practice for the `proposal` kind:
 * the record poller's silent refetch advances the ONE floor `summariseChanges` filters
 * against, and a proposal entry always shares its `changed_at_rev` with the experiment
 * entry beside it. The full measurement, with timings from two runs, is in the block
 * above `an unsaved correction survives a background change-feed refresh`.
 *
 * THE ONE RULE, inherited from `fixtures.ts` and not weakened here: **the reviewed act
 * happens through the visible UI.** The API is used to establish a starting state (a
 * proposal, because nothing in this build produces one — see below), to reach behind
 * the UI's back and simulate a second client, and to read server state back as an
 * independent check. It is never used to perform the act under test. No proposal is
 * rejected, superseded, withdrawn or accepted here by anything but a click.
 *
 * WHY STEP 1 IS API-SIDE SETUP AND THAT IS NOT A GAP IN THE PROOF. There is no producer
 * in the product: `routes.py` states it — *"NOTHING WAS REWIRED TO FEED THEM. There is
 * no automatic producer"* — and `lib/api.ts` deliberately ships no `createProposal`,
 * *"so adding a create button here would be this client manufacturing the queue it is
 * reviewing"*. A browser cannot create one because no surface may. Setting the starting
 * state over HTTP is therefore the only way to reach the surface under test at all, and
 * it is exactly clause (a) of this suite's rule.
 *
 * ── THE ACCEPTANCE QUESTION, ANSWERED IN THE FILE RATHER THAN IN A REPORT ───────────
 *
 * `accept` answers **409 `human_actor_required`** in every default-configured
 * deployment and writes nothing, because no verifier in this build reads a request and
 * the trusted authentication boundary has not been built (contract §5 I4, §10.4;
 * `CLAUDE.md` §15). That is a fact about CONFIGURATION, not about the build — the
 * contract is explicit that a test must not assume acceptance is unreachable, because a
 * deployment setting `ISAAC_EDGE_TRUST_VERIFIER=test_fixture` and
 * `ISAAC_FIXTURE_ACTOR_SUBJECT` selects `FixtureEdgeVerifier` and acceptance then
 * succeeds.
 *
 * So this file does neither of the two wrong things. It does not assume acceptance
 * succeeds, and it does not assert it is unreachable. It **asserts the configuration it
 * is running under, first, from the server's own `/api/health`**, and only then asserts
 * what that configuration does. `assertNoAttributableActor` is that premise check: if
 * someone runs this suite against a backend that DOES establish an actor, the spec
 * fails on the premise with a sentence saying so, rather than failing on an assertion
 * that would read like a product defect.
 *
 * THE SUCCESSFUL-ACCEPTANCE LEG IS NOT PROVEN HERE, AND THE REASON IS STRUCTURAL, NOT
 * A DECISION TO SKIP IT. The verifier is chosen from the BACKEND PROCESS's environment,
 * and this suite starts exactly one backend (`playwright.mutation.config.ts`
 * `webServer[0]`). One process has one configuration, so the refusal leg and the
 * success leg cannot both be measured in one run of one suite — and the refusal is the
 * configuration every shipped deployment has, which makes it the one this suite must
 * cover. The success leg is measured, against the fixture verifier, by
 * `apps/api/tests/test_ingestion_proposals.py::test_I4_accept_succeeds_and_stamps_the_actor_under_the_fixture_verifier`
 * and `::test_an_edited_acceptance_writes_the_corrected_value`. What this file adds
 * that those cannot is that the REFUSAL reaches the scientist as a sentence, and that
 * the record is genuinely untouched afterwards.
 *
 * A MEASURED ORDERING WORTH KNOWING, and pinned below rather than left to be
 * rediscovered: the attributability gate runs BEFORE the `target_digest` comparison, so
 * in a default-configured deployment `409 proposal_stale` is **unreachable through this
 * screen** — an accept on a stale proposal answers `human_actor_required` too. The
 * staleness is still visible to the scientist, because `target_stale` is DERIVED on the
 * list read, which needs no actor. That is what the stale test asserts.
 *
 * ── WHICH RECORDS, AND WHY THESE TWO ────────────────────────────────────────────────
 *
 * `SEED.exported` and `SEED.exportedAlt` — the only two canonical records no other
 * mutation spec touches (`grep -o 'SEED\.[a-zA-Z]*' e2e/mutation/*.spec.ts`). This file
 * moves `system.technique` on one of them, so a record another spec asserted content
 * for would be a cross-file coupling of exactly the kind `workers: 1` cannot save you
 * from.
 *
 * ONE CONSEQUENCE OF THAT CHOICE, STATED RATHER THAN DISCOVERED: an exported record
 * refuses `POST .../runs` (`409 already_exported_without_runs`, measured), so no
 * run-scoped proposal is exercised here. Every target below is the one record-scoped
 * path this build has — `system.technique`, the sole member of
 * `record_scoped_target_field_paths`. Run-scoped acceptance, the `target_run_removed`
 * refusal and the run's own current-value read are NOT covered by this file.
 *
 * SYNTHETIC ONLY. Every note, value and rule sentence below is invented for this file
 * and is about the committed synthetic XANES seed.
 */

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import type { APIRequestContext, Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { mutationSessionId } from './fixtures';
import { MUT_API_BASE, MUT_WORKSPACE, SEED } from './env';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';

// ---------------------------------------------------------------------------
// Reaching the server directly — SETUP and INDEPENDENT VERIFICATION only.
// ---------------------------------------------------------------------------

const scoped = (): Record<string, string> => ({
  [TUTORIAL_SESSION_HEADER]: mutationSessionId(),
});

interface ServerProposal {
  proposal_id: string;
  note_id: string;
  run_id: string | null;
  target_field_path: string;
  proposed_value: unknown;
  rule: string;
  source: string;
  proposed_utc: string;
  state: string;
  target_digest: string;
  current_target_digest: string | null;
  target_stale: boolean | null;
  excerpt: string | null;
  start_char: number | null;
  end_char: number | null;
  is_field_value: false;
  history: {
    action: string;
    reason: string | null;
    from_state: string | null;
    to_state: string | null;
    actor_subject: string | null;
  }[];
}

interface ServerProposalList {
  proposals: ServerProposal[];
  total: number;
  returned: number;
  unreadable_entries: number;
  by_state: Record<string, number>;
  target_field_paths: string[];
  record_scoped_target_field_paths: string[];
}

async function detail(
  api: APIRequestContext,
  id: string
): Promise<{ version: string; rev: number }> {
  const res = await api.get(`${MUT_API_BASE}/experiments/${id}`, { headers: scoped() });
  expect(
    res.ok(),
    `GET /experiments/${id} -> ${res.status()}. A 404 usually means the worked-example ` +
      `session header did not travel; the canonical records exist in no other scope.`
  ).toBeTruthy();
  return (await res.json()) as { version: string; rev: number };
}

/** Capture a note. Every proposal must cite one — `note_id` is required and never invented. */
async function captureNote(api: APIRequestContext, id: string, text: string): Promise<string> {
  const { version } = await detail(api, id);
  const res = await api.post(`${MUT_API_BASE}/experiments/${id}/notes`, {
    headers: {
      ...scoped(),
      'content-type': 'application/json',
      // QUOTED: `version` is the bare `<generation>.<rev>` token and the header wants a
      // strong validator, so an unquoted value is 400 `malformed_if_match`, not 412.
      'If-Match': `"${version}"`,
    },
    data: { text, source: 'typed_note' },
  });
  expect(res.status(), `POST /notes -> ${res.status()} ${await res.text()}`).toBe(201);
  return ((await res.json()) as { note: { id: string } }).note.id;
}

/**
 * Store one proposal, the way a producer would if this build had one.
 *
 * SETUP, NOT THE ACT UNDER TEST. Every REVIEW below goes through a click.
 */
async function proposeBehindTheUi(
  api: APIRequestContext,
  id: string,
  body: {
    note_id: string;
    target_field_path: string;
    proposed_value: unknown;
    rule: string;
    start_char?: number;
    end_char?: number;
  }
): Promise<ServerProposal> {
  const { version } = await detail(api, id);
  const res = await api.post(`${MUT_API_BASE}/experiments/${id}/proposals`, {
    headers: { ...scoped(), 'content-type': 'application/json', 'If-Match': `"${version}"` },
    data: body,
  });
  expect(res.status(), `POST /proposals -> ${res.status()} ${await res.text()}`).toBe(200);
  const created = (await res.json()) as { proposal: ServerProposal; deduplicated: boolean };
  expect(created.deduplicated, 'this setup must MINT a proposal, not reuse one').toBe(false);
  return created.proposal;
}

async function serverList(api: APIRequestContext, id: string): Promise<ServerProposalList> {
  const res = await api.get(`${MUT_API_BASE}/experiments/${id}/proposals?limit=200`, {
    headers: scoped(),
  });
  expect(res.ok(), `GET /proposals -> ${res.status()}`).toBeTruthy();
  return (await res.json()) as ServerProposalList;
}

async function serverProposal(
  api: APIRequestContext,
  id: string,
  proposalId: string
): Promise<ServerProposal> {
  const list = await serverList(api, id);
  const row = list.proposals.find((p) => p.proposal_id === proposalId);
  expect(row, `proposal ${proposalId} is not on record ${id}`).toBeTruthy();
  return row as ServerProposal;
}

/** What the record's own draft holds at a path, read independently of the screen. */
async function draftValue(
  api: APIRequestContext,
  id: string,
  path: string
): Promise<unknown> {
  const res = await api.get(`${MUT_API_BASE}/experiments/${id}/draft`, { headers: scoped() });
  expect(res.ok(), `GET /draft -> ${res.status()}`).toBeTruthy();
  const body = (await res.json()) as {
    groups: { fields: { path: string; value: unknown }[] }[];
  };
  const row = body.groups.flatMap((g) => g.fields).find((f) => f.path === path);
  expect(row, `the draft describes no field at ${path}`).toBeTruthy();
  return (row as { value: unknown }).value;
}

/** Move the record's own value at a path — a SECOND CLIENT, not this screen. */
async function editTargetBehindTheUi(
  api: APIRequestContext,
  id: string,
  path: string,
  value: unknown
): Promise<void> {
  const { version } = await detail(api, id);
  const res = await api.post(`${MUT_API_BASE}/experiments/${id}/edit`, {
    headers: { ...scoped(), 'content-type': 'application/json', 'If-Match': `"${version}"` },
    data: { confirmed_by_user: true, answers: { [path]: value } },
  });
  expect(res.ok(), `POST /edit -> ${res.status()} ${await res.text()}`).toBeTruthy();
  expect(
    await draftValue(api, id, path),
    'the behind-the-UI edit returned 2xx but the draft did not move — a dropped answer ' +
      'would make every staleness assertion below vacuous'
  ).toEqual(value);
}

/**
 * THE CONFIGURATION PREMISE, ASSERTED RATHER THAN ASSUMED.
 *
 * `/api/health` publishes `submission.blockers`, and `no_attributable_actor` is the
 * server saying, in its own words, that this process establishes no human actor. Every
 * acceptance assertion below is a statement about THAT configuration; running this
 * suite against a fixture-verifier backend would make them false without any product
 * defect existing. Failing here, with this message, is the honest outcome.
 */
async function assertNoAttributableActor(api: APIRequestContext): Promise<void> {
  const res = await api.get(`${MUT_API_BASE}/health`);
  expect(res.ok(), `GET /health -> ${res.status()}`).toBeTruthy();
  const health = (await res.json()) as { submission?: { blockers?: string[] } };
  expect(
    health.submission?.blockers ?? [],
    'PREMISE FAILED, and this is not a product defect. These assertions describe a ' +
      'DEFAULT-CONFIGURED deployment, which establishes no attributable human actor. ' +
      'This backend reports that it does establish one — so it was started with ' +
      'ISAAC_EDGE_TRUST_VERIFIER=test_fixture and ISAAC_FIXTURE_ACTOR_SUBJECT set, and ' +
      'acceptance SUCCEEDS here. That is a configuration this suite does not describe; ' +
      'the successful-acceptance leg is measured in apps/api/tests/test_ingestion_proposals.py.'
  ).toContain('no_attributable_actor');
}

// ---------------------------------------------------------------------------
// The screen
// ---------------------------------------------------------------------------

/*
 * `?view=` NAMES THE WORKSPACE, and it is required rather than cosmetic. The Review
 * Record screen is four `?view=` destinations on one route (`RECORD_VIEW_IDS`), each
 * lazily mounted, so a bare `/record/<id>` opens Record Fields and the panel a spec
 * is about may not exist on the page at all. The default is unchanged from what a
 * reader gets by typing the bare URL.
 */
async function openRecord(page: Page, id: string): Promise<void> {
  await page.goto(`/record/${id}?view=capture`);
  await expect(page.getByRole('heading', { name: 'Ingestion Proposals' })).toBeVisible();
  // The panel's own count line, which is only rendered once a window has LOADED.
  // Waiting on it means no assertion below races the first read.
  await expect(page.locator('.proposals-count')).not.toBeEmpty();
}

/**
 * ONE CARD, FOUND BY ITS NOTE ID.
 *
 * NOT by `aria-label`, and the reason is the point: a card's accessible name is the
 * field path plus the state, and every proposal here targets the ONE record-scoped path
 * this build has — so two open proposals have byte-identical names. The note id is
 * minted by the server on this run, is rendered in `.proposal-origin`, and cannot
 * collide with a fixture or with another card.
 */
const cardFor = (page: Page, noteId: string) =>
  page.locator('article.proposal-card').filter({ hasText: noteId });

const REJECT = 'Reject';
const SUPERSEDE = 'Supersede';
const WITHDRAW = 'Withdraw';

/** Open one refusing act's editor, type an optional reason, and confirm it.
 *  Reject stays a top-level peer; Supersede and Withdraw sit behind "More
 *  Actions" (P2 resolution) and that disclosure is opened first for them. */
async function refuseThroughTheUi(
  page: Page,
  noteId: string,
  act: typeof REJECT | typeof SUPERSEDE | typeof WITHDRAW,
  reason?: string
): Promise<void> {
  const card = cardFor(page, noteId);
  if (act !== REJECT) {
    await card.getByRole('button', { name: 'More Actions' }).click();
  }
  await card.getByRole('button', { name: `${act}…`, exact: true }).click();
  const form = card.locator('.proposal-form');
  await expect(form).toBeVisible();
  if (reason !== undefined) {
    await form.getByLabel('Reason (optional)').fill(reason);
  }
  await card.getByRole('button', { name: `Confirm ${act}`, exact: true }).click();
}

// ---------------------------------------------------------------------------
// 1–3 · a stored proposal reaches the screen, and is distinguishable from the record
// ---------------------------------------------------------------------------

const T1_NOTE =
  'Beamline log for this campaign records the technique as XAS, not HERFD-XAS.';
const T1_START = T1_NOTE.indexOf('XAS');
const T1_RULE = 'The beamline log line named a technique and the Technique column was read from it.';

test('a stored proposal reaches the screen, and the panel really read the server', async ({
  page,
  request,
  calls,
}) => {
  const id = SEED.exported;
  const before = await serverList(request, id);
  const noteId = await captureNote(request, id, T1_NOTE);
  const proposal = await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'XAS',
    rule: T1_RULE,
    start_char: T1_START,
    end_char: T1_START + 3,
  });
  const revAfterSetup = (await detail(request, id)).rev;

  await openRecord(page, id);
  const card = cardFor(page, noteId);
  await expect(card).toBeVisible();

  /*
   * NEGATIVE CONTROL — THE PANEL REALLY READ THE SERVER, and it is not "a GET went
   * out". `note_id` and `proposal_id` are ULIDs minted by this run's backend seconds
   * ago; no fixture, no snapshot and no cached window can contain them. Rendering them
   * is only possible from a live response. A panel that fell back to fixture content,
   * or that rendered from the change-feed summary (which carries NO content by
   * construction), fails here.
   */
  await expect(card.locator('.proposal-origin')).toContainText(noteId);
  expect(proposal.proposal_id, 'the server minted a proposal id').toMatch(/^[0-9A-HJKMNP-TV-Z]{26}$/);

  // The state the scientist is being asked to act on.
  await expect(card).toHaveAttribute('data-state', 'open');
  await expect(card).toHaveAttribute(
    'aria-label',
    'Proposal for system.technique — Awaiting your judgement'
  );

  // The count line is the SERVER's arithmetic, not a length of what is on screen.
  const after = await serverList(request, id);
  expect(after.total, 'the record holds exactly one more proposal than before').toBe(
    before.total + 1
  );
  await expect(page.locator('.proposals-count')).toContainText(
    `Showing ${after.returned} of ${after.total} proposal`
  );

  /*
   * NEGATIVE CONTROL — READ-ONLY ON ARRIVAL. Opening a record to look at its review
   * queue must not itself review anything. Zero POSTs to any proposal route, and the
   * record's `rev` is where the setup left it.
   */
  expect(calls.postsTo('/proposals'), 'opening the panel must write nothing').toEqual([]);
  expect(
    (await detail(request, id)).rev,
    'merely opening the panel moved the record'
  ).toBe(revAfterSetup);
});

test('the proposed value and what the record holds are separate, labelled reads', async ({
  page,
  request,
}) => {
  const id = SEED.exported;
  const noteId = await captureNote(
    request,
    id,
    'A second beamline log line for the same campaign, also naming XAS.'
  );
  await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'XAS',
    rule: 'The second beamline log line named the same technique.',
  });

  // Read independently FIRST, so the expectation is the server's and not the screen's.
  const held = await draftValue(request, id, 'system.technique');
  expect(held, 'this test needs the record to hold something OTHER than the proposal').not.toBe(
    'XAS'
  );

  await openRecord(page, id);
  const card = cardFor(page, noteId);

  // The proposed value, labelled as proposed, and never as the record's.
  await expect(card.locator('.proposal-value-label')).toHaveText('Proposed value');
  await expect(card.locator('.proposal-value-body')).toHaveText('XAS');
  await expect(card.locator('.proposal-nature')).toContainText(
    'It is not the field’s value and not evidence for it.'
  );

  /*
   * WHAT THE RECORD HOLDS IS A SEPARATE, EXPLICIT, ON-DEMAND READ — the panel's own
   * design, and the thing it exists to keep apart. Before the button is pressed there
   * is no current value on the card at all.
   */
  await expect(card.locator('.proposal-current-label')).toHaveCount(0);
  await card.getByRole('button', { name: 'Show What the Record Holds Now' }).click();

  await expect(card.locator('.proposal-current-label')).toHaveText(
    "The record's own draft, read just now"
  );
  await expect(card.locator('.proposal-current .proposal-value-body')).toHaveText(String(held));

  /*
   * NEGATIVE CONTROL — THE TWO ARE DIFFERENT TEXT IN DIFFERENT LABELLED REGIONS. A
   * surface that rendered the PROPOSED value under the current-value heading — the
   * defect the panel's own header calls out — passes a "the value is visible" check and
   * fails this one, because the two strings would be equal.
   */
  const proposed = await card.locator('.proposal-value-body').first().innerText();
  const current = await card.locator('.proposal-current .proposal-value-body').innerText();
  expect(current, 'the current value must not be the proposed one').not.toBe(proposed);
  expect(current).toBe(String(held));

  // And nothing here claims a value was written: that block exists only once accepted.
  await expect(card.getByText('Value that was written')).toHaveCount(0);
});

test('source, rule, time and the derived excerpt are shown, and the excerpt is not stored', async ({
  page,
  request,
}) => {
  const id = SEED.exported;
  const text =
    'Sample sheet row 4: the endstation notes say the measurement technique used was XRF for this entry.';
  const start = text.indexOf('XRF');
  const rule = 'The endstation notes named a technique in the row this note was read from.';

  const noteId = await captureNote(request, id, text);
  const proposal = await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'XRF',
    rule,
    start_char: start,
    end_char: start + 3,
  });

  await openRecord(page, id);
  const card = cardFor(page, noteId);

  await expect(card.locator('.proposal-rule')).toContainText(rule);
  await expect(card.locator('.proposal-origin')).toContainText('typed_note');
  await expect(card.locator('.proposal-origin')).toContainText(noteId);
  await expect(card.locator('.proposal-when')).toHaveText(`Proposed ${proposal.proposed_utc}`);
  await expect(card.locator('.proposal-excerpt')).toHaveText('XRF');

  /*
   * NEGATIVE CONTROL FOR DEC-3 ("do not store `quote`"). The excerpt on screen equals
   * the SUBSTRING the offsets name, and the stored row carries offsets and no quote —
   * so what is shown was derived on read. A build that stored the words instead would
   * satisfy the visible assertion and fail both of these.
   */
  expect(proposal.excerpt).toBe(text.slice(start, start + 3));
  expect(proposal.start_char).toBe(start);
  expect(Object.keys(proposal)).not.toContain('quote');

  // The verbatim words stay on the NOTE. The card shows the span, not the note.
  await expect(card).not.toContainText(text);
});

// ---------------------------------------------------------------------------
// 5–6 · the three refusing acts, through the UI
// ---------------------------------------------------------------------------

test('a proposal is rejected through the UI, with a reason, and the server records it', async ({
  page,
  request,
}) => {
  const id = SEED.exported;
  const noteId = await captureNote(request, id, 'A reading that turned out to be the wrong column.');
  const created = await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'XRD',
    rule: 'A column adjacent to Technique was read by mistake.',
  });
  const totalBefore = (await serverList(request, id)).total;
  const rejectedBefore = (await serverList(request, id)).by_state.rejected;

  await openRecord(page, id);
  const card = cardFor(page, noteId);
  await expect(card).toHaveAttribute('data-state', 'open');

  const reason = 'The Technique column was misread; this is the neighbouring column.';
  await refuseThroughTheUi(page, noteId, REJECT, reason);

  // The screen says so.
  await expect(card).toHaveAttribute('data-state', 'rejected');
  await expect(card.locator('.proposal-state')).toHaveText('Rejected — kept on the record');

  /*
   * NEGATIVE CONTROL — THE SERVER REALLY MOVED, and it moved because of the CLICK.
   * A screen that painted the new state locally and never sent the request passes the
   * assertion above and fails all four of these.
   */
  const row = await serverProposal(request, id, created.proposal_id);
  expect(row.state).toBe('rejected');
  expect(row.history.map((h) => h.action)).toEqual(['propose', 'reject']);
  expect(row.history[1].reason, 'the reason the scientist typed reached the record').toBe(reason);
  expect(row.history[1].from_state).toBe('open');

  // REJECTING IS NOT DELETING. The record holds exactly as many proposals as before.
  const after = await serverList(request, id);
  expect(after.total, 'rejecting must not remove anything').toBe(totalBefore);
  expect(after.by_state.rejected).toBe(rejectedBefore + 1);
});

test('a rejection with a blank reason stores no reason at all', async ({ page, request }) => {
  const id = SEED.exported;
  const noteId = await captureNote(request, id, 'A reading nobody wanted to explain.');
  const created = await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'XPS',
    rule: 'A third reading of the same sheet row.',
  });

  await openRecord(page, id);
  // The editor is opened and the reason box is left untouched — which is the case a
  // scientist reaches by pressing Confirm without typing.
  await refuseThroughTheUi(page, noteId, REJECT);

  await expect(cardFor(page, noteId)).toHaveAttribute('data-state', 'rejected');

  /*
   * NEGATIVE CONTROL — ABSENT, NOT EMPTY. The panel's own hint promises "a blank is
   * left absent rather than stored as an empty reason". A client that sent `reason: ""`
   * would either be refused (`invalid_reason`) or store one — and `null` is the only
   * result consistent with the promise.
   */
  const row = await serverProposal(request, id, created.proposal_id);
  expect(row.history.map((h) => h.action)).toEqual(['propose', 'reject']);
  expect(row.history[1].reason, 'a reason nobody wrote must not be composed for them').toBeNull();
});

test('a proposal is superseded and another withdrawn through the UI', async ({
  page,
  request,
}) => {
  const id = SEED.exported;

  const supersededNote = await captureNote(request, id, 'An early reading, later replaced.');
  const superseded = await proposeBehindTheUi(request, id, {
    note_id: supersededNote,
    target_field_path: 'system.technique',
    proposed_value: 'SAXS',
    rule: 'An early pass over the sheet.',
  });
  const withdrawnNote = await captureNote(request, id, 'A reading that should not have been made.');
  const withdrawn = await proposeBehindTheUi(request, id, {
    note_id: withdrawnNote,
    target_field_path: 'system.technique',
    proposed_value: 'WAXS',
    rule: 'A pass over a sheet belonging to another campaign.',
  });
  const totalBefore = (await serverList(request, id)).total;

  await openRecord(page, id);

  await refuseThroughTheUi(page, supersededNote, SUPERSEDE, 'A later reading replaces this one.');
  await expect(cardFor(page, supersededNote)).toHaveAttribute('data-state', 'superseded');

  await refuseThroughTheUi(page, withdrawnNote, WITHDRAW, 'This sheet was not this campaign’s.');
  await expect(cardFor(page, withdrawnNote)).toHaveAttribute('data-state', 'withdrawn');

  const a = await serverProposal(request, id, superseded.proposal_id);
  const b = await serverProposal(request, id, withdrawn.proposal_id);
  expect(a.state).toBe('superseded');
  expect(a.history.map((h) => h.action)).toEqual(['propose', 'supersede']);
  expect(b.state).toBe('withdrawn');
  expect(b.history.map((h) => h.action)).toEqual(['propose', 'withdraw']);

  /*
   * NEGATIVE CONTROL — NEITHER ACT CREATED A REPLACEMENT, and neither removed anything.
   * `supersede` records that a later judgement replaces this one; the panel says
   * "nothing here creates the replacement", and a build that minted one would move the
   * total.
   */
  expect((await serverList(request, id)).total).toBe(totalBefore);
});

// ---------------------------------------------------------------------------
// 7 · pending by inaction
// ---------------------------------------------------------------------------

test('a proposal left alone stays open — there is no defer act, and inaction records nothing', async ({
  page,
  request,
  calls,
}) => {
  const id = SEED.exported;
  const noteId = await captureNote(request, id, 'A reading nobody has judged yet.');
  const created = await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'PDF',
    rule: 'A reading awaiting a scientist.',
  });
  const revBefore = (await detail(request, id)).rev;

  await openRecord(page, id);
  const card = cardFor(page, noteId);

  // The panel says what taking no action means, rather than leaving it to be inferred.
  await expect(card.locator('.proposal-pending-note')).toContainText(
    'Leaving this proposal alone leaves it awaiting judgement.'
  );

  /*
   * NEGATIVE CONTROL 1 — THERE IS NO DEFER CONTROL, anywhere in the panel. The contract
   * rejects the state outright ("do not model `expired`"; there is no `defer`), so a
   * build that grew one would be storing a state the record cannot hold. Asserted over
   * the whole section, not just this card.
   */
  const panel = page.locator('.proposals-section');
  await expect(
    panel.getByRole('button', { name: /defer|decide later|snooze|remind me/i })
  ).toHaveCount(0);

  /*
   * THE FOUR ACTS THAT DO EXIST ARE THE FOUR THE SERVER OFFERED, AND NO FIFTH —
   * split across the top-level row and the "More Actions" disclosure PR-D's P2
   * resolution introduced (Accept + Reject stay top-level peers; Correct-the-Value,
   * Supersede and Withdraw sit one click behind "More Actions").
   */
  await expect(card.locator('.proposal-actions button')).toHaveText([
    'Accept as Proposed',
    'Reject…',
    'More Actions',
  ]);
  await card.getByRole('button', { name: 'More Actions' }).click();
  await expect(card.locator('.proposal-more button')).toHaveText([
    'Correct the Value, Then Accept',
    'Supersede…',
    'Withdraw…',
  ]);

  /*
   * NEGATIVE CONTROL 2 — INACTION IS NOT AN ABSENCE OF ASSERTIONS. The proposal is
   * still `open` with exactly one history entry after the screen has been opened,
   * reloaded and read; the page sent no review request; and the record's `rev` has not
   * moved. A build that recorded a "seen"/"deferred" act on render fails all three.
   */
  await page.reload();
  await expect(cardFor(page, noteId)).toHaveAttribute('data-state', 'open');

  expect(
    calls.posts().filter((u) => u.includes('/review')),
    'reading a queue must not review anything'
  ).toEqual([]);
  const row = await serverProposal(request, id, created.proposal_id);
  expect(row.state).toBe('open');
  expect(row.history).toHaveLength(1);
  expect(row.history[0].action).toBe('propose');
  expect((await detail(request, id)).rev, 'inaction moved the record').toBe(revBefore);
});

// ---------------------------------------------------------------------------
// 9 · a closed proposal stays readable, with its history, and its note is untouched
// ---------------------------------------------------------------------------

test('a rejected proposal stays readable with its history, and the note behind it is untouched', async ({
  page,
  request,
}) => {
  const id = SEED.exported;
  const text = 'The words behind a proposal that is about to be rejected.';
  const noteId = await captureNote(request, id, text);
  const created = await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'TEM',
    rule: 'A reading that will be rejected.',
  });

  // The note EXACTLY as it stands before any judgement.
  const noteBefore = await request.get(`${MUT_API_BASE}/experiments/${id}/notes/${noteId}`, {
    headers: scoped(),
  });
  expect(noteBefore.ok()).toBeTruthy();
  const noteBeforeBody = await noteBefore.json();

  await openRecord(page, id);
  await refuseThroughTheUi(page, noteId, REJECT, 'The instrument named here is not this one.');
  await expect(cardFor(page, noteId)).toHaveAttribute('data-state', 'rejected');

  // STILL THERE after a full reload — not spliced out of a local list.
  await page.reload();
  const card = cardFor(page, noteId);
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute('data-state', 'rejected');
  await expect(card.locator('.proposal-closed-note')).toContainText(
    'Every recorded judgement stays exactly as it was made'
  );

  // The history is READABLE, both acts, in order, with the reason.
  await card.getByRole('button', { name: 'Show history (2 acts)' }).click();
  const acts = card.locator('.proposal-history-list li');
  await expect(acts).toHaveCount(2);
  await expect(acts.nth(0)).toContainText('propose');
  await expect(acts.nth(1)).toContainText('reject');
  await expect(acts.nth(1)).toContainText('The instrument named here is not this one.');
  // No name is substituted for an actor nobody established.
  await expect(acts.nth(1)).toContainText('recorded without an attributed actor');

  /*
   * NEGATIVE CONTROL — I6, "NOTHING CAPTURED IS DISCARDED". The note is byte-identical
   * to what it was before the rejection and is still listed. A build that cleaned up
   * the note behind a refused proposal passes every screen assertion above.
   */
  const noteAfter = await request.get(`${MUT_API_BASE}/experiments/${id}/notes/${noteId}`, {
    headers: scoped(),
  });
  expect(noteAfter.status(), 'the note behind a rejected proposal must still resolve').toBe(200);
  expect(await noteAfter.json()).toEqual(noteBeforeBody);

  // And a second act on it is refused — the recorded judgement is not replaceable.
  const row = await serverProposal(request, id, created.proposal_id);
  expect(row.state).toBe('rejected');
  await expect(card.locator('.proposal-actions')).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// 10 · an unsaved correction survives a change-feed refresh that really happened
// ---------------------------------------------------------------------------

/**
 * HOW LONG EACH CHANGE-FEED REQUEST IS HELD in the test below, and why one is held at
 * all — on the FEED, which is the opposite route from the one this test used to hold.
 * Read the block inside the test before changing this.
 *
 * It must exceed one full record-poll cadence with jitter (8 s ±20% → at most 9.6 s),
 * so that between a feed poll being issued and its response arriving, the RECORD poller
 * is certain to have polled and adopted the new revision. 12 s clears 9.6 s with margin
 * and costs one extra cadence of wall clock.
 */
const FEED_POLL_HOLD_MS = 12_000;

test('an unsaved correction survives a background change-feed refresh', async ({
  page,
  request,
}) => {
  /*
   * THE FEED IS AN 8 s TIMER WITH JITTER (`useRecordSync.POLL_INTERVAL_MS`), so this
   * test waits on a real poll rather than a mocked clock. That is the whole point: the
   * property under test is what the REAL poller does to an open editor.
   *
   * ── THE MEASUREMENT THIS TEST MADE, AND THE FIX IT PRODUCED ──────────────────────
   *
   * KEPT IN FULL, INCLUDING THE WORKAROUND IT ONCE NEEDED, because the numbers are the
   * evidence for a production change and a deleted measurement cannot be re-checked.
   *
   * TWO pollers run on this screen at the same 8 s cadence: `useRecordSync` on the
   * record, and `useChangeFeed` on the record's change feed. THEY USED TO SHARE ONE
   * FLOOR — `summariseChanges(entries, recordRev)` dropped every entry whose
   * `changed_at_rev` was `<= recordRev`, and `recordRev` is `detail.rev`, which
   * `RecordWorkbench`'s `onChange: () => bundle.reloadSilent()` advances the moment the
   * RECORD poller notices a new version.
   *
   * A proposal act moves the record's `rev` (contract DEC-10), so a `proposal` entry
   * and the `experiment` entry beside it always carry the SAME `changed_at_rev`. If the
   * record poller reached that rev first, both entries were filtered,
   * `summariseChanges` returned `null`, `onEntitiesChanged` never fired, and this
   * panel's `activity` prop stayed `null` — permanently, because the floor never went
   * back down.
   *
   * THAT WAS MEASURED, NOT REASONED. Two runs of the same scenario in this suite:
   *
   *   · pollers untouched — the feed DID deliver `{"kind":"proposal", …,
   *     "changed_at_rev":2}` at 9,969 ms, the record poller had already refetched at
   *     7,541 ms, and the panel issued NO further `GET .../proposals` in 47 s. The
   *     count line read "Showing 0 of 0" before and after.
   *   · the record-detail poll held open for 25 s — the feed poll at 8,703 ms produced
   *     a summary and the panel re-read `.../proposals` at 8,739 ms. "Showing 0 of 0"
   *     became "Showing 1 of 1".
   *
   * So the ordering decided whether this panel ever refreshed, and the ordinary
   * ordering was the losing one.
   *
   * ── WHAT CHANGED, AND WHICH POLLER IS SLOWED NOW ────────────────────────────────
   *
   * ~~"So the ordering is what decides, and it is reported as a FINDING rather than
   * fixed here — this is a measurement slice and the fix is a production change."~~ —
   * the production change has since been made, and the sentence is struck rather than
   * deleted so the sequence stays legible.
   *
   * `recordChanges.ChangeFloors` splits the one floor into two, because there are two
   * independent reads on this screen and only one of them is the record's: refetching
   * the record adopts NO proposal state, since the list lives behind its own route and
   * its own component. A `proposal` entry is now measured against where the PROPOSAL
   * read stands, and every other kind still against `recordRev`, which is what keeps a
   * scientist's own save the ordinary filtered case rather than a special one.
   *
   * ── THE HOLD WAS NOT REMOVED. IT WAS INVERTED, AND THAT IS A MEASUREMENT, NOT A
   *    PREFERENCE. ───────────────────────────────────────────────────────────────────
   *
   * The obvious way to show the fix works is to delete the hold and watch the test
   * pass. IT DOES PASS — and it passes on the UNFIXED code too, which makes the
   * deletion worthless as evidence. Measured on this machine, with the production
   * `summariseChanges` reverted to a single floor and no hold at all, FIVE runs of this
   * one test: PASS, FAIL, PASS, FAIL, PASS. It is a coin flip, because with nothing
   * holding either poller the feed sometimes wins, and when it wins even the broken
   * build refreshes. A test that passes on the defect half the time is not a regression
   * test; it is a flake that reads like evidence.
   *
   * So the hold is kept and moved to the OTHER route. It used to delay
   * `GET /api/experiments/{id}` so the FEED would win — the ordering under which even
   * the old code worked, which is why the original measurement needed it to observe any
   * refresh at all. It now delays `GET /api/experiments/{id}/changes` so the RECORD
   * poller wins, which is the ordering that used to drop the proposal FOREVER. The test
   * is therefore deterministic in the direction that fails on the defect: with the
   * single-floor build, the panel issues no further list read and this test fails every
   * time.
   *
   * WHAT THE DELAY IS AND IS NOT, unchanged from the original: it holds a request for
   * `FEED_POLL_HOLD_MS` and then lets the REAL one through. It synthesises no response,
   * injects no failure (an abort would trip `feedDegraded` and change the screen), and
   * mocks nothing — it makes one poller slower than the other, which is an ordering the
   * cadence's own ±20% jitter produces on its own, as the five runs above show.
   */
  test.setTimeout(120_000);

  /*
   * THE RECORD POLLER IS LEFT ALONE AND THE FEED IS SLOWED — the inversion described
   * above. Every change-feed request reaches the server `FEED_POLL_HOLD_MS` late, so
   * by the time a `proposal` entry arrives the record poller has already refetched the
   * bundle and `recordRev` has advanced onto that entry's own `changed_at_rev`. That
   * is exactly the condition under which the single floor dropped it forever.
   */
  await page.route(
    (url) => /\/api\/experiments\/[^/?]+\/changes$/.test(url.pathname),
    async (route) => {
      await new Promise((resolve) => setTimeout(resolve, FEED_POLL_HOLD_MS));
      // Chains to the auto-use `scope` fixture's route, which attaches the
      // worked-example session header. A `fulfill` here would be a synthetic response.
      await route.fallback();
    }
  );

  // Every list read the PAGE makes, so "the panel re-read the server on its own" is a
  // counted request rather than an inference from what appeared.
  const listReads: number[] = [];
  page.on('request', (r) => {
    if (r.method() === 'GET' && /\/proposals(\?|$)/.test(r.url())) listReads.push(Date.now());
  });

  const id = SEED.exported;
  const noteId = await captureNote(request, id, 'A reading a scientist is midway through correcting.');
  await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'STM',
    rule: 'A reading that needs correcting before it could be written.',
  });

  await openRecord(page, id);
  const card = cardFor(page, noteId);

  // Behind "More Actions" now (P2 resolution).
  await card.getByRole('button', { name: 'More Actions' }).click();
  await card.getByRole('button', { name: 'Correct the Value, Then Accept' }).click();
  const editor = card.getByLabel('The corrected value, as JSON');
  await expect(editor).toBeVisible();
  // Prefilled once, from the proposed value, as JSON.
  await expect(editor).toHaveValue('"STM"');

  const typed = '"AFM"';
  await editor.fill(typed);
  const readsBeforeTheSecondClient = listReads.length;

  // A SECOND CLIENT changes this record. This is what puts a `proposal` entry in the
  // feed the open screen is polling.
  const otherNote = await captureNote(request, id, 'A note added by a second client.');
  const other = await proposeBehindTheUi(request, id, {
    note_id: otherNote,
    target_field_path: 'system.technique',
    proposed_value: 'SEM',
    rule: 'A proposal made by somebody else while this editor was open.',
  });

  /*
   * NEGATIVE CONTROL — THE REFRESH REALLY HAPPENED. This repository has shipped a
   * change-feed test that passed with the poller wholly inert (`enabled: false`), so
   * "the text is still here" on its own proves nothing: it is exactly what a dead
   * poller produces. The new card appearing WITHOUT any navigation or manual reload is
   * the poller doing its job, and it is asserted first.
   */
  await expect(cardFor(page, otherNote)).toBeVisible({ timeout: 60_000 });
  expect(other.state).toBe('open');
  expect(
    listReads.length,
    'the new card appeared without the page issuing a list read — that is not a refresh'
  ).toBeGreaterThan(readsBeforeTheSecondClient);

  /*
   * AND THE HALF THE REFRESH MUST NOT DESTROY. `CLAUDE.md` §11 records three banners
   * that promised "your input is kept" beside a refresh that destroyed it; the panel's
   * silent reload exists so this cannot recur.
   */
  await expect(editor, 'the silent refresh destroyed an unsaved correction').toHaveValue(typed);
  await expect(editor).toBeVisible();
});

// ---------------------------------------------------------------------------
// 8 + the acceptance question · staleness is the TARGET's, and acceptance is refused
// ---------------------------------------------------------------------------

const UNCHANGED = 'the value at this field path was unchanged since this proposal was made';
const CHANGED = 'the value at this field path had CHANGED since this proposal was made';

test('an unrelated write does not make a proposal stale; a write to the target does', async ({
  page,
  request,
}) => {
  const id = SEED.exportedAlt;
  const noteId = await captureNote(
    request,
    id,
    'The technique for this campaign is recorded as XES in the endstation log.'
  );
  const created = await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'XES',
    rule: 'The endstation log named the technique.',
  });

  await openRecord(page, id);
  const card = cardFor(page, noteId);
  await expect(card.locator('.proposal-target-state')).toContainText(UNCHANGED);

  /*
   * DEC-1, THE NEGATIVE HALF, AND IT IS THE ONE THAT IS EASY TO GET WRONG. The
   * precondition is a digest over the TARGET's value and evidence — not the record's
   * `rev`, which moves on every unrelated act. Capturing a note is such an act. If
   * staleness were keyed on `rev`, every proposal on an active record would become
   * permanently un-acceptable, and this assertion is what catches that.
   */
  const revBefore = (await detail(request, id)).rev;
  await captureNote(request, id, 'An unrelated observation about the endstation.');
  const revAfterUnrelated = (await detail(request, id)).rev;
  expect(revAfterUnrelated, 'the unrelated act must really have moved the record').toBeGreaterThan(
    revBefore
  );

  await page.reload();
  await expect(cardFor(page, noteId).locator('.proposal-target-state')).toContainText(UNCHANGED);
  const stillFresh = await serverProposal(request, id, created.proposal_id);
  expect(stillFresh.target_stale, 'an unrelated write must not make a proposal stale').toBe(false);
  expect(stillFresh.current_target_digest).toBe(stillFresh.target_digest);

  /*
   * DEC-1, THE POSITIVE HALF. Now move the TARGET itself. Nothing about `rev` is
   * different in kind from the act above — what changed is the content at the path.
   */
  const held = await draftValue(request, id, 'system.technique');
  const moved = held === 'XAS' ? 'RIXS' : 'XAS';
  await editTargetBehindTheUi(request, id, 'system.technique', moved);

  await page.reload();
  const staleCard = cardFor(page, noteId);
  await expect(staleCard.locator('.proposal-target-state')).toContainText(CHANGED);
  await expect(staleCard.locator('.proposal-target-state')).toContainText(
    'accepting is refused while that is so — nothing would be written'
  );

  const staleRow = await serverProposal(request, id, created.proposal_id);
  expect(staleRow.target_stale).toBe(true);
  expect(staleRow.current_target_digest).not.toBe(staleRow.target_digest);
  expect(staleRow.state, 'observing staleness must not change the proposal').toBe('open');
});

test('accepting is refused truthfully, and nothing is written', async ({ page, request }) => {
  /*
   * READ THE FILE HEADER BEFORE CHANGING THIS TEST. It asserts what a
   * DEFAULT-CONFIGURED deployment does, and it says so out loud by checking the
   * server's own `/api/health` first. It does NOT assert that acceptance is
   * unreachable — contract §5 I4 forbids that, and it is reachable under the fixture
   * verifier.
   */
  await assertNoAttributableActor(request);

  const id = SEED.exportedAlt;
  const noteId = await captureNote(
    request,
    id,
    'A reading a scientist will try to accept in a deployment that cannot attribute it.'
  );
  const created = await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'NMR',
    rule: 'A reading offered for acceptance.',
  });

  const heldBefore = await draftValue(request, id, 'system.technique');
  const revBefore = (await detail(request, id)).rev;

  await openRecord(page, id);
  const card = cardFor(page, noteId);

  /*
   * THE ACCEPT CONTROL IS OFFERED. That is deliberate and is not a defect: the panel
   * withholds Accept only for conditions that are PERMANENT for a proposal, and
   * "this deployment establishes no actor" is not observable from the list payload.
   * A build that hid the control would be asserting a limitation it cannot see.
   */
  const accept = card.getByRole('button', { name: 'Accept as Proposed', exact: true });
  await expect(accept).toBeEnabled();

  // Capture the server's own answer, so the assertion below is about what the SERVER
  // said and not about a sentence this client could have invented.
  const answered = page.waitForResponse(
    (r) => r.url().includes(`/proposals/${created.proposal_id}/review`) && r.request().method() === 'POST'
  );
  await accept.click();
  const response = await answered;
  expect(response.status(), 'the review route answered something other than a refusal').toBe(409);
  expect((await response.json()).error).toBe('human_actor_required');

  // THE REFUSAL REACHES THE SCIENTIST, and it says the two things that matter: nothing
  // was written, and retrying will not help.
  const banner = page.locator('.proposals-error[role="alert"]');
  await expect(banner).toBeVisible();
  await expect(banner).toContainText('NOTHING WAS WRITTEN');
  await expect(banner).toContainText('retrying will not change it');
  await expect(banner).toContainText(
    'Rejecting, superseding and withdrawing need no actor and still work.'
  );

  /*
   * NEGATIVE CONTROLS — THE REFUSAL IS TRUE. Four independent reads, because "nothing
   * was written" is a claim about the RECORD and not about the response body. A route
   * that half-applied and then refused would satisfy the banner assertions above.
   */
  expect(await draftValue(request, id, 'system.technique'), 'the field moved').toEqual(heldBefore);
  const row = await serverProposal(request, id, created.proposal_id);
  expect(row.state, 'the proposal moved').toBe('open');
  expect(row.history, 'an act was recorded against a refused acceptance').toHaveLength(1);
  expect((await detail(request, id)).rev, 'the record moved').toBe(revBefore);

  /*
   * AND THE ACT THE REFUSAL POINTED THE SCIENTIST AT ACTUALLY WORKS — which is the
   * half that makes the queue clearable in exactly the deployments where acceptance is
   * refused (DEC-9). Without this, "still work" is an unverified promise in a banner.
   */
  await refuseThroughTheUi(page, noteId, WITHDRAW, 'Nobody here can attribute an acceptance.');
  await expect(cardFor(page, noteId)).toHaveAttribute('data-state', 'withdrawn');
  expect((await serverProposal(request, id, created.proposal_id)).state).toBe('withdrawn');
});

// ---------------------------------------------------------------------------
// 11 · the panel is truthful about stored entries it cannot show
// ---------------------------------------------------------------------------

/**
 * THE ONLY TEST HERE THAT TOUCHES THE WORKSPACE FILE, AND IT HAS TO.
 *
 * `POST .../proposals` refuses every malformed shape by design, so an unreadable stored
 * entry is not constructible through any route — which is precisely why DEC-6 exists
 * (`_hydrate_notes` returns the `(readable, unreadable_raw)` pair "so one malformed row
 * cannot 500 the list screen", the `pending: 7` finding). Writing the row directly is
 * clause (b) of this suite's rule — reaching behind the UI to create a condition a
 * second client, or a legacy document, could produce.
 *
 * It runs LAST and on the record no other spec reads, because the row is meant to
 * survive: "kept unchanged on the record" is one of the things asserted.
 */
const experimentFile = (recordId: string): string =>
  join(MUT_WORKSPACE, '_tutorial', mutationSessionId(), recordId, 'experiment.json');

test('the panel discloses stored entries it cannot show, and still shows the ones it can', async ({
  page,
  request,
}) => {
  const id = SEED.exportedAlt;

  const noteId = await captureNote(request, id, 'A readable reading beside an unreadable row.');
  await proposeBehindTheUi(request, id, {
    note_id: noteId,
    target_field_path: 'system.technique',
    proposed_value: 'FTIR',
    rule: 'A readable proposal.',
  });

  const file = experimentFile(id);
  expect(
    existsSync(file),
    `the experiment document is not at ${file}. This suite's workspace layout is ` +
      `<ISAAC_UI_WORKSPACE>/_tutorial/<session>/<record>/experiment.json; if that has ` +
      `moved, this test needs the new path, not deleting.`
  ).toBe(true);

  const before = await serverList(request, id);
  const document = JSON.parse(readFileSync(file, 'utf8')) as {
    proposals: unknown[];
  };
  const malformed = { proposal_id: 'not-a-proposal-this-build-can-read', shape: 'unknown' };
  document.proposals.push(malformed);
  writeFileSync(file, JSON.stringify(document));

  await openRecord(page, id);

  /*
   * THE DISCLOSURE. One string, used by the count line and by both empty states, so two
   * places on the same screen cannot say different things — and it names BOTH causes
   * rather than asserting the one that is wrong half the time.
   */
  await expect(page.locator('.proposals-count')).toContainText(
    '1 stored entry this version cannot show as a proposal'
  );
  await expect(page.locator('.proposals-count')).toContainText(
    'either unreadable, or repeating an id another proposal already holds'
  );
  await expect(page.locator('.proposals-count')).toContainText('kept unchanged on the record');

  /*
   * NEGATIVE CONTROL 1 — ONE BAD ROW DOES NOT TAKE THE PANEL DOWN. The readable
   * proposals are still listed and the screen did not fall into an error state. This is
   * the `pending: 7` property: a malformed value already PERSISTED is READ, not refused
   * to the reader, who did nothing wrong.
   */
  await expect(cardFor(page, noteId)).toBeVisible();
  await expect(page.locator('.proposals-section .fetch-state.error')).toHaveCount(0);

  /*
   * NEGATIVE CONTROL 2 — THE COUNTS ARE HONEST IN BOTH DIRECTIONS. `total` counts only
   * what this build could turn into a proposal, and the unreadable one is reported
   * SEPARATELY rather than folded into it or dropped silently.
   */
  const after = await serverList(request, id);
  expect(after.unreadable_entries).toBe(before.unreadable_entries + 1);
  // `before` was read AFTER the readable proposal was stored and BEFORE the malformed
  // row was appended, so an honest `total` is unmoved by the append.
  expect(after.total, 'an unreadable row must not be counted as a proposal').toBe(before.total);
  expect(after.proposals.some((p) => p.proposal_id === malformed.proposal_id)).toBe(false);

  /*
   * NEGATIVE CONTROL 3 — "KEPT UNCHANGED ON THE RECORD" IS TRUE. The row is preserved
   * VERBATIM: not coerced, not parsed, not walked, not dropped. Read the file back
   * after the screen has read the record.
   */
  const reread = JSON.parse(readFileSync(file, 'utf8')) as { proposals: unknown[] };
  expect(
    reread.proposals.find(
      (p) => (p as { proposal_id?: string }).proposal_id === malformed.proposal_id
    ),
    'the unreadable row was altered or dropped'
  ).toEqual(malformed);
});

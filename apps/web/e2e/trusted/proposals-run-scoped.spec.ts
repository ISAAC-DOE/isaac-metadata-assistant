/**
 * A RUN-SCOPED INGESTION PROPOSAL, REVIEWED IN A BROWSER, ON A RECORD WITH TWO RUNS.
 *
 * WHAT THIS FILE EXISTS TO OVERTURN. `e2e/mutation/proposals.spec.ts` records:
 * *"an exported record refuses `POST .../runs` (409 `already_exported_without_runs`,
 * measured), so no run-scoped proposal is exercised here. Every target below is the
 * one record-scoped path this build has … Run-scoped acceptance, the
 * `target_run_removed` refusal and the run's own current-value read are NOT covered
 * by this file."*
 *
 * **THAT IS TRUE OF THE TWO RECORDS THAT SPEC CHOSE AND FALSE OF THE PRODUCT.** It
 * uses `SEED.exported` and `SEED.exportedAlt` because they are the only canonical
 * examples no other mutation spec touches — and both are exported, which is what
 * refuses a run. `POST /api/experiments` is the product's own creation path, works
 * in the ordinary scope, and a record made through it takes runs happily. This file
 * makes one through the SCREEN, adds two runs through the SCREEN, and reviews a
 * run-scoped proposal on it.
 *
 * TWO RUNS, NOT ONE, AND THE SECOND ONE IS THE ENTIRE POINT. With one run, "the
 * value was written to the run this proposal names" and "the value was written to
 * the only run there is" are the same observation. The two runs here hold DIFFERENT
 * values at the target and the proposal proposes a THIRD, so a panel reading the
 * wrong run, and a write landing on the wrong run, are both detectable rather than
 * merely unproven.
 *
 * THE TARGET AND ITS VALUES ARE READ OFF THE WIRE, NOT WRITTEN OUT HERE. The
 * run-scoped set is `target_field_paths` minus `record_scoped_target_field_paths`,
 * both served by the list operation; the values are members of the enum the vendored
 * official schema declares, served by `GET /api/schema`. A literal in this file would
 * be a second copy of two documents the server already publishes, free to rot into a
 * spec that passes for the wrong reason.
 *
 * WHY A SEPARATE BACKEND. `accept` needs an attributable human actor and answers
 * `409 human_actor_required` in every default-configured deployment, which is what
 * the mutation suite measures and must keep measuring. The verifier comes from the
 * backend PROCESS's environment, so the two legs cannot share a process. See
 * `playwright.trusted.config.ts` and `e2e/trusted/env.ts`. The mutation suite is
 * untouched.
 *
 * THE ONE RULE, unchanged: the reviewed act happens through the visible UI. Nothing
 * below is accepted or rejected by anything but a click.
 *
 * MEASURED CONTROLS — run by hand, reverted, and recorded here because a browser
 * assertion that has never been observed going red is not evidence that it would.
 * Each was applied to THIS FILE, the suite re-run, and the change reverted:
 *
 *   A. expecting the OTHER run's value in the current-value panel -> FAILED,
 *      `Received string: "in_situ"` — which is the SECOND run's value, so the panel
 *      is genuinely reading the run the proposal names;
 *   B. deleting the `Accept as Proposed` click -> FAILED, the "— Accepted" card never
 *      appeared, so nothing in the setup accepts the proposal on its own;
 *   C. writing the UNTARGETED run out of band after the baseline was captured ->
 *      FAILED with "the run this proposal did not name was modified by accepting
 *      it", so the byte-identity comparison can say no.
 *
 * SYNTHETIC ONLY. Every record here is created by this file, seconds earlier.
 */

import type { APIRequestContext } from '@playwright/test';
import {
  addRunThroughTheUi,
  createExperimentThroughTheUi,
  expect,
  openRecord,
  proposalCard,
  test,
  type ServerApi,
} from './fixtures';
import { FIXTURE_ACTOR_SUBJECT, FIXTURE_TRUST_BASIS, TRUSTED_API_BASE } from './env';

const RULE = 'SYNTHETIC — the second configuration block named a different environment';
const NOTE_TEXT =
  'SYNTHETIC — the second run was not held the way the configuration sheet says';

interface Target {
  path: string;
  runOne: string;
  runTwo: string;
  proposed: string;
}

/**
 * A run-scoped target and three distinct legal values, DERIVED FROM THE SERVER.
 *
 * Two wire reads, no literals:
 *   1. the list operation's `target_field_paths` minus its
 *      `record_scoped_target_field_paths` — the application's own answer to "which
 *      targets are a run's", computed by `routes._proposal_writer_for` and
 *      `_PROPOSAL_WRITER_SCOPE`;
 *   2. `GET /api/schema`, the vendored official schema, for a closed enum at one of
 *      those paths.
 *
 * The enum is what makes three DISTINCT legal values available; a free-string target
 * would give values this file invented, and a numeric one would give values the
 * schema has no opinion about. Requiring three members is the property this suite
 * needs stated as a requirement rather than assumed of a named path.
 */
async function deriveTarget(api: APIRequestContext, server: ServerApi, id: string): Promise<Target> {
  const listed = await server.proposals(id);
  const runScoped = listed.target_field_paths.filter(
    (path) => !listed.record_scoped_target_field_paths.includes(path)
  );
  expect(
    runScoped.length,
    'the server reports no run-scoped proposal target at all; this suite has no subject'
  ).toBeGreaterThan(0);

  const schemaRes = await api.get(`${TRUSTED_API_BASE}/schema`);
  expect(schemaRes.ok(), `GET /schema -> ${schemaRes.status()}`).toBeTruthy();
  const { schema } = (await schemaRes.json()) as { schema: Record<string, unknown> };

  const nodeAt = (path: string): Record<string, unknown> | null => {
    let node: unknown = schema;
    for (const segment of path.split('.')) {
      const properties = (node as { properties?: Record<string, unknown> } | null)?.properties;
      if (!properties || typeof properties !== 'object') return null;
      node = (properties as Record<string, unknown>)[segment];
      if (node === undefined || node === null) return null;
    }
    return node as Record<string, unknown>;
  };

  for (const path of [...runScoped].sort()) {
    const values = nodeAt(path)?.enum;
    if (Array.isArray(values) && values.length >= 3 && values.every((v) => typeof v === 'string')) {
      const [runOne, runTwo, proposed] = values as string[];
      return { path, runOne, runTwo, proposed };
    }
  }
  throw new Error(
    `no run-scoped target is a schema enum of three or more string members. ` +
      `Run-scoped targets served: ${JSON.stringify(runScoped)}`
  );
}

/**
 * Everything these specs share: a record with two runs holding different values, and
 * one open run-scoped proposal on the SECOND run.
 *
 * The second run rather than the first, deliberately: a write that defaulted to
 * `runs[0]` — the exact mutation `test_run_scoped_proposal_lifecycle.py` uses — would
 * be indistinguishable from a correct one if the target were the first.
 */
async function aRecordWithTwoRunsAndAProposal(
  page: import('@playwright/test').Page,
  api: APIRequestContext,
  server: ServerApi,
  title: string
) {
  const id = await createExperimentThroughTheUi(page, title);

  // THROUGH THE SCREEN. This is the step the previous conclusion said was
  // unreachable, so it is deliberately not done over HTTP.
  await addRunThroughTheUi(page, 1);
  await addRunThroughTheUi(page, 2);

  const runs = await server.runs(id);
  expect(runs, 'the two Add Run clicks did not produce two runs').toHaveLength(2);
  const [first, second] = runs;

  const target = await deriveTarget(api, server, id);
  // Different values, so a read or a write of the wrong run is detectable.
  await server.setRunField(id, first.id, target.path, target.runOne);
  await server.setRunField(id, second.id, target.path, target.runTwo);
  expect(
    new Set([target.runOne, target.runTwo, target.proposed]).size,
    'the two runs and the proposal must hold three DISTINCT values'
  ).toBe(3);

  const noteId = await server.captureNote(id, NOTE_TEXT);
  const proposal = await server.propose(id, {
    note_id: noteId,
    run_id: second.id,
    target_field_path: target.path,
    proposed_value: target.proposed,
    rule: RULE,
  });
  expect(proposal.run_id).toBe(second.id);

  return { id, first, second, target, proposal };
}

test.describe('a run-scoped ingestion proposal, reviewed in a browser', () => {
  test('the scientist sees it, and sees which RUN it is about', async ({ page, request, server }) => {
    const { id, second, target } = await aRecordWithTwoRunsAndAProposal(
      page,
      request,
      server,
      'Run-scoped proposal — visibility'
    );

    await openRecord(page, id);
    const card = proposalCard(page, target.path);
    await expect(card).toBeVisible();

    // THE SCOPE LINE. `On run <id>` for a run-scoped proposal, `On the record` for a
    // record-scoped one — the panel's own two-way branch on `proposal.run_id`.
    const scope = card.locator('.proposal-scope');
    await expect(scope).toHaveText(`On run ${second.id}`);
    await expect(scope).not.toHaveText('On the record');

    // ...and the proposed value is the third value, rendered under its own label.
    await expect(card.locator('.proposal-value-label').first()).toHaveText('Proposed value');
    await expect(card.locator('.proposal-value-body').first()).toContainText(target.proposed);
  });

  test('the CURRENT value it shows is the targeted run\'s — not the other run\'s, not the proposal\'s', async ({
    page,
    request,
    server,
  }) => {
    const { id, target } = await aRecordWithTwoRunsAndAProposal(
      page,
      request,
      server,
      'Run-scoped proposal — current value'
    );

    await openRecord(page, id);
    const card = proposalCard(page, target.path);

    // NOTHING IS READ UNTIL A PERSON ASKS. The panel fetches the current value only
    // on this click — one read per card on mount would be N requests for a question
    // nobody asked.
    await card.getByRole('button', { name: 'Show What the Record Holds Now' }).click();

    const label = card.locator('.proposal-current-label');
    await expect(label).toBeVisible();
    const body = card.locator('.proposal-current-body .proposal-value-body');
    await expect(body).toBeVisible();

    // THE CENTRAL ASSERTION OF THIS FILE. Three distinct values are in play; the one
    // rendered must be the SECOND run's.
    await expect(body).toContainText(target.runTwo);
    await expect(body).not.toContainText(target.runOne);
    await expect(body).not.toContainText(target.proposed);

    // And it says WHOSE value it is. A correct value under a label claiming it came
    // from the record would still be a false statement about provenance.
    await expect(label).toHaveText(/run/i);
  });

  test('accepting it through the screen writes ONE run, and the other is byte-identical', async ({
    page,
    request,
    server,
  }) => {
    const { id, first, second, target, proposal } = await aRecordWithTwoRunsAndAProposal(
      page,
      request,
      server,
      'Run-scoped proposal — acceptance'
    );
    const untouchedBefore = await server.runBody(id, first.id);

    await openRecord(page, id);
    const card = proposalCard(page, target.path);
    await card.getByRole('button', { name: 'Accept as Proposed' }).click();

    // The card's own accessible name carries its state, so waiting for the name to
    // change is waiting for the screen to have caught up — not for a fixed delay.
    await expect(
      page.getByRole('article', { name: new RegExp(`^Proposal for ${target.path.replace(/\./g, '\\.')} — Accepted`) })
    ).toBeVisible();

    // INDEPENDENT VERIFICATION, over HTTP, of what the click did.
    const reviewed = (await server.proposals(id)).proposals.find(
      (p) => p.proposal_id === proposal.proposal_id
    );
    expect(reviewed?.state).toBe('accepted');
    expect(reviewed?.applied_run_id).toBe(second.id);
    expect(reviewed?.accepted_value).toBe(target.proposed);

    const targetedAfter = (await server.runBody(id, second.id)) as {
      run: { fields: Record<string, { value: unknown }> };
    };
    expect(targetedAfter.run.fields[target.path]?.value).toBe(target.proposed);

    // THE WHOLE DOCUMENT, not chosen keys. A run's version token is the RUN's
    // `<generation>.<rev>`, so the record's revision moving does not touch it — which
    // is what makes byte-identity the right claim rather than an over-strong one.
    expect(
      await server.runBody(id, first.id),
      'the run this proposal did not name was modified by accepting it'
    ).toEqual(untouchedBefore);
  });

  test('the acceptance is attributed to the subject this deployment vouches for', async ({
    page,
    request,
    server,
  }) => {
    const { id, target, proposal } = await aRecordWithTwoRunsAndAProposal(
      page,
      request,
      server,
      'Run-scoped proposal — attribution'
    );

    await openRecord(page, id);
    await proposalCard(page, target.path)
      .getByRole('button', { name: 'Accept as Proposed' })
      .click();
    await expect(
      page.getByRole('article', { name: new RegExp(`— Accepted`) })
    ).toBeVisible();

    const reviewed = (await server.proposals(id)).proposals.find(
      (p) => p.proposal_id === proposal.proposal_id
    );
    const accept = reviewed?.history.find((entry) => entry.action === 'accept');
    expect(accept, 'the acceptance recorded no `accept` transition').toBeTruthy();
    expect(accept?.actor_subject).toBe(FIXTURE_ACTOR_SUBJECT);
    expect(accept?.actor_trust_basis).toBe(FIXTURE_TRUST_BASIS);

    // The act of PROPOSING stays unattributed: nobody was named when it was made,
    // and creating a proposal requires no actor in any deployment.
    const propose = reviewed?.history.find((entry) => entry.action === 'propose');
    expect(propose?.actor_subject).toBeNull();
  });

  test('rejecting it through the screen leaves BOTH runs exactly as they were', async ({
    page,
    request,
    server,
  }) => {
    const { id, first, second, target, proposal } = await aRecordWithTwoRunsAndAProposal(
      page,
      request,
      server,
      'Run-scoped proposal — rejection'
    );
    const before = {
      first: await server.runBody(id, first.id),
      second: await server.runBody(id, second.id),
    };

    await openRecord(page, id);
    const card = proposalCard(page, target.path);
    await card.getByRole('button', { name: 'Reject…' }).click();
    await card.getByRole('button', { name: 'Confirm Reject' }).click();

    await expect(
      page.getByRole('article', { name: new RegExp(`— Rejected`) })
    ).toBeVisible();

    const reviewed = (await server.proposals(id)).proposals.find(
      (p) => p.proposal_id === proposal.proposal_id
    );
    expect(reviewed?.state).toBe('rejected');
    expect(reviewed?.applied_run_id).toBeNull();

    expect(await server.runBody(id, first.id)).toEqual(before.first);
    expect(await server.runBody(id, second.id)).toEqual(before.second);
  });
});

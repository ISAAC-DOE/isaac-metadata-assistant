/**
 * Fixtures for the trusted-identity suite.
 *
 * THE ONE RULE, inherited from `e2e/mutation/fixtures.ts` and not weakened here:
 * **the reviewed act happens through the visible UI.** The API is used only to (a)
 * establish a starting state, and (b) read server state back as an INDEPENDENT
 * check. It never performs the action under test, and nothing here mocks a mutation
 * — every response asserted below comes from the real FastAPI process.
 *
 * WHAT SETUP IS AND IS NOT DONE OVER HTTP, stated because the split is deliberate:
 *
 *   · the EXPERIMENT and its two RUNS are created THROUGH THE SCREEN, because the
 *     product has surfaces for both and the previous session's conclusion — that a
 *     run-scoped proposal is "structurally untestable" in a browser — rested on
 *     there being no reachable record that takes runs. There is one; this is it.
 *   · the NOTE and the PROPOSAL are created over HTTP, because no surface may make
 *     them: `routes.py` states *"NOTHING WAS REWIRED TO FEED THEM. There is no
 *     automatic producer"*, and `lib/api.ts` deliberately ships no `createProposal`
 *     *"so adding a create button here would be this client manufacturing the queue
 *     it is reviewing"*. A browser cannot create one because no surface may.
 *
 * SYNTHETIC ONLY. Every note, value and rule sentence is invented for this suite and
 * is about a record this suite created seconds earlier.
 */

import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';
import { TRUSTED_API_BASE } from './env';

export { expect };

export interface ServerProposal {
  proposal_id: string;
  note_id: string;
  run_id: string | null;
  target_field_path: string;
  proposed_value: unknown;
  state: string;
  applied_via: string | null;
  applied_run_id: string | null;
  accepted_value: unknown;
  accepted_from: string | null;
  target_stale: boolean | null;
  history: {
    action: string;
    actor_subject: string | null;
    actor_trust_basis: string | null;
    reason: string | null;
  }[];
}

export interface ServerApi {
  /** Every run of a record, in server order. */
  runs(id: string): Promise<{ id: string; label: string; ordinal: number }[]>;
  /** ONE run's WHOLE served document — the basis of the isolation comparison. */
  runBody(id: string, runId: string): Promise<unknown>;
  /** The record's opaque version token, for an out-of-band write. */
  version(id: string): Promise<string>;
  /** Capture a note. Every proposal cites one; `note_id` is never invented. */
  captureNote(id: string, text: string): Promise<string>;
  /** Store one proposal, the way a producer would if this build had one. */
  propose(
    id: string,
    body: {
      note_id: string;
      run_id?: string;
      target_field_path: string;
      proposed_value: unknown;
      rule: string;
    }
  ): Promise<ServerProposal>;
  /** The proposals as the list operation reports them. */
  proposals(id: string): Promise<{
    proposals: ServerProposal[];
    target_field_paths: string[];
    record_scoped_target_field_paths: string[];
  }>;
  /** Set one run-level field out of band, to give the two runs different content. */
  setRunField(id: string, runId: string, path: string, value: unknown): Promise<void>;
}

function makeServer(api: APIRequestContext): ServerApi {
  const json = async (res: { ok: () => boolean; status: () => number; text: () => Promise<string>; json: () => Promise<unknown> }, what: string) => {
    expect(res.ok(), `${what} -> ${res.status()} ${await res.text()}`).toBeTruthy();
    return res.json();
  };

  const version = async (id: string): Promise<string> => {
    const res = await api.get(`${TRUSTED_API_BASE}/experiments/${id}`);
    const body = (await json(res, `GET /experiments/${id}`)) as { version: string };
    return body.version;
  };

  const runEtag = async (id: string, runId: string): Promise<string> => {
    const res = await api.get(`${TRUSTED_API_BASE}/experiments/${id}/runs/${runId}`);
    await json(res, `GET /runs/${runId}`);
    // The RUN's own validator, not the record's — `PATCH .../runs/{id}` takes the
    // run's, and sending the record's is a `412` that reads like a concurrency
    // defect and is not one.
    return res.headers()['etag'];
  };

  return {
    runs: async (id) => {
      const res = await api.get(`${TRUSTED_API_BASE}/experiments/${id}/runs`);
      const body = (await json(res, `GET /runs`)) as {
        runs: { id: string; label: string; ordinal: number }[];
      };
      return body.runs;
    },
    runBody: async (id, runId) => {
      const res = await api.get(`${TRUSTED_API_BASE}/experiments/${id}/runs/${runId}`);
      return json(res, `GET /runs/${runId}`);
    },
    version,
    captureNote: async (id, text) => {
      const res = await api.post(`${TRUSTED_API_BASE}/experiments/${id}/notes`, {
        headers: {
          'content-type': 'application/json',
          // QUOTED: `version` is the bare `<generation>.<rev>` token and the header
          // wants a strong validator, so an unquoted value is 400
          // `malformed_if_match`, not 412.
          'If-Match': `"${await version(id)}"`,
        },
        data: { text, source: 'typed_note' },
      });
      expect(res.status(), `POST /notes -> ${res.status()} ${await res.text()}`).toBe(201);
      return ((await res.json()) as { note: { id: string } }).note.id;
    },
    propose: async (id, body) => {
      const res = await api.post(`${TRUSTED_API_BASE}/experiments/${id}/proposals`, {
        headers: { 'content-type': 'application/json', 'If-Match': `"${await version(id)}"` },
        data: body,
      });
      expect(res.status(), `POST /proposals -> ${res.status()} ${await res.text()}`).toBe(200);
      const created = (await res.json()) as { proposal: ServerProposal; deduplicated: boolean };
      expect(created.deduplicated, 'this setup must MINT a proposal, not reuse one').toBe(false);
      return created.proposal;
    },
    proposals: async (id) => {
      const res = await api.get(`${TRUSTED_API_BASE}/experiments/${id}/proposals`);
      return (await json(res, `GET /proposals`)) as Awaited<ReturnType<ServerApi['proposals']>>;
    },
    setRunField: async (id, runId, path, value) => {
      const before = await api.get(`${TRUSTED_API_BASE}/experiments/${id}/runs/${runId}`);
      const beforeRev = ((await before.json()) as { run: { rev: number } }).run.rev;
      const res = await api.patch(`${TRUSTED_API_BASE}/experiments/${id}/runs/${runId}`, {
        headers: {
          'content-type': 'application/json',
          'If-Match': `"${(await runEtag(id, runId)).replace(/"/g, '')}"`,
        },
        data: { confirmed_by_user: true, fields: { [path]: value } },
      });
      expect(res.ok(), `PATCH /runs/${runId} -> ${res.status()} ${await res.text()}`).toBeTruthy();
      // A 200 IS NOT ENOUGH: the write routes drop values they do not recognise and
      // still answer 200, so a setup built on that would be comparing two reads of
      // an unchanged run.
      const after = await api.get(`${TRUSTED_API_BASE}/experiments/${id}/runs/${runId}`);
      const body = (await after.json()) as { run: { rev: number; fields: Record<string, { value: unknown }> } };
      expect(
        body.run.rev,
        `the out-of-band write returned 200 but did not change run ${runId} — the ` +
          `value was dropped rather than applied`
      ).toBeGreaterThan(beforeRev);
      expect(body.run.fields[path]?.value).toEqual(value);
    },
  };
}

export const test = base.extend<{
  /** Read/mutate server state directly — SETUP and INDEPENDENT VERIFICATION only. */
  server: ServerApi;
}>({
  server: async ({ request }, use) => {
    await use(makeServer(request));
  },
});

/**
 * Create one experiment THROUGH THE SCREEN and return its id.
 *
 * The whole point of this suite's existence rests on this being possible: an
 * exported canonical example refuses `POST .../runs` with `409
 * already_exported_without_runs`, which is why the mutation suite's proposals spec
 * covers no run scope. A record the product created takes runs.
 */
export async function createExperimentThroughTheUi(page: Page, title: string): Promise<string> {
  await page.goto('/experiments');
  await page.getByRole('button', { name: 'Create Experiment' }).first().click();
  await page.getByLabel('Experiment title').fill(title);
  await page.getByRole('button', { name: 'Create Experiment', exact: true }).last().click();
  await page.waitForURL(/\/record\/[0-9A-Z]{26}/);
  const id = new URL(page.url()).pathname.split('/')[2];
  expect(id, `the URL after creating did not carry a record id: ${page.url()}`).toMatch(
    /^[0-9A-Z]{26}$/
  );
  return id;
}

/** Add one run THROUGH THE SCREEN, and wait for the count to actually grow. */
export async function addRunThroughTheUi(page: Page, expectedTotal: number): Promise<void> {
  await page.getByRole('button', { name: 'Add Run' }).click();
  await expect(page.locator('.run-card')).toHaveCount(expectedTotal);
}

/** Navigate to the Review Record screen and wait for the proposals panel. */
export async function openRecord(page: Page, id: string): Promise<void> {
  await page.goto(`/record/${id}`);
  await expect(page.getByRole('heading', { name: 'Ingestion Proposals' })).toBeVisible();
}

/** The one proposal card on the screen, addressed by its own accessible name. */
export function proposalCard(page: Page, path: string) {
  return page.getByRole('article', { name: new RegExp(`^Proposal for ${path.replace(/\./g, '\\.')} — `) });
}

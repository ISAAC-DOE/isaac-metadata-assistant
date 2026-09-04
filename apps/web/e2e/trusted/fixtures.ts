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
  /*
   * ADDED 2026-09-02 for `two-actor-workflow.spec.ts`. Every one of these is on the
   * wire already — measured by listing the served keys of a real proposal:
   * `client_request_key`, `target_digest` and `current_target_digest` are all in the
   * serializer's output. They are declared here rather than cast at the use site so a
   * server that stopped sending one is a compile error in the spec that reads it.
   */
  client_request_key: string | null;
  target_digest: string;
  current_target_digest: string | null;
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
      /*
       * THE EXACTLY-ONCE KEY, added 2026-09-02. The route takes it and answers
       * `deduplicated: true` with the SAME `proposal_id` when a key it has already
       * seen on this record arrives again — measured, not assumed. An MCP producer
       * retrying a request it never saw the answer to is the case it exists for, and
       * a spec that omits it cannot tell a retry from a second proposal.
       */
      client_request_key?: string;
    }
  ): Promise<ServerProposal>;
  /**
   * `propose`, WITHOUT the "this must MINT a proposal" assertion — for the one call
   * that is deliberately a REPLAY and must be allowed to come back deduplicated.
   */
  proposeRaw(
    id: string,
    body: Record<string, unknown>
  ): Promise<{ proposal: ServerProposal; deduplicated: boolean }>;
  /** Review one proposal over HTTP — used ONLY to measure a refusal, never to act. */
  review(
    id: string,
    proposalId: string,
    body: Record<string, unknown>
  ): Promise<{ status: number; body: Record<string, unknown> }>;
  /** One record-level field, written the way the Record Description panel writes it. */
  setRecordField(id: string, path: string, value: unknown): Promise<void>;
  /** The served draft's value at one record-level field path, or `undefined`. */
  recordFieldValue(id: string, path: string): Promise<unknown>;
  /** `POST .../validate` — the verdict the Workbench's Validate & Review renders. */
  validate(id: string): Promise<{
    ok: boolean;
    errors: { path: string; message: string }[];
    dry_run: boolean;
    official_validator_ran?: boolean;
    runs?: { run_id: string; ok: boolean; errors: { path: string; message: string }[] }[];
  }>;
  /** One page of the change feed. `cursor` omitted means the cursorless resync. */
  changes(
    id: string,
    query?: { cursor?: string; limit?: number }
  ): Promise<{
    changes: { kind: string; entity_id: string; changed_at_rev: number; state?: string }[];
    next_cursor: string;
    has_more: boolean;
    limit: number;
  }>;
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

  /**
   * One record-level field's value, read off the SERVED DRAFT rather than out of any
   * stored document — the same place the Record Description panel reads it from, so a
   * mismatch between what the panel shows and what this asserts is impossible.
   */
  const recordFieldValue = async (id: string, path: string): Promise<unknown> => {
    const res = await api.get(`${TRUSTED_API_BASE}/experiments/${id}/draft`);
    const body = (await json(res, `GET /draft`)) as {
      groups: { fields?: { path: string; value?: unknown }[] }[];
    };
    for (const group of body.groups ?? []) {
      for (const field of group.fields ?? []) {
        if (field.path === path) return field.value;
      }
    }
    return undefined;
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
    proposeRaw: async (id, body) => {
      const res = await api.post(`${TRUSTED_API_BASE}/experiments/${id}/proposals`, {
        headers: { 'content-type': 'application/json', 'If-Match': `"${await version(id)}"` },
        data: body,
      });
      expect(res.status(), `POST /proposals -> ${res.status()} ${await res.text()}`).toBe(200);
      return (await res.json()) as { proposal: ServerProposal; deduplicated: boolean };
    },
    /*
     * DELIBERATELY DOES NOT ASSERT `res.ok()`. Its only caller is measuring a REFUSAL,
     * and a helper that threw on a non-2xx could not be used to observe one — the
     * status is the observation.
     */
    review: async (id, proposalId, body) => {
      const res = await api.post(
        `${TRUSTED_API_BASE}/experiments/${id}/proposals/${proposalId}/review`,
        {
          headers: { 'content-type': 'application/json', 'If-Match': `"${await version(id)}"` },
          data: body,
        }
      );
      let parsed: Record<string, unknown> = {};
      try {
        parsed = (await res.json()) as Record<string, unknown>;
      } catch {
        parsed = {};
      }
      return { status: res.status(), body: parsed };
    },
    setRecordField: async (id, path, value) => {
      /*
       * `POST .../answers` WITH THE BARE DOTTED PATH AS THE KEY, which is exactly what
       * `RecordDescriptionPanel` sends for a path the record does not yet hold
       * (`api.submitAnswer` -> this route; it routes an already-held path to `/edit`
       * instead). Measured over HTTP: `field:system.technique` is refused
       * `422 unrecognized_field` and `system.technique` is accepted 200 — so the
       * `field:` prefix that the RUN override routes take is wrong here, and a fixture
       * using it would report the record-level surface as broken.
       */
      const res = await api.post(`${TRUSTED_API_BASE}/experiments/${id}/answers`, {
        headers: { 'content-type': 'application/json', 'If-Match': `"${await version(id)}"` },
        data: { confirmed_by_user: true, answers: { [path]: value } },
      });
      expect(
        res.ok(),
        `POST /answers ${path} -> ${res.status()} ${await res.text()}`
      ).toBeTruthy();
      // A 200 IS NOT ENOUGH, for the reason `setRunField` states: these routes drop a
      // value they do not recognise and still answer 200.
      expect(
        await recordFieldValue(id, path),
        `the record-level write returned 200 but ${path} did not take the value`
      ).toEqual(value);
    },
    recordFieldValue: (id, path) => recordFieldValue(id, path),
    validate: async (id) => {
      const res = await api.post(`${TRUSTED_API_BASE}/experiments/${id}/validate`, {
        headers: { 'content-type': 'application/json' },
        data: {},
      });
      return json(res, 'POST /validate') as ReturnType<ServerApi['validate']>;
    },
    changes: async (id, query = {}) => {
      const params = new URLSearchParams();
      if (query.cursor !== undefined) params.set('cursor', query.cursor);
      if (query.limit !== undefined) params.set('limit', String(query.limit));
      const qs = params.toString();
      const res = await api.get(
        `${TRUSTED_API_BASE}/experiments/${id}/changes${qs === '' ? '' : `?${qs}`}`
      );
      return json(res, 'GET /changes') as ReturnType<ServerApi['changes']>;
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
  /*
   * ── AND THEN OPEN THE RUNS WORKSPACE, WHICH IS WHY THIS FUNCTION NOW ENDS
   * ── WITH A NAVIGATION. ─────────────────────────────────────────────────────
   *
   * Create lands on the BARE `/record/<id>`, which is Record Fields — and the
   * record screen's four workspaces are lazily mounted `?view=` destinations, so
   * `RunsSection` is not on that page AT ALL. Every caller of this helper adds a
   * run as its next act (`addRunThroughTheUi`), so without this hop the whole
   * trusted suite fails on `Add Run` not existing.
   *
   * IT IS HERE RATHER THAN IN `addRunThroughTheUi` on purpose: that helper is
   * called twice in a row, and a navigation between two Add Run clicks would
   * discard the page between them — turning a two-click sequence into two
   * separate visits and losing exactly the in-page state those specs are about.
   */
  await openWorkspace(page, id, 'runs');
  return id;
}

/**
 * Open one of the record's four workspaces by URL, and wait for it to be there.
 *
 * A FULL NAVIGATION, used only where a spec has no page state to preserve (right
 * after a create, or after a deliberate reload). Where the state matters, use
 * `switchWorkspace` below — it clicks the control a scientist clicks.
 */
export async function openWorkspace(
  page: Page,
  id: string,
  view: 'fields' | 'runs' | 'capture' | 'graph'
): Promise<void> {
  await page.goto(`/record/${id}?view=${view}`);
  await expect(
    page.getByRole('link', { name: WORKSPACE_LABEL[view] }),
    `the ${view} workspace did not open on /record/${id}`
  ).toHaveAttribute('aria-current', 'page');
}

/**
 * Switch workspace THROUGH THE SIDEBAR — the control a scientist uses.
 *
 * Preferred over `openWorkspace` in the middle of a sequence: the switch is an
 * in-app `<Link>`, so the page, its pollers and its record session survive it,
 * which is what lets a spec walk several workspaces inside one visit. It also
 * means the trusted suite exercises the switcher itself rather than only the URL
 * contract behind it.
 */
export async function switchWorkspace(
  page: Page,
  view: 'fields' | 'runs' | 'capture' | 'graph'
): Promise<void> {
  await page.getByRole('link', { name: WORKSPACE_LABEL[view] }).click();
  await expect(
    page.getByRole('link', { name: WORKSPACE_LABEL[view] }),
    `the sidebar did not mark ${view} as the open workspace`
  ).toHaveAttribute('aria-current', 'page');
}

/** The four sidebar labels, verbatim (`lib/labels.ts`). */
const WORKSPACE_LABEL = {
  fields: 'Record Fields',
  runs: 'Runs',
  capture: 'Capture & Proposals',
  graph: 'Graph',
} as const;

/** Add one run THROUGH THE SCREEN, and wait for the count to actually grow.
 *  Requires the RUNS workspace to be open — see `createExperimentThroughTheUi`. */
export async function addRunThroughTheUi(page: Page, expectedTotal: number): Promise<void> {
  await page.getByRole('button', { name: 'Add Run' }).click();
  await expect(page.locator('.run-card')).toHaveCount(expectedTotal);
}

/*
 * `?view=` NAMES THE WORKSPACE, and it is required rather than cosmetic. The Review
 * Record screen is four `?view=` destinations on one route (`RECORD_VIEW_IDS`), each
 * lazily mounted, so a bare `/record/<id>` opens Record Fields and the panel a spec
 * is about may not exist on the page at all. The default is unchanged from what a
 * reader gets by typing the bare URL.
 */
/** Navigate to the Review Record screen's Capture & Proposals workspace and wait
 *  for the proposals panel. */
export async function openRecord(page: Page, id: string, view = 'capture'): Promise<void> {
  await page.goto(`/record/${id}?view=${view}`);
  await expect(page.getByRole('heading', { name: 'Ingestion Proposals' })).toBeVisible();
}

/** The one proposal card on the screen, addressed by its own accessible name. */
export function proposalCard(page: Page, path: string) {
  return page.getByRole('article', { name: new RegExp(`^Proposal for ${path.replace(/\./g, '\\.')} — `) });
}

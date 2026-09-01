/*
 * RECORD DESCRIPTION — the capture surface for what the whole record is.
 *
 * WHAT WAS MISSING, and what these tests would have been red for. A scientist creating
 * a record in-product could not enter a facility, a sample, a contributor or a tag ON
 * THE RECORD. `system.domain` and `system.technique` had a record-level write path that
 * NO screen anywhere reached; the other twelve experiment-level paths had no
 * record-level route at all and were accepted only as a RUN's override, which records
 * a divergence from a value the record does not hold.
 *
 * THE PATH SET IS NOT ASSERTED HERE, deliberately. It is a cross-language contract —
 * this file could only compare the panel against a literal it also owns, which passes
 * against any set at all. `apps/api/tests/test_record_campaign_fields.py` parses
 * `lib/recordFields.ts` and compares it to what the two write operations ACCEPT, which
 * is the only comparison that can catch an unreachable field. What is asserted here is
 * everything that comparison cannot see: which request each change is routed to, what
 * is preserved, what is refused, and what the screen says while it happens.
 *
 * Everything is synthetic: stubbed routes, a fixture record, no network.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RecordDescriptionPanel } from '../components/RecordDescriptionPanel';
import {
  EXP_ID,
  VERSION_FIELDS,
  draftResponse,
  experimentDetail,
  runFixture,
  runsPage,
  stubFetchRoutes,
  type RouteEntry,
} from '../test/apiFixtures';
import officialSchema from '../../../../schema/isaac_record_v1.json';

const BASE = `/api/experiments/${EXP_ID}`;

/**
 * THE VENDORED SCHEMA ITSELF, not a hand-built double.
 *
 * The whole claim of this panel is that its closed lists come from the document
 * `CLAUDE.md` §1 makes the authority. A test double would let the panel and the test
 * agree about 37 techniques that the real schema does not declare — which is exactly
 * the drift the design exists to prevent, reproduced inside the guard against it.
 */
const SCHEMA_ROUTE: Record<string, RouteEntry> = {
  'GET /api/schema': {
    body: {
      schema_title: 'ISAAC record',
      schema_version: '1.05',
      schema: officialSchema,
      vocabularies: {},
    },
  },
};

function routes(extra: Record<string, RouteEntry> = {}): Record<string, RouteEntry> {
  return {
    [`GET ${BASE}`]: { body: { ...experimentDetail, id: EXP_ID } },
    [`GET ${BASE}/draft`]: { body: draftResponse },
    [`GET ${BASE}/runs`]: { body: runsPage([]) },
    ...SCHEMA_ROUTE,
    ...extra,
  };
}

async function open(extra: Record<string, RouteEntry> = {}) {
  const calls = stubFetchRoutes(routes(extra));
  render(<RecordDescriptionPanel experimentId={EXP_ID} />);
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /Record Description/ }));
  });
  await screen.findByRole('button', { name: /Save record description/ });
  return calls;
}

/** The body of the one POST to `suffix`, parsed. Throws rather than returning nothing. */
function postBody(suffix: 'answers' | 'edit'): Record<string, unknown> {
  const stub = globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } };
  const call = stub.mock.calls.find(
    ([url, init]) => init?.method === 'POST' && String(url).endsWith(`/${suffix}`),
  );
  if (!call) throw new Error(`no POST to /${suffix} was made`);
  return JSON.parse(String(call[1].body)).answers as Record<string, unknown>;
}

function ifMatchOf(suffix: 'answers' | 'edit'): string | undefined {
  const stub = globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } };
  const call = stub.mock.calls.find(
    ([url, init]) => init?.method === 'POST' && String(url).endsWith(`/${suffix}`),
  );
  return (call?.[1].headers as Record<string, string> | undefined)?.['If-Match'];
}

const ACCEPTED = {
  body: {
    ...VERSION_FIELDS,
    version: '1.1',
    pending: [],
    pending_page: { total: 0, returned: 0, offset: 0, limit: 50, withheld: 0, complete: true, run_id: null, record_total: 0 },
    status: 'in_review',
    workflow: experimentDetail.workflow,
    invalidation: { changed: true, rev: 4, changed_fields: [], reopened_steps: [], artifact: { state: 'none', reason: null }, reason: null },
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the record description panel', () => {
  it('is collapsed on arrival and fetches nothing until it is opened', async () => {
    const calls = stubFetchRoutes(routes());
    render(<RecordDescriptionPanel experimentId={EXP_ID} />);
    // THE COST OF THIS SECTION ON A RECORD NOBODY OPENS IS ONE LINE AND ZERO REQUESTS.
    expect(calls).toEqual([]);
    expect(screen.queryByRole('button', { name: /Save record description/ })).toBeNull();
  });

  it('offers the technique picker over the schema\'s own values, read from the API', async () => {
    await open();
    const technique = screen.getByLabelText('Technique') as HTMLSelectElement;
    const offered = [...technique.options].map((o) => o.value).filter((v) => v !== '');
    // THE SCHEMA'S OWN LIST, compared against the schema rather than against a literal:
    // a transcription in either the panel or this test would be a second copy free to
    // drift from the document.
    const declared = officialSchema.properties.system.properties.technique.enum;
    expect(offered).toEqual(declared);
    expect(offered.length).toBeGreaterThan(30);
    // NO DEFAULT IS SELECTED beyond what the record already holds.
    expect(technique.value).toBe('HERFD-XAS');
  });

  it('says the pickers are unavailable when the schema cannot be read, and offers no free text', async () => {
    // THE SCHEMA ROUTE IS ABSENT, so `GET /api/schema` rejects — the panel must not
    // degrade a closed list to a text box, because a value outside the list produces a
    // record that cannot export.
    const calls = stubFetchRoutes({
      [`GET ${BASE}`]: { body: { ...experimentDetail, id: EXP_ID } },
      [`GET ${BASE}/draft`]: { body: draftResponse },
      [`GET ${BASE}/runs`]: { body: runsPage([]) },
    });
    render(<RecordDescriptionPanel experimentId={EXP_ID} />);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Record Description/ }));
    });
    await screen.findByRole('button', { name: /Save record description/ });
    expect(calls).toContain('GET /api/schema');
    expect(
      screen.getAllByText(/the official schema could not be read/i).length,
    ).toBeGreaterThan(0);
    // The contributor editor is read-only for the same reason: no role vocabulary.
    expect(screen.getByText(/roles it allows are unknown/i)).toBeInTheDocument();
  });

  it('routes a NEW value to /answers and a CHANGED one to /edit, in one save', async () => {
    await open({ [`POST ${BASE}/answers`]: ACCEPTED, [`POST ${BASE}/edit`]: ACCEPTED });

    // `system.facility.beamline` is not in the draft fixture: the record holds nothing
    // there, so it is an ANSWER. `sample.material.formula` is, so it is a CORRECTION.
    fireEvent.change(screen.getByLabelText('Beamline'), { target: { value: 'BL-9-3' } });
    fireEvent.change(screen.getByLabelText('Formula'), { target: { value: 'Cu2O' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Save record description/ }));
    });

    expect(postBody('answers')).toEqual({ 'system.facility.beamline': 'BL-9-3' });
    expect(postBody('edit')).toEqual({ 'sample.material.formula': 'Cu2O' });
    // THE RECORD'S OWN VALIDATOR, and the second request carries the token the FIRST
    // one returned — not the one the panel loaded with, which the first write moved.
    expect(ifMatchOf('answers')).toBe(`"${VERSION_FIELDS.version}"`);
    expect(ifMatchOf('edit')).toBe('"1.1"');
    await screen.findByText(/Saved 2 values to this record\./);
  });

  it('sends nothing for a box the reader emptied, and says a blank is not a delete', async () => {
    await open({ [`POST ${BASE}/answers`]: ACCEPTED, [`POST ${BASE}/edit`]: ACCEPTED });
    expect(screen.getByText(/Emptying a box does not remove a stored value/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Formula'), { target: { value: '   ' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Save record description/ }));
    });
    const stub = globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } };
    expect(stub.mock.calls.filter(([, init]) => init?.method === 'POST')).toEqual([]);
    await screen.findByText(/Nothing has changed, so nothing was sent\./);
  });

  it('shows a 412 as a conflict, keeps what was typed, and does not retry', async () => {
    await open({
      [`POST ${BASE}/edit`]: {
        status: 412,
        body: { error: 'stale_write', current_version: '9.9' },
      },
    });
    fireEvent.change(screen.getByLabelText('Formula'), { target: { value: 'Cu2O' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Save record description/ }));
    });

    await screen.findByText(/This record changed somewhere else while you were editing/);
    // WHAT WAS TYPED IS STILL THERE, and Save is disabled until a re-read — nothing is
    // overwritten and no retry is made behind the reader's back.
    expect((screen.getByLabelText('Formula') as HTMLInputElement).value).toBe('Cu2O');
    expect(screen.getByRole('button', { name: /Save record description/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Re-read this record/ })).toBeInTheDocument();
    const stub = globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } };
    expect(stub.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  });

  it('renders the server\'s own refusal per field, with the values the schema allows', async () => {
    await open({
      [`POST ${BASE}/edit`]: {
        status: 422,
        body: {
          error: 'not_an_allowed_value',
          experiment_id: EXP_ID,
          key: 'system.technique',
          keys: ['system.technique'],
          allowed: { 'system.technique': ['XAS', 'XES'] },
          message: 'server message',
        },
      },
    });
    fireEvent.change(screen.getByLabelText('Technique'), { target: { value: 'XES' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Save record description/ }));
    });
    const summary = await screen.findByRole('alert');
    expect(within(summary).getByText(/Technique/)).toBeInTheDocument();
    expect(within(summary).getByText(/XAS, XES/)).toBeInTheDocument();
  });

  it('preserves a contributor\'s other properties when the list is edited', async () => {
    const withExtras = {
      ...draftResponse,
      record_blocks: {
        ...draftResponse.record_blocks,
        'block:attribution': {
          contributors: [
            {
              name: 'Synthetic Operator',
              role: 'performed_measurement',
              orcid: '0000-0002-1825-0097',
              affiliation: 'Synthetic Institute',
            },
          ],
        },
      },
    };
    await open({
      [`GET ${BASE}/draft`]: { body: withExtras },
      [`POST ${BASE}/edit`]: ACCEPTED,
    });

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Renamed Operator' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Save record description/ }));
    });

    // A BLOCK WRITE REPLACES THE WHOLE BLOCK, so rebuilding `{name, role}` from scratch
    // would DELETE the orcid and the affiliation. The row keeps the object it came from.
    expect(postBody('edit')).toEqual({
      'block:attribution': {
        contributors: [
          {
            name: 'Renamed Operator',
            role: 'performed_measurement',
            orcid: '0000-0002-1825-0097',
            affiliation: 'Synthetic Institute',
          },
        ],
      },
    });
  });

  it('refuses to send a contributor missing a name or a role, and says why', async () => {
    await open({ [`POST ${BASE}/answers`]: ACCEPTED, [`POST ${BASE}/edit`]: ACCEPTED });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Add a contributor/ }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Save record description/ }));
    });
    expect(
      await screen.findByText(/Every contributor needs both a name and a role/),
    ).toBeInTheDocument();
    const stub = globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } };
    expect(stub.mock.calls.filter(([, init]) => init?.method === 'POST')).toEqual([]);
  });

  it('makes the contributor list READ-ONLY when the record stores an entry it cannot present', async () => {
    const unreadable = {
      ...draftResponse,
      record_blocks: {
        ...draftResponse.record_blocks,
        'block:attribution': { contributors: ['not an object'] },
      },
    };
    await open({ [`GET ${BASE}/draft`]: { body: unreadable } });
    // NEVER SILENTLY SHRUNK. Replacing the block would delete the entry this screen
    // cannot show, so it is disclosed and the editor is disabled instead.
    expect(
      screen.getByText(/stores 1 contributor entry this screen cannot present/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add a contributor/ })).toBeDisabled();
  });

  it('reports which runs have overridden a record-level value, with the bound stated', async () => {
    const overriding = runFixture({
      inherited: {
        'field:sample.material.formula': {
          state: 'overridden',
          payload: { value: 'Cu2O', status: 'verified', evidence: [] },
          inherited_payload: { value: 'CuO2', status: 'verified', evidence: [] },
          overridable: true,
        },
      },
    });
    await open({
      [`GET ${BASE}/runs`]: { body: runsPage([overriding], { total: 40, matched: 30 }) },
    });
    // THE SERVER'S OWN COUNT, and the page's own bound — never "no run overrides this",
    // which a bounded page cannot establish.
    expect(
      screen.getByText(/30 of 40 runs have recorded their own value/),
    ).toBeInTheDocument();
    expect(screen.getByText(/examined 1 of them/)).toBeInTheDocument();
    expect(screen.getByText(/1 or more runs override this/)).toBeInTheDocument();
  });

  it('says the runs could not be read rather than claiming no run has diverged', async () => {
    await open({ [`GET ${BASE}/runs`]: { status: 503, body: { error: 'unavailable' } } });
    expect(
      screen.getByText(/runs could not be read, so this screen cannot say/),
    ).toBeInTheDocument();
  });

  it('runs on the SERVED inventory — the shared fixture carries the `capture` the API always sends', async () => {
    /*
     * WHY THIS IS ASSERTED AT ALL. `serialize._capture_for` returns a dict on every
     * call, and both `_draft_field` and `_skeleton_field` route through it, so there is
     * no `GET .../draft` response this build can produce in which a field row lacks
     * `capture`. While the shared fixture omitted it, every test in this file ran on
     * `offeredRecordFields`' whole-draft FALLBACK — a branch the server cannot reach —
     * and the proof was mechanical: with the panel's derivation reverted to a hardcoded
     * list, all thirteen tests here still passed.
     *
     * This pins the fixture back onto the served branch. It is the counterpart of
     * `record-writable-inventory.test.tsx`'s deliberate `omitCapture` test, which keeps
     * the fallback covered ON PURPOSE rather than by accident.
     */
    for (const group of draftResponse.groups) {
      for (const field of group.fields) {
        expect(field, `${field.path} carries no capture`).toHaveProperty('capture');
      }
    }
    await open();
    // AND THE PANEL IS ON THAT BRANCH: the fallback disclosure is the sentence it prints
    // when the server has not spoken the contract, and it must not be on screen here.
    expect(screen.queryByText(/did not say which fields it accepts a value at/i)).toBeNull();
  });

  it('labels every control and keeps the status region mounted', async () => {
    await open();
    // EVERY OFFERED FIELD HAS A LABEL TIED TO ITS CONTROL. `getByLabelText` throws when
    // it does not, so this is the assertion rather than a count.
    for (const label of [
      'Domain',
      'Technique',
      'Site',
      'Facility name',
      'Organization',
      'Beamline',
      'Endstation',
      'Material name',
      'Formula',
      'Provenance',
      'Sample form',
      'CuO₂ mass fraction',
      'Sucrose mass fraction',
      'Pellet diameter (mm)',
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    // ALWAYS MOUNTED, empty when there is nothing to say — a live region inserted with
    // its content is announced unreliably.
    await waitFor(() => expect(document.querySelector('[role="status"]')).not.toBeNull());
  });
});

/*
 * A PROPOSAL CARD MUST NOT CONTRADICT ITSELF, AND A LOCKED ONE MUST SAY WHAT A
 * SCIENTIST CAN STILL DO — QA findings A-13/C-18, A-09, A-10, A-29 (2026-10-12),
 * each measured in Chromium before it was fixed.
 *
 *   A-13/C-18  An ACCEPTED card said "accepting is refused … nothing would be
 *              written" directly above "Accepted … the value was written". After an
 *              acceptance the target's digest is the ACCEPTED value's, so
 *              `target_stale` is `true` on every accepted card — and the stale
 *              sentence, written for an open card, rendered on it. The same
 *              sentence appeared on rejected cards.
 *   A-09       In the default deployment Accept is locked, and the "Why?" names an
 *              operator fix — nothing the scientist can do. A locked open card now
 *              says the value can be entered directly in the field it targets, and
 *              links there. NOTHING is prefilled or copied, and the proposal is not
 *              marked accepted: that would be an acceptance without the attributable
 *              actor contract §5 I4 requires.
 *   A-10       "in situ" (as written) is not the enum member `in_situ`. Accepting it
 *              as proposed stored an off-enum value. The card now withholds "Accept
 *              as Proposed" for a value outside the field's closed list and steers
 *              to "Correct the Value, Then Accept", which offers the list as a
 *              choice and chooses NOTHING for the reader.
 *   A-29       "Correct the Value" demanded JSON with quotes for a plain text value.
 */
import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { IngestionProposalsPanel } from '../components/IngestionProposalsPanel';
import {
  PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
  PROPOSAL_TARGET_PATHS,
  runFixture,
  runsPage,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { ApiProposal, ApiProposalsResponse } from '../lib/types';

const EXP = 'demo';
const LIST = `GET /api/experiments/${EXP}/proposals`;
const REVIEW = `POST /api/experiments/${EXP}/proposals/P1/review`;
const RUN = '01RUNAAAAAAAAAAAAAAAAAAAA0';

afterEach(() => {
  vi.unstubAllGlobals();
});

function proposal(over: Partial<ApiProposal> = {}): ApiProposal {
  return {
    proposal_id: 'P1',
    experiment_id: EXP,
    note_id: 'N1',
    run_id: RUN,
    target_field_path: 'context.thermodynamics.atmosphere',
    proposed_value: 'helium',
    rule: 'the phrase after "atmosphere", as written',
    source: 'transcript',
    proposed_utc: '2026-09-01T10:00:00Z',
    base_rev: 3,
    target_digest: 'd0',
    start_char: null,
    end_char: null,
    client_request_key: null,
    state: 'open',
    subject: null,
    trust_basis: 'unattributed',
    accepted_value: null,
    accepted_from: null,
    applied_via: null,
    applied_run_id: null,
    applied_rev: null,
    applied_target_digest: null,
    history: [],
    status: 'ingestion_proposal',
    verified: false,
    is_evidence: false,
    is_field_value: false,
    applied: false,
    current_target_digest: 'd0',
    target_stale: false,
    still_current: null,
    excerpt: null,
    attributed: false,
    accepted_by: null,
    ...over,
  };
}

function page(proposals: ApiProposal[]): ApiProposalsResponse {
  const count = (state: string) => proposals.filter((p) => p.state === state).length;
  return {
    proposals,
    total: proposals.length,
    returned: proposals.length,
    by_state: {
      open: count('open'),
      accepted: count('accepted'),
      rejected: count('rejected'),
      superseded: count('superseded'),
      withdrawn: count('withdrawn'),
    },
    has_more: false,
    next_cursor: null,
    order: 'oldest_first',
    window_default: 50,
    window_max: 200,
    max_per_record: 1000,
    unreadable_entries: 0,
    target_field_paths: PROPOSAL_TARGET_PATHS,
    record_scoped_target_field_paths: PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
    states: ['open', 'accepted', 'rejected', 'superseded', 'withdrawn'],
    review_actions: ['accept', 'reject', 'supersede', 'withdraw'],
    accepted_from_values: ['candidate', 'edited'],
    experiment_version: '1.7',
  };
}

function renderPanel(acceptance?: { available: boolean; reason: string | null }) {
  return render(
    <MemoryRouter
      initialEntries={['/']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <IngestionProposalsPanel experimentId={EXP} activity={null} acceptance={acceptance} />
    </MemoryRouter>,
  );
}

function posts(): Record<string, unknown>[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls
    .filter(([, init]) => init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>);
}

const LOCKED = { available: false, reason: 'no_verifier_configured' };
const STALE_SENTENCE = /accepting is refused while that is so/;

// --- A-13 / C-18 ---------------------------------------------------------------

describe('a decided card never carries the open-card acceptance sentence (A-13/C-18)', () => {
  it('an ACCEPTED card whose target now holds the accepted value says nothing about refusal', async () => {
    /* MUTATION: rendering `TargetState` for every state (the base behaviour) puts
       "accepting is refused while that is so — nothing would be written" on this
       card, beside the acceptance record that says the value WAS written. */
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposal({
            state: 'accepted',
            applied: true,
            accepted_from: 'candidate',
            accepted_value: 'helium',
            applied_via: 'run_field',
            applied_run_id: RUN,
            target_stale: true,
            still_current: true,
          }),
        ]),
      },
    });
    renderPanel();
    await screen.findByText(/still held what this acceptance wrote/);
    expect(screen.queryByText(STALE_SENTENCE)).toBeNull();
    expect(screen.queryByText(/nothing would be written/)).toBeNull();
  });

  it('REVIEW minor: the acceptance time reads as a date, the exact instant on <time>', async () => {
    const at = '2026-09-01T10:00:00Z';
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposal({
            state: 'accepted',
            applied: true,
            accepted_from: 'candidate',
            target_stale: true,
            still_current: true,
            accepted_by: { subject: 'synthetic.reviewer', trust_basis: 'test_fixture', attributed: true, at },
          }),
        ]),
      },
    });
    renderPanel();
    const line = await screen.findByText(/Accepted by synthetic\.reviewer/);
    expect(line.textContent).not.toContain(at);
    const when = line.querySelector('time');
    expect(when?.getAttribute('dateTime')).toBe(at);
    expect(when?.getAttribute('title')).toBe(at);
  });

  it('a REJECTED card carries no acceptance sentence either', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposal({ state: 'rejected', target_stale: true })]) },
    });
    renderPanel();
    await screen.findByText('helium');
    expect(screen.queryByText(STALE_SENTENCE)).toBeNull();
  });

  it('an OPEN card whose target moved still says so — the warning is not deleted', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposal({ target_stale: true })]) } });
    renderPanel();
    await screen.findByText(STALE_SENTENCE);
  });
});

// --- A-09 -------------------------------------------------------------------------

describe('a locked open card names what the scientist CAN do (A-09)', () => {
  it('says the value can be entered directly, and links to that run field', async () => {
    stubFetchRoutes({ [LIST]: { body: page([proposal()]) } });
    renderPanel(LOCKED);
    const accept = await screen.findByRole('button', { name: 'Accept as Proposed' });
    expect((accept as HTMLButtonElement).disabled).toBe(true);
    await screen.findByText(/enter it yourself in the field it targets/);
    const link = screen.getByRole('link', { name: /Go to Field/ });
    const href = decodeURIComponent(link.getAttribute('href') ?? '');
    expect(href).toContain(`/record/${EXP}?view=runs&run=${RUN}`);
    expect(href).toContain('at=field:context.thermodynamics.atmosphere');
    // Navigation only: following it sends nothing and changes no proposal.
    expect(posts()).toHaveLength(0);
    // And it never carries the proposed value anywhere — no prefill, no copy.
    expect(href).not.toContain('helium');
  });

  it('a record-scoped proposal links to the record field it targets', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposal({ run_id: null, target_field_path: 'system.technique', proposed_value: 'XAS' }),
        ]),
      },
    });
    renderPanel(LOCKED);
    const link = await screen.findByRole('link', { name: /Go to Field/ });
    // The FIELD, not its section (review minor): the Record Fields view opens the
    // section and focuses that field's own control.
    expect(decodeURIComponent(link.getAttribute('href') ?? '')).toBe(
      `/record/${EXP}?view=fields&at=field:system.technique`,
    );
  });

  it('REVIEW I-4: a record-level path on a run with NO row there gets no false promise', async () => {
    /* The run's inherited-values panel renders a row — and its Override control — only
       for an address the record holds a value at (`runOverrides.overrideRows`). On a
       record holding nothing at `pellet_diameter_mm` the link landed on 0 targets and
       0 override controls while the card said "you can enter it yourself". */
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposal({ target_field_path: 'sample.geometry.pellet_diameter_mm', proposed_value: 13 }),
        ]),
      },
      [`GET /api/experiments/${EXP}/runs`]: {
        body: runsPage([runFixture({ id: RUN, inherited: {} })]),
      },
    } as never);
    renderPanel(LOCKED);
    await screen.findByRole('button', { name: 'Accept as Proposed' });
    // Give the runs read its chance to land, then assert the sentence never appeared.
    await waitFor(() =>
      expect((globalThis.fetch as Mock).mock.calls.some(([u]) => String(u).includes('/runs'))).toBe(
        true,
      ),
    );
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByText(/enter it yourself in the field it targets/)).toBeNull();
    expect(screen.queryByRole('link', { name: /Go to Field/ })).toBeNull();
  });

  it('REVIEW I-4: …and WHEN the run shows an overridable row there, the link is offered', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposal({ target_field_path: 'sample.material.name', proposed_value: 'CuO (fake)' }),
        ]),
      },
      // `runFixture` carries an overridable inherited row at `sample.material.name`.
      [`GET /api/experiments/${EXP}/runs`]: { body: runsPage([runFixture({ id: RUN })]) },
    } as never);
    renderPanel(LOCKED);
    const link = await screen.findByRole('link', { name: /Go to Field/ });
    expect(decodeURIComponent(link.getAttribute('href') ?? '')).toContain(
      'at=field:sample.material.name',
    );
  });

  it('NOT shown where acceptance is available, nor on a decided card', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposal(), proposal({ proposal_id: 'P2', state: 'rejected' })]) },
    });
    renderPanel({ available: true, reason: null });
    await screen.findByRole('button', { name: 'Accept as Proposed' });
    expect(screen.queryByText(/enter it yourself in the field it targets/)).toBeNull();
    expect(screen.queryByRole('link', { name: /Go to Field/ })).toBeNull();
  });
});

// --- A-10 -------------------------------------------------------------------------

describe('a value outside the field’s closed list is never accepted as proposed (A-10)', () => {
  const offEnum = proposal({ target_field_path: 'context.environment', proposed_value: 'in situ' });

  it('withholds "Accept as Proposed", says why, and steers to correcting it', async () => {
    stubFetchRoutes({ [LIST]: { body: page([offEnum]) } });
    renderPanel({ available: true, reason: null });
    await screen.findByText(/is not one of the values the official schema allows/);
    expect(screen.queryByRole('button', { name: 'Accept as Proposed' })).toBeNull();
    // The steer is on the card's top row, not buried behind More Actions.
    expect(screen.getByRole('button', { name: 'Correct the Value, Then Accept' })).toBeTruthy();
  });

  it('offers the schema list as a CHOICE, preselects nothing, and sends the chosen member', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([offEnum]) },
      [REVIEW]: { body: { proposal: proposal({ state: 'accepted' }), experiment_version: '1.8' } },
    });
    renderPanel({ available: true, reason: null });
    fireEvent.click(await screen.findByRole('button', { name: 'Correct the Value, Then Accept' }));
    const select = screen.getByLabelText('The corrected value') as HTMLSelectElement;
    expect(select.tagName).toBe('SELECT');
    // "in situ" is NEVER mapped to `in_situ` on the reader's behalf.
    expect(select.value).toBe('');
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(['', 'operando', 'in_situ', 'ex_situ', 'in_silico']);
    // The option a person reads is words; the value sent is the schema's token.
    expect(screen.getByRole('option', { name: 'In situ' })).toBeTruthy();

    // Nothing chosen yet → nothing sent.
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));
    await screen.findByText(/Choose one of the values/);
    expect(posts()).toHaveLength(0);

    fireEvent.change(select, { target: { value: 'in_situ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0]).toMatchObject({ accepted_from: 'edited', value: 'in_situ' });
  });

  it('a value that IS a member keeps "Accept as Proposed"', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposal({ target_field_path: 'context.environment', proposed_value: 'operando' })]),
      },
    });
    renderPanel({ available: true, reason: null });
    await screen.findByRole('button', { name: 'Accept as Proposed' });
    expect(screen.queryByText(/is not one of the values the official schema allows/)).toBeNull();
  });

  it('REVIEW minor: a RECORD-level closed list is consulted too, before any refusal', async () => {
    /* The off-enum check read only `RUN_FIELDS`, so an off-enum `system.technique`
       card kept "Accept as Proposed" until the server refused — and a default
       deployment, where acceptance is locked, never showed the note at all. The list
       is read from the schema the server serves. */
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposal({ run_id: null, target_field_path: 'system.technique', proposed_value: 'xas' }),
        ]),
      },
      'GET /api/schema': {
        body: {
          schema_version: '1.05',
          schema: {
            properties: {
              system: { properties: { technique: { type: 'string', enum: ['XAS', 'XES'] } } },
            },
          },
        },
      },
    } as never);
    renderPanel(LOCKED);
    await screen.findByText(/is not one of the values the official schema allows/);
    expect(screen.queryByRole('button', { name: 'Accept as Proposed' })).toBeNull();
  });

  it('a server refusal that names the allowed values turns the correction into that choice', async () => {
    /* A record-level closed list (37 techniques) is not transcribed on this side; when
       the server refuses `not_an_allowed_value` it SAYS the list, and the card offers
       exactly that. */
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposal({ run_id: null, target_field_path: 'system.technique', proposed_value: 'xas' }),
        ]),
      },
      [REVIEW]: {
        status: 422,
        body: {
          error: 'not_an_allowed_value',
          message: 'not one of its members',
          key: 'system.technique',
          allowed: ['XAS', 'XES'],
        },
      },
    });
    renderPanel({ available: true, reason: null });
    fireEvent.click(await screen.findByRole('button', { name: 'Accept as Proposed' }));
    await screen.findByText(/The schema allows: XAS, XES/);
    // The card now steers rather than offering the same refused act again.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Accept as Proposed' })).toBeNull(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Correct the Value, Then Accept' }));
    const select = screen.getByLabelText('The corrected value') as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual(['', 'XAS', 'XES']);
  });
});

// --- A-29 -------------------------------------------------------------------------

describe('"Correct the Value" types the value the way the field holds it (A-29)', () => {
  function openCorrection() {
    fireEvent.click(screen.getByRole('button', { name: 'More Actions' }));
    fireEvent.click(screen.getByRole('button', { name: 'Correct the Value, Then Accept' }));
  }

  it('a text field takes plain text — no quotes, no JSON', async () => {
    stubFetchRoutes({
      [LIST]: { body: page([proposal()]) },
      [REVIEW]: { body: { proposal: proposal({ state: 'accepted' }), experiment_version: '1.8' } },
    });
    renderPanel({ available: true, reason: null });
    await screen.findByRole('button', { name: 'Accept as Proposed' });
    openCorrection();
    const box = screen.getByLabelText('The corrected value') as HTMLInputElement;
    expect(box.value).toBe('helium');
    fireEvent.change(box, { target: { value: 'argon' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0]).toMatchObject({ accepted_from: 'edited', value: 'argon' });
  });

  it('a number field sends a number, and says so when the text is not one', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([proposal({ target_field_path: 'context.temperature_K', proposed_value: 300 })]),
      },
      [REVIEW]: { body: { proposal: proposal({ state: 'accepted' }), experiment_version: '1.8' } },
    });
    renderPanel({ available: true, reason: null });
    await screen.findByRole('button', { name: 'Accept as Proposed' });
    openCorrection();
    const box = screen.getByLabelText('The corrected value') as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'warm' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));
    const error = await screen.findByText(/That is not a number/);
    expect(box.getAttribute('aria-invalid')).toBe('true');
    expect(box.getAttribute('aria-describedby') ?? '').toContain(error.id);
    expect(posts()).toHaveLength(0);
    fireEvent.change(box, { target: { value: '310.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0]).toMatchObject({ value: 310.5 });
  });

  it('a STRUCTURED value keeps JSON, and invalid JSON gets a message tied to the box', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: page([
          proposal({ target_field_path: 'sample.material.name', proposed_value: { a: 1 } }),
        ]),
      },
    });
    renderPanel({ available: true, reason: null });
    await screen.findByRole('button', { name: 'Accept as Proposed' });
    openCorrection();
    const box = screen.getByLabelText('The corrected value, as JSON') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: '{a: 1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept the Corrected Value' }));
    const error = await screen.findByText(/That is not valid JSON, so it was not sent/);
    expect(box.getAttribute('aria-invalid')).toBe('true');
    expect(box.getAttribute('aria-describedby') ?? '').toContain(error.id);
    expect(posts()).toHaveLength(0);
  });
});

/*
 * NEW PROPOSAL — the creation door on the Ingestion Proposals panel.
 *
 * WHAT WOULD FAIL BEFORE THE BEHAVIOUR THESE TESTS DEFEND. Each item is a way this
 * form could be built that renders convincingly and still breaks a promise the
 * feature rests on, and each names the test that catches it:
 *
 *   1. A DISABLED PLACEHOLDER. The project owner asked for "at least a service
 *      button"; the measured fact is that `POST .../proposals` WORKS, so a placeholder
 *      would be a surface claiming a blocker that does not exist. (`the trigger opens
 *      a real form`, `storing a proposal sends the real create request`)
 *   2. A RUN INFERRED FROM "there is only one run". Scope comes from the server's own
 *      `record_scoped_target_field_paths`; a form that aimed a run-scoped proposal at
 *      whichever run happened to exist would pass every happy-path test.
 *      (`a run-scoped target requires a run and is refused before sending`,
 *       `a record-scoped target sends no run_id at all`)
 *   3. A DIRECT WRITE THAT BYPASSES THE NOTE ANCHOR. The note is what keeps the
 *      verbatim words safe from rejection; a form that invented a value from nowhere
 *      would break the one guarantee the whole feature is for.
 *      (`every create names a note`, `writing a source note stores it first`)
 *   4. A FORM THAT CLAIMS THE VALUE WAS WRITTEN. (`it never says the value was
 *      applied, before or after`)
 *   5. A REFUSED WRITE THAT DESTROYS WHAT WAS TYPED, or a background refresh that
 *      does. `CLAUDE.md` §11 records this repository shipping that three times, and
 *      this form is a NEW open editor on a panel whose silent-refresh gate was built
 *      for the old ones. (`a refused write leaves every box exactly as it was`,
 *       `a background change-feed refresh does not wipe a half-filled form`)
 *   6. A HALF-DONE TWO-STEP REPORTED AS "nothing happened". Writing the note and
 *      minting the proposal are two requests; if the second fails the FIRST ALREADY
 *      LANDED. (`a stored note whose proposal is refused is named, not glossed`)
 *   7. A FABRICATED FIELD LABEL. The picker shows a human label, and a label that
 *      renamed a schema field would be this bundle inventing vocabulary. The
 *      property is scoped to the HUMANIZER and not to `RUN_FIELDS`' curated labels,
 *      and that scoping is itself a correction this test made — see its own comment.
 *      (`every word of every HUMANIZED label is a word of the path it labels`,
 *       `a path with a declared spec BORROWS that label rather than minting a second one`)
 *   8. AN "unavailable" STATE INVENTED FROM A FAILED READ rather than from the
 *      server's own empty answer. (`an empty served target list is named as
 *      unavailable, with its reason`)
 *
 * Every fixture is synthetic and no test here reaches a backend. The happy path was
 * ALSO proven against a real uvicorn over HTTP while this was written — see the
 * slice report; a form proven only against a mock has not been proven to work.
 */
import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { IngestionProposalsPanel } from '../components/IngestionProposalsPanel';
import {
  NEW_PROPOSAL_ACCEPTANCE_DISCLOSURE,
  NEW_PROPOSAL_EFFECT_CLAIM,
  NEW_PROPOSAL_UNAVAILABLE_REASON,
} from '../components/NewProposalForm';
import {
  HUMAN_PROPOSED_RULE,
  proposalFieldLabel,
  proposalFieldSpec,
} from '../lib/proposalAuthoring';
import {
  PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
  PROPOSAL_TARGET_PATHS,
  noteFixture,
  notesPage,
  runFixture,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { RecordChangeSummary } from '../lib/recordChanges';
import type { ApiProposalsResponse } from '../lib/types';

const EXP = 'demo';
const LIST = `GET /api/experiments/${EXP}/proposals`;
const NOTES = `GET /api/experiments/${EXP}/notes`;
const RUNS = `GET /api/experiments/${EXP}/runs`;
const CREATE = `POST /api/experiments/${EXP}/proposals`;
const CAPTURE = `POST /api/experiments/${EXP}/notes`;

/** The one record-scoped target the server serves, and one that needs a run. */
const RECORD_PATH = 'system.technique';
const RUN_PATH = 'sample.material.name';
const VERSION = '1.7';
const NOTE_ID = '01SYNTHTESTNOTE000000000A1';
const RUN_ID = '01SYNTHTESTRUN0000000000A1';

afterEach(() => {
  vi.unstubAllGlobals();
});

function page(over: Partial<ApiProposalsResponse> = {}): ApiProposalsResponse {
  return {
    proposals: [],
    total: 0,
    returned: 0,
    by_state: { open: 0, accepted: 0, rejected: 0, superseded: 0, withdrawn: 0 },
    has_more: false,
    next_cursor: null,
    order: 'oldest_first' as const,
    window_default: 50,
    window_max: 200,
    max_per_record: 1000,
    unreadable_entries: 0,
    target_field_paths: PROPOSAL_TARGET_PATHS,
    record_scoped_target_field_paths: PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
    states: ['open', 'accepted', 'rejected', 'superseded', 'withdrawn'],
    review_actions: ['accept', 'reject', 'supersede', 'withdraw'],
    accepted_from_values: ['candidate', 'edited'],
    experiment_version: VERSION,
    ...over,
  };
}

/** The proposal the create route answers with. Shape only — no test reads its science. */
function created(over: Record<string, unknown> = {}) {
  return {
    proposal: {
      proposal_id: 'P-NEW',
      experiment_id: EXP,
      note_id: NOTE_ID,
      run_id: null,
      target_field_path: RECORD_PATH,
      proposed_value: 'XANES',
      rule: HUMAN_PROPOSED_RULE,
      source: 'typed_note',
      proposed_utc: '2099-04-02T09:20:00Z',
      base_rev: 3,
      target_digest: 'd',
      start_char: null,
      end_char: null,
      client_request_key: 'k',
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
      current_target_digest: 'd',
      target_stale: false,
      still_current: null,
      excerpt: null,
      attributed: false,
      accepted_by: null,
    },
    deduplicated: false,
    experiment_version: '1.8',
    ...over,
  };
}

function renderPanel(activity: RecordChangeSummary | null = null) {
  return render(
    <MemoryRouter
      initialEntries={['/']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <IngestionProposalsPanel experimentId={EXP} activity={activity} />
    </MemoryRouter>,
  );
}

/** Every POST this panel made, with its parsed body and `If-Match`. */
function posts(): { url: string; body: Record<string, unknown>; ifMatch?: string }[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls
    .filter(([, init]) => init?.method === 'POST')
    .map(([url, init]) => ({
      url: String(url),
      body: JSON.parse(String(init?.body)) as Record<string, unknown>,
      ifMatch: (init?.headers as Record<string, string> | undefined)?.['If-Match'],
    }));
}

/** Open the form and wait for its lazy note read to settle. */
async function openForm() {
  fireEvent.click(await screen.findByRole('button', { name: 'New Proposal' }));
  await screen.findByText('Source Note');
}

function chooseField(path: string) {
  fireEvent.change(screen.getByLabelText('Field this value is for'), {
    target: { value: path },
  });
}

// ---------------------------------------------------------------------------

describe('New Proposal · the creation door exists and is real', () => {
  it('the trigger opens a real form, not a disabled placeholder', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
    });
    renderPanel();

    const trigger = await screen.findByRole('button', { name: 'New Proposal' });
    // NOT disabled, and NOT wearing an unavailability label. The measured fact is
    // that creation works; a placeholder here would assert a blocker that is not real.
    expect((trigger as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText(/Unavailable on this deployment/)).toBeNull();

    fireEvent.click(trigger);
    await screen.findByText('Source Note');
    expect(screen.getByLabelText('Field this value is for')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Store This Proposal' })).toBeTruthy();
  });

  it('is discoverable from the panel itself — the trigger renders before anything is opened', async () => {
    stubFetchRoutes({ [LIST]: { body: page() } });
    renderPanel();

    // The defect the owner reported was that the proposals surface offered no way in
    // at all. The trigger must be present on first paint of a loaded panel.
    await screen.findByRole('button', { name: 'New Proposal' });
    expect(
      screen.getByText(/Suggest a value for one field, citing the note it was read from/),
    ).toBeTruthy();
  });
});

describe('New Proposal · scope is the server’s answer, never inferred', () => {
  it('a record-scoped target asks for no run and sends no run_id at all', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      // A run EXISTS. A form that inferred a run "because there is one" would
      // silently attach it, and every happy-path assertion would still pass.
      [RUNS]: { body: { runs: [runFixture()], total: 1, returned: 1 } },
      [CREATE]: { body: created() },
    });
    renderPanel();
    await openForm();

    fireEvent.click(screen.getByLabelText('Cite a note this record already holds'));
    fireEvent.change(await screen.findByLabelText(/The note this value was read from/), {
      target: { value: NOTE_ID },
    });
    chooseField(RECORD_PATH);

    expect(screen.queryByLabelText('Run this value is about')).toBeNull();
    expect(screen.getByText(/recorded on the record, so this proposal names no run/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XANES"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Store This Proposal' }));

    await waitFor(() => expect(posts().length).toBe(1));
    const sent = posts()[0];
    expect(sent.url).toContain('/proposals');
    expect(sent.body.target_field_path).toBe(RECORD_PATH);
    // ABSENT, not null. A `run_id: null` would be this client answering a question
    // the record-scoped path does not ask.
    expect('run_id' in sent.body).toBe(false);
  });

  it('a run-scoped target requires a run and is refused BEFORE sending', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [runFixture()], total: 1, returned: 1 } },
      [CREATE]: { body: created() },
    });
    renderPanel();
    await openForm();

    fireEvent.click(screen.getByLabelText('Cite a note this record already holds'));
    fireEvent.change(await screen.findByLabelText(/The note this value was read from/), {
      target: { value: NOTE_ID },
    });
    chooseField(RUN_PATH);
    await screen.findByLabelText('Run this value is about');
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"CuO"' },
    });

    // The control is not submittable, AND nothing was sent. The second half is the
    // real assertion: a disabled button that still fired would pass the first.
    const store = screen.getByRole('button', {
      name: 'Store This Proposal',
    }) as HTMLButtonElement;
    expect(store.disabled).toBe(true);
    fireEvent.click(store);
    expect(posts().length).toBe(0);

    // Choosing the run makes it submittable and the run travels with the request.
    fireEvent.change(screen.getByLabelText('Run this value is about'), {
      target: { value: RUN_ID },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Store This Proposal' }));
    await waitFor(() => expect(posts().length).toBe(1));
    expect(posts()[0].body.run_id).toBe(RUN_ID);
  });

  it('a run-scoped target with no runs on the record says so instead of offering a picker', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
    });
    renderPanel();
    await openForm();
    chooseField(RUN_PATH);

    expect(
      await screen.findByText(/this record has no runs yet \(or they could not be read\)/),
    ).toBeTruthy();
    expect(screen.queryByLabelText('Run this value is about')).toBeNull();
  });
});

describe('New Proposal · the note anchor is never bypassed', () => {
  it('every create names a note, and the rule is the shared provenance sentence', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
      [CREATE]: { body: created() },
    });
    renderPanel();
    await openForm();

    fireEvent.click(screen.getByLabelText('Cite a note this record already holds'));
    fireEvent.change(await screen.findByLabelText(/The note this value was read from/), {
      target: { value: NOTE_ID },
    });
    chooseField(RECORD_PATH);
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XANES"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Store This Proposal' }));

    await waitFor(() => expect(posts().length).toBe(1));
    const sent = posts()[0];
    expect(sent.body.note_id).toBe(NOTE_ID);
    // THE SAME SENTENCE THE SIBLING SURFACE STORES. Two surfaces performing one act
    // must not store two different provenance sentences.
    expect(sent.body.rule).toBe(HUMAN_PROPOSED_RULE);
    // The record's own version, quoted — never a run's, and never absent.
    expect(sent.ifMatch).toBe(`"${VERSION}"`);
    // Exactly-once within the record, keyed the same way the sibling keys it, so a
    // double click on either surface dedupes to one proposal.
    expect(String(sent.body.client_request_key)).toContain(`note-propose:${NOTE_ID}:${RECORD_PATH}:`);
  });

  it('writing a source note stores it FIRST, then cites the id the server gave back', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
      [CAPTURE]: {
        body: {
          note: { ...noteFixture(), id: 'N-FRESH', text: 'Logbook: technique was XANES.' },
          experiment_version: '1.75',
        },
      },
      [CREATE]: { body: created({ experiment_version: '1.8' }) },
    });
    renderPanel();
    await openForm();

    // With no note on the record the only possible source is a new one, and that is
    // the mode the form opens in — the one default that invents nothing.
    expect(
      (screen.getByLabelText('Write a source note now') as HTMLInputElement).checked,
    ).toBe(true);
    fireEvent.change(screen.getByLabelText('What the source says, in your words'), {
      target: { value: 'Logbook: technique was XANES.' },
    });
    chooseField(RECORD_PATH);
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XANES"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Store This Proposal' }));

    await waitFor(() => expect(posts().length).toBe(2));
    const [note, proposal] = posts();
    // ORDER MATTERS: the note must exist before anything may cite it.
    expect(note.url).toContain('/notes');
    expect(note.body.text).toBe('Logbook: technique was XANES.');
    expect(note.body.source).toBe('typed_note');
    expect(note.ifMatch).toBe(`"${VERSION}"`);
    expect(proposal.url).toContain('/proposals');
    expect(proposal.body.note_id).toBe('N-FRESH');
    // THE SECOND WRITE CARRIES THE VERSION THE FIRST RETURNED. Reusing the stale
    // token would make the note write guarantee the proposal write's 412.
    expect(proposal.ifMatch).toBe('"1.75"');
  });

  it('a stored note whose proposal is then refused is NAMED, not glossed as "nothing happened"', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
      [CAPTURE]: {
        body: { note: { ...noteFixture(), id: 'N-FRESH' }, experiment_version: '1.75' },
      },
      [CREATE]: { status: 422, body: { error: 'unrecognized_field' } },
    });
    renderPanel();
    await openForm();

    fireEvent.change(screen.getByLabelText('What the source says, in your words'), {
      target: { value: 'Logbook line.' },
    });
    chooseField(RECORD_PATH);
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XANES"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Store This Proposal' }));

    // The half that succeeded is stated, because it did succeed and the reader's
    // words are now on the record.
    expect(
      await screen.findByText(/Your source note WAS stored on this record and is safe/),
    ).toBeTruthy();
    expect(screen.getByText(/no proposal exists yet/)).toBeTruthy();
  });
});

describe('New Proposal · it never claims a write it did not make', () => {
  it('it never says the value was applied, before or after storing', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
      [CREATE]: { body: created() },
    });
    renderPanel();
    await openForm();

    // BEFORE: the effect claim is on screen while the reader is still filling it in,
    // not tucked behind the disclosure.
    expect(screen.getByText(NEW_PROPOSAL_EFFECT_CLAIM)).toBeTruthy();
    // The presence of the right sentence beside the ABSENCE of the wrong one, so a
    // build that renders both does not pass.
    expect(screen.queryByText(/the value has been written/i)).toBeNull();
    expect(screen.queryByText(/field updated/i)).toBeNull();
  });

  it('discloses that acceptance is blocked by configuration, without faking or hiding it', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
    });
    renderPanel();
    await openForm();

    // Behind a NATIVE disclosure — keyboard operable, screen-reader announced, and
    // queryable whether open or closed — never hover-only.
    expect(screen.getByText(NEW_PROPOSAL_ACCEPTANCE_DISCLOSURE)).toBeTruthy();
    expect(
      screen.getByText(/What happens after you store it\?/).tagName.toLowerCase(),
    ).toBe('summary');
    // And it must not read as "creation is blocked", which is the false half.
    expect(NEW_PROPOSAL_ACCEPTANCE_DISCLOSURE).toContain('Creating a proposal works.');
  });

  it('shows the exact provenance sentence that will be stored, rather than hiding it', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
    });
    renderPanel();
    await openForm();

    expect(screen.getByText(HUMAN_PROPOSED_RULE)).toBeTruthy();
    expect(screen.getByText(/an explanation, not a code or an identifier/)).toBeTruthy();
  });
});

describe('New Proposal · nothing typed is ever destroyed', () => {
  it('a refused write leaves every box exactly as it was', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
      [CREATE]: { status: 500, body: {} },
    });
    renderPanel();
    await openForm();

    fireEvent.click(screen.getByLabelText('Cite a note this record already holds'));
    fireEvent.change(await screen.findByLabelText(/The note this value was read from/), {
      target: { value: NOTE_ID },
    });
    chooseField(RECORD_PATH);
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XANES"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Store This Proposal' }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    // The form is still open and still holds what was typed.
    expect(
      (screen.getByLabelText('The value, as JSON') as HTMLTextAreaElement).value,
    ).toBe('"XANES"');
    expect(
      (screen.getByLabelText('Field this value is for') as HTMLSelectElement).value,
    ).toBe(RECORD_PATH);
  });

  it('a 412 is recoverable, and says so, without clearing the form', async () => {
    let attempt = 0;
    stubFetchRoutes({
      /*
       * THE LIST ADVANCES AFTER THE REFUSAL, WHICH IS WHAT A REAL BACKEND DOES and
       * is why this fixture is a thunk. The panel adopts a version from TWO places
       * after a 412 — the refusal body (immediately) and the silent reload it
       * triggers (a moment later, and more authoritative, because it is the list
       * route's own answer). A fixture that kept serving the STALE version would
       * have the reload overwrite the recovery and the resubmit 412 forever; that is
       * a property of the stub, not of the panel, and pinning it would pin a fiction.
       */
      [LIST]: () => ({ body: page(attempt === 0 ? {} : { experiment_version: '2.0' }) }),
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
      [CREATE]: () => {
        attempt += 1;
        return attempt === 1
          ? {
              status: 412,
              body: {
                error: 'stale_write',
                current_version: '2.0',
                expected_version: VERSION,
              },
            }
          : { body: created() };
      },
    });
    renderPanel();
    await openForm();

    fireEvent.click(screen.getByLabelText('Cite a note this record already holds'));
    fireEvent.change(await screen.findByLabelText(/The note this value was read from/), {
      target: { value: NOTE_ID },
    });
    chooseField(RECORD_PATH);
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"XANES"' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Store This Proposal' }));

    expect(
      await screen.findByText(/This record changed while you were filling this in/),
    ).toBeTruthy();
    expect(
      (screen.getByLabelText('The value, as JSON') as HTMLTextAreaElement).value,
    ).toBe('"XANES"');

    // AND THE RECOVERY IS REAL: submitting again carries the version the server
    // reported, not the stale one. A message promising recovery over an unchanged
    // token would be the exact over-claim this project keeps catching.
    fireEvent.click(screen.getByRole('button', { name: 'Store This Proposal' }));
    await waitFor(() => expect(posts().length).toBe(2));
    expect(posts()[1].ifMatch).toBe('"2.0"');
  });

  it('a background change-feed refresh does not wipe a half-filled form', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
    });
    const { rerender } = renderPanel();
    await openForm();

    chooseField(RECORD_PATH);
    fireEvent.change(screen.getByLabelText('The value, as JSON'), {
      target: { value: '"half typed' },
    });

    // A colleague's proposal arrives. The panel refreshes SILENTLY; this form is a
    // sibling of the list and must not be unmounted by it.
    rerender(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <IngestionProposalsPanel
          experimentId={EXP}
          activity={{
            recordMoved: false,
            runIds: [],
            proposalIds: ['P-FROM-A-COLLEAGUE'],
            proposalStates: ['open'],
            otherKinds: [],
            highestRev: 9,
            runRev: -1,
            proposalRev: 9,
          }}
        />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(
        (screen.getByLabelText('The value, as JSON') as HTMLTextAreaElement).value,
      ).toBe('"half typed'),
    );
    // And the form is still OPEN — an unmount would clear it and also close it.
    expect(screen.getByRole('button', { name: 'Store This Proposal' })).toBeTruthy();
  });
});

describe('New Proposal · the unavailable case is real, not invented', () => {
  it('an empty served target list is named as unavailable, with its reason', async () => {
    stubFetchRoutes({ [LIST]: { body: page({ target_field_paths: [] }) } });
    renderPanel();

    // In its REAL location, with the reason one keystroke away — never a button that
    // fails after being clicked.
    expect(await screen.findByText(/New Proposal · Unavailable on this deployment/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'New Proposal' })).toBeNull();
    expect(screen.getByText(NEW_PROPOSAL_UNAVAILABLE_REASON)).toBeTruthy();
    expect(screen.getByText('Why?').tagName.toLowerCase()).toBe('summary');
  });

  it('a FAILED read is not reported as unavailable — that is a different fact', async () => {
    stubFetchRoutes({ [LIST]: { status: 500, body: {} } });
    renderPanel();

    await waitFor(() => expect(screen.getAllByRole('alert').length).toBeGreaterThan(0));
    // Neither the working control nor the unavailability claim. "We could not look"
    // is not "this deployment cannot do it", and collapsing the two would be the
    // same over-claim `target_stale: null` already has a rule against on this panel.
    expect(screen.queryByRole('button', { name: 'New Proposal' })).toBeNull();
    expect(screen.queryByText(/Unavailable on this deployment/)).toBeNull();
  });
});

describe('New Proposal · the field label invents no vocabulary', () => {
  /*
   * THE §11 PRECEDENT, APPLIED. `test_blocker_wording.py` pins that a humanized
   * blocker key emits only words the key already contained; this is the same
   * property for a schema path, and it is what keeps `proposalFieldLabel` a CASING
   * transform rather than a second name for a field.
   */
  it('every word of every HUMANIZED label is a word of the path it labels', () => {
    /*
     * SCOPED TO THE FALLBACK, AND THE SCOPE IS A CORRECTION MADE BY THIS TEST.
     *
     * Its first version asserted the property over ALL 18 served paths and FAILED:
     * `RUN_FIELDS` labels `timestamps.acquired_start_utc` "Acquisition start", and
     * "Acquisition" is not a word of that path. That is not a defect — it is a
     * curated, reviewed vocabulary that has been on screen in `RunCard` since long
     * before this form — but it means the "casing only" property belongs to the
     * HUMANIZER, which is the part this slice wrote, and not to the declared labels,
     * which it borrows. Both halves are pinned: this test for the humanizer, the
     * next one for the borrowing.
     */
    const humanized = PROPOSAL_TARGET_PATHS.filter((p) => proposalFieldSpec(p) === null);
    // A negative control: if the spec set ever grew to cover everything, this test
    // would pass vacuously and stop defending anything.
    expect(humanized.length).toBeGreaterThan(0);
    for (const path of humanized) {
      const label = proposalFieldLabel(path);
      const pathWords = path
        .split(/[.:_]/)
        .map((w) => w.toLowerCase())
        .filter((w) => w !== '');
      for (const word of label.split(/\s+/)) {
        expect(pathWords).toContain(word.toLowerCase());
      }
    }
  });

  it('a path with a declared spec BORROWS that label rather than minting a second one', () => {
    const specced = PROPOSAL_TARGET_PATHS.filter((p) => proposalFieldSpec(p) !== null);
    expect(specced.length).toBeGreaterThan(0);
    for (const path of specced) {
      // Verbatim. A form that re-worded `RUN_FIELDS`' label would put two names for
      // one field on two screens of the same application.
      expect(proposalFieldLabel(path)).toBe(proposalFieldSpec(path)?.label);
    }
  });

  it('the dotted path is shown beside the label, never replaced by it', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
    });
    renderPanel();
    await openForm();
    chooseField(RECORD_PATH);

    // `UX-014`: the path is demoted, never removed — a curator maps fields by path.
    const mono = document.querySelectorAll('.new-proposal-form .mono');
    expect(Array.from(mono).some((el) => el.textContent === RECORD_PATH)).toBe(true);
  });
});

/* ── a disabled control must say why, in the state where it is disabled ────── */

/**
 * *** THIS EXISTS BECAUSE ITS ABSENCE LET A DISABLED CONTROL SHIP WITH NO
 * REASON, on this feature's own primary path. ***
 *
 * `Cite a note this record already holds` is disabled when the record holds no
 * notes. Its explanation used to render inside `sourceMode === 'existing'` — and
 * `sourceMode` defaults to `'new'`, so the reason was unreachable precisely when
 * it applied: the only control that would have revealed it was the disabled one.
 *
 * That is the state of every freshly created record, and it is the exact case
 * the owner was in when he reported that a proposal could not be added. Found by
 * independent review; 703 lines of tests in this file passed it.
 */
describe('the no-notes state explains its own disabled control', () => {
  it('states why citing is unavailable WITHOUT the reader selecting that mode', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
    });
    renderPanel();
    await openForm();

    // The default mode is "write a note now" — the reason must be visible anyway.
    const cite = screen.getByLabelText(/Cite a note this record already holds/i);
    expect(cite).toBeDisabled();
    expect(
      screen.getByText(/This record holds no notes yet, so there is nothing to cite/i),
      'a disabled control with no reason beside it leaves a reader guessing whether the ' +
        'feature is broken — and the reason must not live inside the branch that control selects',
    ).toBeInTheDocument();
  });

  /*
   * THE NEGATIVE CONTROL. With notes present the hint must be ABSENT, or the
   * assertion above would pass on a form that shows it unconditionally — which
   * would be a different false claim, not a fix.
   */
  it('does NOT claim the record has no notes when it has some', async () => {
    stubFetchRoutes({
      [LIST]: { body: page() },
      [NOTES]: { body: notesPage([noteFixture()]) },
      [RUNS]: { body: { runs: [], total: 0, returned: 0 } },
    });
    renderPanel();
    await openForm();

    expect(screen.getByLabelText(/Cite a note this record already holds/i)).toBeEnabled();
    expect(
      screen.queryByText(/This record holds no notes yet/i),
    ).toBeNull();
  });
});

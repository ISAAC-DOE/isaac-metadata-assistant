/*
 * The Transcript Capture panel.
 *
 * WHAT WOULD FAIL BEFORE THE BEHAVIOUR THESE TESTS DEFEND. Each is a way the panel
 * could be built that renders perfectly and still breaks the feature's promise:
 *
 *   1. A panel that reads while the reader types — a debounce, an `onChange`
 *      handler, an autosave. Authoritative metadata would then move from text
 *      nobody finished.
 *      (`typing alone sends nothing`, `finalizing is the only thing that reads`)
 *   2. An Accept control that writes through a path of its own, or one that omits
 *      the run's `If-Match`, silently overwriting a concurrent edit.
 *      (`accepting writes through the existing run edit, with the run's version`,
 *       `the panel never issues a write to any path but the run edit`)
 *   3. A panel that clears the transcript box, or hides the stored notes, after a
 *      reading that proposed nothing — leaving a scientist to believe their words
 *      went nowhere.
 *      (`text survives a reading that proposed nothing`,
 *       `text survives a failed accept`)
 *   4. A voice surface that says "Connected", "Ready", or "Configured", or that
 *      shows a spinner where a refusal belongs.
 *      (`no part of this panel claims a provider exists`,
 *       `the refusal is rendered from the server's own words`)
 *   5. A run chosen on the reader's behalf when the record has exactly one.
 *      (`the run is never pre-selected`)
 *
 * Every fixture is synthetic and no test here reaches a backend.
 */
import { describe, it, expect, afterEach, beforeEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axe from 'axe-core';

import { TranscriptCapturePanel } from '../components/TranscriptCapturePanel';
import { CAPTURE_COPY, CAPTURE_GUIDANCE_SENTENCE } from '../lib/transcriptCaptureContent';
import {
  CAPTURE_GUIDANCE_KEY,
  isCaptureGuidanceSeen,
} from '../lib/transcriptCapturePreference';
import { runFixture, stubFetchRoutes } from '../test/apiFixtures';

const EXP = 'demo';
const RUNS = `GET /api/experiments/${EXP}/runs`;
const CAPS = 'GET /api/providers/capabilities';
const TRANSCRIPT = `POST /api/experiments/${EXP}/transcript`;
const TRANSCRIBE = 'POST /api/transcription';

const RUN = runFixture({ id: 'run-1', label: 'Run 1', version: 'r1.0', fields: {} });

const runsPage = {
  runs: [RUN],
  experiment_version: 'g1.4',
  total: 1,
  matched: 1,
  returned: 1,
  offset: 0,
};

/** The seam report a deployment with no provider actually serves. */
const capabilities = {
  any_provider_configured: false,
  decision_reference: 'docs/ai-integration-decision-packet.md',
  note: 'A note the server composes.',
  manual_transcript_available: true,
  seams: [
    {
      seam: 'transcription',
      implementation: 'unconfigured',
      configured: false,
      is_test_double: false,
      reason:
        'No transcription provider is configured. Speech is not transcribed and no audio leaves the browser.',
      selected_by: 'ISAAC_TRANSCRIPTION_PROVIDER',
    },
  ],
};

function candidate(over: Partial<Record<string, unknown>> = {}) {
  return {
    field_path: 'context.temperature_K',
    proposed_value: 300,
    quote: 'Temperature was 300 K.',
    start_char: 0,
    end_char: 22,
    origin: 'transcript',
    produced_by: 'transcript-reader',
    rule: 'the words temperature and a number followed by K appear in one clause',
    provenance: { reader_rule: 'temperature_kelvin' },
    status: 'needs_confirmation',
    verified: false,
    is_evidence: false,
    requires_user_confirmation: true,
    ...over,
  };
}

function noteOf(text: string, id: string) {
  return {
    id,
    experiment_id: EXP,
    run_id: 'run-1',
    source: 'transcript',
    text,
    revised_text: null,
    captured_utc: '2099-04-02T09:12:00Z',
    state: 'unreviewed',
    candidate_field_path: null,
    candidate_rule: null,
    mapped_field_path: null,
    history: [],
    status: 'unmapped_note',
    verified: false,
    is_evidence: false,
    is_field_value: false,
    display_text: text,
  };
}

/**
 * One entry of the capture's `proposals` list — what the SERVER stored, paired to
 * the candidate it came from.
 *
 * `candidate_index` and not a field path, for the reason the wire type gives: two
 * candidates can share one path, and matching on the path would collapse them.
 */
function mintedFor(index: number, over: Partial<Record<string, unknown>> = {}) {
  return {
    candidate_index: index,
    client_request_key: `transcript-capture:n1:${index}`,
    deduplicated: false,
    proposal: {
      proposal_id: `p${index}`,
      experiment_id: EXP,
      note_id: 'n1',
      run_id: 'run-1',
      target_field_path: 'context.temperature_K',
      proposed_value: 300,
      rule: 'the words temperature and a number followed by K appear in one clause',
      state: 'open',
      applied: false,
      verified: false,
      is_evidence: false,
      is_field_value: false,
    },
    ...over,
  };
}

function reading(over: Partial<Record<string, unknown>> = {}) {
  return {
    capture: {
      finalized: true,
      run_id: 'run-1',
      segments: 1,
      retention: {
        state: 'retained_with_experiment',
        notes_captured: 1,
        deletable: false,
        description: 'The finalized transcript is stored with this record as notes.',
        not_implemented: [
          { state: 'retain_during_draft', reason: 'Nothing here removes a note.' },
        ],
        raw_audio: { stored: false, reason: 'No audio reaches this server.' },
      },
    },
    applied: false,
    candidates: [candidate()],
    clarifications: [],
    abstentions: [],
    review_required: [],
    notes: [noteOf('Temperature was 300 K.', 'n1')],
    proposals: [mintedFor(0)],
    unproposable: [],
    ambiguity_policy: [],
    /*
     * THE CONTRACT NAMES THE REVIEW ROUTE, and this fixture used to name
     * `PATCH .../runs/{run_id}`. It changed because the server's did: a candidate is
     * now stored as a durable proposal in the same save as the notes, and a stored
     * proposal is accepted through its own operation. A fixture still carrying the
     * run PATCH would let this suite go on proving a contract the server no longer
     * publishes — which is the exact failure `test_contract_description_parity.py`
     * exists to catch on the description side.
     */
    accept_contract: {
      method: 'POST',
      path: '/api/experiments/{experiment_id}/proposals/{proposal_id}/review',
      requires: ['confirmed_by_user: true', 'action: accept'],
      message: 'This operation writes no field.',
    },
    experiment_version: 'g1.5',
    ...over,
  };
}

const BASE_ROUTES: Record<string, unknown> = {
  [RUNS]: { body: runsPage },
  [CAPS]: { body: capabilities },
};

beforeEach(() => {
  try {
    localStorage.setItem(
      CAPTURE_GUIDANCE_KEY,
      JSON.stringify({
        guidanceId: 'isaac-transcript-capture-guidance',
        version: 1,
        seen: true,
        seenAt: '2099-01-01T00:00:00Z',
      }),
    );
  } catch {
    /* the read path fails safe; a test that needs the guidance clears the key */
  }
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Render the panel and OPEN it — it is a closed disclosure until a reader acts. */
async function renderPanel() {
  const rendered = render(
    <MemoryRouter
      initialEntries={['/']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <TranscriptCapturePanel experimentId={EXP} />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Start a capture' }));
  return rendered;
}

/** Every request this panel issued, as `"METHOD /path"`. */
function requests(): string[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls.map(([url, init]) => `${init?.method ?? 'GET'} ${String(url).replace(/^https?:\/\/[^/]+/, '')}`);
}

/** Every write, with its parsed body and `If-Match`. */
function writes(): { key: string; body: Record<string, unknown>; ifMatch?: string }[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls
    .filter(([, init]) => init?.method === 'POST' || init?.method === 'PATCH')
    .map(([url, init]) => ({
      key: `${init?.method} ${String(url).replace(/^https?:\/\/[^/]+/, '')}`,
      body: JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>,
      ifMatch: (init?.headers as Record<string, string> | undefined)?.['If-Match'],
    }));
}

async function typeAndFinalize(text = 'Temperature was 300 K.') {
  const box = await screen.findByLabelText('Transcript');
  fireEvent.change(box, { target: { value: text } });
  fireEvent.change(await screen.findByLabelText(/Run these notes describe/), {
    target: { value: 'run-1' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Finalize and read' }));
}

// --- 1. nothing is read from unfinished text ---------------------------------

describe('unfinished text', () => {
  it('a closed panel fetches nothing at all', async () => {
    // The record screen already issues a bundle of reads on mount. A section that
    // quietly added two more, for readers who never dictate anything, would change
    // the request pattern of every screen it appears on.
    stubFetchRoutes(BASE_ROUTES as never);
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
      </MemoryRouter>,
    );
    await screen.findByRole('button', { name: 'Start a capture' });
    expect(requests()).toEqual([]);
    expect(screen.queryByLabelText('Transcript')).toBeNull();
  });

  it('typing alone sends nothing', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    const box = await screen.findByLabelText('Transcript');
    fireEvent.change(box, { target: { value: 'Temperature was' } });
    fireEvent.change(box, { target: { value: 'Temperature was 300' } });
    fireEvent.change(box, { target: { value: 'Temperature was 300 K.' } });
    await waitFor(() => expect(requests()).toContain(RUNS));
    expect(writes()).toEqual([]);
    expect(requests().filter((key) => key === TRANSCRIPT)).toEqual([]);
  });

  it('finalizing is the only thing that reads, and it says so in the body', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText('context.temperature_K');
    const finalize = writes().filter((entry) => entry.key === TRANSCRIPT);
    expect(finalize).toHaveLength(1);
    expect(finalize[0].body.finalized).toBe(true);
    expect(finalize[0].body.text).toBe('Temperature was 300 K.');
    expect(finalize[0].ifMatch).toBe('"g1.4"');
  });

  it('the finalize control is unavailable while the box is empty', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    expect(await screen.findByRole('button', { name: 'Finalize and read' })).toBeDisabled();
  });
});

// --- 2. a candidate is never a value, and the panel now WRITES NOTHING --------
//
// THIS SECTION USED TO PROVE THE OPPOSITE HALF OF THE SAME PROMISE, and the four
// tests it lost are named here rather than quietly dropped: "accepting writes
// through the existing run edit, with the run's own version", "the panel never
// issues a write to any path but the run edit", "undo restores what the run held
// before, through the same path", and "rejecting writes nothing at all". All four
// were correct, and all four pinned an Accept control that lived in this panel and
// called `PATCH .../runs/{run_id}` directly.
//
// That control is gone. A candidate is now stored server-side as a durable ingestion
// proposal in the same save as the notes, and accepting one is the proposals
// surface's act — which is what makes it visible to a colleague, recorded with a
// reason when refused, and survivable across a navigation. So the claim those four
// tests made ("the write goes through the existing path") is now made where the write
// is, and what this section proves instead is stronger and simpler: from finalize
// onward this panel issues NO write at all.

describe('what the capture stored', () => {
  it('the panel issues no write but the finalize itself', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText('context.temperature_K');

    // THE WHOLE SET, not "no PATCH". A `queryByRole('button', {name: 'Accept'})`
    // assertion would pass over a panel that had merely renamed the control, and a
    // "no PATCH" assertion would pass over one that had moved the write to a POST.
    expect(writes().map((entry) => entry.key)).toEqual([TRANSCRIPT]);
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull();
    expect(screen.queryByLabelText('Edit before accepting')).toBeNull();
  });

  it('a stored proposal says it is waiting for review, and where', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText('context.temperature_K');

    expect(screen.getByText(CAPTURE_COPY.proposalStored)).toBeInTheDocument();
    expect(screen.getByText(/waits in Ingestion Proposals/)).toBeInTheDocument();
    // THE POSITIVE CONTROL FOR THE CONDITIONAL BLANKET CLAIM. This reading refused
    // nothing, so the paragraph saying every proposal below is stored is true of it
    // and is shown. Its negative control is in the refused-candidate test below,
    // which asserts the same paragraph is ABSENT.
    expect(screen.getByText(CAPTURE_COPY.candidatesAllStored)).toBeInTheDocument();
    // THE SERVER'S ROUTE, RENDERED RATHER THAN TRANSCRIBED. A literal in this bundle
    // would be a second copy of the write contract, free to drift.
    expect(container.textContent).toContain(
      '/api/experiments/{experiment_id}/proposals/{proposal_id}/review',
    );
    expect(container.textContent).not.toContain('/runs/{run_id}');
  });

  it('a proposal the record already held says so instead of claiming a create', async () => {
    /*
     * A FIXTURE-ONLY PATH, AND THAT IS STATED RATHER THAN IMPLIED. No request can
     * make the server emit `deduplicated: true` here at this HEAD — the transcript
     * route's dedupe key is built from a note id minted by the same request, so
     * nothing already on the record can carry it (contract §11.2). The field is on
     * the wire, so the panel must render it truthfully; this asserts it does, and
     * does not assert that a deployment produces it.
     */
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIPT]: { body: reading({ proposals: [mintedFor(0, { deduplicated: true })] }) },
    } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText('context.temperature_K');
    expect(screen.getByText(CAPTURE_COPY.proposalAlreadyStored)).toBeInTheDocument();
    expect(screen.queryByText(CAPTURE_COPY.proposalStored)).toBeNull();
  });

  it("a candidate the server could not store says so, in the SERVER's words", async () => {
    const refused = reading({
      proposals: [],
      unproposable: [
        {
          candidate_index: 0,
          field_path: 'context.temperature_K',
          note_id: 'n1',
          error: 'no_write_path_for_field',
          message:
            'No write operation in this build accepts a value at this path, so a ' +
            'proposal for it could be created and never applied.',
        },
      ],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: refused } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText('context.temperature_K');

    expect(
      screen.getByText(/No write operation in this build accepts a value at this path/),
    ).toBeInTheDocument();
    // AND NOT A SENTENCE THIS BUNDLE COMPOSED. The panel renders the server's
    // `message`; a reason written here would be this client explaining a refusal it
    // did not make.
    expect(container.textContent).not.toContain(CAPTURE_COPY.proposalStored);
    // AND NO BLANKET CLAIM ABOVE THE LIST. The lead paragraph used to end "Each
    // proposal below is stored with this record and waits in Ingestion Proposals",
    // rendered unconditionally — so on THIS reading it asserted storage for the one
    // candidate the server had just declined, one line above the server's own
    // sentence saying nothing was stored. The claim now renders only when
    // `unproposable` is empty. MUTATION: dropping the
    // `reading.unproposable.length === 0` guard in the panel turns this RED.
    expect(container.textContent).not.toContain(CAPTURE_COPY.candidatesAllStored);
    expect(container.textContent).not.toContain('is stored with this record and waits');
    // The lead paragraph is still there, describing the labels rather than claiming
    // them, so this is not passing merely because the whole paragraph vanished.
    expect(screen.getByText(/A proposal, not a value/)).toBeInTheDocument();
    // The words are still stored, which is the whole of the promise.
    expect(screen.getAllByText('Temperature was 300 K.').length).toBeGreaterThanOrEqual(1);
  });

  it('a proposal is labelled as a proposal, with the words it came from', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText('context.temperature_K');
    expect(screen.getByText(/A proposal, not a value/)).toBeInTheDocument();
    expect(screen.getByText(/“Temperature was 300 K\.”/)).toBeInTheDocument();
    expect(
      screen.getByText(/the words temperature and a number followed by K/),
    ).toBeInTheDocument();
  });
});

// --- 3. text is never lost ----------------------------------------------------

describe('nothing a scientist wrote is discarded', () => {
  it('text survives a reading that proposed nothing', async () => {
    const empty = reading({
      candidates: [],
      notes: [noteOf('The cryostat rattled.', 'n2')],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: empty } } as never);
    await renderPanel();
    await typeAndFinalize('The cryostat rattled.');
    await screen.findByText(/Nothing was proposed from this transcript/);
    // The words are shown as stored, AND the box still holds them. Both matches
    // are wanted: the stored-notes list and the textarea's own value.
    expect(screen.getAllByText('The cryostat rattled.').length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByLabelText('Transcript')).toHaveValue('The cryostat rattled.');
  });

  /*
   * "TEXT SURVIVES A FAILED ACCEPT" WAS HERE, and it went with the Accept control it
   * exercised — it clicked Accept, met a `412` from `PATCH .../runs/{run_id}`, and
   * asserted the transcript was still on screen. There is no accept in this panel any
   * more, so the case it covered has moved to the proposals surface.
   *
   * WHAT REPLACES IT COVERS THE SAME PROMISE ON THE PATH THAT STILL EXISTS: a
   * candidate the SERVER declined to store as a proposal. That is now the way a value
   * can fail to become one, and the claim is unchanged — the words survive.
   */
  it('text survives a candidate the server declined to store', async () => {
    const refused = reading({
      proposals: [],
      unproposable: [
        {
          candidate_index: 0,
          field_path: 'context.temperature_K',
          note_id: 'n1',
          error: 'too_many_proposals',
          message:
            'This record already holds the maximum number of proposals, so no ' +
            'proposal was created for this candidate.',
        },
      ],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: refused } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText(/already holds the maximum number of proposals/);
    // The stored note and the transcript are both still on screen.
    expect(screen.getAllByText('Temperature was 300 K.').length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByLabelText('Transcript')).toHaveValue('Temperature was 300 K.');
  });

  it('a failed finalize says the transcript was not stored and keeps the text', async () => {
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIPT]: { status: 412, body: { error: 'stale_write' } },
    } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByRole('alert');
    expect(screen.getByRole('alert')).toHaveTextContent(/was NOT stored/);
    expect(await screen.findByLabelText('Transcript')).toHaveValue('Temperature was 300 K.');
  });

  it('the panel says every segment is stored, including the ones that proposed', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText(/including the ones that produced a proposal/);
  });
});

// --- 4. ambiguity is shown as a question, never resolved ----------------------

describe('ambiguity', () => {
  it('the run is never pre-selected, even with exactly one run', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    const select = await screen.findByLabelText(/Run these notes describe/);
    expect(select).toHaveValue('');
    expect(screen.getByText(/never chosen for you, even when the record has exactly one run/)).toBeInTheDocument();
  });

  it('a clarification is rendered as a question with its alternatives', async () => {
    const asked = reading({
      candidates: [],
      clarifications: [
        {
          outcome: 'clarification',
          kind: 'ambiguous_run_reference',
          question: 'The run named here matches more than one run of this record. Which one is it?',
          quote: 'run Cooling',
          options: [
            { run_id: 'run-1', label: 'Cooling sweep', ordinal: 1 },
            { run_id: 'run-2', label: 'Cooling repeat', ordinal: 2 },
          ],
          segment_index: 0,
        },
      ],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: asked } } as never);
    await renderPanel();
    await typeAndFinalize('Notes for run Cooling.');
    await screen.findByText(/matches more than one run/);
    expect(screen.getByText('Cooling sweep')).toBeInTheDocument();
    expect(screen.getByText('Cooling repeat')).toBeInTheDocument();
    // NOTHING was proposed, so there is no Accept control to press by mistake.
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
  });

  it('an abstention states the subject and the reason, and proposes nothing', async () => {
    const abstained = reading({
      candidates: [],
      abstentions: [
        {
          outcome: 'abstention',
          kind: 'temperature_not_in_kelvin',
          reason: 'The temperature field records kelvin and this statement gives another unit.',
          quote: 'Temperature was 25 C',
          segment_index: 0,
        },
      ],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: abstained } } as never);
    await renderPanel();
    await typeAndFinalize('Temperature was 25 C.');
    await screen.findByText(/records kelvin and this statement gives another unit/);
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
  });

  it('two values for one field are BOTH offered, with the conflict stated', async () => {
    const conflicted = reading({
      candidates: [candidate(), candidate({ proposed_value: 320, quote: 'Later the temperature was 320 K.', start_char: 23 })],
      // TWO candidates, so TWO stored proposals. The server mints one per candidate,
      // and a fixture with one would be asserting against a server that dropped one.
      proposals: [mintedFor(0), mintedFor(1, { proposal: { proposal_id: 'p1', proposed_value: 320 } })],
      review_required: [
        {
          outcome: 'needs_review',
          kind: 'conflicting_values_for_one_field',
          field_path: 'context.temperature_K',
          reason: 'Accept at most one.',
          candidate_indexes: [0, 1],
        },
      ],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: conflicted } } as never);
    await renderPanel();
    await typeAndFinalize();
    const conflicts = await screen.findAllByText(/proposes another value for the same field/);
    expect(conflicts).toHaveLength(2);
    // BOTH ARE STORED AND NEITHER IS PREFERRED. The panel used to offer two Accept
    // buttons here; it now shows two stored proposals and says the choice is made in
    // Ingestion Proposals. What must not change is that there are TWO of them —
    // dropping one would be the preference this reader refuses to hold.
    expect(screen.getAllByText(CAPTURE_COPY.proposalStored)).toHaveLength(2);
    expect(screen.getAllByText(CAPTURE_COPY.conflictBothStored)).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
  });

  it('a conflict whose other side was REFUSED does not say both are stored', async () => {
    /*
     * "Both are stored" was rendered for every conflict, whatever the server had
     * done with the two candidates — so this reading, in which the second candidate
     * hit the row ceiling, was told both were stored while one row beside it carried
     * the server's sentence saying no proposal was created for it.
     *
     * MUTATION: reverting the conflict line to the single unconditional sentence
     * turns this RED on both assertions.
     */
    const halfRefused = reading({
      candidates: [candidate(), candidate({ proposed_value: 320, quote: 'Later the temperature was 320 K.', start_char: 23 })],
      proposals: [mintedFor(0)],
      unproposable: [
        {
          candidate_index: 1,
          field_path: 'context.temperature_K',
          note_id: 'n1',
          error: 'too_many_proposals',
          message:
            'This record already holds the maximum number of proposals, so no ' +
            'proposal was created for this candidate.',
        },
      ],
      review_required: [
        {
          outcome: 'needs_review',
          kind: 'conflicting_values_for_one_field',
          field_path: 'context.temperature_K',
          reason: 'Accept at most one.',
          candidate_indexes: [0, 1],
        },
      ],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: halfRefused } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText(/already holds the maximum number of proposals/);

    // The conflict is still stated on BOTH rows — it is a real conflict — and
    // neither of them claims the refused side is stored.
    expect(
      screen.getAllByText(CAPTURE_COPY.conflictNotAllStored),
    ).toHaveLength(2);
    expect(container.textContent).not.toContain(CAPTURE_COPY.conflictBothStored);
    expect(container.textContent).not.toContain('Both are stored');
    // And the row that DID get a proposal still says so, so this is not passing by
    // the panel having stopped reporting storage altogether.
    expect(screen.getByText(CAPTURE_COPY.proposalStored)).toBeInTheDocument();
  });
});

// --- 5. the voice surface claims nothing --------------------------------------

describe('voice capture', () => {
  it('no part of this panel claims a provider exists', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText('context.temperature_K');
    const text = (container.textContent ?? '').toLowerCase();
    for (const banned of [
      'connected',
      'ready to transcribe',
      'provider configured',
      'temporarily',
      'try again',
      'coming soon',
      'not yet available',
    ]) {
      expect(text).not.toContain(banned);
    }
  });

  it('the seam status is rendered from the server, not from this bundle', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    // Byte-for-byte the `reason` the capability report served.
    await screen.findByText(/No transcription provider is configured\. Speech is not transcribed/);
  });

  it('I9 — the seam line still renders when the capability report never arrives', async () => {
    /*
     * THE DISCLOSURE WAS CONDITIONAL ON THE VERY THING IT DISCLOSES. The seam line was
     * guarded by `transcription !== null`, and `transcription` is `null` in three
     * reachable states: the capabilities fetch has not resolved (every first paint after
     * the panel opens), it rejected, or the report names no such seam. In all three the
     * voice section rendered with NO statement about whether this deployment can
     * transcribe at all.
     *
     * WHY THAT IS LOAD-BEARING RATHER THAN COSMETIC. `docs/ai-integration-decision-packet.md`'s
     * D6 supersession justifies shipping a recorder against an unconfigured seam on the
     * grounds that "the mitigation is disclosure, not prevention — the seam's status
     * renders ABOVE the controls, before any recording starts". That argument is false
     * for exactly as long as the fetch has not resolved, which is the window in which a
     * reader decides whether to press Start.
     *
     * The failure is simulated the way it actually happens — the capabilities request
     * rejects — and the assertion is that the panel says UNKNOWN. It must not say "not
     * configured": the panel's own rule is that a string in this bundle describes the
     * build the browser came from, not the deployment it is talking to, which is why the
     * `.catch` leaves the report absent rather than defaulting it.
     */
    stubFetchRoutes({ ...BASE_ROUTES, [CAPS]: { status: 503, body: { detail: 'no' } } } as never);
    const { container } = await renderPanel();

    const seam = await waitFor(() => {
      const el = container.querySelector('.capture-seam');
      if (!el) throw new Error('no seam line rendered');
      return el as HTMLElement;
    });
    expect(seam.getAttribute('data-configured')).toBe('unreported');
    expect(seam.textContent).toMatch(/not reported/i);
    // It states the consequence for the reader…
    expect(seam.textContent).toMatch(/treat turning a recording into text as unavailable/i);
    // …and the audio claim, which is true either way and is what matters most when the
    // rest is unknown.
    expect(seam.textContent).toMatch(/nothing is sent anywhere/i);
    // AND IT DOES NOT OVERSTATE. Unknown is not "not configured" — a client cannot
    // assert a fact about the server it failed to read.
    expect(seam.textContent).not.toMatch(/no transcription provider is configured/i);

    // THE POSITION IS THE ARGUMENT: the status is above the controls, before any
    // recording starts. `voiceHeading` opens the section the line belongs to.
    const voice = container.querySelector('.capture-voice') as HTMLElement;
    expect(voice.contains(seam)).toBe(true);
  });

  it('the refusal is rendered from the server’s own words, with what is missing', async () => {
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIBE]: {
        status: 501,
        body: {
          refused: true,
          seam: 'transcription',
          reason: 'no_provider_configured',
          missing: ['an approved transcription provider (decision D9)'],
          message: 'This build cannot transcribe speech: no provider is configured.',
          decision_reference: 'docs/ai-integration-decision-packet.md',
        },
      },
    } as never);
    // The panel reports the browser has no recorder in jsdom, which is TRUE here
    // and is itself the honest surface — so this test drives the API directly to
    // pin the refusal rendering the recorder path leads to.
    const { api, providerRefusalOf } = await import('../lib/api');
    const failure = await api.requestTranscription({ audioRef: 'held-in-tab:1' }).catch((e: unknown) => e);
    const stated = providerRefusalOf(failure);
    expect(stated?.missing).toEqual(['an approved transcription provider (decision D9)']);
    expect(stated?.message).toContain('no provider is configured');
  });

  it('a browser with no recorder says so plainly and keeps the typed path', async () => {
    // jsdom has no `MediaRecorder`, which is the case this branch exists for.
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    await screen.findByText(/This browser does not offer audio recording/);
    expect(await screen.findByLabelText('Transcript')).toBeInTheDocument();
  });

  it('the header does NOT offer dictation as a third equal option', async () => {
    /*
     * THE COPY THIS PINS USED TO OVERCLAIM. `panelIntro` read "Type, paste, or
     * dictate notes about a run, then finalize them." — dictation offered
     * unqualified, in the panel HEADER, which renders BEFORE the panel is opened
     * and therefore before the seam status and the refusal body that would explain
     * it. `POST /api/transcription` answers `501` `no_provider_configured` in every
     * shipped deployment, and not by accident: `providers/config.py::_selected`
     * resolves unset, empty and unrecognised values all to `unconfigured`, and
     * `validate_provider_config_or_raise` REFUSES TO BOOT an app whose seam is set
     * to `deterministic-fake` (DECISION D6) — so the unconfigured implementation is
     * the only one a running application can hold.
     * `ai-integration-decision-packet.md` §9, "build nothing that implies any of it
     * exists", binds per `CLAUDE.md` §15.
     *
     * WHAT THIS TEST MUST NOT BECOME: a requirement that the recorder is gone. The
     * Record / Request a transcript / Discard controls are a deliberate product
     * decision and stay. Only the promise around them is corrected, and the
     * assertions below check the copy — not the controls.
     */
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    const text = container.textContent ?? '';
    expect(text).not.toContain('or dictate');
    expect(text).not.toMatch(/Type, paste, or dictate/);
    // It still says what DOES work, and says the audio path depends on something
    // this bundle cannot assert the presence of.
    expect(CAPTURE_COPY.panelIntro).toContain('Type or paste notes');
    expect(CAPTURE_COPY.panelIntro).toContain('needs a transcription');
    /*
     * AND IT STILL DOES NOT STATE A STATUS, which is the rule at the top of
     * `transcriptCaptureContent.ts`: every claim about what the deployment CAN do
     * comes from the server. A hardcoded "not configured" here would be a claim
     * about a deployment this bundle has never met — so fixing an overclaim must
     * not introduce the opposite one.
     */
    for (const banned of ['not configured', 'unavailable', 'cannot transcribe', 'disabled']) {
      expect(CAPTURE_COPY.panelIntro.toLowerCase()).not.toContain(banned);
    }
  });

  it('no request this panel makes carries audio', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText('context.temperature_K');
    for (const entry of writes()) {
      expect(Object.keys(entry.body)).not.toContain('audio');
      expect(Object.keys(entry.body)).not.toContain('audio_data');
    }
    expect(requests().some((key) => key.includes('/uploads'))).toBe(false);
  });
});

// --- 6. first-use guidance ----------------------------------------------------

describe('first-use guidance', () => {
  it('is shown on first use with the exact guidance sentence and a worked example', async () => {
    localStorage.removeItem(CAPTURE_GUIDANCE_KEY);
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    expect(await screen.findByText(CAPTURE_GUIDANCE_SENTENCE)).toBeInTheDocument();
    expect(screen.getByText(/Notes for run 2\. Temperature was 300 K\./)).toBeInTheDocument();
    expect(screen.getByText(/proposed for the temperature field, in kelvin/)).toBeInTheDocument();
  });

  it('is skippable, persists the dismissal, and stays reachable afterwards', async () => {
    localStorage.removeItem(CAPTURE_GUIDANCE_KEY);
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Got it' }));

    expect(screen.queryByText(CAPTURE_GUIDANCE_SENTENCE)).toBeNull();
    expect(isCaptureGuidanceSeen()).toBe(true);
    // Unobtrusive, but not gone: one control brings it back.
    fireEvent.click(screen.getByRole('button', { name: 'Show capture guidance' }));
    expect(screen.getByText(CAPTURE_GUIDANCE_SENTENCE)).toBeInTheDocument();
  });

  it('is not shown again once this browser has seen it', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    await screen.findByLabelText('Transcript');
    expect(screen.queryByText(CAPTURE_GUIDANCE_SENTENCE)).toBeNull();
    expect(screen.getByRole('button', { name: 'Show capture guidance' })).toBeInTheDocument();
  });

  it('says the dismissal is remembered by the browser and not by the server', async () => {
    localStorage.removeItem(CAPTURE_GUIDANCE_KEY);
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    await screen.findByText(/This browser remembers that you have seen this/);
  });

  it('stores no transcript text and no record identifier', async () => {
    localStorage.removeItem(CAPTURE_GUIDANCE_KEY);
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Got it' }));
    const stored = localStorage.getItem(CAPTURE_GUIDANCE_KEY) ?? '';
    expect(Object.keys(JSON.parse(stored)).sort()).toEqual([
      'guidanceId',
      'seen',
      'seenAt',
      'version',
    ]);
    expect(stored).not.toContain(EXP);
    expect(stored).not.toContain('run-1');
  });
});

// --- 7. retention: only what is enforced --------------------------------------

describe('retention', () => {
  it('reports the enforced state and names the ones this build does not offer', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText(/The finalized transcript is stored with this record as notes/);
    expect(screen.getByText(/retain_during_draft/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing here removes a note/)).toBeInTheDocument();
  });

  it('offers no raw-audio retention control, and says why', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText(/No audio reaches this server/);
    expect(screen.queryByLabelText(/audio retention/i)).toBeNull();
  });
});

// --- 8. accessibility ---------------------------------------------------------

describe('accessibility', () => {
  async function violations(container: HTMLElement) {
    const results = await axe.run(container, {
      runOnly: {
        type: 'rule',
        values: [
          'button-name',
          'label',
          'aria-allowed-attr',
          'aria-allowed-role',
          'aria-required-attr',
          'aria-valid-attr-value',
          'select-name',
        ],
      },
      resultTypes: ['violations'],
    });
    return results.violations;
  }

  it('every control is named and every field is labelled', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText('context.temperature_K');
    expect(await violations(container)).toEqual([]);
  });

  it('a failure is announced as an alert, not only coloured', async () => {
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIPT]: { status: 412, body: { error: 'stale_write' } },
    } as never);
    await renderPanel();
    await typeAndFinalize();
    expect(await screen.findByRole('alert')).toHaveTextContent(/NOT stored/);
  });

  it('the recording state is carried by a live region, not by colour', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    await screen.findByLabelText('Transcript');
    const live = container.querySelectorAll('[aria-live="polite"]');
    expect(live.length).toBeGreaterThanOrEqual(1);
  });

  it('an outcome is never distinguished by colour alone', async () => {
    const mixed = reading({
      candidates: [],
      abstentions: [
        {
          outcome: 'abstention',
          kind: 'implicit_only_subject',
          reason: 'No field exists for this in the official record schema.',
          quote: 'Cu K-edge',
          segment_index: 0,
        },
      ],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: mixed } } as never);
    await renderPanel();
    await typeAndFinalize('We measured the Cu K-edge.');
    // A WORD, not a hue. Removing the tag would turn this red.
    const item = (await screen.findByText(/No field exists for this/)).closest('li');
    expect(within(item as HTMLElement).getByText('Not proposed')).toBeInTheDocument();
  });

  it('finalizing announces what happened to the text', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText('context.temperature_K');
    const status = container.querySelector('[role="status"]');
    expect(status?.textContent).toMatch(/1 segment\(s\) stored with this record/);
    // AND WHAT WAS STORED, not only what was read. The two can differ — a candidate
    // the server declined is reported separately — so announcing the read count alone
    // would let the panel imply a store that did not happen.
    expect(status?.textContent).toMatch(/1 value\(s\) read/);
    expect(status?.textContent).toMatch(/1 stored as proposal\(s\) for review/);
  });
});

// --- 6. the panel toggle, and the recorder lifecycle -------------------------
//
// THIS BLOCK EXISTS BECAUSE ITS ABSENCE SHIPPED TWO DEFECTS.
//
// Independent review found both, and neither was reachable by the suite as it
// stood: nothing here ever closed the panel, and jsdom has no `MediaRecorder`,
// so `audioRecordingAvailable()` returned false, `voice` was pinned to
// `'unsupported'`, and every line of the recorder lifecycle — start, stop,
// discard, drop — was dead to the tests. The "no part of this panel claims a
// provider exists" scan was likewise only ever scanning the unsupported branch.

/** The smallest `MediaRecorder` that reproduces the real ordering hazard. */
class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];
  state: 'inactive' | 'recording' = 'inactive';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  constructor(_stream: unknown) {
    FakeMediaRecorder.instances.push(this);
  }
  start() {
    this.state = 'recording';
  }
  /**
   * THE POINT OF THIS FAKE. A real `MediaRecorder` emits its final
   * `dataavailable` ASYNCHRONOUSLY, on a later task — which is exactly how a
   * "discarded" recording used to end up back in the buffer after the live
   * region had already announced it gone. A synchronous fake would not
   * reproduce the defect and the test would pass against the broken code.
   */
  stop() {
    this.state = 'inactive';
    const emit = this.ondataavailable;
    setTimeout(() => emit?.({ data: new Blob(['audio-bytes']) }), 0);
  }
}

describe('the panel toggle and the recorder lifecycle', () => {
  const tracks = { stop: vi.fn() };

  beforeEach(() => {
    FakeMediaRecorder.instances = [];
    tracks.stop.mockClear();
    (globalThis as never as Record<string, unknown>).MediaRecorder = FakeMediaRecorder;
    (globalThis as never as Record<string, unknown>).Blob =
      (globalThis as never as Record<string, unknown>).Blob ?? class {};
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [tracks] })) },
    });
  });

  afterEach(() => {
    delete (globalThis as never as Record<string, unknown>).MediaRecorder;
  });

  it('CLOSING THE PANEL DOES NOT DISCARD TYPED TEXT', async () => {
    // The fourth path the three "text survives" controls missed. The reset
    // effect used to key on `open` and ran its setters BEFORE the `if (!open)`
    // guard, so collapsing the panel — to scroll, or by accident — wiped every
    // word. Finalize had not been pressed, so nothing had reached the server and
    // there was nothing to recover from.
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    const box = await screen.findByLabelText('Transcript');
    fireEvent.change(box, { target: { value: 'Several careful paragraphs.' } });

    fireEvent.click(screen.getByRole('button', { name: /Close capture/i }));
    fireEvent.click(screen.getByRole('button', { name: /Start a capture/i }));

    const reopened = await screen.findByLabelText('Transcript');
    expect((reopened as HTMLTextAreaElement).value).toBe('Several careful paragraphs.');
  });

  it('DISCARDING MID-RECORDING REALLY DISCARDS, even though stop() emits later', async () => {
    // `MediaRecorder.stop()` fires `dataavailable` on a later task. The handler
    // closes over a stable ref, so clearing the buffer and THEN stopping put the
    // complete recording straight back — after the live region had announced
    // "Audio discarded." Nulling the recorder ref does not unbind a handler.
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: /Start recording/i }));
    await waitFor(() => expect(FakeMediaRecorder.instances).toHaveLength(1));

    const recorder = FakeMediaRecorder.instances[0];
    fireEvent.click(screen.getByRole('button', { name: /Discard/i }));

    // The handler must be detached BEFORE the async emission lands.
    expect(recorder.ondataavailable).toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(recorder.ondataavailable).toBeNull();
    // And the microphone was actually released.
    expect(tracks.stop).toHaveBeenCalled();
  });

  it('CLOSING THE PANEL RELEASES THE MICROPHONE', async () => {
    // Closing does not unmount, and Stop/Discard live inside the body that stops
    // rendering — so a hot microphone had no ISAAC-visible control at all.
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: /Start recording/i }));
    await waitFor(() => expect(FakeMediaRecorder.instances).toHaveLength(1));

    fireEvent.click(screen.getByRole('button', { name: /Close capture/i }));
    await waitFor(() => expect(tracks.stop).toHaveBeenCalled());
    expect(FakeMediaRecorder.instances[0].state).toBe('inactive');
  });
});

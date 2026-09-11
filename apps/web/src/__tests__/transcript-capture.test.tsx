/*
 * The Transcript Capture panel.
 *
 * PR-D (2026-09-03) REPLACED THE PANEL'S INSTRUCTION-DOCUMENT-PLUS-CONTROL-PILE WITH
 * A STATE MACHINE — see `TranscriptCapturePanel.tsx`'s own header table. This suite
 * is rewritten to match: sections 2 and 4 below no longer assert a per-candidate
 * list (that UI is gone, replaced by a compact summary card), and new sections cover
 * the voice state machine's five reachable states, the `processing` lock, and the
 * `proposals-ready` summary's own controls.
 *
 * WHAT WOULD FAIL BEFORE THE BEHAVIOUR THESE TESTS DEFEND. Each is a way the panel
 * could be built that renders perfectly and still breaks the feature's promise:
 *
 *   1. A panel that reads while the reader types — a debounce, an `onChange`
 *      handler, an autosave. Authoritative metadata would then move from text
 *      nobody finished. ('typing alone sends nothing', 'finalizing is the only
 *      thing that reads')
 *   2. A panel that clears the transcript box, or hides the stored notes, after a
 *      reading that proposed nothing — leaving a scientist to believe their words
 *      went nowhere. ('text survives a reading that proposed nothing')
 *   3. A voice surface that says "Connected", "Ready", or "Configured", or that
 *      shows a spinner where a refusal belongs. ('no part of this panel claims a
 *      provider exists')
 *   4. A run chosen on the reader's behalf when the record has exactly one.
 *      ('the run is never pre-selected')
 *   5. A `processing` state that lets a second click double-submit, or that leaves
 *      the form editable while a write is in flight.
 *   6. A `proposals-ready` state that keeps rendering the old per-candidate accept/
 *      reject UI PR-A already removed the write path for.
 *
 * Every fixture is synthetic and no test here reaches a backend.
 */
import { describe, it, expect, afterEach, beforeEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
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

const noRunsPage = { ...runsPage, runs: [], total: 0, matched: 0, returned: 0 };

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

/** One entry of the capture's `proposals` list. */
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

// jsdom implements no `scrollIntoView` — a real gap in the test environment, not
// in any browser this ships to. `reviewProposals` calls it unconditionally, so a
// bare click threw `TypeError: heading.scrollIntoView is not a function` and
// crashed React's event handler. Polyfilled here, scoped to this file, rather
// than in the shared setup — no other suite in this repository has needed it yet.
if (typeof Element !== 'undefined' && typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = function scrollIntoViewPolyfill() {
    /* no-op: jsdom has no layout, so there is nothing to scroll */
  };
}

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
  if (vi.isFakeTimers()) vi.useRealTimers();
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
  fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryOpen }));
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
  fireEvent.change(await screen.findByLabelText(CAPTURE_COPY.runLabel), {
    target: { value: 'run-1' },
  });
  fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.finalize }));
}

// --- 1. nothing is read from unfinished text ---------------------------------

describe('C1, independent review of PR-D: the collapsed header names only the path that always works', () => {
  it('the collapsed-header sentence mentions no recording/voice/transcription path, and is visible before the panel is opened', async () => {
    /*
     * Before the fix, `panelIntro` rendered inside the always-visible header
     * AND described recording as an equally-finished path alongside typing —
     * false: finalize posts typed text only, and every deployment's own
     * transcription seam answers 501. A reader who never opens the panel
     * must not be told a claim the panel cannot keep.
     */
    stubFetchRoutes(BASE_ROUTES as never);
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
      </MemoryRouter>,
    );
    // Not opened — the entry toggle is the only interaction so far.
    const intro = await screen.findByText(CAPTURE_COPY.panelIntro);
    expect(intro).toBeInTheDocument();
    const text = intro.textContent ?? '';
    expect(text.toLowerCase()).not.toMatch(/record|voice|transcri|speak|dictat/);
    // Screen.queryByLabelText('Transcript') stays null while collapsed —
    // confirms the sentence really is the COLLAPSED header, not open-body text.
    expect(screen.queryByLabelText('Transcript')).toBeNull();
  });
});

describe('unfinished text', () => {
  it('a closed panel fetches nothing at all', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
      </MemoryRouter>,
    );
    await screen.findByRole('button', { name: CAPTURE_COPY.entryOpen });
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
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    const finalize = writes().filter((entry) => entry.key === TRANSCRIPT);
    expect(finalize).toHaveLength(1);
    expect(finalize[0].body.finalized).toBe(true);
    expect(finalize[0].body.text).toBe('Temperature was 300 K.');
    expect(finalize[0].ifMatch).toBe('"g1.4"');
  });

  it('the finalize control is unavailable while the box is empty', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    expect(await screen.findByRole('button', { name: CAPTURE_COPY.finalize })).toBeDisabled();
  });
});

// --- 2. proposals-ready: the summary card, not the old per-candidate list -----

describe('proposals-ready: what the capture stored', () => {
  it('the panel issues no write but the finalize itself', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    expect(writes().map((entry) => entry.key)).toEqual([TRANSCRIPT]);
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull();
    // AND THE OLD PER-CANDIDATE ROW IS GONE — the whole point of the summary card.
    expect(screen.queryByText('context.temperature_K')).toBeNull();
  });

  it('the summary states both counts and offers Review N Proposals', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    expect(await screen.findByText('1 proposal, 1 note stored with this record.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: CAPTURE_COPY.reviewProposals(1) }),
    ).toBeInTheDocument();
  });

  /*
   * MUTATION 1 — quoted in the slice report. Removing the `proposalsStored > 0`
   * guard around the "Review N Proposals" button would render it reading "Review 0
   * Proposals", which is a control offering to review nothing. This is the negative
   * control for that guard.
   */
  it('MUTATION-GUARDED: Review N Proposals is absent when nothing was stored as a proposal', async () => {
    const nothingProposed = reading({
      candidates: [],
      proposals: [],
      notes: [noteOf('Just an aside, nothing measurable.', 'n1')],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: nothingProposed } } as never);
    await renderPanel();
    await typeAndFinalize('Just an aside, nothing measurable.');
    await screen.findByText(CAPTURE_COPY.candidatesEmpty);
    expect(screen.queryByRole('button', { name: /Review \d+ Proposals?/ })).toBeNull();
  });

  it('an unstored candidate is disclosed with the server’s own message', async () => {
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
    await renderPanel();
    await typeAndFinalize();
    expect(
      await screen.findByText(/No write operation in this build accepts a value at this path/),
    ).toBeInTheDocument();
    expect(screen.getByText(CAPTURE_COPY.summaryUnproposable(1))).toBeInTheDocument();
    // The words are still stored, which is the whole of the promise.
    expect(screen.getAllByText('Temperature was 300 K.').length).toBeGreaterThanOrEqual(1);
  });

  /*
   * MUTATION 2 — quoted in the slice report. Removing the
   * `unproposableCount > 0` guard would render `summaryUnproposable(0)` (or the
   * heading with an empty list) on every fully-stored reading. This reading refuses
   * nothing, so the disclosure and its heading must both be absent.
   */
  it('MUTATION-GUARDED: the unproposable disclosure is absent when nothing was refused', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    expect(screen.queryByText(CAPTURE_COPY.unproposableHeading)).toBeNull();
    expect(screen.queryByText(/could not be stored as a proposal/)).toBeNull();
  });

  it('a proposal is not shown as a value — the nature sentence stays off this panel', async () => {
    // The per-candidate quote/rule breakdown moved with the accept/reject UI to
    // `IngestionProposalsPanel`, which is where a reader now checks a proposal
    // against the words it came from. This panel states counts, not content.
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    expect(screen.queryByText(/A proposal, not a value/)).toBeNull();
  });
});

// --- 3. text is never lost ----------------------------------------------------

describe('nothing a scientist wrote is discarded', () => {
  it('text survives a reading that proposed nothing', async () => {
    const empty = reading({
      candidates: [],
      proposals: [],
      notes: [noteOf('The cryostat rattled.', 'n2')],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: empty } } as never);
    await renderPanel();
    await typeAndFinalize('The cryostat rattled.');
    await screen.findByText(CAPTURE_COPY.candidatesEmpty);
    expect(screen.getAllByText('The cryostat rattled.').length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByLabelText('Transcript')).toHaveValue('The cryostat rattled.');
  });

  /*
   * REGRESSION — found taking this slice's own screenshots. "Capture Another
   * Note" lived inside the `candidates.length > 0` branch, so a reading that
   * proposed nothing (every word stored as a note, nothing recognised as a
   * value — exactly the case above) offered NO way back to a fresh box short of
   * closing and reopening the whole panel. `Review N Proposals` correctly stays
   * absent here — there is nothing to review.
   */
  it('MUTATION-GUARDED: Capture Another Note stays offered even when nothing was proposed', async () => {
    const empty = reading({
      candidates: [],
      proposals: [],
      notes: [noteOf('Just an aside, nothing measurable.', 'n2')],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: empty } } as never);
    await renderPanel();
    await typeAndFinalize('Just an aside, nothing measurable.');
    await screen.findByText(CAPTURE_COPY.candidatesEmpty);

    expect(screen.queryByRole('button', { name: /Review \d+ Proposals?/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.captureAnother }));
    expect(screen.queryByText(CAPTURE_COPY.candidatesEmpty)).toBeNull();
    expect(await screen.findByLabelText('Transcript')).toHaveValue('');
  });

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
    expect(screen.getAllByText('Temperature was 300 K.').length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByLabelText('Transcript')).toHaveValue('Temperature was 300 K.');
  });

  it('a failed finalize says the transcript was not stored, keeps the text, and offers Try Again', async () => {
    let calls = 0;
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIPT]: () => {
        calls += 1;
        return { status: 412, body: { error: 'stale_write' } };
      },
    } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByRole('alert');
    expect(screen.getByRole('alert')).toHaveTextContent(/was NOT stored/);
    expect(await screen.findByLabelText('Transcript')).toHaveValue('Temperature was 300 K.');

    // recoverable-error's own primary action re-invokes the same failed act.
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.tryAgain }));
    await waitFor(() => expect(calls).toBe(2));
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
    const select = await screen.findByLabelText(CAPTURE_COPY.runLabel);
    expect(select).toHaveValue('');
    expect(screen.getByText(/never chosen for you, even when the record has exactly one run/)).toBeInTheDocument();
  });

  it('a clarification is rendered as a question with its alternatives', async () => {
    const asked = reading({
      candidates: [],
      proposals: [],
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
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
  });

  it('an abstention states the subject and the reason, and proposes nothing', async () => {
    const abstained = reading({
      candidates: [],
      proposals: [],
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

  it('two values for one field are BOTH stored, with the contradiction stated', async () => {
    // The per-candidate "Both are stored"/"only the labelled rows" copy moved with
    // the row it annotated. The contradiction itself is still disclosed, directly,
    // through `review_required` — unchanged mechanism, unchanged section.
    const conflicted = reading({
      candidates: [candidate(), candidate({ proposed_value: 320, quote: 'Later the temperature was 320 K.', start_char: 23 })],
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
    await screen.findByText('2 proposals, 1 note stored with this record.');
    // The reason sits beside a `<strong>field_path</strong>` inside its own `<li>`,
    // so its OWN text (RTL's `getByText` unit) is only the trailing fragment —
    // asserted against the row's full text instead of via `getByText`.
    const row = screen.getByText('context.temperature_K').closest('li');
    expect(row?.textContent).toContain('Accept at most one.');
    expect(
      screen.getByRole('button', { name: CAPTURE_COPY.reviewProposals(2) }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
  });
});

// --- 5. the voice surface claims nothing --------------------------------------

describe('voice capture: honesty', () => {
  it('no part of this panel claims a provider exists', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    const text = (container.textContent ?? '').toLowerCase();
    for (const banned of [
      'connected',
      'ready to transcribe',
      'provider configured',
      'temporarily',
      'coming soon',
      'not yet available',
    ]) {
      expect(text).not.toContain(banned);
    }
  });

  it('the seam status is rendered from the server, not from this bundle', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    await screen.findByText(/No transcription provider is configured\. Speech is not transcribed/);
  });

  it('the seam line still renders when the capability report never arrives', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [CAPS]: { status: 503, body: { detail: 'no' } } } as never);
    const { container } = await renderPanel();
    const seam = await waitFor(() => {
      const el = container.querySelector('.capture-seam');
      if (!el) throw new Error('no seam line rendered');
      return el as HTMLElement;
    });
    expect(seam.getAttribute('data-configured')).toBe('unreported');
    expect(seam.textContent).toMatch(/not reported/i);
    expect(seam.textContent).not.toMatch(/no transcription provider is configured/i);
  });

  it('no request this panel makes carries audio', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    for (const entry of writes()) {
      expect(Object.keys(entry.body)).not.toContain('audio');
      expect(Object.keys(entry.body)).not.toContain('audio_data');
    }
    expect(requests().some((key) => key.includes('/uploads'))).toBe(false);
  });
});

// --- 6. the voice STATE MACHINE ------------------------------------------------
//
// jsdom has no `MediaRecorder`, so every test that needs `recording`/`held`/
// `requesting-permission`/`permission-denied` installs `FakeMediaRecorder` first.
// Without it, `voice` is pinned to `unsupported` — which is its own state below.

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
  /** `stop()` emits its final `dataavailable` ASYNCHRONOUSLY — see `dropAudio`'s
   *  own comment in the panel for the ordering hazard this reproduces. */
  stop() {
    this.state = 'inactive';
    const emit = this.ondataavailable;
    setTimeout(() => emit?.({ data: new Blob(['audio-bytes']) }), 0);
  }
}

/**
 * OBJECT-URL BOOKKEEPING, installed beside the recorder double rather than as a
 * second one — jsdom implements NEITHER `URL.createObjectURL` nor
 * `URL.revokeObjectURL`, so without this the playback effect's own
 * `typeof URL.createObjectURL !== 'function'` guard would short-circuit and
 * every playback assertion below would pass vacuously by never running the
 * code it is about.
 *
 * BOTH SIDES ARE RECORDED, because the create is the easy half. A leak is a URL
 * created and never revoked, and only `revoked` can see that.
 *
 * INSTALLED AT MODULE SCOPE, NOT TORN DOWN IN `afterEach` — and that is a
 * correction, not a shortcut. Deleting these in an `afterEach` beside the
 * `MediaRecorder` teardown made TWELVE tests fail with `URL.revokeObjectURL is
 * not a function`: testing-library's own auto-`cleanup` hook unmounts the tree
 * AFTER this file's hooks run, so the component's revoke-on-unmount reached a
 * global that had already been removed. A real browser never withdraws these
 * two mid-teardown, so neither does this double.
 */
const objectUrls: { created: string[]; revoked: string[] } = { created: [], revoked: [] };
let objectUrlsMinted = 0;

(URL as unknown as Record<string, unknown>).createObjectURL = () => {
  objectUrlsMinted += 1;
  const url = `blob:isaac-test/${objectUrlsMinted}`;
  objectUrls.created.push(url);
  return url;
};
(URL as unknown as Record<string, unknown>).revokeObjectURL = (url: string) => {
  objectUrls.revoked.push(url);
};

function installRecorder(getUserMedia: Mock) {
  FakeMediaRecorder.instances = [];
  (globalThis as never as Record<string, unknown>).MediaRecorder = FakeMediaRecorder;
  (globalThis as never as Record<string, unknown>).Blob =
    (globalThis as never as Record<string, unknown>).Blob ?? class {};
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  });
  objectUrls.created = [];
  objectUrls.revoked = [];
}

afterEach(() => {
  delete (globalThis as never as Record<string, unknown>).MediaRecorder;
});

describe('voice state machine', () => {
  it('unsupported: voice controls are absent and only typing is offered', async () => {
    // jsdom's own baseline — no installRecorder() call in this test.
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    await screen.findByText(/This browser does not offer audio recording/);
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceRecord })).toBeNull();
    expect(await screen.findByLabelText('Transcript')).toBeInTheDocument();
  });

  it('idle: Start Recording is the one primary action, and the live region says so', async () => {
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord });
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceStop })).toBeNull();
    const live = container.querySelectorAll('[aria-live="polite"]');
    expect(Array.from(live).some((el) => el.textContent === CAPTURE_COPY.voiceIdleLive)).toBe(true);
  });

  it('requesting-permission: Start becomes disabled and busy-labeled; typing stays live', async () => {
    let resolveGetUserMedia: (v: unknown) => void = () => {};
    const gate = new Promise((resolve) => {
      resolveGetUserMedia = resolve;
    });
    installRecorder(vi.fn(() => gate));
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));

    const busyButton = await screen.findByRole('button', { name: CAPTURE_COPY.voiceRequesting });
    expect(busyButton).toBeDisabled();
    expect(busyButton).toHaveAttribute('aria-busy', 'true');
    const live = container.querySelectorAll('[aria-live="polite"]');
    expect(
      Array.from(live).some((el) => el.textContent === CAPTURE_COPY.voiceRequestingLive),
    ).toBe(true);
    // The textarea is never blocked by an in-flight permission prompt.
    const box = await screen.findByLabelText('Transcript');
    expect(box).not.toBeDisabled();
    fireEvent.change(box, { target: { value: 'typed while requesting' } });
    expect(box).toHaveValue('typed while requesting');

    await act(async () => {
      resolveGetUserMedia({ getTracks: () => [{ stop: vi.fn() }] });
      await Promise.resolve();
    });
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop });
  });

  it('recording: elapsed time ticks, and on stop the bar says HELD rather than vanishing', async () => {
    /*
     * FAKE TIMERS ARE ENABLED BEFORE THE CLICK, and everything after is driven by
     * explicit `act()`/`advanceTimersByTimeAsync` rather than `findBy*`/`waitFor`
     * — the same discipline `run-workspace.test.tsx` documents ("everything AFTER
     * `vi.useFakeTimers()` … is driven by explicit `advanceTimersByTimeAsync`").
     * The timer under test (`startElapsedTimer`'s `setInterval`) is created the
     * instant `recording` is entered, so it must already be bound to the FAKE
     * clock when that happens — enabling fake timers only afterward binds the
     * interval to the real one, and `advanceTimersByTimeAsync` then advances a
     * clock nothing is listening to (measured: the elapsed text stayed `0:00`).
     */
    vi.useFakeTimers();
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceStop })).toBeInTheDocument();
    // m5: not `aria-hidden` and prefixed with the state, so a screen reader that
    // navigates here (rather than catching the one-shot live announcement) still
    // gets both facts.
    const elapsed = container.querySelector('.capture-elapsed');
    expect(elapsed).not.toHaveAttribute('aria-hidden');
    /*
     * THE EXACT TEXT IS A CONTRACT WITH A SPEC THIS FILE CANNOT SEE.
     * `e2e/mutation/capture-microphone.spec.ts` asserts `Recording · 0:01`
     * (`:901`), matches `/Recording · (?!0:00)\d+:\d\d/` (`:774`) and parses
     * `/(\d+):(\d\d)\s*$/` off this element's `innerText` (`:510`). The 2026-09-10
     * bar redesign splits the state and the time into two differently-sized
     * spans; asserting the concatenation here is what proves the split changed
     * no character of the text those three depend on.
     */
    expect(elapsed?.textContent).toBe('Recording · 0:00');
    // The state word and the time are separately addressable, so the time can be
    // set large without touching the string above.
    expect(container.querySelector('.capture-elapsed-state')?.textContent).toBe('Recording');
    expect(container.querySelector('.capture-elapsed-time')?.textContent).toBe('0:00');
    expect(container.querySelector('.capture-live')?.getAttribute('data-state')).toBe('recording');
    // The mark carries no information a sighted reader does not also get from
    // the word beside it, which is the whole basis for hiding it.
    expect(container.querySelector('.capture-live-mark')).toHaveAttribute('aria-hidden', 'true');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(container.querySelector('.capture-elapsed')?.textContent).toBe('Recording · 0:05');

    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceStop }));
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceTypeWhatWasSaid })).toBeInTheDocument();
    /*
     * THIS ASSERTION USED TO READ `toBeNull()`, AND THE BEHAVIOUR IT PINNED WAS
     * THE DEFECT. On Stop the elapsed indicator disappeared and NOTHING VISIBLE
     * said audio was still held — the only statement was the `sr-only` live
     * region, so a screen-reader user was better informed than a sighted one.
     * The bar now persists, says `Held`, and keeps the duration; the clock has
     * stopped, which is what the unchanged `0:05` five seconds later proves.
     */
    expect(container.querySelector('.capture-live')?.getAttribute('data-state')).toBe('held');
    expect(container.querySelector('.capture-elapsed')?.textContent).toBe('Held · 0:05');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(container.querySelector('.capture-elapsed')?.textContent).toBe('Held · 0:05');
    vi.useRealTimers();
  });

  it('held: Type What Was Said is primary; Request a Transcript and Discard Audio are offered', async () => {
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));

    const typeButton = await screen.findByRole('button', { name: CAPTURE_COPY.voiceTypeWhatWasSaid });
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceTranscribe })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceDiscard })).toBeInTheDocument();

    const box = screen.getByLabelText('Transcript') as HTMLTextAreaElement;
    box.blur();
    fireEvent.click(typeButton);
    expect(document.activeElement).toBe(box);
  });

  /*
   * I8, INDEPENDENT REVIEW OF PR-D — FOUR BRANCHES, EACH ITS OWN TEST, EACH
   * CLASSIFIED BY THE REAL `DOMException.name` A BROWSER ACTUALLY THROWS.
   * Note also I8's SECOND requirement, pinned once for all four here rather
   * than per-branch: the persistent notice is PLAIN TEXT, never a second live
   * region — `role="alert"` carries an implicit `aria-live="assertive"`, and
   * the one announcement already happened through the sr-only status region.
   */
  const denialCases: {
    name: string;
    domName: string;
    copy: string;
  }[] = [
    { name: 'NotAllowedError → denied', domName: 'NotAllowedError', copy: CAPTURE_COPY.voicePermissionRefused },
    { name: 'NotFoundError → no microphone', domName: 'NotFoundError', copy: CAPTURE_COPY.voiceNoMicrophone },
    { name: 'OverconstrainedError → no microphone', domName: 'OverconstrainedError', copy: CAPTURE_COPY.voiceNoMicrophone },
    { name: 'NotReadableError → microphone busy', domName: 'NotReadableError', copy: CAPTURE_COPY.voiceMicrophoneBusy },
    { name: 'an unnamed/unrecognised DOMException → generic, names no cause', domName: 'SomeFutureError', copy: CAPTURE_COPY.voiceStartFailed },
  ];

  for (const { name, domName, copy } of denialCases) {
    it(`permission-denied (${name}): the right sentence, said once, and never a second live region`, async () => {
      installRecorder(vi.fn(async () => {
        throw new DOMException('synthetic, for this test only', domName);
      }));
      stubFetchRoutes(BASE_ROUTES as never);
      const { container } = await renderPanel();
      await act(async () => {
        fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
        await Promise.resolve();
      });

      // Persistent, visible text — and NOT a live region: `role="alert"` would
      // be a SECOND announcement of the same sentence the status region (below)
      // already made once. Queried by class, not text: the sr-only status
      // region carries the identical sentence, so `findByText` alone would see
      // two matches.
      const notice = await waitFor(() => {
        const el = container.querySelector('.capture-note-warn');
        if (el === null) throw new Error('persistent notice not rendered yet');
        return el;
      });
      expect(notice.textContent).toBe(copy);
      expect(notice.tagName).toBe('P');
      expect(notice).not.toHaveAttribute('role');
      expect(notice).not.toHaveAttribute('aria-live');

      expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceTypeWhatWasSaid })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceTryAgain })).toBeInTheDocument();

      // The ONE announcement, in the ordinary status region, is the SAME sentence.
      const live = container.querySelectorAll('[role="status"]');
      expect(Array.from(live).some((el) => el.textContent === copy)).toBe(true);
      // No `role="alert"` anywhere on this card — the second-live-region defect.
      expect(container.querySelectorAll('[role="alert"]').length).toBe(0);

      // Still there after a delay — it is a state, not a one-shot toast.
      await new Promise((resolve) => setTimeout(resolve, 20));
      expect(container.querySelector('.capture-note-warn')?.textContent).toBe(copy);
    });
  }

  it('held: a transcription refusal is rendered from the server’s own words', async () => {
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
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
    await renderPanel();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceTranscribe }));

    expect(
      await screen.findByText('This build cannot transcribe speech: no provider is configured.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('an approved transcription provider (decision D9)'),
    ).toBeInTheDocument();
    // Audio stays held — a refusal to transcribe is not a discard.
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceDiscard })).toBeInTheDocument();
  });

  it('duplicate Start is prevented — a second click while requesting starts no second recorder', async () => {
    let resolveGetUserMedia: (v: unknown) => void = () => {};
    const gate = new Promise((resolve) => {
      resolveGetUserMedia = resolve;
    });
    const getUserMedia = vi.fn(() => gate);
    installRecorder(getUserMedia);
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    const start = await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord });
    fireEvent.click(start);
    // The control that would fire a second `getUserMedia` no longer renders in
    // `requesting-permission` — this IS the duplicate-session guard.
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceRecord })).toBeNull();
    await act(async () => {
      resolveGetUserMedia({ getTracks: () => [{ stop: vi.fn() }] });
      await Promise.resolve();
    });
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  it('unmount mid-recording stops tracks', async () => {
    const stop = vi.fn();
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    const rendered = await renderPanel();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop });
    rendered.unmount();
    expect(stop).toHaveBeenCalled();
  });

  it('the elapsed timer is cleared on unmount, not left running', async () => {
    const clearSpy = vi.spyOn(window, 'clearInterval');
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    const rendered = await renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop });
    const callsBefore = clearSpy.mock.calls.length;
    rendered.unmount();
    expect(clearSpy.mock.calls.length).toBeGreaterThan(callsBefore);
  });
});

// --- 7. `processing` locks the form and prevents a double submit --------------

describe('processing: the finalize lock', () => {
  it('the disabled attribute stops an ordinary second click', async () => {
    const gateHandle: { resolve: (() => void) | null } = { resolve: null };
    const gate = new Promise<void>((resolve) => {
      gateHandle.resolve = () => resolve();
    });
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIPT]: async () => {
        await gate;
        return { body: reading() };
      },
    } as never);
    await renderPanel();
    const box = await screen.findByLabelText('Transcript');
    fireEvent.change(box, { target: { value: 'Temperature was 300 K.' } });
    fireEvent.change(await screen.findByLabelText(CAPTURE_COPY.runLabel), {
      target: { value: 'run-1' },
    });
    const finalizeButton = screen.getByRole('button', { name: CAPTURE_COPY.finalize });
    fireEvent.click(finalizeButton);
    fireEvent.click(finalizeButton);
    fireEvent.click(finalizeButton);

    const busyButton = await screen.findByRole('button', { name: /Reading/ });
    expect(busyButton).toBeDisabled();
    expect(busyButton).toHaveAttribute('aria-busy', 'true');
    // The rest of the form is locked too — a run select and a textarea a reader
    // could otherwise edit mid-submit.
    expect(box).toBeDisabled();
    expect(screen.getByLabelText(CAPTURE_COPY.runLabel)).toBeDisabled();

    gateHandle.resolve?.();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    expect(writes().filter((entry) => entry.key === TRANSCRIPT)).toHaveLength(1);
  });

  /*
   * I3a, INDEPENDENT REVIEW OF PR-D — THE TEST ABOVE PROVED THE WRONG THING.
   * `fireEvent.click` on a `disabled` DOM button never dispatches, in jsdom or
   * in a real browser — so that test passes even with the
   * `if (busyKind !== null …) return;` guard DELETED from `finalize()`
   * entirely: the disabled attribute alone was already stopping every
   * repeated click. This test bypasses the button altogether and dispatches
   * `submit` directly on the `<form>` — which `finalize()`'s own `onSubmit`
   * calls regardless of any button's disabled state, exactly as a stray
   * re-entrant call or a double Enter-press would — so the GUARD ITSELF, not
   * the disabled attribute, is what is under test.
   *
   * MUTATION-GUARDED: delete `if (busyKind !== null || text.trim() === '')
   * return;` from `finalize()` and this turns red (two POSTs instead of one).
   */
  it('MUTATION-GUARDED: the in-flight guard inside finalize() itself stops a second submit, bypassing the disabled button', async () => {
    const gateHandle: { resolve: (() => void) | null } = { resolve: null };
    const gate = new Promise<void>((resolve) => {
      gateHandle.resolve = () => resolve();
    });
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIPT]: async () => {
        await gate;
        return { body: reading() };
      },
    } as never);
    const { container } = await renderPanel();
    const box = await screen.findByLabelText('Transcript');
    fireEvent.change(box, { target: { value: 'Temperature was 300 K.' } });
    fireEvent.change(await screen.findByLabelText(CAPTURE_COPY.runLabel), {
      target: { value: 'run-1' },
    });

    const form = container.querySelector('form.capture-form');
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);
    // A SECOND submit, still gated — the button is disabled by now, but this
    // never touches the button.
    fireEvent.submit(form as HTMLFormElement);
    fireEvent.submit(form as HTMLFormElement);

    gateHandle.resolve?.();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    expect(writes().filter((entry) => entry.key === TRANSCRIPT)).toHaveLength(1);
  });
});

// --- 7b. I1 — Try Again re-invokes the CURRENT action, never a stale closure ---

describe('I1: Try Again dispatches through a tag, never a captured closure', () => {
  it('MUTATION-GUARDED: a 412 → edited text → Try Again sends the NEW version AND the NEW text', async () => {
    /*
     * THE DEFECT THIS GUARDS. `setRetry(() => finalize)` used to capture
     * `experimentVersion` and `text` AT THE MOMENT OF FAILURE. A 412 already
     * calls `loadRuns()` to adopt the record's current version — so the very
     * next "Try Again" re-sent the OLD, already-known-stale version and was
     * refused again, FOREVER, and separately re-sent whatever was typed at
     * failure time, silently discarding any edit made afterwards. Both halves
     * are asserted below: the second attempt's `If-Match` is the version
     * `loadRuns()` adopted, and its body is the text typed AFTER the failure,
     * not before it.
     */
    let transcriptAttempts = 0;
    let runsReads = 0;
    stubFetchRoutes({
      [RUNS]: () => {
        runsReads += 1;
        return { body: { ...runsPage, experiment_version: runsReads === 1 ? 'g1.4' : 'g2.0' } };
      },
      [CAPS]: { body: capabilities },
      [TRANSCRIPT]: () => {
        transcriptAttempts += 1;
        if (transcriptAttempts === 1) {
          return { status: 412, body: { error: 'stale_write', current_version: 'g2.0' } };
        }
        return { body: reading({ experiment_version: 'g2.1' }) };
      },
    } as never);
    await renderPanel();
    await typeAndFinalize('The FIRST, stale text.');
    await screen.findByRole('alert');
    // The 412 handler's own `loadRuns()` — the second RUNS read, adopting g2.0.
    await waitFor(() => expect(runsReads).toBe(2));

    fireEvent.change(await screen.findByLabelText('Transcript'), {
      target: { value: 'The SECOND, corrected text.' },
    });
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.tryAgain }));

    await waitFor(() => expect(transcriptAttempts).toBe(2));
    const finalizeCalls = writes().filter((entry) => entry.key === TRANSCRIPT);
    expect(finalizeCalls).toHaveLength(2);
    expect(finalizeCalls[1].ifMatch).toBe('"g2.0"');
    expect(finalizeCalls[1].body.text).toBe('The SECOND, corrected text.');
  });
});

// --- 7c. I2 — exactly one primary action per state ----------------------------

describe('I2: exactly one .btn-primary is ever visible', () => {
  function primaries(container: HTMLElement): HTMLElement[] {
    return Array.from(container.querySelectorAll('.btn-primary'));
  }

  it('collapsed: the entry action is the only primary', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
      </MemoryRouter>,
    );
    await screen.findByRole('button', { name: CAPTURE_COPY.entryOpen });
    const found = primaries(container);
    expect(found).toHaveLength(1);
    expect(found[0].textContent).toBe(CAPTURE_COPY.entryOpen);
  });

  it('MUTATION-GUARDED: open, idle, empty box — Start Recording is the only primary; Close Capture and Finalize are secondary', async () => {
    /*
     * MEASURED BEFORE THIS FIX: `idle` rendered THREE `.btn-primary` at once
     * (the entry toggle, Start Recording, and Finalize and Read). Reverting
     * the entry toggle's class to an unconditional `btn btn-primary` — its
     * shape before I2 — turns this test's length assertion red (2, not 1).
     */
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord });
    const found = primaries(container);
    expect(found).toHaveLength(1);
    expect(found[0].textContent).toBe(CAPTURE_COPY.voiceRecord);
    expect(screen.getByRole('button', { name: CAPTURE_COPY.entryClose })).toHaveClass(
      'btn-secondary',
    );
    expect(screen.getByRole('button', { name: CAPTURE_COPY.finalize })).toHaveClass(
      'btn-secondary',
    );
  });

  it('open, idle, WITH text typed — Start Recording still wins; Finalize stays secondary until nothing else claims the slot', async () => {
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    fireEvent.change(await screen.findByLabelText('Transcript'), {
      target: { value: 'Some notes, not yet recorded or sent.' },
    });
    const found = primaries(container);
    expect(found).toHaveLength(1);
    expect(found[0].textContent).toBe(CAPTURE_COPY.voiceRecord);
  });

  it('unsupported browser, WITH text — Finalize becomes primary, because no voice control competes for the slot', async () => {
    // jsdom's own baseline has no `MediaRecorder` — no `installRecorder()` call.
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    await screen.findByText(/This browser does not offer audio recording/);
    fireEvent.change(await screen.findByLabelText('Transcript'), {
      target: { value: 'Typed, on a browser with no recorder.' },
    });
    const found = primaries(container);
    expect(found).toHaveLength(1);
    expect(found[0].textContent).toBe(CAPTURE_COPY.finalize);
  });

  it('recording: Stop Recording is the only primary', async () => {
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop });
    const found = primaries(container);
    expect(found).toHaveLength(1);
    expect(found[0].textContent).toBe(CAPTURE_COPY.voiceStop);
  });

  it('held: Type What Was Said is the only primary; Request a Transcript and Discard Audio are secondary', async () => {
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceTypeWhatWasSaid });
    const found = primaries(container);
    expect(found).toHaveLength(1);
    expect(found[0].textContent).toBe(CAPTURE_COPY.voiceTypeWhatWasSaid);
  });

  it('processing: only the busy Finalize button is primary, even though voice is concurrently idle', async () => {
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    const gateHandle: { resolve: (() => void) | null } = { resolve: null };
    const gate = new Promise<void>((resolve) => {
      gateHandle.resolve = () => resolve();
    });
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIPT]: async () => {
        await gate;
        return { body: reading() };
      },
    } as never);
    const { container } = await renderPanel();
    fireEvent.change(await screen.findByLabelText('Transcript'), {
      target: { value: 'Temperature was 300 K.' },
    });
    fireEvent.change(await screen.findByLabelText(CAPTURE_COPY.runLabel), {
      target: { value: 'run-1' },
    });
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.finalize }));
    await screen.findByRole('button', { name: /Reading/ });

    const found = primaries(container);
    expect(found).toHaveLength(1);
    expect(found[0].textContent).toMatch(/Reading/);
    // `voice` is still `idle` throughout — `formLocked` alone must demote it.
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceRecord })).toHaveClass(
      'btn-secondary',
    );
    gateHandle.resolve?.();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
  });

  it('proposals-ready, with proposals stored: Review N Proposals is the only primary; Capture Another Note is secondary', async () => {
    // A recorder is installed deliberately so the voice control is genuinely
    // `idle` (and therefore assertable below as demoted to secondary) rather
    // than `unsupported` (which renders no "Start Recording" button at all).
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    const found = primaries(container);
    expect(found).toHaveLength(1);
    expect(found[0].textContent).toBe(CAPTURE_COPY.reviewProposals(1));
    expect(screen.getByRole('button', { name: CAPTURE_COPY.captureAnother })).toHaveClass(
      'btn-secondary',
    );
    // The voice control, still `idle`, is ALSO demoted now that reading owns the slot.
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceRecord })).toHaveClass(
      'btn-secondary',
    );
  });

  it('proposals-ready, nothing proposed: Capture Another Note becomes primary — there is no Review control to compete with it', async () => {
    const empty = reading({ candidates: [], proposals: [], notes: [] });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: empty } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.candidatesEmpty);
    const found = primaries(container);
    expect(found).toHaveLength(1);
    expect(found[0].textContent).toBe(CAPTURE_COPY.captureAnother);
  });

  it('recoverable-error: Try Again is the only primary, even though the voice state would otherwise claim the slot', async () => {
    // A recorder is installed deliberately, so `voice` is genuinely `idle`
    // (and would otherwise show its own primary) rather than `unsupported`
    // (which shows none) — this is the case the error must actually override.
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIPT]: { status: 412, body: { error: 'stale_write' } },
    } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByRole('alert');
    const found = primaries(container);
    expect(found).toHaveLength(1);
    expect(found[0].textContent).toBe(CAPTURE_COPY.tryAgain);
    // `voice` is `idle` throughout this failure — it must not also be primary.
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceRecord })).toHaveClass(
      'btn-secondary',
    );
  });
});

// --- 8. `proposals-ready`'s own controls ---------------------------------------

describe('proposals-ready controls', () => {
  it('Review N Proposals moves focus to the Ingestion Proposals heading', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
        {/* Stands in for `IngestionProposalsPanel`'s own heading, which lives
            directly below this panel on every screen this app mounts it on. */}
        <h2 id="ingestion-proposals-heading" tabIndex={-1}>
          Ingestion Proposals
        </h2>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryOpen }));
    await typeAndFinalize();
    fireEvent.click(
      await screen.findByRole('button', { name: CAPTURE_COPY.reviewProposals(1) }),
    );
    await waitFor(() =>
      expect(document.activeElement?.id).toBe('ingestion-proposals-heading'),
    );
  });

  /*
   * m6, INDEPENDENT REVIEW OF PR-D — `reviewProposals` MUST NEVER BE A DEAD
   * CONTROL. The two tests below drive the FALLBACK paths directly: no
   * `IngestionProposalsPanel` mounted at all, and a `.proposals-section` with
   * no heading (a layout this component does not control but must still not
   * silently fail against). The REAL `IngestionProposalsPanel` end-to-end case
   * — the one I4 asks for — lives in
   * `transcript-to-proposals-integration.test.tsx`, where it is exercised
   * against the genuine component and its genuine `tabIndex={-1}` heading,
   * not a stand-in.
   */
  it('m6: with no Ingestion Proposals surface anywhere, Review N Proposals announces truthfully instead of doing nothing', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    fireEvent.click(
      await screen.findByRole('button', { name: CAPTURE_COPY.reviewProposals(1) }),
    );
    const status = container.querySelector('[role="status"]');
    await waitFor(() =>
      expect(status?.textContent).toMatch(/Ingestion Proposals could not be located/),
    );
    expect(status?.textContent).toMatch(/Your proposals are still stored/);
  });

  it('m6: falls back to the proposals SECTION by class when the heading itself is missing', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
        {/* A section with no heading — the id-based lookup must miss, and the
            class-based fallback must still find this. */}
        <section className="proposals-section" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryOpen }));
    await typeAndFinalize();
    fireEvent.click(
      await screen.findByRole('button', { name: CAPTURE_COPY.reviewProposals(1) }),
    );
    await screen.findByText(/scrolled to the proposals section instead/);
  });

  it('Capture Another Note clears the summary and the box without touching stored notes/proposals', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.captureAnother }));
    expect(screen.queryByText(CAPTURE_COPY.summaryStored(1, 1))).toBeNull();
    expect(await screen.findByLabelText('Transcript')).toHaveValue('');
    // No request was issued by clearing the screen — nothing was un-stored.
    expect(writes().filter((entry) => entry.key === TRANSCRIPT)).toHaveLength(1);
  });

  it('Discard This Transcript stays reachable and scoped to the typed text only', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    await renderPanel();
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    fireEvent.click(screen.getByRole('button', { name: /Discard this transcript/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(await screen.findByLabelText('Transcript')).toHaveValue('');
    // The summary is untouched — this control never reaches what was stored.
    expect(screen.getByText(CAPTURE_COPY.summaryStored(1, 1))).toBeInTheDocument();
  });
});

// --- 9. the run selector's own empty state -------------------------------------

describe('the run selector empty state', () => {
  it('shows Create a Run only when the record has zero runs, as the selector’s own empty state', async () => {
    stubFetchRoutes({ ...BASE_ROUTES, [RUNS]: { body: noRunsPage } } as never);
    const { container } = await renderPanel();
    const empty = await waitFor(() => {
      const el = container.querySelector('.capture-run-empty');
      if (!el) throw new Error('run-empty state not rendered yet');
      return el as HTMLElement;
    });
    // The sentence spans a sibling `<button>`, so it is asserted against the
    // paragraph's full text rather than via `getByText`, which matches only an
    // element's OWN (non-nested) text content.
    expect(empty.textContent).toContain(CAPTURE_COPY.runEmptyPrefix);
    expect(empty.textContent).toContain(CAPTURE_COPY.runEmptySuffix);
    expect(screen.queryByLabelText(CAPTURE_COPY.runLabel)).toBeNull();
    expect(screen.getByRole('button', { name: CAPTURE_COPY.runCreate })).toBeInTheDocument();
  });

  it('the run selector renders normally, with no permanent Create a Run button, once a run exists', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    expect(await screen.findByLabelText(CAPTURE_COPY.runLabel)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.runCreate })).toBeNull();
  });

  it('announces which run proposals from this capture will target', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    expect(await screen.findByText(CAPTURE_COPY.runTargetsNone)).toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText(CAPTURE_COPY.runLabel), {
      target: { value: 'run-1' },
    });
    expect(await screen.findByText(CAPTURE_COPY.runTargetsRun('Run 1'))).toBeInTheDocument();
  });
});

// --- 10. first-use guidance ----------------------------------------------------

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
    fireEvent.click(screen.getByRole('button', { name: 'Show capture guidance' }));
    expect(screen.getByText(CAPTURE_GUIDANCE_SENTENCE)).toBeInTheDocument();
  });

  it('is closed by default once this browser has seen it — the steady state', async () => {
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
});

// --- 11. retention: only what is enforced --------------------------------------

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

// --- 12. accessibility ---------------------------------------------------------

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
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
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
      proposals: [],
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
    const item = (await screen.findByText(/No field exists for this/)).closest('li');
    expect(within(item as HTMLElement).getByText('Not proposed')).toBeInTheDocument();
  });

  it('finalizing announces BOTH numbers — read and stored — pointing at Proposals below', async () => {
    /*
     * I7, INDEPENDENT REVIEW OF PR-D: the announcement used to name only what
     * was STORED, dropping the READ count the build this replaces always
     * said. `reading()`'s fixture carries one candidate and one stored
     * proposal, so "1 value(s) read" and "1 stored as proposal(s)" are the
     * same number here — the negative-count test below is what actually
     * proves the two are tracked separately rather than one being echoed as
     * the other.
     */
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: reading() } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    const status = container.querySelector('[role="status"]');
    expect(status?.textContent).toMatch(/1 segment\(s\) stored with this record/);
    expect(status?.textContent).toMatch(/1 value\(s\) read/);
    expect(status?.textContent).toMatch(/1 stored as proposal\(s\)/);
    expect(status?.textContent).toMatch(/Review them in Ingestion Proposals below/);
  });

  it('MUTATION-GUARDED: the read and stored counts differ when a candidate could not be stored, and the announcement says both', async () => {
    const halfStored = reading({
      proposals: [],
      unproposable: [
        {
          candidate_index: 0,
          field_path: 'context.temperature_K',
          note_id: 'n1',
          error: 'too_many_proposals',
          message: 'This record already holds the maximum number of proposals.',
        },
      ],
    });
    stubFetchRoutes({ ...BASE_ROUTES, [TRANSCRIPT]: { body: halfStored } } as never);
    const { container } = await renderPanel();
    await typeAndFinalize();
    await screen.findByText(/already holds the maximum number of proposals/);
    const status = container.querySelector('[role="status"]');
    expect(status?.textContent).toMatch(/1 value\(s\) read/);
    expect(status?.textContent).toMatch(/0 stored as proposal\(s\)/);
    // NOTHING was stored — the announcement must not direct a reader to an
    // empty Ingestion Proposals destination.
    expect(status?.textContent).not.toMatch(/Review them in Ingestion Proposals below/);
  });
});

// --- 13. the panel toggle, and the recorder lifecycle -------------------------

describe('the panel toggle and the recorder lifecycle', () => {
  const tracks = { stop: vi.fn() };

  beforeEach(() => {
    FakeMediaRecorder.instances = [];
    tracks.stop.mockClear();
    installRecorder(vi.fn(async () => ({ getTracks: () => [tracks] })));
  });

  it('CLOSING THE PANEL DOES NOT DISCARD TYPED TEXT', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    const box = await screen.findByLabelText('Transcript');
    fireEvent.change(box, { target: { value: 'Several careful paragraphs.' } });

    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryClose }));
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryOpen }));

    const reopened = await screen.findByLabelText('Transcript');
    expect((reopened as HTMLTextAreaElement).value).toBe('Several careful paragraphs.');
  });

  it('DISCARDING MID-RECORDING REALLY DISCARDS, even though stop() emits later', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    await waitFor(() => expect(FakeMediaRecorder.instances).toHaveLength(1));
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));

    const recorder = FakeMediaRecorder.instances[0];
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceDiscard }));

    expect(recorder.ondataavailable).toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(recorder.ondataavailable).toBeNull();
    expect(tracks.stop).toHaveBeenCalled();
  });

  it('CLOSING THE PANEL RELEASES THE MICROPHONE', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    await waitFor(() => expect(FakeMediaRecorder.instances).toHaveLength(1));

    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryClose }));
    await waitFor(() => expect(tracks.stop).toHaveBeenCalled());
    expect(FakeMediaRecorder.instances[0].state).toBe('inactive');
  });
});

// --- 14. LEAVING A RECORD: WHICH MECHANISM ACTUALLY DOES IT ------------------
//
// READ THIS BEFORE ADDING A TEST HERE, because the section's original premise
// was measured FALSE in a real browser and the correction is the useful part.
//
// CLAIMED: `RecordWorkbench` renders `<TranscriptCapturePanel experimentId={id} />`
// with no `key` under a single `/record/:id` route, therefore an in-app record
// switch re-uses this component instance and leaves a live microphone behind.
//
// MEASURED (real Chromium, instrumented `MediaStreamTrack.prototype.stop`, real
// fake audio device — `apps/web/e2e/mutation/capture-microphone.spec.ts`):
// `RecordWorkbench.tsx:397-412` renders the panel ONLY while
// `bundle.status === 'data'`. A switch refetches, status goes `'loading'`, the
// subtree is DELETED, the panel UNMOUNTS, and the pre-existing unmount cleanup
// releases the microphone — at `0650bd46`, before any of this work. The in-app
// record switch was never leaking.
//
// SO WHAT ARE THESE TESTS? Almost all of them drive a state that is reached
// ONLY by re-rendering one instance with a new `experimentId`, WHICH NO CALLER
// IN THIS APPLICATION DOES. They are INVARIANT guards, not regression guards:
// they pin that the component honours `CAPTURE_COPY.voiceAudioHandling`'s
// "leave this record" promise on its own, without depending on a screen it does
// not control to unmount it. Several of them pass at `0650bd46` too. Each says
// which it is.
//
// THE EXCEPTIONS — the two tests at the end of this section, under the
// `RealMountPattern` harness. Those drive the caller's ACTUAL sequence and one
// of them is a genuine regression guard for a defect a real browser reproduces.

describe('leaving a record: the panel keeps its own promise, whoever the caller is', () => {
  const OTHER = 'other-record';
  const OTHER_RUNS = `GET /api/experiments/${OTHER}/runs`;
  const OTHER_ROUTES: Record<string, unknown> = {
    ...BASE_ROUTES,
    [OTHER_RUNS]: { body: runsPage },
  };

  function panelFor(id: string) {
    return (
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={id} />
      </MemoryRouter>
    );
  }

  /** Renders record A's panel, opens it, and returns the render handle. */
  async function renderOpenedFor(id: string) {
    const rendered = render(panelFor(id));
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryOpen }));
    return rendered;
  }

  it('the panel MAKES the claim these tests defend, and makes it on screen', async () => {
    /*
     * The link between the sentence and the behaviour, in one place. Nothing
     * else in this suite asserted `voiceAudioHandling`'s content, so the "leave
     * this record" clause could have been quietly weakened — the cheaper way to
     * make a false claim true — and every behaviour test above would still pass
     * while defending a promise the panel no longer makes. This fails in that
     * case, which is the point.
     */
    expect(CAPTURE_COPY.voiceAudioHandling).toContain('leave this record');
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(OTHER_ROUTES as never);
    await renderOpenedFor(EXP);
    expect(await screen.findByText(CAPTURE_COPY.voiceAudioHandling)).toBeInTheDocument();
  });

  it('held mounted across a record change, the panel releases the microphone itself — INVARIANT GUARD, not a regression guard: this state is reached by a rerender no caller performs — see the section header.', async () => {
    const stop = vi.fn();
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop }] })));
    stubFetchRoutes(OTHER_ROUTES as never);
    const rendered = await renderOpenedFor(EXP);
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    await waitFor(() => expect(FakeMediaRecorder.instances).toHaveLength(1));
    const recorder = FakeMediaRecorder.instances[0];
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop });

    // The one act under test: the SAME instance, a different record.
    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });

    expect(stop).toHaveBeenCalled();
    expect(recorder.state).toBe('inactive');
    // The handler is detached BEFORE `stop()`, so the final asynchronous chunk
    // cannot refill a buffer the panel has just declared empty.
    expect(recorder.ondataavailable).toBeNull();
    // And the panel no longer offers to stop a recording that is over.
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceStop })).toBeNull();
    expect(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord })).toBeInTheDocument();
  });

  it('held mounted across a record change, the previous record’s chunk count is not carried over — INVARIANT GUARD, not a regression guard: this state is reached by a rerender no caller performs — see the section header.', async () => {
    /*
     * The held-chunk count is never rendered — it exists only to build the
     * opaque handle the transcription request carries. That handle is therefore
     * the one place the buffer is OBSERVABLE from outside, which is why this
     * asserts on it rather than reaching into the component.
     */
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes({
      ...OTHER_ROUTES,
      [TRANSCRIBE]: { status: 501, body: { detail: 'no provider' } },
    } as never);
    const rendered = await renderOpenedFor(EXP);
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    await waitFor(() => expect(FakeMediaRecorder.instances).toHaveLength(1));
    // Two real chunks arrive on record A.
    await act(async () => {
      FakeMediaRecorder.instances[0].ondataavailable?.({ data: new Blob(['a']) });
      FakeMediaRecorder.instances[0].ondataavailable?.({ data: new Blob(['b']) });
      await Promise.resolve();
    });

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });

    // A fresh recording on record B, with NO chunk delivered.
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop });

    /*
     * EVERYTHING FROM HERE IS SYNCHRONOUS, DELIBERATELY. `FakeMediaRecorder.stop()`
     * emits its final chunk on a `setTimeout(…, 0)` — modelling the real API — and
     * an `await` between the two clicks lets that macrotask run, so record B's own
     * final chunk lands and the handle reads `held-in-tab:1` whatever record A did.
     * Using the synchronous `getByRole` keeps the count attributable: the handle is
     * minted before ANY chunk of record B's exists, so the number it carries can
     * only have come from record A. It also models the ordinary case of stopping
     * and asking for a transcript straight away.
     */
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceStop }));
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceTranscribe }));

    await waitFor(() => {
      const sent = writes().filter((entry) => entry.key === TRANSCRIBE);
      expect(sent).toHaveLength(1);
      // `held-in-tab:2` here would mean record A's buffer survived into record B.
      expect(sent[0].body.audio_ref).toBe('held-in-tab:0');
    });
  });

  it('held mounted across a record change, held audio is not offered to the next record — INVARIANT GUARD, not a regression guard: this state is reached by a rerender no caller performs — see the section header.', async () => {
    // The user-facing half of the test above: record A's audio must not still be
    // sitting behind "Request a Transcript"/"Discard Audio" on record B's screen.
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(OTHER_ROUTES as never);
    const rendered = await renderOpenedFor(EXP);
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceDiscard });

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });

    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceDiscard })).toBeNull();
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceTranscribe })).toBeNull();
    expect(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord })).toBeInTheDocument();
  });

  it('a pending permission prompt never becomes the next record’s microphone (rerender form; the REAL-PATH form of this is the regression guard at the end of this section)', async () => {
    let resolveGetUserMedia: (v: unknown) => void = () => {};
    const gate = new Promise((resolve) => {
      resolveGetUserMedia = resolve;
    });
    const stop = vi.fn();
    installRecorder(vi.fn(() => gate));
    stubFetchRoutes(OTHER_ROUTES as never);
    const rendered = await renderOpenedFor(EXP);
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceRequesting });

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });
    // The browser only NOW grants the request the previous record made.
    await act(async () => {
      resolveGetUserMedia({ getTracks: () => [{ stop }] });
      await Promise.resolve();
      await Promise.resolve();
    });

    // The stream is released rather than adopted, and record B is not recording.
    expect(stop).toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceStop })).toBeNull();
    expect(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord })).toBeInTheDocument();
  });

  it('held mounted across a record change, a stale transcription refusal is cleared — its own sentence stops being true — INVARIANT GUARD, not a regression guard: this state is reached by a rerender no caller performs — see the section header.', async () => {
    // `voiceAfterRefusal` says "The audio is still held in this tab" — which the
    // record change has just made false. The refusal card must not survive it.
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes({
      ...OTHER_ROUTES,
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
    const rendered = await renderOpenedFor(EXP);
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceTranscribe }));
    await screen.findByText('This build cannot transcribe speech: no provider is configured.');

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });

    expect(
      screen.queryByText('This build cannot transcribe speech: no provider is configured.'),
    ).toBeNull();
    expect(screen.queryByText(CAPTURE_COPY.voiceAfterRefusal)).toBeNull();
  });

  it('`permission-denied` SURVIVES a record change — it is a fact about the browser', async () => {
    installRecorder(vi.fn(async () => {
      throw new DOMException('synthetic, for this test only', 'NotAllowedError');
    }));
    stubFetchRoutes(OTHER_ROUTES as never);
    const rendered = await renderOpenedFor(EXP);
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    const { container } = rendered;
    await waitFor(() => expect(container.querySelector('.capture-note-warn')).not.toBeNull());

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });

    expect(container.querySelector('.capture-note-warn')?.textContent).toBe(
      CAPTURE_COPY.voicePermissionRefused,
    );
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceTryAgain })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceRecord })).toBeNull();
    // The live region still holds the SAME sentence, so the record change fired
    // no second announcement about a record the reader has already left.
    const live = container.querySelectorAll('[role="status"]');
    expect(
      Array.from(live).some((el) => el.textContent === CAPTURE_COPY.voicePermissionRefused),
    ).toBe(true);
  });

  it('`unsupported` SURVIVES a record change — it is a fact about the browser', async () => {
    // No `installRecorder()`: jsdom's own baseline has no `MediaRecorder`.
    stubFetchRoutes(OTHER_ROUTES as never);
    const rendered = await renderOpenedFor(EXP);
    await screen.findByText(CAPTURE_COPY.voiceUnsupported);

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });

    expect(screen.getByText(CAPTURE_COPY.voiceUnsupported)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceRecord })).toBeNull();
  });

  /* ------------------------------------------------------------------------
   * C1 / C2 — IN-FLIGHT REQUESTS, AND A CLAIM THAT WAS SCOPED DOWN.
   *
   * The reset above cleans up what the previous record LEFT BEHIND; it can do
   * nothing about what the previous record is STILL WAITING FOR. Every handler
   * is a plain function closing over the render that started it, so a response
   * landing after the record changed would write one record's facts onto
   * another's screen. These tests gate a response open, change record
   * underneath it, and release it.
   *
   * THEY DO NOT DEMONSTRATE A DEFECT IN THIS APPLICATION, and saying so is the
   * point. C1 and C2 were both raised as reproduced cross-record leaks — one
   * record's dictation in another's transcript box, one record's finalize
   * announced on another's screen. Both were produced by re-rendering ONE
   * instance with a new `experimentId`. Measured through the caller's real
   * mount sequence (see `RealMountPattern` at the end of this section), the
   * panel UNMOUNTS, React 18 no-ops the `setState`, and the next record gets a
   * fresh instance: with `requestTranscript`'s guard REMOVED, the next record's
   * transcript box was still empty. The guards are hazard-class defence — one
   * comparison each, load-bearing the moment any caller keeps this panel
   * mounted — and the tests below pin them as such, not as fixes.
   * --------------------------------------------------------------------- */

  /** A route that answers only once `open()` is called. */
  function gated(result: unknown) {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = () => resolve();
    });
    return {
      route: async () => {
        await gate;
        return result as { body: unknown };
      },
      release: async () => {
        await act(async () => {
          release();
          await Promise.resolve();
          await Promise.resolve();
          await Promise.resolve();
        });
      },
    };
  }

  const RUN_B = runFixture({ id: 'run-b1', label: 'Run B1', version: 'rb1.0', fields: {} });
  const otherRunsPage = {
    ...runsPage,
    runs: [RUN_B],
    experiment_version: 'gB.1',
  };

  it('C1 (HAZARD-CLASS, NOT REPRODUCIBLE IN THIS APP): held mounted, a stale transcript does not land in the next record’s box', async () => {
    const transcribe = gated({
      body: {
        refused: false,
        text: 'Synthetic dictation belonging to record A only.',
        segments: [],
        produced_by: 'test-double',
        verbatim: true,
        language: null,
      },
    });
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes({
      ...OTHER_ROUTES,
      [OTHER_RUNS]: { body: otherRunsPage },
      [TRANSCRIBE]: transcribe.route,
    } as never);
    const rendered = await renderOpenedFor(EXP);
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceTranscribe }));

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });
    await transcribe.release();

    // The scientist must never be handed words they did not say on this record:
    // they are one Finalize away from being stored as B's notes and proposals.
    const box = (await screen.findByLabelText('Transcript')) as HTMLTextAreaElement;
    expect(box.value).toBe('');
    expect(screen.queryByText(/Synthetic dictation belonging to record A/)).toBeNull();
  });

  it('C1 (HAZARD-CLASS, NOT REPRODUCIBLE IN THIS APP): held mounted, a stale transcription refusal does not render on the next record', async () => {
    const transcribe = gated({
      status: 501,
      body: {
        refused: true,
        seam: 'transcription',
        reason: 'no_provider_configured',
        missing: ['an approved transcription provider (decision D9)'],
        message: 'This build cannot transcribe speech: no provider is configured.',
        decision_reference: 'docs/ai-integration-decision-packet.md',
      },
    });
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes({
      ...OTHER_ROUTES,
      [OTHER_RUNS]: { body: otherRunsPage },
      [TRANSCRIBE]: transcribe.route,
    } as never);
    const rendered = await renderOpenedFor(EXP);
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceTranscribe }));

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });
    await transcribe.release();

    // The card ends with `voiceAfterRefusal` — "The audio is still held in this
    // tab" — which the record change has already made false.
    expect(
      screen.queryByText('This build cannot transcribe speech: no provider is configured.'),
    ).toBeNull();
    expect(screen.queryByText(CAPTURE_COPY.voiceAfterRefusal)).toBeNull();
  });

  it('C2 (HAZARD-CLASS, NOT REPRODUCIBLE IN THIS APP): held mounted, a stale finalize announces nothing, renders nothing, and imports no runs', async () => {
    const capture = gated({ body: reading() });
    stubFetchRoutes({
      ...OTHER_ROUTES,
      [OTHER_RUNS]: { body: otherRunsPage },
      [TRANSCRIPT]: capture.route,
    } as never);
    const rendered = await renderOpenedFor(EXP);
    const box = await screen.findByLabelText('Transcript');
    fireEvent.change(box, { target: { value: 'Temperature was 300 K.' } });
    fireEvent.change(await screen.findByLabelText(CAPTURE_COPY.runLabel), {
      target: { value: 'run-1' },
    });
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.finalize }));

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });
    // Record B's own runs resolve FIRST — the un-gated route — so the ordering
    // below is deterministic rather than a race the test happens to win.
    await screen.findByRole('option', { name: 'Run B1' });
    await capture.release();

    const { container } = rendered;
    const status = container.querySelector('[role="status"]');
    expect(status?.textContent ?? '').not.toMatch(/Finalized/);
    expect(screen.queryByText(CAPTURE_COPY.summaryStored(1, 1))).toBeNull();
    // Record A's run must not be selectable on record B's screen.
    expect(screen.queryByRole('option', { name: 'Run 1' })).toBeNull();
    expect(screen.getByRole('option', { name: 'Run B1' })).toBeInTheDocument();
  });

  it('C2 (HAZARD-CLASS, NOT REPRODUCIBLE IN THIS APP): held mounted, a stale finalize does not hand the next record another record’s version token', async () => {
    /*
     * The half of C2 with consequences past the screen: `experiment_version` is
     * what the next write sends as `If-Match`, so adopting record A's would aim
     * record B's write at another record's concurrency token.
     */
    const capture = gated({ body: reading() }); // carries experiment_version 'g1.5'
    const OTHER_TRANSCRIPT = `POST /api/experiments/${OTHER}/transcript`;
    stubFetchRoutes({
      ...OTHER_ROUTES,
      [OTHER_RUNS]: { body: otherRunsPage }, // carries experiment_version 'gB.1'
      [TRANSCRIPT]: capture.route,
      [OTHER_TRANSCRIPT]: { body: reading() },
    } as never);
    const rendered = await renderOpenedFor(EXP);
    fireEvent.change(await screen.findByLabelText('Transcript'), {
      target: { value: 'Temperature was 300 K.' },
    });
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.finalize }));

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });
    await screen.findByRole('option', { name: 'Run B1' });
    await capture.release();

    // Now write on record B and read the token off the wire.
    fireEvent.change(await screen.findByLabelText('Transcript'), {
      target: { value: 'A note typed on record B.' },
    });
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.finalize }));
    await waitFor(() => {
      const sent = writes().filter((entry) => entry.key === OTHER_TRANSCRIPT);
      expect(sent).toHaveLength(1);
      // The token really is on the wire as `If-Match`, which is the whole point:
      // `"g1.5"` here would be record A's version aimed at record B's write.
      expect(sent[0].ifMatch).toBe('"gB.1"');
    });
  });

  it('I1 (HAZARD-CLASS): held mounted, a record change mid-finalize does not leave the next record’s form locked', async () => {
    const capture = gated({ body: reading() });
    stubFetchRoutes({
      ...OTHER_ROUTES,
      [OTHER_RUNS]: { body: otherRunsPage },
      [TRANSCRIPT]: capture.route,
    } as never);
    const rendered = await renderOpenedFor(EXP);
    fireEvent.change(await screen.findByLabelText('Transcript'), {
      target: { value: 'Temperature was 300 K.' },
    });
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.finalize }));
    // Record A really is locked.
    expect(await screen.findByRole('button', { name: /Reading/ })).toBeDisabled();

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });

    // Record B has nothing in flight, so nothing about it may be reported busy.
    expect(screen.queryByRole('button', { name: /Reading/ })).toBeNull();
    expect(await screen.findByLabelText('Transcript')).not.toBeDisabled();
    await capture.release();
    expect(await screen.findByLabelText('Transcript')).not.toBeDisabled();
  });

  it('held mounted, the stale finalize announcement is cleared by the record change itself — INVARIANT GUARD, not a regression guard: this state is reached by a rerender no caller performs — see the section header.', async () => {
    /*
     * Pins `setAnnouncement('')` in the reset, which survived an independent
     * reviewer's mutation. This is the completed-finalize case (no gate): the
     * card is gone because `reading` is cleared, and the sentence describing it
     * must not be left in a live region on someone else's record.
     */
    stubFetchRoutes({
      ...OTHER_ROUTES,
      [OTHER_RUNS]: { body: otherRunsPage },
      [TRANSCRIPT]: { body: reading() },
    } as never);
    const rendered = await renderOpenedFor(EXP);
    await typeAndFinalize();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
    const { container } = rendered;
    expect(container.querySelector('[role="status"]')?.textContent).toMatch(/Finalized/);

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });

    expect(container.querySelector('[role="status"]')?.textContent).toBe('');
    expect(screen.queryByText(CAPTURE_COPY.summaryStored(1, 1))).toBeNull();
  });

  it('held mounted, a stale permission refusal neither accuses the next record nor stops its recording — INVARIANT GUARD, not a regression guard: this state is reached by a rerender no caller performs — see the section header.', async () => {
    /*
     * Pins the CATCH-path generation guard, which survived an independent
     * reviewer's mutation. It matters more than the success path: `dropAudio()`
     * operates on the SHARED refs, so a refusal arriving late would tear down a
     * recording the new record had legitimately started — the stale response
     * reaching in and stopping a live microphone that is not its own.
     */
    let rejectFirst: (cause: unknown) => void = () => {};
    const firstAttempt = new Promise((_resolve, reject) => {
      rejectFirst = reject;
    });
    const secondTrack = { stop: vi.fn() };
    const getUserMedia = vi
      .fn()
      .mockImplementationOnce(() => firstAttempt)
      .mockImplementation(async () => ({ getTracks: () => [secondTrack] }));
    installRecorder(getUserMedia);
    stubFetchRoutes({ ...OTHER_ROUTES, [OTHER_RUNS]: { body: otherRunsPage } } as never);

    const rendered = await renderOpenedFor(EXP);
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceRequesting });

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });
    // Record B starts its own, successful recording.
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop });

    // Only NOW does record A's permission prompt come back refused.
    await act(async () => {
      rejectFirst(new DOMException('synthetic, for this test only', 'NotAllowedError'));
      await Promise.resolve();
      await Promise.resolve();
    });

    const { container } = rendered;
    expect(container.querySelector('.capture-note-warn')).toBeNull();
    // Record B is still recording, and its microphone was not stopped.
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceStop })).toBeInTheDocument();
    expect(secondTrack.stop).not.toHaveBeenCalled();
  });

  /* ------------------------------------------------------------------------
   * I3 — THE OTHER WAY OF LEAVING, AND THE ONE THAT WAS REALLY BROKEN ON SCREEN.
   *
   * Unlike everything above, this needs no rerender and no held-mounted caller:
   * "Close Capture" is a real control a scientist presses, and it was
   * reproduced through it. Closing already released the microphone and already
   * dropped the buffer — it just never said so, leaving "Stop Recording", an
   * elapsed indicator reading `Recording · 0:00`, and a live region claiming
   * audio was being held, with no stream, recorder or buffer behind any of it.
   * These two tests ARE regression guards.
   * --------------------------------------------------------------------- */

  it('I3: CLOSING THE PANEL MID-RECORDING LEAVES NO "RECORDING" CLAIM BEHIND', async () => {
    const stop = vi.fn();
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop }] })));
    stubFetchRoutes(OTHER_ROUTES as never);
    const { container } = await renderOpenedFor(EXP);
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop });

    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryClose }));
    await waitFor(() => expect(stop).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryOpen }));

    // Reopened: there is no stream, no recorder and no buffer, so nothing on
    // screen may say otherwise.
    expect(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceStop })).toBeNull();
    expect(container.querySelector('.capture-elapsed')).toBeNull();
    const live = container.querySelectorAll('[aria-live="polite"]');
    expect(Array.from(live).some((el) => el.textContent === CAPTURE_COPY.voiceIdleLive)).toBe(true);
    expect(
      Array.from(live).some((el) => el.textContent === CAPTURE_COPY.voiceRecordingLive),
    ).toBe(false);
  });

  it('I3: `permission-denied` SURVIVES CLOSING THE PANEL, for the same reason it survives a record change', async () => {
    installRecorder(vi.fn(async () => {
      throw new DOMException('synthetic, for this test only', 'NotAllowedError');
    }));
    stubFetchRoutes(OTHER_ROUTES as never);
    const { container } = await renderOpenedFor(EXP);
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    await waitFor(() => expect(container.querySelector('.capture-note-warn')).not.toBeNull());

    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryClose }));
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryOpen }));

    expect(container.querySelector('.capture-note-warn')?.textContent).toBe(
      CAPTURE_COPY.voicePermissionRefused,
    );
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceRecord })).toBeNull();
  });

  /* ------------------------------------------------------------------------
   * I2 — THE RUN LIST AND THE VERSION TOKEN, WHICH NEED A SLOW FETCH TO SEE.
   * Both tests gate a runs response open. Without a gate the window in which
   * one record's runs could be shown on another's screen is zero, and a
   * mutation removing either guard passes the whole suite — measured: it did.
   * Hazard-class like C1/C2: in the shipped app the panel unmounts, so the
   * window does not exist there either. The `If-Match` consequence is why they
   * are worth keeping anyway.
   * --------------------------------------------------------------------- */

  it('I2 (HAZARD-CLASS): held mounted, the previous record’s runs are gone before the next record’s arrive', async () => {
    const otherRuns = gated({ body: otherRunsPage });
    stubFetchRoutes({
      ...OTHER_ROUTES,
      [OTHER_RUNS]: otherRuns.route,
    } as never);
    const rendered = await renderOpenedFor(EXP);
    await screen.findByRole('option', { name: 'Run 1' });

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });

    // THE WINDOW. Record B's runs have not arrived. Record A's must not be
    // selectable here: choosing one would aim record B's write at another
    // record's run id, holding another record's version token.
    expect(screen.queryByRole('option', { name: 'Run 1' })).toBeNull();
    // THE DOCUMENTED COST OF CLEARING, pinned so it stays a known trade-off and
    // not a discovery: for the length of the fetch the panel shows its
    // zero-runs branch, exactly as it already does on every first open.
    expect(screen.getByRole('button', { name: CAPTURE_COPY.runCreate })).toBeInTheDocument();

    await otherRuns.release();
    expect(await screen.findByRole('option', { name: 'Run B1' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Run 1' })).toBeNull();
  });

  it('I2 (HAZARD-CLASS): held mounted, a runs response for the previous record does not overwrite the next record’s list', async () => {
    /*
     * The success-path guard inside `loadRuns`. `loadRunsAttempt` has always had
     * a generation check, but only around its CATCH — a successful read for the
     * record just left went straight through to `setRuns`/`setExperimentVersion`.
     */
    const firstRuns = gated({ body: runsPage });
    stubFetchRoutes({
      ...OTHER_ROUTES,
      [RUNS]: firstRuns.route,
      [OTHER_RUNS]: { body: otherRunsPage },
    } as never);
    const rendered = await renderOpenedFor(EXP);

    await act(async () => {
      rendered.rerender(panelFor(OTHER));
      await Promise.resolve();
    });
    await screen.findByRole('option', { name: 'Run B1' });

    // Record A's runs arrive LAST, and must be discarded rather than displayed.
    await firstRuns.release();
    expect(screen.queryByRole('option', { name: 'Run 1' })).toBeNull();
    expect(screen.getByRole('option', { name: 'Run B1' })).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------------
   * THE REAL MOUNT SEQUENCE — the only two tests in this section that drive
   * what the application actually does, and the only place a regression guard
   * for this work lives.
   *
   * `RecordWorkbench.tsx:397-412` renders this panel ONLY while
   * `bundle.status === 'data'`. A record switch refetches, so the sequence is:
   * react-router commits the new `:id` FIRST (one commit, panel still mounted,
   * carrying the NEW id), then the bundle flips to `'loading'` and the whole
   * subtree is deleted. That single mounted commit is what bumps the record
   * generation, and it is why the guard in `startRecording` is reachable at all
   * for a panel that is about to unmount.
   * --------------------------------------------------------------------- */

  /** Mimics the caller's gating faithfully: the panel exists only on `'data'`. */
  function RealMountPattern({
    state,
  }: {
    state: { id: string; status: 'data' | 'loading' };
  }) {
    return (
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        {state.status === 'data' ? (
          <TranscriptCapturePanel experimentId={state.id} />
        ) : (
          <p>Loading the record from the ISAAC API…</p>
        )}
      </MemoryRouter>
    );
  }

  it('REGRESSION GUARD (real path): leaving mid-permission-prompt does not orphan a microphone nothing can stop', async () => {
    /*
     * THE ONE DEFECT IN THIS SECTION A REAL BROWSER REPRODUCES. Press Start
     * Recording, leave before the browser resolves the prompt: the panel
     * unmounts, its cleanup runs `dropAudio()` and finds no stream to stop
     * because none exists yet, and THEN `getUserMedia` resolves into a dead
     * component's closure — assigning the stream and calling `recorder.start()`
     * with nothing left holding a reference to either.
     *
     * Measured in real Chromium at `0650bd46` (instrumented
     * `MediaStreamTrack.prototype.stop`, real fake audio device): the track
     * stayed `live` for a 15-second poll with ZERO `stop()` calls. The same
     * sequence here, with `startRecording`'s stale-generation branch removed,
     * measures 0 stops and 1 constructed recorder; with it, 1 stop and 0
     * recorders. Spec: `apps/web/e2e/mutation/capture-microphone.spec.ts`.
     */
    let grant: (value: unknown) => void = () => {};
    const prompt = new Promise((resolve) => {
      grant = resolve;
    });
    const track = { stop: vi.fn() };
    installRecorder(vi.fn(() => prompt));
    stubFetchRoutes({ ...OTHER_ROUTES, [OTHER_RUNS]: { body: otherRunsPage } } as never);

    const rendered = render(<RealMountPattern state={{ id: EXP, status: 'data' }} />);
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryOpen }));
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
    await screen.findByRole('button', { name: CAPTURE_COPY.voiceRequesting });

    // The caller's real two-step: new id commits while still mounted, THEN the
    // subtree is deleted. Collapsing these into one step would skip the commit
    // that bumps the generation and quietly make this test prove nothing.
    await act(async () => {
      rendered.rerender(<RealMountPattern state={{ id: OTHER, status: 'data' }} />);
      await Promise.resolve();
    });
    await act(async () => {
      rendered.rerender(<RealMountPattern state={{ id: OTHER, status: 'loading' }} />);
      await Promise.resolve();
    });
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.entryOpen })).toBeNull();

    // Only now does the browser answer the prompt, into a dead closure.
    await act(async () => {
      grant({ getTracks: () => [track] });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(track.stop).toHaveBeenCalled();
    // And no recorder was ever constructed from the orphaned stream.
    expect(FakeMediaRecorder.instances).toHaveLength(0);
  });

  it('INVARIANT GUARD (real path): an in-app record switch cannot carry content between records, because the panel unmounts', async () => {
    /*
     * PINS THE MECHANISM, AND PASSES WITHOUT ANY GUARD IN THIS SLICE — measured:
     * with `requestTranscript`'s generation check removed, the next record's
     * transcript box is still empty. That is the whole finding. C1 was raised as
     * a reproduced cross-record content leak and is not one in this application:
     * the switch deletes the subtree, React 18 no-ops the late `setText`, and
     * the next record is served by a fresh instance with its own empty state.
     *
     * It is kept because the mechanism is load-bearing and invisible. If a
     * future screen keeps this panel mounted across a record change — a `key`
     * removed, a workspace that hides instead of unmounting — this test still
     * passes only because of the guards, and their value stops being
     * hypothetical. It is labelled an invariant guard so nobody cites it as
     * proof that this slice fixed something.
     */
    let release: () => void = () => {};
    const answered = new Promise<void>((resolve) => {
      release = () => resolve();
    });
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes({
      ...OTHER_ROUTES,
      [OTHER_RUNS]: { body: otherRunsPage },
      [TRANSCRIBE]: async () => {
        await answered;
        return {
          body: {
            refused: false,
            text: 'Synthetic dictation belonging to the first record only.',
            segments: [],
            produced_by: 'test-double',
            verbatim: true,
            language: null,
          },
        };
      },
    } as never);

    const rendered = render(<RealMountPattern state={{ id: EXP, status: 'data' }} />);
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryOpen }));
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceTranscribe }));

    // Switch, unmount, and land on the next record — the caller's real path.
    await act(async () => {
      rendered.rerender(<RealMountPattern state={{ id: OTHER, status: 'data' }} />);
      await Promise.resolve();
    });
    await act(async () => {
      rendered.rerender(<RealMountPattern state={{ id: OTHER, status: 'loading' }} />);
      await Promise.resolve();
    });
    await act(async () => {
      rendered.rerender(<RealMountPattern state={{ id: OTHER, status: 'data' }} />);
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.entryOpen }));

    await act(async () => {
      release();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    const box = (await screen.findByLabelText('Transcript')) as HTMLTextAreaElement;
    expect(box.value).toBe('');
    expect(screen.queryByText(/Synthetic dictation belonging to the first record/)).toBeNull();
  });
});

// --- 14. local playback of the held audio -------------------------------------
//
// ADDED 2026-09-10. Before this, a scientist could record audio and never hear
// it: the only exits from a recording were *Request a Transcript* (which
// refuses in every deployment) and *Discard Audio*. There was no `<audio>`, no
// `createObjectURL` and no `new Audio()` anywhere in the capture path, so the
// Record button's entire value was contingent on a transcription provider that
// does not exist.
//
// EVERY TEST HERE DRIVES THE SHIPPED `FakeMediaRecorder`/`installRecorder`
// DOUBLES. No second double is introduced: `installRecorder` gained the
// object-URL bookkeeping the playback path needs, because jsdom implements
// neither `createObjectURL` nor `revokeObjectURL` and the component's own
// `typeof` guard would otherwise skip the code these tests are about.

describe('local playback of the held audio', () => {
  /**
   * Record, stop, and FLUSH THE FINAL CHUNK.
   *
   * The flush is the whole reason this helper exists rather than three inline
   * lines. `FakeMediaRecorder.stop()` emits its `dataavailable` on a
   * `setTimeout(…, 0)` — reproducing the real API, whose final chunk arrives
   * asynchronously — and a `MediaRecorder` started with no timeslice emits
   * exactly ONE chunk, at stop. So immediately after the Stop click the buffer
   * is still EMPTY, and a test that asserted here would be asserting that no
   * player exists, for the wrong reason.
   */
  async function recordAndHold() {
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    const rendered = await renderPanel();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));
    // The buffer is empty until the asynchronous final chunk lands.
    expect(rendered.container.querySelector('audio')).toBeNull();
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    return rendered;
  }

  const player = (container: HTMLElement) =>
    container.querySelector('audio') as
      | (HTMLAudioElement & { disableRemotePlayback?: boolean })
      | null;

  it('offers a player for the held audio, from an object URL this tab minted', async () => {
    const { container } = await recordAndHold();
    const audio = player(container);
    expect(audio, 'no player was rendered for held audio').not.toBeNull();
    // Vacuity: the double really was reached, and the src really is the URL it
    // handed back — not some other string that merely looks like one.
    expect(objectUrls.created).toHaveLength(1);
    expect(audio!.getAttribute('src')).toBe(objectUrls.created[0]);
    expect(audio!.hasAttribute('controls')).toBe(true);
    expect(audio!).toHaveAttribute('aria-label', CAPTURE_COPY.voicePlaybackLabel);
    expect(objectUrls.revoked).toEqual([]);
  });

  it('the player offers no download and no casting — two ways audio could leave', () => {
    /*
     * NOT A STYLE PREFERENCE, EITHER OF THEM.
     *
     * `nodownload` — Chrome's default `<audio controls>` overflow menu carries
     * a Download item. `CAPTURE_COPY.voiceAudioHandling` promises the audio is
     * "never written to disk"; a download control would make a shipped claim
     * false.
     *
     * `noremoteplayback` + `disableRemotePlayback` — remote playback would
     * stream the clip to a Cast device. That is audio leaving the tab over a
     * channel no HTTP assertion in this repository watches, including
     * `e2e/mutation/capture-microphone.spec.ts`'s request sweep.
     */
    return recordAndHold().then(({ container }) => {
      const audio = player(container)!;
      const list = audio.getAttribute('controlsList') ?? '';
      expect(list.split(/\s+/)).toContain('nodownload');
      expect(list.split(/\s+/)).toContain('noremoteplayback');
      expect(audio.disableRemotePlayback).toBe(true);
    });
  });

  it('rendering the player issues NO request of any kind', async () => {
    const { container } = await recordAndHold();
    expect(player(container)).not.toBeNull();
    /*
     * The premise this rests on: the only requests in the log are the two the
     * panel makes when it OPENS. Playback added neither a third nor a body.
     * Stated as an exact set rather than as "no audio key", because a new
     * request with no audio in it would still be a request this claim denies.
     */
    expect(requests()).toEqual([`GET /api/experiments/${EXP}/runs`, 'GET /api/providers/capabilities']);
    expect(writes()).toEqual([]);
  });

  it('Discard Audio revokes the object URL and removes the player', async () => {
    const { container } = await recordAndHold();
    const minted = objectUrls.created[0];
    expect(player(container)).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceDiscard }));

    expect(objectUrls.revoked).toEqual([minted]);
    expect(player(container)).toBeNull();
    // And nothing new was minted on the way out — a revoke followed by a
    // re-create would leak on the next transition instead of this one.
    expect(objectUrls.created).toHaveLength(1);
  });

  it('unmounting revokes the object URL', async () => {
    const { unmount } = await recordAndHold();
    const minted = objectUrls.created[0];
    expect(objectUrls.revoked).toEqual([]);
    unmount();
    expect(objectUrls.revoked).toEqual([minted]);
  });

  it('closing the panel revokes it too — the other way of leaving', async () => {
    const { container } = await recordAndHold();
    const minted = objectUrls.created[0];
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryClose }));
    expect(objectUrls.revoked).toEqual([minted]);
    expect(player(container)).toBeNull();
  });

  it('a SECOND recording mints a fresh URL, never reusing the revoked one', async () => {
    /*
     * THE ONLY WAY BACK TO `idle` FROM `held` IS DISCARD, and that is measured
     * rather than assumed: `Start Recording` renders in `voice === 'idle'`
     * alone, so a held recording cannot be restarted over the top of itself.
     * The four other exits from `held` (Close Capture, a record change, an
     * unmount, and this discard) each have their own test above.
     */
    const { container } = await recordAndHold();
    const first = objectUrls.created[0];
    expect(screen.queryByRole('button', { name: CAPTURE_COPY.voiceRecord })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceDiscard }));
    expect(objectUrls.revoked).toEqual([first]);
    expect(player(container)).toBeNull();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceStop }));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(objectUrls.created).toHaveLength(2);
    expect(player(container)!.getAttribute('src')).toBe(objectUrls.created[1]);
    expect(player(container)!.getAttribute('src')).not.toBe(first);
    // Exactly one live URL at any moment: two minted, one revoked.
    expect(objectUrls.revoked).toHaveLength(1);
  });
});

// --- 15. the held state is visible, and the refusal speaks to a scientist ------

describe('held is visible to a sighted reader, not only to a screen reader', () => {
  async function hold() {
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIBE]: {
        status: 501,
        body: {
          refused: true,
          seam: 'transcription',
          reason: 'no_provider_configured',
          missing: [
            'an approved transcription provider (decision D9)',
            'an institutional credential for it (decision D4)',
          ],
          message:
            'This build cannot transcribe speech: no provider is configured for the ' +
            'transcription seam. These are institutional decisions recorded in ' +
            'docs/ai-integration-decision-packet.md.',
          decision_reference: 'docs/ai-integration-decision-packet.md',
        },
      },
    } as never);
    const rendered = await renderPanel();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceStop }));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    return rendered;
  }

  it('states in VISIBLE text that audio is held — not only in the sr-only region', async () => {
    const { container } = await hold();
    /*
     * THE DEFECT THIS PINS. Before 2026-09-10 the only statement that audio was
     * held after Stop was the `aria-live` region, which a sighted reader never
     * sees — an inversion of the usual accessibility failure. The assertion is
     * therefore specifically that the sentence exists OUTSIDE `.sr-only`.
     */
    const held = screen.getByText(CAPTURE_COPY.voiceHeldPersistent);
    expect(held.closest('.sr-only')).toBeNull();
    expect(container.querySelector('.capture-live[data-state="held"]')).not.toBeNull();
  });

  it('I-2: a Stop that cannot be pressed is disabled AND carries its disabled styling hook', async () => {
    /*
     * THE DEFECT THIS PINS WAS INTRODUCED BY THIS SLICE, one rule away from
     * the one it was fixing. `formLocked` (a finalize in flight) makes
     * `showVoicePrimary` false, so a DISABLED Stop renders `btn btn-secondary
     * capture-stop` — and `.btn-secondary` declares no `:disabled` state while
     * the `.capture-stop` repaint wins anyway. Measured in Chrome before the
     * fix: `rgb(178,58,48)` on `#fff` with `cursor: pointer`, byte-identical
     * to a live armed Stop.
     *
     * REACHABLE, not theoretical: type a transcript while recording, press
     * Finalize. That is exactly what this test does. jsdom computes no
     * stylesheet, so the class is what is checkable here; the rule it hooks
     * (`.capture-voice-controls .btn.capture-stop:disabled`, plus
     * `:not(:disabled)` on the two state rules) lives in `transcriptCapture.css`
     * with its measured ratio.
     */
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    /*
     * THE ROUTE IS A FUNCTION THAT AWAITS, NOT A `delay` OPTION — the shape
     * `apiFixtures.ts:117` warns about. A first version of this test wrote
     * `{ body: reading(), delay: gate }`; `delay` is not a fixture key, the
     * stub answered IMMEDIATELY, and `formLocked` was never true, so the
     * assertion below ran against an ordinary enabled Stop and failed for a
     * reason that had nothing to do with the defect.
     */
    const gateHandle: { resolve: (() => void) | null } = { resolve: null };
    const gate = new Promise<void>((resolve) => {
      gateHandle.resolve = () => resolve();
    });
    stubFetchRoutes({
      ...BASE_ROUTES,
      [TRANSCRIPT]: async () => {
        await gate;
        return { body: reading() };
      },
    } as never);
    await renderPanel();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    const stop = screen.getByRole('button', { name: CAPTURE_COPY.voiceStop });
    expect(stop).toBeEnabled();

    fireEvent.change(screen.getByLabelText('Transcript'), { target: { value: 'still recording' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.finalize }));
      await Promise.resolve();
    });

    const locked = screen.getByRole('button', { name: CAPTURE_COPY.voiceStop });
    expect(locked).toBeDisabled();
    expect(locked).toHaveClass('capture-stop');
    // It is NOT primary in this state, which is the whole reason the plain
    // `.btn-secondary` fallback left it looking armed.
    expect(locked).toHaveClass('btn-secondary');
    gateHandle.resolve?.();
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 1));
  });

  it('the refusal leads with one scientist-facing sentence and keeps every server word', async () => {
    await hold();
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceTranscribe }));

    // The lead, chosen by the SERVER's own `reason` code.
    const lead = await screen.findByText(CAPTURE_COPY.voiceRefusalNoProvider);
    expect(lead).toHaveClass('capture-refusal-message');
    // Nothing the server said is dropped: its message, its missing items and
    // its decision reference are all still rendered, behind the disclosure.
    expect(screen.getByText(/This build cannot transcribe speech/)).toBeInTheDocument();
    expect(
      screen.getByText('an approved transcription provider (decision D9)'),
    ).toBeInTheDocument();
    // `getAllBy`: the reference appears twice by design — once inside the
    // server's own sentence, and once as the `<code>` pointer beneath it.
    expect(screen.getAllByText(/docs\/ai-integration-decision-packet\.md/)).toHaveLength(2);
    // …and they are behind it, rather than beside it — which is the change.
    const why = screen.getByText(CAPTURE_COPY.voiceRefusalWhy).closest('details');
    expect(why).not.toBeNull();
    expect(why!.open).toBe(false);
    expect(why!.contains(screen.getByText(/This build cannot transcribe speech/))).toBe(true);
    expect(why!.contains(lead)).toBe(false);
  });

  it('the held state, the player and the refusal disclosure are all accessible', async () => {
    /*
     * THE STATE THE EXISTING AXE TEST DOES NOT REACH. `accessibility` above
     * scans the POST-FINALIZE tree; every element this slice added — the state
     * bar, the `<audio>` player, the `<details>` disclosure — lives in `held`,
     * which that scan never enters. Same rule set, so the two are comparable.
     */
    const { container } = await hold();
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceTranscribe }));
    await screen.findByText(CAPTURE_COPY.voiceRefusalNoProvider);
    // Vacuity: the scan must actually be looking at the new markup.
    expect(container.querySelector('audio')).not.toBeNull();
    expect(container.querySelector('details')).not.toBeNull();
    expect(container.querySelector('.capture-live[data-state="held"]')).not.toBeNull();

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
    expect(results.violations).toEqual([]);
  });

  it('Request a Transcript is disarmed once it has refused, and re-armed by a new recording', async () => {
    await hold();
    const request = () => screen.getByRole('button', { name: CAPTURE_COPY.voiceTranscribe });
    expect(request()).toBeEnabled();
    fireEvent.click(request());
    await screen.findByText(CAPTURE_COPY.voiceRefusalNoProvider);
    /*
     * A CONTROL THAT CAN NEVER SUCCEED MUST NOT STAY ARMED. This operation is
     * refused `501 no_provider_configured` in every deployment, and it used to
     * return to its enabled resting state so the same wall could be summoned
     * forever.
     */
    expect(request()).toBeDisabled();
    /*
     * AND IT LOOKS DISABLED. `.btn-secondary` declares no `:disabled` state
     * anywhere in `styles/base.css`, so without `capture-transcribe` this
     * button renders PIXEL-IDENTICAL to the live `Discard Audio` beside it —
     * measured in Chrome: both `rgb(255,255,255)` / border
     * `rgb(211,218,226)` / `color: rgb(70,81,95)` / `cursor: pointer`. jsdom
     * computes no stylesheet, so the class is what this can check; the rule
     * it hooks is in `transcriptCapture.css` with its own measured ratios.
     */
    expect(request()).toHaveClass('capture-transcribe');
    // The audio is NOT discarded by a refusal, so the other two stay live.
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceDiscard })).toBeEnabled();
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceTypeWhatWasSaid })).toBeEnabled();

    /*
     * THE SEAM STAYS DISCOVERABLE: a NEW recording clears the refusal and
     * re-arms the control. Discard is the one way back to `idle` from `held`,
     * and it is clicked OUTSIDE `act` — nesting a `findBy*` inside an
     * `act(async …)` makes testing-library's own async wrapper wait on a
     * flush the outer `act` is holding.
     */
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceDiscard }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
    });
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceStop }));
    expect(request()).toBeEnabled();
    // …and the wall is gone with it, rather than lingering beside an armed control.
    expect(screen.queryByText(CAPTURE_COPY.voiceRefusalNoProvider)).toBeNull();
  });
});

// --- 16. finalizing with no run is warned about, not blocked -------------------

describe('the no-run pre-flight', () => {
  it('warns beside Finalize that nothing will be proposed, and leaves it enabled', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    const box = await screen.findByLabelText('Transcript');
    fireEvent.change(box, { target: { value: 'Temperature was 300 K.' } });

    const preflight = screen.getByText(CAPTURE_COPY.finalizePreflightNoRun);
    expect(preflight).toBeInTheDocument();
    const finalize = screen.getByRole('button', { name: CAPTURE_COPY.finalize });
    /*
     * ENABLED IS THE POINT. Notes are still stored with the record and that is
     * genuinely valuable; the defect was that the consequence was discovered
     * only afterwards, from a summary card reading "Nothing was proposed from
     * this transcript."
     */
    expect(finalize).toBeEnabled();
    expect(finalize.getAttribute('aria-describedby')).toBe(preflight.id);
  });

  it('clears the warning once a run is chosen', async () => {
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    /*
     * THE TEXT IS TYPED FIRST, AND THAT IS NOT SETUP NOISE. After M-3 the
     * warning is gated on `text.trim() !== ''` as well as on the empty run,
     * so a version of this test that never typed would find it absent for
     * the WRONG REASON and pass whatever the run selector did — a guard that
     * cannot fail. The positive assertion below is what makes the negative
     * one mean something.
     */
    const box = await screen.findByLabelText('Transcript');
    fireEvent.change(box, { target: { value: 'Temperature was 300 K.' } });
    expect(screen.getByText(CAPTURE_COPY.finalizePreflightNoRun)).toBeInTheDocument();

    fireEvent.change(await screen.findByLabelText(CAPTURE_COPY.runLabel), {
      target: { value: 'run-1' },
    });
    expect(screen.queryByText(CAPTURE_COPY.finalizePreflightNoRun)).toBeNull();
    expect(
      screen.getByRole('button', { name: CAPTURE_COPY.finalize }).getAttribute('aria-describedby'),
    ).toBeNull();
  });

  it('M-3: says nothing before there is anything to finalize', async () => {
    /*
     * The warning used to render the moment the panel opened — describing a
     * press that is not yet possible, since Finalize is `disabled` while the
     * box is empty. It now appears with the action it describes.
     */
    stubFetchRoutes(BASE_ROUTES as never);
    await renderPanel();
    await screen.findByLabelText('Transcript');
    expect(screen.queryByText(CAPTURE_COPY.finalizePreflightNoRun)).toBeNull();
    expect(screen.getByRole('button', { name: CAPTURE_COPY.finalize })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Transcript'), { target: { value: 'a note' } });
    expect(screen.getByText(CAPTURE_COPY.finalizePreflightNoRun)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: CAPTURE_COPY.finalize })).toBeEnabled();
  });

  it('I-3: no CAPTURE_COPY string promises a browser BEHAVIOUR this build cannot enforce', () => {
    /*
     * `voicePlaybackNote` shipped "the player offers no download and no
     * casting to another device" — a claim about what every engine DOES.
     * `controlsList` and `disableRemotePlayback` are Chromium-only; Firefox
     * honours neither, and there the native player DOES offer a download. The
     * browser suites here run chromium only, so nothing could have caught it.
     *
     * The ban is on the ASSERTIVE shape ("the player offers no…", "no download
     * is offered"), not on the reassurance: "is configured to offer no…" is a
     * claim about this build's own markup and is true in every engine. Same
     * correction shape as the scoped-not-deleted upload claims in CLAUDE.md
     * §11.
     */
    const UNCONDITIONAL_UA_CLAIM =
      /\b(the\s+)?player\s+(offers|provides|has|shows)\s+no\b|\bno\s+(download|casting)\s+(is|will\s+be)\s+(offered|shown|provided)\b/i;
    const offenders = Object.entries(CAPTURE_COPY)
      .filter(([, v]) => typeof v === 'string' && UNCONDITIONAL_UA_CLAIM.test(v as string))
      .map(([k]) => k);
    expect(offenders).toEqual([]);
    // Polarity: the retired phrasing really is caught, and the corrected one is not.
    expect(
      UNCONDITIONAL_UA_CLAIM.test('the player offers no download and no casting to another device'),
    ).toBe(true);
    expect(UNCONDITIONAL_UA_CLAIM.test(CAPTURE_COPY.voicePlaybackNote)).toBe(false);
    // …and the reassurance is still made, rather than deleted to satisfy the ban.
    expect(CAPTURE_COPY.voicePlaybackNote).toMatch(/configured to offer no download/i);
  });

  it('no shipped string implies a value might not need a run — the two used to contradict', () => {
    /*
     * MEASURED AT `65f5ebd3`, over the server rather than assumed:
     *
     *   .venv/bin/python -c "import sys; sys.path.insert(0,'apps/api');
     *     from isaac_api import transcript_capture as tc, routes;
     *     print({p: routes._PROPOSAL_WRITER_SCOPE.get(routes._proposal_writer_for(p))
     *            for p in sorted(tc.READABLE_FIELD_PATHS)})"
     *
     * All five readable paths resolve to scope `run`. So the panel's "only
     * run-scoped values need a run chosen first" was false, and the server's
     * "Every value this reader can propose belongs to a run" was true — and
     * BOTH shipped, on the same screen, one before finalize and one after.
     *
     * This guard bans the shape rather than the sentence, because the sentence
     * is the thing most likely to be reworded back into the same error.
     */
    const IMPLIES_OPTIONAL = /only\s+run-scoped[^.]*\bneed\b/i;
    const offenders = Object.entries(CAPTURE_COPY)
      .filter(([, v]) => typeof v === 'string' && IMPLIES_OPTIONAL.test(v as string))
      .map(([k]) => k);
    expect(offenders).toEqual([]);
    // Polarity: the retired sentence really is caught, so the guard cannot go
    // quiet and read as a pass.
    expect(
      IMPLIES_OPTIONAL.test(
        'No run is selected. Proposals from this transcript will target the record ' +
          'itself — only run-scoped values need a run chosen first.',
      ),
    ).toBe(true);
  });
});

// --- 17. the elapsed count is wall-clock, not a tick count --------------------

describe('the elapsed indicator survives a throttled timer', () => {
  it('reads the wall clock, so a tab that was backgrounded does not understate', async () => {
    /*
     * THE DEFECT THIS PINS WAS MEASURED IN REAL CHROME, NOT REASONED ABOUT.
     * The count used to be `setElapsedSec((s) => s + 1)` on a 1000 ms
     * interval — a count of CALLBACK RUNS. Browsers throttle background
     * timers hard, and this panel's own header says a recording is expected
     * to keep running while hidden. Measured on a backgrounded tab at
     * 127.0.0.1:5173: the indicator read `0:03` while the held clip decoded
     * (via `AudioContext.decodeAudioData` on the object URL's own bytes) to
     * 6.96 s of 2-channel 44.1 kHz audio. It understated, and silently.
     *
     * `vi.setSystemTime` moves `Date.now()` WITHOUT firing pending timers,
     * which is exactly the shape of throttling: wall time passes, callbacks
     * do not run. A tick-counting implementation reads 0:00 here.
     */
    vi.useFakeTimers();
    installRecorder(vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })));
    stubFetchRoutes(BASE_ROUTES as never);
    const { container } = await renderPanel();
    const start = Date.now();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceRecord }));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.querySelector('.capture-elapsed')?.textContent).toBe('Recording · 0:00');

    // Seven seconds of wall time; ONE tick allowed to run.
    vi.setSystemTime(start + 7000);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(container.querySelector('.capture-elapsed')?.textContent).toBe('Recording · 0:07');

    /*
     * AND THE FINAL READING IS TAKEN AT STOP. Five more seconds pass with no
     * tick at all, then Stop is pressed: without `settleElapsedTimer` the
     * `held` bar would freeze whatever the last tick that managed to run had
     * said — here 0:07 for twelve seconds of audio.
     */
    vi.setSystemTime(start + 12_000);
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceStop }));
    expect(container.querySelector('.capture-elapsed')?.textContent).toBe('Held · 0:12');
    vi.useRealTimers();
  });
});

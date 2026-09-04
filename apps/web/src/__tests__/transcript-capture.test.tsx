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

function installRecorder(getUserMedia: Mock) {
  FakeMediaRecorder.instances = [];
  (globalThis as never as Record<string, unknown>).MediaRecorder = FakeMediaRecorder;
  (globalThis as never as Record<string, unknown>).Blob =
    (globalThis as never as Record<string, unknown>).Blob ?? class {};
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  });
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

  it('recording: elapsed time ticks and is cleared on stop', async () => {
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
    expect(elapsed?.textContent).toBe('Recording · 0:00');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(container.querySelector('.capture-elapsed')?.textContent).toBe('Recording · 0:05');

    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.voiceStop }));
    expect(screen.getByRole('button', { name: CAPTURE_COPY.voiceTypeWhatWasSaid })).toBeInTheDocument();
    // `held` renders no elapsed indicator at all — it belongs to `recording` only.
    expect(container.querySelector('.capture-elapsed')).toBeNull();
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

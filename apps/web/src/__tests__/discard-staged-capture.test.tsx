/*
 * DISCARDING STAGED CAPTURE INPUT — the behaviour contract, per panel.
 *
 * WHAT WOULD FAIL BEFORE THE BEHAVIOUR THIS DEFENDS. Each is a way the control could be
 * built that renders perfectly and still breaks its own promise:
 *
 *   1. A Discard that talks to the server. Nothing here has been sent, so there is
 *      nothing at the server to withdraw and no request that would mean anything — and a
 *      request that CAN fail turns "clear this box" into an operation with an error
 *      state. §"no request" below asserts the absence directly, per panel: every method
 *      the panel issued across a whole discard is `GET`.
 *   2. A Discard that fires on one click, or on close, blur or unmount. §"two acts".
 *   3. A Discard that is present-but-inert when there is nothing to discard, so a reader
 *      cannot tell an empty box from a broken control. §"absent until there is
 *      something".
 *   4. A Discard that clears the visible state and leaves the OWNER's surviving copy, so
 *      the abandoned value comes back on the next Refresh, reopen or remount. §"cancelled
 *      intent does not return" — this is the defect `GuidedCompletion.discardStaged`
 *      already exists to close for Cancel and for "I don't know", reached by a third act.
 *   5. A Discard on the transcript panel that reaches the finalized notes or an accepted
 *      value. §"what the transcript control does NOT reach".
 *
 * The COPY is pinned separately, in `discard-claim-parity.test.tsx`.
 *
 * Every fixture is synthetic and no test here reaches a backend.
 */

import { describe, it, expect, afterEach, beforeEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axe from 'axe-core';

import { AppRoutes } from '../App';
import { TranscriptCapturePanel } from '../components/TranscriptCapturePanel';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import { UnmappedNotesPanel } from '../components/UnmappedNotesPanel';
import { ConflictResolutionPanel } from '../components/ConflictResolutionPanel';
import { GuidedPrompt } from '../components/GuidedPrompt';
import { DiscardStaged } from '../components/DiscardStaged';
import { DISCARD_COPY } from '../lib/discardContent';
import {
  answersAfterNotebook,
  answersStaleWrite,
  bundleRoutes,
  conflictFixture,
  conflictsPage,
  noteFixture,
  notesPage,
  runFixture,
  runsEmpty,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { PendingBlocker } from '../lib/types';

const EXP = 'demo';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/**
 * EVERY REQUEST METHOD THE PANEL ISSUED. A discard that stayed local leaves this all
 * `GET` — which is a stronger statement than "the mutating endpoint was not called",
 * because it also catches a write to an endpoint no fixture registered.
 */
function methods(): string[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls.map(([, init]) => (init?.method ?? 'GET').toUpperCase());
}

/** The methods issued from now on, for asserting about one gesture rather than a test. */
function methodsSince(mark: number): string[] {
  return methods().slice(mark);
}

function mark(): number {
  return methods().length;
}

const trigger = (copy: { trigger: string }) =>
  screen.queryByRole('button', { name: copy.trigger });

/** Open the confirm step and commit it. Two acts, deliberately — see §"two acts". */
function discardVia(copy: { trigger: string; commit: string }) {
  fireEvent.click(screen.getByRole('button', { name: copy.trigger }));
  fireEvent.click(screen.getByRole('button', { name: copy.commit }));
}

// ═══════════════════════════════════════════════════════════════════════════════
// 0. The shared control, in isolation
// ═══════════════════════════════════════════════════════════════════════════════

describe('the control itself', () => {
  const COPY = DISCARD_COPY.noteCapture;

  function harness(staged: boolean, onDiscard = vi.fn()) {
    render(<DiscardStaged staged={staged} copy={COPY} onDiscard={onDiscard} />);
    return onDiscard;
  }

  it('is ABSENT — not disabled — when there is nothing staged', () => {
    harness(false);
    expect(trigger(COPY)).toBeNull();
    // and nothing that could be mistaken for it
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders a real <button>, keyboard-reachable, never a div with a click handler', () => {
    harness(true);
    const el = screen.getByRole('button', { name: COPY.trigger });
    expect(el.tagName).toBe('BUTTON');
    expect(el.getAttribute('type')).toBe('button');
    // In the tab order by default: no negative tabindex, no aria-hidden ancestor.
    expect(el.getAttribute('tabindex')).toBeNull();
    expect(el.closest('[aria-hidden="true"]')).toBeNull();
  });

  it('does not discard on a single click of the trigger — the confirm step is a second act', () => {
    const onDiscard = harness(true);
    fireEvent.click(screen.getByRole('button', { name: COPY.trigger }));
    expect(onDiscard).not.toHaveBeenCalled();
    // The sentence is on screen, and so are both ways out of it.
    expect(screen.getByText(COPY.body)).toBeTruthy();
    expect(screen.getByRole('button', { name: COPY.commit })).toBeTruthy();
    expect(screen.getByRole('button', { name: COPY.keep })).toBeTruthy();
  });

  it('moves focus to the committing control when the step opens, so the decision is under the caret', () => {
    harness(true);
    fireEvent.click(screen.getByRole('button', { name: COPY.trigger }));
    expect(document.activeElement).toBe(screen.getByRole('button', { name: COPY.commit }));
  });

  it('"Keep it" discards nothing and returns focus to the trigger', () => {
    const onDiscard = harness(true);
    fireEvent.click(screen.getByRole('button', { name: COPY.trigger }));
    fireEvent.click(screen.getByRole('button', { name: COPY.keep }));
    expect(onDiscard).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: COPY.trigger }));
  });

  it('Escape leaves the step exactly as "Keep it" does', () => {
    const onDiscard = harness(true);
    fireEvent.click(screen.getByRole('button', { name: COPY.trigger }));
    fireEvent.keyDown(screen.getByRole('group', { name: COPY.trigger }), { key: 'Escape' });
    expect(onDiscard).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: COPY.trigger }));
  });

  it('announces the outcome in a live region, and that region exists BEFORE it has anything to say', () => {
    const onDiscard = vi.fn();
    const { rerender } = render(
      <DiscardStaged staged copy={COPY} onDiscard={onDiscard} />,
    );
    // Mounted and empty — a live region inserted together with its content is
    // announced unreliably.
    const live = screen.getByRole('status');
    expect(live.textContent).toBe('');

    discardVia(COPY);
    expect(onDiscard).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status').textContent).toBe(COPY.announcement);

    // …and the trigger is gone, because the owner reports nothing is staged now.
    rerender(<DiscardStaged staged={false} copy={COPY} onDiscard={onDiscard} />);
    expect(trigger(COPY)).toBeNull();
  });

  it('routes the sentence into the PANEL’s live region when one is supplied, and mounts none of its own', () => {
    const onAnnounce = vi.fn();
    render(
      <DiscardStaged staged copy={COPY} onDiscard={vi.fn()} onAnnounce={onAnnounce} />,
    );
    expect(screen.queryByRole('status')).toBeNull();
    discardVia(COPY);
    expect(onAnnounce).toHaveBeenCalledWith(COPY.announcement);
  });

  it('closes the confirm step WITHOUT announcing when the staged content vanishes under it', () => {
    const onDiscard = vi.fn();
    const { rerender } = render(<DiscardStaged staged copy={COPY} onDiscard={onDiscard} />);
    fireEvent.click(screen.getByRole('button', { name: COPY.trigger }));
    expect(screen.getByText(COPY.body)).toBeTruthy();

    // The reader emptied the box by hand while the step was open.
    rerender(<DiscardStaged staged={false} copy={COPY} onDiscard={onDiscard} />);
    expect(screen.queryByText(COPY.body)).toBeNull();
    expect(onDiscard).not.toHaveBeenCalled();
    // No discard happened, so nothing is claimed to have happened.
    expect(screen.getByRole('status').textContent).toBe('');
  });

  it('reserves its row height whether or not the trigger is in it, so the form does not jump', () => {
    const { container, rerender } = render(
      <DiscardStaged staged={false} copy={COPY} onDiscard={vi.fn()} />,
    );
    const empty = container.querySelector('.discard-slot')!;
    expect(empty).toBeTruthy();
    expect(empty.getAttribute('data-staged')).toBe('no');
    rerender(<DiscardStaged staged copy={COPY} onDiscard={vi.fn()} />);
    // The SAME element is still there — the trigger appears inside a row that was
    // already occupying space, rather than the row itself appearing.
    const filled = container.querySelector('.discard-slot')!;
    expect(filled).toBe(empty);
    expect(filled.getAttribute('data-staged')).toBe('yes');
  });

  /*
   * AXE, ON BOTH STATES OF THE CONTROL. The rule set is the one the sibling panel
   * suites use, plus `button-name` and `aria-hidden-focus` — the two a quiet
   * icon-and-label trigger is most likely to break, and the two a `<button>` with an
   * `aria-hidden` glyph inside it would break if the glyph were ever made focusable.
   *
   * `color-contrast` is deliberately NOT in this list, and its absence is stated rather
   * than left implicit: jsdom computes no layout and axe cannot measure contrast in it,
   * so including it would report a clean pass over a check that never ran. The colour
   * decision is recorded in `discard.css` against the measured tokens instead.
   */
  const AXE_RULES = [
    'label',
    'button-name',
    'aria-allowed-role',
    'aria-valid-attr-value',
    'aria-hidden-focus',
    'aria-required-attr',
    'aria-required-children',
    'nested-interactive',
  ];

  it('reports no axe violation with the trigger on screen', async () => {
    const { container } = render(
      <DiscardStaged staged copy={COPY} onDiscard={vi.fn()} />,
    );
    const results = await axe.run(container, {
      runOnly: { type: 'rule', values: AXE_RULES },
      resultTypes: ['violations'],
    });
    expect(results.violations.map((v) => `${v.id} \u00d7 ${v.nodes.length}`)).toEqual([]);
  });

  it('reports no axe violation with the confirm step open', async () => {
    const { container } = render(
      <DiscardStaged staged copy={COPY} onDiscard={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: COPY.trigger }));
    const results = await axe.run(container, {
      runOnly: { type: 'rule', values: AXE_RULES },
      resultTypes: ['violations'],
    });
    expect(results.violations.map((v) => `${v.id} \u00d7 ${v.nodes.length}`)).toEqual([]);
  });

  it('cannot reach the network: the module imports no api, fetch or request helper', async () => {
    const source = await import('node:fs').then(({ readFileSync }) => {
      const { join } = require('node:path') as typeof import('node:path');
      const roots = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
      const { existsSync } = require('node:fs') as typeof import('node:fs');
      const dir = roots.find((r) => existsSync(join(r, 'main.tsx')));
      return readFileSync(join(dir!, 'components', 'DiscardStaged.tsx'), 'utf8');
    });
    const imports = source
      .split('\n')
      .filter((line) => /^\s*import\s/.test(line))
      .join('\n');
    expect(imports).not.toMatch(/lib\/api/);
    // and no ad-hoc call anywhere in the file
    expect(source).not.toMatch(/\bfetch\s*\(/);
    expect(source).not.toMatch(/XMLHttpRequest|sendBeacon|navigator\.send/);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 1. Transcript capture
// ═══════════════════════════════════════════════════════════════════════════════

describe('the transcript box', () => {
  const RUNS = `GET /api/experiments/${EXP}/runs`;
  const CAPS = 'GET /api/providers/capabilities';
  const RUN = runFixture({ id: 'run-1', label: 'Run 1', version: 'r1.0', fields: {} });
  const runsPage = {
    runs: [RUN],
    experiment_version: 'g1.4',
    total: 1,
    matched: 1,
    returned: 1,
    offset: 0,
  };
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
        reason: 'No transcription provider is configured.',
        selected_by: 'ISAAC_TRANSCRIPTION_PROVIDER',
      },
    ],
  };

  beforeEach(() => {
    try {
      localStorage.setItem(
        'isaac.transcriptCapture.guidance.v1',
        JSON.stringify({
          guidanceId: 'isaac-transcript-capture-guidance',
          version: 1,
          seen: true,
          seenAt: '2099-01-01T00:00:00Z',
        }),
      );
    } catch {
      /* the read path fails safe */
    }
  });

  async function open() {
    stubFetchRoutes({ [RUNS]: { body: runsPage }, [CAPS]: { body: capabilities } });
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Capture Experiment Notes' }));
    return screen.getByLabelText('Transcript') as HTMLTextAreaElement;
  }

  it('offers nothing while the box is empty', async () => {
    await open();
    expect(trigger(DISCARD_COPY.transcriptUnsent)).toBeNull();
  });

  it('clears the box, tells the reader nothing had been sent, and issues NO request', async () => {
    const box = await open();
    fireEvent.change(box, { target: { value: 'Notes for run 1. Temperature was 300 K.' } });
    const before = mark();

    discardVia(DISCARD_COPY.transcriptUnsent);

    expect((screen.getByLabelText('Transcript') as HTMLTextAreaElement).value).toBe('');
    // NOT "no POST to /transcript" — no non-GET request at all.
    expect(methodsSince(before)).toEqual([]);
    await waitFor(() =>
      expect(
        screen.getAllByRole('status').some(
          (el) => el.textContent === DISCARD_COPY.transcriptUnsent.announcement,
        ),
      ).toBe(true),
    );
    // Focus lands in the box that just emptied, not on <body>.
    expect(document.activeElement).toBe(screen.getByLabelText('Transcript'));
  });

  it('is gone once the box is empty, and comes back — still local — when it is not', async () => {
    const box = await open();
    fireEvent.change(box, { target: { value: 'first' } });
    discardVia(DISCARD_COPY.transcriptUnsent);
    expect(trigger(DISCARD_COPY.transcriptUnsent)).toBeNull();

    // A second discard is not a no-op that had to be coded — it is UNREACHABLE until
    // something is staged again. Stage again and discard again.
    const before = mark();
    fireEvent.change(screen.getByLabelText('Transcript'), { target: { value: 'second' } });
    discardVia(DISCARD_COPY.transcriptUnsent);
    expect((screen.getByLabelText('Transcript') as HTMLTextAreaElement).value).toBe('');
    expect(methodsSince(before)).toEqual([]);
  });

  it('CLOSING the panel still keeps the text — the deliberate behaviour this control does not replace', async () => {
    const box = await open();
    fireEvent.change(box, { target: { value: 'paragraphs worth keeping' } });
    fireEvent.click(screen.getByRole('button', { name: 'Close Capture' }));
    fireEvent.click(screen.getByRole('button', { name: 'Capture Experiment Notes' }));
    expect((screen.getByLabelText('Transcript') as HTMLTextAreaElement).value).toBe(
      'paragraphs worth keeping',
    );
  });

  it('a discarded transcript does NOT come back when the panel is closed and reopened', async () => {
    const box = await open();
    fireEvent.change(box, { target: { value: 'abandoned' } });
    discardVia(DISCARD_COPY.transcriptUnsent);
    fireEvent.click(screen.getByRole('button', { name: 'Close Capture' }));
    fireEvent.click(screen.getByRole('button', { name: 'Capture Experiment Notes' }));
    expect((screen.getByLabelText('Transcript') as HTMLTextAreaElement).value).toBe('');
    expect(trigger(DISCARD_COPY.transcriptUnsent)).toBeNull();
  });

  /*
   * ═══ THE COPY BRANCH, EXERCISED RATHER THAN ONLY PINNED ═══════════════════════
   *
   * ADDED IN REVIEW. `discard-claim-parity.test.tsx` proves the two transcript bodies say
   * the right things; nothing proved the panel SELECTS the right one, which is the half
   * that can be false on a screen. It matters more here than anywhere else in this slice:
   * after Finalize the segments ARE stored with the record as Unmapped Notes
   * (`routes.py:9936-9954` at commit `8994525` — the `EVERY SEGMENT IS STORED` loop;
   * ~~`9483-9494`~~ was a wrong pointer, corrected 2026-08-27 in all four places that
   * carried it), so the unsent body — "Nothing in it has been read or stored"
   * — becomes a false statement rendered above a box whose words are on the record.
   *
   * Three states are walked, because the branch is `reading === null` and a failed
   * finalize must NOT move it: before any finalize, after one that SUCCEEDED, and after
   * one the server REFUSED.
   */
  const CAPTURE = `POST /api/experiments/${EXP}/transcript`;
  /** The server's real answer shape, mirrored from `transcript-capture.test.tsx`. */
  const captureReading = (candidates: unknown[] = []) => ({
    capture: {
      finalized: true,
      run_id: 'run-1',
      segments: 1,
      retention: {
        state: 'retained_with_experiment',
        notes_captured: 1,
        deletable: false,
        description: 'The finalized transcript is stored with this record as notes.',
        not_implemented: [],
        raw_audio: { stored: false, reason: 'No audio reaches this server.' },
      },
    },
    applied: false,
    candidates,
    clarifications: [],
    abstentions: [],
    review_required: [],
    notes: [],
    /* ONE STORED PROPOSAL PER CANDIDATE, which is what the server now does. A
       fixture with an empty `proposals` over a non-empty `candidates` would render
       the panel's "no proposal was stored" branch for every row and quietly change
       what these Discard tests are looking at. */
    proposals: candidates.map((_, index) => ({
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
        rule: 'a rule',
        state: 'open',
        applied: false,
      },
    })),
    unproposable: [],
    ambiguity_policy: [],
    accept_contract: {
      method: 'POST',
      path: '/api/experiments/{experiment_id}/proposals/{proposal_id}/review',
      requires: ['confirmed_by_user: true'],
      message: 'This operation writes no field.',
    },
    experiment_version: 'g1.5',
  });
  const CANDIDATE = {
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
  };

  it('shows the UNSENT body while no finalize has landed', async () => {
    const box = await open();
    fireEvent.change(box, { target: { value: 'Notes for run 1.' } });
    fireEvent.click(screen.getByRole('button', { name: DISCARD_COPY.transcriptUnsent.trigger }));
    expect(screen.getByText(DISCARD_COPY.transcriptUnsent.body)).toBeInTheDocument();
    expect(screen.queryByText(DISCARD_COPY.transcriptAfterFinalize.body)).toBeNull();
  });

  it('switches to the AFTER-FINALIZE body once the words are stored as notes', async () => {
    stubFetchRoutes({
      [RUNS]: { body: runsPage },
      [CAPS]: { body: capabilities },
      [CAPTURE]: { body: captureReading() },
    });
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Capture Experiment Notes' }));
    fireEvent.change(screen.getByLabelText('Transcript'), {
      target: { value: 'Notes for run 1.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Finalize and Read' }));
    await waitFor(() =>
      expect(screen.getByLabelText('Transcript')).toHaveValue('Notes for run 1.'),
    );

    // The trigger is still offered — the box deliberately keeps its text after a
    // finalize — and it now carries the body that admits the notes are stored.
    fireEvent.click(
      screen.getByRole('button', { name: DISCARD_COPY.transcriptAfterFinalize.trigger }),
    );
    expect(
      screen.getByText(DISCARD_COPY.transcriptAfterFinalize.body),
    ).toBeInTheDocument();
    expect(screen.queryByText(DISCARD_COPY.transcriptUnsent.body)).toBeNull();

    const before = mark();
    fireEvent.click(screen.getByRole('button', { name: DISCARD_COPY.transcriptAfterFinalize.commit }));
    expect(screen.getByLabelText('Transcript')).toHaveValue('');
    // Still no request, on the branch where a request would be most tempting.
    expect(methodsSince(before)).toEqual([]);
    await waitFor(() =>
      expect(
        screen
          .getAllByRole('status')
          .some(
            (el) =>
              el.textContent === DISCARD_COPY.transcriptAfterFinalize.announcement,
          ),
      ).toBe(true),
    );
  });

  it('keeps the UNSENT body when the finalize was REFUSED — nothing was stored', async () => {
    stubFetchRoutes({
      [RUNS]: { body: runsPage },
      [CAPS]: { body: capabilities },
      [CAPTURE]: { status: 412, body: { detail: { code: 'stale_write' } } },
    });
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Capture Experiment Notes' }));
    fireEvent.change(screen.getByLabelText('Transcript'), {
      target: { value: 'Notes for run 1.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Finalize and Read' }));
    await screen.findByRole('alert');

    // A 412 is the compare-and-swap refusal: nothing was stored, so the body that says
    // so is still the true one. A branch keyed on "finalize was pressed" would be wrong
    // here; this one is keyed on the server's answer having arrived.
    fireEvent.click(
      screen.getByRole('button', { name: DISCARD_COPY.transcriptUnsent.trigger }),
    );
    expect(screen.getByText(DISCARD_COPY.transcriptUnsent.body)).toBeInTheDocument();
  });

  /*
   * TWO TESTS USED TO SIT HERE AND THEY ARE REPLACED BY ONE, WITH BOTH DEFECTS THEY
   * CLOSED NAMED RATHER THAN FORGOTTEN.
   *
   * They were "offers nothing on a fresh record, even after a proposal was edited on
   * the last one" and "offers nothing once the only edited proposal has been ACCEPTED
   * and the box emptied". Both were about `edits` — the map of values typed over a
   * proposal before accepting it — and both closed the same defect from different
   * sides: `hasStagedCapture` counted entries the reader could no longer see, so
   * Discard offered to clear something invisible, under copy reading "This clears the
   * transcript box". The first leaked across a record change; the second leaked across
   * an accept, because the row that rendered the input unmounted and neither `accept`
   * nor `reject` deleted its entry.
   *
   * `edits` NO LONGER EXISTS. The Accept control it fed is gone — a candidate is now a
   * durable proposal reviewed on the proposals surface — so the map went with it, and
   * `hasStagedCapture` is now `text !== ''`. The defect is closed by DELETION rather
   * than by a predicate, which is the stronger form; what must not be lost is the RULE
   * the two tests were enforcing, so it is asserted directly below: the control is
   * offered only for state the reader can see, and proposals on screen are not that
   * state — they are the server's answer, not a staged edit.
   */
  it('offers nothing once the box is empty, however many proposals are on screen', async () => {
    stubFetchRoutes({
      [RUNS]: { body: runsPage },
      [CAPS]: { body: capabilities },
      [CAPTURE]: { body: captureReading([CANDIDATE]) },
    });
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Capture Experiment Notes' }));
    fireEvent.change(screen.getByLabelText('Transcript'), {
      target: { value: 'Temperature was 300 K.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Finalize and Read' }));
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 0));

    // The reader empties the box themselves. The proposal row is STILL on screen —
    // which is the case the old tests were reaching for — and nothing about it is
    // staged, so nothing may be offered.
    fireEvent.change(screen.getByLabelText('Transcript'), { target: { value: '' } });
    expect(screen.getByText(CAPTURE_COPY.summaryStored(1, 0))).toBeInTheDocument();
    expect(trigger(DISCARD_COPY.transcriptAfterFinalize)).toBeNull();
    expect(trigger(DISCARD_COPY.transcriptUnsent)).toBeNull();
  });

  it('offers nothing on a fresh record, whatever the last one was showing', async () => {
    stubFetchRoutes({
      [RUNS]: { body: runsPage },
      [`GET /api/experiments/other/runs`]: { body: runsPage },
      [CAPS]: { body: capabilities },
      [CAPTURE]: { body: captureReading([CANDIDATE]) },
    });
    const view = render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Capture Experiment Notes' }));
    fireEvent.change(screen.getByLabelText('Transcript'), {
      target: { value: 'Temperature was 300 K.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Finalize and Read' }));
    await screen.findByText(CAPTURE_COPY.summaryStored(1, 0));

    // Same mounted component, different record — the panel is not keyed on the id.
    view.rerender(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId="other" />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByLabelText('Transcript')).toHaveValue(''));
    expect(trigger(DISCARD_COPY.transcriptUnsent)).toBeNull();
    expect(trigger(DISCARD_COPY.transcriptAfterFinalize)).toBeNull();
  });

  /*
   * THE HELD AUDIO IS NOT ASSERTED HERE, and the omission is stated rather than left
   * as a gap. `Discard audio` renders only when `audioRecordingAvailable()` is true,
   * and jsdom has no `MediaRecorder`, so the panel takes its `voice === 'unsupported'`
   * branch in every test environment and the control is not in the DOM to assert
   * about. What CAN be shown from here is that the two are different acts in the
   * source: `discardAudio` calls `dropAudio` and touches neither `text` nor `edits`,
   * and `discardStagedCapture` touches neither the recorder nor `chunksRef`. A test
   * that rendered a fake recorder would be asserting against the fake.
   */
});

// ═══════════════════════════════════════════════════════════════════════════════
// 2. The note capture box
// ═══════════════════════════════════════════════════════════════════════════════

describe('the note capture box', () => {
  const NOTES = `GET /api/experiments/${EXP}/notes`;
  const COPY = DISCARD_COPY.noteCapture;

  async function open() {
    stubFetchRoutes({
      [NOTES]: { body: notesPage([noteFixture({ id: 'N-1' })]) },
    });
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <UnmappedNotesPanel experimentId={EXP} />
      </MemoryRouter>,
    );
    return (await screen.findByLabelText('Capture a note')) as HTMLTextAreaElement;
  }

  it('offers nothing while the box is empty', async () => {
    await open();
    expect(trigger(COPY)).toBeNull();
  });

  it('clears the box and issues NO request', async () => {
    const box = await open();
    fireEvent.change(box, { target: { value: 'the cryostat rattled' } });
    const before = mark();

    discardVia(COPY);

    expect((screen.getByLabelText('Capture a note') as HTMLTextAreaElement).value).toBe('');
    expect(methodsSince(before)).toEqual([]);
    expect(document.activeElement).toBe(screen.getByLabelText('Capture a note'));
  });

  it('announces through the PANEL’s one act-announcement region, not a second one', async () => {
    const box = await open();
    fireEvent.change(box, { target: { value: 'something' } });
    discardVia(COPY);
    // `getByRole` — singular — is the assertion: exactly one status region in the panel.
    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toBe(COPY.announcement),
    );
  });

  it('never touches the notes already on the record', async () => {
    const box = await open();
    const noteText = screen.getByText(noteFixture({ id: 'N-1' }).display_text);
    fireEvent.change(box, { target: { value: 'draft' } });
    discardVia(COPY);
    expect(noteText).toBeInTheDocument();
    expect(methods().every((m) => m === 'GET')).toBe(true);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 3. The conflict decision form
// ═══════════════════════════════════════════════════════════════════════════════

describe('the conflict decision form', () => {
  const CONFLICTS = `GET /api/experiments/${EXP}/conflicts`;
  const RUNS = `GET /api/experiments/${EXP}/runs`;
  const COPY = DISCARD_COPY.conflictDecision;

  async function open() {
    stubFetchRoutes({
      [CONFLICTS]: { body: conflictsPage([conflictFixture()]) },
      [RUNS]: { body: runsEmpty },
    });
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <ConflictResolutionPanel experimentId={EXP} />
      </MemoryRouter>,
    );
    await screen.findByText('LiFePO4');
  }

  it('offers nothing while the form is at rest — nothing is selected on arrival', async () => {
    await open();
    expect(trigger(COPY)).toBeNull();
  });

  it('appears once ANY of the four inputs is touched, including the attestation alone', async () => {
    await open();
    const attest = screen.getByLabelText(/I am recording this decision myself/);
    fireEvent.click(attest);
    expect(trigger(COPY)).toBeTruthy();
  });

  it('empties the selection, the typed value, the reason and the attestation — with NO request', async () => {
    await open();
    fireEvent.click(
      screen.getByLabelText('A different value — none of the recorded answers is right'),
    );
    fireEvent.change(screen.getByLabelText('The value you stand behind'), {
      target: { value: 'LiFePO4' },
    });
    fireEvent.change(screen.getByLabelText('Why (optional)'), {
      target: { value: 'the notebook says so' },
    });
    fireEvent.click(screen.getByLabelText(/I am recording this decision myself/));
    const before = mark();

    discardVia(COPY);

    // The typed-value box is unmounted with its radio, so the radio is the assertion.
    expect(
      (screen.getByLabelText(
        'A different value — none of the recorded answers is right',
      ) as HTMLInputElement).checked,
    ).toBe(false);
    expect(screen.queryByLabelText('The value you stand behind')).toBeNull();
    expect((screen.getByLabelText('Why (optional)') as HTMLTextAreaElement).value).toBe('');
    expect(
      (screen.getByLabelText(/I am recording this decision myself/) as HTMLInputElement)
        .checked,
    ).toBe(false);
    expect(methodsSince(before)).toEqual([]);
    expect(trigger(COPY)).toBeNull();
  });

  it('leaves the conflict, its competing answers and the primary control exactly where they were', async () => {
    await open();
    fireEvent.change(screen.getByLabelText('Why (optional)'), { target: { value: 'x' } });
    discardVia(COPY);
    expect(screen.getByText('LiFePO4')).toBeInTheDocument();
    expect(screen.getByText('LiFePO3')).toBeInTheDocument();
    // The decision control is still there, and still refuses an empty form.
    const submit = screen.getByRole('button', { name: 'Record This Decision' });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 4. One completion question
// ═══════════════════════════════════════════════════════════════════════════════

describe('one completion question', () => {
  const COPY = DISCARD_COPY.guidedAnswer;

  /*
   * `GuidedPrompt` makes no read of its own — every value it renders arrives as a prop
   * — so nothing here registers a route. The stub is installed anyway, un-routed, so
   * that `methods()` can state the strong form of the claim: not "the write endpoint
   * was not called" but "no request of any kind was issued", which is what an EMPTY
   * call list says.
   */
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  const hashBlocker: PendingBlocker = {
    id: 'assets[0].sha256',
    key: 'assets[0].sha256',
    kind: 'asset_hash',
    question: 'What is the sha256 of the notebook?',
    label: 'Asset Hash',
    path: 'assets[0].sha256',
    inputType: 'hash',
  };

  const verdictBlocker: PendingBlocker = {
    id: 'qc',
    key: 'qc',
    kind: 'qc',
    question: 'Was the spectrum usable?',
    label: 'QC verdict',
    path: 'measurement.qc',
    inputType: 'verdict',
  };

  function mount(blocker: PendingBlocker, onDiscardStaged = vi.fn()) {
    const onConfirm = vi.fn();
    render(
      <GuidedPrompt
        blocker={blocker}
        index={0}
        total={1}
        onConfirm={onConfirm}
        onDontKnow={vi.fn()}
        onDiscardStaged={onDiscardStaged}
      />,
    );
    return { onConfirm, onDiscardStaged };
  }

  it('is not mounted at all when the owner cannot also drop its surviving copy', () => {
    render(
      <GuidedPrompt
        blocker={hashBlocker}
        index={0}
        total={1}
        onConfirm={vi.fn()}
        onDontKnow={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText('Asset Hash'), { target: { value: 'abc' } });
    expect(trigger(COPY)).toBeNull();
  });

  it('offers nothing on a blank question', () => {
    mount(hashBlocker);
    expect(trigger(COPY)).toBeNull();
  });

  it('clears the box, drops the owner’s copy, confirms nothing, and issues NO request', () => {
    const { onConfirm, onDiscardStaged } = mount(hashBlocker);
    fireEvent.change(screen.getByLabelText('Asset Hash'), { target: { value: 'ABANDONED' } });
    const before = mark();

    discardVia(COPY);

    expect((screen.getByLabelText('Asset Hash') as HTMLInputElement).value).toBe('');
    // The surviving copy a Refresh would read is dropped — otherwise the abandoned
    // value returns pre-filled, one click from being confirmed.
    expect(onDiscardStaged).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(methodsSince(before)).toEqual([]);
    expect(trigger(COPY)).toBeNull();
  });

  it('appears on a HALF-finished verdict, which is where it is worth most', () => {
    mount(verdictBlocker);
    // A verdict with no reasoning cannot be confirmed…
    fireEvent.click(screen.getByLabelText('compromised'));
    expect(
      (screen.getByRole('button', { name: 'Confirm' }) as HTMLButtonElement).disabled,
    ).toBe(true);
    // …and is still the reader's work, so it can still be discarded.
    expect(trigger(COPY)).toBeTruthy();
  });

  it('empties BOTH halves of a verdict, which one control has to do because they are one answer', () => {
    mount(verdictBlocker);
    fireEvent.click(screen.getByLabelText('compromised'));
    fireEvent.change(screen.getByLabelText('How was it determined?'), {
      target: { value: 'the cryostat rattled halfway through' },
    });

    discardVia(COPY);

    expect((screen.getByLabelText('compromised') as HTMLInputElement).checked).toBe(false);
    expect(
      (screen.getByLabelText('How was it determined?') as HTMLTextAreaElement).value,
    ).toBe('');
    expect(trigger(COPY)).toBeNull();
  });

  it('does not replace "I don’t know" — the two acts stay separate controls', () => {
    mount(hashBlocker);
    fireEvent.change(screen.getByLabelText('Asset Hash'), { target: { value: 'x' } });
    expect(
      screen.getByRole('button', { name: "I don't know — leave honestly missing" }),
    ).toBeTruthy();
    expect(trigger(COPY)).toBeTruthy();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 5. …and through the real screen: cancelled intent does not return
// ═══════════════════════════════════════════════════════════════════════════════

describe('a discarded answer does not come back on the completion screen', () => {
  const COPY = DISCARD_COPY.guidedAnswer;

  /*
   * THE PROPERTY THIS SECTION EXISTS FOR, AND WHY THE ISOLATED TEST ABOVE IS NOT ENOUGH.
   *
   * `GuidedCompletion` deliberately holds staged input in a ref ABOVE the component
   * `Refresh` unmounts, so a reload cannot destroy what a reader typed — and three
   * banners on that screen say so beside the Refresh button. The consequence is that
   * clearing the visible boxes is only half a discard: if the ref still holds the value,
   * the very next Refresh puts it back, pre-filled, one click from being confirmed. That
   * is the exact defect `discardStaged` was written to close for `Cancel` and for "I
   * don't know"; a third act reaching the same ref has to be wired to the same drop.
   *
   * The isolated test above proves the callback FIRES. This one proves it is wired to
   * something that works, through the screen's own Refresh.
   */
  it('survives a Refresh as an EMPTY box — the ref the reload reads is dropped too', async () => {
    /*
     * The Refresh control is only on screen once the record reports it changed
     * elsewhere, so a 412 on the answer path is how a test reaches the exact banner
     * whose sentence this asserts about: "What you typed is kept, including through
     * Refresh". True of what you typed. It must NOT be true of what you discarded.
     */
    const calls = stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': { status: 412, body: answersStaleWrite },
    });
    render(
      <MemoryRouter
        initialEntries={['/record/demo/complete']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    const box = (await screen.findByLabelText('Asset Hash')) as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'ABANDONED-ANSWER' } });
    fireEvent.click(screen.getByText('Confirm'));
    // The refusal keeps the input and puts Refresh on screen.
    await screen.findByText(/what you typed is kept, including through Refresh/);
    expect((screen.getByLabelText('Asset Hash') as HTMLInputElement).value).toBe(
      'ABANDONED-ANSWER',
    );

    const before = mark();
    discardVia(COPY);
    expect((screen.getByLabelText('Asset Hash') as HTMLInputElement).value).toBe('');
    expect(methodsSince(before)).toEqual([]);

    // Now press the button whose own banner promises that what you typed is kept.
    const reads = calls.filter((c) => c === 'GET /api/experiments/demo').length;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() =>
      expect(calls.filter((c) => c === 'GET /api/experiments/demo').length).toBeGreaterThan(
        reads,
      ),
    );
    const reloaded = (await screen.findByLabelText('Asset Hash')) as HTMLInputElement;
    expect(reloaded.value).toBe('');
    // …and with nothing staged, the control is gone rather than sitting there inert.
    expect(trigger(COPY)).toBeNull();
  });

  it('the control is absent on an EDIT of an answered question — Cancel already abandons it there', async () => {
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': { body: answersAfterNotebook },
    });
    render(
      <MemoryRouter
        initialEntries={['/record/demo/complete']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    const box = (await screen.findByLabelText('Asset Hash')) as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'c'.repeat(64) } });
    fireEvent.click(screen.getByText('Confirm'));
    await screen.findByText('1 / 5');

    // The answered row's Edit opens the same prompt with `Cancel` as its secondary act.
    fireEvent.click(document.querySelector('.answered-edit') as HTMLElement);
    await screen.findByRole('button', { name: 'Cancel' });
    // One abandon, not two that read alike.
    expect(trigger(COPY)).toBeNull();
  });
});

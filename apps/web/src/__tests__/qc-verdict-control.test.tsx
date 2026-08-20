/**
 * The QC verdict control — the last thing standing between a scientist and a finished
 * record, and the reason the backend fix alone was not the product fix.
 *
 * WHAT WAS WRONG
 * ==============
 * A `qc` blocker got `inputType: 'text'`, so the app rendered a free-text box. Whatever
 * was typed went to `POST /answers` as a bare string, and the API requires
 * `{status, evidence}` with `status` inside the official enum (`complete.is_qc_shaped`).
 * So the value was declined, the question stayed open, and nothing on screen said why.
 * A record created in this application could never be completed.
 *
 * The backend half of that is pinned by `apps/api/tests/test_qc_answerable.py`. This
 * file pins the half a scientist actually touches, and in particular the three
 * properties that make it honest rather than merely functional:
 *
 *   1. NOTHING IS PRESELECTED. The blocker says "there is no default and none is
 *      assumed — not even 'valid'", and a control that arrives with a verdict chosen
 *      would assume one by doing nothing.
 *   2. THE VERDICT AND ITS REASONING TRAVEL TOGETHER — a PRODUCT decision stricter
 *      than any backend rule, and this comment used to justify it with a rule that does
 *      not exist ("the draft validator refuses a verdict with no provenance"). It does
 *      not: `complete.apply_answers` writes the `block_evidence` confirmation
 *      unconditionally, so a note-less verdict exports clean —
 *      `test_qc_answerable.py::test_a_note_less_verdict_is_accepted_and_exports_...`
 *      pins that. What IS true is that `portal_warnings.QC_NONVALID_WITHOUT_EVIDENCE`
 *      fires (advisory, non-gating) for a non-`valid` verdict with no evidence, and
 *      that a verdict recorded without reasoning is a scientific judgement with no
 *      trail. That is the reason; the borrowed refusal was not.
 *   3. WHAT IS SUBMITTED IS THE SHAPE THE API ACCEPTS — a negative control on the
 *      exact regression that caused this, which no type checker catches because
 *      `onConfirm` takes `unknown`.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { GuidedPrompt } from '../components/GuidedPrompt';
import { QC_VERDICTS } from '../lib/types';
import type { PendingBlocker } from '../lib/types';

const QC_BLOCKER: PendingBlocker = {
  id: 'qc',
  key: 'qc',
  kind: 'qc',
  question:
    'What is the QC verdict for this measurement (valid/compromised/failed/pending) and how was it determined?',
  label: 'QC verdict',
  path: 'measurement.qc.status',
  about: 'qc_status',
  inputType: 'verdict',
  inferability: {
    field: 'qc_status',
    state: 'not_inferable',
    explanation:
      "A QC verdict is a scientific judgement about this measurement. There is no default and none is assumed — not even 'valid'.",
    value: null,
    provenance: null,
    detail: {},
  },
};

function renderPrompt(overrides: Partial<PendingBlocker> = {}) {
  const onConfirm = vi.fn();
  render(
    <GuidedPrompt
      blocker={{ ...QC_BLOCKER, ...overrides }}
      index={0}
      total={1}
      onConfirm={onConfirm}
      onDontKnow={vi.fn()}
    />,
  );
  return { onConfirm };
}

describe('the QC verdict blocker offers a control that can actually answer it', () => {
  it('renders one option per official verdict, and none is preselected', () => {
    renderPrompt();
    for (const verdict of QC_VERDICTS) {
      const option = screen.getByRole('radio', { name: verdict });
      expect(option).not.toBeChecked();
    }
    // NEGATIVE CONTROL for a silently widened enum: exactly four, no more.
    expect(screen.getAllByRole('radio')).toHaveLength(QC_VERDICTS.length);
  });

  it('does NOT render a free-text box, which is what used to be here', () => {
    renderPrompt();
    expect(screen.queryByPlaceholderText('type a value…')).toBeNull();
  });

  it('refuses to submit a verdict with no reasoning', () => {
    const { onConfirm } = renderPrompt();

    fireEvent.click(screen.getByRole('radio', { name: 'valid' }));
    const confirm = screen.getByRole('button', { name: /confirm/i });
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('refuses to submit reasoning with no verdict', () => {
    const { onConfirm } = renderPrompt();

    fireEvent.change(screen.getByLabelText(/how was it determined/i), {
      target: { value: 'I0 was stable throughout.' },
    });
    expect(screen.getByRole('button', { name: /confirm/i })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('submits the exact shape the API accepts', () => {
    const { onConfirm } = renderPrompt();

    fireEvent.click(screen.getByRole('radio', { name: 'compromised' }));
    fireEvent.change(screen.getByLabelText(/how was it determined/i), {
      target: { value: 'Beam dropped during scan 3.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

    // NEGATIVE CONTROL for the regression that caused this whole defect: a bare string
    // here is refused by `complete.is_qc_shaped` and leaves the question open forever.
    // `onConfirm` takes `unknown`, so nothing but this assertion catches it.
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith({
      status: 'compromised',
      evidence: 'Beam dropped during scan 3.',
    });
  });

  it('trims the note but never invents one from whitespace', () => {
    const { onConfirm } = renderPrompt();
    const note = () => screen.getByLabelText(/how was it determined/i);

    fireEvent.click(screen.getByRole('radio', { name: 'failed' }));
    fireEvent.change(note(), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: /confirm/i })).toBeDisabled();

    fireEvent.change(note(), { target: { value: '  Sample degraded.  ' } });
    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    expect(onConfirm).toHaveBeenCalledWith({
      status: 'failed',
      evidence: 'Sample degraded.',
    });
  });

  it("states that nothing is assumed, rather than only behaving that way", () => {
    renderPrompt();
    // The server's own inferability sentence, rendered verbatim.
    expect(
      screen.getByText(/There is no default and none is assumed/i),
    ).toBeInTheDocument();
  });

  it('still renders a free-text control for an ordinary text blocker', () => {
    // NEGATIVE CONTROL for over-reach: the verdict branch must not have captured
    // every blocker that is not structured or a hash.
    renderPrompt({ id: 'beamline', kind: 'beamline', inputType: 'text', path: 'system.beamline' });
    expect(screen.getByPlaceholderText('type a value…')).toBeInTheDocument();
    expect(screen.queryAllByRole('radio')).toHaveLength(0);
  });

  it('reports every keystroke and selection upward so a Refresh cannot destroy them', () => {
    // NEGATIVE CONTROL for a re-occurrence of a defect this project has fixed before:
    // `GuidedCompletion` renders "What you typed is kept, including through Refresh"
    // beside a Refresh button, and keeps staged input in a ref above the prompt. That
    // channel carried only `text`, so a verdict and a paragraph of reasoning were
    // silently discarded by the very button the sentence reassures the reader about.
    const onStagedChange = vi.fn();
    render(
      <GuidedPrompt
        blocker={QC_BLOCKER}
        index={0}
        total={1}
        onConfirm={vi.fn()}
        onDontKnow={vi.fn()}
        onStagedChange={onStagedChange}
      />,
    );

    fireEvent.click(screen.getByRole('radio', { name: 'failed' }));
    expect(onStagedChange).toHaveBeenLastCalledWith({ status: 'failed', evidence: '' });

    fireEvent.change(screen.getByLabelText(/how was it determined/i), {
      target: { value: 'Sample degraded.' },
    });
    expect(onStagedChange).toHaveBeenLastCalledWith({
      status: 'failed',
      evidence: 'Sample degraded.',
    });
  });

  it('reopens with the staged value it was given, rather than blank', () => {
    // The other half of the same promise: the owner hands the survivor back through
    // `initialValue`. It was typed `string`, so a verdict's object value could not
    // travel and the edit form opened with blank radios and a blank note — contradicting
    // the screen's own claim that an edit is "prefilled with the current value".
    render(
      <GuidedPrompt
        blocker={QC_BLOCKER}
        index={0}
        total={1}
        initialValue={{ status: 'compromised', evidence: 'Beam dropped during scan 3.' }}
        onConfirm={vi.fn()}
        onDontKnow={vi.fn()}
      />,
    );
    expect(screen.getByRole('radio', { name: 'compromised' })).toBeChecked();
    expect(screen.getByLabelText(/how was it determined/i)).toHaveValue(
      'Beam dropped during scan 3.',
    );
  });

  it('says that both halves are required, rather than only disabling the button', () => {
    // A scientist who picks a verdict and stops otherwise sees a dead control with no
    // explanation, and a screen-reader user gets less than that.
    renderPrompt();
    expect(screen.getByText(/Both the verdict and how you determined it are required/i))
      .toBeInTheDocument();
    const note = screen.getByLabelText(/how was it determined/i);
    expect(note).toHaveAttribute('aria-required', 'true');
    expect(note.getAttribute('aria-describedby')).toBeTruthy();
  });
});

describe('a question that belongs to a run says which run', () => {
  it('renders the owning run, so identical cards are distinguishable', () => {
    // CRITICAL REGRESSION TEST. Three runs each needing a QC verdict produce three
    // blockers whose `id`, `question`, `label` and `path` are byte-identical. `runLabel`
    // was carried through the adapter and read by NO component, so a scientist saw N
    // identical cards with nothing to tell them apart — measured by an independent
    // review.
    render(
      <GuidedPrompt
        blocker={{ ...QC_BLOCKER, runId: '01RUNAAAAAAAAAAAAAAAAAAAA0', runLabel: '400 K' }}
        index={0}
        total={1}
        onConfirm={vi.fn()}
        onDontKnow={vi.fn()}
      />,
    );
    expect(screen.getByText('400 K')).toBeInTheDocument();
  });

  it('shows no owner for a record-level question', () => {
    // NEGATIVE CONTROL: a record with no runs must look exactly as it did.
    renderPrompt();
    expect(screen.queryByText(/^Run$/)).toBeNull();
  });
});

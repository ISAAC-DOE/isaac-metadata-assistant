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
 *   2. THE VERDICT AND ITS REASONING TRAVEL TOGETHER, because the draft validator
 *      refuses a verdict with no provenance and would otherwise block the export one
 *      screen later, with nothing connecting the two.
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
});

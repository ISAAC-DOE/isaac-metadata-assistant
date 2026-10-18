/*
 * B-02 (agent half) — "Identify the Next Missing Field" printed a raw internal key.
 *
 * The Agent Action built its label in `useRecordSession.toPendingItems`, on a ladder whose
 * first rung was `about` verbatim, so on a record created through `POST /api/experiments`
 * it said `The next pending field is "reduced_spectrum"` beside the typed answer's
 * "Reduced Spectrum". The ladder now maps a bare internal key through the SAME mirror the
 * chip and the screens use (`adapt.blockerDisplayName`) and leaves a real locator alone.
 */
import { describe, expect, it } from 'vitest';
import { toPendingItems } from '../lib/useRecordSession';
import { runIntent } from '../lib/assistantAgent';
import type { ApiPendingItem } from '../lib/types';

const item = (over: Record<string, unknown>) =>
  ({ id: 'series', kind: 'series', question: 'Provide the spectrum.', about: null, ...over }) as unknown as ApiPendingItem;

describe('toPendingItems — the agent’s label for a pending entry (B-02)', () => {
  it('maps each of the three internal keys to the server’s words', () => {
    const labels = toPendingItems([
      item({ about: 'reduced_spectrum' }),
      item({ id: 'qc', kind: 'qc', about: 'qc_status' }),
      item({ id: 'r', kind: 'r', about: 'required_for_evidence_record' }),
    ]).map((p) => p.label);
    expect(labels).toEqual(['Reduced Spectrum', 'QC Status', 'Required For Evidence Record']);
  });

  it('leaves a real locator verbatim', () => {
    const locator = 'ssrl-archive://BL15-2/2099_run_000/raw/scan_0044.dat';
    expect(toPendingItems([item({ about: locator })])[0].label).toBe(locator);
  });

  it('keeps the rest of the ladder: question, then id, then the server’s reason', () => {
    expect(toPendingItems([item({ about: null })])[0].label).toBe('Provide the spectrum.');
    expect(toPendingItems([item({ about: null, question: null })])[0].label).toBe('series');
  });
});

describe('identify_next_missing_field — end to end through the label (B-02)', () => {
  it('names the field in words, not as a key', () => {
    const pending = toPendingItems([item({ about: 'reduced_spectrum' })]);
    const result = runIntent(
      'identify_next_missing_field',
      {
        workflow: { current_step: null, ordered_steps: [] },
        evidence: [],
        pending,
      } as never,
      {},
    );
    expect(result.text).toContain('"Reduced Spectrum"');
    expect(result.text).not.toContain('reduced_spectrum');
  });
});

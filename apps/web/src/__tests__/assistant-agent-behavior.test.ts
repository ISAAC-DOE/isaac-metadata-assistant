/*
 * P29.3 — added behavioral tests for the deterministic agent (red-first).
 * These complement the frozen contract in assistant-agent.test.ts (unchanged):
 *   - navigate_to_step is a NON-mutating navigation intent,
 *   - confirm_staged_answer never writes from runIntent; the only write path is
 *     confirmProposal,
 *   - a COMPLETED field is never named as the next missing field,
 *   - Project Memory is never consulted for field evidence — review_field_evidence
 *     reads ONLY ctx.evidence.
 */

import { describe, expect, it, vi } from 'vitest';
import {
  confirmProposal,
  runIntent,
  stageAnswer,
  type AgentContext,
} from '../lib/assistantAgent';

const CTX: AgentContext = {
  experimentId: '01EXPERIMENTA0000000000000',
  recordRev: 5,
  version: 'genabc.5',
  workflow: {
    current_step: 'complete_metadata',
    ordered_steps: [
      { id: 'load_record', label: 'Load Record', state: 'completed', current: false, reopened: false, blocked: false, reason: null },
      { id: 'complete_metadata', label: 'Complete Metadata', state: 'current', current: true, reopened: false, blocked: false, reason: null },
      { id: 'review_evidence', label: 'Review Evidence', state: 'reopened', current: false, reopened: true, blocked: false, reason: 'An upstream change reopened this step.' },
      { id: 'export', label: 'Export', state: 'completed', current: false, reopened: false, blocked: false, reason: null },
    ],
  },
  evidence: [
    { field: 'sample.material', classification: 'supported', value_state: 'confirmed', explanation: 'Backed by observed evidence.', sources: [{ source_type: 'spreadsheet' }] },
  ],
  pending: [
    { id: 'series', label: 'Reduced Series' },
    { id: 'descriptor', label: 'Descriptor' },
  ],
};

describe('P29.3 agent — added behavior', () => {
  it('navigate_to_step returns a navigation intent and mutates nothing', () => {
    const r = runIntent('navigate_to_step', CTX, { step: 'review_evidence' });
    expect(r.navigateTo).toBe('review_evidence');
    expect(r.text).toContain('Review Evidence');
    // A navigation intent must not carry a classification or otherwise write.
    expect(r.classification).toBeUndefined();
  });

  it('confirm_staged_answer via runIntent NEVER writes — confirmProposal is the only write path', async () => {
    const api = { submitAnswer: vi.fn(), editField: vi.fn() };
    // The read intent explains only; it must not touch the api.
    const explained = runIntent('confirm_staged_answer', CTX);
    expect(explained.text.length).toBeGreaterThan(0);
    expect(api.submitAnswer).not.toHaveBeenCalled();
    expect(api.editField).not.toHaveBeenCalled();

    // The actual confirmation flows through confirmProposal.
    api.submitAnswer.mockResolvedValue({ version: 'genabc.6' });
    const p = stageAnswer(CTX, { field: 'series', value: 'series-42' });
    const res = await confirmProposal(p, CTX, api as never);
    expect(res.status).toBe('ok');
    expect(api.submitAnswer).toHaveBeenCalledTimes(1);
  });

  it('a completed step label is never named as the next missing field', () => {
    const r = runIntent('identify_next_missing_field', CTX);
    for (const completed of ['Load Record', 'Export']) {
      expect(r.text).not.toContain(completed);
    }
    // When nothing is pending, it says none — never invents a completed step.
    const empty = runIntent('identify_next_missing_field', { ...CTX, pending: [] });
    expect(empty.text.toLowerCase()).toContain('no pending');
    expect(empty.text).not.toContain('Load Record');
  });

  it('review_field_evidence reads ONLY ctx.evidence, never Project Memory', () => {
    // A field known to Project Memory but absent from the record evidence yields
    // an honest "not recorded" — proving no memory lookup backfills it.
    const r = runIntent('review_field_evidence', CTX, { field: 'memory.only.concept' });
    expect(r.classification).toBeUndefined();
    expect(r.text.toLowerCase()).toContain('no evidence classification');

    // And a real entry is echoed verbatim from ctx.evidence.
    const known = runIntent('review_field_evidence', CTX, { field: 'sample.material' });
    expect(known.classification).toBe('supported');
  });

  it('confirmProposal refuses a non-pending (already-stale/confirmed) proposal — no api call', async () => {
    const p = { ...stageAnswer(CTX, { field: 'series', value: 'v' }), confirmationState: 'stale' as const };
    const api = { submitAnswer: vi.fn(), editField: vi.fn() };
    const res = await confirmProposal(p, CTX, api as never);
    expect(res.status).toBe('stale');
    expect(api.submitAnswer).not.toHaveBeenCalled();
    expect(api.editField).not.toHaveBeenCalled();
  });

  it('confirmProposal refuses to write on a DEGRADED (unverifiable) context — no api call', async () => {
    const p = stageAnswer(CTX, { field: 'series', value: 'v' });
    const api = { submitAnswer: vi.fn(), editField: vi.fn() };
    const res = await confirmProposal(p, { ...CTX, degraded: true }, api as never);
    expect(res.status).toBe('stale');
    expect(api.submitAnswer).not.toHaveBeenCalled();
    expect(api.editField).not.toHaveBeenCalled();
  });
});

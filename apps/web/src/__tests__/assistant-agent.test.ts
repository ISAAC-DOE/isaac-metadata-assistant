/*
 * P29.3 — bounded DETERMINISTIC workflow agent (authority + proposal/confirmation).
 *
 * TEST-FIRST (orchestrator-authored, RED until lib/assistantAgent.ts exists).
 * The agent is a bounded typed-intent state machine over the P28 authoritative
 * context (workflow + evidence classification + pending + record rev). It EXPLAINS
 * and STAGES; it never confirms scientific values on its own, never strengthens a
 * classification, never guesses Unknown, never resolves a conflict, never uses
 * Project Memory as record evidence, never claims current state without version
 * verification, and never silently retries/auto-merges after a stale conflict.
 * NO external LLM. These are the truth-critical authority invariants.
 */

import { describe, expect, it, vi } from 'vitest';
import { confirmProposal, runIntent, stageAnswer } from '../lib/assistantAgent';
import type { AgentContext } from '../lib/assistantAgent';

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
      { id: 'review_export_readiness', label: 'Review Export Readiness', state: 'blocked', current: false, reopened: false, blocked: true, reason: "Complete 'Complete Metadata' first." },
      { id: 'export', label: 'Export', state: 'completed', current: false, reopened: false, blocked: false, reason: null },
    ],
  },
  evidence: [
    { field: 'sample.material', classification: 'supported', value_state: 'confirmed', explanation: 'Backed by observed evidence.', sources: [{ source_type: 'spreadsheet' }] },
    { field: 'xas.edge', classification: 'inferred_candidate', value_state: 'candidate', explanation: 'Proposed by a derivation rule; unconfirmed.', sources: [{ source_type: 'derivation' }] },
    { field: 'sample.mass_mg', classification: 'conflicting_evidence', value_state: 'candidate', explanation: 'Evidence asserts incompatible values.', sources: [{ source_type: 'user_confirmation' }, { source_type: 'user_confirmation' }] },
    { field: 'sample.origin', classification: 'unknown', value_state: 'none', explanation: 'No defensible value.', sources: [] },
  ],
  pending: [
    { id: 'series', label: 'Reduced Series' },
    { id: 'descriptor', label: 'Descriptor' },
  ],
};

describe('P29.3 deterministic agent — authority (read intents)', () => {
  it('identify_next_missing_field returns the ACTUAL first pending field, not a completed one', () => {
    const r = runIntent('identify_next_missing_field', CTX);
    expect(r.text).toContain('Reduced Series');
    expect(r.text).not.toContain('Load Record');
  });

  it('explain_current_state uses the authoritative current step', () => {
    expect(runIntent('explain_current_state', CTX).text).toContain('Complete Metadata');
  });

  it('explain_reopened_step uses the backend reason, not an invented one', () => {
    const r = runIntent('explain_reopened_step', CTX);
    expect(r.text).toContain('Review Evidence');
    expect(r.text).toContain('An upstream change reopened this step.');
  });

  it('review_field_evidence returns the backend classification VERBATIM (never strengthened)', () => {
    const cand = runIntent('review_field_evidence', CTX, { field: 'xas.edge' });
    expect(cand.classification).toBe('inferred_candidate');
    expect(cand.text.toLowerCase()).not.toContain('supported'); // must not upgrade a candidate
  });

  it('show_inferred_candidates labels candidates unconfirmed and never as fact', () => {
    const r = runIntent('show_inferred_candidates', CTX);
    expect(r.text).toContain('xas.edge');
    expect(r.text.toLowerCase()).toMatch(/candidate|unconfirmed|not entered as fact/);
  });

  it('review_evidence_conflicts presents the conflict without picking a winner', () => {
    const r = runIntent('review_evidence_conflicts', CTX);
    expect(r.text).toContain('sample.mass_mg');
    expect(r.text.toLowerCase()).toMatch(/human|resolve|person|both/);
  });

  it('explain_unknown states Unknown without guessing a value', () => {
    const r = runIntent('explain_unknown', CTX);
    expect(r.text).toContain('sample.origin');
    expect(r.text.toLowerCase()).toMatch(/unknown|no defensible|not.*determine/);
  });

  it('never renders a verdict (no PASS/FAIL / validity claim) from any read intent', () => {
    for (const intent of ['explain_current_state', 'review_field_evidence', 'review_evidence_conflicts', 'explain_unknown']) {
      const r = runIntent(intent, CTX, { field: 'sample.material' });
      expect(/\b(PASS|FAIL)\b/.test(r.text)).toBe(false);
      expect(/\b(in)?valid against\b/i.test(r.text)).toBe(false);
    }
  });

  it('a degraded context yields the exact honest "cannot verify" message, never a fabricated answer', () => {
    const degraded = { ...CTX, degraded: true };
    const r = runIntent('identify_next_missing_field', degraded);
    expect(r.text).toBe('I cannot verify the current record state right now.');
  });
});

describe('P29.3 deterministic agent — proposal + confirmation safety', () => {
  it('stage_answer creates a proposal bound to the current source rev, pending, from the USER value only', () => {
    const p = stageAnswer(CTX, { field: 'series', value: 'series-42' });
    expect(p.field).toBe('series');
    expect(p.value).toBe('series-42');
    expect(p.sourceRev).toBe(5); // bound to the context it was computed against
    expect(p.confirmationState).toBe('pending'); // never auto-confirmed
    expect(p.experimentId).toBe(CTX.experimentId);
  });

  it('a proposal grounded in an older rev CANNOT be confirmed after the record advances (no silent write)', async () => {
    const p = stageAnswer(CTX, { field: 'series', value: 'series-42' });
    const advanced = { ...CTX, recordRev: 6, version: 'genabc.6' };
    const api = { submitAnswer: vi.fn(), editField: vi.fn() };
    const res = await confirmProposal(p, advanced, api as never);
    expect(res.status).toBe('stale'); // revalidation required
    expect(api.submitAnswer).not.toHaveBeenCalled();
    expect(api.editField).not.toHaveBeenCalled();
  });

  it('confirm on the SAME rev sends the current version as If-Match and mutates once', async () => {
    const p = stageAnswer(CTX, { field: 'series', value: 'series-42' });
    const api = {
      submitAnswer: vi.fn().mockResolvedValue({ version: 'genabc.6', pending: [] }),
      editField: vi.fn(),
    };
    const res = await confirmProposal(p, CTX, api as never);
    expect(res.status).toBe('ok');
    // exactly one mutation call, carrying the current version token for If-Match
    const calls = api.submitAnswer.mock.calls.length + api.editField.mock.calls.length;
    expect(calls).toBe(1);
    const firstCall = api.submitAnswer.mock.calls[0] ?? api.editField.mock.calls[0];
    expect(JSON.stringify(firstCall)).toContain('genabc.5'); // If-Match = the rev the user confirmed against
  });

  it('a 412 stale conflict marks the proposal stale, does NOT retry, does NOT auto-merge', async () => {
    const p = stageAnswer(CTX, { field: 'series', value: 'series-42' });
    const err = Object.assign(new Error('stale'), { status: 412 });
    const api = { submitAnswer: vi.fn().mockRejectedValue(err), editField: vi.fn() };
    const res = await confirmProposal(p, CTX, api as never);
    expect(res.status).toBe('conflict');
    expect(res.proposal?.confirmationState).toBe('stale');
    expect(api.submitAnswer).toHaveBeenCalledTimes(1); // no silent retry
  });

  it('the agent exposes no read intent that mutates — only confirmProposal writes', async () => {
    const api = { submitAnswer: vi.fn(), editField: vi.fn() };
    for (const intent of ['explain_current_state', 'identify_next_missing_field', 'review_field_evidence', 'show_inferred_candidates', 'explain_unknown']) {
      runIntent(intent, CTX, { field: 'sample.material' });
    }
    expect(api.submitAnswer).not.toHaveBeenCalled();
    expect(api.editField).not.toHaveBeenCalled();
  });
});


describe('a run-owned proposal reaches the run that OWNS it', () => {
  const RUN_ONE = '01RUNAAAAAAAAAAAAAAAAAAAA0';
  const RUN_TWO = '01RUNBBBBBBBBBBBBBBBBBBBB0';
  const twoRuns: AgentContext = {
    ...CTX,
    pending: [
      { id: 'series', label: 'series', run_id: RUN_ONE, blocker_key: `${RUN_ONE}:series` },
      { id: 'series', label: 'series', run_id: RUN_TWO, blocker_key: `${RUN_TWO}:series` },
    ],
  };

  it('CRITICAL: writes run TWO\'s value onto run TWO, not onto the first of that kind', async () => {
    /* An independent review measured this writing run 2's spectrum onto RUN 1, with run
       1's `If-Match`, and reporting `status: 'ok'` — while run 2's question stayed open.
       The cause: `ctx.pending.find((p) => p.id === proposal.field)` and `field` is the
       KIND, so `find` returned the FIRST entry. Before the routing existed the same click
       409'd, which is a worse experience and a better outcome. */
    const p = stageAnswer(twoRuns, {
      field: 'series',
      blockerKey: `${RUN_TWO}:series`,
      value: 'run-two-spectrum',
    });
    const api = {
      submitAnswer: vi.fn().mockResolvedValue({ version: 'genabc.6', pending: [] }),
      editField: vi.fn(),
      getRun: vi.fn().mockResolvedValue({ run: { version: 'run-two.3' } }),
    };
    const res = await confirmProposal(p, twoRuns, api as never);

    expect(res.status).toBe('ok');
    expect(api.getRun).toHaveBeenCalledWith(twoRuns.experimentId, RUN_TWO);
    expect(api.submitAnswer).toHaveBeenCalledWith(
      twoRuns.experimentId,
      { series: 'run-two-spectrum' },
      'run-two.3',
      RUN_TWO,
    );
    expect(api.editField).not.toHaveBeenCalled();
  });

  it('routes the EDIT path to the run too, which it never did', async () => {
    /* `open === undefined` is what SELECTS `editField`, so reading the run from the
       matching pending entry alone left this path always record-routed — and correcting
       an answered run-owned field then 409'd on every record with runs, into copy saying
       it could not tell whether anything reached the record. The run id is recovered from
       the key's own prefix, which is available precisely because the question is gone. */
    const answered: AgentContext = { ...CTX, pending: [] };
    const p = stageAnswer(answered, {
      field: 'qc',
      blockerKey: `${RUN_ONE}:qc`,
      value: { status: 'valid', evidence: 'Re-checked.' },
    });
    const api = {
      submitAnswer: vi.fn(),
      editField: vi.fn().mockResolvedValue({ version: 'genabc.6', pending: [] }),
      getRun: vi.fn().mockResolvedValue({ run: { version: 'run-one.4' } }),
    };
    const res = await confirmProposal(p, answered, api as never);

    expect(res.status).toBe('ok');
    expect(api.getRun).toHaveBeenCalledWith(answered.experimentId, RUN_ONE);
    expect(api.editField).toHaveBeenCalledWith(
      answered.experimentId,
      { qc: { status: 'valid', evidence: 'Re-checked.' } },
      'run-one.4',
      RUN_ONE,
    );
    expect(api.submitAnswer).not.toHaveBeenCalled();
  });

  it('NEGATIVE CONTROL: a record-level proposal is not routed to any run', async () => {
    // A key with no ULID prefix must never become a run route. This is what stops the
    // fallback from turning a record-level question into a run write.
    const p = stageAnswer(CTX, { field: 'series', blockerKey: 'series', value: 'x' });
    const api = {
      submitAnswer: vi.fn().mockResolvedValue({ version: 'genabc.6', pending: [] }),
      editField: vi.fn(),
      getRun: vi.fn(),
    };
    await confirmProposal(p, CTX, api as never);
    expect(api.getRun).not.toHaveBeenCalled();
    const call = api.submitAnswer.mock.calls[0] ?? api.editField.mock.calls[0];
    expect(call[3]).toBeUndefined(); // no runId
  });
});

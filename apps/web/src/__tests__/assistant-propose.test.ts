/*
 * P29.6 — Agent Actionability Closure: the GUARDED staging entry.
 *
 * TEST-FIRST (orchestrator-authored, RED until `proposeForField` exists in
 * lib/assistantAgent.ts). This is the truth-critical guard on WHICH sources may
 * create a proposal — the confirm/cancel/stale/leak machinery already exists
 * (P29.3 confirmProposal, P29.4b ProposalCard). A proposal must never be
 * fabricated for an Unknown, never auto-pick a conflict winner, never come from
 * Project Memory, and a focused user answer must be labeled user-provided (NOT
 * auto-classified as evidence-supported). Every proposal is pending, version-
 * bound, and experiment-bound. Pure: it returns a Proposal (or null) and never
 * mutates.
 */

import { describe, expect, it } from 'vitest';
import { proposeForField } from '../lib/assistantAgent';
import type { AgentContext } from '../lib/assistantAgent';

const CTX: AgentContext = {
  experimentId: '01EXPERIMENTA0000000000000',
  recordRev: 5,
  version: 'genabc.5',
  workflow: { current_step: 'complete_metadata', ordered_steps: [] },
  evidence: [
    { field: 'sample.material', classification: 'supported', value_state: 'confirmed', explanation: '', sources: [] },
    { field: 'xas.edge', classification: 'inferred_candidate', value_state: 'candidate', explanation: '', sources: [] },
    { field: 'sample.mass_mg', classification: 'conflicting_evidence', value_state: 'candidate', explanation: '', sources: [] },
    { field: 'sample.origin', classification: 'unknown', value_state: 'none', explanation: '', sources: [] },
  ],
  pending: [{ id: 'series', label: 'Reduced Series' }],
};

describe('P29.6 proposeForField — guarded staging entry', () => {
  it('a focused USER answer for the current pending field stages a pending, user-provided proposal', () => {
    const p = proposeForField(CTX, { field: 'series', value: 'series-42', source: 'user' });
    expect(p).not.toBeNull();
    expect(p!.field).toBe('series');
    expect(p!.value).toBe('series-42');
    expect(p!.sourceRev).toBe(5);
    expect(p!.experimentId).toBe(CTX.experimentId);
    expect(p!.confirmationState).toBe('pending'); // never auto-confirmed
    // A user answer is labeled user-provided, NOT auto-classified as supported.
    expect(String(p!.origin).toLowerCase()).toContain('user');
    expect(p!.classification).not.toBe('supported');
  });

  it('an UNKNOWN field never yields a fabricated proposal', () => {
    expect(proposeForField(CTX, { field: 'sample.origin', source: 'candidate' })).toBeNull();
  });

  it('a CONFLICTING field never auto-picks a winner (null unless an explicit option is selected)', () => {
    expect(proposeForField(CTX, { field: 'sample.mass_mg', source: 'candidate' })).toBeNull();
    // With an explicit user-selected option it may stage for REVIEW (still pending).
    const chosen = proposeForField(CTX, { field: 'sample.mass_mg', value: '12', source: 'user' });
    expect(chosen).not.toBeNull();
    expect(chosen!.confirmationState).toBe('pending');
    expect(chosen!.value).toBe('12');
  });

  it('an INFERRED candidate stages as an explicitly inferred/unconfirmed proposal (never as fact)', () => {
    const p = proposeForField(CTX, { field: 'xas.edge', source: 'candidate' });
    expect(p).not.toBeNull();
    expect(p!.classification).toBe('inferred_candidate');
    expect(p!.confirmationState).toBe('pending');
  });

  it('Project Memory / graph can NEVER create a scientific-value proposal', () => {
    expect(proposeForField(CTX, { field: 'series', value: 'x', source: 'memory' } as never)).toBeNull();
    expect(proposeForField(CTX, { field: 'series', value: 'x', source: 'graph' } as never)).toBeNull();
  });

  it('is pure — returns a proposal object and never mutates the context', () => {
    const before = JSON.stringify(CTX);
    proposeForField(CTX, { field: 'series', value: 'v', source: 'user' });
    expect(JSON.stringify(CTX)).toBe(before);
  });

  it('a focused user answer is constrained to a NAMED field (no field → null, never a blanket write)', () => {
    expect(proposeForField(CTX, { field: '', value: 'v', source: 'user' } as never)).toBeNull();
  });
});

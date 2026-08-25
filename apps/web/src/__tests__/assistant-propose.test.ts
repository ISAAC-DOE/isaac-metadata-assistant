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

/*
 * A MODEL IS NOT A SOURCE THIS FLOW ADMITS, and nothing said so.
 *
 * `ProposeSource` is `'user' | 'candidate' | 'memory' | 'graph'`, and the suite
 * above pins the two refusals it names. A MODEL is not in the union at all, so
 * TypeScript is the first line of defence and the strongest one — the call
 * `{ source: 'model' }` does not compile, which is why every assertion here needs
 * an `as never` to be written down. That is worth stating rather than assuming:
 * ADDING `'model'` to the union would be the change to argue about, not a runtime
 * branch to add.
 *
 * WHY THE RUNTIME REFUSAL IS PINNED TOO. The union is erased at runtime, and this
 * function is reachable from a `source` that arrived over the wire or out of a
 * session — `AssistantPanel` reads a persisted conversation. `proposeForField`'s
 * guard is `if (source !== 'user' && source !== 'candidate') return null`, an
 * allowlist, so it already refuses; nothing measured that it does. A future edit
 * to a denylist (`source === 'memory' || source === 'graph'`) would pass every
 * test in this file and admit a model, which is exactly the shape of the bug the
 * allowlist exists to prevent.
 *
 * WHY IT MUST REFUSE, and it is not squeamishness about models. A staged value
 * becomes a recorded value through `confirmProposal`, and every written value
 * carries evidence or a `user_confirmation` (`CLAUDE.md` §5). There is no ISAAC
 * source type for a model's output: `src/isaac_records/models.py`'s `SOURCE_TYPES`
 * is closed at seven, and adding an eighth is a truth-core change under §13.
 * `providers/guards.py`'s docstring already worked this through for the transcript
 * seam and reached the same place — a transcript candidate is *pre-evidence*
 * because it QUOTES what a scientist said, and the scientist's confirmation of
 * their own words is what writes the evidence. A generated value quotes nothing,
 * so the same confirmation would be a rubber stamp on a guess.
 * `docs/ai-integration-decision-packet.md` §6.3: "a model-proposed value is never
 * `verified` on the model's word."
 */
describe('a model output cannot enter the proposal flow', () => {
  /*
   * EVERY CASE BELOW USES `sample.material`, AND THE CHOICE IS THE TEST.
   *
   * The first version of this block asked about `series`, which has no evidence
   * entry — so `proposeForField` returned null down the *candidate* path
   * (`if (!evidence) return null`) whether the source guard fired or not. Measured:
   * with the guard mutated from its allowlist to a denylist
   * (`source === 'memory' || source === 'graph'`), 13 of those 14 assertions still
   * passed. They were testing a missing fixture, not a boundary.
   *
   * `sample.material` is classified `supported`, which is the one state a
   * `candidate` source DOES stage. So a refusal here can only come from the source
   * guard, and the same mutation fails every case.
   */
  it('the control: a permitted source DOES stage this field, so a refusal below means something', () => {
    expect(proposeForField(CTX, { field: 'sample.material', source: 'candidate' })).not.toBeNull();
  });

  it.each(['model', 'assistant', 'llm', 'provider', 'mcp', 'transcription-seam', ''])(
    'the source %o stages nothing, on a field a permitted source would stage',
    (source) => {
      expect(
        proposeForField(CTX, { field: 'sample.material', value: '300 K', source } as never),
      ).toBeNull();
    },
  );

  it('the two named refusals are refused on that field too, not only where evidence is absent', () => {
    // `memory` and `graph` are pinned above against `series`, which has no
    // evidence — so those assertions also survived the denylist mutation. Re-put
    // against a stageable field, they measure the guard.
    expect(
      proposeForField(CTX, { field: 'sample.material', value: 'x', source: 'memory' } as never),
    ).toBeNull();
    expect(
      proposeForField(CTX, { field: 'sample.material', value: 'x', source: 'graph' } as never),
    ).toBeNull();
  });
});

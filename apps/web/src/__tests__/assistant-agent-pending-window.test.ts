/*
 * `AgentContext.pending` IS A PREFIX, NOT THE SET — AND NOTHING MAY DEPEND ON THE REST.
 *
 * `useRecordSession` fills it from a bounded page (`limit: 50`) rather than the complete
 * list, because the effect that fetches it is keyed on `version` and the completion
 * screen adopts a fresh `version` from every accepted answer — so the unbounded read was
 * 1,772,692 bytes fetched again after EVERY SUBMISSION on a 1,000-run record, on the very
 * screen the pending bound was written for.
 *
 * That is only safe while every consumer needs the HEAD and nothing more. Two do today:
 * `identify_next_missing_field` reads `pending[0]`, and `confirmProposal` uses membership
 * as a routing HINT that the server corrects (`assistant-answer-routing.test.ts`). The
 * dangerous change is not either of those — it is the third consumer, added later by
 * someone reading `pending` as a complete list and writing `ctx.pending.length` into a
 * sentence. That sentence would be wrong by exactly what the window withheld, and no
 * existing test would notice, because every fixture in this suite is smaller than 50.
 *
 * So the property is pinned structurally: EVERY registered intent must render
 * byte-identically from the full list and from a one-entry window of it. An intent that
 * counts, totals, sums or exhaustively lists `pending` fails this by construction, which
 * is the point — it is a tripwire for a claim that has not been made yet.
 */

import { describe, expect, it } from 'vitest';
import { INTENTS, runIntent } from '../lib/assistantAgent';
import type { AgentContext } from '../lib/assistantAgent';

const FULL: AgentContext = {
  experimentId: '01EXPERIMENTA0000000000000',
  recordRev: 5,
  version: 'genabc.5',
  workflow: {
    current_step: 'complete_metadata',
    ordered_steps: [
      { id: 'complete_metadata', label: 'Complete Metadata', state: 'current', current: true, reopened: false, blocked: false, reason: null },
      { id: 'review_evidence', label: 'Review Evidence', state: 'reopened', current: false, reopened: true, blocked: false, reason: 'An upstream change reopened this step.' },
      { id: 'review_export_readiness', label: 'Review Export Readiness', state: 'blocked', current: false, reopened: false, blocked: true, reason: "Complete 'Complete Metadata' first." },
    ],
  },
  evidence: [
    { field: 'sample.material', classification: 'supported', value_state: 'confirmed', explanation: 'Backed by observed evidence.', sources: [{ source_type: 'spreadsheet' }] },
    { field: 'xas.edge', classification: 'inferred_candidate', value_state: 'candidate', explanation: 'Proposed by a derivation rule; unconfirmed.', sources: [{ source_type: 'derivation' }] },
    { field: 'sample.mass_mg', classification: 'conflicting_evidence', value_state: 'candidate', explanation: 'Evidence asserts incompatible values.', sources: [{ source_type: 'user_confirmation' }] },
    { field: 'sample.origin', classification: 'unknown', value_state: 'none', explanation: 'No defensible value.', sources: [] },
  ],
  // Deliberately more than one, and deliberately DIFFERENT after the head, so a
  // consumer reading past it produces different text rather than the same text twice.
  pending: [
    { id: 'series', label: 'Reduced Series' },
    { id: 'descriptor', label: 'Descriptor' },
    { id: 'qc', label: 'QC Verdict' },
  ],
};

/** The same record, as a client that asked for one entry sees it. */
const WINDOWED: AgentContext = { ...FULL, pending: FULL.pending.slice(0, 1) };

/** Enough opts that every registered intent renders its full branch, not its guard. */
const OPTS = { field: 'xas.edge', step: 'review_evidence' };

describe('every intent is indifferent to how much of the pending list it was given', () => {
  it('the fixture can tell the two apart — a control, so the assertion below is not vacuous', () => {
    // If a consumer DID read past the head, this is the difference it would produce. The
    // guard is only meaningful because this is non-trivially true of the fixture.
    expect(FULL.pending.length).not.toBe(WINDOWED.pending.length);
    expect(FULL.pending.map((p) => p.label).join()).not.toBe(
      WINDOWED.pending.map((p) => p.label).join(),
    );
    expect(FULL.pending[0]).toEqual(WINDOWED.pending[0]); // …but the HEAD is the same
  });

  it('EVERY registered intent renders identically from the full list and from a window', () => {
    expect(INTENTS.length).toBeGreaterThan(0);
    for (const intent of INTENTS) {
      expect(
        JSON.stringify(runIntent(intent, WINDOWED, OPTS)),
        `intent "${intent}" reads past the head of ctx.pending — see this file's header`,
      ).toBe(JSON.stringify(runIntent(intent, FULL, OPTS)));
    }
  });

  it('the head is still the answer: the next missing field is the first entry', () => {
    // A window is a PREFIX FROM OFFSET 0, so "the next pending field" means exactly what
    // it meant before. This is the one claim the bound could have made false.
    expect(runIntent('identify_next_missing_field', WINDOWED).text).toContain('Reduced Series');
  });

  it('an EMPTY window is an empty list, and saying "none is blocking" stays honest', () => {
    /* The other claim the bound could have made false, and the reason it does not: the
       server returns entries from offset 0 up to the limit, so an empty prefix cannot
       coexist with a non-empty list. "There are no pending fields" is therefore a
       statement about the record, not about the window. */
    const empty = { ...FULL, pending: [] };
    const r = runIntent('identify_next_missing_field', empty);
    expect(r.text).toContain('no pending fields');
    // …and it still points at the deterministic audit rather than claiming completeness
    // on its own authority.
    expect(r.text).toContain('audit');
  });
});

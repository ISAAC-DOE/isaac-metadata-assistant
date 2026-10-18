/*
 * The blocker answer, chip composer vs server composer. `apps/web/src/test/blocker-answer-cases.json`
 * is asserted here AND by `apps/api/tests/test_assistant_query.py` (`test_the_blocker_answer_matches_the_
 * shared_parity_table`), so the "What's left before export?" chip and the typed answer cannot drift
 * apart without one of the two suites failing — the same arrangement as `blocker-wording-parity.test.ts`.
 * `expected` is the chip text; the server appends its Open Validator sentence.
 */
import { describe, expect, it } from 'vitest';
import cases from '../test/blocker-answer-cases.json';
import { compose } from '../lib/assistantComposer';
import {
  auditNotExported,
  draftResponse,
  evidenceResponse,
  experimentDetail,
  graphStatusUnavailable,
  validateDryRun,
  warningsDryRun,
} from '../test/apiFixtures';
import type { ApiPendingItem, GroundingState, RecordBundle } from '../lib/types';

type Case = {
  name: string;
  pending: Record<string, unknown>[];
  errors: { path: string; message: string }[];
  expected: string;
};

function chipText(c: Case): string {
  const bundle = {
    detail: experimentDetail,
    groups: draftResponse.groups,
    pending: c.pending as unknown as ApiPendingItem[],
    pendingTotal: c.pending.length,
    validate: { ...validateDryRun, errors: c.errors },
    audit: auditNotExported,
    warnings: warningsDryRun,
    evidence: evidenceResponse.evidence,
    graph: graphStatusUnavailable,
  } as unknown as RecordBundle;
  const state: GroundingState = { context: 'review', bundle };
  return compose(state).prompts[1].answer!.text;
}

describe('the blocker chip agrees with the server composer on the shared cases', () => {
  for (const c of (cases as { cases: Case[] }).cases) {
    it(c.name, () => {
      expect(chipText(c)).toBe(c.expected);
    });
  }

  it('the table is not vacuous', () => {
    expect((cases as { cases: Case[] }).cases.length).toBeGreaterThanOrEqual(10);
  });
});

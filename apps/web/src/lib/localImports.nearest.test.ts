import { describe, it, expect } from 'vitest';
import { nearestRecordText } from './localImports';

// Audit round 2 (worded plainly 2026-11-17 and led by the group's NAME, never its id): the nearest group never names a decision already made, and a null group (every live group
// has nothing left here) is said in the server's own words — never "group null needs 0 ..., plus: ."
describe('nearestRecordText', () => {
  it('names only the decisions still to make', () => {
    expect(nearestRecordText({ group_id: 'rg-1', blocking_questions: 2, plus_decisions: ['approve its processing result'] }, 'SYN_run_A')).toBe(
      'Closest to done: SYN_run_A. 2 answers left. Also needed: approve its processing result.',
    );
    expect(nearestRecordText({ group_id: 'rg-1', blocking_questions: 1, plus_decisions: [] }, 'SYN_run_A')).toBe('Closest to done: SYN_run_A. 1 answer left.');
  });

  it('says so when no group has anything left here', () => {
    const statement = '2 record group(s) have no blocking question and no decision left here';
    expect(nearestRecordText({ group_id: null, blocking_questions: 0, plus_decisions: [], statement }, '')).toBe(statement);
  });

  it('keeps the blocked reason', () => {
    expect(nearestRecordText({ group_id: 'g', blocking_questions: 0, plus_decisions: ['confirm the group'], blocked: 'No protocol' }, 'SYN_run_G')).toBe(
      'Closest to done: SYN_run_G. 0 answers left. Also needed: confirm the group. No protocol.',
    );
  });
});

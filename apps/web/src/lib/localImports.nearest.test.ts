import { describe, it, expect } from 'vitest';
import { nearestRecordText } from './localImports';

// Audit round 2: the nearest group never names a decision already made, and a null group (every live group
// has nothing left here) is said in the server's own words — never "group null needs 0 ..., plus: ."
describe('nearestRecordText', () => {
  it('names only the decisions still to make', () => {
    expect(nearestRecordText({ group_id: 'rg-1', blocking_questions: 2, plus_decisions: ['approve its processing result'] })).toBe(
      'group rg-1 needs 2 blocking answer(s), plus: approve its processing result.',
    );
    expect(nearestRecordText({ group_id: 'rg-1', blocking_questions: 1, plus_decisions: [] })).toBe('group rg-1 needs 1 blocking answer(s).');
  });

  it('says so when no group has anything left here', () => {
    const statement = '2 record group(s) have no blocking question and no decision left here';
    expect(nearestRecordText({ group_id: null, blocking_questions: 0, plus_decisions: [], statement })).toBe(statement);
  });

  it('keeps the blocked reason', () => {
    expect(nearestRecordText({ group_id: 'g', blocking_questions: 0, plus_decisions: ['confirm the group'], blocked: 'No protocol' })).toBe(
      'group g needs 0 blocking answer(s), plus: confirm the group. No protocol.',
    );
  });
});

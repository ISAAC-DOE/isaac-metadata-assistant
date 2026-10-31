import { describe, it, expect } from 'vitest';
import { countsText, deferredText, fieldWords, nearestRecordText, notCountedText, onlyWords, splitAtId } from '../lib/localImports';

// Polish cycle 1, review round 2 (L2): the nearest group names the required fields no question asks yet
// (`unasked_required`), never only counts them as answers; and the tier-3 counts the blocking / optional split
// leaves out (`conflicts_without_a_record_field`, `outside_live_groups`) are said. SYNTHETIC values only.
const unasked = (path: string, answerable = false) => ({ path, answerable, reason: 'synthetic reason', command: 'isaac bundle decide …' });

describe('nearestRecordText with the minimum’s questions and unasked fields', () => {
  it('a group whose only remaining items are unasked required fields names them in plain words', () => {
    const m = {
      group_id: 'g1',
      blocking_questions: 0,
      plus_decisions: [],
      questions: [],
      unasked_required: [unasked('sample.sample_form'), unasked('context.environment')],
    };
    expect(nearestRecordText(m)).toBe('group g1 needs 2 required fields no question asks yet: sample form, environment.');
  });

  it('counts the questions it lists, and names the unasked fields beside them (one field: singular)', () => {
    const m = {
      group_id: 'g2',
      blocking_questions: 2,
      plus_decisions: ['confirm the group'],
      questions: [{ question_id: 'Q-0000000001', fields: ['system.technique'], only: null }],
      unasked_required: [unasked('attribution.produced_by.group', true)],
    };
    expect(nearestRecordText(m)).toBe(
      'group g2 needs 1 blocking answer(s) and 1 required field no question asks yet: produced by group; plus: confirm the group.',
    );
  });

  it('a server that sends neither list is read as before', () => {
    expect(nearestRecordText({ group_id: 'g3', blocking_questions: 3, plus_decisions: [] })).toBe('group g3 needs 3 blocking answer(s).');
    expect(nearestRecordText({ group_id: 'g3', blocking_questions: 1, plus_decisions: [], questions: [{ question_id: 'Q-1', fields: [], only: null }], unasked_required: [] })).toBe(
      'group g3 needs 1 blocking answer(s).',
    );
  });

  it('keeps the blocked reason after the named fields', () => {
    const m = { group_id: 'g4', blocking_questions: 0, plus_decisions: [], questions: [], unasked_required: [unasked('sample.material.name')], blocked: 'SERVER-SAID: no measurement run' };
    expect(nearestRecordText(m)).toBe('group g4 needs 1 required field no question asks yet: material name. SERVER-SAID: no measurement run.');
  });
});

describe('fieldWords', () => {
  it('says a field path in plain words', () => {
    expect(fieldWords('sample.sample_form')).toBe('sample form');
    expect(fieldWords('context.environment')).toBe('environment');
    expect(fieldWords('attribution.produced_by.organization')).toBe('produced by organization');
    expect(fieldWords('assets[].uri')).toBe('uri');
  });
});

describe('notCountedText', () => {
  it('names both counts the blocking / optional split leaves out', () => {
    expect(notCountedText({ total: 9, blocking: 1, optional: 4, conflicts_without_a_record_field: 2, outside_live_groups: 1 })).toBe(
      'Neither blocking nor counted as optional: 2 disagreement(s) about something no record field holds (settling one changes ' +
        'no record); 1 question(s) about runs no record group holds (no record is built from them).',
    );
  });

  it('says nothing when both are zero, absent, or the counts are unavailable', () => {
    expect(notCountedText({ total: 3, blocking: 1, conflicts_without_a_record_field: 0, outside_live_groups: 0 })).toBeNull();
    expect(notCountedText({ total: 3, blocking: 1 })).toBeNull();
    expect(notCountedText({ unavailable: 'KeyError' })).toBeNull();
    expect(notCountedText(null)).toBeNull();
  });

  it('names only the one that is not zero', () => {
    expect(notCountedText({ outside_live_groups: 4 })).toBe(
      'Neither blocking nor counted as optional: 4 question(s) about runs no record group holds (no record is built from them).',
    );
  });
});

describe('polish c7-w: counts that add up, deferred, links', () => {
  it('names informational questions beside the other tier-3 counts, and deferred ones as overlapping', () => {
    expect(notCountedText({ total: 10, informational: 4 })).toBe(
      'Neither blocking nor counted as optional: 4 listed for information only (no answer can reach a record from them yet).',
    );
    expect(notCountedText({ total: 10, deferred: 2 })).toBe('Of the open questions, 2 deferred (“I don’t know”); they are still counted above.');
    expect(notCountedText({ total: 10, informational: 0, deferred: 0, outside_live_groups: 0 })).toBeNull();
  });

  it('countsText names every counted tier', () => {
    expect(countsText({ blocking: 1, conflicts_affecting_a_record: 2, optional: 3 })).toBe(
      '1 blocking export, 2 conflicts affecting a record, 3 optional',
    );
  });

  it('nearestRecordText says how many of its answers are deferred', () => {
    const m = {
      group_id: 'g1', blocking_questions: 2, plus_decisions: [],
      questions: [{ question_id: 'Q-1', fields: ['a'], only: null, deferred: true }, { question_id: 'Q-2', fields: ['b'], only: null }],
    };
    expect(nearestRecordText(m)).toBe('group g1 needs 2 blocking answer(s) (1 deferred).');
  });

  it('deferredText, onlyWords and splitAtId', () => {
    expect(deferredText({ by: 'Synthetic Scientist', decided_utc: '2099-01-02T03:04:05Z' })).toBe('Deferred by Synthetic Scientist, 2099-01-02');
    expect(deferredText({ by: null, decided_utc: null })).toBe('Deferred by a name not recorded, date not recorded');
    expect(onlyWords('group:g1')).toBe('group g1');
    expect(onlyWords('run:r1')).toBe('run r1');
    expect(onlyWords(null)).toBeNull();
    expect(splitAtId('answer Q-1 now', 'Q-1')).toEqual(['answer ', ' now']);
    expect(splitAtId('no id here', 'Q-1')).toBeNull();
    expect(splitAtId('x', null)).toBeNull();
  });
});

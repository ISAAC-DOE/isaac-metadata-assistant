import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { LocalQuestion } from '../lib/localImports';
import {
  cannotExportLines,
  cardTitle,
  clusterRepeats,
  counterExample,
  countLine,
  fieldAsk,
  groupName,
  plainQuestion,
  repeatKey,
  sampleLabel,
  scopeName,
} from '../lib/plainQuestions';

/**
 * The site's plain layer over the backend's question text (2026-11-17). SYNTHETIC values only. Pinned:
 *   · the plain sentence by kind and field, and the server's own text whenever the kind is unknown;
 *   · the backend strings the skill reads are untouched (this is a frontend layer, not a rewrite);
 *   · a repeated question is gathered on one card, every question kept exactly once;
 *   · groups are named, never shown by an internal id while a name is known.
 */

function q(over: Partial<LocalQuestion>): LocalQuestion {
  return {
    question_id: 'Q-syn0000001',
    tier: 1,
    blocking: true,
    why: 'SERVER why',
    kind: 'missing_value',
    scope: 'experiment',
    target_field_path: 'context.environment',
    text: 'SERVER text',
    applies_to: { groups: 1, runs: 1, targets: 1 },
    targets: [],
    per_scope_targets: {},
    allowed_values: null,
    allowed_decisions: ['correct', 'defer', 'reject'],
    answer_command: 'isaac bundle decide …',
    display: {
      folder: 'syn', beamtime: null, beamline: [], answer_kind: 'field_value', settles_many: false, scopes: [],
      record_run_names: [], targets_described: 0, targets_total: 0, suggestions_differ: false, suggestions: [],
      suggestions_total: 0, distinct_extracted_values: [], field_suggestions: {}, value_rule: null, fields: {},
      suggested_absorber: null, suggestion_statement: '',
    },
    ...over,
  } as LocalQuestion;
}

describe('plainQuestion', () => {
  it('asks the owner’s example in plain words', () => {
    expect(plainQuestion(q({}))).toBe('Was this measured in situ, operando or ex situ? None of your files say.');
  });

  it('asks every kind it knows plainly, and a field it has no word for by its last segment', () => {
    expect(plainQuestion(q({ target_field_path: 'context.temperature_K' }))).toBe('What is the temperature? None of your files say.');
    expect(plainQuestion(q({ kind: 'resolve_conflict', target_field_path: 'system.technique' }))).toBe(
      'Your files disagree about the technique. Which is right?',
    );
    expect(plainQuestion(q({ kind: 'resolve_conflict', target_field_path: null }))).toBe('Your files disagree here. Which is right?');
    expect(plainQuestion(q({ kind: 'confirm_value', target_field_path: 'context.electrochemistry.cell_type',
      display: { ...q({}).display, distinct_extracted_values: [{ value: 'flow_cell', targets: 1 }] } }))).toBe(
      'Is the cell type read from your files right?',
    );
    expect(plainQuestion(q({ kind: 'confirm_value', target_field_path: 'sample.material.name' }))).toBe(
      'What is the sample material? Your files mention it, but not as a value a record can hold.',
    );
    expect(plainQuestion(q({ kind: 'naming_counter_positions', target_field_path: null, positions: [1] }))).toBe(
      'Is the first number in these file names a repeat counter?',
    );
    expect(plainQuestion(q({ kind: 'naming_counter_positions', target_field_path: null, positions: [-1] }))).toBe(
      'Is the last number in these file names a repeat counter?',
    );
    expect(plainQuestion(q({ kind: 'clock_time_zone', target_field_path: null }))).toBe('What time zone was the instrument clock set to?');
    expect(plainQuestion(q({ kind: 'confirm_absorber', target_field_path: null }))).toBe('Which element and absorption edge were measured?');
  });

  it('leaves a kind it does not know in the server’s own words', () => {
    expect(plainQuestion(q({ kind: 'condition_label' }))).toBeNull();
    expect(cardTitle(q({ kind: 'condition_label', text: 'SERVER condition text' }))).toBe('SERVER condition text');
    expect(fieldAsk('attribution.produced_by.group')).toBe('Which research group produced this data?');
  });

  it('never changes the backend strings the skill reads (the plain layer lives in the frontend only)', () => {
    const src = readFileSync(join(__dirname, '../../../api/isaac_api/local_import/questions.py'), 'utf8');
    expect(src).toContain('What is the {_label(path)} ({path})? No source in this import states it.');
    expect(src).not.toContain('None of your files say');
  });
});

describe('sampleLabel and the counter example', () => {
  it('names the sample in the files’ own spelling, else from the partition', () => {
    const said = q({
      partition: 'sample={"sample_name": "jk1", "sample_or_electrode_number": "06"}',
      text: "… with the same sample reading (sample name 'JK1', sample or electrode number '06', as the files write it) — …",
    });
    expect(sampleLabel(said)).toBe('Sample JK1, no. 06');
    expect(sampleLabel(q({ partition: 'sample={"sample_name": "irtio2", "loading_or_thickness": "2nm"}' }))).toBe('Sample irtio2, 2nm');
    expect(sampleLabel(q({ partition: 'sample=unrecorded' }))).toBe('Groups whose files name no sample');
    expect(sampleLabel(q({}))).toBeNull();
  });

  it('reads one example file name from the server’s wording, or none', () => {
    expect(counterExample('… (e.g. the 1st token: [03]_01_SYN_acid (no two names …')).toEqual({ name: '03_01_SYN_acid', part: '03' });
    expect(counterExample('no example here')).toBeNull();
  });
});

describe('clusterRepeats', () => {
  it('gathers a question asked per sample, or per group, where its first copy stood; every question is kept once', () => {
    const a = q({ question_id: 'Q-a', target_field_path: 'sample.sample_form', partition: 'sample={"sample_name": "a"}' });
    const other = q({ question_id: 'Q-x', target_field_path: 'system.domain' });
    const b = q({ question_id: 'Q-b', target_field_path: 'sample.sample_form', partition: 'sample={"sample_name": "b"}' });
    const g1 = q({ question_id: 'Q-g1', kind: 'resolve_conflict', scope: 'group:g1', target_field_path: 'system.technique' });
    const g2 = q({ question_id: 'Q-g2', kind: 'resolve_conflict', scope: 'group:g2', target_field_path: 'system.technique' });
    const out = clusterRepeats([a, other, b, g1, g2]);
    expect(out).toHaveLength(3);
    expect(out[0]).toEqual({ by: 'sample', questions: [a, b] });
    expect(out[1]).toBe(other);
    expect(out[2]).toEqual({ by: 'group', questions: [g1, g2] });
  });

  it('leaves a single copy alone, and never gathers confirm questions with and without a value', () => {
    const lone = q({ question_id: 'Q-a', target_field_path: 'sample.sample_form', partition: 'sample={"sample_name": "a"}' });
    expect(clusterRepeats([lone])).toEqual([lone]);
    const withValue = q({ kind: 'confirm_value', scope: 'group:g1', display: { ...q({}).display, distinct_extracted_values: [{ value: 'x', targets: 1 }] } });
    const without = q({ kind: 'confirm_value', scope: 'group:g2' });
    expect(repeatKey(withValue)).not.toBe(repeatKey(without));
  });
});

describe('counts and groups in plain words', () => {
  it('says the counts as the owner wrote them', () => {
    expect(countLine({ blocking: 110, optional: 485 })).toBe('110 answers block a record. 485 are optional.');
    expect(countLine({ blocking: 1, conflicts_affecting_a_record: 2, optional: 1 })).toBe(
      '1 answer blocks a record. 2 disagreements change a record. 1 is optional.',
    );
  });

  it('says why groups cannot become records without the reason codes', () => {
    expect(cannotExportLines({ 'processing_not_applicable:no_xas_channel': 2 })).toEqual(['2 groups have no absorption signal ISAAC can read.']);
    expect(cannotExportLines({ no_scans: 1, not_a_measurement_run: 4 })).toEqual([
      '1 group has no scans.',
      '4 groups hold only reference, alignment or calibration scans.',
    ]);
    for (const line of cannotExportLines({ 'processing_not_applicable:SYN_code': 3, SYN_other: 1 })) expect(line).not.toMatch(/_/);
  });

  it('names a group by its name, else its first file; the id only when nothing else tells groups apart', () => {
    expect(groupName('rg-1', { 'rg-1': 'SYN_run_A_1p2V' })).toBe('SYN_run_A_1p2V');
    expect(groupName('rg-1', {}, ['SYN_run_B'])).toBe('SYN_run_B');
    expect(groupName('rg-1', {})).toBe('group rg-1');
    expect(scopeName({ kind: 'group', group_id: 'rg-1', run_names: ['SYN_run_C'], label: 'Record group rg-1' }, {})).toBe('SYN_run_C');
    expect(scopeName({ kind: 'experiment', run_names: [], label: 'The whole beamtime' }, {})).toBe('The whole beamtime');
  });
});

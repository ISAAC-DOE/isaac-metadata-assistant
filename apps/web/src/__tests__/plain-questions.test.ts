import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { LocalQuestion } from '../lib/localImports';
import {
  cannotExportLines,
  cardTitle,
  clusterRepeats,
  clusterRowLabels,
  clusterSize,
  confirmShape,
  counterExample,
  countLine,
  fieldAsk,
  groupName,
  plainQuestion,
  questionWarnings,
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
    expect(plainQuestion(q({ allowed_values: ['operando', 'in_situ', 'ex_situ', 'in_silico'] }))).toBe(
      'Was this done operando, in situ, ex situ or in silico? None of your files say.',
    );
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
    expect(plainQuestion(q({ kind: 'confirm_value', target_field_path: 'sample.material.name', no_value: true }))).toBe(
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
    const without = q({ kind: 'confirm_value', scope: 'group:g2', no_value: true });
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

/*
 * 2026-11-17 review fixes. SYNTHETIC values only.
 */
describe('the environment choices come from the schema the server serves, never a hand list (review 5)', () => {
  const schemaEnum = (): string[] => {
    const schema = JSON.parse(readFileSync(join(__dirname, '../../../../schema/isaac_record_v1.json'), 'utf8'));
    return schema.properties.context.properties.environment.enum as string[];
  };

  it('asks every value the vendored schema allows, in_silico included', () => {
    const allowed = schemaEnum();
    expect(allowed).toContain('in_silico');
    const text = plainQuestion(q({ allowed_values: allowed })) ?? '';
    for (const v of allowed) expect(text).toContain(v.replace(/_/g, ' '));
  });

  it('follows the served list, and names no value when none is served', () => {
    expect(plainQuestion(q({ allowed_values: ['SYN_one', 'SYN_two'] }))).toBe('Was this done SYN one or SYN two? None of your files say.');
    expect(plainQuestion(q({ allowed_values: null }))).toBe('What is the measurement environment? None of your files say.');
  });
});

describe('a confirm question is read from the server’s flags, not from distinct_extracted_values (review 4)', () => {
  const targets = [1, 2, 3, 4].map((i) => ({ kind: 'candidate', id: `cand-${i}` }));
  it('most targets with a value: asked to confirm, and the ones without are said beside it', () => {
    // the server sends no distinct values when any target lacks one
    const mixed = q({ kind: 'confirm_value', target_field_path: 'context.electrochemistry.cell_type', targets, targets_without_a_value: 1 });
    expect(confirmShape(mixed)).toBe('value');
    expect(plainQuestion(mixed)).toBe('Is the cell type read from your files right?');
    expect(questionWarnings(mixed)).toEqual([
      'No value was read from your files for 1 of the 4 asked about here, so those cannot be confirmed. Give their value one group at a time.',
    ]);
  });

  it('no target with a value (no_value), and every value unfit, are each asked as what they are', () => {
    const none = q({ kind: 'confirm_value', target_field_path: 'sample.material.name', targets, no_value: true, targets_without_a_value: 4 });
    expect(plainQuestion(none)).toBe('What is the sample material? Your files mention it, but not as a value a record can hold.');
    expect(questionWarnings(none)).toEqual([]);
    const unfit = q({ kind: 'confirm_value', target_field_path: 'sample.material.name', targets, targets_with_an_unfit_value: 4 });
    expect(plainQuestion(unfit)).toBe('What is the sample material? The value read from your files does not fit this field.');
  });
});

describe('what changes how to answer is said beside the title (review 1, CRITICAL)', () => {
  it('groups whose files name no sample: one answer for all only if they are the same sample', () => {
    const unrecorded = q({ partition: 'sample=unrecorded', per_scope_targets: { 'group:g1': ['m1'], 'group:g2': ['m2'] } });
    const [w] = questionWarnings(unrecorded);
    expect(w).toMatch(/name no sample, so they may be different samples/);
    expect(w).toMatch(/only if they are all the same sample\. Otherwise answer each group on its own\./);
    // one group alone: nothing to choose between, and the server says nothing either
    expect(questionWarnings(q({ partition: 'sample=unrecorded', per_scope_targets: { 'group:g1': ['m1'] } }))).toEqual([]);
  });

  it('answers already given differ: answer per group unless they truly are the same', () => {
    expect(questionWarnings(q({ answers_differ: true }))).toEqual([
      'Answers already given for this field in other groups differ. Answer each group on its own, unless they really are all the same.',
    ]);
  });

  it('asked again: how many, which answers and why, and what to do', () => {
    const again = q({
      asked_again: [
        { answered: 'SYN_word', target: { kind: 'missing_value', id: 'm1' }, reason: 'not one of the allowed values' },
        { answered: 'SYN_word', target: { kind: 'missing_value', id: 'm2' }, reason: 'not one of the allowed values' },
        { answered: 7, target: { kind: 'missing_value', id: 'm3' }, reason: null },
      ],
    });
    expect(questionWarnings(again)).toEqual([
      'Asked again: 3 answers already given here cannot go into the record: “SYN_word” (not one of the allowed values); 7. ' +
        'Answer again with a value the record can take.',
    ]);
    expect(questionWarnings(q({}))).toEqual([]);
  });
});

describe('a merged card counts groups and tells its rows apart (review 3)', () => {
  const cf = (id: string, group: string, subject: string | null, readings: string[]) =>
    q({
      question_id: id, kind: 'resolve_conflict', scope: `group:${group}`, target_field_path: 'system.technique',
      display: { ...q({}).display, conflict: { conflict_id: `conf-${id}`, kind: 'field_disagreement', subject, readings } },
    });

  it('three disagreements in two groups: 2 groups, each row its own label', () => {
    const cluster = { by: 'group' as const, questions: [cf('Q-1', 'g1', 'SYN header A', ['x', 'y']), cf('Q-2', 'g1', 'system.technique', ['p', 'q']), cf('Q-3', 'g2', null, ['m', 'n'])] };
    expect(clusterSize(cluster)).toBe(2);
    const names: Record<string, string> = { 'group:g1': 'SYN_run_A', 'group:g2': 'SYN_run_B' };
    expect(clusterRowLabels(cluster, (x) => names[x.scope])).toEqual(['SYN_run_A: SYN header A', 'SYN_run_A: “p” or “q”', 'SYN_run_B']);
  });

  it('two rows that would still read alike are numbered', () => {
    const cluster = { by: 'group' as const, questions: [cf('Q-1', 'g1', 'same', ['x']), cf('Q-2', 'g1', 'same', ['x'])] };
    expect(clusterRowLabels(cluster, () => 'SYN_run_A')).toEqual(['SYN_run_A: same (1 of 2)', 'SYN_run_A: same (2 of 2)']);
  });
});

describe('a start time asked again after the clock’s time zone changed (re-review 1)', () => {
  const base = {
    kind: 'confirm_value', scope: 'group:g1', target_field_path: 'timestamps.acquired_start_utc', blocking: false, tier: 3,
    reason: 'clock_zone_changed_after_confirmation',
  };
  it('no single instant under the new zone: never asked to confirm, and the zone change is said beside the title', () => {
    // the server sets neither no_value nor a target count on it: the page's server counts the targets with no value
    const none = q({ ...base, targets: [{ kind: 'candidate', id: 'cand-1' }], display: { ...q({}).display, targets_without_a_value: 1 } });
    expect(confirmShape(none)).toBe('no_value');
    expect(plainQuestion(none)).toBe(
      'When did the measurement start? Under the clock’s time zone now recorded, the time in your files is not a single moment, so there is nothing to confirm. Give it in UTC.',
    );
    expect(plainQuestion(none)).not.toMatch(/read from your files right/);
    expect(questionWarnings(none)).toEqual([
      'The instrument clock’s time zone was changed after this was confirmed, so that confirmation no longer counts.',
    ]);
  });

  it('a start under the new zone: asked again, with the zone change said beside the title', () => {
    const valued = q({ ...base, targets: [{ kind: 'candidate', id: 'cand-1' }], display: { ...q({}).display, targets_without_a_value: 0 } });
    expect(plainQuestion(valued)).toBe('Is the start time right under the time zone now recorded?');
    expect(questionWarnings(valued)).toEqual([
      'The instrument clock’s time zone was changed after this was confirmed, so that confirmation no longer counts. Confirm it again, or correct it.',
    ]);
  });
});

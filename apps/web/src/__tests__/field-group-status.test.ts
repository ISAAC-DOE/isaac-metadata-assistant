/*
 * A RECORD FIELDS SECTION DOES NOT CALL A RUN'S VALUE "MISSING" — QA C-28
 * (2026-10-12). After every run's start time was accepted, the record's Timestamps
 * card still read "3 fields · Missing". Measured: `GET /draft` is the RECORD's draft,
 * and `timestamps.acquired_start_utc` / `acquired_end_utc` are RUN-level
 * (`capture.level === 'run'`), so the record never holds them — each run does. The
 * card counted them as the record's gaps. They are now counted as "on each run", and
 * only the fields the record itself can hold decide Missing / Remaining.
 */
import { describe, it, expect } from 'vitest';

import { fieldGroupStatus } from '../lib/adapt';
import type { DraftField, DraftFieldCapture } from '../lib/types';

const RUN: DraftFieldCapture = {
  level: 'run',
  record_writable: false,
  run_field_writable: true,
  run_overridable: false,
  choices: null,
};
const STAMPED: DraftFieldCapture = {
  level: 'unclassified',
  record_writable: false,
  run_field_writable: false,
  run_overridable: false,
  choices: null,
  open_namespace: null,
};

function field(path: string, capture: DraftFieldCapture, value: unknown = null): DraftField {
  return {
    path,
    label: path,
    value,
    status: value === null ? 'missing' : 'verified',
    evidence_count: 0,
    source_types: [],
    present: value !== null,
    capture,
  } as DraftField;
}

describe('fieldGroupStatus and run-level rows (QA C-28)', () => {
  it('Timestamps: two times are entered on each run and the third is SET AT EXPORT — none is "missing"', () => {
    /* REVIEW minor: this first read "1 Missing", counting `timestamps.created_utc` —
       which no route accepts and the exporter stamps — as a gap the scientist owns. */
    const status = fieldGroupStatus(
      [
        field('timestamps.acquired_end_utc', RUN),
        field('timestamps.acquired_start_utc', RUN),
        field('timestamps.created_utc', STAMPED),
      ],
      0,
    );
    expect(status.onRuns).toBe(2);
    expect(status.atExport).toBe(1);
    // Re-review: the chip must not claim only one of the two — two fields are entered
    // on each run and the third is set at export.
    expect(status.label).toBe('On Each Run · At Export');
    expect(status.state).toBe('notShownHere');
  });

  it('a split group names each place; a group wholly on runs, or wholly at export, names one', () => {
    expect(fieldGroupStatus([field('context.environment', RUN)], 0).label).toBe(
      'Entered on Each Run',
    );
    expect(fieldGroupStatus([field('timestamps.created_utc', STAMPED)], 0).label).toBe(
      'Set at Export',
    );
  });

  it('a created time the record DOES hold is recorded, not "set at export"', () => {
    const status = fieldGroupStatus(
      [field('timestamps.created_utc', STAMPED, '2099-01-01T00:00:00Z')],
      0,
    );
    expect(status.atExport).toBe(0);
    expect(status.label).toBe('All Recorded');
  });

  it('a section made only of run-level fields says where they live, not "Missing"', () => {
    const status = fieldGroupStatus(
      [field('context.environment', RUN), field('context.temperature_K', RUN)],
      0,
    );
    expect(status.label).toBe('Entered on Each Run');
    expect(status.state).toBe('notShownHere');
    expect(status.onRuns).toBe(2);
  });

  it('a run-level path the record DOES hold still counts as recorded (seeded drafts)', () => {
    const status = fieldGroupStatus(
      [field('context.environment', RUN, 'operando'), field('context.temperature_K', RUN, 300)],
      0,
    );
    expect(status.onRuns).toBe(0);
    expect(status.label).toBe('All Recorded');
  });

  it('a row awaiting confirmation still wins over every count', () => {
    expect(fieldGroupStatus([field('context.environment', RUN)], 1).state).toBe('needsReview');
  });

  it('negative control: a record-level section is unchanged', () => {
    const RECORD: DraftFieldCapture = { ...RUN, level: 'experiment', run_field_writable: false };
    expect(fieldGroupStatus([field('sample.material.name', RECORD)], 0)).toMatchObject({
      label: 'Missing',
      onRuns: 0,
    });
  });
});

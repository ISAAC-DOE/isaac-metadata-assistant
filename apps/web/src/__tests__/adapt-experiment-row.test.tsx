import { describe, it, expect } from 'vitest';
import { toExperimentSummary, trailingFor } from '../lib/adapt';
import { formatCreatedDate } from '../lib/labels';
import type { ApiExperimentSummary } from '../lib/types';

// P33 S1 · adapt-layer contract for the dashboard card (D1/D2/C1). Presentation
// mapping only — no verdict/coverage/status is computed here, only passed
// through or derived by a documented display rule (suffix strip, date format).

function baseSummary(overrides: Partial<ApiExperimentSummary> = {}): ApiExperimentSummary {
  return {
    id: '01SYNTH1',
    title: 'Synthetic XANES — CuO (Cu K-edge)',
    status: 'needs_attention',
    created_utc: '2026-07-12T10:00:00Z',
    pending_count: 5,
    evidenced_field_count: 3,
    exported: false,
    record_id: null,
    // The LIB-001 Library columns. The server sends all six on every row;
    // these are the neutral values for a fixture that is not about them.
    updated_utc: '2026-07-12T10:00:00Z',
    run_count: 0,
    open_proposal_count: 0,
    folder: '',
    technique: null,
    beamline: null,
    ...overrides,
  };
}

describe('adapt — title lifecycle-suffix stripping (D1)', () => {
  const knownSuffixes = [
    ' · New Draft',
    ' · Partially Completed',
    ' · Export Review Required',
    ' · Ready to Export',
    ' · Exported Record',
  ];

  it.each(knownSuffixes)('strips known suffix %s', (suffix) => {
    const s = baseSummary({ title: `Synthetic XANES — CuO (Cu K-edge)${suffix}` });
    expect(toExperimentSummary(s).title).toBe('Synthetic XANES — CuO (Cu K-edge)');
  });

  it('keeps the full title when the suffix is unknown', () => {
    const s = baseSummary({ title: 'Synthetic XANES — CuO (Cu K-edge) · Some Other Suffix' });
    expect(toExperimentSummary(s).title).toBe(
      'Synthetic XANES — CuO (Cu K-edge) · Some Other Suffix',
    );
  });

  it('keeps the full title when there is no suffix at all', () => {
    const s = baseSummary({ title: 'Synthetic XANES — CuO (Cu K-edge)' });
    expect(toExperimentSummary(s).title).toBe('Synthetic XANES — CuO (Cu K-edge)');
  });
});

describe('adapt — created-date formatter', () => {
  it('formats an ISO datetime into a short display + full accessible string', () => {
    expect(formatCreatedDate('2026-07-12T10:00:00Z')).toEqual({
      iso: '2026-07-12',
      display: 'Jul 12, 2026',
      accessible: 'Created July 12, 2026',
    });
  });

  it('propagates onto the summary date field', () => {
    const s = baseSummary({ created_utc: '2026-07-12T10:00:00Z' });
    expect(toExperimentSummary(s).date).toEqual({
      iso: '2026-07-12',
      display: 'Jul 12, 2026',
      accessible: 'Created July 12, 2026',
    });
  });

  it('is undefined when there is no created_utc', () => {
    const s = baseSummary({ created_utc: '' });
    expect(toExperimentSummary(s).date).toBeUndefined();
  });
});

describe('adapt — lifecycle mapping', () => {
  it('maps exported:false to lifecycle "draft"', () => {
    const s = baseSummary({ exported: false });
    expect(toExperimentSummary(s).lifecycle).toBe('draft');
  });

  it('maps exported:true to lifecycle "exported"', () => {
    const s = baseSummary({ exported: true, status: 'done', record_id: '01SYNTHXANESSEED0000000005' });
    expect(toExperimentSummary(s).lifecycle).toBe('exported');
  });
});

describe('adapt — trailingFor', () => {
  it('"done" carries no chip data (lifecycle badge names it instead)', () => {
    const s = baseSummary({ status: 'done', exported: true });
    expect(trailingFor(s, 'done')).toEqual({});
  });

  it('"needsAttention" carries the pending count', () => {
    const s = baseSummary({ pending_count: 5 });
    expect(trailingFor(s, 'needsAttention')).toEqual({ needsYouCount: 5 });
  });

  it('"inReview" and "ready" carry no chip data', () => {
    const s = baseSummary();
    expect(trailingFor(s, 'inReview')).toEqual({});
    expect(trailingFor(s, 'ready')).toEqual({});
  });
});

describe('adapt — the Library columns are PASSED THROUGH, never invented', () => {
  /*
   * THE INVARIANT THIS BLOCK EXISTS FOR, and the reason it is at the ADAPTER and
   * not at the renderer.
   *
   * `adapt.ts` once set `technique` on every row from a module constant
   * `const TECHNIQUE = 'Cu K-edge XANES'` — a scientific value invented in the
   * client, for a schema-governed enum field, wrong for any record that was not
   * Cu K-edge XANES and carrying no signal that it was fabricated. Its own
   * comment said "a display label, not a server field" as though that made it
   * safe. The only thing standing over that hole afterwards was an assertion in
   * `experiment-row.test.tsx` that the ROW renders no technique badge — a
   * RENDERER test, which could only ever have caught the adapter's constant by
   * accident of which string it happened to be, and which had to be replaced the
   * moment a real server-supplied technique started rendering.
   *
   * These assertions are that guard, relocated to the layer that can breach it.
   */
  it('the adapter never invents a technique or a beamline', () => {
    const row = toExperimentSummary(baseSummary({ technique: null, beamline: null }));
    expect(row.technique).toBeUndefined();
    expect(row.beamline).toBeUndefined();
  });

  it('passes a server-supplied technique and beamline through unchanged', () => {
    const row = toExperimentSummary(baseSummary({ technique: 'HERFD-XAS', beamline: '15-2' }));
    expect(row.technique).toBe('HERFD-XAS');
    expect(row.beamline).toBe('15-2');
  });

  it('passes the server counts through as numbers, including zero', () => {
    const zero = toExperimentSummary(baseSummary({ run_count: 0, open_proposal_count: 0 }));
    expect(zero.runCount).toBe(0);
    expect(zero.openProposalCount).toBe(0);
    const some = toExperimentSummary(baseSummary({ run_count: 3, open_proposal_count: 2 }));
    expect(some.runCount).toBe(3);
    expect(some.openProposalCount).toBe(2);
  });

  it('maps an unfiled folder to undefined, not to the empty string', () => {
    // `''` would render as a blank element in the metadata line, which reads as
    // "we know this and it is nothing" — a different claim from "unfiled".
    expect(toExperimentSummary(baseSummary({ folder: '' })).folder).toBeUndefined();
    expect(toExperimentSummary(baseSummary({ folder: 'A/B' })).folder).toBe('A/B');
  });

  it('carries NO disambiguator unless the caller says the title collides', () => {
    // The default is the common case and it must be silent: an id beside every
    // title is noise a reader learns to skip, which is how it would fail to help
    // on the two rows where it matters.
    expect(toExperimentSummary(baseSummary()).disambiguator).toBeUndefined();
    expect(toExperimentSummary(baseSummary(), { ambiguousTitle: true }).disambiguator).toBe(
      '01SYNTH1',
    );
  });

  it('prefers updated_utc for the row date and still maps created_utc', () => {
    const row = toExperimentSummary(
      baseSummary({ created_utc: '2026-07-12T10:00:00Z', updated_utc: '2026-08-01T09:00:00Z' }),
    );
    expect(row.updated?.iso).toBe('2026-08-01');
    expect(row.updated?.accessible).toBe('Last updated August 1, 2026');
    // The created date is still mapped, so the row can fall back to it when a
    // response carried no `updated_utc` at all.
    expect(row.date?.iso).toBe('2026-07-12');
    expect(row.date?.accessible).toBe('Created July 12, 2026');
  });
});

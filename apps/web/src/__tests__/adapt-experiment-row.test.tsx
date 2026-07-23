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

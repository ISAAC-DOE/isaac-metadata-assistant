/*
 * RAW IDENTIFIERS AND MIS-CASED LABELS ON SCIENTIST SCREENS — QA A-15/A-16
 * (2026-10-12). Presentation only: every assertion below is about what a label READS;
 * no path, value or stored token changes, and each raw token stays available to a
 * curator (in a `title`, a `?`, or the value sent).
 */
import { describe, it, expect } from 'vitest';

import { fieldLabel } from '../lib/fieldLabels';
import { fieldPathLabel, humanizeSegment } from '../lib/recordMap';
import { activityFieldLabel } from '../components/ActivityHistoryPanel';
import { evidenceSourceLabel, sourceTypeWords } from '../components/EvidenceRow';
import { RECORD_FIELDS } from '../lib/recordFields';

describe('a path segment keeps the schema’s casing (A-16)', () => {
  it('a formula is not lowercased — "CuO2", never "Cuo2"', () => {
    expect(humanizeSegment('CuO2_mass_fraction')).toBe('CuO2 Mass Fraction');
    expect(fieldPathLabel('sample.composition.CuO2_mass_fraction')).toBe(
      'Sample · CuO2 Mass Fraction',
    );
  });

  it('a trailing unit reads as a unit — "(mm)", never "Mm"', () => {
    expect(humanizeSegment('pellet_diameter_mm')).toBe('Pellet Diameter (mm)');
    expect(humanizeSegment('temperature_K')).toBe('Temperature (K)');
  });

  it('every output word is an input word (casing and the unit’s parentheses only)', () => {
    for (const segment of ['CuO2_mass_fraction', 'pellet_diameter_mm', 'acquired_start_utc']) {
      const words = humanizeSegment(segment)
        .split(' ')
        .map((w) => w.replace(/[()]/g, '').toLowerCase());
      expect(words).toEqual(segment.toLowerCase().split('_'));
    }
  });

  it('the Record Description label uses the same spelling as every other surface', () => {
    const spec = RECORD_FIELDS.find((f) => f.path === 'sample.composition.CuO2_mass_fraction');
    expect(spec?.label).toBe('CuO2 mass fraction');
  });
});

describe('one name for the QC verdict (A-16)', () => {
  it('a finding at `measurement.qc.status` is called what every blocker summary calls it', () => {
    expect(fieldLabel('measurement.qc.status')).toBe('QC Verdict');
    expect(fieldLabel('$.measurement.qc.status')).toBe('QC Verdict');
  });
});

describe('stored tokens read as words (A-15)', () => {
  it('an Activity address drops its namespace and reads as the field', () => {
    expect(activityFieldLabel('block:tags')).toBe('Tags');
    expect(activityFieldLabel('field:sample.material.name')).toBe('Sample · Material Name');
    expect(activityFieldLabel('context.temperature_K')).toBe('Temperature');
  });

  it('an evidence source type reads as words, casing only', () => {
    expect(evidenceSourceLabel('user_confirmation')).toBe('User Confirmation');
    expect(evidenceSourceLabel('file_listing')).toBe('File Listing');
  });
});

describe('an UNKNOWN source type is shown verbatim everywhere (review minor)', () => {
  it('known types read as words; an unrecognised one is printed as stored', () => {
    expect(sourceTypeWords('user_confirmation')).toBe('User Confirmation');
    expect(sourceTypeWords('some_future_kind')).toBe('some_future_kind');
  });
});

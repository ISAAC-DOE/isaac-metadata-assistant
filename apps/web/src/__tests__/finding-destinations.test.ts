/*
 * Where a validation finding can send the reader, and what it is called — review
 * #277, I-9. jsonschema reports a missing `required` property at the PARENT's path,
 * and the structured detail naming the child is dropped inside the truth plane, so
 * both the name and the destination are derived from the PATH alone. The message
 * text is never read here.
 */
import { describe, it, expect } from 'vitest';
import { goToDestination } from '../components/BlockerItems';
import { fieldLabel } from '../lib/fieldLabels';
import { fieldPathLabel } from '../lib/recordMap';

describe('a field path, in words', () => {
  it('a single-segment path is its BLOCK, by the block’s own name', () => {
    expect(fieldPathLabel('context')).toBe('Environment & Context');
    expect(fieldPathLabel('system')).toBe('System & Instrument');
    expect(fieldPathLabel('links')).toBe('Relationships');
  });

  it('an indexed path keeps its index', () => {
    expect(fieldPathLabel('tags.0')).toBe('Tags · 0');
  });

  it('a generic last word keeps what it belongs to, and an acronym keeps its case', () => {
    expect(fieldPathLabel('measurement.qc.status')).toBe('Measurement · QC Status');
    expect(fieldPathLabel('sample.material.name')).toBe('Sample · Material Name');
    expect(fieldPathLabel('system.facility.site')).toBe('System & Instrument · Site');
  });

  it('run-level fields use their own labels; the whole document names no field', () => {
    expect(fieldLabel('context.temperature_K')).toBe('Temperature');
    expect(fieldLabel('$')).toBeNull();
    // Namespaces, not path: a `$.` root and the draft's `fields.` envelope map.
    expect(fieldLabel('$.measurement.series')).toBe('Measurement · Series');
    expect(fieldLabel('fields.context.temperature_K')).toBe('Temperature');
    expect(fieldLabel('')).toBeNull();
  });
});

describe('where a finding can send the reader — only where something real exists', () => {
  const E = 'EXP';
  const R = 'RUN1';

  it('a run-level field on a run → that field’s input', () => {
    const d = goToDestination(E, R, 'context.temperature_K')!;
    expect(d.label).toBe('Go to Field');
    expect(decodeURIComponent(d.href)).toContain('at=field:context.temperature_K');
    expect(d.href).toContain('run=RUN1');
  });

  it('a `required` error at a PARENT of run fields (`context`) → the run’s Conditions', () => {
    const d = goToDestination(E, R, 'context')!;
    expect(d.label).toBe('Go to Run Conditions');
    expect(decodeURIComponent(d.href)).toContain('at=section:run-conditions');
  });

  it('under the spectrum / QC / descriptors → Complete Metadata', () => {
    expect(goToDestination(E, R, 'measurement.qc.status')).toEqual({
      href: '/record/EXP/complete',
      label: 'Go to Complete Metadata',
    });
    expect(goToDestination(E, null, 'descriptors')?.label).toBe('Go to Complete Metadata');
  });

  it('under a Record Fields section → that section, expanded on arrival', () => {
    const d = goToDestination(E, null, 'sample.material')!;
    expect(d.label).toBe('Go to Section');
    expect(decodeURIComponent(d.href)).toBe('/record/EXP?view=fields&at=block:sample');
  });

  it('NOTHING for the whole document, an unknown block, or no record', () => {
    expect(goToDestination(E, R, '$')).toBeNull();
    expect(goToDestination(E, R, '')).toBeNull();
    expect(goToDestination(E, R, 'attribution.contributors.0.name')).toBeNull();
    expect(goToDestination(undefined, R, 'context.temperature_K')).toBeNull();
  });

  it('a run field WITHOUT a run offers no run form (there is no run to open)', () => {
    // `context.temperature_K` with no run: not a Record Fields section path either,
    // because `context` IS one — so it goes to that section instead.
    expect(goToDestination(E, null, 'context.temperature_K')?.label).toBe('Go to Section');
  });
});

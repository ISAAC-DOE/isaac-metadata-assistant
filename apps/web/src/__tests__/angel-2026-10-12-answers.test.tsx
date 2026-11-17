/*
 * THE DOMAIN OWNER'S 2026-10-12 ANSWERS ON THE RUN SURFACES.
 *
 * Provenance: an OWNER RELAY of the domain owner's (Angel's) words, relayed by the project
 * owner on 2026-10-12 — only Krish can confirm the relay, only Angel the content.
 *
 *   The Run editor offers the reaction and the cell type as the schema's own options.
 *
 * ~~1. A sample-position disagreement … 2. "Left for You to Choose" …~~ — removed
 * 2026-11-16 with the in-browser import flow they were about (historical import is the
 * Claude Code skill's job now; `/imports` is its guide).
 */
import { describe, expect, it } from 'vitest';
import { RUN_FIELDS, enumOptionLabel } from '../lib/runFields';

describe('the Run editor offers the reaction and the cell type', () => {
  it('as closed-enum selects whose options are the schema’s own tokens', () => {
    const reaction = RUN_FIELDS.find((f) => f.path === 'context.electrochemistry.reaction');
    const cell = RUN_FIELDS.find((f) => f.path === 'context.electrochemistry.cell_type');
    expect(reaction?.kind).toBe('enum');
    expect(cell?.kind).toBe('enum');
    expect(reaction?.options).toContain('OER');
    expect(cell?.options).toContain('three_electrode');
    // Pinned against the vendored schema by apps/api/tests/test_angel_2026_10_12_answers.py.
  });

  it('labels an abbreviation in capitals and changes nothing but casing', () => {
    expect(enumOptionLabel('gde_cell')).toBe('GDE cell');
    expect(enumOptionLabel('mea_cell')).toBe('MEA cell');
    expect(enumOptionLabel('three_electrode')).toBe('Three electrode');
    expect(enumOptionLabel('OER')).toBe('OER');
  });
});

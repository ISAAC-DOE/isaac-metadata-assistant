/*
 * THE DOMAIN OWNER'S 2026-10-12 ANSWERS ON THE IMPORT AND RUN SURFACES.
 *
 * Provenance: an OWNER RELAY of the domain owner's (Angel's) words, relayed by the project
 * owner on 2026-10-12 — only Krish can confirm the relay, only Angel the content. Every
 * value below is synthetic (`ZZ` stems, `FAKE/` paths).
 *
 *   1. A sample-position disagreement resolved by the standing rule reads as RESOLVED, by
 *      the domain owner's rule, with both readings named by the kind of source they are.
 *   2. "Left for You to Choose" says, per field, how many runs it leaves blank and where
 *      to choose — every number the server's.
 *   3. The Run editor offers the reaction and the cell type as the schema's own options.
 */
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ImportConflicts } from '../components/ImportConflicts';
import { conflictViews } from '../lib/importStages';
import { RUN_FIELDS, enumOptionLabel } from '../lib/runFields';
import { LeftForAPerson } from '../screens/HistoricalImport';
import type { ApiImportLeftForAPerson, ApiImportSession } from '../lib/types';

const STEM = '04_02_ZZ2_base_after500Cycling_filter20_800mV';
const STANDING = {
  rule_id: 'bl15.resolution.recorded_motor_position.v1',
  rule_version: 1,
  authority: 'domain_owner_rule' as const,
  layer: 'scientist_confirmed_resolution',
  chosen_source_role: 'instrument_header',
  chosen_source_role_meaning: 'The raw acquisition file: the motor position the instrument recorded, scan by scan.',
  over_source_role: 'planned_acquisition',
  over_source_role_meaning: 'A run file: the move command a person wrote before the measurement.',
  statement:
    'The position the acquisition file recorded is the one used. A move command in a run file is written by hand and can be out of date; the raw file records where the motor actually was. Both readings are kept.',
  attribution:
    'Angel (domain owner), relayed by the project owner on 2026-10-12. No transcript is committed; only Krish can confirm the relay and only Angel the content.',
  confirmed: '2026-10-12',
  reading_used: [
    { scan: '1', item: 'Sx', value: 'Sx 12.5', source_ids: ['S1'], locators: ['FAKE/001.dat · #P0 Sx'] },
    { scan: '2', item: 'Sx', value: 'Sx 12.5', source_ids: ['S1'], locators: ['FAKE/002.dat · #P0 Sx'] },
  ],
  every_reading_kept: true as const,
  writes_a_record_field: false as const,
  applied: true as const,
};

function session(): ApiImportSession {
  return {
    corpus_review: null,
    sources: [{ source_id: 'S1', filename: 'FAKE archive' }],
    archive: null,
    reconstruction: {
      candidates: [
        {
          candidate_id: `${STEM}::sample_position`,
          kind: 'field',
          determinism: 'deterministic',
          rule: 'FAKE warrant',
          supporting_source_ids: ['S1'],
          supporting_statements: [],
          target_field_path: null,
          proposed_value: null,
          disagreement: [
            { value: 'Sx 12.5', source_ids: ['S1', 'S1'], locators: ['FAKE/001.dat · #P0 Sx', 'FAKE/002.dat · #P0 Sx'] },
            { value: 'Sx 13.0', source_ids: ['S1'], locators: ['FAKE/run01.mac · line 7 `mv`'] },
          ],
          unresolved_reason: 'sources_disagree',
          not_proposable_reason: 'FAKE no field',
          proposable: false,
          agreement: 'sources_conflict',
          review_status: 'resolved',
          resolved_by_rule: STANDING.rule_id,
          standing_resolution: STANDING,
        },
      ],
    },
  } as unknown as ApiImportSession;
}

describe('a position disagreement the standing rule resolves', () => {
  it('names each reading by the kind of source it is and shows the readings used once', () => {
    const [view] = conflictViews(session());
    expect(view.readings.map((r) => [r.role, r.value])).toEqual([
      ['instrument_header', 'Sx 12.5'],
      ['planned_acquisition', 'Sx 13.0'],
    ]);
    expect(view.resolution?.authority).toBe('domain_owner_rule');
    // Two scans recording the same position is one reading used, not two.
    expect(view.resolution?.chosen_value).toBe('Sx 12.5');
  });

  it('reads as resolved by the domain owner’s rule, both readings on the surface, the rule and its source behind Review Sources', () => {
    const { container } = render(
      <MemoryRouter>
        <ImportConflicts
          conflicts={conflictViews(session())}
          importId="IMPZZ"
          busy={null}
          onAct={async (_n, run) => {
            await run();
          }}
          destinations={{ rows: [], failed: false, reload: async () => {} }}
        />
      </MemoryRouter>,
    );
    const row = container.querySelector('li.hi-conflict')!;
    expect(row.className).toContain('is-resolved');
    const main = row.querySelector('.hi-conflict-main')!.textContent!.replace(/\s+/g, ' ');
    expect(main).toContain('Header Sx 12.5');
    expect(main).toContain('Macro Sx 13.0');
    expect(main).toContain("Resolved by the domain owner's rule: The position the acquisition file recorded is the one used (Sx 12.5).");
    expect(main).toContain('Every reading is still kept.');
    // NOT the sentence a scientist-recorded rule gets.
    expect(main).not.toContain('a rule you recorded');
    const layers = row.querySelector('.hi-layers')!;
    expect(layers.textContent).toContain('Confirmed by the domain owner.');
    expect(layers.textContent).toContain('Nothing is written to the record.');
    // THE PROVENANCE IS DETAIL (review, 2026-10-12): the rule id and the owner-relay
    // sentence live in the `?` panel, and NOT in the sentence a scientist reads.
    expect(within(layers as HTMLElement).getByRole('button', { name: 'About who confirmed this rule', hidden: true })).toBeInTheDocument();
    const panel = layers.querySelector('.helptip-panel')!;
    expect(panel.textContent).toContain('bl15.resolution.recorded_motor_position.v1');
    expect(panel.textContent).toContain('relayed by the project owner on 2026-10-12');
    const visible = (layers.textContent ?? '').replace(panel.textContent ?? '', '');
    expect(visible).not.toContain('No transcript is committed');
    expect(visible).not.toContain('relayed by the project owner');
    // No resolve form is offered for it: it is already resolved.
    expect(within(row as HTMLElement).queryByRole('button', { name: /Record/ })).toBeNull();
  });
});

const LEFT: ApiImportLeftForAPerson = {
  rule: 'Markers, descriptors and values are taken from the metadata the import reads. When the metadata does not state one, it is left blank for a person to choose — never guessed and never filled in from another experiment.',
  attribution: 'FAKE attribution',
  where: "Choose them on each run: open the record's Runs, open the run, and set them under Conditions for this run.",
  reasons: { not_stated: 'No file this import read states it.', sources_disagree: 'The sources state different values, and nothing was chosen.' },
  runs: 3,
  fields: [
    { path: 'context.environment', label: 'Environment', left: 1, offered: 2, options: ['operando', 'in_situ', 'ex_situ', 'in_silico'] },
    { path: 'context.electrochemistry.reaction', label: 'Reaction', left: 3, offered: 0, options: ['OER'] },
    { path: 'context.electrochemistry.cell_type', label: 'Cell type', left: 0, offered: 3, options: ['three_electrode'] },
  ],
  by_measurement: {
    '01_01_ZZ1_x': [{ path: 'context.electrochemistry.reaction', label: 'Reaction', reason: 'not_stated' }],
    '09_04_ZZ4_AsIs_NoElectrolyte': [
      { path: 'context.environment', label: 'Environment', reason: 'sources_disagree' },
      { path: 'context.electrochemistry.reaction', label: 'Reaction', reason: 'not_stated' },
    ],
    '02_01_ZZ1_y': [],
  },
  fills_anything: false,
};

describe('Left for You to Choose', () => {
  it('says per field how many runs are left blank, how many were proposed, and where to choose — all from the server', () => {
    render(
      <MemoryRouter>
        <LeftForAPerson left={LEFT} />
      </MemoryRouter>,
    );
    const block = screen.getByRole('region', { name: 'Left for You to Choose' });
    const text = block.textContent!.replace(/\s+/g, ' ');
    expect(text).toContain(LEFT.rule);
    expect(text).toContain('Environment blank on 1 of 3 runs · 2 proposed from what the files state');
    expect(text).toContain('Reaction blank on 3 of 3 runs');
    expect(text).toContain('Cell type Nothing left blank · 3 proposed from what the files state');
    expect(text).toContain(LEFT.where);
    // Per measurement, with the server's own reason — and a measurement with nothing
    // left is not listed.
    expect(text).toContain('09_04_ZZ4_AsIs_NoElectrolyte');
    expect(text).toContain('Environment — The sources state different values, and nothing was chosen.');
    expect(text).not.toContain('02_01_ZZ1_y');
  });

  it('renders nothing for an import with no runs to choose on', () => {
    const { container } = render(<LeftForAPerson left={{ ...LEFT, runs: 0 }} />);
    expect(container.textContent).toBe('');
  });
});

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

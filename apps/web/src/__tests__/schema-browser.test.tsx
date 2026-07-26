/**
 * P36.6 / P36R S8 — the read-only Schema Reference browser (Governance &
 * Safety > Schema Reference).
 *
 * `SchemaBrowser` fetches `GET /api/schema` and renders EVERY field, type,
 * required/optional flag, allowed value, example, description, rule, and
 * vocabulary term verbatim from that response — it computes no verdict and
 * invents nothing.
 *
 * P36R S8 restructured the surface into three subviews. These tests pin:
 *   - the inner tablist (Fields · Conditional Rules · Vocabulary), its default,
 *     its `aria-selected`/`aria-controls` wiring, and Arrow/Home/End keys;
 *   - Fields as a MASTER-DETAIL browser: a searchable flat list plus one
 *     detail panel carrying path, verbatim description, type, required/optional,
 *     allowed values, pattern, examples, nested structure, related conditional
 *     rules, and source/version — never everything expanded at once;
 *   - Conditional Rules presented as trigger / consequence / affected paths,
 *     searchable, with the raw JSON-Schema clause behind a disclosure;
 *   - Vocabulary rendering the REAL controlled-vocabulary content with its own
 *     provenance note and source, the schema↔vocabulary link made legible, and
 *     the honest empty state as the FALLBACK branch;
 *   - loading / backend-down states reuse the shared FetchStates components;
 *   - every control is keyboard-reachable, and there is NO
 *     edit/propose/approve/save control anywhere.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import { SchemaBrowser } from '../components/SchemaBrowser';
import {
  fieldsCitingVocabulary,
  vocabularySourceSlug,
  type SchemaFieldNode,
} from '../lib/schemaBrowser';
import { stubFetchRoutes, stubFetchDown, schemaBrowserFixture } from '../test/apiFixtures';

const URL = 'GET /api/schema';

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubSchema(body: unknown = schemaBrowserFixture) {
  return stubFetchRoutes({ [URL]: { body: body as never } });
}

/**
 * The real schema's `context.electrochemistry` conditional rule, reproduced
 * clause-for-clause from `schema/isaac_record_v1.json` (`allOf[1]`), plus a
 * SIBLING subtree the rule says nothing about. The rule names
 * `context.electrochemistry` and `context.electrochemistry.control_mode`;
 * `context.electrochemistry.anolyte.notes` is merely a descendant of a named
 * path, which is not the same thing and must not be presented as one.
 */
const electrochemistryRuleFixture = {
  schema_title: 'ISAAC AI-Ready Scientific Record v1.05 (fixture)',
  schema_version: '1.05',
  schema: {
    required: ['record_domain'],
    allOf: [
      {
        if: {
          properties: {
            record_domain: { const: 'performance' },
            context: { type: 'object', required: ['electrochemistry'] },
          },
          required: ['record_domain', 'context'],
        },
        then: {
          properties: {
            context: { properties: { electrochemistry: { required: ['control_mode'] } } },
          },
        },
      },
    ],
    properties: {
      record_domain: { type: 'string', enum: ['performance', 'characterization'] },
      context: {
        type: 'object',
        description: 'Domain-specific experimental context.',
        properties: {
          electrochemistry: {
            type: 'object',
            description: 'Electrochemical operating context.',
            properties: {
              control_mode: { type: 'string', enum: ['galvanostatic', 'potentiostatic'] },
              anolyte: {
                type: 'object',
                properties: {
                  notes: { type: 'string', description: 'Free-text operator notes.' },
                },
              },
            },
          },
        },
      },
    },
  },
  vocabularies: {},
};

/**
 * A vocabulary file whose source slug is a bare English word, alongside a
 * schema field whose description merely USES that word. Vocabulary files are
 * auto-globbed by the backend, so this is a shape a future file could really
 * take — and it must produce no citation claim at all.
 */
const genericSlugFixture = {
  schema_title: 'ISAAC AI-Ready Scientific Record v1.05 (fixture)',
  schema_version: '1.05',
  schema: {
    properties: {
      current_density: {
        type: 'number',
        description: 'Current density, in the units the instrument reported.',
      },
    },
  },
  vocabularies: {
    units: {
      field: 'units',
      note: 'Fixture units vocabulary (synthetic, for tests).',
      source: 'https://example.invalid/wiki/Units',
      allowed: ['eV', 'mA_cm2'],
    },
  },
};

/** Freeze an object graph in place — any write attempt throws in strict mode. */
function deepFreeze<T>(value: T): T {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child);
  }
  return value;
}

/** A minimal field node — only the keys the citation helpers actually read. */
function fieldWithDescription(description: string): SchemaFieldNode {
  return { path: 'a', name: 'a', typeLabel: 'string', required: false, depth: 0, description };
}

/**
 * A row in the Fields master list. Each row carries the field's bare NAME in
 * `.schema-field-name`; the dotted path lives only in the detail panel, so this
 * selector identifies a list row unambiguously (the way a user would).
 */
function row(text: string): HTMLElement {
  return screen.getByText(text, { selector: '.schema-field-name' });
}
async function findRow(text: string): Promise<HTMLElement> {
  return screen.findByText(text, { selector: '.schema-field-name' });
}
function rowButton(name: HTMLElement): HTMLElement {
  return name.closest('button') as HTMLElement;
}
/** `.schema-field-head` wraps only a row's own name/type/badge. */
function badgeFor(name: HTMLElement): HTMLElement {
  const head = name.closest('.schema-field-head') as HTMLElement;
  return head.querySelector('.schema-field-badge') as HTMLElement;
}
function detail(): HTMLElement {
  return document.querySelector('.schema-fields-detailpane') as HTMLElement;
}
async function selectView(name: RegExp | string) {
  fireEvent.click(await screen.findByRole('tab', { name }));
}

// --- inner subview navigation ------------------------------------------------

describe('SchemaBrowser — subviews', () => {
  it('exposes an inner tablist with Fields, Conditional Rules, and Vocabulary', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    expect(await screen.findByRole('tablist', { name: /Schema Reference views/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Fields' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Conditional Rules' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Vocabulary' })).toBeInTheDocument();
  });

  it('Fields is the default subview', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    const fields = await screen.findByRole('tab', { name: 'Fields' });
    expect(fields).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Conditional Rules' })).toHaveAttribute(
      'aria-selected',
      'false',
    );
    // The Fields panel is the one mounted, and the tab controls it.
    const panel = screen.getByRole('tabpanel');
    expect(fields).toHaveAttribute('aria-controls', panel.id);
    expect(panel).toHaveAttribute('aria-labelledby', fields.id);
  });

  it('renders the card heading as "Schema Reference"', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    expect(await screen.findByRole('heading', { name: 'Schema Reference', level: 2 })).toBeInTheDocument();
  });

  it('switching subviews swaps the panel', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await findRow('record_id');

    await selectView('Conditional Rules');
    expect(screen.getByRole('tab', { name: 'Conditional Rules' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.queryByText('record_id', { selector: '.schema-field-name' })).toBeNull();
    expect(screen.getByLabelText(/search rules/i)).toBeInTheDocument();

    await selectView('Vocabulary');
    expect(screen.getByLabelText(/search vocabulary/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/search rules/i)).toBeNull();
  });

  it('Arrow/Home/End move the inner subview selection and focus (roving tabindex)', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    const fields = await screen.findByRole('tab', { name: 'Fields' });
    expect(fields).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: 'Vocabulary' })).toHaveAttribute('tabindex', '-1');

    fields.focus();
    fireEvent.keyDown(fields, { key: 'ArrowRight' });
    const rules = screen.getByRole('tab', { name: 'Conditional Rules' });
    expect(rules).toHaveAttribute('aria-selected', 'true');
    expect(rules).toHaveFocus();

    fireEvent.keyDown(rules, { key: 'End' });
    const vocab = screen.getByRole('tab', { name: 'Vocabulary' });
    expect(vocab).toHaveAttribute('aria-selected', 'true');
    expect(vocab).toHaveFocus();

    fireEvent.keyDown(vocab, { key: 'Home' });
    expect(screen.getByRole('tab', { name: 'Fields' })).toHaveAttribute('aria-selected', 'true');
  });
});

// --- Fields: master list -----------------------------------------------------

describe('SchemaBrowser — Fields master list', () => {
  it('lists fields at every depth with an honest required/optional TEXT badge', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    expect(badgeFor(await findRow('record_id'))).toHaveTextContent('Required');
    expect(badgeFor(row('sample'))).toHaveTextContent('Optional');
    // Nested fields are rows of the same flat list — no expand step needed.
    expect(badgeFor(row('sample_form'))).toHaveTextContent('Required');
    expect(badgeFor(row('material'))).toHaveTextContent('Optional');
    expect(row('formula')).toBeInTheDocument();
  });

  it('does not expand every field at once — only the SELECTED field is described', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('record_id')));
    expect(within(detail()).getByText('ULID identifier for the record.')).toBeInTheDocument();
    // The real guard: a NON-selected field's description is nowhere in the DOM.
    // The master list carries names/types/badges only, and one detail renders.
    expect(screen.queryByText('Fundamental nature of the record.')).toBeNull();
    expect(screen.queryByText('The physical sample under study.')).toBeNull();
    expect(screen.queryByText('Free-form, user-assigned grouping labels.')).toBeNull();
    expect(document.querySelectorAll('.schema-field-detail')).toHaveLength(1);
  });

  it('renders the schema title, version, and read-only source line', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await findRow('record_id');
    expect(
      screen.getAllByText(/ISAAC AI-Ready Scientific Record v1\.05 \(fixture\) — v1\.05/).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/vendored official schema \(read-only reference\)/).length,
    ).toBeGreaterThan(0);
  });

  it('never renders any propose/review/approve/edit control', async () => {
    stubSchema();
    const { container } = render(<SchemaBrowser />);
    await findRow('record_id');
    expect(screen.queryByRole('button', { name: /propose|approve|edit|delete|save/i })).toBeNull();
    expect(container.querySelector('input[type="text"], textarea')).toBeNull();
  });
});

// --- Fields: master-list keyboard model (roving tabindex) ---------------------

describe('SchemaBrowser — Fields master list keyboard model', () => {
  it('puts exactly ONE row in the tab order (roving tabindex), not every row', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await findRow('record_id');
    const buttons = [...document.querySelectorAll('.schema-field-btn')] as HTMLElement[];
    expect(buttons.length).toBeGreaterThan(5);
    expect(buttons.filter((b) => b.tabIndex === 0)).toHaveLength(1);
    expect(buttons.filter((b) => b.tabIndex === -1)).toHaveLength(buttons.length - 1);
  });

  it('Arrow/Home/End move the cursor and focus WITHOUT changing the selection', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    const first = rowButton(await findRow('isaac_record_version'));
    // The first visible field is selected by default, and carries the cursor.
    expect(first).toHaveAttribute('aria-current', 'true');
    expect(first.tabIndex).toBe(0);

    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowDown' });
    const second = rowButton(row('record_id'));
    expect(second).toHaveFocus();
    expect(second.tabIndex).toBe(0);
    expect(first.tabIndex).toBe(-1);
    // Focus moved; the SELECTION did not — the detail pane is unchanged.
    expect(second).not.toHaveAttribute('aria-current');
    expect(first).toHaveAttribute('aria-current', 'true');
    expect(
      within(detail()).getByText('isaac_record_version', { selector: '.schema-fielddetail-path' }),
    ).toBeInTheDocument();

    fireEvent.keyDown(second, { key: 'End' });
    expect(rowButton(row('tags'))).toHaveFocus();

    fireEvent.keyDown(rowButton(row('tags')), { key: 'Home' });
    expect(rowButton(row('isaac_record_version'))).toHaveFocus();

    // Still exactly one selected row, and it is still the original one.
    expect(document.querySelectorAll('[aria-current="true"]')).toHaveLength(1);
    expect(
      within(detail()).getByText('isaac_record_version', { selector: '.schema-fielddetail-path' }),
    ).toBeInTheDocument();
  });

  it('clicking a row moves the cursor onto it, so it stays a single tab stop', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    const target = rowButton(await findRow('formula'));
    fireEvent.click(target);
    expect(target.tabIndex).toBe(0);
    const buttons = [...document.querySelectorAll('.schema-field-btn')] as HTMLElement[];
    expect(buttons.filter((b) => b.tabIndex === 0)).toHaveLength(1);
  });

  it('the detail pane is a named region and a programmatic focus target', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('record_id')));
    const pane = detail();
    expect(pane).toHaveAttribute('role', 'region');
    expect(pane).toHaveAttribute('tabindex', '-1');
    const heading = within(pane).getByRole('heading', { level: 3, name: 'record_id' });
    expect(heading.id).not.toBe('');
    expect(pane.getAttribute('aria-labelledby')).toBe(heading.id);
  });
});

// --- Fields: search ----------------------------------------------------------

describe('SchemaBrowser — Fields search', () => {
  it('filters the field list by name/path/description', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await findRow('record_id');
    expect(row('sample')).toBeInTheDocument();
    expect(row('tags')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/search fields/i), { target: { value: 'ULID' } });

    expect(row('record_id')).toBeInTheDocument();
    expect(screen.queryByText('sample', { selector: '.schema-field-name' })).toBeNull();
    expect(screen.queryByText('tags', { selector: '.schema-field-name' })).toBeNull();
  });

  it('reports how many fields the search narrowed the list to', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await findRow('record_id');
    const heading = screen.getByRole('heading', { name: /^Fields/, level: 3 });
    const total = document.querySelectorAll('.schema-field-btn').length;
    expect(heading).toHaveTextContent(String(total));

    fireEvent.change(screen.getByLabelText(/search fields/i), { target: { value: 'ULID' } });
    expect(document.querySelectorAll('.schema-field-btn')).toHaveLength(1);
    expect(screen.getByRole('heading', { name: /^Fields/, level: 3 })).toHaveTextContent(
      `1 of ${total}`,
    );
  });

  it('shows an honest empty state for a query with no matches', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await findRow('record_id');
    fireEvent.change(screen.getByLabelText(/search fields/i), {
      target: { value: 'no-such-field-anywhere' },
    });
    expect(await screen.findByText(/no fields match/i)).toBeInTheDocument();
    expect(screen.getByText(/no field selected/i)).toBeInTheDocument();
  });

  it('the search input is a real, keyboard-reachable <input>', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await findRow('record_id');
    const input = screen.getByLabelText(/search fields/i);
    expect(input.tagName).toBe('INPUT');
    expect(input).toHaveAttribute('type', 'search');
    expect(input).not.toHaveAttribute('tabindex', '-1');
  });
});

// --- Fields: selection + detail ----------------------------------------------

describe('SchemaBrowser — Fields detail panel', () => {
  it('selecting a field renders its path, verbatim description, type and requirement', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('record_id')));

    const pane = within(detail());
    expect(pane.getByRole('heading', { name: 'record_id', level: 3 })).toBeInTheDocument();
    expect(pane.getByText('record_id', { selector: '.schema-fielddetail-path' })).toBeInTheDocument();
    // Description read VERBATIM from the schema.
    expect(pane.getByText('ULID identifier for the record.')).toBeInTheDocument();
    expect(pane.getByText('string', { selector: '.schema-field-type' })).toBeInTheDocument();
    expect(pane.getByText('Required')).toBeInTheDocument();
  });

  it('marks the selected row with aria-current and points it at the detail panel', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    const button = rowButton(await findRow('record_type'));
    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-current', 'true');
    expect(button).toHaveAttribute('aria-controls', detail().id);
    expect(document.querySelectorAll('[aria-current="true"]')).toHaveLength(1);
  });

  it('renders the enum allowed values of the selected field', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('record_type')));
    const pane = within(detail());
    expect(pane.getByRole('heading', { name: /Allowed values \(3\)/i, level: 4 })).toBeInTheDocument();
    expect(pane.getByText('evidence')).toBeInTheDocument();
    expect(pane.getByText('intent')).toBeInTheDocument();
    expect(pane.getByText('synthesis')).toBeInTheDocument();
  });

  it('renders the schema-declared examples of the selected field', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('formula')));
    const pane = within(detail());
    expect(pane.getByRole('heading', { name: /Examples \(2\)/i, level: 4 })).toBeInTheDocument();
    expect(pane.getByText('CuO2')).toBeInTheDocument();
    expect(pane.getByText('Fe2O3')).toBeInTheDocument();
  });

  it('renders the pattern of a regex-constrained field, honestly labeled', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('record_id')));
    const pane = within(detail());
    expect(pane.getByRole('heading', { name: 'Pattern', level: 4 })).toBeInTheDocument();
    expect(pane.getByText('^[0-9A-Z]{26}$')).toBeInTheDocument();
    expect(pane.getByText(/does not list its allowed values inline/i)).toBeInTheDocument();
  });

  it('renders the nested structure of an object field and navigates into a child', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('sample')));
    const pane = within(detail());
    expect(pane.getByRole('heading', { name: /Nested fields \(2\)/i, level: 4 })).toBeInTheDocument();

    fireEvent.click(pane.getByRole('button', { name: 'material' }));
    expect(
      within(detail()).getByText('sample.material', { selector: '.schema-fielddetail-path' }),
    ).toBeInTheDocument();
    // …and back up via the parent link.
    fireEvent.click(within(detail()).getByRole('button', { name: 'sample' }));
    expect(
      within(detail()).getByText('sample', { selector: '.schema-fielddetail-path' }),
    ).toBeInTheDocument();
  });

  it('lists the conditional rules that name the selected field, and links to them', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    // The fixture declares two fields named `descriptors` (the top-level object
    // and the nested descriptor rows). The flat list is in schema declaration
    // order, so [0] is the top-level one.
    const rows = await screen.findAllByText('descriptors', { selector: '.schema-field-name' });
    fireEvent.click(rowButton(rows[0]));
    const pane = within(detail());
    expect(
      pane.getByRole('heading', { name: /Related conditional rules \(1\)/i, level: 4 }),
    ).toBeInTheDocument();
    expect(pane.getByText(/If record_type = "evidence", then descriptors is required\./)).toBeInTheDocument();

    // The list is labeled with the relation it actually asserts.
    expect(
      pane.getByRole('heading', { name: /Rules that name this field \(1\)/i, level: 5 }),
    ).toBeInTheDocument();

    fireEvent.click(pane.getByRole('button', { name: /open in conditional rules/i }));
    expect(screen.getByRole('tab', { name: 'Conditional Rules' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByLabelText(/search rules/i)).toHaveValue('descriptors');
  });

  it('separates "names this field" from "constrains a field nested inside it"', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    // No rule clause names `sample` itself; the schema's `sample` rule names
    // sample.sample_form and sample.material, both nested inside it.
    fireEvent.click(rowButton(await findRow('sample')));
    const pane = within(detail());
    expect(
      pane.getByRole('heading', { name: /Related conditional rules \(1\)/i, level: 4 }),
    ).toBeInTheDocument();
    expect(
      pane.getByRole('heading', {
        name: /Rules that constrain a field nested inside it \(1\)/i,
        level: 5,
      }),
    ).toBeInTheDocument();
    expect(pane.queryByRole('heading', { name: /Rules that name this field/i })).toBeNull();
  });

  it('says so honestly when no conditional rule names the field', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('tags')));
    expect(
      within(detail()).getByText(
        /No conditional rule in this schema names this field, or any field nested inside it\./i,
      ),
    ).toBeInTheDocument();
  });

  it('never attributes a rule to a field it only ENCLOSES (sample.material.formula)', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('formula')));
    const pane = within(detail());
    expect(
      pane.getByText('sample.material.formula', { selector: '.schema-fielddetail-path' }),
    ).toBeInTheDocument();
    // `sample.material` is named by a rule; `sample.material.formula` is not.
    expect(
      pane.getByRole('heading', { name: /Related conditional rules \(0\)/i, level: 4 }),
    ).toBeInTheDocument();
    expect(pane.queryByText(/sample\.material is required/)).toBeNull();
    expect(pane.getByText(/or any field nested inside it/i)).toBeInTheDocument();
  });

  it('the real electrochemistry rule is not attributed to a sibling notes field', async () => {
    stubSchema(electrochemistryRuleFixture);
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('notes')));
    const pane = within(detail());
    expect(
      pane.getByText('context.electrochemistry.anolyte.notes', {
        selector: '.schema-fielddetail-path',
      }),
    ).toBeInTheDocument();
    expect(
      pane.getByRole('heading', { name: /Related conditional rules \(0\)/i, level: 4 }),
    ).toBeInTheDocument();
    expect(pane.queryByText(/control_mode is required/)).toBeNull();
    expect(pane.queryByRole('button', { name: /open in conditional rules/i })).toBeNull();
  });

  it('…while the fields that rule really does name still carry it', async () => {
    stubSchema(electrochemistryRuleFixture);
    render(<SchemaBrowser />);

    // Named directly by the `if` clause.
    fireEvent.click(rowButton(await findRow('electrochemistry')));
    expect(
      within(detail()).getByRole('heading', {
        name: /Rules that name this field \(1\)/i,
        level: 5,
      }),
    ).toBeInTheDocument();

    // `context` is named by no clause, but the rule constrains fields inside it.
    fireEvent.click(rowButton(row('context')));
    expect(
      within(detail()).getByRole('heading', {
        name: /Rules that constrain a field nested inside it \(1\)/i,
        level: 5,
      }),
    ).toBeInTheDocument();
  });

  it('shows the source and version the field was read from', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    fireEvent.click(rowButton(await findRow('record_id')));
    expect(
      within(detail()).getByText(/ISAAC AI-Ready Scientific Record v1\.05 \(fixture\) — v1\.05/),
    ).toBeInTheDocument();
  });
});

// --- Conditional Rules -------------------------------------------------------

describe('SchemaBrowser — Conditional Rules', () => {
  it('presents each rule as trigger / consequence / affected paths, not raw JSON first', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Conditional Rules');

    const cards = document.querySelectorAll('.schema-rule-card');
    expect(cards).toHaveLength(2);
    const first = within(cards[0] as HTMLElement);
    expect(first.getByRole('heading', { name: /Rule 1/, level: 4 })).toBeInTheDocument();
    expect(first.getByRole('heading', { name: 'Trigger condition', level: 5 })).toBeInTheDocument();
    expect(first.getByRole('heading', { name: 'Required consequence', level: 5 })).toBeInTheDocument();
    expect(first.getByRole('heading', { name: 'Affected field paths', level: 5 })).toBeInTheDocument();
    expect(first.getByText('record_type = "evidence"')).toBeInTheDocument();
    expect(first.getByText('descriptors is required')).toBeInTheDocument();
    // The plain-language sentence leads; the raw clause is behind a disclosure.
    expect(
      first.getByText(/If record_type = "evidence", then descriptors is required\./),
    ).toBeInTheDocument();
    expect(first.queryByText(/"allOf"/)).toBeNull();
  });

  it('labels each rule with the scope it is declared in', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Conditional Rules');
    const cards = document.querySelectorAll('.schema-rule-card');
    expect(within(cards[0] as HTMLElement).getByText('record')).toBeInTheDocument();
    expect(within(cards[1] as HTMLElement).getByText('sample')).toBeInTheDocument();
  });

  it('exposes the exact source clause behind a disclosure', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Conditional Rules');
    const card = document.querySelector('.schema-rule-card') as HTMLElement;
    const summary = within(card).getByText(/source rule \(raw json schema\)/i);
    fireEvent.click(summary);
    const raw = card.querySelector('.schema-rule-rawpre') as HTMLElement;
    // Byte-for-byte the schema's own allOf entry — nothing trimmed or rewritten.
    expect(JSON.parse(raw.textContent ?? '')).toEqual(schemaBrowserFixture.schema.allOf[0]);
  });

  it('search narrows the rule list and reports the count honestly', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Conditional Rules');
    expect(document.querySelectorAll('.schema-rule-card')).toHaveLength(2);

    fireEvent.change(screen.getByLabelText(/search rules/i), { target: { value: 'sample_form' } });
    expect(document.querySelectorAll('.schema-rule-card')).toHaveLength(1);
    expect(screen.getByRole('heading', { name: /^Conditional rules/, level: 3 })).toHaveTextContent(
      '1 of 2',
    );

    fireEvent.change(screen.getByLabelText(/search rules/i), { target: { value: 'zzz-nothing' } });
    expect(await screen.findByText(/no rules match/i)).toBeInTheDocument();
  });

  it('a rule keeps its ordinal from the UNFILTERED list under search', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Conditional Rules');
    const headings = [...document.querySelectorAll('.schema-rule-heading')].map(
      (h) => h.textContent ?? '',
    );
    expect(headings[0]).toMatch(/^Rule 1/);
    expect(headings[1]).toMatch(/^Rule 2/);

    fireEvent.change(screen.getByLabelText(/search rules/i), { target: { value: 'sample_form' } });
    const cards = document.querySelectorAll('.schema-rule-card');
    expect(cards).toHaveLength(1);
    // The survivor is the schema's SECOND rule — a filter must not renumber it.
    expect(
      within(cards[0] as HTMLElement).getByRole('heading', { name: /Rule 2/, level: 4 }),
    ).toBeInTheDocument();
    expect(within(cards[0] as HTMLElement).queryByRole('heading', { name: /Rule 1/ })).toBeNull();
  });

  it('an affected field path navigates back into the Fields detail', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Conditional Rules');
    const card = document.querySelector('.schema-rule-card') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: 'descriptors' }));

    expect(screen.getByRole('tab', { name: 'Fields' })).toHaveAttribute('aria-selected', 'true');
    expect(
      within(detail()).getByText('descriptors', { selector: '.schema-fielddetail-path' }),
    ).toBeInTheDocument();
  });

  it('states honestly when a schema declares no conditional rules', async () => {
    stubSchema({
      schema_title: 't',
      schema_version: '1.05',
      schema: { properties: { a: { type: 'string' } } },
      vocabularies: {},
    });
    render(<SchemaBrowser />);
    await selectView('Conditional Rules');
    expect(
      screen.getByText(/No conditional rules are declared in this schema\./i),
    ).toBeInTheDocument();
  });
});

// --- Vocabulary --------------------------------------------------------------

describe('SchemaBrowser — Vocabulary', () => {
  it('renders the real controlled-vocabulary terms as a browsable list', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Vocabulary');

    expect(screen.getByRole('heading', { name: /descriptor_class/, level: 4 })).toBeInTheDocument();
    expect(screen.getByText('white_line_energy')).toBeInTheDocument();
    expect(screen.getByText('edge_shift')).toBeInTheDocument();
    expect(screen.getByText('H2')).toBeInTheDocument();
    expect(screen.getByText('CO')).toBeInTheDocument();
  });

  it("shows the file's own provenance note and source, verbatim", async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Vocabulary');
    expect(screen.getByRole('heading', { name: 'Provenance', level: 5 })).toBeInTheDocument();
    expect(screen.getByText('Fixture vocabulary note (synthetic, for tests).')).toBeInTheDocument();
    expect(screen.getByText('https://example.invalid/wiki/Zebra-Terms')).toBeInTheDocument();
  });

  it('makes the schema ↔ vocabulary relationship legible, and navigates to the citing field', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Vocabulary');

    expect(
      screen.getByRole('heading', { name: /how the schema uses this/i, level: 5 }),
    ).toBeInTheDocument();
    expect(screen.getByText(/is constrained by a regular expression/i)).toBeInTheDocument();
    expect(screen.getByText(/pattern-constrained, not enumerated inline/i)).toBeInTheDocument();

    const path = 'descriptors.outputs.descriptors.name';
    fireEvent.click(screen.getByRole('button', { name: path }));
    expect(screen.getByRole('tab', { name: 'Fields' })).toHaveAttribute('aria-selected', 'true');
    expect(
      within(detail()).getByText(path, { selector: '.schema-fielddetail-path' }),
    ).toBeInTheDocument();
  });

  it('the cited slug is DERIVED from the file’s own source, not hard-coded', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Vocabulary');
    // The fixture's slug ("Zebra-Terms") shares no substring with production's
    // ("Controlled-Vocabulary"), so a hard-coded needle renders nothing here.
    const rendered = document.querySelector('.schema-vocab-linktext .mono') as HTMLElement;
    expect(rendered.textContent).toBe('Zebra-Terms');
    expect(screen.getByText(/One schema field cites/i)).toBeInTheDocument();
  });

  it('renders NO citation claim when the source slug is too generic to license one', async () => {
    stubSchema(genericSlugFixture);
    render(<SchemaBrowser />);
    await selectView('Vocabulary');
    // The file itself is still shown in full…
    expect(screen.getByRole('heading', { name: /units/, level: 4 })).toBeInTheDocument();
    expect(screen.getByText('mA_cm2')).toBeInTheDocument();
    expect(screen.getByText('https://example.invalid/wiki/Units')).toBeInTheDocument();
    // …but a schema description that merely uses the word "units" is not a
    // citation, so no relationship is asserted at all.
    expect(screen.queryByRole('heading', { name: /how the schema uses this/i })).toBeNull();
    expect(screen.queryByText(/schema field/i)).toBeNull();
    expect(document.querySelector('.schema-vocab-link')).toBeNull();
  });

  it('search narrows vocabulary terms', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Vocabulary');
    expect(screen.getByText('white_line_energy')).toBeInTheDocument();
    expect(screen.getByText('H2')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/search vocabulary/i), { target: { value: 'edge' } });
    expect(screen.getByText('edge_shift')).toBeInTheDocument();
    expect(screen.queryByText('white_line_energy')).toBeNull();
    expect(screen.queryByText('H2')).toBeNull();

    fireEvent.change(screen.getByLabelText(/search vocabulary/i), { target: { value: 'zzz' } });
    expect(await screen.findByText(/no terms match/i)).toBeInTheDocument();
  });

  it('counts the terms it renders instead of estimating', async () => {
    stubSchema();
    render(<SchemaBrowser />);
    await selectView('Vocabulary');
    // 2 spectroscopy classes + 2 products = 4 entries in the fixture.
    expect(screen.getByRole('heading', { name: /descriptor_class/, level: 4 })).toHaveTextContent(
      '4 entries',
    );
  });

  it('FALLBACK: an honest, compact empty state when no vocabulary file is bundled', async () => {
    stubSchema({ ...schemaBrowserFixture, vocabularies: {} });
    render(<SchemaBrowser />);
    await selectView('Vocabulary');
    expect(
      screen.getByText(/No controlled-vocabulary file is bundled with this deployment\./i),
    ).toBeInTheDocument();
    // It must not pretend the schema lost its authority.
    expect(screen.getByText(/The official schema remains the authority on allowed values/i)).toBeInTheDocument();
  });
});

// --- derivation guards (pure helpers) ----------------------------------------

describe('schemaBrowser — vocabulary citation derivation', () => {
  it('takes the page slug, ignoring a query string or fragment', () => {
    expect(vocabularySourceSlug('https://github.com/ISAAC-DOE/x/wiki/Controlled-Vocabulary')).toBe(
      'Controlled-Vocabulary',
    );
    expect(
      vocabularySourceSlug('https://github.com/ISAAC-DOE/x/wiki/Controlled-Vocabulary#classes'),
    ).toBe('Controlled-Vocabulary');
    expect(vocabularySourceSlug(undefined)).toBeNull();
  });

  it('refuses a slug too generic to license a citation claim', () => {
    expect(vocabularySourceSlug('https://example.invalid/wiki/Units')).toBeNull();
    expect(vocabularySourceSlug('https://example.invalid/wiki/QC')).toBeNull();
    expect(vocabularySourceSlug('https://example.invalid')).toBeNull();
  });

  it('matches a slug as a distinct token, never as part of a longer word', () => {
    // Word-boundary, not substring: "units" inside "subunits" is not a citation.
    expect(
      fieldsCitingVocabulary([fieldWithDescription('Number of repeating subunits.')], 'units'),
    ).toEqual([]);
    expect(
      fieldsCitingVocabulary([fieldWithDescription('Reported in units of eV.')], 'units'),
    ).toHaveLength(1);
    // The production shape: the slug cited mid-sentence, hyphen and all.
    expect(
      fieldsCitingVocabulary(
        [fieldWithDescription('See Controlled-Vocabulary wiki for the canonical class list.')],
        'Controlled-Vocabulary',
      ),
    ).toHaveLength(1);
    expect(fieldsCitingVocabulary([fieldWithDescription('anything')], null)).toEqual([]);
  });
});

// --- immutability of the fetched schema --------------------------------------

describe('SchemaBrowser — never mutates the schema it was given', () => {
  it('drives every subview, search, selection and disclosure over a DEEP-FROZEN response', async () => {
    // A structural clone so freezing cannot leak into any other test, then
    // frozen all the way down: any write attempt throws in strict mode (ES
    // modules are strict), so a mutation shows up as a failing test, not as a
    // silent edit to the canonical schema the whole surface reads from.
    const frozen = deepFreeze(JSON.parse(JSON.stringify(schemaBrowserFixture)));
    const before = JSON.stringify(frozen);
    stubSchema(frozen);
    render(<SchemaBrowser />);

    // Fields: selection at several depths, plus search and its empty state.
    fireEvent.click(rowButton(await findRow('record_id')));
    fireEvent.click(rowButton(row('sample')));
    fireEvent.click(rowButton(row('formula')));
    fireEvent.keyDown(rowButton(row('formula')), { key: 'ArrowUp' });
    fireEvent.change(screen.getByLabelText(/search fields/i), { target: { value: 'descriptor' } });
    fireEvent.change(screen.getByLabelText(/search fields/i), { target: { value: 'zzz-none' } });
    fireEvent.change(screen.getByLabelText(/search fields/i), { target: { value: '' } });

    // Conditional Rules: search, plus the raw-clause disclosure (which renders
    // the schema's own `allOf` entry, held by reference).
    await selectView('Conditional Rules');
    fireEvent.change(screen.getByLabelText(/search rules/i), { target: { value: 'sample' } });
    const card = document.querySelector('.schema-rule-card') as HTMLElement;
    fireEvent.click(within(card).getByText(/source rule \(raw json schema\)/i));
    fireEvent.change(screen.getByLabelText(/search rules/i), { target: { value: '' } });

    // Vocabulary: the file card, its search, and the derived citation link.
    await selectView('Vocabulary');
    fireEvent.change(screen.getByLabelText(/search vocabulary/i), { target: { value: 'edge' } });
    fireEvent.change(screen.getByLabelText(/search vocabulary/i), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'descriptors.outputs.descriptors.name' }));

    expect(
      within(detail()).getByText('descriptors.outputs.descriptors.name', {
        selector: '.schema-fielddetail-path',
      }),
    ).toBeInTheDocument();
    expect(Object.isFrozen(frozen.schema)).toBe(true);
    expect(JSON.stringify(frozen)).toBe(before);
  });
});

// --- loading / backend-down --------------------------------------------------

describe('SchemaBrowser — loading + backend-down', () => {
  it('shows a loading panel before the fetch resolves', () => {
    // fetch never resolves → the screen stays on the loading state (no act
    // warning from a resolution the test never awaits).
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    render(<SchemaBrowser />);
    expect(screen.getByText(/loading schema/i)).toBeInTheDocument();
  });

  it('shows the backend-down state without crashing', async () => {
    stubFetchDown();
    render(<SchemaBrowser />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/not running|unreachable/i);
  });
});

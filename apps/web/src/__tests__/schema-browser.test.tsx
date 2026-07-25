/**
 * P36.6 — the read-only Schema & Vocabulary browser (Governance & Safety).
 *
 * `SchemaBrowser` fetches `GET /api/schema` and renders EVERY field, type,
 * required/optional flag, allowed value, description, and relationship
 * verbatim from that response — it computes no verdict and invents nothing.
 * These tests pin:
 *   - top-level fields render with an honest required/optional badge, enum,
 *     and description, all read from the stubbed schema;
 *   - client-side search filters the field list;
 *   - a nested object field expands to reveal its own properties;
 *   - the schema's `allOf` if/then conditional renders as a readable sentence;
 *   - vocabulary terms render as a browsable list;
 *   - loading / backend-down states reuse the shared FetchStates components;
 *   - the search input and expandable rows are keyboard-reachable, and there
 *     is NO edit/propose/approve control anywhere.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import { SchemaBrowser } from '../components/SchemaBrowser';
import { stubFetchRoutes, stubFetchDown, schemaBrowserFixture } from '../test/apiFixtures';

const URL = 'GET /api/schema';

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * A top-level field's dotted `path` equals its bare `name` (e.g. "sample"),
 * so its name (`.schema-field-name`) and its path line (`.schema-field-path`)
 * are both the exact text "sample" — ambiguous for a plain `getByText`. Scope
 * to the name span specifically, matching how a user would identify the row.
 */
function fieldName(text: string): HTMLElement {
  return screen.getByText(text, { selector: '.schema-field-name' });
}
async function findFieldName(text: string): Promise<HTMLElement> {
  return screen.findByText(text, { selector: '.schema-field-name' });
}

/**
 * A native `<details>` keeps its (closed) children in the DOM — only their
 * visual rendering is suppressed — so scoping a badge lookup to the row's
 * `<li>` would also catch a nested child's badge once expanded. `.schema-
 * field-head` wraps ONLY a row's own name/type/badge (children are rendered
 * as siblings after it), so it is the correct, unambiguous scope.
 */
function badgeFor(name: HTMLElement): HTMLElement {
  const head = name.closest('.schema-field-head') as HTMLElement;
  return head.querySelector('.schema-field-badge') as HTMLElement;
}

// --- top-level fields: required/optional, enum, description -----------------

describe('SchemaBrowser — top-level fields', () => {
  it('renders required and optional fields with an honest text badge', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);

    expect(badgeFor(await findFieldName('record_id'))).toHaveTextContent('Required');
    expect(badgeFor(fieldName('sample'))).toHaveTextContent('Optional');
  });

  it('renders a field description read verbatim from the schema', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);
    expect(await screen.findByText('ULID identifier for the record.')).toBeInTheDocument();
  });

  it('renders the enum allowed values for an enum field', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);
    const recordType = (await findFieldName('record_type')).closest('li')!;
    expect(within(recordType).getByText('evidence')).toBeInTheDocument();
    expect(within(recordType).getByText('intent')).toBeInTheDocument();
    expect(within(recordType).getByText('synthesis')).toBeInTheDocument();
  });

  it('renders the schema title, version, and read-only source line', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);
    expect(
      await screen.findByText(/ISAAC AI-Ready Scientific Record v1\.05 \(fixture\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/v1\.05/)).toBeInTheDocument();
    expect(screen.getByText(/vendored official schema \(read-only reference\)/)).toBeInTheDocument();
  });

  it('never renders any propose/review/approve/edit control', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    const { container } = render(<SchemaBrowser />);
    await findFieldName('record_id');
    expect(screen.queryByRole('button', { name: /propose|approve|edit|delete|save/i })).toBeNull();
    expect(container.querySelector('input[type="text"], textarea')).toBeNull();
  });
});

// --- search --------------------------------------------------------------

describe('SchemaBrowser — search', () => {
  it('filters the field list by name/path/description', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);
    await findFieldName('record_id');
    expect(fieldName('sample')).toBeInTheDocument();
    expect(fieldName('tags')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/search fields/i), { target: { value: 'ULID' } });

    expect(fieldName('record_id')).toBeInTheDocument();
    expect(screen.queryByText('sample', { selector: '.schema-field-name' })).toBeNull();
    expect(screen.queryByText('tags', { selector: '.schema-field-name' })).toBeNull();
  });

  it('shows an honest empty state for a query with no matches', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);
    await findFieldName('record_id');
    fireEvent.change(screen.getByLabelText(/search fields/i), {
      target: { value: 'no-such-field-anywhere' },
    });
    expect(await screen.findByText(/no fields match/i)).toBeInTheDocument();
  });

  it('the search input is a real, keyboard-reachable <input>', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);
    await findFieldName('record_id');
    const input = screen.getByLabelText(/search fields/i);
    expect(input.tagName).toBe('INPUT');
    expect(input).not.toHaveAttribute('tabindex', '-1');
  });
});

// --- nested expand ---------------------------------------------------------

describe('SchemaBrowser — nested object expand', () => {
  it('a nested object field expands via its native disclosure to reveal its properties', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);
    await findFieldName('sample');

    // A closed native <details> keeps its children in the DOM but not
    // visible — `material` is nested under the (closed) `sample` disclosure.
    expect(screen.getByText('material')).not.toBeVisible();

    const summary = fieldName('sample').closest('summary')!;
    expect(summary).toBeInTheDocument();
    fireEvent.click(summary);

    expect(await screen.findByText('material')).toBeVisible();
    // The nested field's OWN required flag (from sample's required array).
    expect(badgeFor(screen.getByText('sample_form'))).toHaveTextContent('Required');
    expect(badgeFor(screen.getByText('material'))).toHaveTextContent('Optional');
  });

  it('expanding a second level reveals a doubly-nested field', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);
    await findFieldName('sample');
    fireEvent.click(fieldName('sample').closest('summary')!);
    await screen.findByText('material');
    fireEvent.click(screen.getByText('material').closest('summary')!);
    expect(await screen.findByText('formula')).toBeInTheDocument();
    expect(screen.getByText('Chemical formula, e.g. CuO2.')).toBeInTheDocument();
  });
});

// --- relationships (allOf if/then) ------------------------------------------

describe('SchemaBrowser — relationships', () => {
  it('renders the allOf conditional as a readable relationship sentence', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);
    const text = await screen.findByText(
      /If record_type = "evidence", then descriptors is required\./,
    );
    expect(text).toBeInTheDocument();
  });
});

// --- vocabulary --------------------------------------------------------------

describe('SchemaBrowser — vocabulary', () => {
  it('renders vocabulary terms as a browsable list', async () => {
    stubFetchRoutes({ [URL]: { body: schemaBrowserFixture } });
    render(<SchemaBrowser />);
    expect(await screen.findByText('descriptor_class')).toBeInTheDocument();
    expect(screen.getByText('white_line_energy')).toBeInTheDocument();
    expect(screen.getByText('edge_shift')).toBeInTheDocument();
    expect(screen.getByText('H2')).toBeInTheDocument();
    expect(screen.getByText('CO')).toBeInTheDocument();
    expect(screen.getByText(/fixture vocabulary note/i)).toBeInTheDocument();
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

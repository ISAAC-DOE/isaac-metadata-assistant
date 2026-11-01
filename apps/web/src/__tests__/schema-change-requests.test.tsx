import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { ROUTES } from '../lib/routes';
import { RecordValidator } from '../components/RecordValidator';
import { IngestionProposalsPanel } from '../components/IngestionProposalsPanel';
import { RunInheritedPanel } from '../components/RunInheritedPanel';
import { ProposeTermLink } from '../components/ProposeTermLink';
import {
  PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
  PROPOSAL_TARGET_PATHS,
  stubFetchRoutes,
  type RouteEntry,
} from '../test/apiFixtures';
import {
  canProposeTerm,
  categoryKeyOf,
  proposeTermHref,
  type ApiSchemaChangeRequest,
  type ApiSchemaProposal,
  type ApiSchemaVocabulary,
} from '../lib/schemaProposals';
import type { ApiProposal, ApiProposalsResponse, ApiRunView } from '../lib/types';

/**
 * SCHEMA CHANGE REQUESTS (a new FIELD, which the upstream portal has no proposal type for)
 * and PROPOSE FROM WHERE THE GAP IS FOUND. Behaviour, not copy: what the form sends, that a
 * new field is never offered a portal payload, what the export hands out, and on which
 * surfaces a "Propose this term" link appears — with a negative control for each.
 */

const envelope = {
  persistence: { class: 'workspace_files', survives_restart: 'not_guaranteed', message: 'SERVER-SAID: temporary.' },
  review_note: 'SERVER-SAID: review happens in the portal.',
  attribution_note: 'Who is calling is not verified.',
};

const NOT_PORTAL = 'SERVER-SAID: the portal has no proposal type for a new field.';

const portalContext = {
  id: 'Context',
  label: 'Context',
  block: 'context',
  categories: [
    { key: 'context.environment', label: 'environment', description: '', terms: ['operando', 'in_situ'], kind: 'terms' as const },
  ],
};
const portalSystem = {
  id: 'System',
  label: 'System',
  block: 'system',
  categories: [
    { key: 'system.technique', label: 'technique', description: '', terms: ['XAS', 'XES'], kind: 'terms' as const },
  ],
};

const baseVocabulary: ApiSchemaVocabulary = {
  schema_version: '1.05',
  default_source: 'portal',
  term_rule: 'RULE: one word.',
  // The server's own patterns (`TERM_SHAPE_FOR_CLIENTS`), as served.
  term_shape: { term: '^[A-Za-z][A-Za-z0-9_./-]*$', snake_case: '^[a-z][a-z0-9_]*$', path_like: '(\\.\\.|//|\\./|/\\.)' },
  review_note: 'SERVER-SAID: review happens in the portal.',
  proposal_types: ['add_term', 'add_category', 'schema_change'],
  portal_proposal_types: ['add_term', 'add_category'],
  limits: {
    section_max: 100,
    category_max: 255,
    term_max: 80,
    description_min: 20,
    description_max: 2000,
    problem_max: 2000,
    examples_max: 2000,
    affected_records_estimate_max: 200,
    flip_list_max: 2000,
    field_name_max: 80,
    unit_max: 40,
    example_max: 500,
    migration_max: 2000,
    max_pending: 50,
    max_withdrawn_kept: 500,
    max_body_bytes: 131072,
    page_max: 100,
  },
  sources: {
    portal: {
      id: 'portal',
      label: 'Portal vocabulary (snapshot a1cb1c8)',
      detail: 'DETAIL-PORTAL',
      sha256: 'b'.repeat(64),
      section_count: 2,
      category_count: 2,
      term_list_count: 2,
      term_count: 4,
      sections: [portalContext, portalSystem],
    },
    schema: {
      id: 'schema',
      label: 'Schema enums (vendored v1.05)',
      detail: 'DETAIL-SCHEMA',
      sha256: 'a'.repeat(64),
      section_count: 1,
      category_count: 1,
      term_list_count: 1,
      term_count: 2,
      sections: [
        {
          id: 'Context',
          label: 'Context',
          block: 'context',
          categories: [{ key: 'context.electrochemistry.reference_electrode.offset_basis', label: 'offset_basis', description: '', terms: ['measured'] }],
        },
      ],
    },
  },
  proposal_sections: [
    { id: 'Context', label: 'Context', block: 'context', term_lists: ['context.environment'] },
    { id: 'System', label: 'System', block: 'system', term_lists: ['system.technique'] },
  ],
  schema_change: {
    kinds: ['add_field'],
    value_types: ['string', 'number', 'integer', 'boolean', 'object', 'array'],
    scopes: ['core', 'domain_profile'],
    not_a_portal_proposal: NOT_PORTAL,
    upstream: {
      repository: 'https://github.com/ISAAC-DOE/isaac-ai-ready-record',
      process: 'governance/README.md',
      drafts: 'governance/changes/PROPOSED.md',
    },
    object_paths: [
      { path: 'context', section: 'Context', open: false, fields: ['environment', 'electrochemistry'] },
      { path: 'context.electrochemistry', section: 'Context', open: false, fields: ['pH', 'cell_type'] },
      { path: 'system', section: 'System', open: false, fields: ['technique'] },
    ],
  },
};

function fieldProposal(over: Partial<ApiSchemaProposal> = {}): ApiSchemaProposal {
  return {
    id: '01M61FIELD3DFS5VX1C7X1RZJS5',
    proposal_type: 'schema_change',
    section: 'Context',
    category: 'context.electrochemistry.c_rate',
    term: null,
    description: 'The C-rate of a battery cycling test.',
    gate0: { problem: 'Two of three battery sets wrote an areal current instead.' },
    status: 'pending',
    proposed_by: null,
    attribution: 'unverified',
    proposed_at: '2026-10-29T10:00:00Z',
    withdrawn_at: null,
    schema_version: '1.05',
    change: {
      kind: 'add_field',
      parent_path: 'context.electrochemistry',
      field_name: 'c_rate',
      path: 'context.electrochemistry.c_rate',
      value_type: 'number',
      unit: '1/h',
      required: false,
      example: '0.5',
      scope: null,
      migration: null,
      parent_open_today: false,
    },
    sent_by_isaac: false,
    ...over,
  };
}

function list(proposals: ApiSchemaProposal[]): RouteEntry {
  return {
    body: {
      ...envelope,
      proposals,
      total: proposals.length,
      limit: 25,
      offset: 0,
      next_offset: null,
      statuses: ['pending', 'withdrawn'],
      capacity: { pending: proposals.length, max_pending: 50, max_withdrawn_kept: 500, scope: 'SERVER-SAID: shared.' },
    },
  };
}

const MARKDOWN = '# Proposed schema change: add `context.electrochemistry.c_rate`\n\nSERVER-SAID: markdown body.\n';
function changeRequest(p: ApiSchemaProposal): ApiSchemaChangeRequest {
  return {
    ...envelope,
    proposal_id: p.id,
    status: p.status,
    format: 'isaac.schema-change-request',
    format_version: '1',
    is_portal_payload: false,
    markdown: MARKDOWN,
    document: { format: 'isaac.schema-change-request', change: { path: 'context.electrochemistry.c_rate' } },
    filename_stem: `isaac-schema-change-${p.id}`,
    upstream: baseVocabulary.schema_change!.upstream,
    sent_by_isaac: false,
    notes: ['SERVER-SAID: ISAAC has not sent this anywhere.'],
  };
}

function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

const ROUTE = ROUTES.schemaProposals;
const proposePanel = () => screen.getByRole('tabpanel', { name: 'Propose a Change' });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// --- the third proposal type --------------------------------------------------------

describe('a new field (schema change request)', () => {
  it('is offered only when the server describes it', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
      'GET /api/schema-proposals': list([]),
    });
    const first = renderAt(`${ROUTE}?tab=propose`);
    await screen.findByRole('radio', { name: /Add a new field to the ISAAC schema/ });
    first.unmount();
    // Negative control: a server that predates the type is offered the portal's two only.
    const { schema_change: _drop, ...older } = baseVocabulary;
    void _drop;
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: older },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByRole('radio', { name: 'Add a term to an existing list' });
    expect(screen.queryByRole('radio', { name: /Add a new field/ })).toBeNull();
  });

  it('says the portal has no such type, lists only the real blocks of the section, and sends the change', async () => {
    let sent: Record<string, unknown> | null = null;
    const saved = fieldProposal();
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
      'GET /api/schema-proposals': list([]),
      'POST /api/schema-proposals': (init) => {
        sent = JSON.parse(String(init?.body));
        return { status: 201, body: { ...envelope, proposal: saved, ignored_fields: [] } };
      },
      [`GET /api/schema-proposals/${saved.id}/change-request`]: { body: changeRequest(saved) },
    });
    renderAt(`${ROUTE}?tab=propose`);
    fireEvent.click(await screen.findByRole('radio', { name: /Add a new field to the ISAAC schema/ }));
    const panel = within(proposePanel());
    expect(panel.getByText(NOT_PORTAL)).toBeInTheDocument();
    fireEvent.change(panel.getByLabelText('Section'), { target: { value: 'Context' } });
    const where = panel.getByLabelText('Where in the schema');
    expect(within(where).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Choose a block…',
      'context',
      'context.electrochemistry',
    ]);
    fireEvent.change(where, { target: { value: '@context.electrochemistry' } });
    expect(panel.getByText(/refuses any key the schema does not declare/)).toBeInTheDocument();
    fireEvent.change(panel.getByLabelText('New field name'), { target: { value: 'c_rate' } });
    fireEvent.change(panel.getByLabelText('Kind of value'), { target: { value: 'number' } });
    fireEvent.change(panel.getByLabelText('Unit (optional)'), { target: { value: '1/h' } });
    fireEvent.click(panel.getByRole('radio', { name: 'No, optional' }));
    fireEvent.change(panel.getByLabelText('Definition (required)'), {
      target: { value: 'The C-rate of a battery cycling test.' },
    });
    fireEvent.change(panel.getByLabelText(/The problem, with counts and examples/), {
      target: { value: 'Two of three battery sets wrote an areal current instead.' },
    });
    fireEvent.click(panel.getByRole('button', { name: 'Save Proposal' }));

    const status = await screen.findByText(/download the change-request document/);
    const notice = within(status.closest('[role="status"]') as HTMLElement);
    expect(notice.getByRole('button', { name: 'Copy Change Request' })).toBeInTheDocument();
    // NEVER a portal payload for a new field.
    expect(notice.queryByRole('button', { name: 'Copy Portal Payload' })).toBeNull();
    expect(sent).toEqual({
      proposal_type: 'schema_change',
      section: 'Context',
      description: 'The C-rate of a battery cycling test.',
      gate0: { problem: 'Two of three battery sets wrote an areal current instead.' },
      change: {
        kind: 'add_field',
        parent_path: 'context.electrochemistry',
        field_name: 'c_rate',
        value_type: 'number',
        required: false,
        unit: '1/h',
      },
    });
    expect(JSON.stringify(sent)).not.toMatch(/"category"|"term"|proposed_by/);
  });

  it('defaults nothing: an unchosen kind or "required?" is not sent, and the server\'s sentence lands beside its field', async () => {
    let sent: Record<string, unknown> | null = null;
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
      'GET /api/schema-proposals': list([]),
      'POST /api/schema-proposals': (init) => {
        sent = JSON.parse(String(init?.body));
        return {
          status: 422,
          body: {
            error: 'required_must_be_stated',
            message: 'The proposal needs a few changes before it can be saved.',
            errors: [
              { field: 'change.required', code: 'required_must_be_stated', message: 'SERVER-SAID: say whether it is required.' },
              { field: 'change.value_type', code: 'invalid_value_type', message: 'SERVER-SAID: choose the kind of value.' },
            ],
          },
        };
      },
    });
    renderAt(`${ROUTE}?tab=propose`);
    fireEvent.click(await screen.findByRole('radio', { name: /Add a new field to the ISAAC schema/ }));
    const panel = within(proposePanel());
    fireEvent.change(panel.getByLabelText('Section'), { target: { value: 'Context' } });
    fireEvent.change(panel.getByLabelText('Where in the schema'), { target: { value: '@context' } });
    fireEvent.change(panel.getByLabelText('New field name'), { target: { value: 'buffer_name' } });
    fireEvent.click(panel.getByRole('button', { name: 'Save Proposal' }));
    await screen.findByText('SERVER-SAID: say whether it is required.');
    expect(screen.getByText('SERVER-SAID: choose the kind of value.')).toBeInTheDocument();
    const change = (sent as unknown as { change: Record<string, unknown> }).change;
    expect(change).toEqual({ kind: 'add_field', parent_path: 'context', field_name: 'buffer_name' });
    // What was typed survives the refusal.
    expect(panel.getByLabelText('New field name')).toHaveValue('buffer_name');
  });

  it('is listed with its own facts and exports the server\'s Markdown exactly, never a portal payload', async () => {
    const p = fieldProposal();
    const blobs: Blob[] = [];
    const createObjectURL = vi.fn((b: Blob) => {
      blobs.push(b);
      return 'blob:x';
    });
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const clicked: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this.download);
    });
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
      'GET /api/schema-proposals': list([p]),
      [`GET /api/schema-proposals/${p.id}/change-request`]: { body: changeRequest(p) },
    });
    renderAt(`${ROUTE}?tab=proposals`);
    const heading = await screen.findByRole('heading', { name: 'Add the field context.electrochemistry.c_rate to the schema' });
    const row = within(heading.closest('li') as HTMLElement);
    expect(row.getByText(/schema change request \(not a portal proposal\)/)).toBeInTheDocument();
    expect(row.getByText('1/h', { exact: false })).toBeInTheDocument();
    expect(row.queryByRole('button', { name: 'Copy Portal Payload' })).toBeNull();
    fireEvent.click(row.getByRole('button', { name: 'Download Markdown' }));
    await row.findByText(/Downloaded the change request as Markdown\. ISAAC has not sent it anywhere\./);
    expect(clicked).toEqual([`isaac-schema-change-${p.id}.md`]);
    expect(blobs).toHaveLength(1);
    expect(await readBlob(blobs[0])).toBe(MARKDOWN);
    expect(row.getByText('SERVER-SAID: ISAAC has not sent this anywhere.')).toBeInTheDocument();
  });
});

// --- propose from where the gap is found -------------------------------------------

describe('opening the form from a link', () => {
  it('fills the list, the term and the source surface, and looks the section up itself', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(proposeTermHref(ROUTE, { category: 'system.technique', term: 'XMCD', from: 'validator' }));
    const panel = within(await screen.findByRole('tabpanel', { name: 'Propose a Change' }));
    await waitFor(() => expect(panel.getByLabelText('Category')).toHaveValue('system.technique'));
    expect(panel.getByLabelText('Section')).toHaveValue('System');
    expect(panel.getByLabelText('New term')).toHaveValue('XMCD');
    expect(panel.getByText(/Opened from the Validator/)).toBeInTheDocument();
    expect(panel.getByLabelText('Examples')).toHaveValue(
      'Found in the Validator on the ISAAC Metadata Assistant, as "XMCD".',
    );
  });

  it('fills in nothing for a list the portal does not have, and says so', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(
      proposeTermHref(ROUTE, {
        category: 'context.electrochemistry.reference_electrode.offset_basis',
        term: 'guessed',
        from: 'validator',
      }),
    );
    const panel = within(await screen.findByRole('tabpanel', { name: 'Propose a Change' }));
    await panel.findByText(/is not a term list in the portal vocabulary snapshot, so nothing was filled in/);
    expect(panel.getByLabelText('New term')).toHaveValue('');
    expect(panel.queryByText(/Opened from/)).toBeNull();
  });

  it('names no surface for an unknown `from`', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=propose&category=system.technique&term=XMCD&from=somewhere`);
    const panel = within(await screen.findByRole('tabpanel', { name: 'Propose a Change' }));
    await waitFor(() => expect(panel.getByLabelText('New term')).toHaveValue('XMCD'));
    expect(panel.queryByText(/Opened from/)).toBeNull();
    expect(panel.getByLabelText('Examples')).toHaveValue('');
  });
});

describe('when a "Propose this term" link fits', () => {
  it('only for a portal term list, a value not on it, and not a spelling of one that is', () => {
    expect(canProposeTerm(baseVocabulary, 'system.technique', 'XMCD')).toBe(true);
    expect(canProposeTerm(baseVocabulary, 'system.technique', 'XAS')).toBe(false); // already allowed
    expect(canProposeTerm(baseVocabulary, 'context.environment', 'in situ')).toBe(false); // in_situ as written
    expect(canProposeTerm(baseVocabulary, 'context.environment', 'In-Situ')).toBe(false);
    expect(canProposeTerm(baseVocabulary, 'context.electrochemistry.reference_electrode.offset_basis', 'x')).toBe(false); // schema-only
    expect(canProposeTerm(baseVocabulary, 'sample.material.name', 'anything')).toBe(false); // free text
    expect(canProposeTerm(baseVocabulary, 'system.technique', '')).toBe(false);
    expect(canProposeTerm(baseVocabulary, 'system.technique', 3)).toBe(false);
    // A phrase the server would refuse as a term (`invalid_term`) gets no link either …
    expect(canProposeTerm(baseVocabulary, 'system.technique', 'cathodic corrosion')).toBe(false);
    expect(canProposeTerm(baseVocabulary, 'system.technique', 'a..b')).toBe(false);
    // … nor a non-snake term for a list whose every term is snake_case (`in_situ`, `operando`).
    expect(canProposeTerm(baseVocabulary, 'context.environment', 'Cryogenic')).toBe(false);
    expect(canProposeTerm(baseVocabulary, 'context.environment', 'cryogenic')).toBe(true);
    // Without the served rules (an older server), nothing is offered.
    const { term_shape: _shape, ...older } = baseVocabulary;
    void _shape;
    expect(canProposeTerm(older, 'system.technique', 'XMCD')).toBe(false);
    expect(categoryKeyOf('measurement.series.0.channels.2.name')).toBe('measurement.series.channels.name');
    expect(categoryKeyOf('measurement.series[].channels[].name')).toBe('measurement.series.channels.name');
  });
});

function renderValidator() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <RecordValidator />
    </MemoryRouter>,
  );
}

const VALIDATE_FAIL = {
  ok: false,
  schema_ok: false,
  summary: 'FAIL',
  schema_version: '1.05',
  errors: [
    { path: 'system.technique', message: "'XMCD' is not one of [...]" },
    { path: 'context.environment', message: "'ambient' is not one of [...]" },
  ],
  exactness_errors: [],
  advisory: true,
  gating: false,
  warnings: [],
};

describe('the Validator', () => {
  it('offers a link for a value outside a portal list, read from the record (not the message)', async () => {
    stubFetchRoutes({
      'POST /api/validate/record': { body: VALIDATE_FAIL },
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
    });
    renderValidator();
    // The message says 'XMCD' but the RECORD holds 'telepathy': the record is what is read.
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: JSON.stringify({ system: { technique: 'telepathy' }, context: { environment: 'in situ' } }) },
    });
    fireEvent.click(screen.getByRole('button', { name: /Validate/ }));
    const link = await screen.findByRole('link', { name: 'Propose this term: telepathy, for system.technique (opens in a new tab)' });
    const href = new URL(link.getAttribute('href') ?? '', 'http://x');
    expect(href.pathname).toBe(ROUTES.schemaProposals);
    expect(Object.fromEntries(href.searchParams)).toEqual({
      tab: 'propose',
      category: 'system.technique',
      term: 'telepathy',
      from: 'validator',
    });
    // `in situ` is in_situ as written: no link for it.
    expect(screen.getAllByRole('link', { name: /^Propose / })).toHaveLength(1);
  });

  it('offers nothing when the vocabulary cannot be read', async () => {
    stubFetchRoutes({ 'POST /api/validate/record': { body: VALIDATE_FAIL } });
    renderValidator();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: JSON.stringify({ system: { technique: 'telepathy' } }) },
    });
    fireEvent.click(screen.getByRole('button', { name: /Validate/ }));
    await screen.findByText(/Checked against official ISAAC schema/);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole('link', { name: /^Propose / })).toBeNull();
  });
});

// --- a proposed value from a file --------------------------------------------------

const EXP = 'demo';
function ingestion(over: Partial<ApiProposal>): ApiProposal {
  return {
    proposal_id: 'P1',
    experiment_id: EXP,
    note_id: 'N1',
    run_id: '01RUNAAAAAAAAAAAAAAAAAAAA0',
    target_field_path: 'system.technique',
    proposed_value: 'XMCD',
    rule: 'as written',
    source: 'transcript',
    proposed_utc: '2026-09-01T10:00:00Z',
    base_rev: 3,
    target_digest: 'd0',
    start_char: null,
    end_char: null,
    client_request_key: null,
    state: 'open',
    subject: null,
    trust_basis: 'unattributed',
    accepted_value: null,
    accepted_from: null,
    applied_via: null,
    applied_run_id: null,
    applied_rev: null,
    applied_target_digest: null,
    history: [],
    status: 'ingestion_proposal',
    verified: false,
    is_evidence: false,
    is_field_value: false,
    applied: false,
    current_target_digest: 'd0',
    target_stale: false,
    still_current: null,
    excerpt: null,
    attributed: false,
    accepted_by: null,
    ...over,
  } as ApiProposal;
}

function page(proposals: ApiProposal[]): ApiProposalsResponse {
  return {
    proposals,
    total: proposals.length,
    returned: proposals.length,
    by_state: { open: proposals.length, accepted: 0, rejected: 0, superseded: 0, withdrawn: 0 },
    has_more: false,
    next_cursor: null,
    order: 'oldest_first',
    window_default: 50,
    window_max: 200,
    max_per_record: 1000,
    unreadable_entries: 0,
    target_field_paths: PROPOSAL_TARGET_PATHS,
    record_scoped_target_field_paths: PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
    states: ['open', 'accepted', 'rejected', 'superseded', 'withdrawn'],
    review_actions: ['accept', 'reject', 'supersede', 'withdraw'],
    accepted_from_values: ['candidate', 'edited'],
    experiment_version: '1.7',
  };
}

describe('a proposed value from a file, outside the field\'s list', () => {
  function renderPanel() {
    return render(
      <MemoryRouter initialEntries={['/']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <IngestionProposalsPanel experimentId={EXP} activity={null} acceptance={{ available: true, reason: null }} />
      </MemoryRouter>,
    );
  }

  it('links to propose it when the portal list lacks it', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP}/proposals`]: {
        body: page([ingestion({ target_field_path: 'context.environment', proposed_value: 'cryogenic' })]),
      },
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
    });
    renderPanel();
    await screen.findByText(/is not one of the values the official schema allows/);
    const link = await screen.findByRole('link', { name: 'Propose this term: cryogenic, for context.environment (opens in a new tab)' });
    expect(link.getAttribute('href')).toContain('from=ingestion_proposal');
  });

  it('does not link a spelling of an allowed term (it is a correction, not a missing term)', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP}/proposals`]: {
        body: page([ingestion({ target_field_path: 'context.environment', proposed_value: 'in situ' })]),
      },
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
    });
    renderPanel();
    await screen.findByText(/is not one of the values the official schema allows/);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole('link', { name: /^Propose / })).toBeNull();
  });
});

// --- the component's own guard ------------------------------------------------------

describe('ProposeTermLink', () => {
  function renderLink(fieldPath: string, term: unknown) {
    return render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ProposeTermLink fieldPath={fieldPath} term={term} from="validator" vocabulary={baseVocabulary} />
      </MemoryRouter>,
    );
  }

  it('opens in a new tab, so the screen it sits on keeps its pasted record or half-typed override', () => {
    renderLink('system.technique', 'XMCD');
    const link = screen.getByRole('link', { name: /opens in a new tab/ });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toContain('noopener');
    expect(link).toHaveAccessibleName('Propose this term: XMCD, for system.technique (opens in a new tab)');
  });

  it('renders for a portal list value it lacks, and nothing for any other field or value', () => {
    const shown = renderLink('system.technique', 'XMCD');
    expect(screen.getByRole('link', { name: 'Propose this term: XMCD, for system.technique (opens in a new tab)' })).toBeInTheDocument();
    shown.unmount();
    for (const [path, term] of [
      ['system.technique', 'XAS'],
      ['context.electrochemistry.reference_electrode.offset_basis', 'x'],
      ['sample.material.name', 'anything'],
      ['system.technique', ''],
      ['system.technique', 7],
    ] as const) {
      const r = renderLink(path, term);
      expect(screen.queryByRole('link')).toBeNull();
      r.unmount();
    }
  });
});

// --- a run's own stored value, outside the list --------------------------------------

describe('a run override holding a value outside the list', () => {
  const EXP2 = 'demo';
  const RUN = 'RUNAAA';
  const TECHNIQUE = 'field:system.technique';
  const SCHEMA = {
    schema_version: '1.05',
    schema: { properties: { system: { properties: { technique: { type: 'string', enum: ['XAS', 'XES'] } } } } },
  };
  const env = (value: unknown) => ({ value, status: 'verified', evidence: [] });
  function run(stored: string): ApiRunView {
    return {
      id: RUN,
      experiment_id: EXP2,
      label: 'Run 1',
      ordinal: 1,
      created_utc: '2099-04-02T09:05:00Z',
      updated_utc: '2099-04-02T09:05:00Z',
      rev: 3,
      version: 'ra.3',
      record_id: null,
      fields: {},
      inherited: {
        [TECHNIQUE]: {
          state: 'overridden',
          payload: env(stored),
          inherited_payload: env('XAS'),
          displaced_payload: env('XAS'),
          overridable: true,
        },
      },
    } as unknown as ApiRunView;
  }
  const rowFor = (address: string) => document.querySelector(`[data-address="${address}"]`) as HTMLElement;

  async function open(stored: string) {
    stubFetchRoutes({
      'GET /api/schema': { body: SCHEMA },
      'GET /api/schema-proposals/vocabulary': { body: baseVocabulary },
    } as never);
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <RunInheritedPanel experimentId={EXP2} run={run(stored)} onRun={vi.fn()} />
      </MemoryRouter>,
    );
    await act(async () => {
      fireEvent.click(within(rowFor(TECHNIQUE)).getByRole('button', { name: /Change this run's value/ }));
    });
    await within(rowFor(TECHNIQUE)).findByRole('combobox');
  }

  it('links to propose it when the portal list lacks it', async () => {
    await open('XMCD');
    const link = await within(rowFor(TECHNIQUE)).findByRole('link', {
      name: 'Propose this term: XMCD, for system.technique (opens in a new tab)',
    });
    expect(link.getAttribute('href')).toContain('from=run_override');
  });

  it('does not link a spelling of an allowed term (the server would refuse it as a duplicate)', async () => {
    await open('x-a-s');
    await new Promise((r) => setTimeout(r, 20));
    expect(within(rowFor(TECHNIQUE)).queryByRole('link', { name: /^Propose / })).toBeNull();
  });
});

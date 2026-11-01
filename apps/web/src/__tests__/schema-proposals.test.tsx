import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { AppRoutes } from '../App';
import { LABELS, formatWhen } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { composeDocumentTitle } from '../lib/documentTitle';
import { stubFetchRoutes, type RouteEntry } from '../test/apiFixtures';
import type {
  ApiSchemaPortalPayload,
  ApiSchemaProposal,
  ApiSchemaVocabulary,
} from '../lib/schemaProposals';

/**
 * Schema Proposals screen. These tests pin BEHAVIOUR: what is rendered from the
 * server's vocabulary, what is sent on submit, where a refusal lands, which proposals can
 * be withdrawn, and what the copy and download controls hand out. They do not pin
 * sentences, except the few that are the honesty claim itself (not sent, not approved,
 * temporary, author not recorded), which are asserted by role and by the presence of the
 * server's own text.
 */

const CAPACITY = {
  pending: 2,
  max_pending: 50,
  max_withdrawn_kept: 500,
  scope: 'SERVER-SAID: shared by everyone using this server.',
};

const PERSISTENCE_TEXT = 'SERVER-SAID: proposals on this server are temporary.';
const REVIEW_TEXT = 'SERVER-SAID: review happens in the ISAAC portal.';

const envelope = {
  persistence: { class: 'workspace_files', survives_restart: 'not_guaranteed', message: PERSISTENCE_TEXT },
  review_note: REVIEW_TEXT,
  attribution_note: 'Who is calling is not verified.',
};

const recordInfo = {
  id: 'Record Info',
  label: 'Record Info (root fields)',
  block: null,
  categories: [{ key: 'record_type', label: 'record_type', description: 'Fundamental nature of the record.', terms: ['evidence', 'intent'], kind: 'terms' as const }],
};
const systemSection = {
  id: 'System',
  label: 'System',
  block: 'system',
  categories: [
    { key: 'system.technique', label: 'technique', description: 'The measurement technique.', terms: ['XAS', 'XPS', 'SAXS'], kind: 'terms' as const },
    { key: 'system.domain', label: 'domain', description: '', terms: ['experimental'], kind: 'terms' as const },
  ],
};
const sampleSection = { id: 'Sample', label: 'Sample', block: 'sample', categories: [] };

const vocabulary: ApiSchemaVocabulary = {
  schema_version: '1.05',
  default_source: 'portal',
  term_rule: 'RULE: one word, no spaces.',
  review_note: REVIEW_TEXT,
  proposal_types: ['add_term', 'add_category'],
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
    max_pending: 50,
    max_withdrawn_kept: 500,
    max_body_bytes: 131072,
    page_max: 100,
  },
  sources: {
    portal: {
      id: 'portal',
      label: 'Portal vocabulary (snapshot a1cb1c8)',
      detail: 'DETAIL-PORTAL: a copy of the portal list at one commit.',
      snapshot_commit: 'a1cb1c8',
      sha256: 'b'.repeat(64),
      section_count: 3,
      category_count: 3,
      term_list_count: 3,
      term_count: 6,
      sections: [recordInfo, systemSection, sampleSection],
    },
    schema: {
      id: 'schema',
      label: 'Schema enums (vendored v1.05)',
      detail: 'DETAIL-SCHEMA: the fixed lists in the record schema.',
      sha256: 'a'.repeat(64),
      section_count: 2,
      category_count: 1,
      term_list_count: 1,
      term_count: 2,
      sections: [
        { id: 'Record Info', label: 'Record Info (root fields)', block: null, categories: [] },
        {
          id: 'Context',
          label: 'Context',
          block: 'context',
          categories: [{ key: 'context.environment', label: 'environment', description: '', terms: ['ambient', 'vacuum'] }],
        },
      ],
    },
  },
  proposal_sections: [
    { id: 'Record Info', label: 'Record Info (root fields)', block: null, term_lists: ['record_type'] },
    { id: 'System', label: 'System', block: 'system', term_lists: ['system.technique', 'system.domain'] },
    { id: 'Sample', label: 'Sample', block: 'sample', term_lists: [] },
    { id: 'Context', label: 'Context', block: 'context', term_lists: [] },
  ],
};

function proposal(over: Partial<ApiSchemaProposal> = {}): ApiSchemaProposal {
  return {
    id: '01M61TASK3DFS5VX1C7X1RZJS5',
    proposal_type: 'add_term',
    section: 'System',
    category: 'system.technique',
    term: 'XMCD',
    description: 'X-ray magnetic circular dichroism, measured at SSRL.',
    gate0: null,
    status: 'pending',
    proposed_by: null,
    attribution: 'unverified',
    proposed_at: '2026-10-28T17:53:37Z',
    withdrawn_at: null,
    schema_version: '1.05',
    sent_by_isaac: false,
    ...over,
  };
}

function payloadFor(p: ApiSchemaProposal): ApiSchemaPortalPayload {
  return {
    ...envelope,
    proposal_id: p.id,
    status: p.status,
    portal: { method: 'POST', path: '/portal/api/vocabulary/proposals', rest_supported: true },
    body: {
      proposal_type: p.proposal_type,
      section: p.section,
      category: p.category,
      term: p.term,
      description: p.description,
    },
    sent_by_isaac: false,
    notes: [],
  };
}

function list(proposals: ApiSchemaProposal[]): RouteEntry {
  return {
    body: { ...envelope, proposals, total: proposals.length, limit: 25, offset: 0, next_offset: null, statuses: ['pending', 'withdrawn'], capacity: CAPACITY },
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

const ROUTE = ROUTES.schemaProposals;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** The Section select INSIDE the Propose panel; Browse has one of the same name. */
function sectionSelect(): HTMLElement {
  return within(screen.getByRole('tabpanel', { name: 'Propose a Change' })).getByLabelText('Section');
}

function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

function fillPropose() {
  fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'system.technique' } });
  fireEvent.change(screen.getByLabelText('New term'), { target: { value: 'xmcd_scan' } });
  fireEvent.change(screen.getByLabelText('Description (required)'), {
    target: { value: 'Magnetic dichroism measured with circular polarisation.' },
  });
}

describe('the destination', () => {
  it('is a primary navigation item, titled by the one authored label', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(ROUTE);
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    const link = within(nav).getByRole('link', { name: LABELS.navSchemaProposals });
    expect(link).toHaveAttribute('href', ROUTES.schemaProposals);
    expect(link).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(LABELS.navSchemaProposals);
    await waitFor(() => {
      expect(document.title).toBe(composeDocumentTitle([LABELS.navSchemaProposals]));
    });
  });

  it('says ISAAC drafts and the standard\'s owners review, and offers no approve, apply or send control', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal()]),
    });
    renderAt(ROUTE);
    await screen.findByRole('combobox', { name: 'Section' });
    expect(screen.getByText(/it does not approve, apply or send anything/)).toBeInTheDocument();
    for (const tab of ['Browse the Vocabulary', 'Propose a Change', 'Proposals']) {
      fireEvent.click(screen.getByRole('tab', { name: tab }));
      const controls = screen
        .getAllByRole('button')
        .map((b) => b.textContent ?? '')
        .concat(screen.getAllByRole('link').map((a) => a.textContent ?? ''));
      expect(controls.filter((c) => /approve|apply|accept|reject|send/i.test(c))).toEqual([]);
    }
  });
});

describe('Browse', () => {
  it('renders the sections, the categories of a section and the allowed terms of a category', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(ROUTE);
    const select = await screen.findByRole('combobox', { name: 'Section' });
    const options = within(select).getAllByRole('option').map((o) => o.textContent);
    expect(options).toHaveLength(vocabulary.sources.portal.sections.length);

    fireEvent.change(select, { target: { value: 'System' } });
    const categories = screen.getByRole('list', { name: 'Categories' });
    expect(within(categories).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'system.technique3',
      'system.domain1',
    ]);

    const table = screen.getByRole('table', { name: 'Allowed terms for system.technique' });
    expect(within(table).getAllByRole('row').slice(1).map((r) => r.textContent)).toEqual(['XAS', 'XPS', 'SAXS']);

    fireEvent.click(within(categories).getByRole('button', { name: /system\.domain/ }));
    const second = screen.getByRole('table', { name: 'Allowed terms for system.domain' });
    expect(within(second).getAllByRole('row').slice(1).map((r) => r.textContent)).toEqual(['experimental']);
  });

  it('says so when a section has no fixed lists, and still offers a new list', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(ROUTE);
    const select = await screen.findByRole('combobox', { name: 'Section' });
    fireEvent.change(select, { target: { value: 'Sample' } });
    expect(screen.getByText(/no fixed lists of allowed terms/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Propose a New List in Sample/ })).toBeInTheDocument();
  });

  it('opens the form on the chosen list', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(ROUTE);
    const select = await screen.findByRole('combobox', { name: 'Section' });
    fireEvent.change(select, { target: { value: 'System' } });
    fireEvent.click(screen.getByRole('button', { name: 'Propose a New Term for This List' }));
    expect(screen.getByRole('tab', { name: 'Propose a Change' })).toHaveAttribute('aria-selected', 'true');
    await waitFor(() => {
      expect(screen.getByLabelText('Category')).toHaveValue('system.technique');
    });
  });
});

describe('Propose a Change', () => {
  it('sends exactly the fields the server takes, and says what saving did and did not do', async () => {
    let sent: Record<string, unknown> | null = null;
    const saved = proposal({ term: 'xmcd_scan' });
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
      'POST /api/schema-proposals': (init) => {
        sent = JSON.parse(String(init?.body));
        return { status: 201, body: { ...envelope, proposal: saved, ignored_fields: [] } };
      },
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('Category');
    fireEvent.change(sectionSelect(), { target: { value: 'System' } });
    fillPropose();
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));

    const status = await screen.findByText(/Saved as a draft on this server/);
    expect(status.closest('[role="status"]')).not.toBeNull();
    const notice = within(status.closest('[role="status"]') as HTMLElement);
    expect(notice.getByText(/not sent anywhere\. Drafts here are temporary; copy or download the portal payload/)).toBeInTheDocument();
    expect(notice.getByRole('button', { name: 'Copy Portal Payload' })).toBeInTheDocument();
    expect(notice.getByRole('button', { name: 'Download JSON' })).toBeInTheDocument();
    expect(sent).toEqual({
      proposal_type: 'add_term',
      section: 'System',
      category: 'system.technique',
      term: 'xmcd_scan',
      description: 'Magnetic dichroism measured with circular polarisation.',
    });
    // The form is cleared for the next proposal, and no author field was ever sent.
    expect(screen.getByLabelText('New term')).toHaveValue('');
    expect(JSON.stringify(sent)).not.toMatch(/proposed_by|attribution|status/);
  });

  it('adds the reviewer notes only when something was written, and drops the term for a new list', async () => {
    let sent: Record<string, unknown> | null = null;
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
      'POST /api/schema-proposals': (init) => {
        sent = JSON.parse(String(init?.body));
        return { status: 201, body: { ...envelope, proposal: proposal({ proposal_type: 'add_category', term: null }) } };
      },
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('Category');
    fireEvent.click(screen.getByRole('radio', { name: 'Add a new list of allowed terms' }));
    fireEvent.change(sectionSelect(), { target: { value: 'System' } });
    fireEvent.change(screen.getByLabelText('New list key'), { target: { value: 'system.viscosity' } });
    fireEvent.change(screen.getByLabelText('Description (required)'), {
      target: { value: 'Dynamic viscosity of the medium, needed for flow cells.' },
    });
    fireEvent.change(screen.getByLabelText('Records affected (estimate)'), { target: { value: 'about 40' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    await screen.findByText(/Saved as a draft on this server/);
    expect(sent).toEqual({
      proposal_type: 'add_category',
      section: 'System',
      category: 'system.viscosity',
      description: 'Dynamic viscosity of the medium, needed for flow cells.',
      gate0: { affected_records_estimate: 'about 40' },
    });
  });

  it('shows each server error beside its own field and keeps everything that was typed', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
      'POST /api/schema-proposals': {
        status: 422,
        body: {
          error: 'invalid_term',
          message: 'The proposal needs a few changes before it can be saved.',
          errors: [
            { field: 'term', code: 'invalid_term', message: 'SERVER: a term is a single word.' },
            { field: 'description', code: 'description_too_short', message: 'SERVER: description is too short.' },
          ],
        },
      },
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('Category');
    fireEvent.change(sectionSelect(), { target: { value: 'System' } });
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'system.technique' } });
    fireEvent.change(screen.getByLabelText('New term'), { target: { value: 'bad term' } });
    fireEvent.change(screen.getByLabelText('Description (required)'), { target: { value: 'short' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));

    const termError = await screen.findByText('SERVER: a term is a single word.');
    const term = screen.getByLabelText('New term');
    expect(term).toHaveAttribute('aria-invalid', 'true');
    expect(term.getAttribute('aria-describedby')).toContain(termError.id);
    const description = screen.getByLabelText('Description (required)');
    expect(description).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('SERVER: description is too short.').id).toBeTruthy();
    // Nothing the reader typed was lost, and nothing was claimed saved.
    expect(term).toHaveValue('bad term');
    expect(description).toHaveValue('short');
    expect(screen.queryByText(/Saved as a draft/)).toBeNull();
    expect(screen.getByRole('alert')).toHaveTextContent('The proposal needs a few changes');
  });

  it('shows a conflict (term already exists) as the server worded it', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
      'POST /api/schema-proposals': {
        status: 409,
        body: { error: 'term_already_exists', message: "SERVER: 'XAS' is already an allowed term.", existing_term: 'XAS' },
      },
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('Category');
    fireEvent.change(sectionSelect(), { target: { value: 'System' } });
    fillPropose();
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("SERVER: 'XAS' is already an allowed term.");
    expect(screen.getByLabelText('New term')).toHaveValue('xmcd_scan');
  });

  it('says nothing was written when the server cannot be reached', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
      'POST /api/schema-proposals': () => {
        throw new TypeError('network down');
      },
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('Category');
    fireEvent.change(sectionSelect(), { target: { value: 'System' } });
    fillPropose();
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/nothing was written/i);
    expect(screen.queryByText(/Saved as a draft/)).toBeNull();
  });

  it('keeps a half-written proposal when you look at another tab and come back', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('New term');
    fireEvent.change(screen.getByLabelText('New term'), { target: { value: 'half_written' } });
    fireEvent.click(screen.getByRole('tab', { name: 'Browse the Vocabulary' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Propose a Change' }));
    expect(screen.getByLabelText('New term')).toHaveValue('half_written');
  });
});

describe('Proposals', () => {
  it('lists proposals with their status, states the temporary storage and that no author is recorded', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([
        proposal({ id: '01M61TASK3DFS5VX1C7X1RZJS5' }),
        proposal({ id: '01M61TASK3DFS5VX1C7X1RZJS6', term: 'old_term', status: 'withdrawn', withdrawn_at: '2026-10-28T18:00:00Z' }),
      ]),
    });
    renderAt(`${ROUTE}?tab=proposals`);
    const items = await screen.findAllByRole('listitem');
    const rows = items.filter((li) => li.classList.contains('sp-item'));
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Pending')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Withdrawn')).toBeInTheDocument();
    expect(screen.getAllByText(PERSISTENCE_TEXT).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Author not recorded/).length).toBeGreaterThan(0);
  });

  it('offers Withdraw on a pending proposal only, behind a confirmation, and shows the result', async () => {
    const withdrawn = proposal({ status: 'withdrawn', withdrawn_at: '2026-10-28T18:00:00Z' });
    const calls: string[] = [];
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([
        proposal(),
        proposal({ id: '01M61TASK3DFS5VX1C7X1RZJS6', status: 'withdrawn' }),
      ]),
      'POST /api/schema-proposals/01M61TASK3DFS5VX1C7X1RZJS5/withdraw': () => {
        calls.push('withdraw');
        return { body: { ...envelope, proposal: withdrawn } };
      },
    });
    renderAt(`${ROUTE}?tab=proposals`);
    await screen.findAllByRole('button', { name: 'Copy Portal Payload' });
    expect(screen.getAllByRole('button', { name: 'Withdraw' })).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Withdraw' }));
    expect(calls).toEqual([]); // asking is not withdrawing
    fireEvent.click(screen.getByRole('button', { name: 'Keep It' }));
    expect(screen.getByRole('button', { name: 'Withdraw' })).toBeInTheDocument();
    expect(calls).toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: 'Withdraw' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Withdraw' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Withdraw' })).toBeNull());
    expect(calls).toEqual(['withdraw']);
    expect(screen.getAllByText('Withdrawn')).toHaveLength(2);
  });

  it('shows the server\'s reason when a withdraw is refused and leaves the proposal pending', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal()]),
      'POST /api/schema-proposals/01M61TASK3DFS5VX1C7X1RZJS5/withdraw': {
        status: 409,
        body: { error: 'not_pending', message: 'SERVER: only a pending proposal can be withdrawn.' },
      },
    });
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Withdraw' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('SERVER: only a pending proposal can be withdrawn.');
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });

  it('says there are no proposals yet instead of rendering an empty list', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=proposals`);
    expect(await screen.findByText(/No proposals on this server yet/)).toBeInTheDocument();
    expect(document.querySelector('.sp-item')).toBeNull();
  });

  it('loads further pages on request and appends them', async () => {
    const second = proposal({ id: '01M61TASK3DFS5VX1C7X1RZJS7', term: 'second_page' });
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals?limit=25&offset=0': {
        body: { ...envelope, proposals: [proposal()], total: 2, limit: 25, offset: 0, next_offset: 1, statuses: ['pending', 'withdrawn'], capacity: CAPACITY },
      },
      'GET /api/schema-proposals?limit=25&offset=1': {
        body: { ...envelope, proposals: [second], total: 2, limit: 25, offset: 1, next_offset: null, statuses: ['pending', 'withdrawn'], capacity: CAPACITY },
      },
    });
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Show More' }));
    await screen.findByText(/second_page/);
    expect(document.querySelectorAll('.sp-item')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'Show More' })).toBeNull();
  });
});

describe('Copy and download the portal payload', () => {
  const p = proposal();

  function stubPayload() {
    return stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([p]),
      [`GET /api/schema-proposals/${p.id}/portal-payload`]: { body: payloadFor(p) },
    });
  }

  it('copies the exact portal body and says ISAAC has not sent it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    stubPayload();
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Copy Portal Payload' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(JSON.parse(writeText.mock.calls[0][0])).toEqual(payloadFor(p).body);
    expect(await screen.findByText(/ISAAC has not sent it/)).toBeInTheDocument();
  });

  it('shows the text to copy by hand, and does not claim it was copied, when the browser refuses', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'));
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    stubPayload();
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Copy Portal Payload' }));
    const box = await screen.findByRole('textbox', { name: 'Portal payload' });
    expect(JSON.parse((box as HTMLTextAreaElement).value)).toEqual(payloadFor(p).body);
    expect(screen.queryByText(/^Copied/)).toBeNull();
  });

  it('downloads the portal body as a JSON file named for the proposal', async () => {
    stubPayload();
    let blob: Blob | null = null;
    const createObjectURL = vi.fn((b: Blob) => {
      blob = b;
      return 'blob:test';
    });
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const clicked: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this.download);
    });
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Download JSON' }));
    await waitFor(() => expect(clicked).toEqual([`isaac-schema-proposal-${p.id}.json`]));
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test');
    expect(blob).not.toBeNull();
    expect(JSON.parse(await readBlob(blob as unknown as Blob))).toEqual(payloadFor(p).body);
    expect(await screen.findByText(/ISAAC has not sent it anywhere/)).toBeInTheDocument();
  });

  it('says nothing was copied when the payload cannot be fetched', async () => {
    const writeText = vi.fn();
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([p]),
      [`GET /api/schema-proposals/${p.id}/portal-payload`]: { status: 404, body: { error: 'proposal_not_found', message: 'gone' } },
    });
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Copy Portal Payload' }));
    expect(await screen.findByText(/Nothing was copied/)).toBeInTheDocument();
    expect(writeText).not.toHaveBeenCalled();
  });
});

describe('review fixes', () => {
  it('Browse shows both vocabulary sources, labelled, and never calls either "the official vocabulary"', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(ROUTE);
    const portalRadio = await screen.findByRole('radio', { name: 'Portal vocabulary (snapshot a1cb1c8)' });
    const schemaRadio = screen.getByRole('radio', { name: 'Schema enums (vendored v1.05)' });
    expect(portalRadio).toBeChecked();
    expect(screen.getByText(/DETAIL-PORTAL/)).toBeInTheDocument();

    fireEvent.click(schemaRadio);
    expect(screen.getByText(/DETAIL-SCHEMA/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: 'Section' }), { target: { value: 'Context' } });
    const table = screen.getByRole('table', { name: 'Allowed terms for context.environment' });
    expect(within(table).getAllByRole('row').slice(1).map((r) => r.textContent)).toEqual(['ambient', 'vacuum']);
    expect(document.body.textContent ?? '').not.toMatch(/official vocabulary/i);
  });

  it('offers a new term only for a list the portal has, and says why for one it does not', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(ROUTE);
    fireEvent.click(await screen.findByRole('radio', { name: 'Schema enums (vendored v1.05)' }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Section' }), { target: { value: 'Context' } });
    expect(screen.queryByRole('button', { name: 'Propose a New Term for This List' })).toBeNull();
    expect(screen.getByText(/portal would\s+refuse a new term/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Portal vocabulary (snapshot a1cb1c8)' }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Section' }), { target: { value: 'System' } });
    expect(screen.getByRole('button', { name: 'Propose a New Term for This List' })).toBeInTheDocument();
  });

  it('the new-term form offers only the portal term lists of the chosen section', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('Category');
    fireEvent.change(sectionSelect(), { target: { value: 'System' } });
    const options = within(screen.getByLabelText('Category')).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(['Choose a list…', 'system.technique', 'system.domain']);
    fireEvent.change(sectionSelect(), { target: { value: 'Context' } });
    expect(within(screen.getByLabelText('Category')).getAllByRole('option').map((o) => o.textContent)).toEqual(['Choose a list…']);
    expect(screen.getByText(/portal vocabulary snapshot has no term lists in this section/)).toBeInTheDocument();
  });

  it('says a new list goes into the portal Ontology Editor, not the web endpoint, and shows the server notes', async () => {
    const category = proposal({ proposal_type: 'add_category', category: 'system.viscosity', term: null });
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([category]),
      [`GET /api/schema-proposals/${category.id}/portal-payload`]: {
        body: {
          ...payloadFor(category),
          portal: { method: 'POST', path: '/portal/api/vocabulary/proposals', rest_supported: false },
          notes: ['SERVER-NOTE: the web endpoint takes new terms only.'],
        },
      },
    });
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Copy Portal Payload' }));
    const status = await screen.findByText(/Ontology Editor/);
    expect(status.textContent).toMatch(/ISAAC has not sent it/);
    expect(status.textContent).not.toMatch(/Paste it into the ISAAC portal/);
    expect(screen.getByText('SERVER-NOTE: the web endpoint takes new terms only.')).toBeInTheDocument();
  });

  it('still tells a new TERM to be pasted into the portal', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    const p = proposal();
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([p]),
      [`GET /api/schema-proposals/${p.id}/portal-payload`]: { body: payloadFor(p) },
    });
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Copy Portal Payload' }));
    expect(await screen.findByText(/Paste it into the ISAAC portal/)).toBeInTheDocument();
  });

  it('shows how many pending places are used and who shares them', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal()]),
    });
    renderAt(`${ROUTE}?tab=proposals`);
    expect(await screen.findByText(/2 of 50 pending places used\. SERVER-SAID: shared by everyone/)).toBeInTheDocument();
  });
});

describe('the boundary is stated once', () => {
  const statement = /does not approve/g;
  const count = () => (document.body.textContent?.match(statement) ?? []).length;

  it('appears exactly once on the page, before and after saving and on the proposals tab', async () => {
    const saved = proposal({ term: 'xmcd_scan' });
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([saved]),
      'POST /api/schema-proposals': { status: 201, body: { ...envelope, proposal: saved, ignored_fields: [] } },
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('Category');
    expect(count()).toBe(1);
    fireEvent.change(sectionSelect(), { target: { value: 'System' } });
    fillPropose();
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    await screen.findByText(/Saved as a draft on this server/);
    expect(count()).toBe(1);
    fireEvent.click(screen.getByRole('tab', { name: 'Proposals' }));
    await screen.findByText(/pending places used/);
    expect(count()).toBe(1);
    // The server's own review note is never rendered a second time.
    expect(document.body.textContent).not.toContain(REVIEW_TEXT);
  });
});

describe('audit fixes', () => {
  it('Keep It returns focus to Withdraw and says the proposal is still pending', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal()]),
    });
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw' }));
    fireEvent.click(screen.getByRole('button', { name: 'Keep It' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Withdraw' })).toHaveFocus());
    expect(screen.getByTestId('sp-row-status')).toHaveAttribute('role', 'status');
    expect(screen.getByTestId('sp-row-status')).toHaveTextContent('Kept. The proposal is still pending.');
  });

  it('a successful withdraw moves focus to the proposal and announces it', async () => {
    const withdrawn = proposal({ status: 'withdrawn', withdrawn_at: '2026-10-28T18:00:00Z' });
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal()]),
      'POST /api/schema-proposals/01M61TASK3DFS5VX1C7X1RZJS5/withdraw': { body: { ...envelope, proposal: withdrawn } },
    });
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Withdraw' }));
    const row = (await screen.findByText('Withdrawn', { selector: '.sp-status' })).closest('li') as HTMLElement;
    await waitFor(() => expect(within(row).getByRole('heading', { level: 2 })).toHaveFocus());
    expect(within(row).getByTestId('sp-row-status')).toHaveTextContent('Withdrawn. The proposal is no longer pending.');
  });

  it('proposal dates are a person’s date, with the exact instant kept on a <time>', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal({ status: 'withdrawn', withdrawn_at: '2026-10-28T18:00:00Z' })]),
    });
    renderAt(`${ROUTE}?tab=proposals`);
    const row = (await screen.findByText('Withdrawn', { selector: '.sp-status' })).closest('li') as HTMLElement;
    expect(row).not.toHaveTextContent('2026-10-28T17:53:37Z');
    const times = row.querySelectorAll('time');
    expect([...times].map((t) => t.getAttribute('dateTime'))).toEqual(['2026-10-28T17:53:37Z', '2026-10-28T18:00:00Z']);
    expect(times[0].textContent).toBe(formatWhen('2026-10-28T17:53:37Z'));
  });

  it('a category error is added to the category’s hint, not put in its place', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
      'POST /api/schema-proposals': {
        status: 422,
        body: { error: 'invalid', message: 'SERVER: check the fields.', errors: [{ field: 'category', code: 'required', message: 'SERVER: choose a list.' }] },
      },
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('Category');
    fireEvent.change(sectionSelect(), { target: { value: 'System' } });
    fillPropose();
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    await screen.findByText('SERVER: choose a list.');
    const ids = (screen.getByLabelText('Category').getAttribute('aria-describedby') ?? '').split(' ');
    expect(ids).toHaveLength(2);
    expect(ids[0]).toMatch(/-hint$/);
    expect(ids[1]).toMatch(/-err$/);
    for (const id of ids) expect(document.getElementById(id)).not.toBeNull();
  });

  it('section-named buttons wrap instead of pushing the page sideways', () => {
    const css = readFileSync(join(process.cwd(), 'src', 'screens', 'schema-proposals.css'), 'utf8');
    expect(css).toMatch(/\.sp-actions \.btn\s*\{[^}]*white-space:\s*normal;[^}]*overflow-wrap:\s*anywhere;/);
  });
});

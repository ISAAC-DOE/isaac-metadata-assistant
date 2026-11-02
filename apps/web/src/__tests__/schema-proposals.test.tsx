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
import { chooseIn, chooseOption, chooseSegment, getSelect, selectGroups, selectOptions, selectValue } from '../test/controls';
import {
  SCHEMA_PROPOSALS_COPY as COPY,
  portalSectionFor,
  type ApiSchemaPortalPayload,
  type ApiSchemaProposal,
  type ApiSchemaVocabulary,
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

/*
 * NO FALSE CLAIM. The standing disclaimers are gone (owner's brief, 2026-11-02); what replaces a pinned
 * disclaimer is a ban on the claim it guarded against: that the page sent, submitted or approved anything, or
 * that a proposal is kept permanently. Run against the page text, never against a server-served note.
 */
const FALSE_CLAIM =
  /\b(?:was|were|been|is|are) (?:sent|submitted|approved|accepted|applied)\b|\bsent to (?:the )?(?:ISAAC )?portal\b|\bpermanent(?:ly)?\b|\bkept (?:forever|for good)\b/i;

/** The notice shown after a save, found by its own sentence (a saved draft row starts with the same words). */
const SAVED_NOTICE = /^Saved as a draft\. Copy or download it to send it to the ISAAC portal\.$/;

function listBody(proposals: ApiSchemaProposal[]) {
  return { ...envelope, proposals, total: proposals.length, limit: 25, offset: 0, next_offset: null, statuses: ['pending', 'withdrawn'], capacity: CAPACITY };
}

function list(proposals: ApiSchemaProposal[]): RouteEntry {
  return { body: listBody(proposals) };
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

/** The form's own region; Browse (folded below it) has a Section select of the same name. */
function proposeRegion(): HTMLElement {
  return screen.getByRole('region', { name: 'Propose a Change' });
}

/** The Section select INSIDE the form (offered for a new list only); Browse has one of the same name. */
function sectionSelect(): HTMLElement {
  return getSelect('Section', proposeRegion());
}

/** Browse's own Section picker (the form has one of the same name for a new list). */
function browseSection(): HTMLElement {
  return getSelect('Section', browseDetails());
}

/** The folded vocabulary, by its summary. */
function browseDetails(): HTMLDetailsElement {
  return screen.getByText(COPY.browseTitle).closest('details') as HTMLDetailsElement;
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
  chooseOption('List', 'Technique');
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

  it('says where a proposal goes from here, claims nothing it does not do, and offers no approve, apply or send control', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal()]),
    });
    renderAt(ROUTE);
    await screen.findByRole('combobox', { name: 'List' });
    await screen.findAllByRole('button', { name: 'Copy Portal Payload' });
    expect(screen.getByText(COPY.boundary)).toBeInTheDocument();
    expect(document.body.textContent ?? '').not.toMatch(FALSE_CLAIM);
    // One page: the form, the proposals and the folded vocabulary are all in the document at once.
    const controls = screen
      .getAllByRole('button')
      .map((b) => b.textContent ?? '')
      .concat(screen.getAllByRole('link').map((a) => a.textContent ?? ''));
    expect(controls.filter((c) => /approve|apply|accept|reject|send/i.test(c))).toEqual([]);
  });

  it('is one page: no tab anywhere, the form and the proposals side by side, the vocabulary folded', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal()]),
    });
    renderAt(ROUTE);
    await screen.findByRole('combobox', { name: 'List' });
    expect(screen.queryAllByRole('tab')).toEqual([]);
    expect(screen.queryAllByRole('tablist')).toEqual([]);
    expect(screen.queryAllByRole('tabpanel')).toEqual([]);
    expect(screen.getByRole('heading', { level: 2, name: 'Propose a Change' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Proposals' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Proposals' })).toBeInTheDocument();
    expect(browseDetails()).not.toHaveAttribute('open');
  });

  it('?tab=browse opens the folded vocabulary; any other old tab link opens nothing and the page never writes one', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    const first = renderAt(`${ROUTE}?tab=browse`);
    await screen.findByRole('radiogroup', { name: 'Source' });
    await waitFor(() => expect(browseDetails()).toHaveAttribute('open'));
    first.unmount();
    for (const path of [`${ROUTE}?tab=propose`, `${ROUTE}?tab=proposals`, ROUTE]) {
      const r = renderAt(path);
      await screen.findByRole('combobox', { name: 'List' });
      expect(browseDetails()).not.toHaveAttribute('open');
      r.unmount();
    }
  });
});

describe('Browse', () => {
  it('goes section -> list -> terms: lists by their human name with key and count, terms as a named set', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=browse`);
    await screen.findByRole('radiogroup', { name: 'Source' });
    expect(browseDetails().querySelector('summary')).toHaveTextContent(COPY.browseTitle);
    expect(selectOptions(browseSection())).toHaveLength(vocabulary.sources.portal.sections.length);

    chooseIn(browseSection(), 'System');
    const lists = within(browseDetails()).getByRole('list', { name: 'Lists in System' });
    const rows = within(lists).getAllByRole('button');
    expect(rows.map((b) => b.querySelector('.sp-cat-name')?.textContent)).toEqual(['Technique', 'Domain']);
    expect(rows.map((b) => b.querySelector('.sp-cat-key')?.textContent)).toEqual(['system.technique', 'system.domain']);
    expect(rows.map((b) => b.querySelector('.sp-cat-count')?.textContent)).toEqual(['3 terms', '1 term']);
    expect(rows[0]).toHaveAttribute('aria-pressed', 'true');

    const terms = within(browseDetails()).getByRole('list', { name: 'Allowed terms for system.technique' });
    expect(within(terms).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['XAS', 'XPS', 'SAXS']);
    expect(within(browseDetails()).getByRole('heading', { level: 3, name: 'Technique' })).toBeInTheDocument();

    fireEvent.click(rows[1]);
    const second = within(browseDetails()).getByRole('list', { name: 'Allowed terms for system.domain' });
    expect(within(second).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['experimental']);
    expect(rows[1]).toHaveAttribute('aria-pressed', 'true');
  });

  it('says so in one line when a section has no fixed lists, and offers a new list in it there', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=browse`);
    await screen.findByRole('radiogroup', { name: 'Source' });
    chooseIn(browseSection(), 'Sample');
    expect(screen.getByText('This section has no fixed lists of allowed terms in this source.')).toBeInTheDocument();
    expect(within(browseDetails()).getByRole('button', { name: 'New List in Sample' })).toBeInTheDocument();
    // This server describes no new-field kind, so none is offered here either.
    expect(within(browseDetails()).queryByRole('button', { name: /New Field in/ })).toBeNull();
  });

  it('"Propose a Term for This List" fills the form on that list and puts the cursor in "New term"', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=browse`);
    await screen.findByRole('radiogroup', { name: 'Source' });
    chooseIn(browseSection(), 'System');
    // The kind is switched back to a term even if another kind was chosen.
    fireEvent.click(screen.getByRole('radio', { name: COPY.kindList }));
    const propose = screen.getByRole('button', { name: 'Propose a Term for This List' });
    expect(propose).toHaveClass('btn-primary');
    fireEvent.click(propose);
    await waitFor(() => expect(selectValue(getSelect('List'))).toBe('system.technique'));
    expect(screen.getByRole('radio', { name: COPY.kindTerm })).toBeChecked();
    await waitFor(() => expect(screen.getByLabelText('New term')).toHaveFocus());
  });

  it('"New List in <section>" opens the form on a new list in that section, cursor in "New list key"', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=browse`);
    await screen.findByRole('radiogroup', { name: 'Source' });
    chooseIn(browseSection(), 'Record Info (root fields)');
    // The section's human name, without its parenthetical, in the action's words.
    fireEvent.click(within(browseDetails()).getByRole('button', { name: 'New List in Record Info' }));
    expect(screen.getByRole('radio', { name: COPY.kindList })).toBeChecked();
    expect(selectValue(sectionSelect())).toBe('Record Info');
    await waitFor(() => expect(screen.getByLabelText('New list key')).toHaveFocus());
  });
});

describe('Browse All Lists, from the form', () => {
  it('opens Look Up on the chosen list\'s section and list, and puts focus on its Section picker', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(ROUTE);
    await screen.findByRole('combobox', { name: 'List' });
    chooseOption('List', 'Domain');
    expect(browseDetails()).not.toHaveAttribute('open');
    const action = within(proposeRegion()).getByRole('button', { name: 'Browse All Lists' });
    expect(action).toHaveClass('sp-text-btn');
    fireEvent.click(action);
    await waitFor(() => expect(browseSection()).toHaveFocus());
    expect(browseDetails()).toHaveAttribute('open');
    expect(selectValue(browseSection())).toBe('System');
    const lists = within(browseDetails()).getByRole('list', { name: 'Lists in System' });
    expect(within(lists).getByRole('button', { name: /Domain/ })).toHaveAttribute('aria-pressed', 'true');
    // The form was not touched.
    expect(selectValue(getSelect('List'))).toBe('system.domain');
  });

  it('with no list chosen, it just opens Look Up and focuses its Section picker', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(ROUTE);
    await screen.findByRole('combobox', { name: 'List' });
    fireEvent.click(within(proposeRegion()).getByRole('button', { name: 'Browse All Lists' }));
    await waitFor(() => expect(browseSection()).toHaveFocus());
    expect(browseDetails()).toHaveAttribute('open');
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
    await screen.findByLabelText('List');
    fillPropose();
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));

    const status = await screen.findByText(SAVED_NOTICE);
    expect(status.closest('[role="status"]')).not.toBeNull();
    const notice = within(status.closest('[role="status"]') as HTMLElement);
    // It says what to do next, and claims nothing was sent.
    expect(status.closest('[role="status"]')?.textContent ?? '').not.toMatch(FALSE_CLAIM);
    expect(notice.getByRole('button', { name: 'Copy Portal Payload' })).toBeInTheDocument();
    expect(notice.getByRole('button', { name: 'Download JSON' })).toBeInTheDocument();
    // The list is beside the form, so the notice has no "View Proposals" button.
    expect(notice.queryByRole('button', { name: 'View Proposals' })).toBeNull();
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
    await screen.findByLabelText('List');
    fireEvent.click(screen.getByRole('radio', { name: COPY.kindList }));
    chooseIn(sectionSelect(), 'System');
    fireEvent.change(screen.getByLabelText('New list key'), { target: { value: 'system.viscosity' } });
    fireEvent.change(screen.getByLabelText('Description (required)'), {
      target: { value: 'Dynamic viscosity of the medium, needed for flow cells.' },
    });
    fireEvent.change(screen.getByLabelText('Records affected (estimate)'), { target: { value: 'about 40' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    await screen.findByText(SAVED_NOTICE);
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
    await screen.findByLabelText('List');
    chooseOption('List', 'Technique');
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
    await screen.findByLabelText('List');
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
    await screen.findByLabelText('List');
    fillPropose();
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/nothing was written/i);
    expect(screen.queryByText(/Saved as a draft/)).toBeNull();
  });

  it('keeps a half-written proposal while you browse the vocabulary, and across a change of kind', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('New term');
    fireEvent.change(screen.getByLabelText('New term'), { target: { value: 'half_written' } });
    fireEvent.change(screen.getByLabelText('Description (required)'), { target: { value: 'Half a description.' } });
    fireEvent.change(screen.getByLabelText('Examples'), { target: { value: 'run 4' } });
    // Looking around Browse does not touch the form.
    fireEvent.click(screen.getByText(COPY.browseTitle));
    chooseIn(browseSection(), 'System');
    expect(screen.getByLabelText('New term')).toHaveValue('half_written');
    // The shared boxes survive a change of kind and back.
    fireEvent.click(screen.getByRole('radio', { name: COPY.kindList }));
    expect(screen.getByLabelText('Description (required)')).toHaveValue('Half a description.');
    expect(screen.getByLabelText('Examples')).toHaveValue('run 4');
    fireEvent.click(screen.getByRole('radio', { name: COPY.kindTerm }));
    expect(screen.getByLabelText('Description (required)')).toHaveValue('Half a description.');
  });

  it('names each kind by its title alone, with its one-line hint as the description', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(ROUTE);
    const group = await screen.findByRole('group', { name: 'What do you want to propose?' });
    const radios = within(group).getAllByRole('radio');
    // This server does not describe the third kind, so two are offered.
    expect(radios.map((r) => r.getAttribute('aria-describedby') !== null)).toEqual([true, true]);
    expect(radios[0]).toHaveAccessibleName(COPY.kindTerm);
    expect(radios[0]).toHaveAccessibleDescription(COPY.kindTermHint);
    expect(radios[1]).toHaveAccessibleName(COPY.kindList);
    expect(radios[1]).toHaveAccessibleDescription(COPY.kindListHint);
    expect(radios[0]).toBeChecked();
  });

  it('offers one List choice grouped by section, and sends the section of the group the list is in', async () => {
    let sent: Record<string, unknown> | null = null;
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
      'POST /api/schema-proposals': (init) => {
        sent = JSON.parse(String(init?.body));
        return { status: 201, body: { ...envelope, proposal: proposal({ category: 'record_type', section: 'Record Info', term: 'simulation' }), ignored_fields: [] } };
      },
    });
    renderAt(ROUTE);
    const select = await screen.findByRole('combobox', { name: 'List' });
    // No separate Section choice for a term: the List carries it.
    expect(within(proposeRegion()).queryByLabelText('Section')).toBeNull();
    // Each list by the name a person uses, as Browse shows it, with its key as the option's description.
    expect(selectGroups(select)).toEqual([
      { group: 'Record Info (root fields)', options: ['Record type'] },
      { group: 'System', options: ['Technique', 'Domain'] },
    ]);
    fireEvent.click(select);
    for (const [name, key] of [['Record type', 'record_type'], ['Technique', 'system.technique'], ['Domain', 'system.domain']]) {
      expect(screen.getByRole('option', { name })).toHaveAccessibleDescription(key);
    }
    fireEvent.keyDown(select, { key: 'Escape' });
    // A themed picker, not the browser's: nothing chosen yet shows the placeholder.
    expect(select.tagName).toBe('BUTTON');
    expect(select).toHaveTextContent('Choose a list…');
    chooseIn(select, 'Record type');
    expect(select).toHaveTextContent('Record type');
    // Type-ahead goes by the name too: "d" on the open picker lands on Domain.
    fireEvent.keyDown(select, { key: 'ArrowDown' });
    fireEvent.keyDown(select, { key: 'd' });
    const active = document.getElementById(select.getAttribute('aria-activedescendant') ?? '');
    expect(active?.querySelector('.select-option-name')?.textContent).toBe('Domain');
    fireEvent.keyDown(select, { key: 'Escape' });
    fireEvent.change(screen.getByLabelText('New term'), { target: { value: 'simulation' } });
    fireEvent.change(screen.getByLabelText('Description (required)'), {
      target: { value: 'A record that describes a simulation, not a measurement.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    await screen.findByText(SAVED_NOTICE);
    expect(sent).toMatchObject({ proposal_type: 'add_term', section: 'Record Info', category: 'record_type' });
    expect((sent as unknown as { section: string }).section).toBe(portalSectionFor(vocabulary, 'record_type'));
  });

  it('says what the chosen list already holds, naming the first twelve and counting the rest', async () => {
    const many = Array.from({ length: 15 }, (_, i) => `T${String(i + 1).padStart(2, '0')}`);
    const big: ApiSchemaVocabulary = structuredClone(vocabulary);
    big.sources.portal.sections[1].categories[0].terms = many;
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: big },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(ROUTE);
    const select = await screen.findByRole('combobox', { name: 'List' });
    expect(screen.queryByText(/Already on the list/)).toBeNull();
    // The hint the picker is described by, as written (the description algorithm adds a space at the mono span).
    const describedBy = () =>
      (select.getAttribute('aria-describedby') ?? '')
        .split(' ')
        .map((id) => document.getElementById(id)?.textContent ?? '')
        .join(' ');
    chooseIn(select, 'Domain');
    expect(describedBy()).toBe('Already on the list (1): experimental.');
    chooseIn(select, 'Technique');
    expect(describedBy()).toBe(`Already on the list (15): ${many.slice(0, 12).join(', ')} and 3 more.`);
  });
});

describe('Proposals', () => {
  it('lists proposals with their status and the server\'s first sentence on storage, claiming no permanence and naming no unverified author', async () => {
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
    const column = screen.getByRole('region', { name: 'Proposals' });
    expect(column.textContent ?? '').not.toMatch(FALSE_CLAIM);
    // Unverified: nobody is named, and no stand-in sentence is put in the name's place.
    expect(column.textContent ?? '').not.toMatch(/Proposed by|Author/);
  });

  it('shows only the first sentence of the server\'s storage statement', async () => {
    const message = 'SERVER-SAID: proposals here are temporary. They live in a working folder. It is cleared on restart.';
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': {
        body: { ...listBody([proposal()]), persistence: { ...envelope.persistence, message } },
      },
    });
    renderAt(ROUTE);
    expect(await screen.findByText('SERVER-SAID: proposals here are temporary.')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('They live in a working folder');
  });

  it('names the author only when the server verified one', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal({ attribution: 'verified', proposed_by: 'SYN Scientist' })]),
    });
    renderAt(ROUTE);
    expect(await screen.findByText('Proposed by SYN Scientist')).toBeInTheDocument();
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
    // Scoped to the column: a role query over the whole one-page DOM is slow under a loaded machine.
    const column = within(await screen.findByRole('region', { name: 'Proposals' }));
    fireEvent.click(await column.findByRole('button', { name: 'Show More' }, { timeout: 4000 }));
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

  it('copies the exact portal body and says where to paste it, claiming nothing was sent', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    stubPayload();
    renderAt(`${ROUTE}?tab=proposals`);
    fireEvent.click(await screen.findByRole('button', { name: 'Copy Portal Payload' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(JSON.parse(writeText.mock.calls[0][0])).toEqual(payloadFor(p).body);
    const said = await screen.findByText(/^Copied\. Paste it into the ISAAC portal\.$/);
    expect(said.textContent).not.toMatch(FALSE_CLAIM);
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
    const said = await screen.findByText(/^Downloaded\. Paste it into the ISAAC portal\.$/);
    expect(said.textContent).not.toMatch(FALSE_CLAIM);
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
  it('Browse shows both vocabulary sources by short names, one quiet fact each, never "the official vocabulary"', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=browse`);
    const source = await screen.findByRole('radiogroup', { name: 'Source' });
    const portal = within(source).getByRole('radio', { name: 'Portal Vocabulary' });
    expect(portal).toHaveAttribute('aria-checked', 'true');
    expect(
      within(browseDetails()).getByText(/The ISAAC portal's terms, snapshot a1cb1c8: 3 sections, 3 term lists, 6 terms\./),
    ).toBeInTheDocument();
    // The server's long source prose is not repeated on the page.
    expect(screen.queryByText(/DETAIL-PORTAL/)).toBeNull();

    chooseSegment('Source', 'Schema Lists');
    expect(within(source).getByRole('radio', { name: 'Schema Lists' })).toHaveAttribute('aria-checked', 'true');
    expect(within(browseDetails()).getByText(/The record schema's fixed lists, version 1\.05/)).toBeInTheDocument();
    chooseIn(browseSection(), 'Context');
    const terms = within(browseDetails()).getByRole('list', { name: 'Allowed terms for context.environment' });
    expect(within(terms).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['ambient', 'vacuum']);
    expect(document.body.textContent ?? '').not.toMatch(/official vocabulary/i);
  });

  it('offers a new term only for a list the portal has, and says why in one line for one it does not', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=browse`);
    await screen.findByRole('radiogroup', { name: 'Source' });
    chooseSegment('Source', 'Schema Lists');
    chooseIn(browseSection(), 'Context');
    expect(screen.queryByRole('button', { name: 'Propose a Term for This List' })).toBeNull();
    expect(screen.getByText(/it would refuse a new term for it/)).toBeInTheDocument();
    chooseSegment('Source', 'Portal Vocabulary');
    chooseIn(browseSection(), 'System');
    expect(screen.getByRole('button', { name: 'Propose a Term for This List' })).toBeInTheDocument();
  });

  it('every action on the page is themed blue: one primary, tinted actions, quiet text for the rest; none is white', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal()]),
    });
    renderAt(`${ROUTE}?tab=browse`);
    await screen.findAllByRole('button', { name: 'Copy Portal Payload' });
    await screen.findByRole('radiogroup', { name: 'Source' });
    expect(document.querySelectorAll('.sp-screen .btn-secondary')).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Save Proposal' })).toHaveClass('btn-primary');
    expect(screen.getByRole('button', { name: 'Copy Portal Payload' })).toHaveClass('btn-action');
    expect(screen.getByRole('button', { name: 'Download JSON' })).toHaveClass('btn-action');
    expect(screen.getByRole('button', { name: 'Withdraw' })).toHaveClass('btn-danger-quiet');
    // No browser-default <select> is left on the screen.
    expect(document.querySelectorAll('.sp-screen select')).toHaveLength(0);
  });

  it('the new-term form offers only the portal term lists, and says so when there are none', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([]),
    });
    const first = renderAt(`${ROUTE}?tab=propose`);
    const options = selectOptions(await screen.findByLabelText('List'));
    // Only the portal's term lists: the schema-only `context.environment` is not one.
    expect(options).toEqual(['Record type', 'Technique', 'Domain']);
    first.unmount();
    const bare: ApiSchemaVocabulary = {
      ...vocabulary,
      proposal_sections: vocabulary.proposal_sections.map((s) => ({ ...s, term_lists: [] })),
    };
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: bare },
      'GET /api/schema-proposals': list([]),
    });
    renderAt(`${ROUTE}?tab=propose`);
    expect(selectOptions(await screen.findByLabelText('List'))).toEqual([]);
    expect(screen.getByText(/portal vocabulary snapshot has no term lists/)).toBeInTheDocument();
  });

  it('a proposal row is folded: its summary says what and where, and its details hold the actions', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal()]),
    });
    renderAt(ROUTE);
    const row = (await screen.findByText('Pending', { selector: '.sp-status' })).closest('li') as HTMLElement;
    const details = row.querySelector('details') as HTMLDetailsElement;
    expect(details).not.toHaveAttribute('open');
    const summary = details.querySelector('summary') as HTMLElement;
    expect(summary).toHaveTextContent('Add the term XMCD to system.technique');
    expect(within(summary).getByText('Pending')).toBeInTheDocument();
    expect(summary.querySelector('time')).not.toBeNull();
    expect(within(summary).queryByRole('button')).toBeNull();
    const body = details.querySelector('.sp-proposal-body') as HTMLElement;
    for (const name of ['Copy Portal Payload', 'Download JSON', 'Withdraw']) {
      expect(within(body).getByRole('button', { name })).toBeInTheDocument();
    }
    expect(body).toHaveTextContent('X-ray magnetic circular dichroism, measured at SSRL.');
    expect(body).not.toHaveTextContent(/Author|Proposed by/);
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
    expect(status.textContent).toMatch(/^Copied\. /);
    expect(status.textContent).not.toMatch(FALSE_CLAIM);
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

  it('shows how many pending places are used, and who shares them, only near the limit', async () => {
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([proposal()]),
    });
    const far = renderAt(`${ROUTE}?tab=proposals`);
    await screen.findByText(PERSISTENCE_TEXT);
    expect(screen.queryByText(/pending places used/)).toBeNull();
    far.unmount();
    for (const [pending, shown] of [[39, false], [40, true], [50, true]] as const) {
      stubFetchRoutes({
        'GET /api/schema-proposals/vocabulary': { body: vocabulary },
        'GET /api/schema-proposals': {
          body: { ...listBody([proposal()]), capacity: { ...CAPACITY, pending } },
        },
      });
      const r = renderAt(ROUTE);
      await screen.findByText(PERSISTENCE_TEXT);
      const line = screen.queryByText(new RegExp(`^${pending} of 50 pending places used\\. SERVER-SAID: shared by everyone`));
      expect(line !== null).toBe(shown);
      r.unmount();
    }
  });
});

describe('the boundary is stated once', () => {
  const statement = new RegExp(COPY.boundary.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
  const count = () => (document.body.textContent?.match(statement) ?? []).length;

  it('appears exactly once on the page, before and after saving, with the proposals listed', async () => {
    const saved = proposal({ term: 'xmcd_scan' });
    stubFetchRoutes({
      'GET /api/schema-proposals/vocabulary': { body: vocabulary },
      'GET /api/schema-proposals': list([saved]),
      'POST /api/schema-proposals': { status: 201, body: { ...envelope, proposal: saved, ignored_fields: [] } },
    });
    renderAt(`${ROUTE}?tab=propose`);
    await screen.findByLabelText('List');
    expect(count()).toBe(1);
    fillPropose();
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    await screen.findByText(SAVED_NOTICE);
    expect(count()).toBe(1);
    await screen.findByText(PERSISTENCE_TEXT);
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
    // The proposal itself takes focus: its summary, which now reads Withdrawn.
    const summary = within(row).getByText('Add the term XMCD to system.technique').closest('summary') as HTMLElement;
    await waitFor(() => expect(summary).toHaveFocus());
    expect(summary).toHaveTextContent('Withdrawn');
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
    await screen.findByLabelText('List');
    fillPropose();
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    await screen.findByText('SERVER: choose a list.');
    const ids = (screen.getByLabelText('List').getAttribute('aria-describedby') ?? '').split(' ');
    expect(ids).toHaveLength(2);
    expect(ids[0]).toMatch(/-hint$/);
    expect(ids[1]).toMatch(/-err$/);
    for (const id of ids) expect(document.getElementById(id)).not.toBeNull();
  });

  it('a long button label in the narrow proposals column wraps instead of pushing the page sideways', () => {
    const css = readFileSync(join(process.cwd(), 'src', 'screens', 'schema-proposals.css'), 'utf8');
    expect(css).toMatch(/\.sp-actions \.btn\s*\{[^}]*white-space:\s*normal;[^}]*overflow-wrap:\s*anywhere;/);
  });
});

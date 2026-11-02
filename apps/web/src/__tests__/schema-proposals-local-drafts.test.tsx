import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { ROUTES } from '../lib/routes';
import { stubFetchRoutes } from '../test/apiFixtures';
import type { ApiSchemaProposal, ApiSchemaVocabulary } from '../lib/schemaProposals';
import { countsSentence, gate0FromDraft, parseTermDraftsFile } from '../lib/termDrafts';

/**
 * Schema Proposals: load the drafts file `isaac bundle propose-terms --out` writes, in the
 * browser, and file one draft at a time. What is pinned is BEHAVIOUR: the file is read here and
 * nothing is requested while it is read or while a draft is opened; the terms are listed in three
 * groups (needs your description, cannot be proposed, nothing needed from you) whose counts the
 * summary line repeats; each term is listed with its field, counts, the scientist's own words where
 * the file has them and the problems it reports; a term the file did not draft cannot be filed; a
 * drafted one opens the form with the description EMPTY and the reviewer notes filled from the
 * file's facts only, and its row says it is the one in the form; and the body sent on save carries
 * the `source` block the server checks. All values are synthetic.
 */

const envelope = {
  persistence: { class: 'workspace_files', survives_restart: 'not_guaranteed', message: 'SERVER-SAID: temporary.' },
  review_note: 'SERVER-SAID: review happens in the ISAAC portal.',
  attribution_note: 'Who is calling is not verified.',
};

const limits = {
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
};

const systemSection = {
  id: 'System',
  label: 'System',
  block: 'system',
  categories: [
    { key: 'system.technique', label: 'technique', description: '', terms: ['XAS', 'XPS'], kind: 'terms' as const },
    { key: 'system.domain', label: 'domain', description: '', terms: ['experimental'], kind: 'terms' as const },
  ],
};

const vocabulary: ApiSchemaVocabulary = {
  schema_version: '1.05',
  default_source: 'portal',
  term_rule: 'RULE: one word, no spaces.',
  review_note: envelope.review_note,
  proposal_types: ['add_term', 'add_category'],
  limits,
  term_shape: { term: '^[A-Za-z][A-Za-z0-9_./-]*$', snake_case: '^[a-z][a-z0-9_]*$', path_like: '(\\.\\.|//|\\./|/\\.)' },
  sources: {
    portal: {
      id: 'portal',
      label: 'Portal vocabulary (snapshot a1cb1c8)',
      detail: 'DETAIL-PORTAL',
      snapshot_commit: 'a1cb1c8',
      sha256: 'b'.repeat(64),
      section_count: 1,
      category_count: 2,
      term_list_count: 2,
      term_count: 3,
      sections: [systemSection],
    },
    schema: {
      id: 'schema',
      label: 'Schema enums (vendored v1.05)',
      detail: 'DETAIL-SCHEMA',
      sha256: 'a'.repeat(64),
      section_count: 1,
      category_count: 0,
      term_list_count: 0,
      term_count: 0,
      sections: [{ id: 'System', label: 'System', block: 'system', categories: [] }],
    },
  },
  proposal_sections: [{ id: 'System', label: 'System', block: 'system', term_lists: ['system.technique', 'system.domain'] }],
};

function drafted(section: string, category: string, term: string) {
  return {
    drafted: true,
    ready_to_send: false,
    missing: ['description'],
    problems: [],
    portal_payload: {
      portal: { method: 'POST', path: '/portal/api/vocabulary/proposals', rest_supported: true },
      body: { proposal_type: 'add_term', section, category, term, description: '' },
      sent_by_isaac: false,
      notes: ['ISAAC has not sent this. Someone with ISAAC portal access has to.'],
    },
  };
}

/** A drafts file in the shape `propose_terms.propose_terms` writes (format 1), synthetic values. */
const DRAFTS_FILE = {
  format: 'isaac.term-proposal-drafts',
  format_version: '1',
  notice: 'Draft proposals, written on this machine and sent nowhere.',
  sent_by_isaac: false,
  bundle_id: 'synthetic-bundle-0001',
  totals: { fields: 2, terms: 3, occurrences: 6, drafts: 2 },
  fields: [
    {
      field_path: 'system.technique',
      judged_by: { schema_enum: true, portal_list: true, portal_section: 'System' },
      occurrences: 4,
      terms: [
        {
          term: 'XMCD',
          count: 3,
          by_origin: { scientist_confirmed: 1, parser_reading: 0, ai_reading: 2 },
          missing_from: ['portal', 'schema'],
          citations: [
            { file: 'logs/synthetic_run_01.txt', locator: 'line 4', origin: 'scientist_confirmed', ref: { kind: 'candidate', id: 'c-1', run_id: 'run-01' } },
            { file: 'notes/synthetic.pdf', locator: 'page 2 (synthetic)', origin: 'ai_reading', ref: { kind: 'ai_interpretation', id: 'ai-1' } },
          ],
          citations_total: 2,
          citations_truncated: false,
          scientist_notes: [
            {
              term_as_said: 'XMCD',
              note: 'We logged it as XMCD on the synthetic beamline sheet.',
              by: 'Synthetic Scientist',
              when: '2026-10-30T12:00:00Z',
              source: { kind: 'decide_answer', said_in: 'an answer to isaac bundle decide', file: null },
              request_id: 'vr-00001',
            },
            // neither is shown as their words: a bare string, and a sentence ISAAC composed
            'A bare string nobody is named for.',
            { text: 'Synthetic Scientist, 2026-10-30, in an answer: "XMCD"' },
          ],
          draft: drafted('System', 'system.technique', 'XMCD'),
        },
        {
          term: 'magnetic dichroism',
          count: 1,
          by_origin: { scientist_confirmed: 0, parser_reading: 0, ai_reading: 1 },
          missing_from: ['portal', 'schema'],
          citations: [{ file: 'notes/synthetic.pdf', locator: 'page 3 (synthetic)', origin: 'ai_reading', ref: { kind: 'ai_interpretation', id: 'ai-2' } }],
          citations_total: 1,
          citations_truncated: false,
          draft: {
            drafted: false,
            reason: 'The ISAAC website would refuse this as a new term: A term is a single word with no spaces.',
            problems: [{ field: 'term', code: 'invalid_term', message: 'A term is a single word with no spaces.' }],
          },
        },
      ],
    },
    {
      field_path: 'system.domain',
      judged_by: { schema_enum: false, portal_list: true, portal_section: 'System' },
      occurrences: 2,
      terms: [
        {
          term: 'simulated',
          count: 2,
          by_origin: { scientist_confirmed: 0, parser_reading: 2, ai_reading: 0 },
          missing_from: ['portal'],
          citations: [],
          citations_total: 0,
          citations_truncated: false,
          draft: drafted('System', 'system.domain', 'simulated'),
        },
      ],
    },
  ],
  exposed_candidates: [],
};

function proposal(over: Partial<ApiSchemaProposal> = {}): ApiSchemaProposal {
  return {
    id: '01M61TASK3DFS5VX1C7X1RZJS5',
    proposal_type: 'add_term',
    section: 'System',
    category: 'system.technique',
    term: 'XMCD',
    description: 'X-ray magnetic circular dichroism, as the synthetic sheet logs it.',
    gate0: null,
    status: 'pending',
    proposed_by: null,
    attribution: 'unverified',
    proposed_at: '2026-10-30T17:53:37Z',
    withdrawn_at: null,
    schema_version: '1.05',
    sent_by_isaac: false,
    ...over,
  };
}

const ROUTE = ROUTES.schemaProposals;

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

function stub(post?: (body: Record<string, unknown>) => { status: number; body: unknown }) {
  const sent: Record<string, unknown>[] = [];
  const calls = stubFetchRoutes({
    'GET /api/schema-proposals/vocabulary': { body: vocabulary },
    'GET /api/schema-proposals': {
      body: { ...envelope, proposals: [], total: 0, limit: 25, offset: 0, next_offset: null, statuses: ['pending', 'withdrawn'], capacity: { pending: 0, max_pending: 50, max_withdrawn_kept: 500, scope: 'shared' } },
    },
    'POST /api/schema-proposals': (init) => {
      const body = JSON.parse(String(init?.body));
      sent.push(body);
      return post ? post(body) : { status: 201, body: { ...envelope, proposal: proposal(), ignored_fields: [] } };
    },
  });
  return { sent, calls };
}

function loader(): HTMLElement {
  return screen.getByRole('region', { name: 'Load drafts from a local import' });
}

async function chooseFile(content: string, name = 'drafts.json') {
  const input = await screen.findByLabelText('Drafts file (JSON)');
  const file = new File([content], name, { type: 'application/json' });
  fireEvent.change(input, { target: { files: [file] } });
}

/** Wait until the file has been read and its summary line shown. */
async function drafts(): Promise<HTMLElement> {
  return within(loader()).findByText(/Nothing was sent\.$/);
}

/** One group's list of terms, by its heading ("Needs Your Description (2)"). */
function groupList(title: RegExp): HTMLElement {
  return within(loader()).getByRole('list', { name: title });
}

/** The rows of one group's list (its own items, not the notes listed inside a row). */
function rowsOf(list: HTMLElement): HTMLElement[] {
  return Array.from(list.querySelectorAll<HTMLElement>(':scope > li'));
}

function draftItem(term: string): HTMLElement {
  const item = within(loader())
    .getAllByRole('listitem')
    .find((li) => within(li).queryByRole('heading', { level: 4, name: term }) !== null);
  if (!item) throw new Error(`no draft listed for ${term}`);
  return item;
}

/** DRAFTS_FILE plus a term answered since it was asked for and one no longer found in the bundle. */
const ANSWER_NOTE = 'Partly answered since it was asked for: an allowed value (`XAS`) now stands for 1 run(s).';
function fileWithEveryKind() {
  const file = structuredClone(DRAFTS_FILE);
  const terms = file.fields[0].terms as unknown as Record<string, unknown>[];
  terms.push({ ...structuredClone(file.fields[0].terms[0]), term: 'ZZANSWERED', scientist_notes: [],
    draft: { drafted: false, answered: true, answered_with: ['XAS'], partly_answered: ANSWER_NOTE,
      reason: 'Answered since it was asked for: SYN reason, so the term is not drafted.' } });
  terms.push({ ...structuredClone(file.fields[0].terms[0]), term: 'ZZGONE', carried_over: true, current: false, count: 0,
    // truncated, so the file states no run count and the "Runs: not stated" sentence follows the counts
    citations: [], citations_total: 0, citations_truncated: true, scientist_notes: [] });
  return file;
}

/** The note above the form that says it was opened on a local-import draft. */
function draftNote(): HTMLElement {
  const notes = within(screen.getByRole('tabpanel', { name: 'Propose a Change' }))
    .getAllByRole('note')
    .filter((n) => /local import/.test(n.textContent ?? ''));
  expect(notes).toHaveLength(1);
  return notes[0];
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Load drafts from a local import', () => {
  it('reads the file in the browser and lists every term, its field, counts, words and problems, sending nothing', async () => {
    const { calls, sent } = stub();
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(DRAFTS_FILE));
    await drafts();

    // The copy says where a saved proposal goes: this build talks to the local server.
    expect(within(loader()).getByText(/the ISAAC server running on this computer/)).toBeInTheDocument();
    expect(within(loader()).getByText(/Nothing leaves your computer/)).toBeInTheDocument();
    // The lead says what a term proposal is.
    expect(within(loader()).getByText(/add one word to one list of allowed values/)).toBeInTheDocument();

    const xmcd = draftItem('XMCD');
    expect(within(xmcd).getByText('system.technique')).toBeInTheDocument();
    expect(xmcd).toHaveTextContent('3 readings (1 confirmed by you, 2 AI readings)');
    // One citation names no run (an AI reading points at a question), so runs are not counted.
    expect(xmcd).toHaveTextContent('Runs: not stated in the file.');
    // Only their words are in quotation marks; who, when and where are outside them.
    expect(xmcd).toHaveTextContent(
      '“XMCD”, with the note “We logged it as XMCD on the synthetic beamline sheet.” (Synthetic Scientist, 2026-10-30, in an answer to isaac bundle decide)',
    );
    expect(xmcd).not.toHaveTextContent('A bare string nobody is named for.');
    expect(xmcd).not.toHaveTextContent('in an answer: "XMCD"');
    expect(xmcd).toHaveTextContent('logs/synthetic_run_01.txt · line 4 (confirmed by you)');
    // What it would add, in one sentence.
    expect(xmcd).toHaveTextContent(
      "Adds XMCD to system.technique, which is not on the portal's list or the ISAAC schema's list today.",
    );
    expect(within(xmcd).getByText('Needs your description')).toBeInTheDocument();
    expect(within(xmcd).getByRole('button', { name: 'Propose This Term' })).toBeInTheDocument();

    const simulated = draftItem('simulated');
    expect(simulated).toHaveTextContent('The file has none for this term.');
    expect(simulated).toHaveTextContent('The file cites nothing for this term.');

    // A term the file did not draft is shown with its own reason and cannot be filed.
    const phrase = draftItem('magnetic dichroism');
    expect(phrase).toHaveTextContent('Cannot be proposed from here.');
    expect(phrase).toHaveTextContent('A term is a single word with no spaces.');
    expect(within(phrase).getByText('Cannot be proposed')).toBeInTheDocument();
    expect(within(phrase).queryByRole('button')).toBeNull();

    expect(within(loader()).getByRole('status')).toHaveTextContent(
      'From the local import synthetic-bundle-0001: 2 need your description · 1 cannot be proposed. Nothing was sent.',
    );
    expect(calls.filter((c) => !c.startsWith('GET '))).toEqual([]);
    expect(sent).toEqual([]);
  });

  it('opens the form on a draft with the description empty and required, and sends nothing until Save', async () => {
    const { calls, sent } = stub();
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(DRAFTS_FILE));
    await drafts();
    fireEvent.click(within(draftItem('XMCD')).getByRole('button', { name: 'Propose This Term' }));

    const panel = screen.getByRole('tabpanel', { name: 'Propose a Change' });
    await waitFor(() => expect(within(panel).getByLabelText('Category')).toHaveValue('system.technique'));
    expect(within(panel).getByLabelText('Section')).toHaveValue('System');
    expect(within(panel).getByLabelText('New term')).toHaveValue('XMCD');
    const description = within(panel).getByLabelText('Description (required)');
    expect(description).toHaveValue('');
    expect(description).toHaveAttribute('aria-required', 'true');
    await waitFor(() => expect(description).toHaveFocus());

    // The reviewer notes are the file's citations and counts, and nothing it does not say.
    expect(within(panel).getByLabelText('Examples (required)')).toHaveValue(
      'logs/synthetic_run_01.txt · line 4 (confirmed by you)\nnotes/synthetic.pdf · page 2 (synthetic) (AI reading)',
    );
    expect(within(panel).getByLabelText('Records affected (estimate) (required)')).toHaveValue(
      '3 readings (1 confirmed by you, 2 AI readings)',
    );
    expect(within(panel).getByLabelText('What would change')).toHaveValue('');
    expect(draftNote()).toHaveTextContent(/The description is left to you, and it is empty/);

    // Nothing was sent by loading the file or opening the draft.
    expect(calls.filter((c) => !c.startsWith('GET '))).toEqual([]);
    expect(sent).toEqual([]);

    fireEvent.change(description, { target: { value: 'X-ray magnetic circular dichroism, as the synthetic sheet logs it.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    await screen.findByText(/Saved as a draft on this server/);
    expect(sent).toHaveLength(1);
    expect(sent[0]).toEqual({
      proposal_type: 'add_term',
      section: 'System',
      category: 'system.technique',
      term: 'XMCD',
      description: 'X-ray magnetic circular dichroism, as the synthetic sheet logs it.',
      gate0: {
        problem:
          '"XMCD" was read 3 times for system.technique in the local import synthetic-bundle-0001, and it is not on the portal\'s list or the ISAAC schema\'s list.',
        examples:
          'logs/synthetic_run_01.txt · line 4 (confirmed by you)\nnotes/synthetic.pdf · page 2 (synthetic) (AI reading)',
        affected_records_estimate: '3 readings (1 confirmed by you, 2 AI readings)',
      },
      source: {
        kind: 'local_import',
        format: 'isaac.term-proposal-drafts',
        bundle_id: 'synthetic-bundle-0001',
        field_path: 'system.technique',
        term: 'XMCD',
        occurrences: 3,
        citations_total: 2,
      },
    });
  });

  it('a description left empty is refused by the server and shown beside the box', async () => {
    const { sent } = stub(() => ({
      status: 422,
      body: {
        error: 'description_required',
        message: 'The proposal needs a few changes before it can be saved.',
        errors: [{ field: 'description', code: 'description_required', message: 'SERVER: Description is required.' }],
      },
    }));
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(DRAFTS_FILE));
    await drafts();
    fireEvent.click(within(draftItem('XMCD')).getByRole('button', { name: 'Propose This Term' }));
    await waitFor(() => expect(screen.getByLabelText('New term')).toHaveValue('XMCD'));
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    const error = await screen.findByText('SERVER: Description is required.');
    const description = screen.getByLabelText('Description (required)');
    expect(description).toHaveAttribute('aria-invalid', 'true');
    expect(description.getAttribute('aria-describedby')).toContain(error.id);
    expect(sent[0].description).toBe('');
    expect(screen.queryByText(/Saved as a draft/)).toBeNull();
    // The draft is still open, so a second try still carries its source.
    expect(draftNote()).toHaveTextContent('Proposing: add XMCD to system.technique (System)');
  });

  it('a reviewer note the file has no fact for is empty, named as missing, and required', async () => {
    stub();
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(DRAFTS_FILE));
    await drafts();
    fireEvent.click(within(draftItem('simulated')).getByRole('button', { name: 'Propose This Term' }));
    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('system.domain'));
    const examples = screen.getByLabelText('Examples (required)');
    expect(examples).toHaveValue('');
    expect(examples).toHaveAttribute('aria-required', 'true');
    expect(draftNote()).toHaveTextContent('The file has nothing for Examples');
  });

  it('Stop Using This Draft sends a plain proposal, with no source', async () => {
    const { sent } = stub();
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(DRAFTS_FILE));
    await drafts();
    fireEvent.click(within(draftItem('XMCD')).getByRole('button', { name: 'Propose This Term' }));
    await waitFor(() => expect(screen.getByLabelText('New term')).toHaveValue('XMCD'));
    fireEvent.click(screen.getByRole('button', { name: 'Stop Using This Draft' }));
    fireEvent.change(screen.getByLabelText('Description (required)'), {
      target: { value: 'X-ray magnetic circular dichroism, typed by hand here.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Proposal' }));
    await screen.findByText(/Saved as a draft on this server/);
    expect(sent[0]).not.toHaveProperty('source');
  });

  it('a file that is not a drafts file is refused in words, and nothing is listed or sent', async () => {
    const { calls } = stub();
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify({ format: 'isaac.something-else', fields: [] }), 'other.json');
    expect(await within(loader()).findByRole('alert')).toHaveTextContent('not a drafts file');
    expect(within(loader()).queryByRole('list')).toBeNull();
    await chooseFile('not json at all', 'broken.json');
    await waitFor(() => expect(within(loader()).getByRole('alert')).toHaveTextContent('not JSON'));
    expect(calls.filter((c) => !c.startsWith('GET '))).toEqual([]);
  });

  it('a draft the server vocabulary would now refuse is listed and cannot be filed', async () => {
    stub();
    const file = structuredClone(DRAFTS_FILE);
    file.fields[0].terms[0].term = 'XAS';
    file.fields[0].terms[0].draft = drafted('System', 'system.technique', 'XAS');
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(file));
    await drafts();
    const item = draftItem('XAS');
    expect(item).toHaveTextContent('Cannot be proposed from here.');
    expect(within(item).queryByRole('button')).toBeNull();
  });

  it('a term carried over from an earlier file is no longer found in the bundle and cannot be filed', async () => {
    const { calls } = stub();
    const file = structuredClone(DRAFTS_FILE);
    Object.assign(file.fields[0].terms[0] as Record<string, unknown>, {
      carried_over: true,
      current: false,
      count: 0,
      by_origin: { scientist_confirmed: 0, parser_reading: 0, ai_reading: 0, scientist_request: 0 },
      runs: 0,
      scientist_notes: [],
      citations: [],
    });
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(file));
    await drafts();
    const item = draftItem('XMCD');
    expect(item).toHaveTextContent('Cannot be proposed from here.');
    expect(item).toHaveTextContent('no longer found in the bundle');
    expect(within(item).getByText('No longer in the bundle')).toBeInTheDocument();
    expect(rowsOf(groupList(/^Nothing Needed From You/))).toContain(item);
    expect(within(item).queryByRole('button')).toBeNull();
    expect(calls.filter((c) => !c.startsWith('GET '))).toEqual([]);
  });

  it("shows the file's own sentences on what was answered since, and an answered term cannot be filed", async () => {
    const { calls } = stub();
    const file = structuredClone(DRAFTS_FILE);
    const xmcd = file.fields[0].terms[0] as Record<string, unknown>;
    const partly = 'Partly answered since it was asked for: an allowed value (`XAS`) now stands for 1 run(s).';
    const early = '1 run(s) already held `XAS` before the word was asked for; ask the scientist whether they still want the term.';
    xmcd.draft = { ...(xmcd.draft as Record<string, unknown>), partly_answered: partly, answered_before_request: true,
      answered_before_request_note: early };
    (file.fields[0].terms as unknown as Record<string, unknown>[]).push({ ...structuredClone(file.fields[0].terms[0]), term: 'ZZANSWERED',
      draft: { drafted: false, answered: true, answered_with: ['XAS'],
        reason: 'Answered since it was asked for: SYN reason, so the term is not drafted.' } });
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(file));
    await drafts();
    const item = draftItem('XMCD');
    expect(item).toHaveTextContent('Since it was asked for');
    // the file's own sentences, word for word; a backticked value is shown as code, not as backticks
    expect(item).toHaveTextContent(partly.replace(/`/g, ''));
    expect(item).toHaveTextContent(early.replace(/`/g, ''));
    expect(within(item).getAllByText('XAS', { selector: 'code' })).toHaveLength(2);
    expect(item.textContent).not.toContain('`');
    const answered = draftItem('ZZANSWERED');
    expect(rowsOf(groupList(/^Nothing Needed From You/))).toContain(answered);
    expect(answered).toHaveTextContent('Cannot be proposed from here.');
    expect(answered).toHaveTextContent('so the term is not drafted');
    expect(within(answered).queryByRole('button')).toBeNull();
    expect(calls.filter((c) => !c.startsWith('GET '))).toEqual([]);
  });
});

describe('an answered term', () => {
  it('is refused with its own reason even when the file also says drafted and carries a body', async () => {
    const { calls } = stub();
    const file = structuredClone(DRAFTS_FILE);
    const xmcd = file.fields[0].terms[0] as Record<string, unknown>;
    xmcd.draft = { ...(xmcd.draft as Record<string, unknown>), drafted: true, answered: true,
      reason: 'Answered since it was asked for: SYN reason, so the term is not drafted.' };
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(file));
    await drafts();
    const item = draftItem('XMCD');
    expect(item).toHaveTextContent('Cannot be proposed from here.');
    expect(item).toHaveTextContent('SYN reason, so the term is not drafted.');
    expect(within(item).queryByRole('button', { name: 'Propose This Term' })).toBeNull();
    expect(calls.filter((c) => !c.startsWith('GET '))).toEqual([]);
  });
});

describe('the drafts, grouped', () => {
  it('lists the terms in three groups, in order, with counts the summary line repeats', async () => {
    const { calls } = stub();
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(fileWithEveryKind()));
    await drafts();
    const headings = within(loader()).getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(['Needs Your Description (2)', 'Cannot Be Proposed From Here (1)', 'Nothing Needed From You (2)']);
    const terms = (title: RegExp) =>
      rowsOf(groupList(title)).map((li) => within(li).getByRole('heading', { level: 4 }).textContent);
    expect(terms(/^Needs Your Description/)).toEqual(['XMCD', 'simulated']);
    expect(terms(/^Cannot Be Proposed From Here/)).toEqual(['magnetic dichroism']);
    expect(terms(/^Nothing Needed From You/)).toEqual(['ZZANSWERED', 'ZZGONE']);
    // A carried-over term's counts sentence has its own full stop, so none is added before "Runs".
    expect(draftItem('ZZGONE')).toHaveTextContent('No longer found in the bundle (carried over from an earlier drafts file).');
    expect(draftItem('ZZGONE')).toHaveTextContent('earlier drafts file). Runs: not stated in the file.');
    expect(draftItem('ZZGONE').textContent).not.toContain('..');
    expect(within(loader()).getByRole('status')).toHaveTextContent(
      'From the local import synthetic-bundle-0001: 2 need your description · 1 cannot be proposed · 2 need nothing from you. Nothing was sent.',
    );
    // Only the first group's rows can be opened.
    expect(within(loader()).getAllByRole('button', { name: 'Propose This Term' })).toHaveLength(2);
    expect(within(groupList(/^Cannot Be Proposed/)).queryByRole('button')).toBeNull();
    expect(within(groupList(/^Nothing Needed/)).queryByRole('button')).toBeNull();
    expect(calls.filter((c) => !c.startsWith('GET '))).toEqual([]);
  });

  it('leaves out a group with no terms, and the summary says only what is listed', async () => {
    stub();
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(DRAFTS_FILE));
    await drafts();
    expect(within(loader()).queryByRole('heading', { name: /^Nothing Needed From You/ })).toBeNull();
    expect(within(loader()).getByRole('status')).not.toHaveTextContent('nothing from you');
  });

  it('an answered term is listed only under Nothing Needed From You, with the file\'s sentences and no button', async () => {
    stub();
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(fileWithEveryKind()));
    await drafts();
    const answered = draftItem('ZZANSWERED');
    expect(rowsOf(groupList(/^Nothing Needed From You/))).toContain(answered);
    expect(rowsOf(groupList(/^Needs Your Description/))).not.toContain(answered);
    expect(rowsOf(groupList(/^Cannot Be Proposed From Here/))).not.toContain(answered);
    expect(within(answered).getByText('Answered')).toBeInTheDocument();
    expect(answered).toHaveTextContent('Since it was asked for');
    expect(answered).toHaveTextContent(ANSWER_NOTE.replace(/`/g, ''));
    expect(within(answered).getByText('XAS', { selector: 'code' })).toBeInTheDocument();
    expect(answered).toHaveTextContent('Cannot be proposed from here.');
    expect(within(answered).queryByRole('button')).toBeNull();
  });

  it('folds where a term was read under "Where it was read (N)", N being the file\'s own total', async () => {
    stub();
    const file = structuredClone(DRAFTS_FILE);
    file.fields[0].terms[0].citations_total = 40;
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(file));
    await drafts();
    const xmcd = draftItem('XMCD');
    const summary = within(xmcd).getByText('Where it was read (40)');
    const details = summary.closest('details')!;
    expect(details).not.toHaveAttribute('open');
    expect(details).toHaveTextContent('logs/synthetic_run_01.txt · line 4 (confirmed by you)');
    expect(details).toHaveTextContent('and 38 more');
    // A term the file cites nothing for says so in plain sight, with nothing to unfold.
    const simulated = draftItem('simulated');
    expect(simulated.querySelector('details')).toBeNull();
    expect(simulated).toHaveTextContent('The file cites nothing for this term.');
  });

  it('marks the row the form is open on, names it above the form, and moves the mark to the next draft opened', async () => {
    const { calls, sent } = stub();
    renderAt(`${ROUTE}?tab=propose`);
    await chooseFile(JSON.stringify(DRAFTS_FILE));
    await drafts();
    expect(within(loader()).queryByText('Being proposed below')).toBeNull();

    fireEvent.click(within(draftItem('XMCD')).getByRole('button', { name: 'Propose This Term' }));
    await waitFor(() => expect(draftItem('XMCD')).toHaveAttribute('aria-current', 'true'));
    expect(within(draftItem('XMCD')).getByText('Being proposed below')).toBeInTheDocument();
    expect(within(draftItem('XMCD')).queryByRole('button', { name: 'Propose This Term' })).toBeNull();
    expect(draftItem('simulated')).not.toHaveAttribute('aria-current');
    expect(draftNote()).toHaveTextContent('Proposing: add XMCD to system.technique (System)');
    expect(draftNote()).toHaveTextContent('at least 20 characters');
    expect(draftNote()).toHaveTextContent('synthetic-bundle-0001');
    // What Save does is said once, above it.
    expect(screen.getByRole('button', { name: 'Save Proposal' })).toHaveAccessibleDescription(
      'Save keeps this proposal as a draft on this server. It does not send it to the ISAAC portal.',
    );

    fireEvent.click(within(draftItem('simulated')).getByRole('button', { name: 'Propose This Term' }));
    await waitFor(() => expect(draftItem('simulated')).toHaveAttribute('aria-current', 'true'));
    expect(draftItem('XMCD')).not.toHaveAttribute('aria-current');
    expect(within(draftItem('XMCD')).getByRole('button', { name: 'Propose This Term' })).toBeInTheDocument();
    expect(within(loader()).getAllByText('Being proposed below')).toHaveLength(1);
    expect(draftNote()).toHaveTextContent('Proposing: add simulated to system.domain (System)');

    // Stopping the draft clears the mark.
    fireEvent.click(screen.getByRole('button', { name: 'Stop Using This Draft' }));
    expect(draftItem('simulated')).not.toHaveAttribute('aria-current');
    expect(within(loader()).queryByText('Being proposed below')).toBeNull();
    expect(calls.filter((c) => !c.startsWith('GET '))).toEqual([]);
    expect(sent).toEqual([]);
  });
});

describe('termDrafts', () => {
  it("reads the draft's answered-since sentences as the file wrote them, in order, and nothing else", () => {
    const file = structuredClone(DRAFTS_FILE);
    const xmcd = file.fields[0].terms[0] as Record<string, unknown>;
    xmcd.draft = { ...(xmcd.draft as Record<string, unknown>), runs_in_no_live_group_note: 'SYN outside.',
      partly_answered: 'SYN partly.', answered_before_request_note: '  ', answered: 'yes',
      earlier_requests_answered_note: 'SYN earlier request answered.' };
    const parsed = parseTermDraftsFile(JSON.stringify(file));
    if (!parsed.ok) throw new Error(parsed.message);
    expect(parsed.file.drafts[0].answerNotes).toEqual(['SYN partly.', 'SYN earlier request answered.', 'SYN outside.']);
    expect(parsed.file.drafts[0].answered).toBe(false); // only `true` is read as answered
  });

  it('counts runs only when every citation names one and none were left out', () => {
    const file = structuredClone(DRAFTS_FILE);
    const xmcd = file.fields[0].terms[0];
    xmcd.citations = [xmcd.citations[0], { ...xmcd.citations[0], locator: 'line 9', ref: { kind: 'candidate', id: 'c-2', run_id: 'run-02' } }];
    let parsed = parseTermDraftsFile(JSON.stringify(file));
    expect(parsed.ok && parsed.file.drafts[0].runs).toBe(2);
    xmcd.citations_truncated = true;
    parsed = parseTermDraftsFile(JSON.stringify(file));
    expect(parsed.ok && parsed.file.drafts[0].runs).toBeNull();
    // The file's own count wins when it has one.
    (xmcd as Record<string, unknown>).runs = 7;
    parsed = parseTermDraftsFile(JSON.stringify(file));
    expect(parsed.ok && parsed.file.drafts[0].runs).toBe(7);
  });

  it('keeps the citations within the examples limit and says how many more the file has', () => {
    const parsed = parseTermDraftsFile(JSON.stringify(DRAFTS_FILE));
    if (!parsed.ok) throw new Error(parsed.message);
    const d = { ...parsed.file.drafts[0], citationsTotal: 40 };
    const { gate0 } = gate0FromDraft(d, null, { ...limits, examples_max: 120 });
    expect(gate0.examples!.length).toBeLessThanOrEqual(120);
    expect(gate0.examples).toMatch(/and \d+ more in the drafts file$/);
  });

  it('counts a vocabulary request as asked by the scientist, never as a reading', () => {
    const file = structuredClone(DRAFTS_FILE);
    const xmcd = file.fields[0].terms[0] as Record<string, unknown>;
    xmcd.count = 2;
    xmcd.by_origin = { scientist_confirmed: 0, parser_reading: 0, ai_reading: 0, scientist_request: 2 };
    xmcd.runs = 2;
    const parsed = parseTermDraftsFile(JSON.stringify(file));
    if (!parsed.ok) throw new Error(parsed.message);
    const d = parsed.file.drafts[0];
    expect(countsSentence(d)).toBe('asked by the scientist (2) in 2 runs');
    const { gate0 } = gate0FromDraft(d, null, limits);
    expect(gate0.problem).toContain('"XMCD" was asked for by the scientist 2 times for system.technique');
    expect(gate0.problem).not.toContain('was read');
    // beside readings, both are said apart
    xmcd.count = 3;
    xmcd.by_origin = { scientist_confirmed: 0, parser_reading: 0, ai_reading: 1, scientist_request: 2 };
    const both = parseTermDraftsFile(JSON.stringify(file));
    if (!both.ok) throw new Error(both.message);
    expect(countsSentence(both.file.drafts[0])).toBe('1 reading (1 AI reading); asked by the scientist (2) in 2 runs');
  });

  it('refuses another format version rather than guessing at it', () => {
    const parsed = parseTermDraftsFile(JSON.stringify({ ...DRAFTS_FILE, format_version: '2' }));
    expect(parsed.ok).toBe(false);
  });
});

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { stubFetchRoutes, type RouteEntry } from '../test/apiFixtures';
import {
  LOCAL_IMPORTS_COPY as COPY,
  __resetLocalImportsAvailability,
  sectionQuestions,
  type ApiLocalBundleList,
  type ApiLocalBundleProgress,
  type ApiLocalQuestions,
  type LocalQuestion,
} from '../lib/localImports';

/**
 * Local Imports — the local-only questions screen and progress overview. SYNTHETIC
 * fixtures only (names and values invented for these tests). Pinned by behaviour:
 *
 *   · absent from navigation in a hosted-like build (flag unset) and when the server does
 *     not serve local bundles, and in the first case no request is made at all;
 *   · every suggestion is labelled not confirmed; a hint cannot be accepted;
 *   · the answer control fits the question (a select for a closed list, a number with its
 *     unit, an IANA zone, element + edge, counter positions);
 *   · "same for all" previews exactly the targets the server says it would write, and only
 *     "Write these answers" writes, against the version the preview was read at;
 *   · after a write the questions are read again from the server; a 412 says nothing was
 *     written and reads them again.
 */

const VERSION = 'sha256:' + 'a'.repeat(64);
const VERSION_2 = 'sha256:' + 'b'.repeat(64);

const header = {
  name: 'synthetic-beamtime',
  source_label: 'SYN_2099_beamtime',
  source_kind: 'folder',
  format_version: '1.6.0',
  bundle_id: 'SYNTHETIC',
  beamline: [{ value: 'SYN-1', basis: 'candidate_extracted' }],
  bundle_version: VERSION,
  modified_utc: '2099-01-01T00:00:00Z',
};

function display(over: Partial<LocalQuestion['display']> = {}): LocalQuestion['display'] {
  return {
    folder: 'synthetic-beamtime',
    beamtime: 'SYN_2099_beamtime',
    beamline: header.beamline,
    answer_kind: 'field_value',
    settles_many: false,
    scopes: [],
    record_run_names: [],
    targets_described: 0,
    targets_total: 0,
    suggestions_differ: false,
    suggestions: [],
    suggestions_total: 0,
    distinct_extracted_values: [],
    field_suggestions: {},
    value_rule: null,
    fields: {},
    suggested_absorber: null,
    suggestion_statement: 'A suggestion is NOT confirmed: nothing is recorded until you answer.',
    ...over,
  };
}

function question(over: Partial<LocalQuestion> & { display?: LocalQuestion['display'] }): LocalQuestion {
  return {
    question_id: 'Q-0000000000',
    tier: 1,
    blocking: true,
    why: 'WHY-SAID-BY-SERVER',
    kind: 'missing_value',
    scope: 'experiment',
    target_field_path: 'context.environment',
    text: 'What is the environment?',
    applies_to: { groups: 2, runs: 2, targets: 2 },
    targets: [],
    per_scope_targets: {},
    allowed_values: null,
    allowed_decisions: ['confirm', 'correct', 'reject', 'defer'],
    answer_command: 'isaac bundle decide <bundle_dir> --question Q-0000000000 --decision correct --value <value> --by "<your name>"',
    display: display(),
    ...over,
  };
}

const MIXED_E1 = {
  value: 'in_situ', who: 'parser' as const, who_label: "Read from the file by ISAAC's parser", model_id: null,
  relative_path: 'SYN_run_E1.dat', locator: 'line 3', quote: 'SYNTHETIC E1 in situ', confirmed: false as const, targets: 1,
  from_own_files: true, provenance_label: "This group's own files",
};
const MIXED_E2 = { ...MIXED_E1, value: 'ex_situ', relative_path: 'SYN_run_E2.dat', quote: 'SYNTHETIC E2 ex situ' };

const envQ = question({
  question_id: 'Q-env0000001',
  text: 'What is the environment (context.environment)? Applies to 2 group(s) — answer once, or per group.',
  targets: [
    { kind: 'missing_value', id: 'miss-0001' },
    { kind: 'missing_value', id: 'miss-0002' },
  ],
  per_scope_targets: {
    'group:g1': ['miss-0001'], 'group:g2': ['miss-0002'], 'group:g3': ['miss-0003'], 'group:g4': ['miss-0004'],
    'group:g5': ['miss-0005', 'miss-0006'],
  },
  allowed_values: ['operando', 'in_situ', 'ex_situ'],
  display: display({
    settles_many: true,
    suggestions_differ: true,
    targets_described: 2,
    targets_total: 2,
    scopes: [
      {
        scope: 'group:g1', kind: 'group', group_id: 'g1', label: 'Record group g1', target_count: 1, run_names: ['SYN_run_A'], run_count: 1,
        own_suggestions: [{ value: 'ex_situ', who: 'ai_reading', who_label: 'Suggested by an AI reading of the files', model_id: 'synthetic-model',
          relative_path: 'notes/SYN_log.txt', locator: 'line 4', quote: 'SYNTHETIC QUOTE measured ex situ', confirmed: false, targets: 1,
          from_own_files: true, provenance_label: "This group's own files" }],
        own_suggestions_total: 1, mixed: false, has_unanimous_value: true, unanimous_from_own_files: true, unanimous_value: 'ex_situ',
      },
      {
        scope: 'group:g2', kind: 'group', group_id: 'g2', label: 'Record group g2', target_count: 1, run_names: ['SYN_run_B'], run_count: 1,
        own_suggestions: [{ value: 'in_situ', who: 'parser', who_label: "Read from the file by ISAAC's parser", model_id: null,
          relative_path: 'SYN_run_B.dat', locator: 'header line 2', quote: 'SYNTHETIC in situ cell', confirmed: false, targets: 1,
          from_own_files: true, provenance_label: "This group's own files" }],
        own_suggestions_total: 1, mixed: false, has_unanimous_value: true, unanimous_from_own_files: true, unanimous_value: 'in_situ',
      },
      {
        scope: 'group:g3', kind: 'group', group_id: 'g3', label: 'Record group g3', target_count: 1, run_names: ['SYN_run_C'], run_count: 1,
        own_suggestions: [{ value: 'in_situ', who: 'ai_reading', who_label: 'Suggested by an AI reading of the files', model_id: 'synthetic-model',
          relative_path: 'SYN_run_B.dat', locator: 'line 10', quote: 'SYNTHETIC names run C', confirmed: false, targets: 1,
          from_own_files: false, provenance_label: "A reading for this group's runs, quoted from a file that is not one of its runs (SYN_run_B.dat)" }],
        own_suggestions_total: 1, mixed: false, has_unanimous_value: true, unanimous_value: 'in_situ', unanimous_from_own_files: false,
      },
      {
        scope: 'group:g4', kind: 'group', group_id: 'g4', label: 'Record group g4', target_count: 1, run_names: ['SYN_run_D'], run_count: 1,
        own_suggestions: [], own_suggestions_total: 0, mixed: false, has_unanimous_value: false, unanimous_from_own_files: false,
      },
      {
        scope: 'group:g5', kind: 'group', group_id: 'g5', label: 'Record group g5', target_count: 2, run_names: ['SYN_run_E1', 'SYN_run_E2'], run_count: 2,
        own_suggestions: [MIXED_E1, MIXED_E2], own_suggestions_total: 2,
        mixed: true, has_unanimous_value: false, unanimous_from_own_files: false,
        per_target: [
          { target_id: 'miss-0005', run_id: 'run-E1', run_name: 'SYN_run_E1', own_suggestions: [MIXED_E1] },
          { target_id: 'miss-0006', run_id: 'run-E2', run_name: 'SYN_run_E2', own_suggestions: [MIXED_E2] },
        ],
      },
    ],
    record_run_names: ['SYN_run_A', 'SYN_run_B'],
    suggestions: [
      {
        who: 'ai_reading', who_label: 'Suggested by an AI reading of the files', hint_kind: 'ai_suggestion', value: 'ex_situ',
        relative_path: 'notes/SYN_log.txt', locator: 'line 4', quote: 'SYNTHETIC QUOTE measured ex situ', model_id: 'synthetic-model',
        field: null, note: null, acceptable: true, confirmed: false, targets: 2,
      },
      {
        who: 'hint', who_label: 'A hint about what is asked, never an answer', hint_kind: 'folder_name', value: 'SYN_2099_beamtime',
        relative_path: null, locator: "the imported folder's name", quote: null, model_id: null, field: null,
        note: 'A folder name is a HINT, never an answer.', acceptable: false, confirmed: false,
      },
    ],
    value_rule: { allowed: ['operando', 'in_situ', 'ex_situ'], numeric: false, integer: false, in_schema: true, unit: null },
  }),
});

const tempQ = question({
  question_id: 'Q-temp000001',
  kind: 'optional_values',
  blocking: false,
  tier: 3,
  scope: 'group:g1',
  target_field_path: null,
  text: '1 optional field(s) no parser read a value for: context.temperature_K.',
  targets: [{ kind: 'missing_value', id: 'miss-0100' }],
  per_scope_targets: { 'group:g1': ['miss-0100'] },
  fields: { 'context.temperature_K': ['miss-0100'] },
  display: display({
    answer_kind: 'optional_values',
    scopes: [{ scope: 'group:g1', kind: 'group', group_id: 'g1', label: 'Record group g1', target_count: 1, run_names: ['SYN_run_A'] }],
    fields: { 'context.temperature_K': { allowed: null, numeric: true, integer: false, in_schema: true, unit: 'K', target_count: 1 } },
  }),
});

const zoneQ = question({
  question_id: 'Q-zone000001',
  kind: 'clock_time_zone',
  blocking: false,
  tier: 3,
  target_field_path: 'timestamps.acquired_start_utc',
  text: 'Which time zone was the instrument clock set to?',
  targets: [{ kind: 'experiment', id: 'experiment' }],
  per_scope_targets: { experiment: ['experiment'] },
  allowed_decisions: ['set_clock_time_zone'],
  display: display({ answer_kind: 'clock_zone', settles_many: true }),
});

const absorberQ = question({
  question_id: 'Q-abs0000001',
  kind: 'confirm_absorber',
  blocking: false,
  tier: 3,
  scope: 'group:g2',
  target_field_path: null,
  text: 'Which is the absorber of this group?',
  targets: [{ kind: 'record_group', id: 'g2' }],
  per_scope_targets: { 'group:g2': ['g2'] },
  allowed_decisions: ['set_absorber', 'defer'],
  display: display({
    answer_kind: 'absorber',
    scopes: [{ scope: 'group:g2', kind: 'group', group_id: 'g2', label: 'Record group g2', target_count: 1, run_names: ['SYN_run_B'] }],
    suggested_absorber: { element: 'Zz', edge: 'K', basis: 'stated in the files (not confirmed)' },
  }),
});

const counterQ = question({
  question_id: 'Q-count00001',
  kind: 'naming_counter_positions',
  blocking: false,
  tier: 2,
  target_field_path: null,
  text: 'Which filename positions are run counters?',
  positions: [2, 3],
  targets: [{ kind: 'experiment', id: 'experiment' }],
  per_scope_targets: { experiment: ['experiment'] },
  allowed_decisions: ['set_counter_positions', 'set_not_counter_positions'],
  display: display({ answer_kind: 'counter_positions', settles_many: true }),
});

function questionsBody(qs: LocalQuestion[], version = VERSION): ApiLocalQuestions {
  return {
    bundle: { ...header, bundle_version: version },
    counts: { total: qs.length, blocking: qs.filter((q) => q.blocking).length, conflicts_affecting_a_record: 0, optional: qs.filter((q) => !q.blocking).length },
    blocking_basis: { schema: 'vendored v1.05', source: 'schema/isaac_record_v1.json', commit: null },
    total: qs.length,
    offset: 0,
    limit: 200,
    returned: qs.length,
    omitted_before: 0,
    omitted_after: 0,
    minimum_for_one_group: null,
    questions: qs,
    capture: { merge_candidates: [], athena_selections: [] },
    exposures_recorded: 0,
    identity: 'local_unverified',
    statement: 'SERVER-SAID: answers stay on this computer.',
  };
}

const listBody: ApiLocalBundleList = {
  local_only: true,
  directory_name: 'synthetic-bundles',
  not_bundles: 0,
  statement: 'SERVER-SAID: nothing is uploaded.',
  bundles: [
    {
      ...header,
      check: { status: 'STALE', errors: [], error_count: 0, stale_values: 3, statement: 'SERVER-SAID: stored by an older build.' },
      counts: { runs: 2 },
      record_groups: 2,
      scientist_decisions: 0,
      readiness: { stage: 'extracted', eligible_value_count: 0, blocking: null },
    },
  ],
};

const progressBody: ApiLocalBundleProgress = {
  bundle: header,
  progress: {
    check: listBody.bundles[0].check,
    runs: 2,
    run_candidates: 2,
    record_groups: { total: 2, by_status: { proposed: 2 } },
    processing_results: { total: 0, by_state: {} },
    scientist_decisions: 0,
    values: {},
    readiness: { stage: 'extracted', eligible_value_count: 0, blocking: null, official_record_ready: false },
    missing_share: null,
    missing_share_statement: 'SERVER-SAID: no missing share is computed.',
    questions: { total: 5, blocking: 1, conflicts_affecting_a_record: 0, optional: 4 },
    minimum_for_one_group: null,
    blocks_export: ['SERVER-SAID: 1 blocking question(s) are open.'],
    last_validation: { reports: [], statement: '' },
  },
};

const QPATH = '/api/local-bundles/synthetic-beamtime/questions';
const APATH = (id: string) => `POST /api/local-bundles/synthetic-beamtime/questions/${id}/answer`;

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

function bodyOf(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
}

beforeEach(() => {
  __resetLocalImportsAvailability();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('the destination is absent unless this is a local build on a server that serves it', () => {
  it('in a build without the local flag: no nav item, and no request is made', async () => {
    const calls = stubFetchRoutes({});
    renderAt(ROUTES.experiments);
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    await waitFor(() => expect(within(nav).getByRole('link', { name: LABELS.navExperiments })).toBeInTheDocument());
    expect(within(nav).queryByRole('link', { name: LABELS.navLocalImports })).toBeNull();
    expect(calls.filter((c) => c.includes('local-bundles'))).toEqual([]);
  });

  it('the page itself, reached by address in such a build, says so and asks nothing', () => {
    const calls = stubFetchRoutes({});
    renderAt(ROUTES.localImports);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(LABELS.navLocalImports);
    expect(screen.getByText(COPY.notInThisBuild)).toBeInTheDocument();
    expect(calls.filter((c) => c.includes('local-bundles'))).toEqual([]);
  });

  it('in a local build whose server does not serve local bundles: no nav item', async () => {
    vi.stubEnv('VITE_ISAAC_LOCAL_IMPORTS', '1');
    const calls = stubFetchRoutes({ 'GET /api/local-bundles': { status: 404, body: { detail: 'Not Found' } } });
    renderAt(ROUTES.localImports);
    expect(await screen.findByText(COPY.notOnThisServer)).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(within(nav).queryByRole('link', { name: LABELS.navLocalImports })).toBeNull();
    expect(calls.filter((c) => c === 'GET /api/local-bundles').length).toBeGreaterThan(0);
  });

  it('with both: the nav item appears after Historical Import and the overview shows progress', async () => {
    vi.stubEnv('VITE_ISAAC_LOCAL_IMPORTS', '1');
    stubFetchRoutes({
      'GET /api/local-bundles': { body: listBody },
      'GET /api/local-bundles/synthetic-beamtime/progress': { body: progressBody },
    });
    renderAt(ROUTES.localImports);
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    const link = await within(nav).findByRole('link', { name: LABELS.navLocalImports });
    expect(link).toHaveAttribute('aria-current', 'page');
    const labels = within(nav).getAllByRole('link').map((a) => a.textContent);
    expect(labels.indexOf(LABELS.navLocalImports)).toBe(labels.indexOf(LABELS.navImports) + 1);
    expect(await screen.findByText('SERVER-SAID: 1 blocking question(s) are open.')).toBeInTheDocument();
    expect(screen.getByText('STALE')).toBeInTheDocument();
    expect(screen.getByText('SYN_2099_beamtime')).toBeInTheDocument();
    expect(screen.getByText('SERVER-SAID: no missing share is computed.')).toBeInTheDocument();
  });
});

describe('the questions screen', () => {
  function stubQuestions(extra: Record<string, RouteEntry> = {}, qs: LocalQuestion[] = [envQ, tempQ, zoneQ, absorberQ, counterQ]) {
    vi.stubEnv('VITE_ISAAC_LOCAL_IMPORTS', '1');
    return stubFetchRoutes({
      'GET /api/local-bundles': { body: listBody },
      [`GET ${QPATH}`]: { body: questionsBody(qs) },
      ...extra,
    });
  }

  it('groups the questions: one-answer-settles-many first, then by type, blocking first', () => {
    const sections = sectionQuestions([tempQ, absorberQ, envQ, zoneQ]);
    expect(sections.map((s) => s.id)).toEqual(['settles-many', 'kind-confirm_absorber', 'kind-optional_values']);
    expect(sections[0].questions.map((q) => q.question_id)).toEqual([envQ.question_id, zoneQ.question_id]);
  });

  it('shows the fields a scientist needs, with every suggestion marked not confirmed', async () => {
    stubQuestions();
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const card = (await screen.findByRole('heading', { name: envQ.text })).closest('li') as HTMLElement;
    const c = within(card);
    // beamline, beamtime and folder are said ONCE, in the bundle header, not on every card
    expect(screen.getByText('SYN-1 (candidate_extracted)', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.getByText('SYN_2099_beamtime', { selector: 'dd' })).toBeInTheDocument();
    expect(c.queryByText('Beamline')).toBeNull();
    expect(c.queryByText('Folder')).toBeNull();
    expect(c.queryByText('Beamtime')).toBeNull();
    expect(c.getByText('SYN_run_A, SYN_run_B')).toBeInTheDocument();
    expect(c.getByText('WHY-SAID-BY-SERVER')).toBeInTheDocument();
    expect(c.getAllByText(COPY.suggestedNotConfirmed).length).toBeGreaterThan(0);
    expect(c.getByText('notes/SYN_log.txt')).toBeInTheDocument();
    // the suggestion ITSELF carries the label, not only the section heading above it
    const item = c.getByText('notes/SYN_log.txt').closest('.li-suggestion') as HTMLElement;
    expect(within(item).getByText(COPY.suggestedNotConfirmed)).toBeInTheDocument();
    expect(within(item).getByText('SYNTHETIC QUOTE measured ex situ')).toBeInTheDocument();
    expect(c.getByText('line 4')).toBeInTheDocument();
    // who made it is said once (no "An AI reading …: Suggested by an AI reading …")
    expect(within(item).getByText('Suggested by an AI reading of the files (synthetic-model)')).toBeInTheDocument();
    expect(within(item).queryByText(/An AI reading of the files/)).toBeNull();
    // the folder-name hint is shown, and cannot be accepted
    expect(c.getByText('A folder name is a HINT, never an answer.')).toBeInTheDocument();
    const accept = c.getAllByRole('button').filter((b) => b.textContent?.startsWith(COPY.acceptSuggestion));
    expect(accept.map((b) => b.textContent)).toEqual([`${COPY.acceptSuggestion}: ex_situ`]);
    // a closed list is a select of exactly the allowed values
    const select = c.getByLabelText('Your answer') as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(['', 'operando', 'in_situ', 'ex_situ']);
  });

  it('offers a number with its unit, an IANA zone, element and edge, and counter positions', async () => {
    stubQuestions();
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const value = await screen.findByLabelText('Value (in K)');
    expect(value).toHaveAttribute('inputmode', 'decimal');
    expect(screen.getByLabelText(/Time zone the instrument clock was set to/)).toBeInTheDocument();
    expect((screen.getByLabelText('Element') as HTMLInputElement).value).toBe('Zz');
    expect((screen.getByLabelText('Edge') as HTMLSelectElement).value).toBe('K');
    // no counter position is pre-checked: which positions are counters is the scientist's answer
    expect(screen.getByRole('checkbox', { name: 'Position 2' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Position 3' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'None of these is a counter' })).toBeInTheDocument();
  });

  it('needs a name before it sends anything', async () => {
    const calls = stubQuestions();
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const card = (await screen.findByRole('heading', { name: envQ.text })).closest('li') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: `${COPY.acceptSuggestion}: ex_situ` }));
    expect(await within(card).findByRole('alert')).toHaveTextContent(COPY.nameNeeded);
    expect(calls.filter((k) => k.startsWith('POST'))).toEqual([]);
  });

  it('where the groups’ suggestions differ, no scope is chosen for you and nothing is sent until one is', async () => {
    const calls = stubQuestions({}, [envQ]);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    fireEvent.change(await screen.findByLabelText(COPY.yourName), { target: { value: 'Synthetic Scientist' } });
    const card = screen.getByRole('heading', { name: envQ.text }).closest('li') as HTMLElement;
    expect(within(card).getByRole('radio', { name: `${COPY.sameForAll} (5)` })).not.toBeChecked();
    expect(within(card).getByRole('radio', { name: COPY.thisGroupOnly })).not.toBeChecked();
    expect(within(card).getByText(COPY.suggestionsDiffer)).toBeInTheDocument();
    fireEvent.change(within(card).getByLabelText('Your answer'), { target: { value: 'in_situ' } });
    fireEvent.click(within(card).getByRole('button', { name: COPY.answer }));
    expect(await within(card).findByRole('alert')).toHaveTextContent(COPY.chooseScope);
    expect(calls.filter((k) => k.startsWith('POST'))).toEqual([]);
  });

  it('the per-group table shows each group’s own suggestion and accepts it for that group alone', async () => {
    const posts: Record<string, unknown>[] = [];
    stubQuestions({
      [APATH(envQ.question_id)]: (init) => {
        posts.push(bodyOf(init));
        return { body: { dry_run: false, question_id: envQ.question_id, result: { recorded: ['miss-0002'], unchanged: [], batch_id: null },
          value: 'in_situ', bundle_version: VERSION_2, identity: 'local_unverified', statement: 'SERVER-SAID: recorded.' } };
      },
    }, [envQ]);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    fireEvent.change(await screen.findByLabelText(COPY.yourName), { target: { value: 'Synthetic Scientist' } });
    const table = screen.getAllByRole('table')[0];
    const row = within(table).getByText('SYN_run_B', { selector: '.li-run-names' }).closest('tr') as HTMLElement;
    expect(row).toHaveTextContent('SYNTHETIC in situ cell');
    expect(row).toHaveTextContent('SYN_run_B.dat @ header line 2');
    fireEvent.click(within(row).getByRole('button', { name: 'Accept in_situ for Record group g2' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ decision: 'correct', value: 'in_situ', only: 'group:g2', dry_run: false, expected_version: VERSION });
  });

  it('"same for all" previews every target, flags groups whose own files say otherwise, and reports the server’s count', async () => {
    const posts: Record<string, unknown>[] = [];
    const headers: (string | null)[] = [];
    let reads = 0;
    let releaseRead: () => void = () => undefined;
    stubQuestions({
      [`GET ${QPATH}`]: async (init) => {
        headers.push(new Headers(init?.headers).get('X-ISAAC-Local'));
        reads += 1;
        if (reads === 2) await new Promise<void>((resolve) => (releaseRead = resolve));
        return { body: questionsBody([envQ], reads === 1 ? VERSION : VERSION_2) };
      },
      [APATH(envQ.question_id)]: (init) => {
        const body = bodyOf(init);
        posts.push(body);
        if (body.dry_run) {
          return {
            body: {
              dry_run: true, question_id: envQ.question_id, would_record: ['miss-0001', 'miss-0002'], unchanged: [],
              target_ids: ['miss-0001', 'miss-0002'], value: 'in_situ', bundle_version: VERSION,
              statement: 'SERVER-SAID: nothing was written.', scopes_total: 2, scopes_whose_files_suggest_otherwise: 1,
              by_scope: [
                { scope: 'group:g1', label: 'Record group g1', run_names: ['SYN_run_A'], run_count: 1, target_ids: ['miss-0001'],
                  own_suggestions: envQ.display.scopes[0].own_suggestions, compared: true, differs: true,
                  differing_targets: [{ target_id: 'miss-0001', run_id: 'run-A', run_name: 'SYN_run_A', own_suggestions: envQ.display.scopes[0].own_suggestions }] },
                { scope: 'group:g2', label: 'Record group g2', run_names: ['SYN_run_B'], run_count: 1, target_ids: ['miss-0002'],
                  own_suggestions: envQ.display.scopes[1].own_suggestions, compared: true, differs: false, differing_targets: [] },
              ],
            },
          };
        }
        // the server recorded ONE (the other was already answered the same way) — not the preview's two
        return {
          body: {
            dry_run: false, question_id: envQ.question_id, result: { recorded: ['miss-0002'], unchanged: ['miss-0001'], batch_id: null },
            value: 'in_situ', bundle_version: VERSION_2, identity: 'local_unverified', statement: 'SERVER-SAID: recorded.',
          },
        };
      },
    }, [envQ]);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    fireEvent.change(await screen.findByLabelText(COPY.yourName), { target: { value: 'Synthetic Scientist' } });
    const card = screen.getByRole('heading', { name: envQ.text }).closest('li') as HTMLElement;
    fireEvent.click(within(card).getByRole('radio', { name: `${COPY.sameForAll} (5)` }));
    fireEvent.change(within(card).getByLabelText('Your answer'), { target: { value: 'in_situ' } });
    fireEvent.click(within(card).getByRole('button', { name: COPY.answer }));
    const preview = await within(card).findByRole('group', { name: /This will write one answer to each of these/ });
    expect(within(preview).getByTestId('li-preview-differs')).toHaveTextContent('1 of these 2 groups’ files suggest ex_situ, not in_situ');
    const flagged = within(preview).getByText(/Record group g1/).closest('li') as HTMLElement;
    expect(flagged).toHaveTextContent(COPY.filesSuggestOtherwise);
    expect(flagged).toHaveTextContent('notes/SYN_log.txt @ line 4');
    expect(flagged).toHaveTextContent('Run SYN_run_A'); // the RUN whose own file differs is named
    expect(within(preview).getByText(/Record group g2/).closest('li')).not.toHaveTextContent(COPY.filesSuggestOtherwise);
    expect(posts).toEqual([
      { decision: 'correct', by: 'Synthetic Scientist', expected_version: VERSION, value: 'in_situ', dry_run: true },
    ]);
    fireEvent.click(within(preview).getByRole('button', { name: COPY.previewWrite }));
    await waitFor(() => expect(reads).toBe(2));
    expect(posts[1]).toEqual({ decision: 'correct', by: 'Synthetic Scientist', expected_version: VERSION, value: 'in_situ', dry_run: false });
    const note = await screen.findByTestId('li-announcement');
    expect(note).toHaveTextContent('Recorded 1 answer(s)');
    expect(note).not.toHaveTextContent(COPY.refreshed); // not before the re-read has arrived
    releaseRead();
    await waitFor(() => expect(screen.getByTestId('li-announcement')).toHaveTextContent(COPY.refreshed));
    expect(screen.getByTestId('li-announcement')).toHaveTextContent('Recorded 1 answer(s)');
    await waitFor(() => expect(screen.getByRole('heading', { level: 2, name: /Questions/ })).toHaveFocus());
    expect(headers).toEqual(['1', '1']);
  });

  it('"this group only" writes at once, for that group alone', async () => {
    const posts: Record<string, unknown>[] = [];
    stubQuestions({
      [APATH(envQ.question_id)]: (init) => {
        posts.push(bodyOf(init));
        return {
          body: {
            dry_run: false, question_id: envQ.question_id, result: { recorded: ['miss-0002'], unchanged: [], batch_id: null },
            value: 'in_situ', bundle_version: VERSION_2, identity: 'local_unverified', statement: 'SERVER-SAID: recorded.',
          },
        };
      },
    }, [envQ]);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    fireEvent.change(await screen.findByLabelText(COPY.yourName), { target: { value: 'Synthetic Scientist' } });
    const card = screen.getByRole('heading', { name: envQ.text }).closest('li') as HTMLElement;
    fireEvent.click(within(card).getByRole('radio', { name: COPY.thisGroupOnly }));
    fireEvent.change(within(card).getByRole('combobox', { name: 'Which group' }), { target: { value: 'group:g2' } });
    expect(within(card).getByTestId('li-selected-group')).toHaveTextContent('in_situ');
    expect(within(card).getByTestId('li-selected-group')).toHaveTextContent('SYN_run_B.dat @ header line 2');
    fireEvent.change(within(card).getByLabelText('Your answer'), { target: { value: 'in_situ' } });
    fireEvent.click(within(card).getByRole('button', { name: COPY.answer }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({
      decision: 'correct', by: 'Synthetic Scientist', expected_version: VERSION, only: 'group:g2', value: 'in_situ', dry_run: false,
    });
  });

  it('a stale version writes nothing, says so, and reads the questions again', async () => {
    let reads = 0;
    stubQuestions({
      [`GET ${QPATH}`]: async () => {
        reads += 1;
        // the re-read takes a moment, as a real one does, so a reload that blanked the screen would show
        if (reads === 2) await new Promise((resolve) => setTimeout(resolve, 30));
        return { body: questionsBody([tempQ]) };
      },
      [APATH(tempQ.question_id)]: {
        status: 412,
        body: { error: 'stale_bundle_version', message: 'SERVER-SAID: changed.', current_version: VERSION_2 },
      },
    }, [tempQ]);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    fireEvent.change(await screen.findByLabelText(COPY.yourName), { target: { value: 'Synthetic Scientist' } });
    fireEvent.change(screen.getByLabelText('Value (in K)'), { target: { value: '295' } });
    fireEvent.click(screen.getByRole('button', { name: COPY.answer }));
    await waitFor(() => expect(reads).toBe(2));
    expect(await screen.findByTestId('li-announcement')).toHaveTextContent(COPY.staleWrite);
    expect(screen.getByTestId('li-announcement')).not.toHaveTextContent(/command|another window/);
    // once the re-read has ARRIVED, the card was not unmounted by it: what was typed is still there
    await waitFor(() => expect(screen.getByTestId('li-announcement')).toHaveTextContent(COPY.refreshed));
    expect(screen.getByLabelText('Value (in K)')).toHaveValue('295');
  });

  it('a refusal is shown in the server’s own words beside the question', async () => {
    stubQuestions({
      [APATH(tempQ.question_id)]: {
        status: 422,
        body: { error: 'value_refused', message: "SERVER-SAID: context.temperature_K: not a number: 'warm'." },
      },
    }, [tempQ]);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    fireEvent.change(await screen.findByLabelText(COPY.yourName), { target: { value: 'Synthetic Scientist' } });
    fireEvent.change(screen.getByLabelText('Value (in K)'), { target: { value: 'warm' } });
    fireEvent.click(screen.getByRole('button', { name: COPY.answer }));
    expect(await screen.findByRole('alert')).toHaveTextContent("SERVER-SAID: context.temperature_K: not a number: 'warm'.");
  });

  it('orders groups by suggested value with counts, collapses the groups with none, and leads with run names', async () => {
    stubQuestions({}, [envQ]);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    expect(await screen.findByTestId('li-suggestion-counts')).toHaveTextContent(
      'in_situ: 2 group(s) · ex_situ: 1 group(s) · runs disagree within the group: 1 group(s) · nothing suggested: 1 group(s)',
    );
    const [table] = screen.getAllByRole('table');
    const heads = within(table).getAllByRole('rowheader').map((h) => h.textContent);
    expect(heads).toEqual(['SYN_run_Bgroup g2', 'SYN_run_Cgroup g3', 'SYN_run_Agroup g1']);
    const first = within(table).getAllByRole('rowheader')[0];
    expect(first.firstElementChild).toHaveClass('li-run-names');
    expect(first.querySelector('.li-group-id')).toHaveTextContent('group g2');
    for (const b of within(table).getAllByRole('button')) expect(b).toHaveClass('li-nowrap');
    // the group with nothing suggested is behind a disclosure with its count
    const summary = screen.getByText(`${COPY.nothingSuggestedRows} (1)`);
    expect(summary.closest('details')).not.toHaveAttribute('open');
    expect(summary.closest('details')).toHaveTextContent('SYN_run_D');
  });

  it('a reading quoted from another run’s file is not called the group’s own, and is left out of the bulk accept', async () => {
    const posts: Record<string, unknown>[] = [];
    stubQuestions({
      [APATH(envQ.question_id)]: (init) => {
        posts.push(bodyOf(init));
        return { body: { dry_run: true, question_id: envQ.question_id, would_record: ['miss-0002'], unchanged: [], target_ids: ['miss-0002'],
          value: 'in_situ', bundle_version: VERSION, statement: 'SERVER-SAID: nothing was written.', scopes_total: 1,
          scopes_whose_files_suggest_otherwise: 0,
          by_scope: [{ scope: 'group:g2', label: 'Record group g2', run_names: ['SYN_run_B'], run_count: 1, target_ids: ['miss-0002'],
            own_suggestions: envQ.display.scopes[1].own_suggestions, compared: true, differs: false, differing_targets: [] }] } };
      },
    }, [envQ]);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    fireEvent.change(await screen.findByLabelText(COPY.yourName), { target: { value: 'Synthetic Scientist' } });
    const [table] = screen.getAllByRole('table');
    const rowC = within(table).getByText('SYN_run_C', { selector: '.li-run-names' }).closest('tr') as HTMLElement;
    expect(within(rowC).getByText(COPY.groupOtherSuggestion)).toBeInTheDocument();
    expect(within(rowC).queryByText(COPY.groupOwnSuggestion)).toBeNull();
    expect(rowC).toHaveTextContent("A reading for this group's runs, quoted from a file that is not one of its runs (SYN_run_B.dat)");
    const rowB = within(table).getByText('SYN_run_B', { selector: '.li-run-names' }).closest('tr') as HTMLElement;
    expect(within(rowB).getByText(COPY.groupOwnSuggestion)).toBeInTheDocument();
    // in_situ is suggested for g2 (own file) and g3 (another run's file): the bulk names g2 alone
    fireEvent.click(screen.getByRole('button', { name: 'Accept in_situ for the 1 group(s) whose own files all suggest it' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ decision: 'correct', value: 'in_situ', only_scopes: ['group:g2'], dry_run: true, expected_version: VERSION });
    expect(posts[0]).not.toHaveProperty('only');
    expect(await screen.findByRole('group', { name: /This will write one answer to each of these/ })).toHaveTextContent('miss-0002');
  });

  it('the stylesheet keeps action buttons whole and stacks the table on a phone-width screen', () => {
    const css = readFileSync(join(process.cwd(), 'src', 'screens', 'local-imports.css'), 'utf8');
    expect(css).toMatch(/\.li-nowrap\s*\{\s*white-space:\s*nowrap;/);
    expect(css).toMatch(/\.li-col-actions\s*\{\s*min-width:\s*13rem;/);
    expect(css).toMatch(/@media \(max-width: 560px\)\s*\{[^}]*\.li-table-groups thead\s*\{\s*display:\s*none;/);
  });

  it('a group whose runs disagree is never counted under one value, offered no whole-group accept, and shows each run', async () => {
    stubQuestions({}, [envQ]);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const mixed = await screen.findByTestId('li-mixed-groups');
    const perRun = within(mixed).getByTestId('li-per-run');
    expect(perRun).toHaveTextContent('Run SYN_run_E1');
    expect(perRun).toHaveTextContent('SYNTHETIC E1 in situ');
    expect(perRun).toHaveTextContent('Run SYN_run_E2');
    expect(perRun).toHaveTextContent('SYNTHETIC E2 ex situ');
    expect(within(mixed).queryByRole('button', { name: /^Accept/ })).toBeNull();
    expect(within(mixed).getByRole('button', { name: /Answer this group/ })).toBeInTheDocument();
    // the bulk accepts name only unanimous own-file groups: ex_situ -> g1, in_situ -> g2 (never g5)
    expect(screen.getByRole('button', { name: 'Accept in_situ for the 1 group(s) whose own files all suggest it' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Accept ex_situ for the 1 group(s) whose own files all suggest it' })).toBeInTheDocument();
  });
});

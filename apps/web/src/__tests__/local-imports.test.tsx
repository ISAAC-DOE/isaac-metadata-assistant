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
  CHECK_STATUS_LABEL,
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

/** A dry-run answer naming exactly `scopes` of envQ. */
function previewOf(scopes: string[], value: unknown = 'in_situ') {
  const by = envQ.display.scopes.filter((sc) => scopes.includes(sc.scope));
  const ids = by.flatMap((sc) => envQ.per_scope_targets[sc.scope]);
  return {
    dry_run: true, question_id: envQ.question_id, would_record: ids, unchanged: [], target_ids: ids, value, bundle_version: VERSION,
    statement: 'SERVER-SAID: nothing was written.', scopes_total: by.length, scopes_whose_files_suggest_otherwise: 0,
    by_scope: by.map((sc) => ({ scope: sc.scope, label: sc.label, run_names: sc.run_names, run_count: sc.run_names.length,
      target_ids: envQ.per_scope_targets[sc.scope], own_suggestions: sc.own_suggestions ?? [], compared: true, differs: false,
      differing_targets: [] })),
  };
}

function recordedBody(id: string, recorded: string[], version = VERSION_2) {
  return { dry_run: false, question_id: id, result: { recorded, unchanged: [], batch_id: null }, value: 'x',
    bundle_version: version, identity: 'local_unverified', statement: 'SERVER-SAID: recorded.' };
}

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
    // the check status in plain words; the raw code stays available in the chip's title
    const chip = screen.getByText(CHECK_STATUS_LABEL.STALE).closest('.li-chip') as HTMLElement;
    expect(chip).toHaveAttribute('title', expect.stringMatching(/^STALE: /));
    expect(screen.queryByText('STALE')).toBeNull();
    expect(screen.getByText('SYN_2099_beamtime')).toBeInTheDocument();
    // the "missing-value share" row said only that it is not available: it is gone
    expect(screen.queryByText('SERVER-SAID: no missing share is computed.')).toBeNull();
    expect(screen.queryByText(/Missing-value share/)).toBeNull();
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

  it('an informational question shows a note and no answer controls, scope choice or command', async () => {
    const infoQ = question({
      question_id: 'Q-info000001',
      kind: 'confirm_value',
      blocking: false,
      tier: 3,
      target_field_path: 'assets[].uri',
      text: 'What is assets[].uri?',
      per_scope_targets: { 'group:g1': ['cand-0001'], 'group:g2': ['cand-0002'] },
      allowed_decisions: [],
      answer_command: '# nothing to answer: no answer for assets[].uri reaches the record',
      display: display({
        answer_kind: 'informational',
        scopes: [
          { scope: 'group:g1', kind: 'group', group_id: 'g1', label: 'Record group g1', target_count: 1, run_names: ['SYN_run_A'], run_count: 1,
            own_suggestions: [], own_suggestions_total: 0, mixed: false, has_unanimous_value: false, unanimous_from_own_files: false, unanimous_value: null },
          { scope: 'group:g2', kind: 'group', group_id: 'g2', label: 'Record group g2', target_count: 1, run_names: ['SYN_run_B'], run_count: 1,
            own_suggestions: [], own_suggestions_total: 0, mixed: false, has_unanimous_value: false, unanimous_from_own_files: false, unanimous_value: null },
        ],
      }),
    });
    stubQuestions({}, [infoQ]);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const card = (await screen.findByRole('heading', { name: infoQ.text })).closest('li') as HTMLElement;
    const c = within(card);
    expect(c.getByTestId('li-informational')).toHaveTextContent(COPY.informational);
    expect(c.queryByRole('button', { name: COPY.answer })).toBeNull();
    expect(c.queryByRole('textbox')).toBeNull();
    expect(c.queryByRole('radio')).toBeNull();
    expect(c.queryByText('Command-line equivalent')).toBeNull();
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

  it('needs a name before it sends anything: the name field is focused and the error said again on every try', async () => {
    const calls = stubQuestions();
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const card = (await screen.findByRole('heading', { name: envQ.text })).closest('li') as HTMLElement;
    const accept = within(card).getByRole('button', { name: `${COPY.acceptSuggestion}: ex_situ` });
    fireEvent.click(accept);
    const nameField = screen.getByLabelText(COPY.yourName);
    const first = await screen.findByTestId('li-name-error');
    expect(first).toHaveAttribute('role', 'alert');
    expect(first).toHaveTextContent(COPY.nameNeeded);
    expect(nameField).toHaveFocus();
    expect(nameField).toHaveAttribute('aria-invalid', 'true');
    expect(nameField.getAttribute('aria-describedby')).toContain(first.id);
    // a second try re-announces: a NEW alert element (same words), and focus goes back to the field
    accept.focus();
    fireEvent.click(accept);
    await waitFor(() => expect(screen.getByTestId('li-name-error')).not.toBe(first));
    expect(nameField).toHaveFocus();
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

  it('the per-group table shows each group’s own suggestion and accepts it for that group alone — after a preview', async () => {
    const posts: Record<string, unknown>[] = [];
    stubQuestions({
      [APATH(envQ.question_id)]: (init) => {
        const body = bodyOf(init);
        posts.push(body);
        if (body.dry_run) return { body: previewOf(['group:g2']) };
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
    // nothing is written by the click: a dry run first, for that group alone
    const preview = await screen.findByRole('group', { name: /This will write one answer to each of these/ });
    expect(posts).toHaveLength(1);
    expect(posts[0]).toMatchObject({ decision: 'correct', value: 'in_situ', only: 'group:g2', dry_run: true, expected_version: VERSION });
    expect(within(preview).getByTestId('li-preview-runs')).toHaveTextContent('Run SYN_run_B');
    fireEvent.click(within(preview).getByRole('button', { name: COPY.previewWrite }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]).toMatchObject({ decision: 'correct', value: 'in_situ', only: 'group:g2', dry_run: false });
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
    // the question is still asked (other groups are open): focus stays on THIS card, on its "Answered" line
    await waitFor(() => expect(within(card).getByText(/Answered: Recorded 1 answer\(s\)/)).toHaveFocus());
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
    // said on the card that was refused
    const card = screen.getByRole('heading', { name: tempQ.text }).closest('li') as HTMLElement;
    expect(await within(card).findByRole('alert')).toHaveTextContent(COPY.staleWrite);
    expect(within(card).getByRole('alert')).not.toHaveTextContent(/command|another window/);
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
    for (const b of within(table).getAllByRole('button')) expect(b).toHaveClass('li-accept');
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

  it('the stylesheet lets an "Accept <long value>" button wrap (no sideways scroll) and stacks the table on a phone', () => {
    const css = readFileSync(join(process.cwd(), 'src', 'screens', 'local-imports.css'), 'utf8');
    expect(css).not.toMatch(/\.li-nowrap/);
    expect(css).toMatch(/\.li-accept\s*\{\s*white-space:\s*normal;\s*overflow-wrap:\s*anywhere;/);
    expect(css).toMatch(/\.li-choices \.btn\s*\{[^}]*overflow-wrap:\s*anywhere;/);
    expect(css).toMatch(/\.li-actions \.btn\s*\{[^}]*white-space:\s*normal;[^}]*overflow-wrap:\s*anywhere;/);
    expect(css).toMatch(/@media \(max-width: 720px\)\s*\{[^}]*\.li-table-groups thead\s*\{\s*display:\s*none;/);
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

describe('audit fixes', () => {
  function stub(routes: Record<string, RouteEntry>, qs: LocalQuestion[]) {
    vi.stubEnv('VITE_ISAAC_LOCAL_IMPORTS', '1');
    return stubFetchRoutes({
      'GET /api/local-bundles': { body: listBody },
      [`GET ${QPATH}`]: { body: questionsBody(qs) },
      ...routes,
    });
  }
  async function open(name = 'Synthetic Scientist') {
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    fireEvent.change(await screen.findByLabelText(COPY.yourName), { target: { value: name } });
  }
  const cardOf = (q: LocalQuestion) => screen.getByRole('heading', { name: q.text }).closest('li') as HTMLElement;
  const withoutScope = (q: LocalQuestion, scope: string): LocalQuestion => ({
    ...q,
    per_scope_targets: Object.fromEntries(Object.entries(q.per_scope_targets).filter(([k]) => k !== scope)),
    display: { ...q.display, scopes: q.display.scopes.filter((sc) => sc.scope !== scope) },
  });

  it('F1: a group answered "this group only" and no longer listed is not sent again: a new choice is required', async () => {
    const posts: Record<string, unknown>[] = [];
    let reads = 0;
    // g4 has one run: "this group only" writes at once
    stub({
      [`GET ${QPATH}`]: () => {
        reads += 1;
        return { body: questionsBody([reads === 1 ? envQ : withoutScope(envQ, 'group:g4')], reads === 1 ? VERSION : VERSION_2) };
      },
      [APATH(envQ.question_id)]: (init) => {
        posts.push(bodyOf(init));
        return { body: recordedBody(envQ.question_id, ['miss-0004'], VERSION_2) };
      },
    }, [envQ]);
    await open();
    let card = cardOf(envQ);
    fireEvent.click(within(card).getByRole('radio', { name: COPY.thisGroupOnly }));
    fireEvent.change(within(card).getByRole('combobox', { name: 'Which group' }), { target: { value: 'group:g4' } });
    fireEvent.change(within(card).getByLabelText('Your answer'), { target: { value: 'operando' } });
    fireEvent.click(within(card).getByRole('button', { name: COPY.answer }));
    await waitFor(() => expect(reads).toBe(2));
    await waitFor(() => expect(screen.getByTestId('li-announcement')).toHaveTextContent(COPY.refreshed));
    card = cardOf(envQ);
    const which = within(card).getByRole('combobox', { name: 'Which group' }) as HTMLSelectElement;
    // what is shown is what would be sent: nothing chosen
    expect(which.value).toBe('');
    expect([...which.options].map((o) => o.value)).not.toContain('group:g4');
    expect(within(card).getByTestId('li-group-gone')).toHaveTextContent(COPY.groupGone);
    fireEvent.click(within(card).getByRole('button', { name: COPY.answer }));
    expect(await within(card).findByRole('alert')).toHaveTextContent(COPY.groupGone);
    expect(posts).toHaveLength(1);
    expect(posts[0]).toMatchObject({ only: 'group:g4' });
  });

  it('F2: a second quick answer is sent with the version the first write returned, before any re-read lands', async () => {
    const posts: { path: string; body: Record<string, unknown> }[] = [];
    let reads = 0;
    const holds: (() => void)[] = [];
    stub({
      [`GET ${QPATH}`]: async () => {
        reads += 1;
        if (reads > 1) await new Promise<void>((resolve) => holds.push(resolve));
        return { body: questionsBody([tempQ, absorberQ], VERSION) };
      },
      [APATH(tempQ.question_id)]: (init) => {
        posts.push({ path: 'temp', body: bodyOf(init) });
        return { body: recordedBody(tempQ.question_id, ['miss-0100'], VERSION_2) };
      },
      [APATH(absorberQ.question_id)]: (init) => {
        posts.push({ path: 'abs', body: bodyOf(init) });
        return { body: recordedBody(absorberQ.question_id, ['g2'], 'sha256:' + 'c'.repeat(64)) };
      },
    }, [tempQ, absorberQ]);
    await open();
    fireEvent.change(screen.getByLabelText('Value (in K)'), { target: { value: '295' } });
    fireEvent.click(within(cardOf(tempQ)).getByRole('button', { name: COPY.answer }));
    await waitFor(() => expect(posts).toHaveLength(1));
    await waitFor(() => expect(reads).toBe(2)); // the re-read is in flight, held
    fireEvent.click(within(cardOf(absorberQ)).getByRole('button', { name: COPY.acceptSuggestion }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[0].body.expected_version).toBe(VERSION);
    expect(posts[1].body.expected_version).toBe(VERSION_2);
    // the OLDER re-read (still carrying VERSION) lands last: the newer version is still the one used
    holds.forEach((h) => h());
    await waitFor(() => expect(screen.getByTestId('li-announcement')).toHaveTextContent(COPY.refreshed));
    // both cards' messages are said; neither replaced the other
    expect(screen.getByTestId('li-announcement')).toHaveTextContent(`Recorded 1 answer(s) to “${tempQ.text.slice(0, 20)}`);
    expect(screen.getByTestId('li-announcement')).toHaveTextContent(`Recorded 1 answer(s) to “${absorberQ.text.slice(0, 20)}`);
  });

  it('F2: a 412 is said on the card that got it, and another card’s "Recorded" stays', async () => {
    stub({
      [APATH(tempQ.question_id)]: { body: recordedBody(tempQ.question_id, ['miss-0100'], VERSION_2) },
      [APATH(absorberQ.question_id)]: { status: 412, body: { error: 'stale_bundle_version', message: 'SERVER-SAID: changed.', current_version: VERSION_2 } },
    }, [tempQ, absorberQ]);
    await open();
    fireEvent.change(screen.getByLabelText('Value (in K)'), { target: { value: '295' } });
    fireEvent.click(within(cardOf(tempQ)).getByRole('button', { name: COPY.answer }));
    await waitFor(() => expect(within(cardOf(tempQ)).getByText(/Answered: Recorded 1 answer/)).toBeInTheDocument());
    fireEvent.click(within(cardOf(absorberQ)).getByRole('button', { name: COPY.acceptSuggestion }));
    expect(await within(cardOf(absorberQ)).findByRole('alert')).toHaveTextContent(COPY.staleWrite);
    await waitFor(() => expect(screen.getByTestId('li-announcement')).toHaveTextContent(COPY.refreshed));
    expect(within(cardOf(tempQ)).getByText(/Answered: Recorded 1 answer/)).toBeInTheDocument();
    expect(within(cardOf(tempQ)).queryByText(COPY.staleWrite)).toBeNull();
    expect(screen.getByTestId('li-announcement')).not.toHaveTextContent(COPY.staleWrite);
  });

  it('F3: accepting one group’s value previews every run, marking the runs with no reading', async () => {
    const reading = { ...MIXED_E1, value: 'ex_situ', relative_path: 'SYN_run_F1.dat', quote: 'SYNTHETIC F1 ex situ' };
    const g6 = {
      scope: 'group:g6', kind: 'group' as const, group_id: 'g6', label: 'Record group g6', target_count: 2,
      run_names: ['SYN_run_F1', 'SYN_run_F2'], run_count: 2, own_suggestions: [reading], own_suggestions_total: 1,
      mixed: false, has_unanimous_value: true, unanimous_value: 'ex_situ', unanimous_from_own_files: true,
      per_target: [
        { target_id: 'miss-0601', run_id: 'run-F1', run_name: 'SYN_run_F1', own_suggestions: [reading] },
        { target_id: 'miss-0602', run_id: 'run-F2', run_name: 'SYN_run_F2', own_suggestions: [] },
      ],
    };
    const q = { ...envQ, per_scope_targets: { ...envQ.per_scope_targets, 'group:g6': ['miss-0601', 'miss-0602'] },
      display: { ...envQ.display, scopes: [...envQ.display.scopes, g6] } };
    const posts: Record<string, unknown>[] = [];
    stub({
      [APATH(envQ.question_id)]: (init) => {
        posts.push(bodyOf(init));
        return { body: { ...previewOf([]), would_record: ['miss-0601', 'miss-0602'], target_ids: ['miss-0601', 'miss-0602'], value: 'ex_situ',
          scopes_total: 1, by_scope: [{ scope: 'group:g6', label: 'Record group g6', run_names: g6.run_names, run_count: 2,
            target_ids: ['miss-0601', 'miss-0602'], own_suggestions: [reading], compared: true, differs: false, differing_targets: [] }] } };
      },
    }, [q]);
    await open();
    const row = screen.getByText('SYN_run_F1, SYN_run_F2', { selector: '.li-run-names' }).closest('tr') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Accept ex_situ for Record group g6' }));
    const preview = await screen.findByRole('group', { name: /This will write one answer to each of these/ });
    expect(posts).toEqual([expect.objectContaining({ only: 'group:g6', dry_run: true })]);
    const runs = within(preview).getByTestId('li-preview-runs');
    const f1 = within(runs).getByText('Run SYN_run_F1').closest('li') as HTMLElement;
    const f2 = within(runs).getByText('Run SYN_run_F2').closest('li') as HTMLElement;
    expect(f1).toHaveTextContent('its files suggest ex_situ');
    expect(f2).toHaveAttribute('data-no-reading', 'true');
    expect(f2).toHaveTextContent(COPY.previewNoReading);
    // run names, not ids, in the list; the ids are behind a disclosure
    const ids = within(preview).getByText(COPY.previewIds).closest('details') as HTMLElement;
    expect(ids).not.toHaveAttribute('open');
    expect(ids).toHaveTextContent('miss-0601');
  });

  it('F4: a 403 refusal shows the server’s reason and never sign-in copy', async () => {
    stub({
      [`GET ${QPATH}`]: { status: 403, body: { detail: { error: 'origin_not_allowed', message: "SERVER-SAID: This page's origin may not use local bundles." } } },
    }, []);
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const refused = await screen.findByTestId('li-refused');
    expect(refused).toHaveTextContent("SERVER-SAID: This page's origin may not use local bundles.");
    expect(refused).toHaveTextContent('HTTP 403');
    expect(screen.queryByText(/Sign-In Required/i)).toBeNull();
    expect(screen.queryByText(/sign-in/i)).toBeNull();
    // the region is named even though the Questions heading does not exist in this state
    expect(screen.getByRole('region', { name: COPY.questionsTitle })).toBeInTheDocument();
  });

  it('F4: a 422 validation error shows what the server said, named by field', async () => {
    stub({
      [APATH(tempQ.question_id)]: {
        status: 422,
        body: { detail: [{ type: 'string_too_long', loc: ['body', 'by'], msg: 'String should have at most 200 characters', input: 'x' }] },
      },
    }, [tempQ]);
    await open();
    fireEvent.change(screen.getByLabelText('Value (in K)'), { target: { value: '295' } });
    fireEvent.click(screen.getByRole('button', { name: COPY.answer }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Your name: String should have at most 200 characters');
  });

  it('F4: the page holds the server’s limits — name 200, element 3 — and keeps a generated note under 2,000', async () => {
    const posts: Record<string, unknown>[] = [];
    const longPath = 'notes/' + 'p'.repeat(3_000) + '.txt';
    const fq = question({
      question_id: 'Q-note000001', scope: 'group:g1', per_scope_targets: { 'group:g1': ['miss-0700'] },
      targets: [{ kind: 'missing_value', id: 'miss-0700' }],
      display: display({
        scopes: [{ scope: 'group:g1', kind: 'group', group_id: 'g1', label: 'Record group g1', target_count: 1, run_names: ['SYN_run_A'] }],
        suggestions: [{ who: 'parser', who_label: 'ISAAC’s parser', hint_kind: 'x', value: 'ex_situ', relative_path: longPath, locator: 'line 1',
          quote: null, model_id: null, field: null, note: null, acceptable: true, confirmed: false }],
      }),
    });
    stub({
      [APATH(fq.question_id)]: (init) => {
        posts.push(bodyOf(init));
        return { body: recordedBody(fq.question_id, ['miss-0700']) };
      },
    }, [fq, absorberQ]);
    await open();
    expect(screen.getByLabelText(COPY.yourName)).toHaveAttribute('maxlength', '200');
    expect(screen.getByLabelText('Element')).toHaveAttribute('maxlength', '3');
    fireEvent.click(within(cardOf(fq)).getByRole('button', { name: `${COPY.acceptSuggestion}: ex_situ` }));
    await waitFor(() => expect(posts).toHaveLength(1));
    const note = String(posts[0].note);
    expect(note.length).toBeLessThanOrEqual(2_000);
    expect(note.startsWith('Accepted the suggestion shown')).toBe(true);
    expect(note.endsWith('…')).toBe(true);
  });

  it('F5: a question answered elsewhere (404 not_found_in_bundle) says so and reads the questions again', async () => {
    let reads = 0;
    stub({
      [`GET ${QPATH}`]: () => {
        reads += 1;
        return { body: questionsBody(reads === 1 ? [tempQ, absorberQ] : [absorberQ]) };
      },
      [APATH(tempQ.question_id)]: { status: 404, body: { error: 'not_found_in_bundle', message: "SERVER-SAID: No open question 'Q-temp000001'." } },
    }, [tempQ, absorberQ]);
    await open();
    fireEvent.change(screen.getByLabelText('Value (in K)'), { target: { value: '295' } });
    fireEvent.click(within(cardOf(tempQ)).getByRole('button', { name: COPY.answer }));
    await waitFor(() => expect(reads).toBe(2));
    await waitFor(() => expect(screen.getByTestId('li-announcement')).toHaveTextContent(COPY.refreshed));
    expect(screen.getByTestId('li-announcement')).toHaveTextContent(COPY.goneElsewhere);
    expect(screen.queryByRole('heading', { name: tempQ.text })).toBeNull();
    // focus moves to the next open question, not the page heading
    await waitFor(() => expect(screen.getByRole('heading', { name: absorberQ.text })).toHaveFocus());
  });

  it('F6: two failed re-reads in a row each say so — "Reading the questions again…" never sticks', async () => {
    let reads = 0;
    stub({
      [`GET ${QPATH}`]: () => {
        reads += 1;
        return reads === 1 ? { body: questionsBody([tempQ]) } : { status: 503, body: { detail: 'down' } };
      },
      [APATH(tempQ.question_id)]: { body: recordedBody(tempQ.question_id, ['miss-0100']) },
    }, [tempQ]);
    await open();
    fireEvent.change(screen.getByLabelText('Value (in K)'), { target: { value: '295' } });
    fireEvent.click(screen.getByRole('button', { name: COPY.answer }));
    await waitFor(() => expect(screen.getByTestId('li-announcement')).toHaveTextContent(COPY.refreshFailed));
    fireEvent.click(screen.getByRole('button', { name: COPY.answer }));
    await waitFor(() => expect(reads).toBe(3));
    await waitFor(() => expect(screen.getByTestId('li-announcement')).toHaveTextContent(COPY.refreshFailed));
    expect(screen.getByTestId('li-announcement')).not.toHaveTextContent(COPY.refreshing);
  });

  it('F7: a failed availability check is not remembered — the nav item appears once the API answers', async () => {
    vi.stubEnv('VITE_ISAAC_LOCAL_IMPORTS', '1');
    let up = false;
    stubFetchRoutes({
      'GET /api/local-bundles': () => (up ? { body: listBody } : { status: 503, body: { detail: 'starting' } }),
      'GET /api/local-bundles/synthetic-beamtime/progress': { body: progressBody },
    });
    renderAt(ROUTES.localImports);
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    await screen.findByRole('button', { name: 'Retry' }).catch(() => undefined);
    expect(within(nav).queryByRole('link', { name: LABELS.navLocalImports })).toBeNull();
    up = true;
    window.dispatchEvent(new Event('focus'));
    expect(await within(nav).findByRole('link', { name: LABELS.navLocalImports })).toBeInTheDocument();
  });

  it('Cancel on a preview writes nothing, says so, and returns focus to the button that opened it', async () => {
    const posts: Record<string, unknown>[] = [];
    stub({
      [APATH(envQ.question_id)]: (init) => {
        posts.push(bodyOf(init));
        return { body: previewOf(['group:g2']) };
      },
    }, [envQ]);
    await open();
    const accept = screen.getByRole('button', { name: 'Accept in_situ for Record group g2' });
    accept.focus();
    fireEvent.click(accept);
    const preview = await screen.findByRole('group', { name: /This will write one answer to each of these/ });
    fireEvent.click(within(preview).getByRole('button', { name: COPY.previewCancel }));
    await waitFor(() => expect(accept).toHaveFocus());
    expect(within(cardOf(envQ)).getByTestId('li-card-status')).toHaveTextContent(COPY.previewCancelled);
    expect(posts.every((p) => p.dry_run === true)).toBe(true);
  });

  it('Enter in a value field answers (a form), and Previous/Next move focus to the questions heading', async () => {
    const posts: Record<string, unknown>[] = [];
    const page = (offset: number) => ({ ...questionsBody([tempQ]), total: 400, offset, limit: 200, returned: 1,
      omitted_before: offset, omitted_after: offset === 0 ? 199 : 0 });
    stub({
      [`GET ${QPATH}`]: (_init, key) => ({ body: page(key?.includes('offset=200') ? 200 : 0) }),
      [APATH(tempQ.question_id)]: (init) => {
        posts.push(bodyOf(init));
        return { body: recordedBody(tempQ.question_id, ['miss-0100']) };
      },
    }, [tempQ]);
    await open();
    const field = screen.getByLabelText('Value (in K)');
    fireEvent.change(field, { target: { value: '295' } });
    fireEvent.submit(field.closest('form') as HTMLFormElement);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ value: '295', field: 'context.temperature_K' });
    expect(within(field.closest('form') as HTMLElement).getByRole('button', { name: COPY.answer })).toHaveAttribute('type', 'submit');
    fireEvent.click(screen.getByRole('button', { name: 'Next questions' }));
    await waitFor(() => expect(screen.getByRole('heading', { level: 2, name: /Questions/ })).toHaveFocus());
  });

  it('keeps the name across reloads, and survives a storage that throws', async () => {
    stub({}, [tempQ]);
    const first = renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    fireEvent.change(await screen.findByLabelText(COPY.yourName), { target: { value: 'Synthetic Scientist' } });
    first.unmount();
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    expect(await screen.findByLabelText(COPY.yourName)).toHaveValue('Synthetic Scientist');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    fireEvent.change(screen.getByLabelText(COPY.yourName), { target: { value: 'Another Name' } });
    expect(screen.getByLabelText(COPY.yourName)).toHaveValue('Another Name');
  });

  it('copy: plain words, and the regroup step is named as a command-line step with a copy button', async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    stub({}, [counterQ, envQ]);
    await open();
    const page = document.body.textContent ?? '';
    expect(page).not.toMatch(/answer slot|exposure\(s\)|blind cross-check|Blocking is judged against|result of record|\btargets\b/);
    expect(page).not.toMatch(/Nearest record|Fewest answers to one record/);
    const card = cardOf(counterQ);
    expect(card).toHaveTextContent('That step is done in the command line');
    const command = within(card).getByLabelText('Command that proposes the groups again');
    expect(command).toHaveTextContent('isaac bundle group "<folder of bundles>/synthetic-beamtime" --regroup');
    fireEvent.click(within(card).getByRole('button', { name: /Copy command/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('isaac bundle group "<folder of bundles>/synthetic-beamtime" --regroup'));
    expect(await within(card).findByText(COPY.copied)).toBeInTheDocument();
  });
});

describe('review round 2: the minimum’s unasked fields and the counts the split leaves out are shown', () => {
  const minimum = {
    group_id: 'g2',
    blocking_questions: 0,
    plus_decisions: ['confirm the group'],
    questions: [],
    unasked_required: [
      { path: 'sample.sample_form', answerable: false, reason: 'SERVER-SAID: reason', command: 'isaac bundle decide …' },
      { path: 'context.environment', answerable: false, reason: 'SERVER-SAID: reason', command: 'isaac bundle decide …' },
    ],
  };
  const notCounted =
    'Neither blocking nor counted as optional: 2 disagreement(s) about something no record field holds (settling one ' +
    'changes no record); 1 question(s) about runs no record group holds (no record is built from them).';

  it('the progress overview names the unasked fields and the two counts', async () => {
    vi.stubEnv('VITE_ISAAC_LOCAL_IMPORTS', '1');
    stubFetchRoutes({
      'GET /api/local-bundles': { body: listBody },
      'GET /api/local-bundles/synthetic-beamtime/progress': {
        body: {
          ...progressBody,
          progress: {
            ...progressBody.progress,
            questions: { total: 8, blocking: 1, conflicts_affecting_a_record: 0, optional: 4, conflicts_without_a_record_field: 2, outside_live_groups: 1 },
            minimum_for_one_group: minimum,
          },
        },
      },
    });
    renderAt(ROUTES.localImports);
    expect(await screen.findByTestId('li-not-counted')).toHaveTextContent(notCounted);
    expect(
      screen.getByText(/group g2 needs 2 required fields no question asks yet: sample form, environment; plus: confirm the group\./),
    ).toBeInTheDocument();
  });

  it('the questions page shows the two counts beside its own, and nothing when both are zero', async () => {
    vi.stubEnv('VITE_ISAAC_LOCAL_IMPORTS', '1');
    const body = questionsBody([envQ]);
    stubFetchRoutes({
      'GET /api/local-bundles': { body: listBody },
      [`GET ${QPATH}`]: { body: { ...body, counts: { ...body.counts, conflicts_without_a_record_field: 2, outside_live_groups: 1 }, minimum_for_one_group: minimum } },
    });
    const view = renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    expect(await screen.findByTestId('li-not-counted')).toHaveTextContent(notCounted);
    expect(screen.getByText(/needs 2 required fields no question asks yet: sample form, environment/)).toBeInTheDocument();
    view.unmount();
    __resetLocalImportsAvailability();
    stubFetchRoutes({
      'GET /api/local-bundles': { body: listBody },
      [`GET ${QPATH}`]: { body: { ...body, counts: { ...body.counts, conflicts_without_a_record_field: 0, outside_live_groups: 0 } } },
    });
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    expect(await screen.findByRole('heading', { level: 2, name: /Questions/ })).toBeInTheDocument();
    expect(screen.queryByTestId('li-not-counted')).toBeNull();
  });
});

describe('polish c7-w: the page says what the command line says', () => {
  function stubWith(extra: Record<string, RouteEntry>, body: ApiLocalQuestions) {
    vi.stubEnv('VITE_ISAAC_LOCAL_IMPORTS', '1');
    return stubFetchRoutes({ 'GET /api/local-bundles': { body: listBody }, [`GET ${QPATH}`]: { body }, ...extra });
  }
  async function cardOf(q: LocalQuestion) {
    return (await screen.findByRole('heading', { name: q.text })).closest('li') as HTMLElement;
  }

  it('a deferred question says who deferred it and when, and Defer is given through the same answer path', async () => {
    const deferredQ = { ...tempQ, deferred: { by: 'Synthetic Scientist', decided_utc: '2099-01-02T03:04:05Z', decision_id: 'd-00001', targets: 1 } };
    const posts: Record<string, unknown>[] = [];
    stubWith({
      [APATH(tempQ.question_id)]: (init) => {
        posts.push(bodyOf(init));
        const r = recordedBody(tempQ.question_id, ['miss-0100']);
        return { body: { ...r, result: { ...r.result, statement: 'SERVER-SAID: deferred for 1 runs: temperature.' } } };
      },
    }, questionsBody([deferredQ]));
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const card = await cardOf(tempQ);
    expect(within(card).getByTestId('li-deferred')).toHaveTextContent('Deferred by Synthetic Scientist, 2099-01-02');
    expect(within(card).getByText(COPY.deferredChip, { selector: '.li-chip' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(COPY.yourName), { target: { value: 'Synthetic Scientist' } });
    const defer = within(card).getByRole('button', { name: COPY.defer });
    expect(defer).toHaveAccessibleDescription(COPY.deferHint);
    fireEvent.click(defer);
    await waitFor(() => expect(posts).toHaveLength(1));
    // one target: written at once, with the field, the name and the version, exactly as an answer is
    expect(posts[0]).toEqual({ decision: 'defer', by: 'Synthetic Scientist', expected_version: VERSION, field: 'context.temperature_K', dry_run: false });
    // decide's own statement is said, not only a count
    expect(await within(card).findByText(/Answered: .*SERVER-SAID: deferred for 1 runs: temperature\./)).toBeInTheDocument();
  });

  it('Defer and Reject are offered exactly where allowed_decisions lists them', async () => {
    stubWith({}, questionsBody([tempQ, absorberQ, zoneQ, counterQ]));
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const temp = await cardOf(tempQ);
    expect(within(temp).getByRole('button', { name: COPY.defer })).toBeInTheDocument();
    expect(within(temp).getByRole('button', { name: COPY.reject })).toBeInTheDocument();
    const abs = await cardOf(absorberQ);
    expect(within(abs).getByRole('button', { name: COPY.defer })).toBeInTheDocument();
    expect(within(abs).queryByRole('button', { name: COPY.reject })).toBeNull();
    for (const q of [zoneQ, counterQ]) {
      const c = await cardOf(q);
      expect(within(c).queryByRole('button', { name: COPY.defer })).toBeNull();
      expect(within(c).queryByRole('button', { name: COPY.reject })).toBeNull();
    }
  });

  it('a dry run shows decide’s "Would record" statement and the regroup preview before anything is written', async () => {
    const posts: Record<string, unknown>[] = [];
    stubWith({
      [APATH(counterQ.question_id)]: (init) => {
        posts.push(bodyOf(init));
        return {
          body: {
            dry_run: true, question_id: counterQ.question_id, would_record: ['experiment'], unchanged: [], target_ids: ['experiment'],
            value: null, bundle_version: VERSION, statement: 'SERVER-SAID: nothing was written.', scopes_total: 1,
            scopes_whose_files_suggest_otherwise: 0,
            by_scope: [{ scope: 'experiment', label: 'The whole beamtime', run_names: [], run_count: 0, target_ids: ['experiment'],
              own_suggestions: [], compared: false, differs: false, differing_targets: [] }],
            would_say: 'Would record: SERVER-SAID positions 2 are counters. Nothing was written.',
            regroup_preview: { groups_joined: 2, into: 1, groups_split: 0, merge_decisions_unblocked: [],
              statement: 'SERVER-SAID: on the next regroup this answer would join 2 of the current groups into 1.' },
          },
        };
      },
    }, questionsBody([counterQ]));
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    fireEvent.change(await screen.findByLabelText(COPY.yourName), { target: { value: 'Synthetic Scientist' } });
    const card = await cardOf(counterQ);
    fireEvent.click(within(card).getByRole('checkbox', { name: 'Position 2' }));
    fireEvent.click(within(card).getByRole('button', { name: 'The checked positions are run counters' }));
    const preview = await within(card).findByRole('group', { name: /This will write one answer to each of these/ });
    expect(within(preview).getByTestId('li-preview-would-say')).toHaveTextContent('Would record: SERVER-SAID positions 2 are counters.');
    expect(within(preview).getByTestId('li-preview-regroup')).toHaveTextContent('would join 2 of the current groups into 1');
    expect(posts).toEqual([{ decision: 'set_counter_positions', by: 'Synthetic Scientist', expected_version: VERSION, positions: [2], dry_run: true }]);
  });

  it('the nearest group lists each needed question by field and group, linked to its card, with its warnings', async () => {
    const minimum = {
      group_id: 'g1',
      blocking_questions: 2,
      plus_decisions: ['confirm the group'],
      questions: [
        { question_id: envQ.question_id, fields: ['context.environment'], only: 'group:g1', deferred: true },
        { question_id: 'Q-elsewhere01', fields: ['sample.sample_form'], only: null },
      ],
      unasked_required: [],
      missing_required_now: ['context.environment', 'sample.sample_form', 'measurement.series'],
      recommended: [{ question_id: tempQ.question_id, fields: ['context.temperature_K'], only: null, blocking: false as const,
        why: 'SERVER-SAID: the file names state a temperature the record will not carry.' }],
      warnings: ['SERVER-SAID: the file names state a temperature the record will not carry.'],
      processing_qc: 'its processing QC verdict is fail (SERVER-SAID reason)',
    };
    stubWith({}, { ...questionsBody([envQ, tempQ]), minimum_for_one_group: minimum });
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const nearest = await screen.findByTestId('li-nearest');
    expect(within(nearest).getByText(/group g1 needs 2 blocking answer\(s\) \(1 deferred\), plus: confirm the group\./)).toBeInTheDocument();
    const listed = within(nearest).getByTestId('li-nearest-questions');
    const link = within(listed).getByRole('link', { name: 'environment' });
    expect(link).toHaveAttribute('href', `#li-q-${envQ.question_id}`);
    expect(link.closest('li')).toHaveTextContent('for group g1 (deferred)');
    // a question on another page is named, never linked to nothing
    expect(within(listed).queryByRole('link', { name: 'sample form' })).toBeNull();
    expect(within(listed).getByText(/sample form/).closest('li')).toHaveTextContent(COPY.notOnThisPage);
    expect(within(nearest).getByTestId('li-nearest-recommended')).toHaveTextContent('SERVER-SAID: the file names state a temperature');
    expect(within(nearest).getByText(/Processing QC: its processing QC verdict is fail/)).toBeInTheDocument();
    expect(within(nearest).getByText(/measurement\.series/)).toBeInTheDocument();
    fireEvent.click(link);
    await waitFor(() => expect(screen.getByRole('heading', { name: envQ.text })).toHaveFocus());
  });

  it('a covered question links the beamtime question it names, in that question’s words', async () => {
    const coveredQ = question({
      question_id: 'Q-covered001',
      blocking: false,
      tier: 3,
      scope: 'group:g1',
      text: 'What is the environment of group g1?',
      why: `Not blocking: answer the experiment-wide question ${envQ.question_id}. SERVER-SAID rest.`,
      covered_by: envQ.question_id,
      display: display({ covered_by: { question_id: envQ.question_id, text: envQ.text } }),
    });
    stubWith({}, questionsBody([envQ, coveredQ]));
    renderAt(ROUTES.localImportBundle('synthetic-beamtime'));
    const card = await cardOf(coveredQ);
    const link = within(card).getByRole('link', { name: `“${envQ.text}”` });
    expect(link).toHaveAttribute('href', `#li-q-${envQ.question_id}`);
    expect(link.closest('dd')).toHaveTextContent('Not blocking: answer the experiment-wide question');
    expect(link.closest('dd')).toHaveTextContent('SERVER-SAID rest.');
    expect(link.closest('dd')).not.toHaveTextContent(envQ.question_id);
  });

  it('the overview’s counts add up, informational and deferred named, and bundle check’s held line is said', async () => {
    vi.stubEnv('VITE_ISAAC_LOCAL_IMPORTS', '1');
    const held = 'SERVER-SAID: This build held 2 value(s) read only from a beamtime-wide notes sentence for review.';
    stubFetchRoutes({
      'GET /api/local-bundles': {
        body: { ...listBody, bundles: [{ ...listBody.bundles[0], check: { status: 'VALID', errors: [], error_count: 0, stale_values: 0,
          statement: 'SERVER-SAID: meets the format.', held_in_memory: 2, held_statement: held } }] },
      },
      'GET /api/local-bundles/synthetic-beamtime/progress': {
        body: { ...progressBody, progress: { ...progressBody.progress,
          questions: { total: 10, blocking: 1, conflicts_affecting_a_record: 2, optional: 3, informational: 4, conflicts_without_a_record_field: 0,
            outside_live_groups: 0, deferred: 1 } } },
      },
    });
    renderAt(ROUTES.localImports);
    expect(await screen.findByText('10 (1 blocking export, 2 conflicts affecting a record, 3 optional)')).toBeInTheDocument();
    expect(screen.getByTestId('li-not-counted')).toHaveTextContent(`4 ${COPY.informationalCount}`);
    expect(screen.getByTestId('li-not-counted')).toHaveTextContent(`Of the open questions, 1 ${COPY.deferredCount}.`);
    expect(screen.getByTestId('li-held')).toHaveTextContent(held);
  });
});

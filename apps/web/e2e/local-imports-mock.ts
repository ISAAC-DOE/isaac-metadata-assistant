/**
 * LOCAL IMPORTS, MOCKED IN THE BROWSER — for the two `localImportsMock` surfaces only.
 *
 * Local Imports needs two things the e2e run does not have, and both are supplied HERE,
 * per page, rather than for the whole run:
 *
 *   1. THE BUILD FLAG. `localImportsBuildEnabled()` (`src/lib/localImports.ts`) is true
 *      only when the app was started with `VITE_ISAAC_LOCAL_IMPORTS=1`. Setting it on the
 *      Playwright web server would switch it on for EVERY surface — each page would then
 *      ask `GET /api/local-bundles`, the real backend would answer its ordinary 404, and
 *      the "Failed to load resource" console error it logs would land in the two specs
 *      that require a quiet console (`tutorial.spec.ts`, `statistics-states.spec.ts`).
 *      So the flag is injected into the ONE module that reads it, on the pages that need
 *      it: Vite's dev transform prefixes that module with a literal
 *      `import.meta.env = {…};`, and the route below adds the flag to that object. It is
 *      exactly what starting Vite with the variable would have put there. If the prefix
 *      is not found (a built bundle via `E2E_EXTERNAL_WEB_SERVER`, a Vite upgrade, the
 *      read moved to another module) `assertLocalImportsFlagInjected` FAILS the open with
 *      the reason — never a quiet "Not part of this build" scan reported as the screen.
 *   2. THE API. `/api/local-bundles/*` exists only on a server started with
 *      `ISAAC_LOCAL_BUNDLES_DIR`. The requests are answered in the browser from the
 *      SYNTHETIC fixtures below (shaped by the wire types in `src/lib/localImports.ts`;
 *      names and values invented, borrowed from `src/__tests__/local-imports.test.tsx`).
 *      Nothing reaches the backend and nothing is written: any POST is refused here.
 *
 * `uninstallLocalImports` removes both handlers again, so a later surface opened on the
 * same page (the width sweeps loop over the catalogue in one page) measures the app
 * without the flag, as before.
 */

import type { Page, Request, Route } from '@playwright/test';

export const LOCAL_BUNDLE_NAME = 'synthetic-beamtime';

/** A value every run of one group suggests — long, so narrow widths measure its button. */
export const LONG_VALUE = 'in_situ_electrochemical_flow_cell_under_potential_control';

const VERSION = 'sha256:' + 'a'.repeat(64);

const header = {
  name: LOCAL_BUNDLE_NAME,
  source_label: 'SYN_2099_beamtime',
  source_kind: 'folder',
  format_version: '1.6.0',
  bundle_id: 'SYNTHETIC',
  beamline: [{ value: 'SYN-1', basis: 'candidate_extracted' }],
  bundle_version: VERSION,
  modified_utc: '2099-01-01T00:00:00Z',
};

function display(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    folder: LOCAL_BUNDLE_NAME,
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

function question(over: Record<string, unknown>): Record<string, unknown> {
  return {
    question_id: 'Q-0000000000',
    tier: 1,
    blocking: true,
    why: 'Synthetic: no file in this import states it.',
    kind: 'missing_value',
    scope: 'experiment',
    target_field_path: 'context.environment',
    text: 'What is the environment?',
    applies_to: { groups: 2, runs: 2, targets: 2 },
    targets: [],
    per_scope_targets: {},
    allowed_values: null,
    allowed_decisions: ['confirm', 'correct', 'reject', 'defer'],
    answer_command:
      'isaac bundle decide <bundle_dir> --question Q-0000000000 --decision correct --value <value> --by "<your name>"',
    display: display(),
    ...over,
  };
}

const own = (value: string, relative_path: string, quote: string, fromOwn = true) => ({
  value,
  who: 'parser',
  who_label: "Read from the file by ISAAC's parser",
  model_id: null,
  relative_path,
  locator: 'header line 2',
  quote,
  confirmed: false,
  targets: 1,
  from_own_files: fromOwn,
  provenance_label: fromOwn
    ? "This group's own files"
    : `A reading for this group's runs, quoted from a file that is not one of its runs (${relative_path})`,
});

const E1 = own('in_situ', 'SYN_run_E1.dat', 'SYNTHETIC E1 in situ');
const E2 = own('ex_situ', 'SYN_run_E2.dat', 'SYNTHETIC E2 ex situ');

const envQ = question({
  question_id: 'Q-env0000001',
  text: 'What is the environment (context.environment)? Applies to 5 group(s) — answer once, or per group.',
  applies_to: { groups: 5, runs: 6, targets: 6 },
  per_scope_targets: {
    'group:g1': ['miss-0001'],
    'group:g2': ['miss-0002'],
    'group:g3': ['miss-0003'],
    'group:g4': ['miss-0004'],
    'group:g5': ['miss-0005', 'miss-0006'],
  },
  allowed_values: ['operando', 'in_situ', 'ex_situ', LONG_VALUE],
  display: display({
    settles_many: true,
    suggestions_differ: true,
    targets_described: 6,
    targets_total: 6,
    record_run_names: ['SYN_run_A', 'SYN_run_B', 'SYN_run_C', 'SYN_run_D', 'SYN_run_E1', 'SYN_run_E2'],
    scopes: [
      {
        scope: 'group:g1', kind: 'group', group_id: 'g1', label: 'Record group g1', target_count: 1,
        run_names: ['SYN_run_A'], run_count: 1,
        own_suggestions: [own('ex_situ', 'notes/SYN_log.txt', 'SYNTHETIC QUOTE measured ex situ')],
        own_suggestions_total: 1, mixed: false, has_unanimous_value: true, unanimous_from_own_files: true,
        unanimous_value: 'ex_situ',
      },
      {
        scope: 'group:g2', kind: 'group', group_id: 'g2', label: 'Record group g2', target_count: 1,
        run_names: ['SYN_run_B'], run_count: 1,
        own_suggestions: [own(LONG_VALUE, 'SYN_run_B.dat', 'SYNTHETIC flow cell held under potential control')],
        own_suggestions_total: 1, mixed: false, has_unanimous_value: true, unanimous_from_own_files: true,
        unanimous_value: LONG_VALUE,
      },
      {
        scope: 'group:g3', kind: 'group', group_id: 'g3', label: 'Record group g3', target_count: 1,
        run_names: ['SYN_run_C'], run_count: 1,
        own_suggestions: [own('in_situ', 'SYN_run_B.dat', 'SYNTHETIC names run C', false)],
        own_suggestions_total: 1, mixed: false, has_unanimous_value: true, unanimous_value: 'in_situ',
        unanimous_from_own_files: false,
      },
      {
        scope: 'group:g4', kind: 'group', group_id: 'g4', label: 'Record group g4', target_count: 1,
        run_names: ['SYN_run_D'], run_count: 1,
        own_suggestions: [], own_suggestions_total: 0, mixed: false, has_unanimous_value: false,
        unanimous_from_own_files: false,
      },
      {
        scope: 'group:g5', kind: 'group', group_id: 'g5', label: 'Record group g5', target_count: 2,
        run_names: ['SYN_run_E1', 'SYN_run_E2'], run_count: 2,
        own_suggestions: [E1, E2], own_suggestions_total: 2, mixed: true, has_unanimous_value: false,
        unanimous_from_own_files: false,
        per_target: [
          { target_id: 'miss-0005', run_id: 'run-E1', run_name: 'SYN_run_E1', own_suggestions: [E1] },
          { target_id: 'miss-0006', run_id: 'run-E2', run_name: 'SYN_run_E2', own_suggestions: [E2] },
        ],
      },
    ],
    suggestions: [
      {
        who: 'ai_reading', who_label: 'Suggested by an AI reading of the files', hint_kind: 'ai_suggestion',
        value: 'ex_situ', relative_path: 'notes/SYN_log.txt', locator: 'line 4',
        quote: 'SYNTHETIC QUOTE measured ex situ', model_id: 'synthetic-model', field: null, note: null,
        acceptable: true, confirmed: false, targets: 2,
      },
      {
        who: 'hint', who_label: 'A hint about what is asked, never an answer', hint_kind: 'folder_name',
        value: 'SYN_2099_beamtime', relative_path: null, locator: "the imported folder's name", quote: null,
        model_id: null, field: null, note: 'A folder name is a HINT, never an answer.', acceptable: false,
        confirmed: false,
      },
    ],
    suggestions_total: 2,
    value_rule: { allowed: ['operando', 'in_situ', 'ex_situ', LONG_VALUE], numeric: false, integer: false, in_schema: true, unit: null },
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
  applies_to: { groups: 1, runs: 1, targets: 1 },
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
  applies_to: { groups: 1, runs: 1, targets: 1 },
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
  per_scope_targets: { experiment: ['experiment'] },
  allowed_decisions: ['set_counter_positions', 'set_not_counter_positions'],
  display: display({ answer_kind: 'counter_positions', settles_many: true }),
});

const QUESTIONS = [envQ, tempQ, zoneQ, absorberQ, counterQ];

const check = {
  status: 'STALE',
  errors: [],
  error_count: 0,
  stale_values: 3,
  statement: 'Synthetic: 3 stored value(s) were written by an older build.',
};

export const LIST_BODY = {
  local_only: true,
  directory_name: 'synthetic-bundles',
  not_bundles: 1,
  statement: 'Synthetic: nothing on this page is uploaded.',
  bundles: [
    {
      ...header,
      check,
      counts: { runs: 6 },
      record_groups: 5,
      scientist_decisions: 0,
      readiness: { stage: 'extracted', eligible_value_count: 0, blocking: null },
    },
  ],
};

export const PROGRESS_BODY = {
  bundle: header,
  progress: {
    check,
    runs: 6,
    run_candidates: 6,
    record_groups: { total: 5, by_status: { proposed: 5 } },
    processing_results: { total: 0, by_state: {} },
    scientist_decisions: 0,
    values: {},
    readiness: { stage: 'extracted', eligible_value_count: 0, blocking: null, official_record_ready: false },
    missing_share: null,
    missing_share_statement: 'Synthetic: no missing-value share is computed for a bundle.',
    questions: { total: 5, blocking: 1, conflicts_affecting_a_record: 0, optional: 4 },
    minimum_for_one_group: { group_id: 'g1', blocking_questions: 1, plus_decisions: ['the absorber of group g1'] },
    blocks_export: ['Synthetic: 1 blocking question(s) are open.'],
    last_validation: {
      reports: [
        { group_id: 'g1', verdict: 'invalid', missing_required: ['context.environment'], written_utc: '2099-01-01T00:00:00Z', older_than_bundle: true },
      ],
      statement: 'Synthetic: the last validation written into the bundle.',
    },
  },
};

export const QUESTIONS_BODY = {
  bundle: header,
  counts: { total: QUESTIONS.length, blocking: 1, conflicts_affecting_a_record: 0, optional: QUESTIONS.length - 1 },
  blocking_basis: { schema: 'vendored v1.05', source: 'schema/isaac_record_v1.json', commit: null },
  total: QUESTIONS.length,
  offset: 0,
  limit: 200,
  returned: QUESTIONS.length,
  omitted_before: 0,
  omitted_after: 0,
  minimum_for_one_group: { group_id: 'g1', blocking_questions: 1, plus_decisions: ['the absorber of group g1'] },
  questions: QUESTIONS,
  capture: {
    merge_candidates: [
      {
        merge_candidate_id: 'merge-0001',
        group_ids: ['g3', 'g4'],
        groups: [
          { group_id: 'g3', run_names: ['SYN_run_C'] },
          { group_id: 'g4', run_names: ['SYN_run_D'] },
        ],
        question: 'Are groups g3 and g4 the same sample and condition?',
        reasons: ['Synthetic: same sample name in both run headers.'],
      },
    ],
    athena_selections: [
      {
        processing_id: 'proc-0001',
        group_id: 'g1',
        run_names: ['SYN_run_A'],
        versions: [
          { version_id: 'athena-v1', project_file: 'SYN_project.prj', athena_group: 'merged A' },
          { version_id: 'athena-v2', project_file: 'SYN_project_rebinned.prj', athena_group: 'merged A rebinned' },
        ],
      },
    ],
  },
  exposures_recorded: 0,
  identity: 'local_unverified',
  statement: 'Synthetic: answers stay on this computer.',
};

// --- the handlers --------------------------------------------------------------------------

interface Installed {
  flag: (route: Route) => Promise<void>;
  api: (route: Route) => Promise<void>;
  flagMatcher: (url: URL) => boolean;
  apiMatcher: (url: URL) => boolean;
  /** Did the flag module pass through the rewrite on this page, and did the rewrite apply? */
  flagState: { served: boolean; injected: boolean };
}

const installed = new WeakMap<Page, Installed>();

const FLAG_MODULE = '/src/lib/localImports.ts';
const ENV_PREFIX = 'import.meta.env = {';

function corsHeaders(req: Request): Record<string, string> {
  const h = req.headers();
  return {
    'access-control-allow-origin': h['origin'] ?? '*',
    'access-control-allow-methods': 'GET, POST, OPTIONS',
    'access-control-allow-headers': h['access-control-request-headers'] ?? 'X-ISAAC-Local, Content-Type',
    vary: 'Origin',
  };
}

function apiAnswer(req: Request): { status: number; body: unknown } {
  const path = new URL(req.url()).pathname.replace(/^.*\/api\//, '/api/');
  if (req.method() !== 'GET') {
    return { status: 405, body: { error: 'read_only_e2e', message: 'The read-only e2e suite writes nothing.' } };
  }
  const base = `/api/local-bundles`;
  const bundle = `${base}/${encodeURIComponent(LOCAL_BUNDLE_NAME)}`;
  if (path === base) return { status: 200, body: LIST_BODY };
  if (path === `${bundle}/progress`) return { status: 200, body: PROGRESS_BODY };
  if (path === `${bundle}/questions`) return { status: 200, body: QUESTIONS_BODY };
  if (path.startsWith(`${base}/`) && !path.startsWith(`${bundle}/`)) {
    return { status: 404, body: { error: 'bundle_not_found', message: 'No bundle by that name.' } };
  }
  return { status: 404, body: { error: 'not_found', message: 'Not Found' } };
}

/** Enable the flag and answer `/api/local-bundles/*` on this page. Idempotent; re-installing
 *  moves the handlers to the front, so they win over any route added since (the
 *  worked-example scope route is one). */
export async function installLocalImports(page: Page): Promise<void> {
  await uninstallLocalImports(page);
  const flagState = { served: false, injected: false };
  const flagMatcher = (url: URL) => url.pathname === FLAG_MODULE;
  const apiMatcher = (url: URL) => /\/api\/local-bundles(\/|$)/.test(url.pathname);
  const flag = async (route: Route) => {
    const response = await route.fetch();
    const text = await response.text();
    flagState.served = true;
    flagState.injected = text.includes(ENV_PREFIX);
    await route.fulfill({
      response,
      body: flagState.injected ? text.replace(ENV_PREFIX, `${ENV_PREFIX}"VITE_ISAAC_LOCAL_IMPORTS": "1", `) : text,
    });
  };
  const api = async (route: Route) => {
    const req = route.request();
    if (req.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: corsHeaders(req) });
      return;
    }
    const { status, body } = apiAnswer(req);
    await route.fulfill({
      status,
      headers: corsHeaders(req),
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  };
  await page.route(flagMatcher, flag);
  await page.route(apiMatcher, api);
  installed.set(page, { flag, api, flagMatcher, apiMatcher, flagState });
}

/** Remove what `installLocalImports` added on this page, if anything. */
export async function uninstallLocalImports(page: Page): Promise<void> {
  const mine = installed.get(page);
  if (!mine) return;
  installed.delete(page);
  // `unroute` of a handler a spec's own `unrouteAll` already removed is a no-op.
  await page.unroute(mine.flagMatcher, mine.flag).catch(() => undefined);
  await page.unroute(mine.apiMatcher, mine.api).catch(() => undefined);
}

/** Throw, with the reason, unless the flag really reached the app on this page. */
export function assertLocalImportsFlagInjected(page: Page): void {
  const mine = installed.get(page);
  if (!mine) throw new Error('local-imports mock: not installed on this page.');
  if (!mine.flagState.served) {
    throw new Error(
      `local-imports mock: the page never requested ${FLAG_MODULE}, so the build flag could not be ` +
        'injected. Is this a built bundle (E2E_EXTERNAL_WEB_SERVER)? The flag is read at build time there; ' +
        'build that bundle with VITE_ISAAC_LOCAL_IMPORTS=1 instead.',
    );
  }
  if (!mine.flagState.injected) {
    throw new Error(
      `local-imports mock: ${FLAG_MODULE} no longer starts with Vite's "${ENV_PREFIX}…" prefix, so ` +
        'VITE_ISAAC_LOCAL_IMPORTS could not be injected. See e2e/local-imports-mock.ts.',
    );
  }
}

/*
 * LOCAL IMPORTS — the wire contract, the copy, and the pure helpers of the local-only
 * questions screen (`screens/LocalImports.tsx`) over `/api/local-bundles/*`
 * (`apps/api/isaac_api/local_bundles.py`).
 *
 * TWO GATES, AND THE NAV ITEM NEEDS BOTH:
 *
 *   1. THIS BUILD. `localImportsBuildEnabled()` is true only in a LOCAL build (`!isHostedBuild`)
 *      started with `VITE_ISAAC_LOCAL_IMPORTS=1`. A hosted image is built without it, so a hosted
 *      bundle never even asks the server — no request, no nav item, nothing to explain.
 *   2. THIS SERVER. The API registers the routes only when it was started with
 *      `ISAAC_LOCAL_BUNDLES_DIR`; otherwise `GET /api/local-bundles` is the ordinary 404 and the
 *      item stays absent. `useLocalImportsAvailable` asks once per session.
 *
 * Nothing here computes a question, a verdict or an eligibility: every one of them is the
 * server's, which is the command line's (`isaac bundle questions` / `decide`).
 */

import { useEffect, useState } from 'react';
import { api, isHostedBuild } from './api';

// --- the wire -----------------------------------------------------------------------------

export interface LocalBeamlineReading {
  value: unknown;
  basis: string | null;
}

export interface LocalBundleCheck {
  status: 'VALID' | 'STALE' | 'INVALID';
  errors: string[];
  error_count: number;
  stale_values: number;
  statement: string;
}

export interface LocalBundleHeader {
  name: string;
  source_label?: string | null;
  source_kind?: string | null;
  format_version?: string | null;
  bundle_id?: string | null;
  beamline?: LocalBeamlineReading[];
  bundle_version: string | null;
  modified_utc?: string | null;
}

export interface LocalBundleSummary extends LocalBundleHeader {
  check: LocalBundleCheck;
  counts?: Record<string, number | null>;
  record_groups?: number;
  scientist_decisions?: number;
  readiness?: { stage?: string | null; eligible_value_count?: number | null; blocking?: Record<string, number> | null };
}

export interface ApiLocalBundleList {
  local_only: true;
  directory_name: string;
  bundles: LocalBundleSummary[];
  not_bundles: number;
  statement: string;
}

export interface LocalValidationReport {
  group_id: string;
  verdict: string | null;
  missing_required: string[];
  written_utc: string;
  older_than_bundle: boolean;
}

export interface LocalProgress {
  check: LocalBundleCheck;
  runs: number | null;
  run_candidates: number | null;
  record_groups: { total: number; by_status: Record<string, number> };
  processing_results: { total: number; by_state: Record<string, number> };
  scientist_decisions: number;
  values: Record<string, number | null>;
  readiness: { stage?: string | null; eligible_value_count?: number | null; blocking?: Record<string, number> | null; official_record_ready: false };
  missing_share: null;
  missing_share_statement: string;
  questions: { total?: number; blocking?: number; conflicts_affecting_a_record?: number; optional?: number; unavailable?: string } | null;
  minimum_for_one_group: { group_id: string; blocking_questions: number; plus_decisions: string[]; blocked?: string } | null;
  blocks_export: string[];
  last_validation: { reports: LocalValidationReport[]; statement: string };
}

export interface ApiLocalBundleProgress {
  bundle: LocalBundleHeader;
  progress: LocalProgress;
}

export type LocalSuggestionWho = 'parser' | 'stored_rule' | 'ai_reading' | 'file_reading' | 'hint';

export interface LocalSuggestion {
  who: LocalSuggestionWho;
  who_label: string;
  hint_kind: string;
  value: unknown;
  relative_path: string | null;
  locator: string | null;
  quote: string | null;
  model_id: string | null;
  field: string | null;
  note: string | null;
  acceptable: boolean;
  confirmed: false;
  candidate_id?: string;
  targets?: number;
  run_names?: string[];
}

/** What ONE scope's (group's) own files, or the AI readings made for it, suggest. Never confirmed. */
export interface LocalOwnSuggestion {
  value: unknown;
  who: LocalSuggestionWho;
  who_label: string;
  model_id: string | null;
  relative_path: string | null;
  locator: string | null;
  quote: string | null;
  confirmed: false;
  targets: number;
  /** True only when the cited file is one of this scope's own runs' files; false for a file of another run (or a shared document); null when not recorded. */
  from_own_files: boolean | null;
  provenance_label: string;
}

export interface LocalScope {
  scope: string;
  kind: 'experiment' | 'group' | 'run';
  label: string;
  target_count: number;
  run_names: string[];
  run_count?: number;
  group_id?: string;
  run_id?: string;
  group_status?: string;
  own_suggestions?: LocalOwnSuggestion[];
  own_suggestions_total?: number;
  /** Targets are per RUN: the runs' own suggestions differ within this group. */
  mixed?: boolean;
  /** Every run with a suggestion suggests exactly this one value. */
  has_unanimous_value?: boolean;
  unanimous_value?: unknown;
  /** …and every such suggestion cites one of the group's own runs' files. */
  unanimous_from_own_files?: boolean;
  per_target?: { target_id: string; run_id: string | null; run_name: string | null; own_suggestions: LocalOwnSuggestion[] }[];
}

export interface LocalValueRule {
  allowed: unknown[] | null;
  numeric: boolean;
  integer: boolean;
  in_schema: boolean;
  unit: string | null;
  target_count?: number;
}

export type LocalAnswerKind =
  | 'field_value'
  | 'optional_values'
  | 'confirm_value'
  | 'conflict'
  | 'counter_positions'
  | 'clock_zone'
  | 'absorber'
  | 'other';

export interface LocalQuestionDisplay {
  folder: string;
  beamtime: string | null;
  beamline: LocalBeamlineReading[];
  answer_kind: LocalAnswerKind;
  settles_many: boolean;
  scopes: LocalScope[];
  record_run_names: string[];
  targets_described: number;
  targets_total: number;
  /** The groups' own suggestions name more than one value: the screen asks for an explicit scope. */
  suggestions_differ: boolean;
  suggestions: LocalSuggestion[];
  suggestions_total: number;
  distinct_extracted_values: { value: unknown; targets: number }[];
  field_suggestions: Record<string, LocalSuggestion[]>;
  value_rule: LocalValueRule | null;
  fields: Record<string, LocalValueRule>;
  suggested_absorber: { element: string; edge: string; basis: string } | null;
  suggestion_statement: string;
}

export interface LocalQuestion {
  question_id: string;
  tier: number;
  blocking: boolean;
  why: string;
  kind: string;
  scope: string;
  partition?: string | null;
  target_field_path: string | null;
  text: string;
  applies_to: { groups: number; runs: number; targets: number };
  targets: { kind: string; id: string }[];
  per_scope_targets: Record<string, string[]>;
  allowed_values: unknown[] | null;
  allowed_decisions: string[];
  positions?: number[];
  fields?: Record<string, string[]>;
  answer_command: string;
  display: LocalQuestionDisplay;
}

export interface LocalMergeCandidate {
  merge_candidate_id: string;
  group_ids: string[];
  groups: { group_id: string; run_names: string[]; status?: string }[];
  question: string | null;
  reasons: string[];
}

export interface LocalAthenaSelection {
  processing_id: string;
  group_id: string | null;
  run_names: string[];
  versions: { version_id: string; project_file?: string | null; athena_group?: string | null }[];
}

export interface ApiLocalQuestions {
  bundle: LocalBundleHeader;
  counts: { total: number; blocking: number; conflicts_affecting_a_record: number; optional: number };
  blocking_basis: { schema: string; source: string; commit: string | null };
  total: number;
  offset: number;
  limit: number;
  returned: number;
  omitted_before: number;
  omitted_after: number;
  minimum_for_one_group: LocalProgress['minimum_for_one_group'];
  questions: LocalQuestion[];
  capture: { merge_candidates: LocalMergeCandidate[]; athena_selections: LocalAthenaSelection[] };
  exposures_recorded: number;
  identity: 'local_unverified';
  statement: string;
}

export interface LocalAnswerInput {
  decision: string;
  value?: string;
  by: string;
  only?: string;
  only_scopes?: string[];
  field?: string;
  element?: string;
  edge?: string;
  positions?: number[];
  note?: string;
  expected_version: string;
  dry_run?: boolean;
}

export interface LocalPreviewScope {
  scope: string;
  label: string;
  run_names: string[];
  run_count: number;
  target_ids: string[];
  own_suggestions: LocalOwnSuggestion[];
  compared: boolean;
  differs: boolean;
  /** The runs (targets) whose OWN suggestions exclude the value being written. */
  differing_targets: { target_id: string; run_id: string | null; run_name: string | null; own_suggestions: LocalOwnSuggestion[] }[];
}

export interface ApiLocalAnswerPreview {
  dry_run: true;
  by_scope: LocalPreviewScope[];
  scopes_total: number;
  scopes_whose_files_suggest_otherwise: number;
  question_id: string;
  would_record: string[];
  unchanged: string[];
  target_ids: string[];
  value: unknown;
  bundle_version: string;
  statement: string;
}

export interface ApiLocalAnswerRecorded {
  dry_run: false;
  question_id: string;
  result: { recorded: string[]; unchanged: string[]; batch_id: string | null; statement?: string };
  value: unknown;
  bundle_version: string;
  identity: 'local_unverified';
  statement: string;
}

export interface LocalDecisionInput {
  target: string;
  decision: 'keep_apart' | 'merge' | 'select_athena_version';
  value?: string;
  merge_with?: string[];
  by: string;
  expected_version: string;
}

export interface ApiLocalDecisionRecorded {
  result: { recorded: string[]; unchanged: string[]; statement?: string };
  bundle_version: string;
  identity: 'local_unverified';
  statement: string;
}

// --- the gates ------------------------------------------------------------------------------

/** True only in a LOCAL build started with `VITE_ISAAC_LOCAL_IMPORTS=1`. Read at call time. */
export function localImportsBuildEnabled(): boolean {
  if (isHostedBuild) return false;
  return (import.meta.env.VITE_ISAAC_LOCAL_IMPORTS as string | undefined) === '1';
}

let availability: Promise<boolean> | null = null;
let available = false;

/**
 * Does THIS server serve local bundles? Never throws.
 *
 * Only a YES is remembered for the session. A failed check — the API not up yet when the page
 * first loaded, a refusal, a 404 from a server started without the folder — is forgotten, so the
 * next check asks again; while one check is in flight every caller shares it.
 */
export function localImportsAvailableOnce(): Promise<boolean> {
  if (!localImportsBuildEnabled()) return Promise.resolve(false);
  if (available) return Promise.resolve(true);
  if (!availability) {
    availability = api.listLocalBundles().then(
      () => {
        available = true;
        return true;
      },
      () => {
        availability = null;
        return false;
      },
    );
  }
  return availability;
}

/** Test seam: forget the cached answer. */
export function __resetLocalImportsAvailability(): void {
  availability = null;
  available = false;
}

/** When a "no" is asked again, in ms after the first check (then on focus / coming back online only). */
export const AVAILABILITY_RETRY_MS = [3_000, 10_000, 30_000] as const;

/**
 * `true` once the server has said it serves local bundles; `false` before, and in every hosted
 * build. A "no" is checked again a few times with backoff, and whenever the window regains focus
 * or comes back online, so the nav item appears once the API is up.
 */
export function useLocalImportsAvailable(): boolean {
  const [yes, setYes] = useState(available);
  useEffect(() => {
    if (!localImportsBuildEnabled()) return undefined;
    let alive = true;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const check = () => {
      if (timer !== undefined) clearTimeout(timer);
      timer = undefined;
      void localImportsAvailableOnce().then((ok) => {
        if (!alive) return;
        setYes(ok);
        if (!ok && attempt < AVAILABILITY_RETRY_MS.length) {
          timer = setTimeout(check, AVAILABILITY_RETRY_MS[attempt]);
          attempt += 1;
        }
      });
    };
    const again = () => {
      if (!available) check();
    };
    check();
    window.addEventListener('focus', again);
    window.addEventListener('online', again);
    return () => {
      alive = false;
      if (timer !== undefined) clearTimeout(timer);
      window.removeEventListener('focus', again);
      window.removeEventListener('online', again);
    };
  }, []);
  return yes;
}

// --- the server's limits, and its reasons ---------------------------------------------------

/**
 * The request limits `apps/api/isaac_api/local_bundles.py` enforces (`LocalAnswerRequest` /
 * `LocalDecisionRequest`), so the page refuses what the server would, before sending it.
 */
export const LOCAL_LIMITS = {
  /** `by: str = Field(max_length=200)` */
  nameMax: 200,
  /** `element: str | None = Field(default=None, max_length=3)` */
  elementMax: 3,
  /** `note: str | None = Field(default=None, max_length=2_000)` */
  noteMax: 2_000,
  /** `value: str | None = Field(default=None, max_length=20_000)` (an answer's value) */
  valueMax: 20_000,
} as const;

/**
 * `text` cut to at most `max` UTF-16 units (so at most `max` characters as the server counts them),
 * ending in "…" when cut, never splitting a surrogate pair.
 */
export function clampText(text: string, max: number): string {
  if (text.length <= max) return text;
  let end = max - 1;
  const code = text.charCodeAt(end - 1);
  if (code >= 0xd800 && code <= 0xdbff) end -= 1;
  return `${text.slice(0, end)}…`;
}

const FIELD_NAME: Record<string, string> = {
  by: 'Your name',
  value: 'The answer',
  note: 'The note',
  element: 'Element',
  edge: 'Edge',
  only: 'The group',
  only_scopes: 'The groups',
  field: 'The field',
  positions: 'The positions',
  expected_version: 'The bundle version',
};

/**
 * The server's own reason for a refusal, or `undefined`. Reads every shape this API answers with:
 * `{message}` (the routes' own refusals), `{detail: "…"}`, `{detail: {error, message}}` (the
 * 403/421 guards, raised as `HTTPException`) and FastAPI's 422 `{detail: [{loc, msg}]}`, each
 * item named by the field it is about. An HTML page (`htmlIntercept`) has no reason of ISAAC's.
 */
export function localReasonOf(err: unknown): string | undefined {
  if (typeof err !== 'object' || err === null) return undefined;
  if ((err as { htmlIntercept?: unknown }).htmlIntercept === true) return undefined;
  const body = (err as { body?: unknown }).body;
  if (typeof body !== 'object' || body === null) return undefined;
  const text = (v: unknown) => (typeof v === 'string' && v.trim() !== '' ? v : undefined);
  const b = body as { message?: unknown; detail?: unknown };
  const own = text(b.message);
  if (own) return own;
  const detail = b.detail;
  if (text(detail)) return text(detail);
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d !== 'object' || d === null) return undefined;
        const msg = text((d as { msg?: unknown }).msg);
        if (!msg) return undefined;
        const loc = (d as { loc?: unknown }).loc;
        const path = Array.isArray(loc) ? loc.filter((p) => p !== 'body').map(String) : [];
        const name = path.length ? (FIELD_NAME[path[0]] ?? path.join('.')) : '';
        return name ? `${name}: ${msg}` : msg;
      })
      .filter((m): m is string => m !== undefined);
    return parts.length ? parts.join('; ') : undefined;
  }
  if (typeof detail === 'object' && detail !== null) return text((detail as { message?: unknown }).message);
  return undefined;
}

/** The server's refusal CODE (`error`), wherever the body carries it, or `undefined`. */
export function localReasonCodeOf(err: unknown): string | undefined {
  if (typeof err !== 'object' || err === null) return undefined;
  const body = (err as { body?: unknown }).body as { error?: unknown; detail?: unknown } | undefined;
  if (body && typeof body === 'object') {
    if (typeof body.error === 'string') return body.error;
    const d = body.detail as { error?: unknown } | undefined;
    if (d && typeof d === 'object' && typeof d.error === 'string') return d.error;
  }
  const reason = (err as { reason?: unknown }).reason;
  return typeof reason === 'string' ? reason : undefined;
}

/** A bundle check status in plain words; the raw code stays available beside it. */
export const CHECK_STATUS_LABEL: Record<LocalBundleCheck['status'], string> = {
  VALID: 'Checks out',
  STALE: 'Made by an older ISAAC — refresh it',
  INVALID: 'Has errors',
};

// --- remembering the name typed ---------------------------------------------------------------

const NAME_KEY = 'isaac.localImports.by';

/** The name typed last time on this computer, or ''. Never throws. */
export function rememberedName(): string {
  try {
    return (window.localStorage.getItem(NAME_KEY) ?? '').slice(0, LOCAL_LIMITS.nameMax);
  } catch {
    return '';
  }
}

/** Remember (or, for '', forget) the name. Never throws: a blocked storage just does not remember. */
export function rememberName(name: string): void {
  try {
    if (name.trim()) window.localStorage.setItem(NAME_KEY, name);
    else window.localStorage.removeItem(NAME_KEY);
  } catch {
    // storage blocked or full: the name is still used for this page
  }
}

/** The command that proposes the groups again — a step the command line does, not this page. */
export function regroupCommand(bundleName: string): string {
  return `isaac bundle group "<folder of bundles>/${bundleName}" --regroup`;
}

// --- copy ------------------------------------------------------------------------------------

export const LOCAL_IMPORTS_COPY = {
  lead:
    'Import bundles in the folder this server was started with, on this computer. A bundle is what `isaac import` made from a beamtime folder: what the files say, and the questions only you can answer.',
  boundary:
    'Nothing on this page is uploaded or sent anywhere. An answer is written into the bundle on this computer, by the same code as `isaac bundle decide`, as a local, unverified statement by the name you type.',
  notInThisBuild:
    'Local imports are not part of this build. They are available only when ISAAC runs on your own computer, started for a folder of import bundles.',
  notOnThisServer:
    'This server was not started with a folder of import bundles, so there is nothing to show here.',
  howToStart: 'Start the server for a folder of bundles (see the local development guide):',
  startCommand:
    'ISAAC_LOCAL_BUNDLES_DIR=<folder of bundles> .venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000',
  overviewTitle: 'Import Progress',
  noBundles: 'No bundle folders were found in this folder. `isaac import <beamtime folder> --out <folder>/<name>` makes one.',
  openQuestions: 'Answer Questions',
  backToAll: 'All local imports',
  questionsTitle: 'Questions',
  yourName: 'Your name',
  yourNameHint:
    'Recorded with every answer, exactly as the command line’s `--by`. This build does not verify who you are.',
  nameNeeded: 'Type your name before answering: every answer records who gave it.',
  settlesManyTitle: 'Answer Once for the Whole Beamtime',
  settlesManyLead:
    'Each of these is asked once and settles many records. Check the groups it applies to before answering for all of them.',
  suggestedNotConfirmed: 'Suggested — not confirmed',
  noSuggestion: 'No suggestion. No file in this import states it.',
  otherReadings: 'Other readings and hints',
  allowedAnswers: 'Allowed answers',
  acceptSuggestion: 'Accept suggestion',
  sameForAll: 'Same for all groups in this beamtime',
  thisGroupOnly: 'This group only',
  previewTitle: 'This will write one answer to each of these',
  previewNoReading: 'no reading in its files — this answer will be recorded for it too',
  previewHasReading: 'its files suggest',
  previewCancelled: 'Nothing was written.',
  previewIds: 'Technical ids (for the command line)',
  chooseGroup: 'Choose which group this answer is for.',
  groupGone: 'The group chosen before is no longer asked about here (it may have been answered). Choose a group.',
  goneElsewhere: 'This question was already answered (perhaps in another window or on the command line). Nothing was written; the questions are being read again.',
  answeredHere: 'Answered:',
  previewWrite: 'Write these answers',
  previewCancel: 'Cancel',
  preview: 'Preview',
  answer: 'Answer',
  refreshed: 'Refreshed from the bundle.',
  staleWrite:
    'The bundle changed since this page read it. Nothing was written, and what you typed is kept: check the question against what is read now, and answer again.',
  refreshing: 'Reading the questions again…',
  refreshFailed:
    'The questions could not be read again, so what you see may not include it. Reload the page to read them.',
  chooseScope:
    'Choose whether this answer is for every group or for one group: the groups’ own files suggest different values.',
  suggestionsDiffer:
    'The groups’ own files suggest different values. Nothing is chosen for you: answer group by group below, or choose one answer for every group.',
  perGroupTitle: 'Group by Group',
  groupOwnSuggestion: 'This group’s own suggestion — not confirmed',
  groupOtherSuggestion: 'A reading for this group’s runs — not confirmed',
  mixedTitle: 'Runs Within the Group Disagree',
  mixedNote:
    'The runs of each of these groups suggest different values, so no answer is offered for the whole group: answer it yourself.',
  nothingSuggestedRows: 'Groups whose files suggest nothing',
  groupNoSuggestion: 'Nothing in this group’s files suggests a value.',
  answerThisGroup: 'Answer this group',
  filesSuggestOtherwise: 'Its files suggest otherwise',
  captureTitle: 'Grouping and Processing Decisions',
  mergeTitle: 'Merge or Keep Apart',
  athenaTitle: 'Athena Version of Record',
  keepApart: 'Keep apart',
  mergeThem: 'Merge these groups',
  mergeAfter:
    'A merge takes effect only once the groups are proposed again. That step is done in the command line, not on this page: run this command, then reload this page.',
  counterAfter:
    'The runs are regrouped by these positions only once the groups are proposed again. That step is done in the command line, not on this page: run this command, then reload this page.',
  copyCommand: 'Copy command',
  copied: 'Copied.',
  copyRefused: 'Your browser did not allow copying. Select the command and copy it.',
  selectAthena: 'Use this version',
  athenaQuestion: 'Which Athena version is the final result for',
  nearestRecord: 'Closest to a finished record',
  failedToRead: 'The server refused to read this.',
  notIsaac: 'Something other than this ISAAC server answered (a web page, not data). Check that the server on this computer is running, then try again.',
  retry: 'Retry',
  chipBlocks: 'Blocks Export',
  chipOptional: 'Optional',
  lastValidation: 'Last validation',
  blocksExport: 'What still blocks export',
} as const;

export const KIND_LABEL: Record<string, string> = {
  missing_value: 'Not Stated in Any File',
  resolve_conflict: 'Where the Files Disagree',
  confirm_value: 'Extracted Values to Confirm',
  confirm_absorber: 'Absorbing Element and Edge',
  naming_counter_positions: 'Run Counters in File Names',
  clock_time_zone: 'Instrument Clock Time Zone',
  optional_values: 'Optional Values',
};

/** The order kinds are shown in, after the "answer once" section. */
export const KIND_ORDER = [
  'missing_value',
  'resolve_conflict',
  'confirm_value',
  'confirm_absorber',
  'naming_counter_positions',
  'clock_time_zone',
  'optional_values',
] as const;

export const WHO_LABEL: Record<LocalSuggestionWho, string> = {
  parser: 'ISAAC’s parser',
  stored_rule: 'A stored rule',
  ai_reading: 'An AI reading of the files',
  file_reading: 'The files',
  hint: 'A hint',
};

/**
 * The per-group table's buckets and its bulk actions. Targets are per RUN, so a group is counted under
 * a value only when every run with a suggestion suggests exactly that value (`has_unanimous_value`);
 * a group whose runs disagree goes to `mixed`. `ownFiles` lists, per value, ONLY the unanimous groups
 * whose every suggestion cites one of their own runs' files — a reading quoted from another run's file
 * never puts a group in a bulk action.
 */
export function groupBySuggestion(scopes: LocalScope[]): {
  withSuggestion: LocalScope[];
  mixed: LocalScope[];
  without: LocalScope[];
  counts: { value: unknown; key: string; groups: number }[];
  ownFiles: Record<string, string[]>;
} {
  const counts = new Map<string, { value: unknown; key: string; groups: number }>();
  const ownFiles: Record<string, string[]> = {};
  const unanimous = scopes.filter((sc) => sc.has_unanimous_value && !sc.mixed);
  for (const sc of unanimous) {
    const key = JSON.stringify(sc.unanimous_value);
    const c = counts.get(key) ?? { value: sc.unanimous_value, key, groups: 0 };
    c.groups += 1;
    counts.set(key, c);
    if (sc.unanimous_from_own_files) (ownFiles[key] ??= []).push(sc.scope);
  }
  const ordered = [...counts.values()].sort((a, b) => b.groups - a.groups || a.key.localeCompare(b.key));
  const rank = new Map(ordered.map((c, i) => [c.key, i]));
  const withSuggestion = [...unanimous].sort(
    (a, b) => (rank.get(JSON.stringify(a.unanimous_value)) ?? 0) - (rank.get(JSON.stringify(b.unanimous_value)) ?? 0),
  );
  const mixed = scopes.filter((sc) => sc.mixed);
  const without = scopes.filter((sc) => !sc.mixed && !sc.has_unanimous_value);
  return { withSuggestion, mixed, without, counts: ordered, ownFiles };
}

export const ABSORBER_EDGES = ['K', 'L1', 'L2', 'L3', 'M1', 'M2', 'M3', 'M4', 'M5'] as const;

// --- pure helpers ----------------------------------------------------------------------------

export interface QuestionSection {
  id: string;
  title: string;
  questions: LocalQuestion[];
}

/** Blocking first, then the server's own order (tier, scope, path, id). */
function blockingFirst(qs: LocalQuestion[]): LocalQuestion[] {
  return qs
    .map((q, i) => ({ q, i }))
    .sort((a, b) => Number(b.q.blocking) - Number(a.q.blocking) || a.i - b.i)
    .map(({ q }) => q);
}

/**
 * The screen's sections: the questions one answer settles for many records first, then one
 * section per question type in `KIND_ORDER`, each blocking-first. Every question lands in
 * exactly one section; a kind this screen does not know gets a section of its own at the end,
 * so nothing the server asked is dropped.
 */
export function sectionQuestions(questions: LocalQuestion[]): QuestionSection[] {
  const settles = blockingFirst(questions.filter((q) => q.display.settles_many));
  const rest = questions.filter((q) => !q.display.settles_many);
  const sections: QuestionSection[] = [];
  if (settles.length) {
    sections.push({ id: 'settles-many', title: LOCAL_IMPORTS_COPY.settlesManyTitle, questions: settles });
  }
  const kinds = [...KIND_ORDER, ...new Set(rest.map((q) => q.kind).filter((k) => !(KIND_ORDER as readonly string[]).includes(k)))];
  for (const kind of kinds) {
    const qs = blockingFirst(rest.filter((q) => q.kind === kind));
    if (qs.length) sections.push({ id: `kind-${kind}`, title: KIND_LABEL[kind] ?? kind, questions: qs });
  }
  return sections;
}

/** A value as text, for display only (never sent back). */
export function shownValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

/** The text sent as an answer for a suggestion's value (the server types it). */
export function answerText(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value);
}

/** Every scope key a write with `only` may name: a group or run, never the whole beamtime. */
export function perGroupScopes(q: LocalQuestion): LocalScope[] {
  return q.display.scopes.filter((s) => s.kind !== 'experiment');
}

/** Map target ids to the scopes (with run names) the question lists them under. */
export function describeTargets(q: LocalQuestion, ids: string[]): { scope: LocalScope | null; ids: string[] }[] {
  const out: { scope: LocalScope | null; ids: string[] }[] = [];
  const wanted = new Set(ids);
  const placed = new Set<string>();
  for (const s of q.display.scopes) {
    const mine = (q.per_scope_targets[s.scope] ?? []).filter((id) => wanted.has(id));
    if (mine.length) {
      out.push({ scope: s, ids: mine });
      mine.forEach((id) => placed.add(id));
    }
  }
  const rest = ids.filter((id) => !placed.has(id));
  if (rest.length) out.push({ scope: null, ids: rest });
  return out;
}

/** The IANA zone names this browser knows, for the clock-zone suggestion list. Empty when unknown. */
export function ianaZones(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  try {
    return typeof intl.supportedValuesOf === 'function' ? intl.supportedValuesOf('timeZone') : [];
  } catch {
    return [];
  }
}

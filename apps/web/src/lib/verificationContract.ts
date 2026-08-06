/*
 * Record Verification — the WIRE CONTRACT for `GET /api/runtime/verification`,
 * its decoder, and the pure derivations the section renders from.
 *
 * ── Why the types live here and not in `lib/types.ts` ───────────────────────
 *
 * The precedent is `lib/graphDeep.ts`, whose own header states it: a layer that
 * ships a wire shape AND its decoder stays one self-contained module rather than
 * splitting the shape away from the code that validates it. `lib/types.ts` holds
 * bare interfaces with no runtime guard, and a bare interface is exactly what a
 * fail-closed decoder must not rely on — TypeScript erases at build time and the
 * wire does not.
 *
 * ── THE PARITY RULE ────────────────────────────────────────────────────────
 *
 * The backend projects every block of this response onto a FROZEN allowlist; an
 * unlisted key on the success path raises there and degrades into the failure
 * envelope. The key sets below are this side's copy of those allowlists, and
 * `__tests__/verification-contract.test.ts` pins each one against a literal list.
 * That is the whole point: if the backend adds, renames or drops a key, a test
 * here fails loudly instead of a figure silently going blank on screen.
 *
 * ── WHAT THIS MODULE WILL NOT DO ───────────────────────────────────────────
 *
 *   · It never substitutes a zero. A block that did not arrive, or arrived in a
 *     shape this decoder cannot read, makes the whole report unreadable — the
 *     section then says so. "0 records failing" and "we could not read the
 *     report" are different statements and only one of them was measured.
 *   · It never treats a non-`ok` status as data. The failure envelope carries
 *     null blocks by construction (the backend projects it non-strictly), so a
 *     decoder that read them optimistically would render nulls as absences and
 *     absences as good news.
 *   · It never widens a safeguard. `"not_applicable"` is carried through as its
 *     own state, all the way to the rendered string. See {@link SAFEGUARD_STATES}.
 */

/* ---- envelope ---------------------------------------------------------- */

/**
 * The report format this build understands. A response announcing a different
 * one is NOT rendered — see {@link readVerificationBody}. Bumping this without
 * updating the blocks below would mean rendering a payload whose meaning we have
 * not checked.
 */
export const VERIFICATION_REPORT_FORMAT_VERSION = 2;

/** The occurrence floor the backend suppresses beneath. Disclosed, never hidden. */
export const VERIFICATION_HISTOGRAM_FLOOR = 5;

/** Every `status` the envelope may carry. */
export const VERIFICATION_STATUSES = Object.freeze([
  'ok',
  'error',
  'unavailable',
  'refused',
  'running',
] as const);
export type VerificationStatus = (typeof VERIFICATION_STATUSES)[number];

/**
 * Every `verification_mode` this phase ships. A CLOSED enum on the wire, and
 * rendered VERBATIM by the UI as a disclosure of which corpus was evaluated —
 * so an unfamiliar value is displayed as it arrived rather than mapped onto a
 * friendly word this build cannot justify.
 */
export const VERIFICATION_MODES = Object.freeze(['public_upstream_corpus'] as const);
export type VerificationMode = (typeof VERIFICATION_MODES)[number];

export const VERIFICATION_ENVELOPE_KEYS = Object.freeze([
  'status',
  'report_format_version',
  'schema_version',
  'schema_fingerprint',
  'metadata',
  'corpus',
  'official_validation',
  'format_shadow',
  'mutations',
  'oracles',
  'safeguards',
  'limitations',
] as const);

export const VERIFICATION_METADATA_KEYS = Object.freeze([
  'generated_at',
  'duration_ms',
  'corpus_size',
  'cache_age_seconds',
  'verification_mode',
] as const);

export const VERIFICATION_CORPUS_KEYS = Object.freeze([
  'records_scanned',
  'records_passing_baseline',
  'records_failing_baseline',
] as const);

export const VERIFICATION_OFFICIAL_VALIDATION_KEYS = Object.freeze([
  'passing',
  'failing',
] as const);

export const VERIFICATION_FORMAT_SHADOW_KEYS = Object.freeze([
  'records_passing',
  'records_failing',
  'failures_by_error_code',
  'failures_by_schema_path',
] as const);

export const VERIFICATION_HISTOGRAM_KEYS = Object.freeze([
  'cells',
  'suppressed_categories',
  'suppressed_total',
  'floor',
] as const);

/** Verbatim the backend's `corpus_mutation._MUTATION_KEYS`, in its order. */
export const VERIFICATION_MUTATION_KEYS = Object.freeze([
  'operators_defined',
  'trials_attempted',
  'trials_applicable',
  'trials_skipped_not_applicable',
  'expected_outcome_matches',
  'unexpected_outcomes',
  'observation_only_trials',
] as const);

/** Verbatim the backend's `corpus_mutation._ORACLE_KEYS`, in its order. */
export const VERIFICATION_ORACLE_KEYS = Object.freeze([
  'source_mutation_failures',
  'restoration_failures',
  'repeatability_failures',
  'ordering_instability_failures',
  'no_guessing_failures',
  'workflow_consistency_failures',
  'engine_disagreements',
] as const);

/**
 * The six TRI-STATE safeguards. `dml_statements` and `ddl_statements` are counts
 * and are listed separately below, because rendering a number through the
 * tri-state path is how a count of 0 would acquire the word "verified".
 */
export const VERIFICATION_SAFEGUARD_STATE_KEYS = Object.freeze([
  'transaction_read_only',
  'parameterized_queries_only',
  'source_records_modified',
  'private_values_exposed',
  'official_validator_unchanged',
  'export_gating_unchanged',
] as const);

/** The two safeguards that arrive as counts rather than as a state word. */
export const VERIFICATION_SAFEGUARD_COUNT_KEYS = Object.freeze([
  'dml_statements',
  'ddl_statements',
] as const);

/** The whole `safeguards` block, in the order the backend declares it. */
export const VERIFICATION_SAFEGUARD_KEYS = Object.freeze([
  'transaction_read_only',
  'parameterized_queries_only',
  'dml_statements',
  'ddl_statements',
  'source_records_modified',
  'private_values_exposed',
  'official_validator_unchanged',
  'export_gating_unchanged',
] as const);

/**
 * The three values a tri-state safeguard may take. **Never a bare `true`**, and
 * `"not_applicable"` is never folded into `"verified"` at any point between the
 * wire and the screen.
 *
 * This is the single most consequential rule in this module. A safeguard that
 * says "read-only transaction: verified" when no transaction was ever opened is
 * the exact class of claim this project has shipped and corrected repeatedly
 * (`CLAUDE.md` §15). The decoder keeps the three states distinct, and
 * {@link safeguardStateLabel} renders a different WORD for each, so no code path
 * can collapse them by accident.
 */
export const SAFEGUARD_STATES = Object.freeze([
  'verified',
  'not_applicable',
  'unverified',
] as const);
export type SafeguardState = (typeof SAFEGUARD_STATES)[number];

export type SafeguardStateKey = (typeof VERIFICATION_SAFEGUARD_STATE_KEYS)[number];
export type SafeguardCountKey = (typeof VERIFICATION_SAFEGUARD_COUNT_KEYS)[number];
export type MutationKey = (typeof VERIFICATION_MUTATION_KEYS)[number];
export type OracleKey = (typeof VERIFICATION_ORACLE_KEYS)[number];

/* ---- the decoded shapes ------------------------------------------------ */

export interface VerificationHistogramCell {
  key: string;
  count: number;
}

export interface VerificationHistogram {
  cells: readonly VerificationHistogramCell[];
  /** HOW MANY keys were withheld — never which. */
  suppressed_categories: number;
  /** How many occurrences those withheld keys account for. */
  suppressed_total: number;
  floor: number;
}

export interface VerificationMetadata {
  generated_at: string;
  duration_ms: number;
  corpus_size: number;
  cache_age_seconds: number;
  /** Rendered verbatim. Typed as `string`, not the enum: the wire is not ours. */
  verification_mode: string;
}

export interface VerificationCorpus {
  records_scanned: number;
  records_passing_baseline: number;
  records_failing_baseline: number;
}

export interface VerificationOfficialValidation {
  passing: number;
  failing: number;
}

export interface VerificationFormatShadow {
  records_passing: number;
  records_failing: number;
  failures_by_error_code: VerificationHistogram;
  failures_by_schema_path: VerificationHistogram;
}

export type VerificationMutations = Record<MutationKey, number>;
export type VerificationOracles = Record<OracleKey, number>;

export interface VerificationSafeguards {
  transaction_read_only: SafeguardState;
  parameterized_queries_only: SafeguardState;
  dml_statements: number;
  ddl_statements: number;
  source_records_modified: SafeguardState;
  private_values_exposed: SafeguardState;
  official_validator_unchanged: SafeguardState;
  export_gating_unchanged: SafeguardState;
}

/** A fully readable `status: "ok"` report. Every block present and well typed. */
export interface VerificationReport {
  status: 'ok';
  report_format_version: number;
  schema_version: string | null;
  schema_fingerprint: string | null;
  metadata: VerificationMetadata;
  corpus: VerificationCorpus;
  official_validation: VerificationOfficialValidation;
  format_shadow: VerificationFormatShadow;
  mutations: VerificationMutations;
  oracles: VerificationOracles;
  safeguards: VerificationSafeguards;
  limitations: readonly string[];
}

/**
 * What the section may render, decided once, here.
 *
 * `notReady` carries the wire status verbatim so the UI can say which one it
 * received; `unreadable` carries WHY the body could not be used. Neither is a
 * report, and neither may be rendered as figures — that is the whole reason this
 * is a discriminated union rather than a partially-filled report object.
 */
export type VerificationView =
  | { kind: 'report'; report: VerificationReport }
  | { kind: 'notReady'; status: Exclude<VerificationStatus, 'ok'> }
  | { kind: 'unreadable'; reason: 'format_version' | 'malformed'; formatVersion: number | null };

/* ---- decoding ---------------------------------------------------------- */

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * A finite, non-negative count, or `null`.
 *
 * Every quantity in this report is a count of something. A negative or
 * non-finite one is a malformed body, not a small number, so it is rejected
 * rather than clamped — clamping would draw a bar for a figure nobody measured.
 */
function countOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

function nonEmptyStringOrNull(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

export function isSafeguardState(value: unknown): value is SafeguardState {
  return typeof value === 'string' && (SAFEGUARD_STATES as readonly string[]).includes(value);
}

/** Read a block of plain counts keyed by a frozen allowlist. `null` if any is bad. */
function readCounts<K extends string>(
  value: unknown,
  keys: readonly K[],
): Record<K, number> | null {
  if (!isObject(value)) return null;
  const out = {} as Record<K, number>;
  for (const key of keys) {
    const n = countOrNull(value[key]);
    if (n === null) return null;
    out[key] = n;
  }
  return out;
}

function readHistogram(value: unknown): VerificationHistogram | null {
  if (!isObject(value)) return null;
  const rawCells = value.cells;
  if (!Array.isArray(rawCells)) return null;
  const cells: VerificationHistogramCell[] = [];
  for (const raw of rawCells) {
    if (!isObject(raw)) return null;
    const key = nonEmptyStringOrNull(raw.key);
    const count = countOrNull(raw.count);
    if (key === null || count === null) return null;
    cells.push({ key, count });
  }
  const scalars = readCounts(value, ['suppressed_categories', 'suppressed_total', 'floor']);
  if (scalars === null) return null;
  return {
    cells,
    suppressed_categories: scalars.suppressed_categories,
    suppressed_total: scalars.suppressed_total,
    floor: scalars.floor,
  };
}

function readMetadata(value: unknown): VerificationMetadata | null {
  if (!isObject(value)) return null;
  const generatedAt = nonEmptyStringOrNull(value.generated_at);
  const mode = nonEmptyStringOrNull(value.verification_mode);
  const scalars = readCounts(value, ['duration_ms', 'corpus_size', 'cache_age_seconds']);
  if (generatedAt === null || mode === null || scalars === null) return null;
  return {
    generated_at: generatedAt,
    verification_mode: mode,
    duration_ms: scalars.duration_ms,
    corpus_size: scalars.corpus_size,
    cache_age_seconds: scalars.cache_age_seconds,
  };
}

function readFormatShadow(value: unknown): VerificationFormatShadow | null {
  if (!isObject(value)) return null;
  const counts = readCounts(value, ['records_passing', 'records_failing']);
  const byErrorCode = readHistogram(value.failures_by_error_code);
  const bySchemaPath = readHistogram(value.failures_by_schema_path);
  if (counts === null || byErrorCode === null || bySchemaPath === null) return null;
  return {
    records_passing: counts.records_passing,
    records_failing: counts.records_failing,
    failures_by_error_code: byErrorCode,
    failures_by_schema_path: bySchemaPath,
  };
}

function readSafeguards(value: unknown): VerificationSafeguards | null {
  if (!isObject(value)) return null;
  const counts = readCounts(value, VERIFICATION_SAFEGUARD_COUNT_KEYS);
  if (counts === null) return null;
  const states = {} as Record<SafeguardStateKey, SafeguardState>;
  for (const key of VERIFICATION_SAFEGUARD_STATE_KEYS) {
    const state = value[key];
    // A safeguard this build does not recognise is a malformed body, NOT an
    // "unverified" it is safe to display: silently downgrading an unknown token
    // would let a future `"assumed"` render as a cautionary word we chose.
    if (!isSafeguardState(state)) return null;
    states[key] = state;
  }
  return { ...states, ...counts };
}

/**
 * Decode a response body into exactly one of the three things the section may
 * show. Total, pure, and fail-closed: anything not fully understood becomes
 * `unreadable`, never a partially-drawn report.
 */
export function readVerificationBody(body: unknown): VerificationView {
  if (!isObject(body)) return { kind: 'unreadable', reason: 'malformed', formatVersion: null };

  const formatVersion = countOrNull(body.report_format_version);
  const status = body.status;
  if (typeof status !== 'string' || !(VERIFICATION_STATUSES as readonly string[]).includes(status)) {
    return { kind: 'unreadable', reason: 'malformed', formatVersion };
  }
  if (formatVersion !== VERIFICATION_REPORT_FORMAT_VERSION) {
    return { kind: 'unreadable', reason: 'format_version', formatVersion };
  }
  if (status !== 'ok') {
    return { kind: 'notReady', status: status as Exclude<VerificationStatus, 'ok'> };
  }

  const metadata = readMetadata(body.metadata);
  const corpus = readCounts(body.corpus, VERIFICATION_CORPUS_KEYS);
  const official = readCounts(body.official_validation, VERIFICATION_OFFICIAL_VALIDATION_KEYS);
  const formatShadow = readFormatShadow(body.format_shadow);
  const mutations = readCounts(body.mutations, VERIFICATION_MUTATION_KEYS);
  const oracles = readCounts(body.oracles, VERIFICATION_ORACLE_KEYS);
  const safeguards = readSafeguards(body.safeguards);
  if (
    metadata === null ||
    corpus === null ||
    official === null ||
    formatShadow === null ||
    mutations === null ||
    oracles === null ||
    safeguards === null
  ) {
    return { kind: 'unreadable', reason: 'malformed', formatVersion };
  }

  // `limitations` is prose the report supplies about itself. A missing array is
  // an empty one rather than a decode failure: it withholds a disclosure, it
  // does not corrupt a figure.
  const limitations = Array.isArray(body.limitations)
    ? body.limitations.filter((entry): entry is string => typeof entry === 'string')
    : [];

  return {
    kind: 'report',
    report: {
      status: 'ok',
      report_format_version: formatVersion,
      schema_version: nonEmptyStringOrNull(body.schema_version),
      schema_fingerprint: nonEmptyStringOrNull(body.schema_fingerprint),
      metadata,
      corpus,
      official_validation: official,
      format_shadow: formatShadow,
      mutations,
      oracles,
      safeguards,
      limitations,
    },
  };
}

/* ---- derivations ------------------------------------------------------- */

/** One category and its count, in the shape `StatsCharts` rows take. */
export interface VerificationChartRow {
  key: string;
  label: string;
  value: number;
}

/**
 * The two-segment composition of ONE validator's result over the records it
 * examined. Passing and failing are mutually exclusive and exhaustive there, so
 * they genuinely sum to a whole — which is what earns the stacked form.
 */
export function validatorSplit(passing: number, failing: number): {
  rows: VerificationChartRow[];
  total: number;
} {
  return {
    rows: [
      { key: 'passing', label: 'Passing', value: passing },
      { key: 'failing', label: 'Not Passing', value: failing },
    ],
    total: passing + failing,
  };
}

/** Histogram cells as chart rows, in the order the backend sorted them. */
export function histogramRows(histogram: VerificationHistogram): VerificationChartRow[] {
  return histogram.cells.map((cell) => ({ key: cell.key, label: cell.key, value: cell.count }));
}

/**
 * The denominator a histogram's shares are taken against: the occurrences it
 * SHOWS plus the occurrences it withholds.
 *
 * Using the shown sum alone would make the visible categories add to 100% and
 * quietly erase the withheld ones from the arithmetic — the numbers would then
 * contradict the suppression note printed beside them.
 */
export function histogramTotal(histogram: VerificationHistogram): number {
  return (
    histogram.cells.reduce((sum, cell) => sum + cell.count, 0) + histogram.suppressed_total
  );
}

/**
 * The mandatory visible disclosure when a histogram withheld anything, or `null`
 * when it withheld nothing.
 *
 * Says HOW MANY and WHY, never which — the withheld keys are not in the payload
 * and there is no place in this UI where they could be.
 */
export function suppressionDisclosure(histogram: VerificationHistogram): string | null {
  const categories = histogram.suppressed_categories;
  if (categories <= 0) return null;
  const noun = categories === 1 ? 'category is' : 'categories are';
  return (
    `${categories} further ${noun} withheld, each occurring fewer than ` +
    `${histogram.floor} times, accounting for ${histogram.suppressed_total} of the ` +
    `${histogramTotal(histogram)} occurrences counted.`
  );
}

/** A labelled figure row, already formatted for display. */
export interface VerificationFigure {
  key: string;
  label: string;
  value: number;
}

/**
 * The mutation harness in THREE groups, labelled in plain words.
 *
 * The split is the point. "12 trials matched what the change was designed to
 * cause" and "0 trials did something we did not expect" are opposite kinds of
 * news, and a single list of seven counts makes them look alike.
 */
export interface MutationGroups {
  /** How much was attempted, and how much of it applied at all. */
  coverage: VerificationFigure[];
  /** Changes that produced exactly the outcome they were designed to produce. */
  expected: VerificationFigure[];
  /** Anything that did not. */
  unexpected: VerificationFigure[];
}

export function mutationGroups(mutations: VerificationMutations): MutationGroups {
  return {
    coverage: [
      { key: 'operators_defined', label: 'Change Types Defined', value: mutations.operators_defined },
      { key: 'trials_attempted', label: 'Trials Attempted', value: mutations.trials_attempted },
      { key: 'trials_applicable', label: 'Trials That Applied', value: mutations.trials_applicable },
      {
        key: 'trials_skipped_not_applicable',
        label: 'Trials Skipped as Not Applicable',
        value: mutations.trials_skipped_not_applicable,
      },
    ],
    expected: [
      {
        key: 'expected_outcome_matches',
        label: 'Trials That Behaved as Designed',
        value: mutations.expected_outcome_matches,
      },
      {
        key: 'observation_only_trials',
        label: 'Trials Recorded Without an Expected Outcome',
        value: mutations.observation_only_trials,
      },
    ],
    unexpected: [
      {
        key: 'unexpected_outcomes',
        label: 'Trials That Behaved Unexpectedly',
        value: mutations.unexpected_outcomes,
      },
    ],
  };
}

/**
 * Plain-English names for the harness self-checks the backend calls oracles.
 *
 * "Oracle" is the harness's own word and it means nothing to a scientist reading
 * this screen, so it is glossed in the section copy and never used as a row
 * label. Each row is a COUNT OF TRIALS that tripped that check, so 0 is the
 * expected and good reading.
 */
export const ORACLE_LABELS: Readonly<Record<OracleKey, string>> = Object.freeze({
  source_mutation_failures: 'Source Records Altered by the Run',
  restoration_failures: 'Records Not Restored After a Trial',
  repeatability_failures: 'Repeat Runs That Disagreed',
  ordering_instability_failures: 'Results That Depended on Order',
  no_guessing_failures: 'No-Guessing Breaches',
  workflow_consistency_failures: 'Workflow Inconsistencies',
  engine_disagreements: 'Validation Engine Disagreements',
});

export function oracleFigures(oracles: VerificationOracles): VerificationFigure[] {
  return VERIFICATION_ORACLE_KEYS.map((key) => ({
    key,
    label: ORACLE_LABELS[key],
    value: oracles[key],
  }));
}

/** The sum of every harness self-check count. 0 is the calm, expected reading. */
export function oracleTotal(oracles: VerificationOracles): number {
  return VERIFICATION_ORACLE_KEYS.reduce((sum, key) => sum + oracles[key], 0);
}

/* ---- safeguards -------------------------------------------------------- */

export const SAFEGUARD_LABELS: Readonly<Record<SafeguardStateKey | SafeguardCountKey, string>> =
  Object.freeze({
    transaction_read_only: 'Read-Only Database Access',
    parameterized_queries_only: 'Parameterized Database Queries',
    dml_statements: 'Statements That Would Change Data',
    ddl_statements: 'Statements That Would Change Structure',
    source_records_modified: 'Source Records Left Unchanged',
    private_values_exposed: 'No Record Values in This Report',
    official_validator_unchanged: 'Official Validator Unchanged',
    export_gating_unchanged: 'Export Gate Unchanged',
  });

/**
 * The WORD each state renders as. Three different words for three different
 * states, so nothing in the UI can render `not_applicable` as "verified" without
 * this table saying so.
 */
export const SAFEGUARD_STATE_LABELS: Readonly<Record<SafeguardState, string>> = Object.freeze({
  verified: 'Verified',
  not_applicable: 'Not applicable',
  unverified: 'Unverified',
});

export function safeguardStateLabel(state: SafeguardState): string {
  return SAFEGUARD_STATE_LABELS[state];
}

/**
 * The sentence beneath each safeguard.
 *
 * `not_applicable` gets a per-safeguard REASON, because the bare words "not
 * applicable" leave a reader to guess whether the check was skipped or the
 * situation never arose — and those are very different. The two database
 * safeguards say the specific thing that is true of them in this mode: this run
 * opened no connection, so there was no transaction to keep read-only and no
 * query to parameterize.
 *
 * SCOPED TO THE RUN, deliberately. It must not read as "this deployment has no
 * database" — `apps/api/isaac_api/db_recon.py` does connect from the pod, and
 * `CLAUDE.md` §15 requires the honest form "no connection was opened here"
 * rather than a claim that the database has never been contacted. The sweep in
 * `db-recon-truthfulness.test.tsx` enforces exactly this and caught an earlier
 * draft of the sentence below.
 *
 * `verified` says the check RAN and found nothing, which is what the backend
 * means by it — not "we assume so".
 */
export function safeguardDetail(key: SafeguardStateKey, state: SafeguardState): string {
  if (state === 'verified') return 'This check ran and found nothing to report.';
  if (state === 'unverified') {
    return 'This check did not run, so nothing here states that it holds.';
  }
  if (key === 'transaction_read_only' || key === 'parameterized_queries_only') {
    return 'Not applicable — this run did not open a database connection.';
  }
  return 'Not applicable — this check does not apply to the corpus that was evaluated.';
}

export type SafeguardTone = 'good' | 'neutral' | 'attention';

/**
 * The tone a state carries. DECORATION ONLY: the state word and the sentence
 * beside it say the same thing in words, so every safeguard is fully readable
 * with all colour removed.
 *
 * `not_applicable` is `neutral`, never `good`. It is neither reassuring nor
 * alarming, and giving it the affirmative colour is how the affirmative reading
 * gets smuggled back in after the word was carefully kept out.
 */
export function safeguardTone(state: SafeguardState): SafeguardTone {
  if (state === 'verified') return 'good';
  if (state === 'unverified') return 'attention';
  return 'neutral';
}

/** One rendered safeguard row. Pure — the component does no branching of its own. */
export interface SafeguardRow {
  key: SafeguardStateKey;
  label: string;
  state: SafeguardState;
  stateLabel: string;
  detail: string;
  tone: SafeguardTone;
}

export function safeguardRows(safeguards: VerificationSafeguards): SafeguardRow[] {
  return VERIFICATION_SAFEGUARD_STATE_KEYS.map((key) => {
    const state = safeguards[key];
    return {
      key,
      label: SAFEGUARD_LABELS[key],
      state,
      stateLabel: safeguardStateLabel(state),
      detail: safeguardDetail(key, state),
      tone: safeguardTone(state),
    };
  });
}

/** One rendered safeguard COUNT row. A count of 0 is a calm good state. */
export interface SafeguardCountRow {
  key: SafeguardCountKey;
  label: string;
  value: number;
  tone: SafeguardTone;
}

export function safeguardCountRows(safeguards: VerificationSafeguards): SafeguardCountRow[] {
  return VERIFICATION_SAFEGUARD_COUNT_KEYS.map((key) => ({
    key,
    label: SAFEGUARD_LABELS[key],
    value: safeguards[key],
    tone: safeguards[key] === 0 ? ('good' as const) : ('attention' as const),
  }));
}

/* ---- display formatting ------------------------------------------------ */

/**
 * A run duration in milliseconds, as words.
 *
 * Sub-second durations keep their milliseconds; anything longer is stated in
 * seconds to one decimal, and anything past a minute in whole minutes and
 * seconds. Rounding is disclosed by the unit and never invents precision the
 * value did not have.
 */
export function formatDurationMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return 'Not Available';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} seconds`;
  const wholeMinutes = Math.floor(seconds / 60);
  const restSeconds = Math.round(seconds - wholeMinutes * 60);
  return `${wholeMinutes} min ${restSeconds} s`;
}

/** How old the cached report is, as words. Same rounding discipline as above. */
export function formatAgeSeconds(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return 'Not Available';
  if (seconds < 120) return `${Math.round(seconds)} seconds`;
  if (seconds < 7200) return `${Math.round(seconds / 60)} minutes`;
  return `${Math.round(seconds / 3600)} hours`;
}

/**
 * What the section says when the report is not a report.
 *
 * Every branch names the state the API actually reported. None of them implies a
 * figure: "the run is still in progress" and "0 records evaluated" are not the
 * same sentence, and only the first was observed.
 */
export function notReadyMessage(status: Exclude<VerificationStatus, 'ok'>): {
  title: string;
  body: string;
} {
  if (status === 'running') {
    return {
      title: 'Verification Run in Progress',
      body: 'A verification run is under way, so there are no results to state yet. No earlier result is shown in its place.',
    };
  }
  if (status === 'refused') {
    return {
      title: 'Verification Declined',
      body: 'This build declined to run the verification program, so it reports no result. Nothing is inferred from the refusal.',
    };
  }
  if (status === 'unavailable') {
    return {
      title: 'Verification Results Unavailable',
      body: 'This build reports no verification results. Nothing is shown in their place, and no count is assumed to be zero.',
    };
  }
  return {
    title: 'Verification Results Unavailable',
    body: 'The verification program reported an error and produced no result, so no figure from it is stated here.',
  };
}

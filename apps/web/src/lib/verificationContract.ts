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
export const VERIFICATION_REPORT_FORMAT_VERSION = 3;

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
 * Every `verification_mode` this phase ships. A CLOSED enum on the wire.
 *
 * Mirrors the backend's `authorization.verification_modes()`, which DERIVES the
 * tuple from an approval flag rather than declaring it. `public_reference` is
 * the public upstream example set and needs no authorization;
 * `authorized_private_sample` is the application's own datastore, read-only and
 * aggregate-only under the authorization recorded on 2026-08-05.
 *
 * THE WIRE TOKEN IS ALWAYS RENDERED, and a product label is rendered BESIDE it —
 * never instead of it. See {@link corpusDisclosure} for why both, and for what
 * happens to a member this build has no label for.
 */
export const VERIFICATION_MODES = Object.freeze([
  'public_reference',
  'authorized_private_sample',
] as const);
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
  /**
   * How many occurrences those withheld keys account for — or `null` when the
   * backend withheld that number as well.
   *
   * NULLABLE SINCE REPORT FORMAT 3, and the reason is the whole point of the
   * field. When exactly ONE category is withheld, the withheld occurrences are
   * that one category's exact count, and the key set here (schema paths, shadow
   * error codes) is enumerable from the public schema — so publishing the number
   * publishes the cell. `verification._histogram` therefore serves `null`, and
   * keeps `suppressed_categories` at its real value so the withholding is still
   * disclosed.
   *
   * `null` means WITHHELD, never zero. Nothing in this module may coerce it to
   * `0`, sum it as `0`, or render it as `"0"`, `"null"` or `"NaN"` — the backend
   * rejected zeroing it as a false claim and so does the UI.
   */
  suppressed_total: number | null;
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
  const scalars = readCounts(value, ['suppressed_categories', 'floor']);
  if (scalars === null) return null;
  /*
   * `suppressed_total` is read SEPARATELY from the other scalars because it is
   * the one field that may legitimately be `null` (report format 3 — see
   * {@link VerificationHistogram}). Running it through `readCounts` would
   * conflate two different bodies: an explicit `null`, which is a real value
   * meaning "withheld", and a missing or malformed field, which is a body this
   * decoder must refuse. The first is kept; the second still makes the whole
   * histogram unreadable, exactly as before.
   */
  const rawSuppressedTotal = value.suppressed_total;
  let suppressedTotal: number | null = null;
  if (rawSuppressedTotal !== null) {
    suppressedTotal = countOrNull(rawSuppressedTotal);
    if (suppressedTotal === null) return null;
  }
  return {
    cells,
    suppressed_categories: scalars.suppressed_categories,
    suppressed_total: suppressedTotal,
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

/*
 * `validatorSplit`: REMOVED, and this note is why.
 *
 * It returned ONE validator's passing/failing split for a stacked bar, and the
 * section drew two of them side by side. That form answers "what is this
 * validator's result made of" twice and never answers "how do the two
 * validators compare", which is the question a reader of this section actually
 * has. {@link validatorComparison} supersedes it with a grouped form on one
 * shared axis.
 *
 * DELETED rather than left unused, on the `StageBars` precedent in
 * `screens/statistics/StatsPrimitives.tsx`: a helper shaped exactly like the
 * superseded drawing, sitting in the module, is how the superseded drawing comes
 * back.
 */

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
export function histogramTotal(histogram: VerificationHistogram): number | null {
  /*
   * `null` when the withheld occurrences were themselves withheld, because the
   * denominator is then genuinely unknown — the shown sum plus an unstated
   * number. Falling back to the shown sum would print a total that is smaller
   * than the truth and make the visible shares add to 100%, which is the exact
   * erasure this function was written to prevent. `StatsBarChart` accepts a
   * `null` total and prints "Not Available" for every share.
   */
  if (histogram.suppressed_total === null) return null;
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
 *
 * TWO SENTENCES, because there are two facts to state. When the report also
 * withheld the occurrence COUNT (`suppressed_total === null`, report format 3),
 * the sentence says so and says why, rather than printing a number nobody sent
 * or quietly omitting the clause. An omitted clause reads as "and that is all
 * there is to say", which is the failure mode this whole disclosure exists for.
 */
export function suppressionDisclosure(histogram: VerificationHistogram): string | null {
  const categories = histogram.suppressed_categories;
  if (categories <= 0) return null;
  const noun = categories === 1 ? 'category is' : 'categories are';
  // "each occurring" reads wrong for a single category, and the single-category
  // body is now the one that matters most — it is the only one that reaches the
  // withheld-count branch below.
  const each = categories === 1 ? 'occurring' : 'each occurring';
  const opening = `${categories} further ${noun} withheld, ${each} fewer than ${histogram.floor} times`;
  const total = histogramTotal(histogram);
  if (histogram.suppressed_total === null || total === null) {
    /*
     * The REASON is stated only for the body that reason describes. The backend
     * withholds the count when exactly one category was withheld, and only then;
     * a report withholding it alongside several categories is a body this UI has
     * never seen, so it says what happened and does not explain a cause it
     * cannot vouch for. A confident wrong explanation is worse than none.
     */
    const why =
      categories === 1
        ? " With one category withheld from a set of keys that can be enumerated, that number would be that category's exact count."
        : '';
    return (
      `${opening}. The number of occurrences they account for is withheld as well, ` +
      `so the total counted here is not stated.${why}`
    );
  }
  return (
    `${opening}, accounting for ${histogram.suppressed_total} of the ` +
    `${total} occurrences counted.`
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

/* ---- which corpus ran -------------------------------------------------- */

/**
 * The product name for each mode, and the single highest-stakes string in this
 * module.
 *
 * A public-corpus result presented as if it came from the authorized sample —
 * or the reverse — is a false statement about WHICH RECORDS were evaluated, and
 * every figure on the screen inherits it. The two labels therefore share no
 * word: "preflight" against "reference sample", "Public" against "Authorized".
 * `__tests__/record-verification.test.tsx` pins both strings and pins that
 * neither appears while the other mode is being reported.
 *
 * ── ONE FIGURE IN A LABEL, AND IT IS NOT MEASURED ──────────────────────────
 *
 * "30-record" is authored copy, not a reading. The report's own measurement of
 * how many records were evaluated is `metadata.corpus_size`, and the section
 * renders that separately and adjacently, so the two can be COMPARED by a
 * reader rather than reconciled by this file. {@link corpusSizeMismatch} states
 * the disagreement out loud when they differ; nothing here quietly rewrites
 * either number to agree with the other.
 */
export const VERIFICATION_MODE_LABELS: Readonly<Record<VerificationMode, string>> = Object.freeze({
  public_reference: 'Public reference preflight',
  authorized_private_sample: 'Authorized 30-record reference sample',
});

/**
 * One sentence saying what each corpus IS.
 *
 * Both are scoped to the run. Neither claims anything about the deployment: the
 * public-mode sentence says this run read the vendored public examples, not that
 * no database exists anywhere — `CLAUDE.md` §15 requires that distinction, and
 * `db-recon-truthfulness.test.tsx` sweeps this file's strings for it.
 */
export const VERIFICATION_MODE_DESCRIPTIONS: Readonly<Record<VerificationMode, string>> =
  Object.freeze({
    public_reference:
      /*
       * "this run did not open a database connection", NOT "no database
       * connection was opened" and NOT "there is no database". The phrasing is
       * the same one `safeguardDetail` uses below and for the same reason:
       * `CLAUDE.md` §15 requires the run-scoped form, because `db_recon.py` DOES
       * reach a datastore from the pod. `db-recon-truthfulness.test.tsx` sweeps
       * this file's strings for the flat form and rejects it.
       */
      'The public upstream ISAAC example records vendored in this repository. They are already ' +
      'published, so no approval is needed to read them, and this run did not open a database ' +
      'connection to reach them.',
    authorized_private_sample:
      'A read-only, aggregate-only pass over the records this application holds in its own ' +
      'datastore, under the approval recorded on 2026-08-05. Every figure below is a total ' +
      'across the corpus: no record identifier, title, field value or per-record outcome is in ' +
      'the report, so none can appear on this screen.',
  });

export function isVerificationMode(value: string): value is VerificationMode {
  return (VERIFICATION_MODES as readonly string[]).includes(value);
}

/** What the section states about the corpus. The token is always carried. */
export interface CorpusDisclosure {
  /** The `verification_mode` exactly as it arrived. Rendered verbatim, always. */
  mode: string;
  /** The product name, or the raw token when this build has no label for it. */
  label: string;
  /** `false` when the wire carried a mode this build was not written against. */
  known: boolean;
  description: string;
}

/**
 * The corpus disclosure for a mode.
 *
 * An UNRECOGNISED mode is not an error and is not guessed at: the token becomes
 * its own label and the description says plainly that this build cannot name the
 * corpus. Mapping an unknown member onto either shipped label is the one failure
 * this function exists to make impossible — the wrong one of two labels is worse
 * than no label, because it reads as a measurement of a corpus nobody read.
 */
export function corpusDisclosure(mode: string): CorpusDisclosure {
  if (isVerificationMode(mode)) {
    return {
      mode,
      label: VERIFICATION_MODE_LABELS[mode],
      known: true,
      description: VERIFICATION_MODE_DESCRIPTIONS[mode],
    };
  }
  return {
    mode,
    label: mode,
    known: false,
    description:
      'This build has no description for that corpus, so the value is shown exactly as it ' +
      'arrived and nothing is claimed about which records were evaluated.',
  };
}

/**
 * The disagreement between an authored label and a measured count, or `null`.
 *
 * Only `authorized_private_sample` carries a figure in its name. If the report
 * says it evaluated a different number, BOTH numbers are stated and the label is
 * not silently rewritten — the mismatch is a fact about the run worth surfacing,
 * and picking one number to display would hide it.
 */
export const AUTHORIZED_SAMPLE_LABELLED_SIZE = 30;

export function corpusSizeMismatch(mode: string, corpusSize: number): string | null {
  if (mode !== 'authorized_private_sample') return null;
  if (corpusSize === AUTHORIZED_SAMPLE_LABELLED_SIZE) return null;
  return (
    `This corpus is named for ${AUTHORIZED_SAMPLE_LABELLED_SIZE} records, and the report states ` +
    `that it evaluated ${corpusSize}. Both figures are shown as they stand; neither has been ` +
    'adjusted to match the other.'
  );
}

/* ---- freshness --------------------------------------------------------- */

/**
 * The backend's own cache lifetime for a report, in seconds
 * (`verification.CACHE_TTL_SECONDS`). Past it the next request triggers a
 * recomputation and is answered with the OLD result — deliberately, because a
 * slightly old measurement beats a blank panel. This constant is what lets the
 * UI say which of those two a reader is looking at.
 */
export const VERIFICATION_CACHE_TTL_SECONDS = 3600;

export type ReportFreshness = 'fresh' | 'stale';

export function reportFreshness(cacheAgeSeconds: number): ReportFreshness {
  return cacheAgeSeconds >= VERIFICATION_CACHE_TTL_SECONDS ? 'stale' : 'fresh';
}

/* ---- the two validators, side by side ---------------------------------- */

/** The two outcomes each validator reports, in the order they are drawn. */
export const VALIDATOR_SERIES = Object.freeze([
  { key: 'passing', label: 'Passing' },
  { key: 'failing', label: 'Not Passing' },
] as const);

export interface ValidatorComparisonGroup {
  key: 'official' | 'shadow';
  label: string;
  /** What this validator is, in one clause. Non-colour identity for the group. */
  role: string;
  passing: number;
  failing: number;
  /** THIS validator's own whole. The two groups' totals are not assumed equal. */
  total: number;
}

/**
 * The official validator and the format shadow as two comparable groups.
 *
 * GROUPED, not summed. Each group's passing and not-passing partition that
 * validator's OWN total, and the two totals are separate numbers that this
 * function never adds together — the shadow examines the same corpus but the
 * report states its denominator independently, so a build that combined them
 * would invent a whole nobody measured.
 */
export function validatorComparison(
  official: VerificationOfficialValidation,
  shadow: VerificationFormatShadow,
): [ValidatorComparisonGroup, ValidatorComparisonGroup] {
  return [
    {
      key: 'official',
      label: 'Official Validation',
      role: "ISAAC's own validator — the authority on whether a record is valid.",
      passing: official.passing,
      failing: official.failing,
      total: official.passing + official.failing,
    },
    {
      key: 'shadow',
      label: 'Format Shadow',
      role: 'A stricter second validator, run alongside. It decides nothing and gates nothing.',
      passing: shadow.records_passing,
      failing: shadow.records_failing,
      total: shadow.records_passing + shadow.records_failing,
    },
  ];
}

/**
 * The comparison as one sentence — the text equivalent of the grouped chart.
 *
 * States each group's own denominator explicitly, so the sentence cannot be read
 * as two shares of one total.
 */
export function validatorComparisonSummary(groups: readonly ValidatorComparisonGroup[]): string {
  const clauses = groups.map(
    (group) =>
      `${group.label}: ${group.passing} of ${group.total} records passing, ` +
      `${group.failing} not passing`,
  );
  return `${clauses.join('; ')}. Each validator's figures are counted against its own total.`;
}

/* ---- mutation accounting, reconciled ----------------------------------- */

/**
 * Short plain-word names for the mutation counts, keyed by the BACKEND'S OWN
 * key. Both are rendered: the words carry the meaning for a reader who has never
 * seen the wire, the key is what makes a screen figure traceable to the field it
 * came from, and keeping them in one table is what stops the two drifting apart.
 */
export const MUTATION_SHORT_LABELS: Readonly<Record<MutationKey, string>> = Object.freeze({
  operators_defined: 'change types defined',
  trials_attempted: 'trials attempted',
  trials_applicable: 'trials that applied',
  trials_skipped_not_applicable: 'trials skipped as not applicable',
  expected_outcome_matches: 'trials that behaved as designed',
  unexpected_outcomes: 'trials that behaved unexpectedly',
  observation_only_trials: 'trials recorded without an expected outcome',
});

export interface MutationTerm {
  key: MutationKey;
  label: string;
  value: number;
}

/**
 * One accounting identity the harness's counts are expected to satisfy, with
 * everything needed to show it ON SCREEN rather than assert it in a comment.
 */
export interface MutationIdentity {
  key: 'attempted' | 'applicable';
  total: MutationTerm;
  parts: MutationTerm[];
  /** The parts as they actually add up. MEASURED, never assumed to equal `total`. */
  partsSum: number;
  balances: boolean;
  /** The arithmetic as a sentence, exactly as the counts stand. */
  statement: string;
}

function term(mutations: VerificationMutations, key: MutationKey): MutationTerm {
  return { key, label: MUTATION_SHORT_LABELS[key], value: mutations[key] };
}

/**
 * The two identities the harness's seven counts are supposed to satisfy:
 *
 *   trials_attempted  = trials_applicable + trials_skipped_not_applicable
 *   trials_applicable = expected_outcome_matches + unexpected_outcomes
 *                     + observation_only_trials
 *
 * `balances` is COMPUTED from the values, not declared. A report whose counts do
 * not add up is a real possibility and the section says so out loud rather than
 * drawing a tidy total that hides it — which is the entire reason the sum is
 * carried alongside the stated total instead of replacing it.
 */
export function mutationReconciliation(mutations: VerificationMutations): MutationIdentity[] {
  const build = (
    key: MutationIdentity['key'],
    totalKey: MutationKey,
    partKeys: readonly MutationKey[],
  ): MutationIdentity => {
    const total = term(mutations, totalKey);
    const parts = partKeys.map((partKey) => term(mutations, partKey));
    const partsSum = parts.reduce((sum, part) => sum + part.value, 0);
    const rhs = parts.map((part) => `${part.value} ${part.label}`).join(' + ');
    return {
      key,
      total,
      parts,
      partsSum,
      balances: partsSum === total.value,
      statement: `${total.value} ${total.label} = ${rhs}`,
    };
  };

  return [
    build('attempted', 'trials_attempted', [
      'trials_applicable',
      'trials_skipped_not_applicable',
    ]),
    build('applicable', 'trials_applicable', [
      'expected_outcome_matches',
      'unexpected_outcomes',
      'observation_only_trials',
    ]),
  ];
}

export function mutationsReconcile(mutations: VerificationMutations): boolean {
  return mutationReconciliation(mutations).every((identity) => identity.balances);
}

/** The sentence stated when an identity does not hold. Names both numbers. */
export function reconciliationMismatch(identity: MutationIdentity): string {
  return (
    `These do not add up: the parts total ${identity.partsSum}, and the report states ` +
    `${identity.total.value} ${identity.total.label}. Both figures are shown as they arrived.`
  );
}

/* ---- the withheld bucket ----------------------------------------------- */

/**
 * Did this histogram withhold anything at all?
 *
 * ONE PREDICATE, USED BY BOTH SIDES, because they used to disagree. The chart's
 * empty branch tested `suppressed_total === 0` while the row builder tested
 * `suppressed_total <= 0 && suppressed_categories <= 0`, so a histogram with no
 * cells, some withheld CATEGORIES and zero withheld OCCURRENCES took the empty
 * branch in one place and produced a withheld bar in the other. That body is
 * odd — categories withheld accounting for no occurrences — but it is a body the
 * wire permits, and two code paths disagreeing about it is how one of them ends
 * up drawing a bucket the other says does not exist.
 *
 * Either signal counts. Withholding is withholding, and the disclosure sentence
 * beside it states the categories and the occurrences separately anyway.
 *
 * A `null` `suppressed_total` (report format 3) contributes NOTHING to this
 * predicate on its own — `?? 0` — and that is deliberate rather than lazy. The
 * backend emits `null` only together with `suppressed_categories === 1`, so the
 * first arm already answers yes; and a body claiming zero withheld categories
 * has told us nothing was withheld, whatever the total says. What must never
 * happen is `null` being read here as a POSITIVE number of withheld occurrences,
 * which would make this say "withheld" for a histogram that withheld nothing.
 */
export function histogramWithheldAnything(histogram: VerificationHistogram): boolean {
  return histogram.suppressed_categories > 0 || (histogram.suppressed_total ?? 0) > 0;
}

/**
 * Nothing to draw: no category survived the floor AND nothing was withheld.
 *
 * The distinction matters. "No occurrence was recorded" and "every category was
 * too small to name" are different facts, and only the first justifies drawing
 * nothing at all.
 *
 * So a histogram with no cells, one withheld category and a withheld occurrence
 * count is NOT empty: it is a breakdown whose every category was withheld. It
 * has no bar to draw — see {@link histogramRowsWithSuppressed} — but it still
 * has something to say, and the caller must say it rather than reporting nothing
 * recorded.
 */
export function histogramIsEmpty(histogram: VerificationHistogram): boolean {
  return histogram.cells.length === 0 && !histogramWithheldAnything(histogram);
}

/**
 * The row key for the withheld bucket. Deliberately not a category name: the
 * withheld KEYS are not in the payload, so no code path here could render one
 * even by mistake, and this key cannot collide with a real category because no
 * schema path or error code has this shape.
 */
export const SUPPRESSED_ROW_KEY = '__withheld__';

export const SUPPRESSED_ROW_LABEL = 'Withheld (categories below the disclosure floor)';

/**
 * Histogram cells as chart rows, with the withheld occurrences as their OWN
 * final row when there are any.
 *
 * The bucket is drawn rather than only footnoted because the alternative reads
 * as a complete distribution that happens to have a caveat under it. It is one
 * aggregate row standing for however many categories were withheld — it names no
 * category, and it cannot, because the payload does not carry their names.
 */
export function histogramRowsWithSuppressed(
  histogram: VerificationHistogram,
): VerificationChartRow[] {
  const rows = histogramRows(histogram);
  if (!histogramWithheldAnything(histogram)) return rows;
  /*
   * NO BAR WHEN THERE IS NO NUMBER, and this is NOT the two-branch disagreement
   * the comment on {@link histogramWithheldAnything} records. That bug was two
   * places computing THE SAME question ("did it withhold anything?") by
   * different tests; both now call the one predicate above, and this check asks
   * a different question with a different answer type: "is there a quantity to
   * draw?". A bar needs a length, and `suppressed_total === null` means the
   * quantity was withheld — 0 would be a false claim (the backend refuses to
   * write it for exactly that reason) and a bar of unknown length is not a bar.
   *
   * Withholding is still disclosed, in two places that cannot drift from this
   * one: {@link histogramWithheldAnything} still answers `true`, so
   * {@link histogramIsEmpty} refuses to call the breakdown empty, and
   * {@link suppressionDisclosure} still returns its sentence, which in this case
   * states that the occurrence count itself was withheld.
   */
  if (histogram.suppressed_total === null) return rows;
  return [
    ...rows,
    {
      key: SUPPRESSED_ROW_KEY,
      label: SUPPRESSED_ROW_LABEL,
      value: histogram.suppressed_total,
    },
  ];
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
      /*
       * ONE WORD COVERS SEVERAL CAUSES, AND THE COPY SAYS SO.
       *
       * `verification._PROVIDER_STATUS` maps `not_run`, `unavailable` AND
       * `timeout` onto this single status, and the envelope that carries it has
       * no `metadata` block at all — so nothing on the wire tells this build
       * which of them happened, or even which corpus was being read. Naming the
       * possibilities without asserting one is the only honest reading; picking
       * the most likely would be a guess about an event nobody observed.
       */
      body:
        'This build reports no verification results. The report does not say which of several ' +
        'causes applies: the program may not have run, a source it needed may not have ' +
        'answered, or a read may have timed out — one status word covers all of them. Nothing ' +
        'is shown in their place, and no count is assumed to be zero.',
    };
  }
  return {
    title: 'Verification Results Unavailable',
    body: 'The verification program reported an error and produced no result, so no figure from it is stated here.',
  };
}

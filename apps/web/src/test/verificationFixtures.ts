/*
 * Record Verification — TEST-ONLY wire bodies.
 *
 * Every fixture here is a plain object shaped exactly as the authored wire
 * contract for `GET /api/runtime/verification` describes it, written by hand
 * rather than produced by the decoder. That is deliberate: a fixture built from
 * `readVerificationBody`'s own output would agree with the decoder even if both
 * were wrong, and the parity suite would stop detecting backend drift — the one
 * thing it exists to detect.
 *
 * The figures are invented for this suite and describe nothing real. They are
 * chosen so that no two counts are equal where the assertions depend on telling
 * two slots apart, and so that the format-shadow validator legitimately reports
 * MORE issues than the official one (it is the stricter of the two).
 *
 * Nothing here carries a record id, a title, a scientific value, a host, or a
 * path into a record — none of those exist in the contract, and a fixture that
 * invented a place for one would invite the UI to grow a slot for it.
 */

/** The default `status: "ok"` report. 30 records, one failing each validator. */
export const verificationReportOk = {
  status: 'ok',
  report_format_version: 2,
  schema_version: '1.05',
  schema_fingerprint: 'fb0c9d2a7e114c63',
  metadata: {
    generated_at: '2026-08-04T09:15:32Z',
    duration_ms: 8420,
    corpus_size: 30,
    cache_age_seconds: 645,
    verification_mode: 'public_upstream_corpus',
  },
  corpus: {
    records_scanned: 30,
    records_passing_baseline: 28,
    records_failing_baseline: 2,
  },
  official_validation: {
    passing: 28,
    failing: 2,
  },
  format_shadow: {
    records_passing: 19,
    records_failing: 11,
    failures_by_error_code: {
      cells: [
        { key: 'format', count: 14 },
        { key: 'pattern', count: 9 },
        { key: 'required', count: 6 },
      ],
      suppressed_categories: 3,
      suppressed_total: 7,
      floor: 5,
    },
    failures_by_schema_path: {
      cells: [
        { key: 'properties/dataset/properties/created', count: 12 },
        { key: 'properties/measurement/properties/uri', count: 8 },
      ],
      suppressed_categories: 2,
      suppressed_total: 5,
      floor: 5,
    },
  },
  mutations: {
    operators_defined: 17,
    trials_attempted: 510,
    trials_applicable: 402,
    trials_skipped_not_applicable: 108,
    expected_outcome_matches: 391,
    unexpected_outcomes: 0,
    observation_only_trials: 11,
  },
  oracles: {
    source_mutation_failures: 0,
    restoration_failures: 0,
    repeatability_failures: 0,
    ordering_instability_failures: 0,
    no_guessing_failures: 0,
    workflow_consistency_failures: 0,
    engine_disagreements: 0,
  },
  safeguards: {
    transaction_read_only: 'not_applicable',
    parameterized_queries_only: 'not_applicable',
    dml_statements: 0,
    ddl_statements: 0,
    source_records_modified: 'verified',
    private_values_exposed: 'verified',
    official_validator_unchanged: 'verified',
    export_gating_unchanged: 'verified',
  },
  limitations: [
    'This module opens no connection to any database and imports no driver; the ' +
      'corpus is supplied by the caller and, in this repository, is the public ' +
      'upstream example set.',
    'Counts are global scalars. Per-operator, per-category and per-record ' +
      'applicability breakdowns are deliberately absent.',
    'Zero self-check exceptions is evidence over the corpus actually evaluated, ' +
      'not a proof over all records or all changes.',
  ],
} as const;

/**
 * The same report with a harness self-check tripped and an unexpected trial.
 *
 * The bad-news case has to be a real fixture rather than an edit inside a test,
 * because the calm-zero rendering is only meaningful if the non-zero rendering
 * is visibly different — and nothing proves that if both are drawn from a body
 * whose every count is 0.
 */
export const verificationReportWithFindings = {
  ...verificationReportOk,
  mutations: { ...verificationReportOk.mutations, unexpected_outcomes: 3 },
  oracles: { ...verificationReportOk.oracles, repeatability_failures: 2 },
  safeguards: {
    ...verificationReportOk.safeguards,
    dml_statements: 1,
    export_gating_unchanged: 'unverified',
  },
};

/** A histogram that withheld nothing — the branch with no suppression note. */
export const verificationReportNoSuppression = {
  ...verificationReportOk,
  format_shadow: {
    ...verificationReportOk.format_shadow,
    failures_by_error_code: {
      cells: [{ key: 'format', count: 14 }],
      suppressed_categories: 0,
      suppressed_total: 0,
      floor: 5,
    },
  },
};

/**
 * The FAILURE ENVELOPE, verbatim in shape: the backend projects it non-strictly,
 * so every block it could not build arrives as `null` rather than as absent.
 * A decoder that read those nulls optimistically would render them as zeros.
 */
export const verificationFailureEnvelope = {
  status: 'unavailable',
  report_format_version: 2,
  schema_version: '1.05',
  schema_fingerprint: null,
  metadata: null,
  corpus: null,
  official_validation: null,
  format_shadow: null,
  mutations: null,
  oracles: null,
  safeguards: null,
  limitations: ['This build produced no verification result.'],
} as const;

/** A run that has not finished. Not an error, and pointedly not a zero. */
export const verificationRunningEnvelope = {
  ...verificationFailureEnvelope,
  status: 'running',
} as const;

/** A report announcing a format this build has not been checked against. */
export const verificationFutureFormat = {
  ...verificationReportOk,
  report_format_version: 3,
};

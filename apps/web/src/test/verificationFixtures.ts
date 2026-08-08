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
 * ── TWO INTERNAL CONSISTENCY RULES THESE FIXTURES NOW KEEP ─────────────────
 *
 * 1. THE CORPUS SIZE MATCHES THE MODE. `verificationReportOk` used to pair
 *    `corpus_size: 30` with `verification_mode: 'public_reference'`, which is
 *    not a body the backend can produce: the public corpus is the ten upstream
 *    examples vendored at `tests/fixtures/official/`
 *    (`verification.PUBLIC_CORPUS_DIR`), and 30 is the size of the OTHER
 *    corpus. A fixture that mixes the two teaches every assertion built on it
 *    that the pairing is possible — which is the specific confusion the corpus
 *    labelling exists to prevent. The public fixtures are now 10 records and
 *    the private-sample fixture is 30.
 *
 * 2. THE MUTATION COUNTS RECONCILE. `trials_attempted` equals
 *    `trials_applicable + trials_skipped_not_applicable`, and
 *    `trials_applicable` equals `expected_outcome_matches + unexpected_outcomes
 *    + observation_only_trials`. `verificationReportWithFindings` used to break
 *    the second identity by raising `unexpected_outcomes` without lowering
 *    anything, so the "bad news" fixture was also an arithmetic-failure fixture
 *    and neither could be tested without the other.
 *    `verificationReportUnbalancedMutations` exists to break it ON PURPOSE.
 *
 * Nothing here carries a record id, a title, a scientific value, a host, or a
 * path into a record — none of those exist in the contract, and a fixture that
 * invented a place for one would invite the UI to grow a slot for it.
 */

/**
 * The default `status: "ok"` report — the PUBLIC corpus, ten records, one
 * failing the official validator and four carrying at least one format issue.
 */
export const verificationReportOk = {
  status: 'ok',
  report_format_version: 3,
  schema_version: '1.05',
  schema_fingerprint: 'fb0c9d2a7e114c63',
  metadata: {
    generated_at: '2026-08-04T09:15:32Z',
    duration_ms: 8420,
    corpus_size: 10,
    cache_age_seconds: 645,
    verification_mode: 'public_reference',
  },
  corpus: {
    records_scanned: 10,
    records_passing_baseline: 9,
    records_failing_baseline: 1,
  },
  official_validation: {
    passing: 9,
    failing: 1,
  },
  format_shadow: {
    records_passing: 6,
    records_failing: 4,
    failures_by_error_code: {
      cells: [
        { key: 'format', count: 9 },
        { key: 'pattern', count: 7 },
        { key: 'required', count: 5 },
      ],
      suppressed_categories: 3,
      suppressed_total: 7,
      floor: 5,
    },
    failures_by_schema_path: {
      cells: [
        { key: 'properties/dataset/properties/created', count: 8 },
        { key: 'properties/measurement/properties/uri', count: 6 },
      ],
      suppressed_categories: 2,
      suppressed_total: 5,
      floor: 5,
    },
  },
  mutations: {
    operators_defined: 17,
    trials_attempted: 170,
    trials_applicable: 134,
    trials_skipped_not_applicable: 36,
    expected_outcome_matches: 128,
    unexpected_outcomes: 0,
    observation_only_trials: 6,
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
 * The SAME report shape from the OTHER corpus: the authorized 30-record sample,
 * read from the application's own datastore.
 *
 * Two things differ from the public fixture beyond the size, and both are
 * properties of that mode rather than decoration: the two database safeguards
 * are `verified` rather than `not_applicable`, because a connection really was
 * opened and really was checked, and the limitations name the sample rather than
 * the upstream examples.
 *
 * It still carries no record id, title or value — the aggregate-only boundary is
 * the same in both modes, which is exactly the backend's design.
 */
export const verificationReportPrivateSample = {
  ...verificationReportOk,
  metadata: {
    ...verificationReportOk.metadata,
    corpus_size: 30,
    verification_mode: 'authorized_private_sample',
    duration_ms: 24310,
    cache_age_seconds: 90,
  },
  corpus: {
    records_scanned: 30,
    records_passing_baseline: 27,
    records_failing_baseline: 3,
  },
  official_validation: { passing: 27, failing: 3 },
  format_shadow: {
    ...verificationReportOk.format_shadow,
    records_passing: 21,
    records_failing: 9,
  },
  safeguards: {
    ...verificationReportOk.safeguards,
    transaction_read_only: 'verified',
    parameterized_queries_only: 'verified',
  },
  limitations: [
    'The corpus is a read-only, aggregate-only pass over the records this ' +
      'application holds. No record identifier, title, field value or evidence ' +
      'entry is included in this report.',
    'Counts are global scalars. Per-operator, per-category and per-record ' +
      'applicability breakdowns are deliberately absent.',
  ],
};

/**
 * The same report with a harness self-check tripped and an unexpected trial.
 *
 * The bad-news case has to be a real fixture rather than an edit inside a test,
 * because the calm-zero rendering is only meaningful if the non-zero rendering
 * is visibly different — and nothing proves that if both are drawn from a body
 * whose every count is 0.
 *
 * `expected_outcome_matches` drops by the three trials that went unexpectedly,
 * so the accounting still reconciles: this fixture is about FINDINGS, and a
 * fixture that also failed the arithmetic would make the two indistinguishable.
 */
export const verificationReportWithFindings = {
  ...verificationReportOk,
  mutations: {
    ...verificationReportOk.mutations,
    expected_outcome_matches: 125,
    unexpected_outcomes: 3,
  },
  oracles: { ...verificationReportOk.oracles, repeatability_failures: 2 },
  safeguards: {
    ...verificationReportOk.safeguards,
    dml_statements: 1,
    export_gating_unchanged: 'unverified',
  },
};

/**
 * Counts that DO NOT add up: 134 trials applied, but the three outcome buckets
 * total 137.
 *
 * A report like this is not something the UI may quietly tidy. It exists so the
 * "these do not account for every trial" branch is exercised against a real
 * body rather than asserted about in a comment.
 */
export const verificationReportUnbalancedMutations = {
  ...verificationReportOk,
  mutations: {
    ...verificationReportOk.mutations,
    expected_outcome_matches: 128,
    unexpected_outcomes: 3,
    observation_only_trials: 6,
  },
};

/**
 * A run whose own self-checks say the SOURCE RECORDS WERE TOUCHED.
 *
 * This is the body that caught a false claim in the mutation panel's copy: it
 * read "The records themselves are never altered." while this same report says
 * `source_mutation_failures: 5` and declines to verify
 * `source_records_modified`. The copy asserted in advance what the safeguards
 * panel was explicitly refusing to assert.
 *
 * Nothing about it is far-fetched — it is exactly what the harness would report
 * if a mutation escaped the deep clone, which is the failure the oracle exists
 * to detect. A fixture is the only way to keep the panel honest about it.
 */
export const verificationReportSourceRecordsAltered = {
  ...verificationReportOk,
  oracles: { ...verificationReportOk.oracles, source_mutation_failures: 5 },
  safeguards: {
    ...verificationReportOk.safeguards,
    source_records_modified: 'unverified',
  },
};

/**
 * Categories withheld that account for NO occurrences.
 *
 * Odd, and permitted by the wire. It is the exact body on which the chart's
 * empty branch and the row builder used to disagree — one drew nothing, the
 * other would have appended a value-0 withheld bar. Both now read
 * `histogramWithheldAnything`.
 */
export const verificationReportWithheldButEmpty = {
  ...verificationReportOk,
  format_shadow: {
    ...verificationReportOk.format_shadow,
    failures_by_error_code: {
      cells: [],
      suppressed_categories: 3,
      suppressed_total: 0,
      floor: 5,
    },
  },
};

/**
 * ONE withheld category, and its occurrence count withheld too.
 *
 * `verification._histogram` serves `suppressed_total: null` (report format 3)
 * when exactly one category is withheld from a key set an observer can
 * enumerate — shadow error codes, schema paths — because the withheld total IS
 * that category's exact count. `suppressed_categories: 1` stays visible so the
 * withholding is still disclosed.
 *
 * A DECODER INPUT, NOT A SERVED BODY. This fixture nulls one histogram and
 * leaves the sibling publishing its total, which `build_report` no longer emits:
 * both breakdowns count the same findings, so either reaching one category nulls
 * the total on BOTH. It is kept because the UI must survive a body it did not
 * expect; the served shape is covered by "renders BOTH breakdowns withheld" in
 * `record-verification.test.tsx`.
 *
 * `null` means WITHHELD. Every assertion built on this fixture exists to prove
 * the UI never turns it into `0`, `"null"` or `"NaN"`.
 */
export const verificationReportLoneWithheldCategory = {
  ...verificationReportOk,
  format_shadow: {
    ...verificationReportOk.format_shadow,
    failures_by_error_code: {
      cells: [],
      suppressed_categories: 1,
      suppressed_total: null,
      floor: 5,
    },
  },
};

/**
 * `status: "ok"` with a block missing — THE decoder trap, and not the one the
 * null-filled failure envelope tests.
 *
 * That envelope carries `status: "unavailable"`, so `readVerificationBody`
 * returns at the status check before any block is read: a decoder that
 * substituted 0 for every unreadable count would still pass a test written
 * against it. Only an `ok` body can prove the block readers fail closed.
 *
 * `corpusNull` sends `corpus: null`; `oraclesAbsent` deletes `oracles`
 * outright, because absent and null reach `readCounts` by different routes.
 */
export const verificationReportOkCorpusNull = {
  ...verificationReportOk,
  corpus: null,
};

export const verificationReportOkOraclesAbsent = (() => {
  const { oracles: _oracles, ...rest } = verificationReportOk;
  return rest;
})();

/** A histogram that withheld nothing — the branch with no suppression note. */
export const verificationReportNoSuppression = {
  ...verificationReportOk,
  format_shadow: {
    ...verificationReportOk.format_shadow,
    failures_by_error_code: {
      cells: [{ key: 'format', count: 9 }],
      suppressed_categories: 0,
      suppressed_total: 0,
      floor: 5,
    },
  },
};

/**
 * A report older than the backend's own cache lifetime
 * (`verification.CACHE_TTL_SECONDS`, 3600s). Past it the API triggers a
 * recomputation and still answers with THIS result, so the figures are valid and
 * possibly superseded — a state the reader cannot see from the numbers.
 */
export const verificationReportStale = {
  ...verificationReportOk,
  metadata: { ...verificationReportOk.metadata, cache_age_seconds: 7200 },
};

/**
 * A mode this build has never been written against.
 *
 * The wire enum is closed TODAY. A build deployed against a newer backend is the
 * case that matters: mapping an unfamiliar token onto either shipped label would
 * attribute a whole report to the wrong corpus, which is worse than declining to
 * name it.
 */
export const verificationReportUnknownMode = {
  ...verificationReportOk,
  metadata: { ...verificationReportOk.metadata, verification_mode: 'some_future_corpus' },
};

/**
 * The private-sample mode reporting a corpus size its own label does not claim.
 * Both numbers must survive to the screen; neither may be adjusted to agree.
 */
export const verificationReportPrivateSampleShort = {
  ...verificationReportPrivateSample,
  metadata: { ...verificationReportPrivateSample.metadata, corpus_size: 12 },
  corpus: { records_scanned: 12, records_passing_baseline: 11, records_failing_baseline: 1 },
  official_validation: { passing: 11, failing: 1 },
};

/**
 * The FAILURE ENVELOPE, verbatim in shape: the backend projects it non-strictly,
 * so every block it could not build arrives as `null` rather than as absent.
 * A decoder that read those nulls optimistically would render them as zeros.
 *
 * NOTE WHAT IS ABSENT: there is no `metadata`, so an `unavailable` envelope
 * cannot say which corpus it was reading OR why it failed. The backend collapses
 * `not_run`, `unavailable` and `timeout` onto this one word
 * (`verification._PROVIDER_STATUS`), and nothing on the wire distinguishes them.
 */
export const verificationFailureEnvelope = {
  status: 'unavailable',
  report_format_version: 3,
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

/** The program declined to run at all. Nothing may be inferred from a refusal. */
export const verificationRefusedEnvelope = {
  ...verificationFailureEnvelope,
  status: 'refused',
} as const;

/** The program ran and raised. The exception text is never on the wire. */
export const verificationErrorEnvelope = {
  ...verificationFailureEnvelope,
  status: 'error',
} as const;

/** A report announcing a format this build has not been checked against. */
export const verificationFutureFormat = {
  ...verificationReportOk,
  report_format_version: 4,
};

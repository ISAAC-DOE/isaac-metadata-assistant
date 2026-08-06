import { describe, it, expect } from 'vitest';

import {
  SAFEGUARD_STATES,
  VERIFICATION_CORPUS_KEYS,
  VERIFICATION_ENVELOPE_KEYS,
  VERIFICATION_FORMAT_SHADOW_KEYS,
  VERIFICATION_HISTOGRAM_FLOOR,
  VERIFICATION_HISTOGRAM_KEYS,
  VERIFICATION_METADATA_KEYS,
  VERIFICATION_MODES,
  VERIFICATION_MUTATION_KEYS,
  VERIFICATION_OFFICIAL_VALIDATION_KEYS,
  VERIFICATION_ORACLE_KEYS,
  VERIFICATION_REPORT_FORMAT_VERSION,
  VERIFICATION_SAFEGUARD_KEYS,
  VERIFICATION_STATUSES,
  SUPPRESSED_ROW_KEY,
  VALIDATOR_SERIES,
  VERIFICATION_CACHE_TTL_SECONDS,
  VERIFICATION_MODE_LABELS,
  corpusDisclosure,
  corpusSizeMismatch,
  histogramIsEmpty,
  histogramRowsWithSuppressed,
  histogramTotal,
  histogramWithheldAnything,
  isSafeguardState,
  mutationReconciliation,
  mutationsReconcile,
  readVerificationBody,
  reconciliationMismatch,
  reportFreshness,
  validatorComparison,
  validatorComparisonSummary,
} from '../lib/verificationContract';
import {
  verificationFailureEnvelope,
  verificationFutureFormat,
  verificationReportNoSuppression,
  verificationReportOk,
  verificationReportOkCorpusNull,
  verificationReportOkOraclesAbsent,
  verificationReportUnbalancedMutations,
  verificationReportWithheldButEmpty,
  verificationReportWithFindings,
  verificationRunningEnvelope,
} from '../test/verificationFixtures';

/**
 * The wire contract for `GET /api/runtime/verification`, tested WITHOUT React.
 *
 * This file's job is to fail loudly when the backend drifts. The key sets below
 * are duplicated deliberately rather than derived from the exported constants —
 * a test that reads the same constant it is checking proves only that the
 * constant equals itself, which is the tautology class this repo has shipped
 * before. If the backend renames a key, one side changes and this file breaks.
 */

describe('the frozen key sets', () => {
  it('pins the envelope', () => {
    expect([...VERIFICATION_ENVELOPE_KEYS]).toEqual([
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
    ]);
  });

  it('pins metadata, corpus and official validation', () => {
    expect([...VERIFICATION_METADATA_KEYS]).toEqual([
      'generated_at',
      'duration_ms',
      'corpus_size',
      'cache_age_seconds',
      'verification_mode',
    ]);
    expect([...VERIFICATION_CORPUS_KEYS]).toEqual([
      'records_scanned',
      'records_passing_baseline',
      'records_failing_baseline',
    ]);
    expect([...VERIFICATION_OFFICIAL_VALIDATION_KEYS]).toEqual(['passing', 'failing']);
  });

  it('pins the format-shadow block and the histogram shape', () => {
    expect([...VERIFICATION_FORMAT_SHADOW_KEYS]).toEqual([
      'records_passing',
      'records_failing',
      'failures_by_error_code',
      'failures_by_schema_path',
    ]);
    expect([...VERIFICATION_HISTOGRAM_KEYS]).toEqual([
      'cells',
      'suppressed_categories',
      'suppressed_total',
      'floor',
    ]);
    expect(VERIFICATION_HISTOGRAM_FLOOR).toBe(5);
  });

  it('pins the mutation and oracle blocks in the order the backend declares them', () => {
    expect([...VERIFICATION_MUTATION_KEYS]).toEqual([
      'operators_defined',
      'trials_attempted',
      'trials_applicable',
      'trials_skipped_not_applicable',
      'expected_outcome_matches',
      'unexpected_outcomes',
      'observation_only_trials',
    ]);
    expect([...VERIFICATION_ORACLE_KEYS]).toEqual([
      'source_mutation_failures',
      'restoration_failures',
      'repeatability_failures',
      'ordering_instability_failures',
      'no_guessing_failures',
      'workflow_consistency_failures',
      'engine_disagreements',
    ]);
  });

  it('pins the safeguards block', () => {
    expect([...VERIFICATION_SAFEGUARD_KEYS]).toEqual([
      'transaction_read_only',
      'parameterized_queries_only',
      'dml_statements',
      'ddl_statements',
      'source_records_modified',
      'private_values_exposed',
      'official_validator_unchanged',
      'export_gating_unchanged',
    ]);
  });
});

describe('the closed vocabularies', () => {
  it('offers exactly the two authorized verification modes, in backend order', () => {
    // Q19 was answered on 2026-08-05 (relayed; see
    // `docs/evidence/2026-08-05-q19-q20-authorization.md`), so a datastore-backed
    // mode may exist. It is still aggregate-only: no per-record field reaches
    // this contract in EITHER mode, which the key allowlists above pin.
    //
    // The backend DERIVES its tuple from an approval flag
    // (`authorization.verification_modes()`), so this literal is the mirror, not
    // the source. If the flag is ever cleared, the datastore mode disappears
    // from the backend and this line must be updated to match — a disabled mode
    // is a mode someone re-enables.
    expect([...VERIFICATION_MODES]).toEqual([
      'public_reference',
      'authorized_private_sample',
    ]);
  });

  it('offers three safeguard states and `true` is not one of them', () => {
    expect([...SAFEGUARD_STATES]).toEqual(['verified', 'not_applicable', 'unverified']);
    expect(isSafeguardState(true)).toBe(false);
    expect(isSafeguardState('VERIFIED')).toBe(false);
    expect(isSafeguardState('not_applicable')).toBe(true);
  });

  it('accepts only the five statuses', () => {
    expect([...VERIFICATION_STATUSES].sort()).toEqual(
      ['error', 'ok', 'refused', 'running', 'unavailable'].sort(),
    );
  });
});

describe('readVerificationBody — fail closed', () => {
  it('reads a well-formed report', () => {
    const view = readVerificationBody(verificationReportOk);
    expect(view.kind).toBe('report');
  });

  it('treats a `running` envelope as not-ready, never as zeros', () => {
    const view = readVerificationBody(verificationRunningEnvelope);
    expect(view).toEqual({ kind: 'notReady', status: 'running' });
  });

  it('treats the null-filled failure envelope as not-ready, never as zeros', () => {
    // What this DOES establish: a non-`ok` status is never mined for figures.
    //
    // WHAT IT DOES NOT ESTABLISH, and used to claim it did. This comment read
    // "THE decoder trap … a decoder reading those optimistically renders a
    // fully-populated report of zeros". It cannot: `readVerificationBody`
    // returns at the STATUS check, before a single block is read, so the block
    // readers are never reached on this body. Proven — changing `readCounts` to
    // `out[key] = n === null ? 0 : n` left this assertion passing and the whole
    // suite green. The trap it names is tested in the two cases below, on an
    // `ok` body, which is the only kind that reaches a block reader at all.
    const view = readVerificationBody(verificationFailureEnvelope);
    expect(view).toEqual({ kind: 'notReady', status: 'unavailable' });
  });

  /*
   * THE REAL TRAP, IN TWO DIFFERENT SHAPES — and they are not interchangeable.
   * Each was proven by injecting the defect it names and watching exactly these
   * tests fail, because a comment naming a trap the test does not reach is the
   * defect this block was written to correct.
   *
   *   · A NULL OR ABSENT BLOCK. Injecting "return a record of zeros when the
   *     block is not an object" into `readCounts` fails the three tests below
   *     — and NOT the fourth.
   *   · A MISSING FIELD inside a block that IS present and object-shaped, which
   *     is what a backend key rename looks like on the wire. Injecting
   *     `out[key] = n === null ? 0 : n` fails the fourth, plus the
   *     negative-count test — `countOrNull` also rejects negatives, and the
   *     zero substitution swallows those too. It fails NONE of the three
   *     below: the `isObject` guard still refuses whole null blocks, so they
   *     stay green while a fully-populated report of zeros is exactly what the
   *     decoder now builds for a renamed key.
   *
   * Neither shape covers the other. Both are kept.
   */
  it('refuses an `ok` body whose block is NULL, rather than reading it as zeros', () => {
    // `status: "ok"` promises figures, so every block reader actually runs here
    // — which is what the failure-envelope test above cannot establish.
    const view = readVerificationBody(verificationReportOkCorpusNull);
    expect(view.kind).toBe('unreadable');
    if (view.kind === 'unreadable') expect(view.reason).toBe('malformed');
  });

  it('refuses an `ok` body whose block is ABSENT, which reaches the reader differently', () => {
    // Absent and null are not the same input: one is `undefined` from a missing
    // property, the other an explicit `null`, and a guard written for one can
    // miss the other.
    const view = readVerificationBody(verificationReportOkOraclesAbsent);
    expect(view.kind).toBe('unreadable');
  });

  it('refuses an `ok` body with a null block for EVERY block, one at a time', () => {
    // One at a time, so no single guard can carry the others: a reader that
    // handled `corpus` and not `official_validation` passes a test that nulls
    // both at once only because the first refusal fires.
    for (const block of [
      'metadata',
      'corpus',
      'official_validation',
      'format_shadow',
      'mutations',
      'oracles',
      'safeguards',
    ] as const) {
      const view = readVerificationBody({ ...verificationReportOk, [block]: null });
      expect(view.kind, `${block}: a null block must not be read as zeros`).toBe('unreadable');
    }
  });

  it('refuses an `ok` body with ONE count missing inside an otherwise good block', () => {
    // The subtlest form, and the ONLY one of these four that catches a decoder
    // substituting 0 for an unreadable count: the block is present and
    // object-shaped, so every `isObject` guard is satisfied and only the
    // per-field check stands between a renamed key and a fabricated zero.
    const { records_failing_baseline: _dropped, ...partialCorpus } = verificationReportOk.corpus;
    const view = readVerificationBody({ ...verificationReportOk, corpus: partialCorpus });
    expect(view.kind).toBe('unreadable');
  });

  it('refuses a NEGATIVE or non-finite count rather than clamping it to something drawable', () => {
    // Clamping would draw a bar for a figure nobody measured.
    for (const bad of [-1, Number.NaN, Number.POSITIVE_INFINITY, '4', null]) {
      const view = readVerificationBody({
        ...verificationReportOk,
        corpus: { ...verificationReportOk.corpus, records_scanned: bad },
      });
      expect(view.kind, `records_scanned: ${String(bad)}`).toBe('unreadable');
    }
  });

  it('refuses a format version it has not been checked against', () => {
    const view = readVerificationBody(verificationFutureFormat);
    expect(view.kind).toBe('unreadable');
    if (view.kind === 'unreadable') {
      expect(view.reason).toBe('format_version');
      expect(view.formatVersion).toBe(3);
    }
  });

  it('refuses malformed bodies rather than partially drawing them', () => {
    for (const body of [null, undefined, 42, 'ok', [], {}, { status: 'ok' }]) {
      expect(readVerificationBody(body).kind).toBe('unreadable');
    }
  });

  it('refuses a report whose status word is not in the closed set', () => {
    const view = readVerificationBody({ ...verificationReportOk, status: 'fine' });
    expect(view.kind).toBe('unreadable');
  });

  it('refuses a safeguard that arrives as a bare boolean', () => {
    // `true` is how "verified" gets invented for something never measured.
    const view = readVerificationBody({
      ...verificationReportOk,
      safeguards: { ...verificationReportOk.safeguards, transaction_read_only: true },
    });
    expect(view.kind).toBe('unreadable');
  });

  it('carries the current format version', () => {
    expect(VERIFICATION_REPORT_FORMAT_VERSION).toBe(2);
  });
});

describe('what the decoder must preserve', () => {
  it('keeps not_applicable distinct from verified all the way through', () => {
    const view = readVerificationBody(verificationReportOk);
    expect(view.kind).toBe('report');
    if (view.kind !== 'report') return;
    expect(view.report.safeguards.transaction_read_only).toBe('not_applicable');
    expect(view.report.safeguards.transaction_read_only).not.toBe('verified');
  });

  it('preserves a degraded safeguard rather than normalising it', () => {
    const view = readVerificationBody(verificationReportWithFindings);
    expect(view.kind).toBe('report');
    if (view.kind !== 'report') return;
    expect(view.report.safeguards.export_gating_unchanged).toBe('unverified');
    expect(view.report.safeguards.dml_statements).toBe(1);
  });

  it('distinguishes a histogram that withheld nothing from one that did', () => {
    const withheld = readVerificationBody(verificationReportOk);
    const none = readVerificationBody(verificationReportNoSuppression);
    expect(withheld.kind).toBe('report');
    expect(none.kind).toBe('report');
    if (withheld.kind !== 'report' || none.kind !== 'report') return;
    expect(none.report.format_shadow.failures_by_error_code.suppressed_categories).toBe(0);
  });

  it('never sees an instance-path histogram, because none is served', () => {
    // `by_instance_path` shipped in v0.0.32 and was withdrawn: over a small
    // corpus a count of 1 at an instance path is a single-record fact.
    const serialized = JSON.stringify(verificationReportOk);
    expect(serialized).not.toContain('instance_path');
    expect(serialized).not.toContain('by_instance_path');
  });
});

/* ============================================================ derivations == */

describe('the corpus disclosure', () => {
  it('pins the product label for each mode, as a literal', () => {
    expect(VERIFICATION_MODE_LABELS.public_reference).toBe('Public reference preflight');
    expect(VERIFICATION_MODE_LABELS.authorized_private_sample).toBe(
      'Authorized 30-record reference sample',
    );
  });

  it('carries the wire token alongside the label, never instead of it', () => {
    const disclosure = corpusDisclosure('public_reference');
    expect(disclosure.mode).toBe('public_reference');
    expect(disclosure.label).toBe('Public reference preflight');
    expect(disclosure.known).toBe(true);
  });

  it('maps an unrecognised mode onto NEITHER shipped label', () => {
    // The one failure this function exists to make impossible. The wrong one of
    // two labels is worse than no label: it reads as a measurement of a corpus
    // nobody read.
    for (const unknown of ['', 'public', 'authorized', 'private_sample', 'some_future_corpus']) {
      const disclosure = corpusDisclosure(unknown);
      expect(disclosure.known).toBe(false);
      expect(disclosure.label).toBe(unknown);
      expect(disclosure.label).not.toBe(VERIFICATION_MODE_LABELS.public_reference);
      expect(disclosure.label).not.toBe(VERIFICATION_MODE_LABELS.authorized_private_sample);
    }
  });

  it('describes each known corpus without claiming anything about the deployment', () => {
    // `CLAUDE.md` §15: the honest form is "this run opened no connection", never
    // "the database has never been contacted".
    const publicCopy = corpusDisclosure('public_reference').description;
    expect(publicCopy).toMatch(/this run did not open a database connection/i);
    // The flat forms this project has shipped and corrected. `db_recon.py` DOES
    // reach a datastore from the pod, so only the run-scoped claim is true.
    expect(publicCopy).not.toMatch(/there is no database/i);
    expect(publicCopy).not.toMatch(/\bno database\b/i);

    const privateCopy = corpusDisclosure('authorized_private_sample').description;
    expect(privateCopy).toMatch(/read-only, aggregate-only/i);
    expect(privateCopy).toMatch(/no record identifier, title, field value or per-record outcome/i);
  });

  it('states a size disagreement for the labelled corpus, and only for it', () => {
    expect(corpusSizeMismatch('authorized_private_sample', 30)).toBeNull();
    expect(corpusSizeMismatch('public_reference', 10)).toBeNull();
    // The public label carries no figure, so no corpus size can contradict it.
    expect(corpusSizeMismatch('public_reference', 999)).toBeNull();

    const mismatch = corpusSizeMismatch('authorized_private_sample', 12);
    expect(mismatch).not.toBeNull();
    expect(mismatch).toContain('30');
    expect(mismatch).toContain('12');
    expect(mismatch).toMatch(/neither has been adjusted/i);
  });
});

describe('report freshness', () => {
  it('turns stale exactly at the cache lifetime the backend holds a report for', () => {
    expect(VERIFICATION_CACHE_TTL_SECONDS).toBe(3600);
    expect(reportFreshness(0)).toBe('fresh');
    expect(reportFreshness(3599)).toBe('fresh');
    expect(reportFreshness(3600)).toBe('stale');
    expect(reportFreshness(86400)).toBe('stale');
  });
});

describe('the two validators, side by side', () => {
  const groups = validatorComparison(
    verificationReportOk.official_validation,
    verificationReportOk.format_shadow,
  );

  it('keeps each validator on its OWN denominator', () => {
    expect(groups.map((g) => [g.key, g.passing, g.failing, g.total])).toEqual([
      ['official', 9, 1, 10],
      ['shadow', 6, 4, 10],
    ]);
  });

  it('never derives a total spanning both validators', () => {
    // The shadow reports its own record count; assuming it equals the official
    // one, or adding the two, would invent a whole nobody measured.
    const summary = validatorComparisonSummary(groups);
    expect(summary).not.toContain('20');
    expect(summary).toMatch(/counted against its own total/i);
  });

  it('summarises both groups with their own denominators named', () => {
    expect(validatorComparisonSummary(groups)).toBe(
      'Official Validation: 9 of 10 records passing, 1 not passing; ' +
        'Format Shadow: 6 of 10 records passing, 4 not passing. ' +
        "Each validator's figures are counted against its own total.",
    );
  });

  it('offers the two series, named, in draw order', () => {
    expect(VALIDATOR_SERIES.map((s) => [s.key, s.label])).toEqual([
      ['passing', 'Passing'],
      ['failing', 'Not Passing'],
    ]);
  });
});

describe('mutation accounting', () => {
  it('states both identities using the backend’s own field names', () => {
    const identities = mutationReconciliation(verificationReportOk.mutations);
    expect(identities.map((i) => [i.total.key, i.parts.map((p) => p.key)])).toEqual([
      ['trials_attempted', ['trials_applicable', 'trials_skipped_not_applicable']],
      [
        'trials_applicable',
        ['expected_outcome_matches', 'unexpected_outcomes', 'observation_only_trials'],
      ],
    ]);
  });

  it('MEASURES whether the parts add up rather than assuming it', () => {
    const identities = mutationReconciliation(verificationReportOk.mutations);
    expect(identities.map((i) => [i.partsSum, i.total.value, i.balances])).toEqual([
      [170, 170, true],
      [134, 134, true],
    ]);
    expect(mutationsReconcile(verificationReportOk.mutations)).toBe(true);
  });

  it('reports a report whose counts do NOT add up, rather than tidying it', () => {
    const identities = mutationReconciliation(
      verificationReportUnbalancedMutations.mutations,
    );
    expect(identities[0]!.balances).toBe(true);
    expect(identities[1]!.balances).toBe(false);
    expect(identities[1]!.partsSum).toBe(137);
    expect(identities[1]!.total.value).toBe(134);
    expect(mutationsReconcile(verificationReportUnbalancedMutations.mutations)).toBe(false);

    const mismatch = reconciliationMismatch(identities[1]!);
    // BOTH numbers survive into the sentence; neither is picked over the other.
    expect(mismatch).toContain('137');
    expect(mismatch).toContain('134');
  });

  it('keeps the bad-news fixture arithmetically sound, so the two cases are separable', () => {
    expect(verificationReportWithFindings.mutations.unexpected_outcomes).toBe(3);
    expect(mutationsReconcile(verificationReportWithFindings.mutations)).toBe(true);
  });

  it('writes the arithmetic as a sentence, in plain words', () => {
    const [attempted] = mutationReconciliation(verificationReportOk.mutations);
    expect(attempted!.statement).toBe(
      '170 trials attempted = 134 trials that applied + 36 trials skipped as not applicable',
    );
  });
});

describe('the withheld bucket', () => {
  it('appends ONE aggregate row carrying the withheld occurrences', () => {
    const rows = histogramRowsWithSuppressed(
      verificationReportOk.format_shadow.failures_by_error_code,
    );
    expect(rows.map((r) => [r.key, r.value])).toEqual([
      ['format', 9],
      ['pattern', 7],
      ['required', 5],
      [SUPPRESSED_ROW_KEY, 7],
    ]);
    expect(rows[3]!.label).toBe('Withheld (categories below the disclosure floor)');
  });

  it('names no withheld category, because the payload carries none', () => {
    const rows = histogramRowsWithSuppressed(
      verificationReportOk.format_shadow.failures_by_error_code,
    );
    // The bucket's label is a fixed string with no data in it at all.
    expect(rows[3]!.label).not.toMatch(/format|pattern|required/);
    expect(JSON.stringify(rows[3])).not.toContain('suppressed_categories');
  });

  it('appends nothing when nothing was withheld', () => {
    const rows = histogramRowsWithSuppressed(
      verificationReportNoSuppression.format_shadow.failures_by_error_code,
    );
    expect(rows.map((r) => r.key)).toEqual(['format']);
  });

  it('takes shares against the shown PLUS the withheld occurrences', () => {
    // Using the shown sum alone would make the visible categories add to 100%
    // and erase the withheld ones from the arithmetic.
    const histogram = verificationReportOk.format_shadow.failures_by_error_code;
    expect(histogramTotal(histogram)).toBe(9 + 7 + 5 + 7);
  });
});

describe('one predicate decides "withheld nothing", on both sides', () => {
  it('agrees on the odd body the two used to disagree about', () => {
    // Categories withheld accounting for NO occurrences. The chart's empty
    // branch tested `suppressed_total === 0` and drew nothing; the row builder
    // tested both fields and would have appended a value-0 withheld bar.
    const histogram = verificationReportWithheldButEmpty.format_shadow.failures_by_error_code;
    expect(histogram.cells).toHaveLength(0);
    expect(histogram.suppressed_categories).toBe(3);
    expect(histogram.suppressed_total).toBe(0);

    expect(histogramWithheldAnything(histogram)).toBe(true);
    // Withholding happened, so this is NOT the "nothing was recorded" case…
    expect(histogramIsEmpty(histogram)).toBe(false);
    // …and the bucket is drawn, carrying the occurrences it actually accounts
    // for, which is zero. Stating 0 is honest; omitting the row would say the
    // three categories were never withheld.
    const rows = histogramRowsWithSuppressed(histogram);
    expect(rows.map((r) => [r.key, r.value])).toEqual([[SUPPRESSED_ROW_KEY, 0]]);
  });

  it('calls a genuinely empty histogram empty', () => {
    const histogram = { cells: [], suppressed_categories: 0, suppressed_total: 0, floor: 5 };
    expect(histogramWithheldAnything(histogram)).toBe(false);
    expect(histogramIsEmpty(histogram)).toBe(true);
    expect(histogramRowsWithSuppressed(histogram)).toEqual([]);
  });

  it('never calls a histogram with cells empty', () => {
    const histogram = verificationReportOk.format_shadow.failures_by_error_code;
    expect(histogramIsEmpty(histogram)).toBe(false);
  });
});

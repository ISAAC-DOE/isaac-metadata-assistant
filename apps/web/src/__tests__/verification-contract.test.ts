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
  isSafeguardState,
  readVerificationBody,
} from '../lib/verificationContract';
import {
  verificationFailureEnvelope,
  verificationFutureFormat,
  verificationReportNoSuppression,
  verificationReportOk,
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
  it('offers exactly one verification mode, and it is not a database', () => {
    // Q19 is unanswered (`docs/dean-authorization-packet.md:3`, NOT SENT), so a
    // private-corpus mode must not exist here — not even a disabled one.
    expect([...VERIFICATION_MODES]).toEqual(['public_upstream_corpus']);
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
    // THE decoder trap: the backend projects the failure envelope non-strictly,
    // so every block arrives as `null`. A decoder reading those optimistically
    // renders a fully-populated report of zeros — a fabricated measurement.
    const view = readVerificationBody(verificationFailureEnvelope);
    expect(view).toEqual({ kind: 'notReady', status: 'unavailable' });
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

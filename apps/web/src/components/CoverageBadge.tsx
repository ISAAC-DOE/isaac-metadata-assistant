import './signals.css';
import { FileText } from './icons';
import { LABELS } from '../lib/labels';
import { NO_SERIES_COVERAGE_NOTE, carriesNoMeasurementSeries } from '../lib/adapt';
import type { AdvisoryResult, AuditResult } from '../lib/types';

interface CoverageBadgeProps {
  audit: AuditResult;
  /**
   * The advisory result for the SAME record the count describes.
   *
   * REQUIRED, not optional, and that is the point: the coverage denominator is
   * enumerated from the record's own content, so the figure cannot be rendered
   * honestly without the one signal that says what the record does not contain.
   * An optional prop would let a future surface show `N / N` with the disclosure
   * silently absent, which is the exact failure this prop exists to close.
   *
   * "SAME RECORD" IS NOT ALWAYS "SAME DOCUMENT", and the exception is recorded
   * rather than papered over. `routes.py::_warnings_payload` degrades to the
   * in-memory export CANDIDATE when a record is marked exported but its artifact
   * cannot be read, while `audit` counts the artifact on disk. In that state the
   * advisory describes the draft and the count describes the artifact, which
   * falsifies the sentence above — and `adapt.ts::toAdvisoryResult` drops the
   * payload's `dry_run` flag, so this component could not tell even if it wanted
   * to.
   *
   * It is UNREACHABLE today: on `ExportReadiness` the badge renders only behind
   * `realValidation.verdict === 'pass'`, which requires a readable artifact. That
   * is INCIDENTAL protection — a side effect of where the badge is mounted, not a
   * decision anyone made here — so a new mount site, or a change to that
   * condition, re-opens it. Closing it properly means carrying `dry_run` through
   * `toAdvisoryResult` and refusing to disclose from a candidate while counting an
   * artifact; that is a wire-shape change and is deliberately not in this slice.
   */
  advisory: AdvisoryResult;
}

/**
 * Evidence-audit coverage `N / N` in neutral slate — information, NOT a verdict.
 * Deliberately not green so it can never be mistaken for a PASS; namespaced
 * sidecar keys are excluded from the count upstream. `uncovered` (an expected
 * target with no evidence yet) and `dangling` (a sidecar key that doesn't
 * resolve) are different truth-gap shapes — listed in their own sections, same
 * neutral treatment, never merged into one undifferentiated list.
 */
export function CoverageBadge({ audit, advisory }: CoverageBadgeProps) {
  const uncoveredCount = audit.uncovered.length;
  const danglingCount = audit.dangling.length;
  const clean = uncoveredCount === 0 && danglingCount === 0;

  const segments: string[] = [];
  if (uncoveredCount > 0) {
    segments.push(`${uncoveredCount} uncovered — resolve in ${LABELS.screenComplete}`);
  }
  if (danglingCount > 0) {
    segments.push(`${danglingCount} dangling — fix by re-export, not invalidity`);
  }

  return (
    <section className="coverage" aria-label="Evidence audit coverage · not a verdict">
      <div className="coverage-head">
        <span className="coverage-title">
          <FileText size={15} strokeWidth={2} aria-hidden="true" />
          {LABELS.evidenceAudit}
        </span>
        <span className="coverage-note">coverage · not a verdict</span>
      </div>
      <div className="coverage-figure mono">
        {audit.resolved} / {audit.total}
      </div>
      {/* Static denominator explanation: the live count must be self-explanatory
          where it is shown. Only these lines are static — the numbers above are
          always the live audit payload.

          THE FIRST LINE USED TO READ "Includes fields, assets, descriptors,
          series, QC, links, and attribution." — which invites exactly the wrong
          inference. `isaac_records.audit` builds the denominator FROM THE RECORD
          (`_scalar_targets` + `_block_targets`: one target per series, asset,
          descriptor, link and contributor the record actually has), so "includes
          series" is a claim about the enumeration RULE that a reader reasonably
          takes as a claim about this record. Measured on the canonical worked
          example: 33 / 33 with its series, 32 / 32 with the series emptied — the
          denominator shrank and the figure still read as full coverage. So the
          scope is now stated as scope, and the second line says what a full count
          does and does not mean. Neither line classifies anything. */}
      <div className="coverage-sub">
        Counted from what this record contains: fields, assets, descriptors, series, QC, links,
        and attribution.
      </div>
      <div className="coverage-sub">
        A full count means every target this record has is evidenced — not that any particular
        target exists.
      </div>
      {/* The record-specific half. Keyed on the backend advisory code (see
          `lib/adapt.ts`), never re-derived here from record content the badge does
          not receive. */}
      {carriesNoMeasurementSeries(advisory) && (
        <div className="coverage-sub coverage-sub-scope">{NO_SERIES_COVERAGE_NOTE}</div>
      )}
      <div className="coverage-sub">{clean ? 'paths resolve · 0 dangling' : segments.join(' · ')}</div>
      <div className="coverage-cmd mono">isaac audit</div>
      {uncoveredCount > 0 && (
        <ul className="coverage-dangling mono" aria-label="Uncovered targets">
          {audit.uncovered.map((key) => (
            <li key={key}>{key}</li>
          ))}
        </ul>
      )}
      {danglingCount > 0 && (
        <ul className="coverage-dangling mono" aria-label="Dangling targets">
          {audit.dangling.map((key) => (
            <li key={key}>{key}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

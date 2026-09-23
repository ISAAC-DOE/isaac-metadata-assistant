import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Disclosure } from './Disclosure';
import { HelpTip } from './HelpTip';
import { SemanticStatus } from './SemanticStatus';
import { ROUTES } from '../lib/routes';
import { DETERMINISM_LABELS, IMPORT_COPY, IMPORT_STAGE_COPY } from '../lib/historicalImportContent';
import {
  REVIEW_BUCKET_STATE,
  candidateBucket,
  candidateLabel,
  candidateValue,
  sourceCount,
  type ReviewBucket,
} from '../lib/importStages';
import type { ApiImportCandidate, ApiImportProposedRow } from '../lib/types';

/**
 * ONE CANDIDATE, AS A ROW — the replacement for the always-expanded candidate card
 * (owner QA H1, 2026-09-22).
 *
 * The card rendered, for every one of an archive's 101 candidates: a raw schema
 * path as its heading, "No value was chosen", a multi-paragraph normalisation rule
 * and a refusal paragraph. This row shows what a reviewer scans for — a human name,
 * the value (or that none has been selected), the state as icon + word, and how
 * many distinct files stand behind it — and keeps every one of those other facts one
 * press away, in the DOM and in the accessibility tree.
 *
 * The STATE comes from the server's `review_status`, and `Sources Agree` is shown
 * only when the server's `agreement` says two or more distinct files state one
 * reading: several statements in one file are one witness, not agreement.
 */
export function ImportCandidateRow({
  candidate,
  filenameOf,
  already,
  alreadyTitle,
  bucket: reviewBucket,
  context,
  children,
}: {
  candidate: ApiImportCandidate;
  filenameOf: (sourceId: string) => string;
  /**
   * Which measurement the candidate belongs to, when the row is shown OUTSIDE that
   * measurement (Review lists an archive's candidates together, and ten rows reading
   * "Acquisition timestamp" are indistinguishable without it).
   */
  context?: string;
  /** Where this candidate was already sent, if it was. */
  already?: ApiImportProposedRow;
  /** The title of the record it was sent to, when the screen knows it. */
  alreadyTitle?: string;
  /**
   * The state to show, from `candidateReview(session).bucketOf` — so a candidate this
   * import already sent reads SENT here exactly as it does in the header and the Add
   * stage (2026-09-23). Without it the row still never calls a sent candidate ready.
   */
  bucket?: ReviewBucket;
  /** A send control, for a candidate that can go forward. */
  children?: ReactNode;
}) {
  const bucket: ReviewBucket = reviewBucket ?? (already !== undefined ? 'sent' : candidateBucket(candidate));
  const value = candidateValue(candidate);
  const label = candidateLabel(candidate);
  const sources = sourceCount(candidate);
  const labels = IMPORT_STAGE_COPY.stateLabels;
  const agree = candidate.agreement === 'sources_agree';
  /* VARIES BY SCAN (2026-09-22): neither agreement nor conflict — each scan (or file)
     keeps its own reading, as the concept's registry cardinality expects. */
  const variation = candidate.agreement === 'varies' ? candidate.variation ?? [] : [];
  const basis = candidate.variation_basis ?? 'per_scan';
  const byFile = basis === 'per_source';
  const spans = candidate.variation_scans ?? null;
  const readings = candidate.variation_total ?? variation.length;
  const variesLabel = byFile ? labels.variesByFile : basis === 'per_scan_item' ? labels.severalPerScan : labels.variesByScan;
  const scansText = spans !== null ? `${spans} ${spans === 1 ? 'scan' : 'scans'}` : '';
  const variesSummary = byFile
    ? 'different in each file'
    : basis === 'per_scan_item'
      ? `${readings} ${readings === 1 ? 'value' : 'values'}${scansText ? ` across ${scansText}` : ''}`
      : `one per scan${scansText ? ` · ${scansText}` : ''}`;
  const variesWhy = byFile
    ? IMPORT_STAGE_COPY.variation.whyFile
    : basis === 'per_scan_item'
      ? IMPORT_STAGE_COPY.variation.whyItem
      : IMPORT_STAGE_COPY.variation.why;
  const variesEach = byFile
    ? IMPORT_STAGE_COPY.variation.eachFile
    : basis === 'per_scan_item'
      ? IMPORT_STAGE_COPY.variation.eachItem
      : IMPORT_STAGE_COPY.variation.eachScan;

  return (
    <li className="hi-cand">
      <Disclosure
        className="hi-cand-row"
        summary={
          <span className="hi-cand-summary">
            <span className="hi-cand-name">{label}</span>
            {context && <span className="hi-cand-context">{context}</span>}
            {variation.length > 0 ? (
              <span className="hi-cand-value hi-cand-none">{variesSummary}</span>
            ) : (
              <span className={value === null ? 'hi-cand-value hi-cand-none' : 'hi-cand-value'}>
                {value ?? IMPORT_STAGE_COPY.conflicts.noValue}
              </span>
            )}
          </span>
        }
        meta={
          <span className="hi-cand-meta">
            <SemanticStatus state={REVIEW_BUCKET_STATE[bucket]} label={labels[bucket]} size="sm" />
            {variation.length > 0 && <SemanticStatus state="notApplicable" label={variesLabel} size="sm" />}
            {agree && bucket !== 'conflict' && (
              <SemanticStatus state="sourcesAgree" label={labels.sourcesAgree} size="sm" />
            )}
            <span className="hi-cand-count">
              {sources} {sources === 1 ? 'source' : 'sources'}
            </span>
          </span>
        }
      >
        <div className="hi-cand-detail">
          <div className="hi-cand-facts">
            {/* WHAT WAS READ VERSUS WHAT WAS INFERRED, from the server's own field. */}
            <span>{DETERMINISM_LABELS[candidate.determinism] ?? candidate.determinism}</span>
            {candidate.target_field_path !== null && (
              <>
                {' · '}
                <span className="hi-cand-path-lead">Official field</span>
                <HelpTip subject={`the field for ${label}`}>
                  <code>{candidate.target_field_path}</code> in the official ISAAC schema.
                </HelpTip>
              </>
            )}
          </div>

          {variation.length > 0 && (
            <div className="hi-cand-variation">
              <p className="hi-sub">{variesWhy}</p>
              <Disclosure className="hi-cand-rule" summary={variesEach} meta={String(readings)}>
                <ul className="hi-cand-readings">
                  {variation.map((row, index) => (
                    <li key={index}>
                      <span className="hi-cand-reading-value">
                        <span className="hi-cand-reading-where">
                          {[
                            row.scan !== null
                              ? `Scan ${row.scan}`
                              : row.source !== null
                                ? (row.source.split('/').pop() ?? row.source)
                                : 'The measurement',
                            row.item,
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </span>{' '}
                        {row.value}
                      </span>
                      <span className="hi-sub">{row.locators.join('; ')}</span>
                    </li>
                  ))}
                </ul>
                {typeof candidate.variation_total === 'number' && candidate.variation_total > variation.length && (
                  <p className="hi-sub">
                    {variation.length} of {candidate.variation_total} readings shown.
                  </p>
                )}
              </Disclosure>
            </div>
          )}

          {candidate.disagreement.length > 0 && (
            <ul className="hi-cand-readings">
              {candidate.disagreement.map((row, index) => (
                <li key={index}>
                  <span className="hi-cand-reading-value">{row.value}</span>
                  <span className="hi-sub">
                    from {row.source_ids.map(filenameOf).join(', ')} · {row.locators.join(', ')}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {candidate.supporting_statements.length > 0 && (
            <ul className="hi-support">
              {candidate.supporting_statements.map((statement, index) => (
                <li key={index}>
                  <span className="hi-filename">{filenameOf(statement.source_id)}</span>
                  <span className="hi-locator">{statement.locator}</span>
                  <span className="hi-value">{statement.value}</span>
                </li>
              ))}
            </ul>
          )}
          {typeof candidate.supporting_statement_total === 'number' &&
            candidate.supporting_statement_total > candidate.supporting_statements.length && (
              <p className="hi-sub">
                {candidate.supporting_statements.length} of{' '}
                {candidate.supporting_statement_total} statements shown.
              </p>
            )}

          {/* THE WARRANT, VERBATIM — the reconstruction's own sentence, never a
              paraphrase. One press further in, because for a normalised reading it
              is several paragraphs of rule text a reviewer reads once. */}
          <Disclosure className="hi-cand-rule" summary={IMPORT_STAGE_COPY.whereFrom}>
            <p className="hi-rule">{candidate.rule}</p>
          </Disclosure>

          {already !== undefined ? (
            <p className="hi-sent" role="note">
              {IMPORT_COPY.proposedNote}{' '}
              <Link to={ROUTES.recordProposal(already.experiment_id, already.proposal_id)}>
                {alreadyTitle ? `Open it on ${alreadyTitle}` : 'Open it on that record'}
              </Link>
            </p>
          ) : candidate.proposable ? (
            children
          ) : (
            /* WHY IT CANNOT BE SENT, in the server's own words, with no control. */
            <p className="hi-blocked" role="note">
              {candidate.not_proposable_reason ?? IMPORT_COPY.notProposableFallback}
            </p>
          )}
        </div>
      </Disclosure>
    </li>
  );
}

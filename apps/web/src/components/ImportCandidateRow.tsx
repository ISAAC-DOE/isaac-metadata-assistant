import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Disclosure } from './Disclosure';
import { HelpTip } from './HelpTip';
import { SemanticStatus } from './SemanticStatus';
import { ROUTES } from '../lib/routes';
import { DETERMINISM_LABELS, IMPORT_COPY, IMPORT_STAGE_COPY } from '../lib/historicalImportContent';
import {
  BUCKET_STATE,
  candidateBucket,
  candidateLabel,
  candidateValue,
  sourceCount,
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
  /** A send control, for a candidate that can go forward. */
  children?: ReactNode;
}) {
  const bucket = candidateBucket(candidate);
  const value = candidateValue(candidate);
  const label = candidateLabel(candidate);
  const sources = sourceCount(candidate);
  const labels = IMPORT_STAGE_COPY.stateLabels;
  const agree = candidate.agreement === 'sources_agree';

  return (
    <li className="hi-cand">
      <Disclosure
        className="hi-cand-row"
        summary={
          <span className="hi-cand-summary">
            <span className="hi-cand-name">{label}</span>
            {context && <span className="hi-cand-context">{context}</span>}
            <span className={value === null ? 'hi-cand-value hi-cand-none' : 'hi-cand-value'}>
              {value ?? IMPORT_STAGE_COPY.conflicts.noValue}
            </span>
          </span>
        }
        meta={
          <span className="hi-cand-meta">
            <SemanticStatus state={BUCKET_STATE[bucket]} label={labels[bucket]} size="sm" />
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
                Open it on that record
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

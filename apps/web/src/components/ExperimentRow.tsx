import './queue.css';
import { Link } from 'react-router-dom';
import { ChevronRight, FileText } from './icons';
import { StatusChip } from './StatusChip';
import { ROUTES } from '../lib/routes';
import type { ExperimentSummary } from '../lib/types';

interface ExperimentRowProps {
  exp: ExperimentSummary;
}

/**
 * One experiment as a calm row that opens the workbench. Coverage and verdict
 * stay two distinct tokens on ready rows — never merged into one badge.
 */
export function ExperimentRow({ exp }: ExperimentRowProps) {
  const t = exp.trailing;
  const accessibleName = `${exp.title} — ${describeTrailing(exp)}`;
  return (
    <Link
      to={ROUTES.record(exp.id)}
      className={`exp-row${exp.group === 'done' ? ' done' : ''}`}
      aria-label={accessibleName}
    >
      <div className="exp-main">
        <div className="exp-title">{exp.title}</div>
        <div className="exp-sub">
          <span className="exp-tag">{exp.technique}</span>
          <span className="exp-id">{exp.idOrDraft}</span>
          {exp.meta && <span className="exp-meta">{exp.meta}</span>}
        </div>
      </div>

      <div className="exp-trailing">
        {t.needsYouCount !== undefined && (
          <StatusChip kind="needsYou" label={`${t.needsYouCount} Fields Need You`} />
        )}
        {t.mentorReview && <StatusChip kind="mentorReview" />}
        {t.coverage && (
          <span className="exp-coverage">
            <FileText size={13} strokeWidth={2} aria-hidden="true" />
            {t.coverage.resolved}/{t.coverage.total}
          </span>
        )}
        {t.verdict === 'pass' && <StatusChip kind="pass" />}
        {t.exported && <StatusChip kind="exported" />}
        <ChevronRight className="exp-chevron" size={18} strokeWidth={2} aria-hidden="true" />
      </div>
    </Link>
  );
}

function describeTrailing(exp: ExperimentSummary): string {
  const t = exp.trailing;
  if (t.needsYouCount !== undefined) return `${t.needsYouCount} fields need you`;
  if (t.mentorReview) return 'Mentor Review';
  if (t.verdict === 'pass') return `coverage ${t.coverage?.resolved}/${t.coverage?.total}, PASS`;
  if (t.exported) return `coverage ${t.coverage?.resolved}/${t.coverage?.total}, Exported`;
  return 'open record';
}

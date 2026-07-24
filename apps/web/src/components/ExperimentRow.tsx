import './queue.css';
import { Link } from 'react-router-dom';
import { ChevronRight } from './icons';
import { StatusChip } from './StatusChip';
import { ROUTES } from '../lib/routes';
import { LABELS } from '../lib/labels';
import type { ExperimentSummary, QueueGroupKey } from '../lib/types';

interface ExperimentRowProps {
  exp: ExperimentSummary;
}

const GROUP_STATE_LABEL: Record<QueueGroupKey, string> = {
  needsAttention: LABELS.groupNeedsAttention,
  inReview: LABELS.groupInReview,
  ready: LABELS.groupReady,
  done: LABELS.groupDone,
};

const LIFECYCLE_LABEL: Record<ExperimentSummary['lifecycle'], string> = {
  draft: LABELS.chipDraft,
  exported: LABELS.chipExported,
};

/**
 * One experiment as a calm row that opens the workbench. The metadata row
 * carries exactly one lifecycle badge (Draft/Exported) plus, when known, a
 * neutral created-date badge — never a technique tag or raw ULID on the card
 * face. The trailing side carries an actionable field-count chip only when
 * the row needs you; every other state is named by its group, not repeated
 * as a chip.
 */
export function ExperimentRow({ exp }: ExperimentRowProps) {
  const t = exp.trailing;
  const accessibleName = describeAccessibleName(exp);
  return (
    <Link
      to={ROUTES.record(exp.id)}
      className={`exp-row${exp.group === 'done' ? ' done' : ''}`}
      aria-label={accessibleName}
    >
      <div className="exp-main">
        <div className="exp-title">{exp.title}</div>
        <div className="exp-sub">
          <StatusChip kind={exp.lifecycle} />
          {exp.date && (
            <time className="exp-date" dateTime={exp.date.iso} aria-label={exp.date.accessible}>
              {exp.date.display}
            </time>
          )}
        </div>
      </div>

      <div className="exp-trailing">
        {t.needsYouCount !== undefined && (
          <StatusChip kind="needsYou" label={`${t.needsYouCount} Fields Need You`} />
        )}
        <ChevronRight className="exp-chevron" size={18} strokeWidth={2} aria-hidden="true" />
      </div>
    </Link>
  );
}

function describeAccessibleName(exp: ExperimentSummary): string {
  const t = exp.trailing;
  const lifecycleLabel = LIFECYCLE_LABEL[exp.lifecycle];
  const groupStateLabel = GROUP_STATE_LABEL[exp.group];
  const count = t.needsYouCount;
  const countPart = count !== undefined ? `, ${count} field${count === 1 ? '' : 's'} need you` : '';
  return `${exp.title} — ${lifecycleLabel}, ${groupStateLabel}${countPart}`;
}

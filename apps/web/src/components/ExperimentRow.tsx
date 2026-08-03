import './queue.css';
import { Link } from 'react-router-dom';
import { ChevronRight, LayoutList } from './icons';
import { StatusChip } from './StatusChip';
import { ROUTES } from '../lib/routes';
import { LABELS } from '../lib/labels';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
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
 *
 * The five canonical synthetic seeds share one scientific title, so a
 * server-derived `scenario` label is rendered as a quiet secondary line beneath
 * it (icon + text, never color alone) naming WHICH seeded fixture the row is.
 * The server words it in the past tense — it names how that fixture was
 * MATERIALISED at setup, and is deliberately never refreshed — so advancing the
 * record changes the lifecycle chip and queue group without falsifying the
 * label. (An invariant *present-tense* state description would not be safe here:
 * over a mutating record it is guaranteed to end up contradicting the chip.)
 * A record without a scenario renders no line at all — no empty shell, no
 * "undefined".
 */
export function ExperimentRow({ exp }: ExperimentRowProps) {
  const t = exp.trailing;
  const accessibleName = describeAccessibleName(exp);
  return (
    <Link
      to={ROUTES.record(exp.id)}
      className={`exp-row${exp.group === 'done' ? ' done' : ''}`}
      aria-label={accessibleName}
      /* The guided walkthrough's anchor for "opening a record". EVERY row carries
         it, and the walkthrough resolves the FIRST one in document order —
         deliberately, because the step describes what a row IS, not one
         particular record. */
      data-tutorial-anchor={TUTORIAL_ANCHORS.experimentRow}
    >
      <div className="exp-main">
        <div className="exp-title">{exp.title}</div>
        {exp.scenario && (
          <div className="exp-scenario">
            <LayoutList
              className="exp-scenario-icon"
              size={12}
              strokeWidth={2}
              aria-hidden="true"
            />
            <span className="exp-scenario-text">{exp.scenario}</span>
          </div>
        )}
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
  // The scenario label joins the accessible name so a screen-reader user can tell
  // the five identically-titled canonical seeds apart. Omitted entirely when the
  // record has none, so the name never contains a stray separator or "undefined".
  const scenarioPart = exp.scenario ? `${exp.scenario}, ` : '';
  return `${exp.title} — ${scenarioPart}${lifecycleLabel}, ${groupStateLabel}${countPart}`;
}

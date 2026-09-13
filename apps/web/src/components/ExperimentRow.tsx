import './queue.css';
import { Link } from 'react-router-dom';
import { ChevronRight, FolderIcon, LayoutList } from './icons';
import { StatusChip } from './StatusChip';
import { ROUTES } from '../lib/routes';
import { LABELS } from '../lib/labels';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import { lastRecordView } from '../lib/recordLastView';
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
  /*
   * LIB-005 — REOPEN-AND-CONTINUE. Route to the workspace this BROWSER last saw
   * the reader viewing on THIS record, when one is remembered and it is not
   * `fields` — a bare `ROUTES.record(id)` already opens `fields`
   * (`resolveRecordView`'s own fallback), so there is nothing to change for the
   * common case. See `lib/recordLastView.ts` for what is stored, why it is
   * browser-local, and its fail-safe direction: every unreadable or absent
   * entry resolves to `null` here and this row behaves exactly as it always
   * has.
   */
  const rememberedView = lastRecordView(exp.id);
  const to =
    rememberedView && rememberedView !== 'fields'
      ? ROUTES.recordView(exp.id, rememberedView)
      : ROUTES.record(exp.id);
  return (
    <Link
      to={to}
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
        {/*
          THE METADATA LINE, AND EVERY ITEM IN IT IS CONDITIONAL.

          There is no placeholder for anything absent — no dash, no "unknown", no
          empty chip. A freshly created experiment has no technique, no beamline,
          no runs and no folder, and it renders none of them: four grey dashes
          would say "we looked and there is nothing", which is a claim, where
          nothing at all says only that nothing has established them.

          THE DISAMBIGUATOR COMES FIRST, because it is the item a reader needs
          when they need it at all. It is present ONLY when another row on screen
          shows the same title — see `adapt.RowContext`.

          `runCount` and `openProposalCount` HIDE AT ZERO. `0 runs` on every new
          record is noise on the most common row in the product, and `0
          proposals` would be worse: it invites the reading that proposals are
          expected here.
        */}
        {(exp.disambiguator ||
          exp.folder ||
          exp.technique ||
          exp.beamline ||
          exp.runCount ||
          exp.openProposalCount) && (
          <div className="exp-meta">
            {exp.disambiguator && (
              <span className="exp-meta-item exp-meta-id" title={exp.disambiguator}>
                {/* The visible text is the id, and the accessible text says WHY it
                    is here. A bare 26-character ULID read aloud is not
                    information; "record id …" is. */}
                <span className="sr-only">Record id </span>
                <span className="exp-meta-mono">{exp.disambiguator}</span>
              </span>
            )}
            {exp.folder && (
              <span className="exp-meta-item exp-meta-folder">
                <FolderIcon size={12} strokeWidth={2} aria-hidden="true" />
                <span className="sr-only">In folder </span>
                {exp.folder}
              </span>
            )}
            {exp.technique && (
              <span className="exp-meta-item">
                <span className="sr-only">Technique </span>
                {exp.technique}
              </span>
            )}
            {exp.beamline && (
              <span className="exp-meta-item">
                {/* "Beamline 15-2", not a bare "15-2": the number alone is
                    meaningless out of context and unreadable aloud. */}
                Beamline {exp.beamline}
              </span>
            )}
            {exp.runCount ? (
              <span className="exp-meta-item">
                {exp.runCount} run{exp.runCount === 1 ? '' : 's'}
              </span>
            ) : null}
            {exp.openProposalCount ? (
              <span className="exp-meta-item exp-meta-proposals">
                {exp.openProposalCount} proposal{exp.openProposalCount === 1 ? '' : 's'} waiting
              </span>
            ) : null}
          </div>
        )}
        <div className="exp-sub">
          <StatusChip kind={exp.lifecycle} />
          {/*
            TWO DATES ARE NEVER BOTH SHOWN, and the choice is the Library's need
            rather than a preference. `updated` is what a returning scientist
            reads a list for ("what was I last doing?"), so it wins when the
            server sent one; `date` (created) is the fallback for a response that
            carried no `updated_utc`. Showing both would put two dates a second
            apart on every example record and invite a reader to compare them,
            which a whole-second timestamp cannot support.
          */}
          {exp.updated ? (
            <time
              className="exp-date"
              dateTime={exp.updated.iso}
              aria-label={exp.updated.accessible}
            >
              {exp.updated.display}
            </time>
          ) : (
            exp.date && (
              <time className="exp-date" dateTime={exp.date.iso} aria-label={exp.date.accessible}>
                {exp.date.display}
              </time>
            )
          )}
        </div>
      </div>

      <div className="exp-trailing">
        {t.needsYouCount !== undefined && (
          <StatusChip
            kind="needsYou"
            label={`${t.needsYouCount} Field${t.needsYouCount === 1 ? '' : 's'} Need${
              t.needsYouCount === 1 ? 's' : ''
            } You`}
          />
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
  const countPart =
    count !== undefined
      ? `, ${count} field${count === 1 ? '' : 's'} need${count === 1 ? 's' : ''} you`
      : '';
  // The scenario label joins the accessible name so a screen-reader user can tell
  // the five identically-titled canonical seeds apart. Omitted entirely when the
  // record has none, so the name never contains a stray separator or "undefined".
  const scenarioPart = exp.scenario ? `${exp.scenario}, ` : '';
  /*
   * THE DISAMBIGUATOR REACHES THE ACCESSIBLE NAME TOO, and it has to. The visible
   * remedy for two identical titles is a record id in the metadata line; a screen
   * reader moving between links hears only the accessible name, so without this
   * clause the two rows would be announced IDENTICALLY — the defect this row was
   * changed to fix, unfixed for exactly the readers least able to work around it.
   *
   * IT IS APPENDED, NOT INSERTED, so the leading clauses are byte-identical to
   * what they were. The three existing exact-string assertions in
   * `experiment-scenario-badge.test.tsx` pass a row with no collision and so no
   * `disambiguator` — they compare against a string this expression still
   * produces unchanged, which is why they did not need rewriting to accommodate
   * this.
   */
  const idPart = exp.disambiguator ? `, record id ${exp.disambiguator}` : '';
  return `${exp.title} — ${scenarioPart}${lifecycleLabel}, ${groupStateLabel}${countPart}${idPart}`;
}

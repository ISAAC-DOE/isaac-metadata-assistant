import { useId } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { AudioWaveform, ChevronRight, FileText, FolderIcon, SlidersHorizontal, type LucideIcon } from './icons';
import { captureSummaryLine, railDestination } from './RecordWorkspaceNav';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import { MCP_ENDPOINT } from '../lib/mcpConnectContent';
import { useHealthState } from '../lib/useHealth';
import { claudeVoiceState } from './ClaudeVoicePath';
import { RECORD_CAPTURE_METHOD_PARAM, type CaptureMethodId } from '../lib/routes';
import type { ApiCaptureSummary } from '../lib/types';

/**
 * CAPTURE HOME — how do you want to get this experiment in? (owner QA
 * 2026-09-22, C1).
 *
 * ── WHAT CHANGED, AND WHY ───────────────────────────────────────────────────
 *
 * This used to be four essay cards with the transcript panel, the notes queue and
 * every proposal expanded inline beneath them — 1,795px tall with nothing
 * captured, 4,297px after "Start Writing", and "Start Writing" and "Open Recorder"
 * opened the SAME panel. Now it is only the choice: four ways in, one short line
 * each, and each opens a FOCUSED view on this same record (`?method=`), with the
 * experiment context kept. Review lives in its own destination (`?view=proposals`)
 * and this page shows a one-line count with a link to it.
 *
 * ── WHY ROWS AND NOT FOUR CARDS ─────────────────────────────────────────────
 *
 * Four same-size cards of icon + heading + paragraph read as marketing tiles; this
 * is an instrument's chooser. One list, one row per route, every row the same
 * shape: glyph, name, one line, one action. The whole row is a pointer target
 * (the action link is stretched over it), while the accessible name stays the
 * action's own words, so a screen reader hears four distinct actions rather than
 * four paragraphs.
 *
 * ── WHAT IT IS NOT ──────────────────────────────────────────────────────────
 *
 * Not a workflow step (DEC-14): no tick, no lock, no `aria-current="step"`, no
 * completion state — "the scientist has finished capturing" is not derivable from
 * anything the record holds. The summary line states COUNTS, never a verdict.
 */
interface MethodRow {
  route: CaptureMethodId | 'runs';
  icon: LucideIcon;
  title: string;
  line: string;
  action: string;
}

const METHODS: readonly MethodRow[] = [
  {
    route: 'write',
    icon: FileText,
    title: CAPTURE_COPY.intakeWriteTitle,
    line: CAPTURE_COPY.homeWriteLine,
    action: CAPTURE_COPY.intakeWriteAction,
  },
  {
    route: 'voice',
    icon: AudioWaveform,
    title: CAPTURE_COPY.intakeVoiceTitle,
    line: CAPTURE_COPY.homeVoiceLine,
    action: CAPTURE_COPY.homeVoiceAction,
  },
  {
    route: 'files',
    icon: FolderIcon,
    title: CAPTURE_COPY.intakeFilesTitle,
    line: CAPTURE_COPY.homeFilesLine,
    action: CAPTURE_COPY.homeFilesAction,
  },
  {
    route: 'runs',
    icon: SlidersHorizontal,
    title: CAPTURE_COPY.intakeRunTitle,
    line: CAPTURE_COPY.homeRunLine,
    action: CAPTURE_COPY.intakeRunAction,
  },
];

/** The `to` for one method row: a focused capture view, or the Runs workspace. */
function methodDestination(search: string, route: MethodRow['route']): string {
  if (route === 'runs') return railDestination(search, 'runs');
  const next = new URLSearchParams(railDestination(search, 'capture'));
  next.set(RECORD_CAPTURE_METHOD_PARAM, route);
  return `?${next.toString()}`;
}

export interface CaptureIntakeProps {
  /**
   * The server's own capture totals (`detail.capture_summary`), or `null` when not
   * known — which renders no summary line at all, never a zero.
   */
  captureSummary: ApiCaptureSummary | null;
  /** The published agent address; injectable so the "ready" branch is testable. */
  claudeEndpoint?: string | null;
}

export function CaptureIntake({ captureSummary, claudeEndpoint = MCP_ENDPOINT }: CaptureIntakeProps) {
  const headingId = useId();
  const location = useLocation();
  /* The voice row offers Claude dictation ONLY where the deployment says a Claude
     connection can reach it (review #277, I-4). `claudeVoiceState` is the same
     derivation the Voice view uses, so the two surfaces cannot disagree. */
  const { settled, health } = useHealthState();
  const claudeReady = claudeVoiceState(settled, health, claudeEndpoint).kind === 'ready';
  const summaryLine = captureSummaryLine(captureSummary);
  const hasSomethingToReview =
    captureSummary !== null &&
    (captureSummary.proposals_open > 0 ||
      captureSummary.notes_total > 0 ||
      captureSummary.unreadable_entries > 0);

  return (
    <section className="capture-intake" aria-labelledby={headingId}>
      <h2 className="capture-intake-heading" id={headingId}>
        {CAPTURE_COPY.intakeHeading}
      </h2>
      <p className="capture-intake-intro">{CAPTURE_COPY.homeIntro}</p>

      <ul className="capture-methods">
        {METHODS.map((method, index) => {
          const Icon = method.icon;
          return (
            <li key={method.route} className="capture-method" data-route={method.route}>
              <span className="capture-method-icon" aria-hidden="true">
                <Icon size={18} strokeWidth={2} />
              </span>
              <div className="capture-method-text">
                <h3 className="capture-method-title">{method.title}</h3>
                <p className="capture-method-line">
                  {method.route === 'voice' && claudeReady
                    ? CAPTURE_COPY.homeVoiceLineWithClaude
                    : method.line}
                </p>
              </div>
              {/* Writing is the one route that reaches a proposal in every
                  deployment, so it is the one primary action on the page. */}
              <Link
                className={`btn ${index === 0 ? 'btn-primary' : 'btn-secondary'} capture-method-action`}
                to={{ search: methodDestination(location.search, method.route) }}
              >
                {method.action}
                <ChevronRight size={14} strokeWidth={2.2} aria-hidden="true" />
              </Link>
            </li>
          );
        })}
      </ul>

      {summaryLine !== null && (
        <p className="capture-home-summary">
          <span className="capture-home-summary-label">{CAPTURE_COPY.homeSummaryLabel}</span>
          <span className="capture-home-summary-counts">{summaryLine}</span>
          {hasSomethingToReview && (
            <Link
              className="capture-home-summary-link"
              to={{ search: railDestination(location.search, 'proposals') }}
            >
              {CAPTURE_COPY.homeReviewAction}
              <span className="sr-only"> proposals and notes</span>
            </Link>
          )}
        </p>
      )}
    </section>
  );
}

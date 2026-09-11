import './record-workspaces.css';
import { useId } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LABELS } from '../lib/labels';
import { RECORD_VIEW_PARAM, type RecordViewId } from '../lib/routes';
import type { CaptureSummary } from '../lib/useCaptureSummary';

/**
 * THE RECORD'S FOUR LOCAL DESTINATIONS, IN THE RECORD'S OWN SIDEBAR.
 *
 * ── WHY IT EXISTS ───────────────────────────────────────────────────────────
 *
 * The record screen held four genuinely different tasks — describe the record,
 * manage its runs, triage captured material, read the graph — in ONE 3,116px
 * scroll with 22 content sections and no wayfinding between them (measured; see
 * the IA audit's Measured Facts). This list is the wayfinding: one click from
 * the sidebar to the workspace a reader came for.
 *
 * ── WHAT IT IS NOT, AND THIS IS THE LOAD-BEARING PART ───────────────────────
 *
 * It is NOT a second workflow spine, and it must never acquire one's semantics.
 * `WorkflowSpine`, directly above it, renders a SERVER-DERIVED, GATED pipeline:
 * a step can be blocked, reopened or non-navigable, and forward motion is earned
 * rather than clicked. These four are ungated local destinations — always
 * reachable, in any record state, carrying no completion state, no disc, no
 * connector line and no `aria-current="step"`. A reader must be able to tell the
 * two lists apart without reading them, which is why this one has no discs and
 * why its group label says `Workspaces` rather than anything step-shaped.
 *
 * ── ONE OF THE FOUR IS PROMOTED, AND IT IS STILL NOT A STEP ────────────────
 *
 * `capture` is rendered above the other three, under its own `Data Capture`
 * eyebrow, as a card carrying the record's live note and open-proposal counts.
 * The reason is the one the project owner gave: the spine describes the
 * record-COMPLETION lifecycle, and the scientist's actual first act — writing
 * down what just happened at the instrument — had no place in it and was
 * reaching the reader as the third row of a secondary list.
 *
 * WHAT IT DELIBERATELY IS NOT. It is not a sixth `CANONICAL_ORDER` step and it
 * carries no completion state: no tick, no lock, no disc, no connector, no
 * reason text, no `aria-current="step"`, no position relative to the five the
 * server derives. `apps/api/isaac_api/workflow.py` keeps submission out of the
 * spine because a step state needs a criterion the record's own signals can
 * DECIDE, and capture has no such criterion — "the scientist has finished
 * capturing" is not derivable from any count this build holds, and a criterion
 * invented here would leave every record that legitimately needs no notes
 * permanently unsatisfied. So the card states FACTS (how much is captured, how
 * much awaits judgement) and never a verdict about whether that is enough.
 *
 * The extra visual weight is carried entirely by type scale and a card — the
 * two vocabularies already in this sidebar (`.evidence-trail-link`'s card, the
 * spine's tint) — and by no new hue, radius, shadow or custom property.
 *
 * ── WHY LINKS AND NOT BUTTONS ───────────────────────────────────────────────
 *
 * A destination is an address. Rendering `<Link>` gives a real `href`, so a
 * workspace can be middle-clicked, copied, bookmarked and — the reason the
 * switch is a PUSH rather than the `replace` the old tab bar used — reached
 * again with the browser Back button. A reader who goes Fields -> Runs -> Graph
 * and presses Back twice is on Fields, which is what the control looks like it
 * promises.
 *
 * ── THE SEARCH STRING IS COPIED, NEVER REBUILT ──────────────────────────────
 *
 * `?run=`, `?compare=` and `?at=` are independent parameters on the same record
 * URL, and a reader who focused a run and then opened the graph must come back
 * to the run they left. So each `to` is built by copying the CURRENT search
 * params and setting one key — the same discipline `SettingsPage`, `RunsSection`
 * and `EvidenceExplorer` already follow, and the reason `ROUTES.recordView` is
 * for whole-URL links rather than for switching from inside the screen.
 */

export const RECORD_WORKSPACES: readonly { id: RecordViewId; label: string }[] = [
  { id: 'fields', label: LABELS.workspaceFields },
  { id: 'runs', label: LABELS.workspaceRuns },
  { id: 'capture', label: LABELS.workspaceCapture },
  { id: 'graph', label: LABELS.workspaceGraph },
] as const;

/**
 * THE ONE DESTINATION THAT IS RENDERED OUTSIDE THE LIST.
 *
 * `RECORD_WORKSPACES` stays the complete registry of the four — the assistant
 * reads a workspace's label from it, and so does the screen's region naming —
 * so this is a RENDERING split, not a second list. Each of the four appears in
 * the sidebar exactly once; `capture` simply appears above the others, in its
 * own group, with the summary the others have no equivalent of.
 */
const PROMOTED: RecordViewId = 'capture';

/**
 * What the promoted row says beneath its label, built from the server's own
 * totals and from nothing else.
 *
 * THREE RULES THIS FUNCTION EXISTS TO KEEP:
 *
 *  1. `null` means NOT KNOWN and renders no line at all — never "0". The two
 *     are different claims and a reader must not have to tell them apart from
 *     a number.
 *  2. A clause is omitted when its count is zero rather than printed as "0",
 *     so the line states what is there instead of enumerating what is not.
 *     `0 proposals to review` and no clause at all say the same thing, and the
 *     shorter one leaves the eye on the number that is non-zero.
 *  3. Nothing here is a verdict. "2 to review" is a count of open proposals,
 *     not a claim that the record is incomplete, behind, or ready.
 */
export function captureSummaryLine(summary: CaptureSummary | null): string | null {
  if (summary === null) return null;
  const parts: string[] = [];
  if (summary.notesTotal > 0) {
    parts.push(`${summary.notesTotal} ${summary.notesTotal === 1 ? 'note' : 'notes'}`);
  }
  if (summary.proposalsOpen > 0) parts.push(`${summary.proposalsOpen} to review`);
  if (summary.unreadableEntries > 0) {
    parts.push(
      `${summary.unreadableEntries} unreadable ${
        summary.unreadableEntries === 1 ? 'entry' : 'entries'
      }`,
    );
  }
  return parts.length === 0 ? LABELS.captureNavEmpty : parts.join(' · ');
}

interface RecordWorkspaceNavProps {
  /** The workspace currently rendered — already resolved, never re-derived here. */
  active: RecordViewId;
  /**
   * The server's own capture totals, or `null` while they are unknown — before
   * the first read lands, and after one that failed. Optional so a caller with
   * no capture context (there is none today) renders the destination without a
   * summary rather than inventing one.
   */
  captureSummary?: CaptureSummary | null;
  /**
   * Called immediately before the navigation happens, with the workspace being
   * left. The screen uses it to flush held run edits; this component knows
   * nothing about what that means and deliberately does not.
   */
  onNavigate: () => void;
}

export function RecordWorkspaceNav({
  active,
  captureSummary = null,
  onNavigate,
}: RecordWorkspaceNavProps) {
  const location = useLocation();
  /* `useId`, not a module constant. Only one record sidebar is mounted today,
     so a fixed id would work today — and a duplicate `id` is a silent defect
     the moment a second one is (a split view, a test rendering two). This costs
     nothing and removes the hazard rather than relying on the invariant. */
  const captureSummaryId = useId();

  const capture = RECORD_WORKSPACES.find((w) => w.id === PROMOTED);
  const captureSearch = new URLSearchParams(location.search);
  captureSearch.set(RECORD_VIEW_PARAM, PROMOTED);
  const captureActive = active === PROMOTED;
  const summaryLine = captureSummaryLine(captureSummary);

  return (
    <nav className="workspace-nav" aria-label="Record workspaces">
      {capture && (
        <>
          <div className="workspace-nav-eyebrow eyebrow">{LABELS.recordCaptureEyebrow}</div>
          <Link
            to={{ search: `?${captureSearch.toString()}` }}
            className={`capture-nav-link${captureActive ? ' active' : ''}`}
            /* `page`, exactly as the three rows below carry — see their note.
               This row is visually heavier than they are and must not be
               semantically different from them. */
            aria-current={captureActive ? 'page' : undefined}
            /*
             * THE ACCESSIBLE NAME IS THE DESTINATION; THE COUNTS ARE A
             * DESCRIPTION. Left to the content, the name would grow to
             * "Capture & Proposals 3 notes · 2 to review" — a link whose name
             * changes whenever a colleague captures a note, which is a poor
             * thing to navigate by and a poor thing to write a test against.
             * The counts are still announced, as the link's description.
             */
            aria-label={capture.label}
            aria-describedby={summaryLine === null ? undefined : captureSummaryId}
            onClick={onNavigate}
          >
            <span className="capture-nav-label">{capture.label}</span>
            {summaryLine !== null && (
              <span className="capture-nav-summary" id={captureSummaryId}>
                {summaryLine}
              </span>
            )}
          </Link>
        </>
      )}
      <div className="workspace-nav-eyebrow eyebrow">{LABELS.recordWorkspacesEyebrow}</div>
      <ul className="workspace-nav-list">
        {RECORD_WORKSPACES.filter((workspace) => workspace.id !== PROMOTED).map((workspace) => {
          const next = new URLSearchParams(location.search);
          next.set(RECORD_VIEW_PARAM, workspace.id);
          const isActive = workspace.id === active;
          return (
            <li key={workspace.id} className="workspace-nav-row">
              <Link
                to={{ search: `?${next.toString()}` }}
                className={`workspace-nav-item${isActive ? ' active' : ''}`}
                /* `page`, not `step`. The spine above owns `step`, and giving
                   the same word to an ungated destination would tell a screen
                   reader these are pipeline positions. */
                aria-current={isActive ? 'page' : undefined}
                onClick={onNavigate}
              >
                {workspace.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

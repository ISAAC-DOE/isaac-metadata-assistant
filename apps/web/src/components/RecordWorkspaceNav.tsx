import './record-workspaces.css';
import { Link, useLocation } from 'react-router-dom';
import { LABELS } from '../lib/labels';
import { RECORD_VIEW_PARAM, type RecordViewId } from '../lib/routes';

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

interface RecordWorkspaceNavProps {
  /** The workspace currently rendered — already resolved, never re-derived here. */
  active: RecordViewId;
  /**
   * Called immediately before the navigation happens, with the workspace being
   * left. The screen uses it to flush held run edits; this component knows
   * nothing about what that means and deliberately does not.
   */
  onNavigate: () => void;
}

export function RecordWorkspaceNav({ active, onNavigate }: RecordWorkspaceNavProps) {
  const location = useLocation();

  return (
    <nav className="workspace-nav" aria-label="Record workspaces">
      <div className="workspace-nav-eyebrow eyebrow">{LABELS.recordWorkspacesEyebrow}</div>
      <ul className="workspace-nav-list">
        {RECORD_WORKSPACES.map((workspace) => {
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

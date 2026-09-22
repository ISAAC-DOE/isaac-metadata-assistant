import './record-workspaces.css';
import { useId } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LABELS } from '../lib/labels';
import {
  RECORD_CAPTURE_METHOD_PARAM,
  RECORD_PROPOSAL_PARAM,
  RECORD_VIEW_PARAM,
  ROUTES,
  type RecordViewId,
} from '../lib/routes';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import type { ApiCaptureSummary } from '../lib/types';

/**
 * THE RECORD'S LOCAL DESTINATIONS, IN THE RECORD'S OWN SIDEBAR.
 *
 * ── THE SHAPE, AS OF 2026-09-22 (owner QA, N2/N3) ──────────────────────────
 *
 *     DATA CAPTURE   Capture · Proposals · Runs
 *     WORKFLOW       the server-derived spine (`WorkflowSpine`)
 *     WORKSPACES     Activity · Evidence Trail
 *
 * `Record Fields` is no longer a rail row. It duplicated the destination the
 * spine's `Record Created` step already links to (a bare `/record/<id>`), so the
 * same screen had two entries one list apart. The fields editor keeps its route —
 * bare `/record/<id>` and `?view=fields` still resolve to it — and the spine marks
 * `Record Created` as the displayed page while it is open (`WorkflowSpine`'s
 * location signal). See {@link SPINE_REACHED}.
 *
 * ── WHAT THESE LISTS ARE NOT, AND THIS IS THE LOAD-BEARING PART ────────────
 *
 * They are NOT a second workflow spine and must never acquire one's semantics.
 * Every row here is an ungated local destination — always reachable, in any record
 * state, carrying no completion state, no disc, no connector line and no
 * `aria-current="step"`. Capture in particular is a destination and never a step
 * (DEC-14): nothing the record holds decides "capture is finished", so a criterion
 * invented here would nag every record that legitimately needs no notes. The
 * Proposals row carries a COUNT, which is a fact, never a verdict.
 *
 * ── WHY LINKS AND NOT BUTTONS ───────────────────────────────────────────────
 *
 * A destination is an address: a real `href` can be middle-clicked, bookmarked and
 * reached again with Back, which is why switching is a PUSH. Each `to` COPIES the
 * current search params and sets one key (see {@link railDestination}), so `?run=`,
 * `?compare=` and `?at=` survive a trip to another destination and back.
 */

export const RECORD_WORKSPACES: readonly { id: RecordViewId; label: string }[] = [
  { id: 'fields', label: LABELS.workspaceFields },
  { id: 'runs', label: LABELS.workspaceRuns },
  { id: 'capture', label: LABELS.workspaceCapture },
  { id: 'graph', label: LABELS.workspaceGraph },
  { id: 'activity', label: LABELS.workspaceActivity },
  { id: 'proposals', label: LABELS.workspaceProposals },
] as const;

/**
 * THE DATA CAPTURE GROUP, in rail order. `capture` is Capture Home (choose a
 * method); `proposals` is the ONE focused review surface for what capture
 * produced; `runs` is entering the scan directly (owner, 2026-09-14: "the runs
 * should be a part of the initial capture and proposals"). Grouping them asserts
 * no sequence between them — a reader may add a run before writing a note or after.
 */
export const CAPTURE_GROUP: readonly RecordViewId[] = ['capture', 'proposals', 'runs'] as const;

/**
 * `?view=graph` stays a first-class, addressable workspace that no list renders
 * (`EVG-002`/`DEC-04`, 2026-09-13): an old bookmark still opens it, and the panel
 * is shared with the Evidence screen and Project Memory, so it is not deleted.
 */
export const URL_ONLY: readonly RecordViewId[] = ['graph'];

/**
 * REACHED THROUGH THE WORKFLOW SPINE, NOT A RAIL ROW (2026-09-22, N2).
 *
 * `fields` is the screen the spine's `Record Created` step links to, so a rail row
 * for it was a second entry for one destination. It is kept distinct from
 * {@link URL_ONLY} on purpose: `graph` has no navigation entry at all, while
 * `fields` has one — in the spine — and the route-contract test asserts that every
 * id is reachable by exactly one of rail, spine or address.
 */
export const SPINE_REACHED: readonly RecordViewId[] = ['fields'];

/**
 * The `to` for a rail destination, built from the CURRENT search string.
 *
 * Copies every parameter and sets `view`, with two deliberate removals:
 *
 *  - `method` (the open capture task) is dropped everywhere. It only means
 *    something on `capture`, and the `Capture` row is the way back to Capture
 *    Home, so carrying a task along would reopen the task instead.
 *  - `proposal` is dropped on the way to `capture`, and only there. A
 *    `view=capture&proposal=<id>` address resolves to the Proposals view
 *    (`resolveRecordView` rule 0 — every proposal link ever minted names
 *    `capture`), so keeping it would make the `Capture` row open Proposals.
 */
export function railDestination(search: string, view: RecordViewId): string {
  const next = new URLSearchParams(search);
  next.set(RECORD_VIEW_PARAM, view);
  next.delete(RECORD_CAPTURE_METHOD_PARAM);
  if (view === 'capture') next.delete(RECORD_PROPOSAL_PARAM);
  return `?${next.toString()}`;
}

/**
 * What the capture summary says, built from the server's own totals and from
 * nothing else. Rendered on Capture Home.
 *
 * THREE RULES THIS FUNCTION EXISTS TO KEEP:
 *
 *  1. `null` means NOT KNOWN and renders no line at all — never "0". The two are
 *     different claims and a reader must not have to tell them apart from a number.
 *  2. A clause is omitted when its count is zero rather than printed as "0", so the
 *     line states what is there instead of enumerating what is not.
 *  3. Nothing here is a verdict. "2 to review" is a count of open proposals, not a
 *     claim that the record is incomplete, behind, or ready.
 */
export function captureSummaryLine(summary: ApiCaptureSummary | null): string | null {
  if (summary === null) return null;
  const parts: string[] = [];
  if (summary.notes_total > 0) {
    parts.push(`${summary.notes_total} ${summary.notes_total === 1 ? 'note' : 'notes'}`);
  }
  if (summary.proposals_open > 0) parts.push(`${summary.proposals_open} to review`);
  if (summary.unreadable_entries > 0) {
    parts.push(
      `${summary.unreadable_entries} unreadable ${
        summary.unreadable_entries === 1 ? 'entry' : 'entries'
      }`,
    );
  }
  return parts.length === 0 ? LABELS.captureNavEmpty : parts.join(' · ');
}

interface RecordNavProps {
  /**
   * The destination currently rendered — already resolved, never re-derived here.
   * `null` on the record's SUB-SCREENS (`/complete`, `/export`): those are workflow
   * steps, and the spine marks where you are there.
   */
  active: RecordViewId | null;
  /**
   * The server's own capture totals, straight off the record's detail payload, or
   * `null` when they are not known. Passed through unadapted: three server-owned
   * integers, rendered as integers.
   */
  captureSummary?: ApiCaptureSummary | null;
  /** Called immediately before navigating away (the screen flushes held run edits). */
  onNavigate: () => void;
}

/** One ungated destination row. Shared by both groups so the two cannot drift. */
function DestinationRow({
  id,
  label,
  active,
  search,
  onNavigate,
  count,
}: {
  id: RecordViewId;
  label: string;
  active: RecordViewId | null;
  search: string;
  onNavigate: () => void;
  /** A server count to show as a badge, or `null`/absent for none. */
  count?: { value: number; description: string } | null;
}) {
  const countId = useId();
  const isActive = id === active;
  return (
    <li className="workspace-nav-row">
      <Link
        to={{ search: railDestination(search, id) }}
        className={`workspace-nav-item${isActive ? ' active' : ''}`}
        /* `page`, not `step`: the spine owns `step`, and giving the same word to an
           ungated destination would tell a screen reader these are pipeline
           positions. */
        aria-current={isActive ? 'page' : undefined}
        /* THE NAME IS THE DESTINATION; A COUNT IS ITS DESCRIPTION. Left to the
           content, the name would change every time a colleague's agent proposes
           something — a poor thing to navigate by, and to test against. */
        aria-label={count ? label : undefined}
        aria-describedby={count ? countId : undefined}
        onClick={onNavigate}
      >
        <span className="workspace-nav-label">{label}</span>
        {count && (
          <span className="workspace-nav-count" id={countId}>
            {count.value}
            <span className="sr-only"> {count.description}</span>
          </span>
        )}
      </Link>
    </li>
  );
}

const labelOf = (id: RecordViewId) =>
  RECORD_WORKSPACES.find((w) => w.id === id)?.label ?? id;

/**
 * DATA CAPTURE — rendered ABOVE the workflow spine (owner, 2026-09-13): capture is
 * where a scientist's own work starts, so "what do I want to put in?" is the first
 * question the rail answers, before "where am I in the pipeline?". Being FIRST and
 * being a STEP are different claims, and only the first was asked for.
 */
export function RecordCaptureNav({ active, captureSummary = null, onNavigate }: RecordNavProps) {
  const location = useLocation();
  /*
   * THE PROPOSALS BADGE IS THE SERVER'S `proposals_open`, AND IT IS WITHHELD ON THE
   * PROPOSALS VIEW ITSELF. There the two panels read their own lists and update the
   * instant a proposal is decided, while this number moves only when the record
   * bundle refetches — a poll away. Restating it beside a list that has already
   * corrected it would be wrong for a few seconds; absent is not a degradation there.
   * The screen passes `null` on that view for exactly this reason.
   */
  const open = captureSummary?.proposals_open ?? 0;
  const proposalsCount = open > 0 ? { value: open, description: 'awaiting review' } : null;
  return (
    <nav className="capture-nav" aria-label={LABELS.recordCaptureEyebrow}>
      <div className="workspace-nav-eyebrow eyebrow">{LABELS.recordCaptureEyebrow}</div>
      <ul className="workspace-nav-list">
        {CAPTURE_GROUP.map((id) => (
          <DestinationRow
            key={id}
            id={id}
            label={labelOf(id)}
            active={active}
            search={location.search}
            onNavigate={onNavigate}
            count={id === 'proposals' ? proposalsCount : null}
          />
        ))}
      </ul>
    </nav>
  );
}

/**
 * WORKSPACES — the record's reference destinations: its history, and the Evidence
 * Trail (a separate screen, `/record/<id>/evidence`, so it is a plain link rather
 * than a `?view=` destination and is never marked active here).
 */
export function RecordWorkspaceNav({
  active,
  onNavigate,
  evidenceTrail = null,
}: RecordNavProps & {
  /**
   * The Evidence Trail row, or `null` to omit it — Export Readiness omits it because
   * that screen already uses the words "Evidence Trail" for the exported sidecar
   * artifact. `count` is `null` when the screen has not read the evidence, which
   * renders no count rather than a guessed one.
   */
  evidenceTrail?: { recordId: string; count: number | null } | null;
}) {
  const location = useLocation();
  const rows = RECORD_WORKSPACES.filter(
    (w) =>
      !CAPTURE_GROUP.includes(w.id) && !URL_ONLY.includes(w.id) && !SPINE_REACHED.includes(w.id),
  );
  return (
    <nav className="workspace-nav" aria-label="Record workspaces">
      <div className="workspace-nav-eyebrow eyebrow">{LABELS.recordWorkspacesEyebrow}</div>
      <ul className="workspace-nav-list">
        {rows.map((workspace) => (
          <DestinationRow
            key={workspace.id}
            id={workspace.id}
            label={workspace.label}
            active={active}
            search={location.search}
            onNavigate={onNavigate}
          />
        ))}
        {evidenceTrail !== null && (
          <li className="workspace-nav-row">
            <Link
              to={ROUTES.evidence(evidenceTrail.recordId)}
              className="workspace-nav-item evidence-trail-link"
              data-tutorial-anchor={TUTORIAL_ANCHORS.recordEvidenceTrail}
              onClick={onNavigate}
            >
              <span className="evidence-trail-link-label">{LABELS.evidenceTrail}</span>
              {evidenceTrail.count !== null && (
                <span className="evidence-trail-link-count">
                  {evidenceTrail.count} {evidenceTrail.count === 1 ? 'entry' : 'entries'}
                </span>
              )}
            </Link>
          </li>
        )}
      </ul>
    </nav>
  );
}

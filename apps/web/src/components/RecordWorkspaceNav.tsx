import './record-workspaces.css';
import { useId } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LABELS } from '../lib/labels';
import { RECORD_VIEW_PARAM, type RecordViewId } from '../lib/routes';
import type { ApiCaptureSummary } from '../lib/types';

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
 * eyebrow, as a card carrying the record's note and open-proposal counts — read
 * off the record's OWN detail payload (`capture_summary`), so the card costs no
 * request of its own and can never disagree with the bundle it was drawn from.
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
 * again with the browser Back button. A reader who goes Fields -> Runs ->
 * Experiment Data and presses Back twice is on Fields, which is what the
 * control looks like it promises. (~~Fields -> Runs -> Graph~~ — the Graph left
 * this list on 2026-09-13, `EVG-002`; the example is re-pointed rather than the
 * paragraph rewritten, because the PUSH-not-replace property it describes is
 * unchanged.)
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
 * *** RUNS JOINS DATA CAPTURE (project owner, 2026-09-14). ***
 *
 * The owner's words: *"the runs should be a part of the initial capture and
 * proposals"*. Entering the conditions you set at the instrument IS getting
 * data in -- it sat under `Workspaces`, two groups away from the intake that
 * offers the other three routes, so the most direct way in was the one a reader
 * had to already know about.
 *
 * `capture` is still the group's HEAD -- the card with the counts -- and `runs`
 * is a child row beneath it. It is a RENDERING group and nothing more:
 * `RECORD_WORKSPACES` remains the complete registry of all four ids (the
 * assistant reads labels from it, and so does the screen's region naming), each
 * id is still rendered exactly once, and `?view=runs` is unchanged.
 *
 * *** NEITHER MEMBER IS A STEP, AND GROUPING THEM DOES NOT MAKE ONE. *** No
 * tick, no lock, no disc, no connector, no `aria-current="step"`, no ordering
 * claim between them: a reader may add a run before writing a note or after,
 * and the group asserts no sequence. `workflow.py:128-149` is the standing
 * argument for why -- a step state needs a criterion the record's own signals
 * can DECIDE, and neither "capture is finished" nor "the runs are all entered"
 * is derivable from anything this build holds.
 */
const CAPTURE_GROUP: readonly RecordViewId[] = [PROMOTED, 'runs'] as const;

/**
 * *** EVG-002 / DEC-04 — THE GRAPH LEAVES THE RECORD'S SIDEBAR (2026-09-13). ***
 *
 * ── WHAT WAS DECIDED, AND HOW FAR IT GOES ───────────────────────────────────
 *
 * `DEC-04` is CONFIRMED: *"Evidence Graph is removed from primary scientist
 * navigation; underlying provenance relationships are retained."* The
 * measurement behind it: the Graph workspace is the most control-dense surface
 * on the record screen — **34 buttons and 145 text elements** — in a product
 * whose job is recording an experiment.
 *
 * `DEC-11` orders the removal in six steps. This is **step 3 only**, and steps
 * 1, 2 and 6 are what make it safe:
 *
 * * **Steps 1–2 (provenance parity outside the graph) were ALREADY SATISFIED**
 *   before this change, and `EVG-001` was dissolved on the measurement that
 *   proved it: `derived_from` is not a provenance chain but one of the official
 *   schema's `links[].rel` values, it is rendered today in the record's
 *   `Relationships` section, and `EvidenceTrailPanel.tsx:163-175` renders an
 *   origin + review chip pair computed by `lib/provenance.ts`. The graph never
 *   owned it — `EvidenceGraphPanel.tsx:89` says `derived_from` links *"cannot be
 *   edges of a tree"*, i.e. it EXCLUDES them.
 * * **Step 6 (old deep links degrade safely).** `?view=graph` is unchanged and
 *   still renders the graph: the route is not removed, the panel is not
 *   deleted, and a bookmark a scientist already holds keeps working. A
 *   still-working bookmark is the safest degradation available, so nothing here
 *   needs a fallback.
 *
 * ── STEP 4 IS REFUSED BY ITS OWN CONDITION, AND THE LEDGER WAS WRONG ────────
 *
 * `DEC-11` step 4 deletes the frontend visualization *"if the dependency
 * recheck is still clean"*. **It is not clean.** The ledger's `EVG-002` row
 * records *"0 other consumers"*; measured 2026-09-13 with `grep -ran` (the `-a`
 * is §11's rule — a zero-hit sweep of this tree without it is not a
 * measurement), that is **FALSE in at least three ways**:
 *
 *   1. `EvidenceGraphPanel` is **RENDERED BY A DIFFERENT SCREEN** —
 *      `screens/EvidenceExplorer.tsx:820`, the `/record/:id/evidence` route. It
 *      is not the record graph workspace's private component.
 *   2. `screens/graph/*` is **SHARED WITH PROJECT MEMORY**:
 *      `screens/MemoryGraphCard.tsx` imports eight modules from it
 *      (`GraphBrowse`, `GraphCanvas`, `GraphCommandBar`, `GraphDetail`,
 *      `GraphHelp`, `GraphPathFinder`, `graph.css`, …).
 *   3. `GraphAction` is shared with `components/AssistantPanel.tsx` — the ONE
 *      typed action model the graph command bar and the Assistant's graph
 *      intents both use, by design.
 *
 * So deleting it would break two other surfaces and the Assistant.
 * **`DEC-11`'s own words are *"deletion is not a substitute for
 * understanding"*, and the understanding is that the code is not unused.** The
 * ledger row is corrected rather than quietly bypassed.
 *
 * ── WHY THIS IS A RENDERING FILTER AND NOT A SHORTER REGISTRY ───────────────
 *
 * `RECORD_WORKSPACES` stays the complete registry of the four, for exactly the
 * reason the `PROMOTED` split above states: the Assistant reads a workspace's
 * label from it, and so does the screen's region naming. Removing the entry
 * would break a label lookup to move a link. This is the same mechanism,
 * inverted: `capture` is rendered ABOVE the list, `graph` is rendered in NO
 * list — and `graph` is still a first-class `?view=` id, still named, still
 * addressable.
 */
export const URL_ONLY: readonly RecordViewId[] = ['graph'];

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

interface RecordWorkspaceNavProps {
  /**
   * The workspace currently rendered — already resolved, never re-derived here.
   *
   * `null` means NO workspace is active, which is the honest state on the
   * record's SUB-SCREENS (`/complete`, `/export`). Those are workflow steps, not
   * workspaces: the spine marks where you are and nothing here should claim a
   * second "you are here". Before `RecordRail` existed those screens rendered no
   * workspace list at all, so a scientist lost every way back to Experiment
   * Data, Runs and Record Fields the moment they clicked a step.
   */
  active: RecordViewId | null;
  /**
   * The server's own capture totals, straight off the record's detail payload, or
   * `null` when they are not known — an API build that does not serve the block, or
   * a caller with no capture context. Optional for the same reason: a caller
   * without one renders the destination and no summary rather than inventing one.
   *
   * THE WIRE SHAPE IS PASSED THROUGH UNADAPTED, which is a deliberate exception to
   * this codebase's adapt-at-the-boundary habit. There is nothing to adapt: three
   * server-owned integers, rendered as three integers. An adapter would be a second
   * place for them to live and a second place to get one wrong, and the surrounding
   * rule — `CLAUDE.md` §11's four surfaces that stated a number they had not derived
   * from what they claimed to describe — is exactly about extra copies.
   */
  captureSummary?: ApiCaptureSummary | null;
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
  /* `captureSummary` is still accepted here and is deliberately UNUSED: the
     promoted capture row moved to `RecordCaptureNav` below, and keeping the prop
     means the record sidebar passes ONE summary to both navs, which cannot then
     disagree about the counts. Renaming it away would let a future caller feed
     them from two reads. */
  void captureSummary;

  return (
    <nav className="workspace-nav" aria-label="Record workspaces">
      <div className="workspace-nav-eyebrow eyebrow">{LABELS.recordWorkspacesEyebrow}</div>
      <ul className="workspace-nav-list">
        {RECORD_WORKSPACES.filter(
          (workspace) =>
            !CAPTURE_GROUP.includes(workspace.id) && !URL_ONLY.includes(workspace.id),
        ).map((workspace) => {
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

/**
 * DATA CAPTURE, AS ITS OWN LEADING BLOCK — separated from
 * {@link RecordWorkspaceNav} so the record sidebar can render it ABOVE the
 * workflow spine.
 *
 * WHY IT MOVED TO THE TOP (project owner, 2026-09-13). Capture is where a
 * scientist's own work starts: they come off the instrument with something to
 * write down, or with files, or with something to say. Sitting third — under the
 * spine and above the workspace list — it read as a secondary destination, and
 * the hosted screen showed it exactly that way.
 *
 * *** IT IS STILL NOT A STEP, AND MOVING IT DOES NOT MAKE IT ONE. *** Being
 * FIRST and being a STEP are different claims, and only the first was asked for.
 * It has no completion state, no tick, no lock, no reason text and no
 * `aria-current="step"` — because a step state needs a criterion the record's own
 * signals can decide, and "the scientist has finished capturing" is not one.
 * `workflow.py:128-149` keeps submission out of `CANONICAL_ORDER` for the same
 * reason, and a criterion invented here (`notes >= 1`) would nag every record
 * that legitimately needs none. So it leads the rail and carries live COUNTS,
 * which are facts, and never a verdict.
 *
 * The spine is UNTOUCHED: still server-derived, still gated, still the only list
 * in this rail whose entries can be blocked. What changed is which question the
 * reader meets first — "what do I want to put in?" before "where am I in the
 * pipeline?" — which is the right order for someone who has just finished
 * measuring and has nothing in the record yet.
 */
export function RecordCaptureNav({
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
  if (!capture) return null;

  return (
    <nav className="capture-nav" aria-label={LABELS.recordCaptureEyebrow}>
      <div className="workspace-nav-eyebrow eyebrow">{LABELS.recordCaptureEyebrow}</div>
      <Link
        to={{ search: `?${captureSearch.toString()}` }}
        className={`capture-nav-link${captureActive ? ' active' : ''}`}
        /* `page`, exactly as the three workspace rows in `RecordWorkspaceNav`
           carry — see their note. This row is visually heavier than they are,
           and now sits in a different landmark, but it must not be semantically
           different from them. */
        aria-current={captureActive ? 'page' : undefined}
        /*
         * THE ACCESSIBLE NAME IS THE DESTINATION; THE COUNTS ARE A DESCRIPTION.
         * Left to the content, the name would grow to "Experiment Data 3
         * notes · 2 to review" — a link whose name changes whenever a colleague
         * captures a note, which is a poor thing to navigate by and a poor thing
         * to write a test against. The counts are still announced, as the link's
         * description.
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
      {/*
        THE GROUP'S OTHER MEMBERS, as child rows beneath the head.

        They reuse `.workspace-nav-*` deliberately: a row here must be the same
        KIND of thing as a row in the workspace list -- an ungated destination --
        and reusing the class carries that sameness rather than asserting it. The
        only new declaration is the indent that expresses the nesting, and
        `aria-current` is `page` for exactly the reason the other rows say so.
      */}
      <ul className="workspace-nav-list capture-nav-children">
        {CAPTURE_GROUP.filter((id) => id !== PROMOTED).map((id) => {
          const member = RECORD_WORKSPACES.find((w) => w.id === id);
          if (!member) return null;
          const next = new URLSearchParams(location.search);
          next.set(RECORD_VIEW_PARAM, id);
          const isActive = id === active;
          return (
            <li key={id} className="workspace-nav-row">
              <Link
                to={{ search: `?${next.toString()}` }}
                className={`workspace-nav-item${isActive ? ' active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
                onClick={onNavigate}
              >
                {member.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

import { type RecordViewId } from '../lib/routes';
import type { ApiCaptureSummary, ApiWorkflow } from '../lib/types';
import { WorkflowSpine } from './WorkflowSpine';
import { RecordCaptureNav, RecordWorkspaceNav } from './RecordWorkspaceNav';

/**
 * ONE RECORD RAIL, ON EVERY RECORD SCREEN.
 *
 * ── THE DEFECT THIS CLOSES ──────────────────────────────────────────────────
 *
 * Reported by the project owner, 2026-09-14: *"when i click 'complete metadata'
 * it removes the other things we have in the sidebar, i think we should still
 * have that there to make it easier for scientists to go back and forth if they
 * want to add more data and such as well"*.
 *
 * Measured: `RecordWorkbench` built the full rail inline — `RecordCaptureNav`,
 * the spine, `RecordWorkspaceNav`, the Evidence Trail link — while
 * `GuidedCompletion` and `ExportReadiness` each rendered
 * `sidebar={<WorkflowSpine …/>}` and nothing else. So clicking a workflow step
 * navigated to a route that DROPPED Experiment Data, Runs, Record Fields and the
 * Evidence Trail, leaving a scientist mid-completion with no way back except the
 * browser's own Back button.
 *
 * ── WHY A COMPONENT RATHER THAN A COPY ─────────────────────────────────────
 *
 * The rail is four pieces with a deliberate order and a documented reason for
 * each position (capture first, then the gated spine, then the ungated
 * workspaces, then the one link that leaves the screen). Pasting that into three
 * screens is how the pieces drift apart — this repository has already been
 * caught shipping two nav landmarks whose padding diverged because they were
 * "two rules with identical values".
 *
 * ── `activeView` IS NULL ON A SUB-SCREEN, AND THAT IS THE POINT ────────────
 *
 * `/complete` and `/export` are workflow STEPS. The spine marks where you are
 * there; the workspace rows stay navigable and unhighlighted. Passing an active
 * workspace would put two "you are here" marks on one rail, which is the exact
 * collision fixed on 2026-09-14 when `.spine-step.current` and
 * `.workspace-nav-item.active` were both painting `rgb(232, 240, 248)`.
 *
 * ── WHAT IT DELIBERATELY DOES NOT DO ──────────────────────────────────────
 *
 * `EvidenceExplorer` keeps its own sidebar. That one is not navigation — it is
 * the Evidence Trail master list, a working panel with a selection. Replacing it
 * with this rail would delete a feature to gain a nav, so that screen is left
 * alone and its navigation gap is named rather than papered over.
 */
export function RecordRail({
  recordId,
  workflow,
  activeView,
  captureSummary = null,
  evidenceCount = null,
  showEvidenceTrail = true,
  onNavigate,
}: {
  recordId: string;
  /** The server's derived workflow, or `null` while it is still loading. */
  workflow: ApiWorkflow | null;
  /** The active workspace, or `null` on a sub-screen — see the header. */
  activeView: RecordViewId | null;
  /** The record's own capture totals, straight off its detail payload. */
  captureSummary?: ApiCaptureSummary | null;
  /**
   * How many evidence entries the record has, when the screen happens to know.
   * `null` renders the link WITHOUT a count rather than guessing one — a screen
   * that has not read the evidence must not imply a number, which is the same
   * rule `captureSummaryLine` follows for `null` totals.
   */
  evidenceCount?: number | null;
  /**
   * Whether to offer the Evidence Trail link at all. `false` on Export
   * Readiness, and for a reason worth stating rather than a layout preference:
   * that screen already uses the words "Evidence Trail" for the exported
   * SIDECAR ARTIFACT in its record/sidecar toggle
   * (`ExportReadiness.tsx:1028`). Rendering the rail's navigation link there too
   * put one label on two different things on one screen — the artifact you
   * exported, and a surface you can navigate to — which
   * `completion-export.test.tsx` caught as `Found multiple elements with the
   * text: Evidence Trail`.
   *
   * The rail still offers Capture, Proposals, Runs and Activity there (and the
   * spine's `Record Created` step reaches Record Fields), so the navigation this
   * component exists for is intact; what is dropped is the one row whose name
   * collides.
   */
  showEvidenceTrail?: boolean;
  /**
   * Called immediately before navigating away. `RecordWorkbench` uses it to
   * flush held run edits; the sub-screens have nothing to flush and pass
   * nothing, which is why it is optional here and required there.
   */
  onNavigate?: () => void;
}) {
  const flush = onNavigate ?? (() => {});

  /*
   * 2026-09-22 (owner QA, N3): the Evidence Trail is a row of the WORKSPACES list
   * rather than a separate card below it, so the rail reads as three groups —
   * Data Capture, Workflow, Workspaces — and nothing trails after them.
   */
  return (
    <div className="record-aside">
      <RecordCaptureNav active={activeView} captureSummary={captureSummary} onNavigate={flush} />
      <WorkflowSpine workflow={workflow} recordId={recordId} />
      <RecordWorkspaceNav
        active={activeView}
        captureSummary={captureSummary}
        onNavigate={flush}
        evidenceTrail={showEvidenceTrail ? { recordId, count: evidenceCount } : null}
      />
    </div>
  );
}

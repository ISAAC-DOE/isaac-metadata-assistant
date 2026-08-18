import './screens.css';
import '../components/evidence.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { WorkflowSpine } from '../components/WorkflowSpine';
import { StatusBar } from '../components/StatusBar';
import { FieldGroup } from '../components/FieldGroup';
import { RecordInfoPanel, RecordLinksPanel } from '../components/RecordInfoPanel';
import { RunsSection } from '../components/RunsSection';
import { TranscriptCapturePanel } from '../components/TranscriptCapturePanel';
import { UnmappedNotesPanel } from '../components/UnmappedNotesPanel';
import { AssetReferencesPanel } from '../components/AssetReferencesPanel';
import { ValidateReview } from '../components/ValidateReview';
import { disposeExperiment, flushExperiment } from '../lib/runAutosaveStore';
import { AssistantPanel, type AgentPrompt } from '../components/AssistantPanel';
import { AssistantDrawer } from '../components/AssistantDrawer';
import { LiveSyncNote } from '../components/LiveSyncNote';
import { WorkflowProgressBanner } from '../components/WorkflowProgressBanner';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { CircleAlert, ExternalLink } from '../components/icons';
import { ExperimentGraphPanel } from './graph/ExperimentGraphPanel';
import { LABELS } from '../lib/labels';
import { RECORD_VIEW_PARAM, ROUTES, isRecordView, type RecordViewId } from '../lib/routes';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { useRecordSession } from '../lib/useRecordSession';
import { useWorkspaceScope, useWorkspaceScopeChanged } from '../lib/workspaceScope';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import type { AgentContext } from '../lib/assistantAgent';
import {
  draftGroupsToFieldGroups,
  pendingSummary,
  stripLifecycleSuffix,
  toAdvisoryResult,
  toAuditResult,
  toValidationResult,
} from '../lib/adapt';
import { compose } from '../lib/assistantComposer';
import type { ApiEvidenceEntry, ApiWorkflow, RecordBundle } from '../lib/types';

/**
 * The draft-phase half of the status-bar readout, taken from the SERVER'S OWN
 * workflow derivation instead of from `pending.length === 0`. Called only where
 * `pending.length === 0` (see `LoadedWorkbench`), which is the ONLY thing the
 * caller establishes — see the completion note below.
 *
 * I2 — WHAT WAS FALSE. This read `pending.length > 0 ? 'Draft assembled · N fields
 * to confirm' : 'Draft complete · ready to export'`, and `pending == 0` does not
 * imply export-ready. `apps/api/isaac_api/workspace.py::status` separates
 * `ready_to_export` from `in_review` on exactly that residual — pending 0 with a
 * FAILING official-schema dry-run is `in_review` — and `workflow.derive_workflow`
 * agrees: measured, `derive_workflow(pending_count=0, draft_ok=True, ready=False,
 * exported=False, rev=1)` returns `current_step == 'review_export_readiness'` with
 * the `export` step `blocked`. So on such a record this footer claimed "ready to
 * export" while `WorkflowProgressBanner` on the SAME screen, from the SAME
 * `detail.workflow`, said "Not ready to export yet".
 *
 * F3 — WHAT WAS STILL FALSE AFTER THAT FIX, and what this comment used to claim.
 * It said "every other step maps to the action the banner already names … so the
 * two strings cannot contradict". That was untrue of the retained `Draft complete`
 * PREFIX on the `review_evidence` step. `derive_workflow` leaves `review_evidence`
 * unsatisfied exactly when `pending_count == 0 and draft_ok` is false
 * (`apps/api/isaac_api/workflow.py`), and `draft_ok` is
 * `validate_draft(self.draft).ok` (`workspace.py`) — the no-guessing DRAFT
 * VALIDATOR is failing. `pending_count` is computed independently of it, so an
 * evidence-less finalized field is a draft-validator error that never appears in
 * `pending`. In that state the banner on this screen says "Evidence review needed /
 * This record's evidence checks aren't passing yet." while this line asserted the
 * draft was complete. The state is real, not hypothetical:
 * `apps/api/tests/test_corpus_mutation.py` asserts
 * `derive_workflow(pending_count=0, draft_ok=False, …)['current_step'] ==
 * 'review_evidence'`.
 *
 * So `review_evidence` now carries the banner's OWN words and no completion claim,
 * and the two remaining `Draft complete` prefixes are made only where the server
 * reports `draft_ok` true (`export` and `review_export_readiness` are both
 * downstream of the `review_evidence` step being satisfied). What THIS function
 * guarantees is therefore narrow and checkable: the positive readiness claim is
 * made for exactly one step id, no step whose banner denies the evidence checks
 * carries a completion claim, and an unrecognised or absent `current_step` claims
 * neither readiness nor completion — it states only the thing the caller
 * established, that no confirmation questions are open.
 *
 * Deliberately not worded "not ready to export yet": that phrase contains "ready
 * to export" as a substring, and a footer whose truthfulness is pinned by tests
 * should not be one missed negation away from reading as its own opposite.
 */
export function draftPhaseFromWorkflow(workflow: ApiWorkflow | null): string {
  switch (workflow?.current_step) {
    case 'export':
      return 'Draft complete · ready to export';
    case 'review_export_readiness':
      return 'Draft complete · review export readiness';
    case 'review_evidence':
      // The banner's own heading, verbatim. No "Draft complete": `draft_ok` is
      // false in this state, which is exactly what makes the step current.
      return 'Evidence review needed';
    default:
      return 'No open questions';
  }
}

/**
 * The phase DOT for the same readout, from the same derivation as the text above.
 *
 * F2 — WHAT WAS FALSE, one line away from the corrected sentence. The dot read
 * `pending.length > 0 ? 'attention' : detail.exported ? 'idle' : 'ready'`, and
 * `.dot-ready` is painted `var(--pass-solid)` (`styles/base.css`), a token declared
 * under "signal 1 — validation verdict (RESERVED, hard gate)"
 * (`styles/tokens.css`). So a record with `pending_count == 0` and a FAILING
 * official dry-run rendered the corrected text "Draft complete · review export
 * readiness" beside a PASS-GREEN dot, while the banner above it said "Not ready to
 * export yet": the sentence was fixed and the colour went on making the claim.
 *
 * The tones now mirror `WorkflowProgressBanner`'s two tones for the same step ids —
 * amber `attention` while something still blocks, and the banner's calm action-blue
 * "this is the next step" treatment as `.dot-progress`, which borrows no verdict
 * token. An unrecognised or absent step is `idle` (neutral grey): no claim.
 */
export function draftPhaseDotFromWorkflow(
  workflow: ApiWorkflow | null,
): 'attention' | 'progress' | 'idle' {
  switch (workflow?.current_step) {
    case 'export':
      return 'progress';
    case 'review_export_readiness':
    case 'review_evidence':
      return 'attention';
    default:
      return 'idle';
  }
}

/**
 * S3 · Review Record — the core workbench, live from the record bundle
 * (detail / draft / pending / validate / audit / warnings / evidence / graph —
 * eight endpoints, fetched together, rendered apart). Grouped, calm draft;
 * evidence one tap away in the right panel (above the subordinate assistant,
 * hard-divided); the blocking gate on the left; the trust readout along the
 * bottom with each signal in its own labeled segment, never merged.
 */
export function RecordWorkbench() {
  const { id = '' } = useParams();
  const bundle = useFetch(() => api.getRecordBundle(id), [id]);

  /*
   * THE RUN AUTOSAVE STORE IS DISPOSED HERE — at the RECORD screen's boundary, not at a
   * card's, and that difference is the whole of the Phase-2 change.
   *
   * Save state deliberately outlives a `RunCard`, because a card can unmount and an
   * edit's outcome must survive that. NOTE THE CORRECTION: this used to say a card
   * unmounts "one click away … the Graph tab takes it down". IT NO LONGER DOES — the
   * fields tabpanel is now kept mounted and hidden, precisely so an unsaved textarea is
   * not destroyed by a tab switch, and three other headers in this change were
   * corrected for exactly this while this one was missed. A card still unmounts on
   * paging, searching, filtering and leaving the record, so the reason this store
   * exists is unchanged; only the example was falsified. It must not outlive the record
   * screen either, or the map keeps an entry for every run a session ever opened.
   *
   * `disposeExperiment` IS CONSERVATIVE, AND THE COST OF THAT IS REAL RATHER THAN
   * THEORETICAL. It refuses to drop an entry that is mid-flight or still holding edits,
   * so leaving the screen never discards a write that has not landed — which is the
   * right trade for a scientist. The consequence, MEASURED (12 records abandoned each
   * holding one refused edit retain 12 entries indefinitely; nothing revisits them):
   * the map grows for exactly the runs that still have something unsent. An earlier
   * version of this comment implied disposal bounded growth in general. It bounds it
   * for entries with nothing to remember, which is every entry whose last write
   * succeeded. Entries that hold a refusal are kept ON PURPOSE, because `Retry Save`
   * needs them; a sweep would have to decide when to discard a scientist's unsent edit,
   * and that is not a decision to make silently.
   */
  useEffect(() => () => disposeExperiment(id), [id]);
  // D1 — this record belongs to the workspace scope the surface was opened in. If
  // that scope changes (the walkthrough's temporary workspace was discarded, and
  // with it these records) nothing loaded here describes anything any more. See
  // `lib/workspaceScope.ts` for why the answer is to leave rather than to re-read.
  const scopeChanged = useWorkspaceScopeChanged();

  // P29.4 — the ONE shared record-session owner for this record: the single
  // poller + the authoritative version + the live P29.3 AgentContext the
  // assistant reads. On a change signal it invalidates any stale staged proposal
  // and silently refetches this read-only bundle (never blanks to loading). The
  // fetched bundle stays authoritative; the poller only tells us WHEN to refresh.
  const detail = bundle.status === 'data' ? bundle.data.detail : undefined;
  const session = useRecordSession(id, {
    detail,
    onChange: () => bundle.reloadSilent(),
  });
  const degraded = session.syncDegraded;

  // P29.4b — after a confirmed proposal write, recompute the shared record state
  // (manual fields, workflow, evidence, export readiness) and refetch the bundle
  // so the manual UI reflects the new value.
  const onAgentRefresh = () => {
    session.refresh();
    bundle.reloadSilent();
  };

  /*
   * The workspace this record was read from is no longer the workspace being
   * addressed. Return the reader to a surface that is real in the scope they are
   * now in, replacing this entry so Back does not walk them into it again.
   *
   * Rendered BEFORE the fetch-state branches so no already-loaded field, banner or
   * heading reaches the DOM in the changed scope, and deliberately WITHOUT issuing
   * a fresh request: a 404 here would be true and useless, and its copy would read
   * as a fault when the only thing that happened is that a temporary workspace was
   * discarded exactly as it said it would be.
   */
  if (scopeChanged) return <Navigate to={ROUTES.experiments} replace />;

  if (bundle.status !== 'data') {
    return (
      <AppShell
        variant="record"
        topBar={<TopBar variant="record" title={LABELS.screenReview} />}
        sidebar={<WorkflowSpine workflow={null} recordId={id} />}
        mainPad="pad"
      >
        <h1 className="sr-only">{LABELS.screenReview}</h1>
        {bundle.status === 'loading' ? (
          <LoadingPanel label="Loading the record from the ISAAC API…" />
        ) : (
          <BackendDown error={bundle.error} onRetry={bundle.reload} />
        )}
      </AppShell>
    );
  }

  return (
    <LoadedWorkbench
      id={id}
      bundle={bundle.data}
      degraded={degraded}
      agentContext={session.context}
      agentDegraded={session.degraded}
      onManualRefresh={bundle.reload}
      onAgentRefresh={onAgentRefresh}
      // R1b — a silent refetch that failed (the poll-signalled one above, or the
      // post-write one in `onAgentRefresh`) must not be invisible: the reader
      // would be looking at pre-write state believing it is current.
      refreshFailed={bundle.refreshFailed}
    />
  );
}

// The review-screen INTENT pills. Every entry is an INTENTS-native, target-free
// read intent with a repository-native Title Case label (the panel drops any that
// are not in the frozen registry). Read-only: none mutates — the only write is an
// explicit Confirm on a staged proposal, routed through confirmProposal.
const REVIEW_AGENT_PROMPTS: AgentPrompt[] = [
  { intent: 'explain_current_state', label: 'Explain the Current Step' },
  { intent: 'identify_next_missing_field', label: 'Identify the Next Missing Field' },
  { intent: 'explain_step_blocker', label: 'Explain What Is Blocking' },
  { intent: 'show_inferred_candidates', label: 'Show Inferred Candidates' },
  { intent: 'review_evidence_conflicts', label: 'Review Evidence Conflicts' },
  { intent: 'explain_unknown', label: 'Explain Unknown Fields' },
  { intent: 'review_export_readiness', label: 'Review Export Readiness' },
];

function LoadedWorkbench({
  id,
  bundle,
  degraded,
  agentContext,
  agentDegraded,
  onManualRefresh,
  onAgentRefresh,
  refreshFailed,
}: {
  id: string;
  bundle: RecordBundle;
  degraded: boolean;
  agentContext: AgentContext | undefined;
  agentDegraded: boolean;
  onManualRefresh: () => void;
  onAgentRefresh: () => void;
  refreshFailed: boolean;
}) {
  const navigate = useNavigate();
  const { detail, pending, validate, audit, warnings, evidence, graph } = bundle;

  // The active VIEW is held in the URL, not in component state, so a graph can
  // be linked, bookmarked and reloaded back into. Anything unrecognised falls
  // back to the field workbench — there is no dead view. Switching COPIES the
  // existing params rather than rebuilding the URL, so any other query
  // parameter on the address survives the switch.
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedView = searchParams.get(RECORD_VIEW_PARAM);
  const activeView: RecordViewId = isRecordView(requestedView) ? requestedView : 'fields';
  const selectView = (view: RecordViewId) => {
    /*
     * THE SWITCH FLUSHES THE RUNS' HELD EDITS. It used to get that for free: the
     * fields panel was a conditional branch, so every `RunCard` unmounted and each
     * card's teardown called `flushPending`. The panel now stays mounted (see the
     * tabpanels below), so the property is asked for explicitly instead of being a
     * side effect of destroying the screen. `flushExperiment` is a no-op for a run
     * holding nothing, and never touches a halted or in-flight entry.
     */
    flushExperiment(id);
    const next = new URLSearchParams(searchParams);
    next.set(RECORD_VIEW_PARAM, view);
    setSearchParams(next, { replace: true });
  };

  /*
   * D1 — THE FIELDS PANEL IS MOUNTED ONCE AND THEN NEVER UNMOUNTED, and that is a
   * data-loss fix rather than a rendering preference.
   *
   * It used to be one arm of `activeView === 'graph' ? <graph/> : <fields/>`, so a
   * click on the Graph tab DESTROYED every piece of unsaved text inside it, silently
   * and with no confirmation: the transcript box (typed or dictated), the "Capture a
   * note" box, an open note's Edit-wording textarea and dismissal reason, an open
   * asset create/edit form including its Notes and Caption-verbatim textareas, an open
   * run override value, and any run-field text this build could not parse. `selectView`
   * only writes `?view=` with `replace: true`, so there is no navigation a reader could
   * read as leaving the screen — the text was gone because a tab had been clicked.
   *
   * WHY HIDDEN-BUT-MOUNTED RATHER THAN A DRAFT STORE PER BOX. Every one of the boxes
   * above is a different component with a different shape, so a store would be six
   * migrations and six new sources of truth; the panel is one element, and `hidden` is
   * exactly the semantics wanted — the content leaves the layout AND the accessibility
   * tree, so no duplicate heading, control or landmark is exposed while the graph is
   * open, and axe scans see one view at a time.
   *
   * IT IS LAZY ON FIRST USE, so a deep link to `?view=graph` still costs nothing: the
   * panel's own sections fetch on mount, and mounting them behind a graph the reader
   * asked for would be a page-load cost that view never had.
   *
   * THE GRAPH STAYS CONDITIONAL, deliberately. `RecordGraphView` documents that it is
   * rebuilt from a fresh read every time the view is opened, which is what makes a
   * stale experiment graph structurally impossible; keeping it mounted would cache it.
   */
  const fieldsMounted = useRef(activeView === 'fields');
  if (activeView === 'fields') fieldsMounted.current = true;

  const evidenceByPath = useMemo(
    () => new Map<string, ApiEvidenceEntry>(evidence.map((e) => [e.path, e])),
    [evidence],
  );
  const groups = useMemo(
    () => draftGroupsToFieldGroups(bundle.groups, evidenceByPath),
    [bundle.groups, evidenceByPath],
  );

  // Every group starts collapsed on initial load; user toggles override that.
  const [toggles, setToggles] = useState<Record<string, boolean>>({});
  const isExpanded = (block: string) => toggles[block] ?? false;

  // --- the three signals, each from its own endpoint, each its own segment ---
  // Pre-export, validation is a DRY-RUN and audit has nothing to count — those
  // segments carry the live server result as a note; the reserved PASS/FAIL chip
  // appears only for real (post-export) validation.
  const validationLive = validate.dry_run ? 'pending' : toValidationResult(validate);
  const validationNote = validate.dry_run
    ? `dry-run · ${validate.errors.length} error${validate.errors.length === 1 ? '' : 's'}`
    : undefined;
  const coverageLive = audit.records.length > 0 ? toAuditResult(audit) : 'pending';
  const coverageNote = audit.records.length === 0 ? 'not exported yet' : undefined;
  const advisoryLive = toAdvisoryResult(warnings);

  // The readiness claim comes from `detail.workflow`, never from the pending
  // residual — see `draftPhaseFromWorkflow` above for the measurement. The DOT
  // beside it comes from the same derivation (`draftPhaseDotFromWorkflow`), so the
  // colour cannot claim what the sentence declines to.
  // `exported: true` no longer implies a non-null `record_id`. A record whose runs
  // each export their own official record has NO singular record id — the field is
  // singular and it has several — so this interpolated the literal string and
  // rendered `Exported · null`. Measured. Two lines below, the `filename` prop
  // already guarded with `detail.exported && detail.record_id`; this did not, which
  // is how an unguarded site survived beside a guarded sibling.
  const phase = detail.exported
    ? detail.record_id
      ? `Exported · ${detail.record_id}`
      : 'Exported'
    : pending.length > 0
      ? `Draft assembled · ${pending.length} fields to confirm`
      : draftPhaseFromWorkflow(detail.workflow);

  // D8 — the right rail is the assistant ONLY (advisory). Deterministic evidence
  // lives inline on every field row (truth, in the main column); the whole-record
  // Evidence Trail affordance now sits beneath the WorkflowSpine (see `sidebar`).
  const rightPanel = (
    <AssistantDrawer railClassName="record-right narrow">
      <AssistantPanel
        {...compose({ context: 'review', bundle })}
        experimentId={id}
        recordRev={detail.rev}
        availability={graph.availability}
        agentContext={agentContext}
        degraded={agentDegraded}
        agentPrompts={REVIEW_AGENT_PROMPTS}
        onRefresh={onAgentRefresh}
      />
    </AssistantDrawer>
  );

  // D8 — the whole-record Evidence Trail affordance, moved out of the (removed)
  // right-rail evidence panel to sit directly beneath the workflow. It reuses the
  // EXISTING /evidence route (ROUTES.evidence) — no new route or evidence system.
  const sidebar = (
    <div className="record-aside">
      <WorkflowSpine workflow={detail.workflow} recordId={id} />
      <button
        type="button"
        className="evidence-trail-link"
        data-tutorial-anchor={TUTORIAL_ANCHORS.recordEvidenceTrail}
        onClick={() => navigate(ROUTES.evidence(id))}
      >
        <ExternalLink size={14} strokeWidth={2} aria-hidden="true" />
        <span className="evidence-trail-link-label">{LABELS.evidenceTrail}</span>
        <span className="evidence-trail-link-count">
          {evidence.length} {evidence.length === 1 ? 'entry' : 'entries'}
        </span>
      </button>
    </div>
  );

  return (
    <AppShell
      variant="record"
      topBar={
        <TopBar
          variant="record"
          title={stripLifecycleSuffix(detail.title)}
          filename={
            detail.exported && detail.record_id ? `${detail.record_id}.json` : `${detail.id}`
          }
          stateChip={detail.exported ? 'exported' : 'draft'}
        />
      }
      sidebar={sidebar}
      rightPanel={rightPanel}
      statusBar={
        <StatusBar
          phase={phase}
          phaseDot={
            pending.length > 0
              ? 'attention'
              : detail.exported
                ? 'idle'
                : draftPhaseDotFromWorkflow(detail.workflow)
          }
          validation={validationLive}
          coverage={coverageLive}
          advisory={advisoryLive}
          validationPendingNote={validationNote}
          coveragePendingNote={coverageNote}
        />
      }
      mainPad="pad"
    >
      <h1 className="sr-only">{LABELS.screenReview}</h1>
      <LiveSyncNote
        degraded={degraded}
        refreshFailed={refreshFailed}
        onRefresh={onManualRefresh}
      />
      <WorkflowProgressBanner
        workflow={detail.workflow}
        recordId={id}
        pendingCount={detail.pending_count}
        excludeSteps={['complete_metadata']}
      />

      <RecordViewTabs active={activeView} onSelect={selectView} />

      {activeView === 'graph' && (
        <div
          id={viewPanelId('graph')}
          className="record-view-panel"
          role="tabpanel"
          aria-labelledby={viewTabId('graph')}
          tabIndex={-1}
        >
          <RecordGraphView id={id} />
        </div>
      )}
      {fieldsMounted.current && (
        <div
          id={viewPanelId('fields')}
          className="record-view-panel"
          role="tabpanel"
          aria-labelledby={viewTabId('fields')}
          tabIndex={-1}
          /* Hidden, not removed — see the comment on `fieldsMounted`. `hidden` takes
             the whole panel out of the layout and out of the accessibility tree, so
             nothing in it is announced, focusable or scanned while the graph is up. */
          hidden={activeView !== 'fields'}
        >
      {pending.length > 0 && (
        <div
          className="needsyou-banner"
          role="note"
          data-tutorial-anchor={TUTORIAL_ANCHORS.recordPending}
        >
          <CircleAlert className="needsyou-icon" size={20} strokeWidth={2.2} aria-hidden="true" />
          <div className="needsyou-body">
            <div className="needsyou-title">
              {pending.length} Fields Need Your Confirmation
            </div>
            <p className="needsyou-text">
              These are values the system refuses to guess. Confirm each before this record can
              export — expected, not a failure.
            </p>
            {/* D9/C2 — a NUMBERED list: each item shows the concise structured
             * label as the primary line (never the raw identifier) and its
             * technical locator exactly once as a demoted mono token. The
             * pending data, questions, and ordering are unchanged. */}
            <ol className="needsyou-list">
              {pending.map((p, i) => {
                const summary = pendingSummary(p);
                return (
                  <li key={p.id}>
                    <span className="needsyou-num" aria-hidden="true">
                      {i + 1}
                    </span>
                    <span className="needsyou-item">
                      <span className="needsyou-q">{summary.label}</span>
                      {summary.locator && (
                        <span className="needsyou-about mono">{summary.locator}</span>
                      )}
                    </span>
                  </li>
                );
              })}
            </ol>
          </div>
          <button
            type="button"
            className="btn btn-primary needsyou-action"
            onClick={() => navigate(ROUTES.complete(id))}
          >
            {LABELS.actionReviewAnswer} →
          </button>
        </div>
      )}

      {/*
        THE RUNS SECTION SITS HERE — on this screen, inside the field workbench,
        ABOVE the draft blocks. Three reasons, in the order they decided it:

        1. THIS is the experiment screen. `ExperimentsHome` is the queue: it
           lists experiments and knows nothing about any one of them beyond a
           summary row, so a run editor there would have to load a record to
           show anything, and would then be a second record surface competing
           with this one.
        2. Adding and filling in a run is an ACTION; the draft blocks below are
           a review of what the experiment already holds. The action goes first
           — with five collapsed blocks above it, Add Run would start roughly a
           screen down on a laptop.
        3. A section, not a third view tab. `Record Fields` / `Graph` are two
           renderings of the same content; runs are additional content, and
           putting them behind a tab would hide from a reader on the fields view
           that this experiment has runs at all.
      */}
      <RunsSection experimentId={id} />

      {/*
        VALIDATE & REVIEW SITS DIRECTLY BELOW THE RUNS, and the placement is the
        argument for it: its findings are addressed BY RUN, and the runs a reader
        is being sent back to are the section immediately above.

        IT FETCHES NOTHING ON MOUNT — not one request until the button is pressed
        (see the component header on why: `docs/run-scale-measurements.md` made a
        record's runs a payload cost, and N eager per-run checks would be the same
        mistake in request form). So mounting it here costs this screen nothing on
        load, which is what makes "below the runs" a free choice rather than a
        trade against the screen's first paint.

        IT IS NOT `RunFindings` MOVED. That component is the PASSIVE read-out on
        the export screen, rendering verdicts a bundle already fetched; this is the
        ACTION, on the screen where the fields and runs are edited, and it reaches
        two channels the export bundle never carries — the run's open blocking
        questions and its no-guessing draft report. Both read the same server
        fields and share `runFindingState` and `FindingList` rather than keeping
        two opinions about them.
      */}
      <ValidateReview experimentId={id} />

      {/*
        UNMAPPED NOTES SIT BETWEEN THE RUNS AND THE DRAFT BLOCKS, and the position is
        the argument. What is captured here is content that has NO field — so it
        cannot live inside a field group below, and putting it after them would bury
        the one part of the record that nothing else on this screen can represent.
        Above the blocks and below the runs is where a reader passes it on the way to
        the fields, which is when a note is worth triaging.

        A section, not a tab, for `RunsSection`'s third reason: hiding it behind a tab
        would conceal from a reader on the fields view that this record holds captured
        content nobody has placed yet.

        ── ON THE ORDER OF THESE TWO, 2026-08-16 ──────────────────────────────────
        Both sections were written on separate branches and BOTH claimed the slot
        directly under the runs, each with its own argument. The merge preserves
        both arguments AS WRITTEN rather than picking a winner: Validate & Review
        asked for IMMEDIATE adjacency to the runs, which it has, and this panel
        asked to be ABOVE THE FIELD BLOCKS, which it is. Neither constraint is
        violated, so neither comment above needed editing to stay true.

        WHAT THAT ORDERING DOES NOT SETTLE, and a later slice should: a note is
        unplaced INPUT awaiting triage, and review is the step that judges what has
        been placed — so a reader's natural order is arguably notes first. The
        counter is that Validate & Review fetches nothing until pressed, so it adds
        no visual weight between the runs and these notes. Unresolved rather than
        decided quietly; it becomes a real question once unmapped notes actually
        feed the review state, which today they do not.
      */}
      {/*
        TRANSCRIPT CAPTURE SITS DIRECTLY ABOVE THE NOTES IT PRODUCES, and adjacency
        is the whole of the argument. Finalizing a transcript stores EVERY segment
        of it as an unmapped note, so the panel that creates them and the queue they
        land in are neighbours: a reader who finalizes sees, without scrolling past
        anything else, that their words were kept.

        A section, not a tab, for the reason the two panels around it are sections —
        and here the reason is sharper than usual. Hiding this behind a tab would
        conceal from a reader on the fields view that this record can hold captured
        content at all, and the one thing this feature must never do is let a
        scientist believe what they dictated went nowhere.

        ABOVE the notes panel, not below it, because capture precedes triage. The
        reverse order shows a reader the queue before the thing that fills it.
      */}
      <TranscriptCapturePanel experimentId={id} />

      <UnmappedNotesPanel experimentId={id} />

      {/*
        ASSET REFERENCES SIT BETWEEN THE UNMAPPED NOTES AND THE DRAFT BLOCKS, and the
        position follows the same argument the two sections above it make. An asset
        reference is not a field value — it is a top-level draft block, like the runs
        and the notes — so it cannot live inside a field group below. And it belongs
        AFTER the runs rather than before them, because associating a file with a run
        needs the runs to exist first: a reader who has just added them is in exactly
        the state where "which measurements used this file?" is answerable.

        A section, not a tab, for `RunsSection`'s third reason: hiding it would conceal
        from a reader on the fields view that this record points at files at all — and
        for a record that has runs, an asset no run cites reaches no exported record,
        which is precisely the thing a hidden section would let them not find out.
      */}
      <AssetReferencesPanel experimentId={id} />

      {groups.map((group) => (
        <FieldGroup
          key={group.block}
          group={group}
          expanded={isExpanded(group.block)}
          onToggle={() =>
            setToggles((prev) => ({
              ...prev,
              [group.block]: !isExpanded(group.block),
            }))
          }
        />
      ))}

      {/*
        THE TWO RECORD-LEVEL SECTIONS — the record's own identity, and the
        relationships it declares to other records.

        THEY ARE MOUNTED ONCE, HERE, AND NEVER INSIDE A RUN, because both are
        record-level and that is measured rather than assumed: `links` is on the
        fail-closed "not overridable" list in
        `routes.EXPERIMENT_OVERRIDABLE_ADDRESSES` and `workspace.py` records it as
        neither inherited nor copied into a run's export draft; the classification
        trio lives in the draft's `meta`, which the same module calls "the same for
        every run by construction"; and `timestamps.created_utc` is on the
        unclassified list too, so it is not inherited either
        (`docs/run-scope-decision-packet.md` §2–§3). `RunCard` and `RunsSection`
        are untouched by this slice.

        WHY THEY CLOSE THE COLUMN RATHER THAN OPEN IT. The blocks above are the
        science the reader came for, and the runs above those are the action; what
        a record IS, and what it points at, is reference material about the whole
        of it, so it reads as a footer rather than as a preamble. Both are
        collapsed on arrival like every block above them, so the cost of being
        wrong about that is one line each.

        A SECOND, SMALLER REASON, STATED RATHER THAN HIDDEN: four existing specs
        address "the first `.fg-header` on the screen" as a way of reaching the
        first DRAFT block (`live-screens`, `record-session`,
        `p33-hqa-6-heading-and-header`). Mounting these sections above the blocks
        silently re-pointed that selector at a section those specs know nothing
        about. Ordering was not decided BY the tests — the paragraph above is the
        reason — but rewriting four unrelated specs to keep a placement that was
        already the weaker of the two would have been collateral churn.
      */}
      <RecordInfoPanel detail={detail} groups={bundle.groups} artifacts={bundle.artifacts} />
      <RecordLinksPanel artifacts={bundle.artifacts} />
        </div>
      )}
    </AppShell>
  );
}

// --- the record's two VIEWS ------------------------------------------------
//
// The field workbench and the experiment-scoped graph are two views of the SAME
// record, so they are local page tabs on this screen rather than a separate
// route or a separate nav entry — the same `.section-tabs` pattern (roving
// tabindex, arrow/Home/End) Project Memory and Governance already use, and the
// same `?param=` deep-link mechanism as Settings, Governance and Statistics.
//
// The graph is deliberately mounted HERE and not on a screen a scientist has to
// go looking for: this is the surface they are already on when they are working
// on a record.

const RECORD_VIEWS: { id: RecordViewId; label: string }[] = [
  { id: 'fields', label: 'Record Fields' },
  { id: 'graph', label: 'Graph' },
];

const viewTabId = (id: RecordViewId) => `record-view-tab-${id}`;
const viewPanelId = (id: RecordViewId) => `record-view-panel-${id}`;

function RecordViewTabs({
  active,
  onSelect,
}: {
  active: RecordViewId;
  onSelect: (view: RecordViewId) => void;
}) {
  function onKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      nextIndex = (index + 1) % RECORD_VIEWS.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      nextIndex = (index - 1 + RECORD_VIEWS.length) % RECORD_VIEWS.length;
    } else if (e.key === 'Home') {
      nextIndex = 0;
    } else if (e.key === 'End') {
      nextIndex = RECORD_VIEWS.length - 1;
    }
    if (nextIndex === null) return;
    e.preventDefault();
    const next = RECORD_VIEWS[nextIndex];
    onSelect(next.id);
    (document.getElementById(viewTabId(next.id)) as HTMLButtonElement | null)?.focus();
  }

  return (
    <div className="section-tabs" role="tablist" aria-label="Record views">
      {RECORD_VIEWS.map((view, i) => {
        const selected = active === view.id;
        return (
          <button
            key={view.id}
            id={viewTabId(view.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={selected ? viewPanelId(view.id) : undefined}
            tabIndex={selected ? 0 : -1}
            className={`section-tab${selected ? ' active' : ''}`}
            onClick={() => onSelect(view.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {view.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The graph's own data load.
 *
 * Deliberately a SEPARATE fetch from the record bundle, and deliberately lazy:
 * this component only mounts when the Graph view is selected, so a reader who
 * never opens it never pays for it. It is also deliberately NOT cached — the
 * graph is rebuilt from a fresh read every time the view is opened, which is
 * what makes a stale experiment graph structurally impossible.
 *
 * The scope pair is what enforces tutorial isolation at the model boundary: the
 * scope the bundle was READ in is captured at mount, and compared against the
 * scope the surface is addressing now. They disagree only when a worked-example
 * session was entered or left while this view was open — at which point the
 * records this graph describes no longer exist in the workspace being
 * addressed, and the model refuses rather than drawing them.
 */
function RecordGraphView({ id }: { id: string }) {
  const bundle = useFetch(() => api.getExperimentGraphBundle(id), [id]);
  const currentScope = useWorkspaceScope();
  const readInScope = useRef(currentScope);

  if (bundle.status === 'loading') {
    return <LoadingPanel label="Loading this experiment's graph from the ISAAC API…" />;
  }
  if (bundle.status !== 'data') {
    return <BackendDown error={bundle.error} onRetry={bundle.reload} />;
  }
  return (
    <ExperimentGraphPanel
      bundle={bundle.data}
      readInScope={readInScope.current}
      currentScope={currentScope}
    />
  );
}

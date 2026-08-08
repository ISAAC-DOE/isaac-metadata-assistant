import './screens.css';
import '../components/evidence.css';
import { useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { WorkflowSpine } from '../components/WorkflowSpine';
import { StatusBar } from '../components/StatusBar';
import { FieldGroup } from '../components/FieldGroup';
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
    const next = new URLSearchParams(searchParams);
    next.set(RECORD_VIEW_PARAM, view);
    setSearchParams(next, { replace: true });
  };

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
  const phase = detail.exported
    ? `Exported · ${detail.record_id}`
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

      {activeView === 'graph' ? (
        <div
          id={viewPanelId('graph')}
          className="record-view-panel"
          role="tabpanel"
          aria-labelledby={viewTabId('graph')}
          tabIndex={-1}
        >
          <RecordGraphView id={id} />
        </div>
      ) : (
        <div
          id={viewPanelId('fields')}
          className="record-view-panel"
          role="tabpanel"
          aria-labelledby={viewTabId('fields')}
          tabIndex={-1}
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

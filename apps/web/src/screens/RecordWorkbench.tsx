import './screens.css';
import '../components/evidence.css';
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { useRecordSession } from '../lib/useRecordSession';
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
import type { ApiEvidenceEntry, RecordBundle } from '../lib/types';

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

  const phase = detail.exported
    ? `Exported · ${detail.record_id}`
    : pending.length > 0
      ? `Draft assembled · ${pending.length} fields to confirm`
      : 'Draft complete · ready to export';

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
          phaseDot={pending.length > 0 ? 'attention' : detail.exported ? 'idle' : 'ready'}
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

      {pending.length > 0 && (
        <div className="needsyou-banner" role="note">
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
    </AppShell>
  );
}

import './screens.css';
import { useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { EvidenceTrailPanel } from '../components/EvidenceTrailPanel';
import { EvidenceClassificationPanel } from '../components/EvidenceClassificationPanel';
import { CsvReconcilePanel } from '../components/CsvReconcilePanel';
import { SourcePreview } from '../components/SourcePreview';
import { AssistantPanel } from '../components/AssistantPanel';
import { AssistantDrawer } from '../components/AssistantDrawer';
import { GraphStatusChip } from '../components/GraphStatusChip';
import { StatusBar } from '../components/StatusBar';
import { LiveSyncNote } from '../components/LiveSyncNote';
import { WorkflowProgressBanner } from '../components/WorkflowProgressBanner';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { EvidenceGraphPanel } from './graph/EvidenceGraphPanel';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { compose } from '../lib/assistantComposer';
import { useFetch } from '../lib/useFetch';
import { useRecordSession } from '../lib/useRecordSession';
import { useWorkspaceScope, useWorkspaceScopeChanged } from '../lib/workspaceScope';
import { RUNS_PAGE_SIZE } from '../lib/runPaging';
import {
  EVIDENCE_VIEW_PARAM,
  RECORD_RUN_PARAM,
  ROUTES,
  isEvidenceView,
  type EvidenceViewId,
} from '../lib/routes';
import type { AgentContext } from '../lib/assistantAgent';
import {
  citedLinesForEntry,
  evidenceEntriesToTrail,
  primarySourceFile,
  provenanceFor,
} from '../lib/adapt';
import type { EvidenceBundle } from '../lib/types';

/**
 * S5 · Evidence & File Preview — "where did this come from?" answered in-app,
 * live from the record bundle (evidence trail + exported record/sidecar +
 * cited-source previews + memory freshness). Selecting an evidence entry drives
 * the source preview, highlighting the exact cited line in the real fixture. The
 * sidecar is labeled an assistant convention throughout. Handles both pre-export
 * (draft evidence, no written artifacts) and post-export (real sidecar) honestly.
 */
export function EvidenceExplorer() {
  const { id = '' } = useParams();
  const bundle = useFetch(() => api.getEvidenceBundle(id), [id]);

  // P29.4 — the ONE shared record-session owner (single poller + authoritative
  // version + live AgentContext). Read-only surface: silently refetch on a change
  // signal (never blanks); the owner also invalidates any stale staged proposal.
  const detail = bundle.status === 'data' ? bundle.data.detail : undefined;
  const session = useRecordSession(id, {
    detail,
    onChange: () => bundle.reloadSilent(),
  });
  const degraded = session.syncDegraded;

  // D1 — the evidence trail on this screen belongs to the workspace scope it was
  // opened in. See `lib/workspaceScope.ts`: a scope change destroys the record the
  // trail is about, so the trail describes nothing and must not stay on screen.
  const scopeChanged = useWorkspaceScopeChanged();
  if (scopeChanged) return <Navigate to={ROUTES.experiments} replace />;

  if (bundle.status !== 'data') {
    return (
      <AppShell
        variant="record"
        topBar={<TopBar variant="record" title={LABELS.screenEvidence} recordId={id} />}
        mainPad="pad"
      >
        <h1 className="sr-only">{LABELS.screenEvidence}</h1>
        {bundle.status === 'loading' ? (
          <LoadingPanel label="Loading the evidence trail from the ISAAC API…" />
        ) : (
          <BackendDown error={bundle.error} onRetry={bundle.reload} />
        )}
      </AppShell>
    );
  }

  return (
    <LoadedEvidence
      id={id}
      data={bundle.data}
      degraded={degraded}
      agentContext={session.context}
      agentDegraded={session.degraded}
      onManualRefresh={bundle.reload}
      // R1b — a change-signalled refetch that failed must be stated, or the
      // reader is looking at a superseded evidence trail with no hint of it.
      refreshFailed={bundle.refreshFailed}
    />
  );
}

function LoadedEvidence({
  id,
  data,
  degraded,
  agentContext,
  agentDegraded,
  onManualRefresh,
  refreshFailed,
}: {
  id: string;
  data: EvidenceBundle;
  degraded: boolean;
  agentContext: AgentContext | undefined;
  agentDegraded: boolean;
  onManualRefresh: () => void;
  refreshFailed: boolean;
}) {
  const { detail, evidence, artifacts, graph, sourcePreviews, classification } = data;
  const navigate = useNavigate();

  /*
   * The screen's two VIEWS — the evidence LIST (everything below, unchanged)
   * and the evidence GRAPH.
   *
   * On the same `?view=` mechanism the record screen already uses, so the graph
   * is deep-linkable and a `?run=` focus survives switching between them. `list`
   * is the fallback for anything unrecognised, which is what keeps every
   * existing bookmark to this URL landing on exactly the screen it always did.
   */
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedView = searchParams.get(EVIDENCE_VIEW_PARAM);
  const activeView: EvidenceViewId = isEvidenceView(requestedView) ? requestedView : 'list';
  const focusRunId = searchParams.get(RECORD_RUN_PARAM);

  // Both writers COPY the existing params rather than replacing them, so
  // switching view keeps the focused run and focusing a run keeps the view.
  const selectView = (view: EvidenceViewId) => {
    const next = new URLSearchParams(searchParams);
    if (view === 'list') next.delete(EVIDENCE_VIEW_PARAM);
    else next.set(EVIDENCE_VIEW_PARAM, view);
    setSearchParams(next, { replace: true });
  };
  const selectFocusRun = (runId: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (runId === null) next.delete(RECORD_RUN_PARAM);
    else next.set(RECORD_RUN_PARAM, runId);
    setSearchParams(next, { replace: true });
  };

  const viewTabs = <EvidenceViewTabs active={activeView} onSelect={selectView} />;

  // P28.5 — the evidence-support view is bound to `record_rev`. Compare it to the
  // rev encoded in the loaded detail's version token (`generation.rev`, so the
  // last segment is the rev — the exact value the backend reports as record_rev).
  // If they disagree the view may be behind the record; we surface a subtle
  // refresh affordance rather than silently flipping the classification.
  const detailRev = Number(detail.version.split('.').pop());
  const classificationStale =
    Number.isFinite(detailRev) && detailRev !== classification.record_rev;

  const entries = useMemo(() => evidenceEntriesToTrail(evidence), [evidence]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const selected = entries.find((e) => e.key === selectedKey) ?? entries[0];

  /*
   * The graph branch sits ABOVE the no-evidence early return below, deliberately.
   * An experiment can carry runs while recording no EXPERIMENT-LEVEL evidence at
   * all, and that record's graph is exactly the one worth looking at. Putting the
   * branch after the early return would have made the graph unreachable for it.
   *
   * It sits BELOW every hook in this component, equally deliberately: switching
   * view re-renders the same component, so a return placed above `useMemo` /
   * `useState` would change the hook count between renders.
   */
  if (activeView === 'graph') {
    return (
      <AppShell
        variant="record"
        topBar={
          <TopBar
            variant="record"
            title={detail.title}
            recordId={id}
            surface={LABELS.screenEvidence}
          />
        }
        mainPad="pad"
      >
        <h1 className="sr-only">{LABELS.screenEvidence}</h1>
        {viewTabs}
        <div
          id={evidenceViewPanelId('graph')}
          role="tabpanel"
          aria-labelledby={evidenceViewTabId('graph')}
        >
          <EvidenceGraphView
            id={id}
            detail={detail}
            evidence={evidence}
            classification={classification}
            focusRunId={focusRunId}
            onFocusRun={selectFocusRun}
          />
        </div>
      </AppShell>
    );
  }

  // TWO DIFFERENT FACTS, AND THIS SCREEN USED TO HOLD ONLY ONE OF THEM.
  // `exported` was `artifacts.sidecar !== null` — a DERIVED proxy that never reads
  // `detail.exported`. A record whose runs each export their own official record
  // has no EXPERIMENT-LEVEL sidecar, so the proxy said false for a record that has
  // been exported N times, and the screen rendered `draft · <id>` in the TopBar and
  // a **Draft** state chip. `:202` was quoted as a guarded sibling; the guard
  // stopped a printed null and produced a false claim in its place, which is the
  // category this branch itself created.
  // Whether this record has an experiment-level sidecar OF ITS OWN is a separate
  // question, and it is asked below where it belongs — of `artifacts.sidecar`.
  const exported = detail.exported;
  const directTotal = entries.filter((e) => !e.namespaced).length;

  const sidecar = artifacts.sidecar;
  const meta = sidecar
    ? {
        schema_version: String(sidecar.schema_version ?? '1.05'),
        generated_utc: String(sidecar.generated_utc ?? ''),
      }
    : exported
      ? // Exported, but with no sidecar of its OWN. Saying "not exported yet" here
        // was simply false; the honest statement is that the sidecars belong to the
        // runs, and this screen does not list them (see `get_evidence` in the
        // fan-out disclosure — deferred for cost, not blocked on a question).
        { schema_version: '1.05', generated_utc: 'one sidecar per run — not listed here' }
      : { schema_version: '1.05 · target', generated_utc: 'not exported yet' };

  const recordJson = artifacts.record ? JSON.stringify(artifacts.record, null, 2) : null;
  const sidecarJson = sidecar ? JSON.stringify(sidecar, null, 2) : null;

  if (!selected) {
    return (
      <AppShell
        variant="record"
        topBar={
          <TopBar
            variant="record"
            title={detail.title}
            recordId={id}
            surface={LABELS.screenEvidence}
          />
        }
        mainPad="pad"
      >
        <h1 className="sr-only">{LABELS.screenEvidence}</h1>
        {viewTabs}
        <p className="preview-empty" role="note">
          No evidence has been recorded for this experiment yet.
        </p>
      </AppShell>
    );
  }

  const sourceFile = primarySourceFile(selected);
  const preview = sourceFile ? (sourcePreviews[sourceFile] ?? null) : null;
  const citedLines = citedLinesForEntry(selected, sourceFile);
  const provenance = provenanceFor(selected);

  // P25.5: the grounded assistant now mounts in the Evidence context (Phase 25
  // plan §20). It is subordinate — the Evidence Trail + Source Preview (truth)
  // render first/left; the assistant only echoes counts, the sidecar convention
  // and artifact paths this screen already holds. `selectedPath = selected.key`
  // so a different trail selection updates the multiplicity answer live. It
  // mounts ONLY on this loaded path — never in loading / backend-down / the
  // zero-evidence empty state, where there is no record data to be subordinate to.
  const rightPanel = (
    <AssistantDrawer railClassName="record-right narrow">
      <AssistantPanel
        {...compose({ context: 'evidence', bundle: data, selectedPath: selected.key })}
        experimentId={detail.id}
        recordRev={detail.rev}
        /* This screen's STATUS BAR already renders a `GraphStatusChip` for the
           availability axis (see the `graph` slot below), so the page owns the
           visible label. The panel is still GIVEN the axis — it needs it for
           `classifyAnswer` and for the memory caveat — but does not restate it
           visibly: one fact, one wording, one place. (P33 HQA #7; retained
           through P36V S-A.) */
        availability={graph.availability}
        showAvailabilityStatus={false}
        agentContext={agentContext}
        degraded={agentDegraded}
      />
    </AssistantDrawer>
  );

  return (
    <AppShell
      variant="evidence"
      topBar={
        <TopBar
          variant="record"
          title={detail.title}
          /* Three states, not two. There IS a sidecar filename; there is an
             exported record with no singular sidecar (a fan-out), where the id is
             the only true thing to show; and there is a draft. Collapsing the
             middle one into `draft · <id>` called an exported record a draft. */
          filename={
            exported
              ? detail.record_id
                ? `${detail.record_id}.evidence.json`
                : detail.id
              : `draft · ${detail.id}`
          }
          stateChip={exported ? 'exported' : 'draft'}
          recordId={id}
          surface={LABELS.screenEvidence}
        />
      }
      sidebar={
        <EvidenceTrailPanel
          entries={entries}
          directTotal={directTotal}
          selectedKey={selected.key}
          onSelect={setSelectedKey}
          meta={meta}
        />
      }
      rightPanel={rightPanel}
      statusBar={
        <StatusBar
          phase={LABELS.evidenceTrail}
          phaseDot="idle"
          note={`sidecar · assistant convention, not an official ISAAC standard · ${directTotal} direct paths counted in coverage`}
          graph={<GraphStatusChip availability={graph.availability} note={graph.note} />}
        />
      }
      /* `none`: this is a split layout — the trail rail, `.evclass`, `.csv-recon`
         and `.preview` each own their horizontal inset, so an ambient 28px from
         `pad` would double-inset them. The TOP gutter is NOT opted out of: the
         shell applies `--main-top-gutter` to every unpadded main (chrome.css),
         which is what stopped this screen rendering flush against the TopBar
         while its own loading / no-evidence branches got 22px. */
      mainPad="none"
    >
      <h1 className="sr-only">{LABELS.screenEvidence}</h1>
      {/* `.main-inset-control`, NOT `.main-inset` — same measure, different
          contract. The notices wrapper below is specified to hold only the two
          transient notices and to carry no vertical margin, so that an EMPTY
          wrapper adds no space; `evidence-hierarchy` pins both that composition
          and the fact that exactly one `.main-inset` is a direct child of main.
          A permanently-present control mounted inside it would retire the
          no-double-gutter property those assertions exist to protect. */}
      <div className="main-inset-control">{viewTabs}</div>
      {/* One shared horizontal inset for BOTH transient notices, so the degraded
          live-sync note lines up with the banner and the panels below instead of
          running edge-to-edge. Each child renders null when it has nothing to
          say; the wrapper carries no vertical margin, so an empty wrapper adds
          no space and `.evclass` still starts exactly one gutter below the bar. */}
      <div className="main-inset">
        <LiveSyncNote
          degraded={degraded}
          refreshFailed={refreshFailed}
          onRefresh={onManualRefresh}
        />
        <WorkflowProgressBanner
          workflow={detail.workflow}
          recordId={id}
          pendingCount={detail.pending_count}
        />
      </div>
      <EvidenceClassificationPanel
        classification={classification}
        stale={classificationStale}
        onRefresh={onManualRefresh}
      />
      <CsvReconcilePanel
        experimentId={id}
        version={detail.version}
        onGoToComplete={() => navigate(ROUTES.complete(id))}
      />
      <SourcePreview
        entry={selected}
        provenance={provenance}
        preview={preview}
        citedLines={citedLines}
        recordJson={recordJson}
        sidecarJson={sidecarJson}
      />
    </AppShell>
  );
}

// --- the Evidence screen's two VIEWS ---------------------------------------
//
// The evidence LIST and the evidence GRAPH are two views of the SAME recorded
// evidence, so they are local page tabs on this screen rather than a separate
// route or nav entry — the same `.section-tabs` pattern (roving tabindex,
// arrow/Home/End) that Project Memory, Governance, Settings and the record
// screen already use.
//
// The graph is an ADDITION. Selecting "Evidence List" renders precisely what
// this screen rendered before it existed.

const EVIDENCE_VIEWS: { id: EvidenceViewId; label: string }[] = [
  { id: 'list', label: 'Evidence List' },
  { id: 'graph', label: 'Evidence Graph' },
];

const evidenceViewTabId = (id: EvidenceViewId) => `evidence-view-tab-${id}`;
const evidenceViewPanelId = (id: EvidenceViewId) => `evidence-view-panel-${id}`;

function EvidenceViewTabs({
  active,
  onSelect,
}: {
  active: EvidenceViewId;
  onSelect: (view: EvidenceViewId) => void;
}) {
  function onKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      nextIndex = (index + 1) % EVIDENCE_VIEWS.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      nextIndex = (index - 1 + EVIDENCE_VIEWS.length) % EVIDENCE_VIEWS.length;
    } else if (e.key === 'Home') {
      nextIndex = 0;
    } else if (e.key === 'End') {
      nextIndex = EVIDENCE_VIEWS.length - 1;
    }
    if (nextIndex === null) return;
    e.preventDefault();
    const next = EVIDENCE_VIEWS[nextIndex];
    onSelect(next.id);
    (document.getElementById(evidenceViewTabId(next.id)) as HTMLButtonElement | null)?.focus();
  }

  return (
    <div className="section-tabs" role="tablist" aria-label="Evidence views">
      {EVIDENCE_VIEWS.map((view, i) => {
        const selected = active === view.id;
        return (
          <button
            key={view.id}
            id={evidenceViewTabId(view.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            /*
             * `aria-controls` is deliberately ABSENT.
             *
             * It is optional in the ARIA tabs pattern, and the LIST view is not
             * one element: its trail rail is a sidebar region and its
             * classification, reconciliation and preview are in main. Pointing
             * `aria-controls` at either half would tell a screen-reader user
             * that the tab governs less than it does, which is worse than
             * saying nothing. `role="tab"` + `aria-selected` still convey the
             * set, the position and the current choice.
             */
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
 * The evidence graph's own data load.
 *
 * `detail`, `evidence` and `classification` are handed down from the bundle the
 * screen already holds, so the graph and the list are looking at the SAME read
 * of the record — a graph that refetched them could disagree with the list
 * beside it about what is recorded.
 *
 * The RUNS are the one thing this view needs that the bundle does not carry,
 * and they are read as a BOUNDED PAGE. `docs/run-scale-measurements.md` measured
 * the cost of the run list as the payload (~7.5 KiB per run; 1000 runs is
 * 7.47 MiB and a 10.3 s load), which is why the Runs section is paged — a graph
 * that asked for every run to draw a picture would undo that measurement's whole
 * point. It draws what is loaded and SAYS so (`runs_bounded`).
 *
 * Run CHECKS are not fetched here at all: the panel asks for one run's findings
 * when a reader opens that run.
 *
 * The scope pair enforces tutorial isolation at the model boundary: the scope
 * the data was READ in is captured at mount and compared with the scope the
 * surface is addressing now.
 */
function EvidenceGraphView({
  id,
  detail,
  evidence,
  classification,
  focusRunId,
  onFocusRun,
}: {
  id: string;
  detail: EvidenceBundle['detail'];
  evidence: EvidenceBundle['evidence'];
  classification: EvidenceBundle['classification'];
  focusRunId: string | null;
  onFocusRun: (runId: string | null) => void;
}) {
  const runs = useFetch(() => api.listRuns(id, { limit: RUNS_PAGE_SIZE }), [id]);
  const currentScope = useWorkspaceScope();
  const readInScope = useRef(currentScope);

  if (runs.status === 'loading') {
    return <LoadingPanel label="Loading this experiment's runs from the ISAAC API…" />;
  }
  if (runs.status !== 'data') {
    return <BackendDown error={runs.error} onRetry={runs.reload} />;
  }

  return (
    <EvidenceGraphPanel
      experimentId={id}
      detail={detail}
      evidence={evidence}
      classification={classification}
      runs={runs.data.runs}
      runsMeta={{
        total: runs.data.total,
        matched: runs.data.matched,
        returned: runs.data.returned,
        offset: runs.data.offset,
      }}
      readInScope={readInScope.current}
      currentScope={currentScope}
      focusRunId={focusRunId}
      onFocusRun={onFocusRun}
      onRequestRunCheck={(runId) => api.checkRun(id, runId)}
    />
  );
}

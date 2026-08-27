import './screens.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { EvidenceTrailPanel } from '../components/EvidenceTrailPanel';
import { EvidenceClassificationPanel } from '../components/EvidenceClassificationPanel';
import { ConflictResolutionPanel } from '../components/ConflictResolutionPanel';
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
import type { EvidenceSubFetch } from '../lib/evidenceGraph';
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
            degraded={degraded}
            refreshFailed={refreshFailed}
            onManualRefresh={onManualRefresh}
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
      {/*
        DIRECTLY BELOW EVIDENCE SUPPORT, and that placement is the point.
        `EvidenceClassificationPanel`'s guidance for `conflicting_evidence` tells a
        reader to review the competing sources and record which one is right — an
        instruction that had no control behind it anywhere in this build. This is
        that control, one section below the sentence that sends a reader looking
        for it.

        NOT on Validate & Review, which was the other candidate. That surface's own
        header states, and its tests pin, that "NOTHING HERE SUBMITS ANYTHING,
        EXPORTS ANYTHING, OR REPAIRS ANYTHING — every control is a read"; mounting a
        write there would falsify a documented invariant to save a screen.
      */}
      <ConflictResolutionPanel experimentId={id} />
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
 *
 * ── FRESHNESS: the runs follow the version they are LABELLED with ───────────
 *
 * `EvidenceGraphPanel` prints "Built from this record at version <rev>. Nothing
 * here is cached across a version change." That version is `detail.version`,
 * which the shared poller DOES refresh (the screen's `onChange` calls
 * `bundle.reloadSilent()`). The runs below were fetched with deps `[id]` and so
 * refreshed NEVER — measured, not supposed. The consequence was a specific
 * false statement rather than a general staleness: after a run was edited or
 * removed from another surface, the poll advanced `detail.version`, the panel's
 * `key={freshnessKey}` remounted and evicted every run check, and the rebuilt
 * graph printed the NEW version over the OLD run rows — including a run node,
 * its whole subtree and its `has_run` edge for a run the server had deleted.
 * The sentence about the cache was true; the number over the rows was not.
 *
 * So a moved version silently refetches the runs. `reloadSilent`, NOT the deps
 * array: putting `detail.version` in the deps flips `useFetch` back to
 * `status: 'loading'`, which would blank this whole surface to a LoadingPanel on
 * every detected change — exactly the blanking `reloadSilent` exists to avoid on
 * a read-only screen.
 *
 * ── …and when the refresh does NOT land, this surface now says so ────────────
 *
 * The graph branch rendered no `LiveSyncNote`, so a degraded poller (>= 3
 * consecutive failures) and a failed silent refetch were both invisible HERE
 * while being stated one tab away on the evidence list. A surface that asserts
 * the version it was built from is the last surface that should keep that quiet,
 * and it was the only one with no manual recourse on screen.
 *
 * ── …AND THE NOTE SAT BESIDE THE FALSE SENTENCE RATHER THAN CORRECTING IT ───
 *
 * The re-read above closed the SUCCESS path and left the FAILURE path open, and
 * an independent review measured the residue: the version ref advanced BEFORE
 * the await, `reloadSilent` keeps the old rows and raises `refreshFailed`, and
 * the panel printed `detail.version` unconditionally. So when `/runs` failed
 * while the version poll succeeded the screen showed version 2.0 over rows read
 * at 1.0, with the refresh-failed note beside it — strictly better than no note,
 * and still a sentence asserting the new version over the old rows.
 *
 * The fix is the two-version split below: `requestedRunsVersion` (what a re-read
 * was ISSUED for) and `loadedRunsVersion` (what the rows on screen were READ
 * at), with the second passed to the panel so the freshness sentence can name
 * both when they differ. See `EvidenceGraphPanelProps.runsVersion`.
 */
/**
 * ONE ADDITIVE SUB-READ, re-read silently whenever the record's version moves.
 *
 * The same two-part mechanism the runs use, factored so five call sites cannot
 * drift into five slightly different versions of it:
 *
 *  · `reloadSilent` on a version change rather than `deps`, because `deps` flips
 *    `useFetch` to `loading` and would blank what the graph is drawing every time
 *    the record moves;
 *  · the ref advances BEFORE the request, which is exactly right for its one job
 *    (fire once per distinct version, never loop) and is NOT a statement about
 *    what has landed.
 *
 * Nothing here claims the re-read succeeded, and nothing needs to: every one of
 * these responses publishes the version it was read at, and `buildEvidenceGraph`
 * compares that published token with the record's. So a failed silent re-read
 * leaves the old data on screen carrying its own old token, and the graph says
 * which version it describes rather than inheriting the claim of a request that
 * did not land. That is why this hook does not surface `refreshFailed`: the
 * stale-version note is derived from the data itself and cannot be out of step
 * with it.
 */
function useVersionedSubFetch<T>(
  fetcher: () => Promise<T>,
  deps: readonly unknown[],
  version: string,
): EvidenceSubFetch<T> {
  const fetched = useFetch(fetcher, deps);
  const requested = useRef(version);
  const reloadSilent = fetched.reloadSilent;
  useEffect(() => {
    if (requested.current === version) return;
    requested.current = version;
    reloadSilent();
  }, [version, reloadSilent]);

  const status = fetched.status;
  const payload = fetched.status === 'data' ? fetched.data : undefined;
  const message = fetched.status === 'error' ? fetched.error.message : undefined;

  /*
   * THE RETURNED STATE IS MEMOISED, AND THAT IS NOT A TIDINESS CHOICE.
   *
   * `EvidenceGraphPanel` puts all five of these in the dependency array of the
   * `useMemo` that calls `buildEvidenceGraph` — which runs `computeLayout`, an
   * O(n²) force-directed relaxation over `LAYOUT_ITERATIONS = 240` passes,
   * synchronously on the render path, for a graph bounded at
   * `MAX_EVIDENCE_GRAPH_NODES = 1200`. Returning a fresh object literal on every
   * render made that dependency array change on every render, so the memo held
   * nothing: every re-render of this screen — the record-session poll adopting a
   * change, the agent-context read landing, each of these five reads resolving —
   * rebuilt the whole graph and re-ran the layout. Memoised on `status` plus the
   * payload identity, the object is stable exactly as long as the underlying fetch
   * state is, which is what the panel's memo was written to assume.
   *
   * Nothing about WHAT is returned changes; only its identity is now stable.
   */
  return useMemo<EvidenceSubFetch<T>>(() => {
    if (status === 'loading') return { state: 'loading' };
    if (status === 'error') return { state: 'error', message: message ?? '' };
    return { state: 'data', data: payload as T };
  }, [status, payload, message]);
}

function EvidenceGraphView({
  id,
  detail,
  evidence,
  classification,
  focusRunId,
  onFocusRun,
  degraded,
  refreshFailed,
  onManualRefresh,
}: {
  id: string;
  detail: EvidenceBundle['detail'];
  evidence: EvidenceBundle['evidence'];
  classification: EvidenceBundle['classification'];
  focusRunId: string | null;
  onFocusRun: (runId: string | null) => void;
  degraded: boolean;
  refreshFailed: boolean;
  onManualRefresh: () => void;
}) {
  const runs = useFetch(() => api.listRuns(id, { limit: RUNS_PAGE_SIZE }), [id]);
  const currentScope = useWorkspaceScope();
  const readInScope = useRef(currentScope);

  /*
   * The four routes the graph reads BESIDES this screen's bundle — conflicts,
   * notes, provenance, assets, and the revision history it reads for one
   * question. Every one of them is already served to a record screen; no backend
   * route was added for the graph, and `api.ts` records that policy.
   *
   * THEY DO NOT BLOCK, and that is the point of `useVersionedSubFetch`. The runs
   * above are structural — without them there is no graph — so their loading and
   * error states own the branch below. These five are ADDITIVE: a graph without
   * its conflicts is still the graph, and turning one failed sub-read into a
   * whole-screen `BackendDown` would trade a note for a blank page. So each state
   * is handed to the panel, which draws what it has and says what it does not.
   *
   * `reloadSilent` on a version change, NOT the deps array, for the reason the
   * runs use it: deps would flip `useFetch` to `loading`, and the graph would
   * drop every conflict and note it is drawing each time the record moves.
   */
  const conflicts = useVersionedSubFetch(() => api.listConflicts(id), [id], detail.version);
  const notes = useVersionedSubFetch(() => api.listNotes(id), [id], detail.version);
  const provenance = useVersionedSubFetch(() => api.getProvenance(id), [id], detail.version);
  const assets = useVersionedSubFetch(() => api.listAssets(id), [id], detail.version);
  const revisions = useVersionedSubFetch(
    () => api.getRevisionHistory(id),
    [id],
    detail.version,
  );

  /*
   * TWO VERSIONS, AND CONFLATING THEM IS WHAT LEFT THE HEADLINE FALSE.
   *
   * `requestedRunsVersion` is the version a re-read was ISSUED for. It advances
   * BEFORE the request, which is exactly right for its one job — deciding
   * whether this version has already been asked for, so the effect fires once
   * per distinct version and never loops.
   *
   * It is NOT a statement about what is drawn, and it was being used as one.
   * `reloadSilent` keeps the old data and raises `refreshFailed` when the read
   * fails, so on that path the ref said 2.0, the rows were still the ones read
   * at 1.0, and `EvidenceGraphPanel` printed "Built from this record at version
   * 2.0" over them — the same false statement the re-read was added to remove,
   * surviving on the failure path. The `LiveSyncNote` below is a real
   * mitigation and is not a correction: it sits beside the sentence.
   *
   * `loadedRunsVersion` is the version the rows on screen were actually READ
   * at. It advances only when a new payload lands — `useFetch` replaces
   * `data` with a fresh object on success and leaves it untouched on failure,
   * so a change of identity IS the success signal, and no change to the shared
   * hook is needed to observe it. While a re-read is in flight it correctly
   * still reads the old version, which is what the graph is still drawing.
   */
  const requestedRunsVersion = useRef(detail.version);
  const [loadedRunsVersion, setLoadedRunsVersion] = useState(detail.version);
  const reloadRunsSilent = runs.reloadSilent;
  useEffect(() => {
    if (requestedRunsVersion.current === detail.version) return;
    requestedRunsVersion.current = detail.version;
    reloadRunsSilent();
  }, [detail.version, reloadRunsSilent]);

  const runsPayload = runs.status === 'data' ? runs.data : undefined;
  useEffect(() => {
    if (runsPayload === undefined) return;
    setLoadedRunsVersion(requestedRunsVersion.current);
  }, [runsPayload]);

  // ONE note for both fetches on this branch. A failed refresh of EITHER the
  // bundle (detail/evidence/classification) or the runs means the graph is not
  // the freshly-read state the header claims, and the reader gets the same
  // sentence and the same recourse either way. Refresh reloads both, blanking
  // deliberately — it is an explicit action, and `onManualRefresh` is the
  // screen's own blanking `bundle.reload`.
  //
  // Rendered BARE, not inside `.main-inset`. That wrapper is specified to hold
  // only the two transient notices as a DIRECT child of main, and
  // `evidence-hierarchy.test.tsx` pins both facts; this branch is inside a
  // tabpanel under main's padded preset, whose 28px gutter already aligns the
  // note with the view tabs and the graph panel. A second inset would indent it.
  //
  // (Do not name that preset with its literal attribute here. The same test
  // counts `mainPad=` attribute occurrences in this file's SOURCE against the
  // number of shells, and its regex does not skip comments — a comment quoting
  // the attribute makes the counts disagree.)
  const syncNote = (
    <LiveSyncNote
      degraded={degraded}
      refreshFailed={refreshFailed || runs.refreshFailed}
      onRefresh={() => {
        onManualRefresh();
        runs.reload();
      }}
    />
  );

  if (runs.status === 'loading') {
    return <LoadingPanel label="Loading this experiment's runs from the ISAAC API…" />;
  }
  if (runs.status !== 'data') {
    return <BackendDown error={runs.error} onRetry={runs.reload} />;
  }

  return (
    <>
      {syncNote}
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
        runsVersion={loadedRunsVersion}
        readInScope={readInScope.current}
        currentScope={currentScope}
        focusRunId={focusRunId}
        onFocusRun={onFocusRun}
        onRequestRunCheck={(runId) => api.checkRun(id, runId)}
        conflicts={conflicts}
        notes={notes}
        provenance={provenance}
        assets={assets}
        revisions={revisions}
      />
    </>
  );
}

import './screens.css';
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { compose } from '../lib/assistantComposer';
import { useFetch } from '../lib/useFetch';
import { useRecordSession } from '../lib/useRecordSession';
import { ROUTES } from '../lib/routes';
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

  if (bundle.status !== 'data') {
    return (
      <AppShell
        variant="record"
        topBar={<TopBar variant="record" title={LABELS.screenEvidence} recordId={id} />}
        mainPad="pad"
      >
        <h1 className="sr-only">{LABELS.screenEvidence}</h1>
        {bundle.status === 'loading' ? (
          <LoadingPanel label="Loading the evidence trail from the local backend…" />
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
}: {
  id: string;
  data: EvidenceBundle;
  degraded: boolean;
  agentContext: AgentContext | undefined;
  agentDegraded: boolean;
  onManualRefresh: () => void;
}) {
  const { detail, evidence, artifacts, graph, sourcePreviews, classification } = data;
  const navigate = useNavigate();

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

  const exported = artifacts.sidecar !== null;
  const directTotal = entries.filter((e) => !e.namespaced).length;

  const sidecar = artifacts.sidecar;
  const meta = sidecar
    ? {
        schema_version: String(sidecar.schema_version ?? '1.05'),
        generated_utc: String(sidecar.generated_utc ?? ''),
      }
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
          filename={
            exported && detail.record_id
              ? `${detail.record_id}.evidence.json`
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
      {/* One shared horizontal inset for BOTH transient notices, so the degraded
          live-sync note lines up with the banner and the panels below instead of
          running edge-to-edge. Each child renders null when it has nothing to
          say; the wrapper carries no vertical margin, so an empty wrapper adds
          no space and `.evclass` still starts exactly one gutter below the bar. */}
      <div className="main-inset">
        <LiveSyncNote degraded={degraded} onRefresh={onManualRefresh} />
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
        onOpenRecord={() => navigate(ROUTES.complete(id))}
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

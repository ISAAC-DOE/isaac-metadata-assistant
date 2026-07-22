import './screens.css';
import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { EvidenceTrailPanel } from '../components/EvidenceTrailPanel';
import { EvidenceClassificationPanel } from '../components/EvidenceClassificationPanel';
import { SourcePreview } from '../components/SourcePreview';
import { AssistantPanel } from '../components/AssistantPanel';
import { GraphStatusChip } from '../components/GraphStatusChip';
import { StatusBar } from '../components/StatusBar';
import { LiveSyncNote } from '../components/LiveSyncNote';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { compose } from '../lib/assistantComposer';
import { useFetch } from '../lib/useFetch';
import { useRecordSession } from '../lib/useRecordSession';
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
    <aside className="record-right narrow" aria-label="Assistant">
      <AssistantPanel
        {...compose({ context: 'evidence', bundle: data, selectedPath: selected.key })}
        experimentId={detail.id}
        recordRev={detail.rev}
        availability={graph.availability}
        agentContext={agentContext}
        degraded={agentDegraded}
      />
    </aside>
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
      mainPad="none"
    >
      <LiveSyncNote degraded={degraded} onRefresh={onManualRefresh} />
      <EvidenceClassificationPanel
        classification={classification}
        stale={classificationStale}
        onRefresh={onManualRefresh}
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

import './screens.css';
import '../components/artifact.css';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { WorkflowSpine } from '../components/WorkflowSpine';
import { StatusBar } from '../components/StatusBar';
import { VerdictCard } from '../components/VerdictCard';
import { CoverageBadge } from '../components/CoverageBadge';
import { AdvisoryChip } from '../components/AdvisoryChip';
import { ArtifactCard } from '../components/ArtifactCard';
import { AssistantPanel } from '../components/AssistantPanel';
import { AssistantDrawer } from '../components/AssistantDrawer';
import { LiveSyncNote } from '../components/LiveSyncNote';
import { WorkflowProgressBanner } from '../components/WorkflowProgressBanner';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Shield, TriangleAlert, Lock, Play } from '../components/icons';
import { ROUTES } from '../lib/routes';
import { LABELS } from '../lib/labels';
import { ROUTE_TO_CLI_NOTE } from '../lib/assistant';
import { compose } from '../lib/assistantComposer';
import { api, ApiError } from '../lib/api';
import { useRecordSession } from '../lib/useRecordSession';
import { useWorkspaceScopeChanged } from '../lib/workspaceScope';
import { toAdvisoryResult, toAuditResult, toValidationResult } from '../lib/adapt';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import type {
  ApiExportResponse,
  ExportReadinessBundle,
  ValidationResult,
} from '../lib/types';

type Load =
  | { name: 'loading' }
  | { name: 'error'; error: ApiError }
  | { name: 'data'; data: ExportReadinessBundle };

interface ExportedArtifacts {
  record: Record<string, unknown>;
  sidecar: Record<string, unknown>;
  // P30.6 — safe basenames only (e.g. "<id>.json"), never an absolute
  // server/mount path. Used to label the artifact cards and name downloads.
  recordFilename: string;
  sidecarFilename: string;
  validation: ValidationResult;
}

type ExportPhase =
  | { name: 'idle' }
  | { name: 'exporting' }
  | { name: 'done'; artifacts: ExportedArtifacts }
  | { name: 'conflict'; message: string }
  | { name: 'stale'; message: string }
  | { name: 'failed'; errors: { path: string; message: string }[] }
  | { name: 'error'; error: ApiError };

const SCHEMA = 'ISAAC v1.05';

/**
 * S6 · Ready to Export — the trust readout, live. Three signals from three
 * endpoints render in three distinct components (VerdictCard / CoverageBadge /
 * AdvisoryChip), never merged. The reserved PASS/FAIL verdict is shown ONLY for a
 * real (post-export) validation — a pre-export dry-run reads as a neutral
 * readiness note, never the reserved chip. Export is doubly gated (validation ok
 * AND 0 pending), produces LOCAL artifacts only, and refuses to overwrite an
 * existing record (409 → immutability message).
 */
export function ExportReadiness() {
  const { id = '' } = useParams();
  const [load, setLoad] = useState<Load>({ name: 'loading' });

  // R1b — did the last NON-blanking fetch fail? This screen does not use
  // `useFetch`; it has its own `runFetch(showLoading)`, and the `showLoading:
  // false` branch used to discard the error entirely. That is what made
  // `Re-Validate` on the PASS card able to do nothing at all: on a backend
  // outage the card stayed exactly as it was, and the reader believed they had
  // just re-validated a passing record. The verdict is the surface that gates
  // export, so a trust control failing silently there is the worst instance of
  // the pattern.
  const [refreshFailed, setRefreshFailed] = useState(false);

  const runFetch = useCallback(
    (showLoading: boolean) => {
      if (showLoading) {
        setLoad({ name: 'loading' });
        setRefreshFailed(false);
      }
      api
        .getExportReadiness(id)
        .then((data) => {
          setLoad({ name: 'data', data });
          setRefreshFailed(false);
        })
        .catch((e: unknown) => {
          const error =
            e instanceof ApiError ? e : new ApiError(e instanceof Error ? e.message : String(e));
          // A blanking fetch owns the whole screen and shows BackendDown. A
          // non-blanking one keeps the data on screen — deliberately, so a
          // post-export refresh never blanks the artifacts just written — and
          // raises the honest note instead of swallowing the failure.
          if (showLoading) setLoad({ name: 'error', error });
          else setRefreshFailed(true);
        });
    },
    [id],
  );

  useEffect(() => {
    runFetch(true);
  }, [runFetch]);

  // D1 — the verdict, coverage and advisory on this screen belong to the workspace
  // scope it was opened in. See `lib/workspaceScope.ts`: a scope change destroys
  // the record they were computed for, and a trust readout about a record that no
  // longer exists is the worst instance of showing destroyed content as current.
  const scopeChanged = useWorkspaceScopeChanged();
  if (scopeChanged) return <Navigate to={ROUTES.experiments} replace />;

  if (load.name !== 'data') {
    return (
      <AppShell
        variant="record"
        topBar={<TopBar variant="record" title={LABELS.screenExport} recordId={id} />}
        sidebar={<WorkflowSpine workflow={null} recordId={id} />}
        mainPad="pad"
      >
        <h1 className="sr-only">{LABELS.screenExport}</h1>
        {load.name === 'loading' ? (
          <LoadingPanel label="Loading validation, coverage and advisory from the ISAAC API…" />
        ) : (
          <BackendDown error={load.error} onRetry={() => runFetch(true)} />
        )}
      </AppShell>
    );
  }

  return (
    <LoadedExport
      id={id}
      data={load.data}
      onRefresh={() => runFetch(false)}
      refreshFailed={refreshFailed}
    />
  );
}

function LoadedExport({
  id,
  data,
  onRefresh,
  refreshFailed,
}: {
  id: string;
  data: ExportReadinessBundle;
  onRefresh: () => void;
  refreshFailed: boolean;
}) {
  const navigate = useNavigate();
  const { detail, pending, validate, audit, warnings, graph, artifacts } = data;
  const [phase, setPhase] = useState<ExportPhase>({ name: 'idle' });
  const [viewing, setViewing] = useState<null | 'record' | 'sidecar'>(null);
  // P27.5 — the optimistic-concurrency token, sent as If-Match on export. Adopted
  // from a successful export and re-synced whenever a silent refetch swaps in a
  // fresh detail (LoadedExport is not remounted on refresh, so this effect keeps
  // the held token in step with the reloaded record — e.g. after a stale refresh).
  const [currentVersion, setCurrentVersion] = useState(detail.version);
  useEffect(() => {
    setCurrentVersion(detail.version);
  }, [detail.version]);

  // P29.4 — the ONE shared record-session owner. No text input on this surface,
  // so a change signal can safely trigger a SILENT refetch (updates the readiness
  // signals without blanking); the owner also invalidates any stale staged
  // proposal. Export stays ETag-guarded, so a stale export still gets a 412 as
  // the hard backstop. The poller tracks the held If-Match token (`currentVersion`,
  // which advances on export before the refetch remounts), so we hand the owner a
  // detail carrying it.
  const session = useRecordSession(id, {
    detail: { ...detail, version: currentVersion },
    onChange: () => onRefresh(),
  });
  const degraded = session.syncDegraded;

  // --- artifact "View JSON" modal: a real, focus-trapping dialog --------------
  const modalRef = useRef<HTMLDivElement>(null);
  const modalTriggerRef = useRef<HTMLElement | null>(null); // element to restore focus to
  const wasViewing = useRef(false);
  const modalTitleId = useId();

  // Capture the opener so focus can return to it on close (standard dialog
  // pattern — the trigger is focused when it's activated). Prefer the element
  // the ArtifactCard "View" button passes via e.currentTarget: a mouse click
  // doesn't reliably focus the button first on macOS Safari/Firefox, so
  // document.activeElement alone can land the restore on <body>. Fall back to
  // document.activeElement for any non-click activation path.
  const openViewer = (kind: 'record' | 'sidecar', trigger?: HTMLElement | null) => {
    modalTriggerRef.current = trigger ?? (document.activeElement as HTMLElement | null);
    setViewing(kind);
  };
  const closeViewer = () => setViewing(null);

  // Escape closes; Tab / Shift+Tab wrap inside the dialog (hand-rolled focus
  // containment — this is a true modal, not the lighter Help popover). Capture
  // phase so the dialog handles the keys before any ancestor.
  useEffect(() => {
    if (!viewing) return;
    const modal = modalRef.current;
    if (!modal) return;

    const focusable = () =>
      Array.from(
        modal.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])',
        ),
      );

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        closeViewer();
        return;
      }
      if (e.key !== 'Tab') return;
      const items = focusable();
      if (items.length === 0) {
        e.preventDefault();
        modal!.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || active === modal || !modal!.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [viewing]);

  // Move focus into the dialog on open; return it to the trigger on close.
  useEffect(() => {
    if (viewing) {
      modalRef.current?.focus();
    } else if (wasViewing.current) {
      modalTriggerRef.current?.focus();
    }
    wasViewing.current = !!viewing;
  }, [viewing]);

  const pendingCount = pending.length;
  const pendingZero = pendingCount === 0;
  // Pre-export: `validate` is a DRY-RUN (validate.dry_run true). Its `ok` tells us
  // whether export WILL pass — a gate input, never rendered as the reserved verdict.
  const dryRunOk = validate.dry_run && validate.ok;
  const exported = phase.name === 'done' || detail.exported;
  const canExport = pendingZero && validate.ok && !exported;

  const doExport = () => {
    setPhase({ name: 'exporting' });
    api
      .exportRecord(id, currentVersion)
      .then((resp: ApiExportResponse) => {
        if (resp.ok && resp.record && resp.sidecar) {
          setCurrentVersion(resp.version); // adopt the post-export token
          setPhase({
            name: 'done',
            artifacts: {
              record: resp.record,
              sidecar: resp.sidecar,
              recordFilename: resp.artifact_refs?.record_filename ?? '',
              sidecarFilename: resp.artifact_refs?.sidecar_filename ?? '',
              validation: {
                verdict: resp.official_report?.ok ? 'pass' : 'fail',
                ok: !!resp.official_report?.ok,
                schemaVersion: SCHEMA,
                errors: resp.official_report?.errors ?? [],
              },
            },
          });
          onRefresh(); // refresh coverage/advisory to post-export truth
        } else {
          setPhase({ name: 'failed', errors: resp.errors ?? [] });
        }
      })
      .catch((e: ApiError) => {
        if (e.status === 412) {
          // P27.5 stale write: a concurrent edit changed the record. Nothing was
          // exported. We do NOT auto-refetch — the banner's Refresh reloads the
          // current state (and adopts the fresh version) on the user's click.
          setPhase({
            name: 'stale',
            message:
              'This record changed elsewhere. Nothing was exported — no record was written. Refresh to load the current state, then export again.',
          });
        } else if (e.status === 409) {
          setPhase({
            name: 'conflict',
            message:
              'This record already exists on disk. Official records are immutable — they are written once and never overwritten. No changes were made.',
          });
          onRefresh();
        } else {
          setPhase({ name: 'error', error: e });
        }
      });
  };

  // --- the three signals, each from its own endpoint (never merged) -----------
  const inSession = phase.name === 'done' ? phase.artifacts : null;
  // On a FRESH load of an already-exported record, the content comes from the
  // read-only /artifacts endpoint so View/Download work without re-exporting.
  const freshArtifacts =
    !inSession && detail.exported && artifacts.record && artifacts.sidecar
      ? {
          record: artifacts.record,
          sidecar: artifacts.sidecar,
          recordFilename: artifacts.record_filename ?? '',
          sidecarFilename: artifacts.sidecar_filename ?? '',
        }
      : null;
  // The artifacts to View/Download: this session's export, else the fetched files.
  const viewArtifacts = inSession
    ? {
        record: inSession.record,
        sidecar: inSession.sidecar,
        recordFilename: inSession.recordFilename,
        sidecarFilename: inSession.sidecarFilename,
      }
    : freshArtifacts;
  const realValidation: ValidationResult | null = inSession
    ? inSession.validation
    : detail.exported && !validate.dry_run
      ? toValidationResult(validate)
      : null;
  const coverage = audit.records.length > 0 ? toAuditResult(audit) : 'pending';
  const advisory = toAdvisoryResult(warnings);

  // P30.6 — safe basenames only (never a server path). The API returns null
  // until exported; the fallback below is a locally-constructed filename, not
  // a server-provided path.
  const recordFilename =
    inSession?.recordFilename ||
    detail.artifact_refs.record_filename ||
    `${detail.record_id}.json`;
  const sidecarFilename =
    inSession?.sidecarFilename ||
    detail.artifact_refs.sidecar_filename ||
    `${detail.record_id}.evidence.json`;
  // Never invent a coverage total: while audit data hasn't arrived yet, the
  // sidecar card simply omits the path-count badge (ArtifactCard renders
  // nothing when pathCount is undefined) rather than guessing a number.
  const coverageTotal = coverage === 'pending' ? undefined : coverage.total;

  const download = (content: unknown, filename: string) => {
    const name = filename || 'artifact.json';
    const blob = new Blob([JSON.stringify(content, null, 2) + '\n'], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const rightPanel = (
    <AssistantDrawer railClassName="record-right narrow">
      <AssistantPanel
        {...compose({ context: 'export', bundle: data })}
        experimentId={detail.id}
        recordRev={detail.rev}
        availability={graph.availability}
        note={ROUTE_TO_CLI_NOTE}
        agentContext={session.context}
        degraded={session.degraded}
      />
    </AssistantDrawer>
  );

  return (
    <AppShell
      variant="record"
      topBar={
        <TopBar
          variant="record"
          title={detail.title}
          filename={exported ? recordFilename : `draft · ${detail.id}`}
          stateChip={exported ? 'exported' : undefined}
          recordId={id}
          surface={LABELS.screenExport}
        />
      }
      sidebar={<WorkflowSpine workflow={detail.workflow} recordId={id} />}
      rightPanel={rightPanel}
      statusBar={
        <StatusBar
          validation={realValidation ?? 'pending'}
          coverage={coverage}
          advisory={advisory}
          validationPendingNote={
            realValidation
              ? undefined
              : `dry-run · ${validate.ok ? 'would validate' : `${validate.errors.length} error${validate.errors.length === 1 ? '' : 's'}`}`
          }
          coveragePendingNote="runs after export"
        />
      }
      /* No `width` mode on purpose. Export Readiness is the complex workbench
         (verdict + coverage/advisory grid + artifact cards) and its content
         sits DIRECTLY in <main> with no measure wrapper, so it is already
         uncapped — `width="full"` would change nothing it renders today.
         It is not merely redundant but a trap: `full` publishes
         `--content-max: none`, which every descendant inherits, so a future
         card with its own cap (`.rec-val`, `.schema-browser`, `.settings-card`
         all consume the token) would silently render uncapped here. Opting out
         is the honest state for a screen with nothing to opt in. */
      mainPad="pad"
    >
      <h1 className="sr-only">{LABELS.screenExport}</h1>
      <LiveSyncNote degraded={degraded} refreshFailed={refreshFailed} onRefresh={onRefresh} />
      <WorkflowProgressBanner
        workflow={detail.workflow}
        recordId={id}
        pendingCount={pendingCount}
      />

      {/* P28.2 — the exported record changed after export (records are immutable):
          surface an honest, non-gating advisory so a stale artifact is never
          presented as current. Icon + text (not color-only), announced politely. */}
      {detail.artifact.state === 'stale' && (
        <div className="artifact-stale-note" role="status">
          <TriangleAlert size={16} strokeWidth={2} aria-hidden="true" />
          <span>
            <strong>Exported artifact is out of date.</strong>{' '}
            {detail.artifact.reason ??
              'The record changed after export; the exported artifact no longer reflects the current record.'}
          </span>
        </div>
      )}

      {/* Post-export: the real, reserved verdict + the two export artifacts. */}
      {exported && realValidation && (
        <>
          <VerdictCard
            result={realValidation}
            onRevalidate={() => onRefresh()}
            onBackToComplete={() => navigate(ROUTES.complete(id))}
          />

          {realValidation.verdict === 'pass' && (
            <>
              <div className="signal-row">
                {coverage !== 'pending' ? (
                  <CoverageBadge audit={coverage} advisory={advisory} />
                ) : (
                  <div className="coverage-loading card">Coverage loading…</div>
                )}
                {/* Was "A clean local run": on the hosted deployment the run
                    happens on the server, not the reader's machine. The claim
                    that matters is "here, not upstream" — which is what it now
                    says. */}
                <AdvisoryChip
                  advisory={advisory}
                  explain="A clean run here is not portal sign-off — the upstream validator isn't vendored here."
                />
              </div>

              <div className="ready-heading">
                <span className="dot dot-ready" aria-hidden="true" />
                <span className="ready-label">{LABELS.groupReady}</span>
                <span className="ready-note">
                  — doubly gated: no-guessing checks passed, then official schema.
                </span>
              </div>

              <div className="artifact-row">
                <ArtifactCard
                  artifact={{ kind: 'record', path: recordFilename, verdict: 'pass' }}
                  onView={viewArtifacts ? (e) => openViewer('record', e.currentTarget) : undefined}
                  onDownload={
                    viewArtifacts ? () => download(viewArtifacts.record, recordFilename) : undefined
                  }
                />
                <ArtifactCard
                  artifact={{ kind: 'sidecar', path: sidecarFilename, pathCount: coverageTotal }}
                  onView={viewArtifacts ? (e) => openViewer('sidecar', e.currentTarget) : undefined}
                  onDownload={
                    viewArtifacts ? () => download(viewArtifacts.sidecar, sidecarFilename) : undefined
                  }
                />
              </div>

              <div className="sidecar-note" role="note">
                <Shield
                  size={16}
                  strokeWidth={2}
                  aria-hidden="true"
                  style={{ flex: 'none', color: 'var(--text-slate)' }}
                />
                <span>
                  <strong>Review the sidecar before sharing.</strong> It is an assistant
                  convention — not an official ISAAC standard — and can carry source paths, URIs and
                  hashes. Records are written once, immutable via the CLI: no hand-edit, no
                  overwrite, no portal submission from here.
                </span>
              </div>

              {!inSession && viewArtifacts && (
                <p className="artifact-hint">
                  Loaded from the immutable record + sidecar on disk (read-only) — View and
                  Download show the exact written content.
                </p>
              )}
              {!viewArtifacts && (
                <p className="artifact-hint">
                  The artifact content could not be read from the workspace — open the files at the
                  paths above.
                </p>
              )}
            </>
          )}
        </>
      )}

      {/* Pre-export: readiness / gate. Never the reserved verdict — a dry-run. */}
      {!exported && (
        <>
          {!pendingZero && (
            <section
              className="preexport-gate"
              role="note"
              data-tutorial-anchor={TUTORIAL_ANCHORS.exportGate}
            >
              <Lock size={18} strokeWidth={2} aria-hidden="true" className="preexport-icon" />
              <div>
                <div className="preexport-title">
                  {pendingCount} field{pendingCount === 1 ? '' : 's'} still block export
                </div>
                <p className="preexport-text">
                  Export unlocks only when every field the system refused to guess is confirmed.
                  This is expected — not a failure.
                </p>
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ marginTop: 12 }}
                  data-tutorial-anchor={TUTORIAL_ANCHORS.exportRepair}
                  onClick={() => navigate(ROUTES.complete(id))}
                >
                  {LABELS.actionBackToComplete} →
                </button>
              </div>
            </section>
          )}

          {pendingZero && dryRunOk && (
            <section className="preexport-ready" role="status">
              <div className="preexport-ready-head">
                <span className="dot dot-ready" aria-hidden="true" />
                <span className="preexport-ready-title">{LABELS.groupReady}</span>
                <span className="preexport-ready-note">dry-run · would validate</span>
              </div>
              <p className="preexport-text">
                All blockers are resolved and the in-memory dry-run would pass the official ISAAC
                schema. Exporting runs the real, gated validation and writes the official record +
                evidence sidecar. There is no override and no portal submission.
              </p>
              <button
                type="button"
                className="btn btn-primary"
                data-tutorial-anchor={TUTORIAL_ANCHORS.exportAction}
                onClick={doExport}
                disabled={!canExport || phase.name === 'exporting'}
              >
                <Play size={14} strokeWidth={2.2} aria-hidden="true" />
                {phase.name === 'exporting' ? 'Exporting…' : 'Export Official Record + Sidecar'}
              </button>
            </section>
          )}

          {pendingZero && !dryRunOk && (
            <section className="preexport-blocked card">
              <h2>Would Not Validate Yet</h2>
              <p className="preexport-text">
                The in-memory dry-run does not pass the official ISAAC schema, so export stays gated.
                Nothing was written. Resolve these in the draft, then return.
              </p>
              <ul className="preexport-errors mono">
                {validate.errors.map((e, i) => (
                  <li key={`${e.path}-${i}`}>
                    <span className="preexport-error-path">{e.path}</span> — {e.message}
                  </li>
                ))}
              </ul>
              <button
                type="button"
                className="btn btn-secondary"
                data-tutorial-anchor={TUTORIAL_ANCHORS.exportRepair}
                onClick={() => navigate(ROUTES.complete(id))}
              >
                {LABELS.actionBackToComplete} →
              </button>
            </section>
          )}

          <div className="signal-row" style={{ marginTop: 16 }}>
            <div className="preexport-coverage card" role="note">
              <div className="preexport-coverage-title">{LABELS.evidenceAudit}</div>
              <p className="preexport-text">
                Evidence coverage is counted from the written record — it runs after export.
              </p>
            </div>
            <AdvisoryChip
              advisory={advisory}
              explain="Advisory is non-gating — it never changes the verdict or blocks export."
            />
          </div>
        </>
      )}

      {phase.name === 'conflict' && (
        <div className="export-conflict" role="alert">
          <Lock size={16} strokeWidth={2} aria-hidden="true" />
          <span>{phase.message}</span>
        </div>
      )}

      {phase.name === 'stale' && (
        <div className="export-conflict" role="alert">
          <TriangleAlert size={16} strokeWidth={2} aria-hidden="true" />
          <span>{phase.message}</span>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ marginLeft: 10 }}
            onClick={() => {
              onRefresh();
              setPhase({ name: 'idle' });
            }}
          >
            Refresh
          </button>
        </div>
      )}

      {phase.name === 'failed' && (
        <div className="export-conflict" role="alert">
          <TriangleAlert size={16} strokeWidth={2} aria-hidden="true" />
          <span>
            Export was refused by the gated validation — nothing was written.{' '}
            {phase.errors.length} schema error{phase.errors.length === 1 ? '' : 's'}.
          </span>
        </div>
      )}

      {phase.name === 'error' && (
        <div style={{ marginTop: 12 }}>
          <BackendDown error={phase.error} onRetry={doExport} />
        </div>
      )}

      {viewing && viewArtifacts && (
        <div className="artifact-modal-backdrop" onClick={closeViewer}>
          <div
            ref={modalRef}
            className="artifact-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby={modalTitleId}
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="artifact-modal-head">
              <span id={modalTitleId} className="artifact-modal-title">
                {viewing === 'record' ? LABELS.officialRecord : LABELS.evidenceTrail}
                {viewing === 'sidecar' && (
                  <span className="artifact-modal-sub"> · {LABELS.sidecarNotOfficial}</span>
                )}
              </span>
              <button type="button" className="btn btn-secondary" onClick={closeViewer}>
                Close
              </button>
            </div>
            <pre className="artifact-modal-body mono">
              {JSON.stringify(
                viewing === 'record' ? viewArtifacts.record : viewArtifacts.sidecar,
                null,
                2,
              )}
            </pre>
          </div>
        </div>
      )}
    </AppShell>
  );
}

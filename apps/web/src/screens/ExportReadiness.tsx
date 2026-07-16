import './screens.css';
import '../components/artifact.css';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { WorkflowSpine, buildSpine } from '../components/WorkflowSpine';
import { StatusBar } from '../components/StatusBar';
import { VerdictCard } from '../components/VerdictCard';
import { CoverageBadge } from '../components/CoverageBadge';
import { AdvisoryChip } from '../components/AdvisoryChip';
import { ArtifactCard } from '../components/ArtifactCard';
import { AssistantPanel } from '../components/AssistantPanel';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Shield, TriangleAlert, Lock, Play } from '../components/icons';
import { ROUTES } from '../lib/routes';
import { LABELS } from '../lib/labels';
import { ASSISTANT_SAMPLES, ROUTE_TO_CLI_NOTE } from '../lib/assistant';
import { api, ApiError } from '../lib/api';
import { toAdvisoryResult, toAuditResult, toValidationResult } from '../lib/adapt';
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
  recordPath: string;
  sidecarPath: string;
  validation: ValidationResult;
}

type ExportPhase =
  | { name: 'idle' }
  | { name: 'exporting' }
  | { name: 'done'; artifacts: ExportedArtifacts }
  | { name: 'conflict'; message: string }
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

  const runFetch = useCallback(
    (showLoading: boolean) => {
      if (showLoading) setLoad({ name: 'loading' });
      api
        .getExportReadiness(id)
        .then((data) => setLoad({ name: 'data', data }))
        .catch((e: unknown) => {
          const error =
            e instanceof ApiError ? e : new ApiError(e instanceof Error ? e.message : String(e));
          if (showLoading) setLoad({ name: 'error', error });
        });
    },
    [id],
  );

  useEffect(() => {
    runFetch(true);
  }, [runFetch]);

  if (load.name !== 'data') {
    return (
      <AppShell
        variant="record"
        topBar={<TopBar variant="record" title={LABELS.screenExport} />}
        sidebar={<WorkflowSpine steps={buildSpine('export')} recordId={id} />}
        mainPad="pad"
      >
        {load.name === 'loading' ? (
          <LoadingPanel label="Loading validation, coverage and advisory from the local backend…" />
        ) : (
          <BackendDown error={load.error} onRetry={() => runFetch(true)} />
        )}
      </AppShell>
    );
  }

  return <LoadedExport id={id} data={load.data} onRefresh={() => runFetch(false)} />;
}

function LoadedExport({
  id,
  data,
  onRefresh,
}: {
  id: string;
  data: ExportReadinessBundle;
  onRefresh: () => void;
}) {
  const navigate = useNavigate();
  const { detail, pending, validate, audit, warnings, graph, artifacts } = data;
  const [phase, setPhase] = useState<ExportPhase>({ name: 'idle' });
  const [viewing, setViewing] = useState<null | 'record' | 'sidecar'>(null);

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
      .exportRecord(id)
      .then((resp: ApiExportResponse) => {
        if (resp.ok && resp.record && resp.sidecar) {
          setPhase({
            name: 'done',
            artifacts: {
              record: resp.record,
              sidecar: resp.sidecar,
              recordPath: resp.artifact_refs?.record_path ?? '',
              sidecarPath: resp.artifact_refs?.sidecar_path ?? '',
              validation: {
                verdict: resp.official_report?.ok ? 'pass' : 'fail',
                ok: !!resp.official_report?.ok,
                schemaVersion: SCHEMA,
                exitCode: resp.official_report?.ok ? 0 : 1,
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
        if (e.status === 409) {
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
          recordPath: artifacts.record_path ?? '',
          sidecarPath: artifacts.sidecar_path ?? '',
        }
      : null;
  // The artifacts to View/Download: this session's export, else the fetched files.
  const viewArtifacts = inSession
    ? {
        record: inSession.record,
        sidecar: inSession.sidecar,
        recordPath: inSession.recordPath,
        sidecarPath: inSession.sidecarPath,
      }
    : freshArtifacts;
  const realValidation: ValidationResult | null = inSession
    ? inSession.validation
    : detail.exported && !validate.dry_run
      ? toValidationResult(validate)
      : null;
  const coverage = audit.records.length > 0 ? toAuditResult(audit) : 'pending';
  const advisory = toAdvisoryResult(warnings);

  const recordPath =
    inSession?.recordPath || detail.artifact_refs.record_path || `records/${detail.record_id}.json`;
  const sidecarPath =
    inSession?.sidecarPath ||
    detail.artifact_refs.sidecar_path ||
    `records/${detail.record_id}.evidence.json`;
  // Never invent a coverage total: while audit data hasn't arrived yet, the
  // sidecar card simply omits the path-count badge (ArtifactCard renders
  // nothing when pathCount is undefined) rather than guessing a number.
  const coverageTotal = coverage === 'pending' ? undefined : coverage.total;

  const download = (content: unknown, path: string) => {
    const name = path.split('/').pop() || 'artifact.json';
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

  const spine = buildSpine(exported ? 'validate' : 'export', {
    complete: { meta: `${detail.evidenced_field_count} fields · 0 pending` },
    export: { meta: exported ? 'record written' : pendingZero ? 'ready' : `${pendingCount} to go` },
    validate: { meta: exported ? 'official schema' : 'the hard gate' },
  });

  const rightPanel = (
    <aside className="record-right narrow" aria-label="Assistant">
      <AssistantPanel
        reply={ASSISTANT_SAMPLES.export.reply}
        prompts={ASSISTANT_SAMPLES.export.prompts}
        freshness={graph.status}
        note={ROUTE_TO_CLI_NOTE}
      />
    </aside>
  );

  return (
    <AppShell
      variant="record"
      topBar={
        <TopBar
          variant="record"
          title={detail.title}
          filename={exported ? recordPath.split('/').pop() : `draft · ${detail.id}`}
          stateChip={exported ? 'exported' : undefined}
          recordId={id}
          surface={LABELS.screenExport}
        />
      }
      sidebar={<WorkflowSpine steps={spine} recordId={id} />}
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
      mainPad="pad"
    >
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
                  <CoverageBadge audit={coverage} />
                ) : (
                  <div className="coverage-loading card">Coverage loading…</div>
                )}
                <AdvisoryChip
                  advisory={advisory}
                  explain="A clean local run is not portal sign-off — the upstream validator isn't vendored here."
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
                  artifact={{ kind: 'record', path: recordPath, verdict: 'pass' }}
                  onView={viewArtifacts ? (e) => openViewer('record', e.currentTarget) : undefined}
                  onDownload={
                    viewArtifacts ? () => download(viewArtifacts.record, recordPath) : undefined
                  }
                />
                <ArtifactCard
                  artifact={{ kind: 'sidecar', path: sidecarPath, pathCount: coverageTotal }}
                  onView={viewArtifacts ? (e) => openViewer('sidecar', e.currentTarget) : undefined}
                  onDownload={
                    viewArtifacts ? () => download(viewArtifacts.sidecar, sidecarPath) : undefined
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
            <section className="preexport-gate" role="note">
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
                schema. Exporting runs the real, gated validation and writes the local record +
                evidence sidecar. There is no override and no portal submission.
              </p>
              <button
                type="button"
                className="btn btn-primary"
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
              <h3>Would Not Validate Yet</h3>
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

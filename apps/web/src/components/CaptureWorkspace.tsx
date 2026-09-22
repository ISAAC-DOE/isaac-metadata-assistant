import './capture-workspace.css';
import { useCallback, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { CaptureIntake } from './CaptureIntake';
import { CaptureRecordMap } from './CaptureRecordMap';
import { ClaudeVoicePath } from './ClaudeVoicePath';
import { ArrowLeft } from './icons';
import { railDestination } from './RecordWorkspaceNav';
import { TranscriptCapturePanel, type VoiceState } from './TranscriptCapturePanel';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import { ROUTES, type CaptureView } from '../lib/routes';
import type { ApiCaptureSummary, ApiRunView } from '../lib/types';

/**
 * THE CAPTURE WORKSPACE — Capture Home and its three focused task views (owner QA
 * 2026-09-22, C1–C5).
 *
 *   `?view=capture`                Capture Home: four ways in, one line each.
 *   `?view=capture&method=write`   type or paste → Finalize and Read → result.
 *   `?view=capture&method=voice`   Claude first; the local recorder behind a
 *                                  disclosure.
 *   `?view=capture&method=files`   a bridge to Historical Import and to the
 *                                  record's Asset References.
 *
 * Every focused view is the same split: the ONE task on the left, the live Record
 * Map for the chosen run on the right, stacking into one column when the MAIN
 * column is narrow — a container query on this workspace, not a viewport query,
 * because the assistant rail's expanded state takes ~300px of the same window.
 *
 * ── ONE TRANSCRIPT PANEL, MOUNTED ONCE ──────────────────────────────────────
 *
 * The Write and Voice views are two presentations of ONE `TranscriptCapturePanel`
 * instance, mounted on the first visit to either and never unmounted while the
 * record is open. It sits at a fixed position in this tree and is only HIDDEN on
 * Capture Home and the Files view, so:
 *
 *   - text typed in one view is the same text in the other, and survives a trip
 *     to Capture Home or another workspace (the D1 data-loss rule the record screen
 *     already applies to every workspace);
 *   - a recording keeps running, with every microphone guarantee, while the reader
 *     looks elsewhere — and the record screen keeps it VISIBLE with a notice while
 *     it does (see `onVoiceStateChange`);
 *   - leaving the record still unmounts it, which is what releases the microphone
 *     (`e2e/mutation/capture-microphone.spec.ts`).
 */
export function CaptureWorkspace({
  experimentId,
  experimentTitle,
  captureView,
  captureSummary,
  mapRefreshKey,
  captureRunId,
  onCaptureRunChange,
  onVoiceStateChange,
  onReviewProposals,
  onOpenAssets,
  onCaptured,
}: {
  experimentId: string;
  experimentTitle: string;
  captureView: CaptureView;
  captureSummary: ApiCaptureSummary | null;
  mapRefreshKey: string;
  captureRunId: string;
  onCaptureRunChange: (runId: string) => void;
  onVoiceStateChange: (state: VoiceState) => void;
  onReviewProposals: () => void;
  onOpenAssets: () => void;
  /** A finalize landed: the screen re-reads its record bundle silently. */
  onCaptured: () => void;
}) {
  const location = useLocation();
  const [selectedRun, setSelectedRun] = useState<ApiRunView | null>(null);

  /* Mounted on the first visit to Write or Voice, and kept; see the header. */
  const transcriptMounted = useRef(false);
  const lastMode = useRef<'write' | 'voice'>('write');
  if (captureView === 'write' || captureView === 'voice') {
    transcriptMounted.current = true;
    lastMode.current = captureView;
  }
  const onTask = captureView !== 'home';

  const noop = useCallback(() => {}, []);

  return (
    <>
      {captureView === 'home' && <CaptureIntake captureSummary={captureSummary} />}

      {/* ALWAYS RENDERED, HIDDEN ON HOME, so the transcript panel inside keeps one
          position in the tree whichever view is open. */}
      <div className="capture-task" hidden={!onTask}>
        {onTask && (
          <CaptureTaskHead
            backTo={railDestination(location.search, 'capture')}
            title={
              captureView === 'write'
                ? CAPTURE_COPY.intakeWriteTitle
                : captureView === 'voice'
                  ? CAPTURE_COPY.intakeVoiceTitle
                  : CAPTURE_COPY.intakeFilesTitle
            }
            lead={
              captureView === 'write'
                ? CAPTURE_COPY.writeLead
                : captureView === 'voice'
                  ? CAPTURE_COPY.voiceLead
                  : CAPTURE_COPY.filesLead
            }
          />
        )}
        <div className="capture-split">
          <div className="capture-task-main">
            {captureView === 'voice' && (
              <ClaudeVoicePath
                experimentId={experimentId}
                experimentTitle={experimentTitle}
                runLabel={selectedRun?.label ?? null}
              />
            )}
            {captureView === 'files' && <CaptureFilesBridge onOpenAssets={onOpenAssets} />}
            {transcriptMounted.current && (
              <div className="capture-task-transcript" hidden={captureView !== lastMode.current}>
                <TranscriptCapturePanel
                  experimentId={experimentId}
                  open
                  onOpenChange={noop}
                  mode={lastMode.current}
                  onReviewProposals={onReviewProposals}
                  selectedRunId={captureRunId}
                  onSelectedRunChange={onCaptureRunChange}
                  onVoiceStateChange={onVoiceStateChange}
                  onCaptured={onCaptured}
                />
              </div>
            )}
          </div>
          <div className="capture-task-aside">
            {onTask && (
              <CaptureRecordMap
                experimentId={experimentId}
                runId={captureRunId}
                onRunChange={onCaptureRunChange}
                onRunResolved={setSelectedRun}
                refreshKey={mapRefreshKey}
                picker={captureView !== 'write'}
              />
            )}
          </div>
        </div>
      </div>
    </>
  );
}

/** The focused view's heading: a way back, one short heading, one short line. */
export function CaptureTaskHead({
  backTo,
  title,
  lead,
}: {
  backTo: string;
  title: string;
  lead: ReactNode;
}) {
  return (
    <header className="capture-task-head">
      <Link className="capture-task-back" to={{ search: backTo }}>
        <ArrowLeft size={14} strokeWidth={2.2} aria-hidden="true" />
        {CAPTURE_COPY.backToHome}
      </Link>
      <h2 className="capture-task-title">{title}</h2>
      <p className="capture-task-lead">{lead}</p>
    </header>
  );
}

/**
 * BRING FILES YOU ALREADY HAVE — a bridge, not a second importer.
 *
 * Two real destinations and nothing re-implemented: Historical Import (reads one
 * layout today, keeps anything else as a reference, and every value it finds is a
 * suggestion), and this record's own Asset References (a pointer, a checksum and
 * notes for one file). Neither transmits file bytes from this screen, and the copy
 * claims nothing about file reading beyond what each destination says of itself —
 * `upload-claim-parity.test.tsx` holds every such claim to its scope.
 */
function CaptureFilesBridge({ onOpenAssets }: { onOpenAssets: () => void }) {
  return (
    <div className="capture-files">
      <div className="capture-files-row">
        <p className="capture-files-line">{CAPTURE_COPY.filesImportLine}</p>
        <Link className="btn btn-primary" to={ROUTES.imports}>
          {CAPTURE_COPY.intakeFilesAction}
        </Link>
      </div>
      <div className="capture-files-row">
        <p className="capture-files-line">{CAPTURE_COPY.filesAssetsLine}</p>
        <button type="button" className="btn btn-secondary" onClick={onOpenAssets}>
          {CAPTURE_COPY.filesAssetsAction}
        </button>
      </div>
    </div>
  );
}

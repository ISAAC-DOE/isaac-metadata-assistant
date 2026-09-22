import { useEffect, useId, useState } from 'react';

import { api } from '../lib/api';
import { RUN_LIST_LIMIT_MAX } from '../lib/runPaging';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import type { ApiRunView } from '../lib/types';
import { RunSchemaMirror } from './RunSchemaMirror';

/**
 * THE LIVE RECORD MAP BESIDE A FOCUSED CAPTURE VIEW (owner QA 2026-09-22, C5).
 *
 * `RunSchemaMirror` is reused as-is; this wrapper only answers WHICH run it
 * describes and keeps that run current.
 *
 * ── WHICH RUN: THE ONE THE READER CHOSE, AND NEVER ONE CHOSEN FOR THEM ──────
 *
 * The selection is shared with the transcript form's own run picker (the record
 * screen holds it), and it starts EMPTY. The transcript panel's standing rule is
 * that a run "is never chosen for you, even when the record has exactly one run",
 * and a map that quietly showed the first run would be choosing one — or, worse,
 * reading as the target of a transcript that has none. So with no choice made the
 * pane says so, and offers the same choice here.
 *
 * ── WHY IT DOES NOT SAY "MISSING" FOR A RUN NOBODY PICKED ──────────────────
 *
 * `RunSchemaMirror` given `null` marks every row Missing, which is right beside a
 * run editor that has not loaded yet and false here: nothing is missing from a run
 * the reader has not named. The placeholder states the real situation instead.
 *
 * ── LIVE ────────────────────────────────────────────────────────────────────
 *
 * `refreshKey` moves when the record bundle adopts a new version or a run entry
 * advances on the change feed, and the run is re-read then — so a proposal the
 * reader accepts, or a colleague's run edit, shows here without a reload. The
 * list read is bounded at `RUN_LIST_LIMIT_MAX`; a chosen run beyond it is read by
 * id, so the map never loses a run the picker offered.
 */
export function CaptureRecordMap({
  experimentId,
  runId,
  onRunChange,
  onRunResolved,
  refreshKey,
  picker = true,
}: {
  experimentId: string;
  /** The chosen run id, or `''` for none. */
  runId: string;
  onRunChange: (runId: string) => void;
  /** Reports the run object the map resolved (or `null`), for a caller that needs
   *  its label — the voice view's starter instruction names it. */
  onRunResolved?: (run: ApiRunView | null) => void;
  refreshKey: string;
  /**
   * Whether to offer the run choice here. `false` beside the Write view, whose
   * form already asks "Run These Notes Describe" as its first step — two selects
   * for one choice on one screen would make a reader wonder which one counts.
   */
  picker?: boolean;
}) {
  const selectId = useId();
  const [runs, setRuns] = useState<ApiRunView[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [byId, setById] = useState<ApiRunView | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    api
      .listRuns(experimentId, { limit: RUN_LIST_LIMIT_MAX })
      .then((body) => {
        if (!cancelled) setRuns(body.runs);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [experimentId, refreshKey, attempt]);

  const listed = runs?.find((run) => run.id === runId) ?? null;
  const needsById = runId !== '' && runs !== null && listed === null;
  useEffect(() => {
    if (!needsById) {
      setById(null);
      return;
    }
    let cancelled = false;
    api
      .getRun(experimentId, runId)
      .then((body) => {
        if (!cancelled) setById(body.run);
      })
      .catch(() => {
        if (!cancelled) setById(null);
      });
    return () => {
      cancelled = true;
    };
  }, [experimentId, runId, needsById, refreshKey]);

  const selected = listed ?? byId;
  useEffect(() => {
    onRunResolved?.(selected);
  }, [selected, onRunResolved]);
  const options = runs ?? [];
  const showPicker = picker && runs !== null && runs.length > 0;

  return (
    <div className="capture-map">
      {showPicker && (
        <div className="capture-map-run">
          <label className="capture-label" htmlFor={selectId}>
            {CAPTURE_COPY.mapRunLabel}
          </label>
          <select
            id={selectId}
            className="capture-control"
            value={runId}
            onChange={(event) => onRunChange(event.target.value)}
          >
            <option value="">{CAPTURE_COPY.runPlaceholder}</option>
            {options.map((run) => (
              <option key={run.id} value={run.id}>
                {run.label}
              </option>
            ))}
            {selected !== null && listed === null && (
              <option value={selected.id}>{selected.label}</option>
            )}
          </select>
        </div>
      )}
      {selected !== null ? (
        <RunSchemaMirror run={selected} />
      ) : (
        <MapPlaceholder
          text={
            failed
              ? 'This record’s runs could not be read, so no map is shown.'
              : runs === null
                ? 'Reading this record’s runs…'
                : runs.length === 0
                  ? CAPTURE_COPY.mapNoRuns
                  : CAPTURE_COPY.mapChooseRun
          }
          onRetry={failed ? () => setAttempt((n) => n + 1) : undefined}
        />
      )}
    </div>
  );
}

function MapPlaceholder({ text, onRetry }: { text: string; onRetry?: () => void }) {
  const headingId = useId();
  return (
    <aside className="rsm rsm-placeholder" aria-labelledby={headingId}>
      <h3 className="rsm-heading" id={headingId}>
        Record Map
      </h3>
      <p className="rsm-note">{text}</p>
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Try Again
        </button>
      )}
    </aside>
  );
}

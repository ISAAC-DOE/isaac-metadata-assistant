import './run-artifacts.css';
import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '../lib/api';
import { LABELS } from '../lib/labels';
import type { ApiRunArtifact, ApiRunArtifactsResponse } from '../lib/types';
import { BackendDown, LoadingPanel } from './FetchStates';
import { Download, FileJson, FileText, TriangleAlert } from './icons';

/**
 * EXPORTED RUN RECORDS — every exported run's official record and evidence sidecar,
 * read back from the files the export wrote (QA audit A-02, 2026-10-11).
 *
 * ── THE DEFECT ──────────────────────────────────────────────────────────────
 *
 * A record with runs exports one official record + sidecar PER RUN. This screen could
 * name those files only from the export RESPONSE: it listed filenames with no View and
 * no Download, and after a reload even the names were gone, because no read operation
 * served them (`routes.FAN_OUT_ARTIFACT_REASON` said so in as many words). Every record
 * Historical Import creates has runs, so the import's end-to-end path ended at files the
 * scientist could not retrieve.
 *
 * ── WHAT THIS RENDERS, AND FROM WHERE ───────────────────────────────────────
 *
 * `GET .../run-artifacts`, one bounded page at a time. ~~Every byte shown or downloaded
 * is the file the export WROTE~~ — corrected after review: every VALUE shown or
 * downloaded is the export's written file as the server parsed it — never a re-export,
 * never a reconstruction from the draft — but View and Download re-serialise that JSON
 * (two-space indentation, as the single-record cards always have), so the bytes can
 * differ from the file's in whitespace while the document is the same. A row whose file the server could not read is offered
 * no View/Download for that half and says so; a row whose run changed after export says
 * THAT, in the server's words (`artifact.reason`), because an exported file is fixed
 * and never rewritten (A-06). No control here regenerates anything; none exists.
 *
 * It renders NOTHING when no run has been exported — a record that has not exported is
 * described by the gate above it, and an empty "Exported Run Records" section would be
 * a heading about files that do not exist.
 */

/** Runs per page. The server's own default window is the same size; stated here so a
 *  "Show More Runs" page asks for exactly what the first page did. */
export const RUN_ARTIFACTS_PAGE = 10;

type Kind = 'record' | 'sidecar';

type State =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; page: ApiRunArtifactsResponse; rows: ApiRunArtifact[] };

function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

export function RunArtifactsPanel({
  experimentId,
  reloadKey,
  onView,
  onDownload,
}: {
  experimentId: string;
  /** Changes when the screen knows the set may have moved (an export just finished,
   *  a silent refresh landed), so the list is re-read rather than trusted. */
  reloadKey: string;
  onView: (kind: Kind, content: unknown, runLabel: string, trigger: HTMLElement) => void;
  onDownload: (content: unknown, filename: string) => void;
}) {
  const [state, setState] = useState<State>({ status: 'loading' });
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<ApiError | null>(null);

  const load = useCallback(() => {
    setState((prev) => (prev.status === 'data' ? prev : { status: 'loading' }));
    setMoreError(null);
    api
      .getRunArtifacts(experimentId, { limit: RUN_ARTIFACTS_PAGE })
      .then((page) => setState({ status: 'data', page, rows: page.artifacts }))
      .catch((err: unknown) => setState({ status: 'error', error: asApiError(err) }));
  }, [experimentId]);

  useEffect(() => {
    load();
  }, [load, reloadKey]);

  const loadMore = () => {
    if (state.status !== 'data') return;
    setLoadingMore(true);
    setMoreError(null);
    api
      .getRunArtifacts(experimentId, { limit: RUN_ARTIFACTS_PAGE, offset: state.rows.length })
      .then((next) =>
        setState((prev) => {
          if (prev.status !== 'data') return prev;
          // DEDUPED ON THE RUN ID: offset paging is not snapshot-consistent (the run
          // list's own note), so a run exported between two pages can shift the window.
          const held = new Set(prev.rows.map((r) => r.run_id));
          return {
            status: 'data',
            page: next,
            rows: [...prev.rows, ...next.artifacts.filter((r) => !held.has(r.run_id))],
          };
        }),
      )
      .catch((err: unknown) => setMoreError(asApiError(err)))
      .finally(() => setLoadingMore(false));
  };

  if (state.status === 'loading') {
    return <LoadingPanel label="Loading the exported run records from the ISAAC API…" />;
  }
  if (state.status === 'error') {
    return (
      <section className="run-artifacts" aria-labelledby="run-artifacts-heading">
        <h2 className="run-artifacts-title" id="run-artifacts-heading">
          {LABELS.exportedRunRecordsHeading}
        </h2>
        <BackendDown error={state.error} onRetry={load} />
      </section>
    );
  }

  const { page, rows } = state;
  if (page.total === 0) return null;
  const changed = rows.filter((r) => r.artifact.state === 'stale').length;

  return (
    <section className="run-artifacts" aria-labelledby="run-artifacts-heading">
      <div className="run-artifacts-head">
        <h2 className="run-artifacts-title" id="run-artifacts-heading">
          {LABELS.exportedRunRecordsHeading}
        </h2>
        <span className="run-artifacts-count">
          {page.total} of {page.runs_total} run{page.runs_total === 1 ? '' : 's'} exported
        </span>
      </div>
      <p className="run-artifacts-lead">
        Each run exported its own official ISAAC record and evidence sidecar. These are the
        files the export wrote — they are fixed, and are never rewritten.
        {changed > 0 &&
          ` ${changed} of the runs shown ${changed === 1 ? 'has' : 'have'} changed since export, and ${changed === 1 ? 'its file does' : 'their files do'} not include those changes.`}
      </p>
      <ul className="run-artifacts-list">
        {rows.map((row) => (
          <RunArtifactRow key={row.run_id} row={row} onView={onView} onDownload={onDownload} />
        ))}
      </ul>
      {rows.length < page.total && (
        <div className="run-artifacts-more">
          <span className="run-artifacts-more-note">
            Showing {rows.length} of {page.total} exported runs.
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={loadMore}
            disabled={loadingMore}
          >
            {loadingMore ? 'Loading…' : 'Show More Runs'}
          </button>
        </div>
      )}
      {moreError && <BackendDown error={moreError} onRetry={loadMore} />}
    </section>
  );
}

function RunArtifactRow({
  row,
  onView,
  onDownload,
}: {
  row: ApiRunArtifact;
  onView: (kind: Kind, content: unknown, runLabel: string, trigger: HTMLElement) => void;
  onDownload: (content: unknown, filename: string) => void;
}) {
  const stale = row.artifact.state === 'stale';
  const half = (kind: Kind) => {
    const content = kind === 'record' ? row.record : row.sidecar;
    const filename = (kind === 'record' ? row.record_filename : row.sidecar_filename) ?? '';
    const name = kind === 'record' ? LABELS.officialRecord : LABELS.evidenceTrail;
    // THE RUN IS IN THE ACCESSIBLE NAME. Ten rows each carrying "Download" and "View"
    // would be ten indistinguishable controls to a screen reader's control list.
    const lower = kind === 'record' ? 'official record' : 'evidence sidecar';
    const Icon = kind === 'record' ? FileText : FileJson;
    return (
      <div className="run-artifact-half" data-kind={kind}>
        <span className="run-artifact-half-label">
          <Icon size={14} strokeWidth={2} aria-hidden="true" />
          {name}
        </span>
        <span className="run-artifact-file mono">{filename}</span>
        {content === null ? (
          <span className="run-artifact-unreadable">This file could not be read.</span>
        ) : (
          <span className="run-artifact-actions">
            <button
              type="button"
              className="btn btn-secondary"
              aria-label={`${LABELS.actionDownload} ${lower} for ${row.run_label}`}
              onClick={() => onDownload(content, filename)}
            >
              <Download size={13} strokeWidth={2} aria-hidden="true" />
              {LABELS.actionDownload}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              aria-label={`${LABELS.actionView} ${lower} for ${row.run_label}`}
              onClick={(e) => onView(kind, content, row.run_label, e.currentTarget)}
            >
              {LABELS.actionView}
            </button>
          </span>
        )}
      </div>
    );
  };
  return (
    <li className="run-artifact" data-state={row.artifact.state}>
      <div className="run-artifact-head">
        <span className="run-artifact-label">{row.run_label}</span>
        {stale && (
          <span className="run-artifact-changed">
            <TriangleAlert size={13} strokeWidth={2} aria-hidden="true" />
            {LABELS.chipChangedSinceExport}
          </span>
        )}
      </div>
      {stale && row.artifact.reason && (
        <p className="run-artifact-reason">{row.artifact.reason}</p>
      )}
      {half('record')}
      {half('sidecar')}
    </li>
  );
}

import './csv-reconcile.css';
import { useRef, useState } from 'react';
import { StatusChip } from './StatusChip';
import { LoadingPanel, BackendDown } from './FetchStates';
import { Upload } from './icons';
import { api, ApiError } from '../lib/api';
import { RECONCILE_STATE_CHIP, EVIDENCE_CLASS_CHIP } from '../lib/status';
import type { ApiCsvPreview, ApiCsvReconcileItem } from '../lib/types';

/**
 * P31.3 · CSV Reconciliation (RECONCILIATION-ONLY).
 *
 * A REVIEW surface, never a write surface (human decision 2026-07-22). Uploading a
 * synthetic campaign-sheet CSV previews each mapped value reconciled against the
 * CURRENT record — matches / conflicts / absent — as EVIDENCE. It NEVER mutates
 * the record. Because CSV FIELD_MAP produces only official dotted paths and the
 * only confirmable fields are series/descriptor/edge/asset, NO reconciliation item
 * is ever editable through the app: every item is read-only evidence. This panel
 * therefore renders NO stage / confirm / apply / import / overwrite control.
 */

type Phase = 'idle' | 'loading' | 'done' | 'error';

interface CsvReconcilePanelProps {
  experimentId: string;
  version: string;
  onOpenRecord?: () => void;
}

/**
 * Read a (small) CSV file to text. Prefers the modern `Blob.text()`; falls back
 * to `FileReader` where `text()` is unavailable (e.g. some jsdom builds). Bounded
 * — the campaign sheet is small, so no streaming is needed.
 */
function readFileText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text();
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error ?? new Error('The file could not be read.'));
    reader.readAsText(file);
  });
}

/** Render a proposed/current value safely (never a raw object dump of secrets). */
function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

/**
 * A SAFE, typed message for a non-OK ingress response — never a server path or
 * stack. A trusted, path-free `body.message` is preferred; otherwise a per-status
 * sentence. `unreachable` is handled separately (the BackendDown state).
 */
function safeErrorMessage(err: ApiError): string {
  const bodyMsg = (err.body as { message?: unknown } | undefined)?.message;
  if (
    typeof bodyMsg === 'string' &&
    bodyMsg.trim().length > 0 &&
    !/[/\\]|Traceback|isaac-workspace/.test(bodyMsg)
  ) {
    return bodyMsg;
  }
  switch (err.status) {
    case 428:
      return 'This preview needs the current record version. Reload the record, then upload the CSV again.';
    case 412:
      return 'The record moved on before this preview could run. Re-upload the CSV to reconcile against the current record.';
    case 413:
      return 'That file is too large to preview. Upload a smaller campaign sheet.';
    case 422:
      return 'The CSV could not be processed. Check that column names are not duplicated and that the file is a valid campaign sheet.';
    case 403:
      return 'Uploading this file is not permitted here.';
    default:
      return 'The CSV could not be processed. Please check the file and try again.';
  }
}

export function CsvReconcilePanel({
  experimentId,
  version,
  onOpenRecord,
}: CsvReconcilePanelProps): JSX.Element {
  const [phase, setPhase] = useState<Phase>('idle');
  const [preview, setPreview] = useState<ApiCsvPreview | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  // The record version at the moment of a successful preview — used to detect a
  // record that changed underneath the shown reconciliation.
  const [previewVersion, setPreviewVersion] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const stale = phase === 'done' && previewVersion !== null && previewVersion !== version;

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const input = e.currentTarget;
    const file = input.files?.[0];
    // Reset immediately so re-selecting the SAME file fires a fresh change, and a
    // subsequent empty change event never re-uploads. `file` still holds the ref.
    input.value = '';
    if (!file) return;

    setPhase('loading');
    setError(null);
    try {
      const text = await readFileText(file);
      const result = await api.previewCsv(experimentId, text, {
        version,
        filename: file.name,
      });
      setPreview(result);
      setPreviewVersion(version);
      setPhase('done');
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError('The CSV could not be processed.'));
      setPhase('error');
    }
  }

  function discard() {
    setPreview(null);
    setPreviewVersion(null);
    setError(null);
    setPhase('idle');
  }

  const showUploadPrompt = phase === 'idle' || phase === 'error';

  return (
    <section className="csv-recon" aria-label="CSV reconciliation">
      <header className="csv-recon-head">
        <h2 className="csv-recon-title">Reconcile a Campaign Sheet</h2>
        <p className="csv-recon-sub">
          Compare a campaign sheet against the current record — a read-only review,
          not an edit.
        </p>
      </header>

      <div className="csv-recon-banners">
        <p className="csv-recon-banner csv-recon-banner-strong">
          CSV values are review evidence — uploading this file does not change the
          official record.
        </p>
        <p className="csv-recon-banner csv-recon-banner-warn">
          Synthetic or public data only — do not upload real or private data.
        </p>
        <p className="csv-recon-banner">
          CSV only — the ISAAC campaign metadata sheet (.csv).
        </p>
      </div>

      {/* The file input is ALWAYS mounted so a re-selection (even the same file)
          fires a change, and the double-activate guard has an element to target. */}
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="csv-recon-visually-hidden"
        aria-label="Upload a campaign metadata sheet (CSV)"
        onChange={onFileChange}
      />

      {phase === 'loading' && (
        <LoadingPanel label="Reconciling the campaign sheet against the current record…" />
      )}

      {phase === 'error' && error && (
        error.unreachable ? (
          <BackendDown error={error} />
        ) : (
          <div className="csv-recon-error" role="alert">
            <p className="csv-recon-error-text">{safeErrorMessage(error)}</p>
          </div>
        )
      )}

      {showUploadPrompt && (
        <div className="csv-recon-drop">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => inputRef.current?.click()}
          >
            <Upload size={14} strokeWidth={2.2} aria-hidden="true" />
            Upload CSV File
          </button>
          <span className="csv-recon-drop-hint">
            The file is read locally and sent once for reconciliation; it is never
            written to the record.
          </span>
        </div>
      )}

      {phase === 'done' && preview && (
        <ReconResults
          preview={preview}
          stale={stale}
          onDiscard={discard}
          onOpenRecord={onOpenRecord}
        />
      )}
    </section>
  );
}

function ReconResults({
  preview,
  stale,
  onDiscard,
  onOpenRecord,
}: {
  preview: ApiCsvPreview;
  stale: boolean;
  onDiscard: () => void;
  onOpenRecord?: () => void;
}) {
  const s = preview.reconciliation_summary;
  return (
    <div className="csv-recon-results">
      {stale && (
        <div className="csv-recon-stale" role="status">
          <span className="csv-recon-stale-text">
            Out of date — the record changed after this preview. Re-upload the CSV
            to reconcile against the current record.
          </span>
        </div>
      )}

      <p className="csv-recon-summary">
        Reconciled {preview.candidate_count} mapped field(s) against the current
        record — {s.matches_current} in record, {s.conflicts_with_current} differ,{' '}
        {s.absent_from_record} not recorded.
      </p>
      <p className="csv-recon-note">
        Review only — no field here is editable in the app; each is evidence, not a
        write.
      </p>

      {preview.unknown_header_warnings.length > 0 && (
        <ul className="csv-recon-warnings" aria-label="Ignored columns">
          {preview.unknown_header_warnings.map((w) => (
            <li key={w.header} className="csv-recon-warning">
              {w.message}
            </li>
          ))}
        </ul>
      )}

      <ul className="csv-recon-list">
        {preview.candidates.map((item) => (
          <ReconRow key={`${item.field}-${item.locator}`} item={item} />
        ))}
      </ul>

      <div className="csv-recon-actions">
        <button type="button" className="btn btn-secondary" onClick={onDiscard}>
          Discard Preview
        </button>
        {onOpenRecord && (
          <button type="button" className="btn btn-secondary" onClick={onOpenRecord}>
            Open Record
          </button>
        )}
      </div>
    </div>
  );
}

function ReconRow({ item }: { item: ApiCsvReconcileItem }) {
  const hasCurrent = item.current_value !== null && item.current_value !== undefined;
  return (
    <li className="csv-recon-row">
      <div className="csv-recon-row-head">
        <span className="csv-recon-row-label">{item.field_label}</span>
        <StatusChip kind={RECONCILE_STATE_CHIP[item.reconciliation_state]} />
      </div>
      <div className="csv-recon-row-body">
        <span className="csv-recon-field mono">{item.field}</span>
        <dl className="csv-recon-values">
          <div className="csv-recon-value">
            <dt>Proposed (CSV)</dt>
            <dd className="mono">{formatValue(item.proposed_value)}</dd>
          </div>
          {hasCurrent && (
            <div className="csv-recon-value">
              <dt>Current (record)</dt>
              <dd className="mono">{formatValue(item.current_value)}</dd>
            </div>
          )}
        </dl>
        <div className="csv-recon-meta">
          <StatusChip kind={EVIDENCE_CLASS_CHIP[item.evidence_classification]} />
          <span className="csv-recon-locator">
            {item.locator} · {item.column}
          </span>
          <span className="csv-recon-source">{item.source_name}</span>
        </div>
        <p className="csv-recon-row-note">Read-only evidence — not written to the record.</p>
      </div>
    </li>
  );
}

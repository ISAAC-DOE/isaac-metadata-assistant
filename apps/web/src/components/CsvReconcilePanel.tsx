import './csv-reconcile.css';
import { useRef, useState } from 'react';
import { StatusChip } from './StatusChip';
import { LoadingPanel, BackendDown } from './FetchStates';
import { Upload } from './icons';
import { api, ApiError } from '../lib/api';
import { LABELS } from '../lib/labels';
import { mutationFailureCopy } from '../lib/mutationErrors';
import { RECONCILE_STATE_CHIP, EVIDENCE_CLASS_CHIP } from '../lib/status';
import type { ApiCsvPreview, ApiCsvReconcileItem, ApiCsvWarning } from '../lib/types';

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
  /**
   * R1b — renamed from `onOpenRecord`. Its ONE call site
   * (`screens/EvidenceExplorer.tsx`) navigates to `ROUTES.complete`, i.e. Complete
   * Missing Fields — not the record. The old name agreed with the old (wrong)
   * button label rather than with the destination, which is how the mismatch
   * survived: reading the component alone, label and callback were consistent.
   */
  onGoToComplete?: () => void;
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
 * A SAFE display string for a top-level ingress warning: the string `message`,
 * plus the numeric `count` in parentheses when it is a finite number > 0 (so the
 * count is surfaced honestly, never silently dropped). Reads ONLY `message` and
 * `count` — never the raw object — so an unexpected wire shape can never render
 * `[object Object]` or leak an extra field.
 */
function warningText(w: ApiCsvWarning): string {
  const message = typeof w.message === 'string' ? w.message : '';
  const { count } = w;
  return typeof count === 'number' && Number.isFinite(count) && count > 0
    ? `${message} (${count})`
    : message;
}

/**
 * The last-resort ingress sentence. Named because two branches return it and
 * because it is the one that must NOT be reached by a session failure: it points
 * the reader at their own file.
 */
const GENERIC_INGRESS_FAILURE =
  'The CSV could not be processed. Please check the file and try again.';

/**
 * A SAFE, typed message for a non-OK ingress response — never a server path or
 * stack. A trusted, path-free `body.message` is preferred; otherwise a per-status
 * sentence. `unreachable` is handled separately (the BackendDown state).
 *
 * The trusted-body branch IS reachable on the CSV path: api.ts `mutationError`
 * attaches `.body` only for 400/412. The 412 (`stale_write`) body has no `message`,
 * but several 400 `CsvIngestError` bodies carry a curated, path-free `message`
 * (empty body / NUL byte / invalid UTF-8 / no rows / malformed If-Match). There is
 * no `case 400` in the switch, so without this branch every one of those would fall
 * to the generic default sentence — it stays (pinned by the FE-1 tests). The guard
 * still rejects any body.message containing a path / Traceback / workspace mount.
 *
 * A SESSION THAT ENDED IS ANSWERED FIRST, AND IT IS THE REASON THIS BRANCH WAS
 * ADDED. The `default:` sentence below reads "check the file and try again", so
 * an expired session — where the answer came from the identity provider and the
 * CSV was never read by ISAAC at all — blamed the scientist's file for a response
 * that had nothing to do with it, and sent them to fix a file that was fine. The
 * signal is established in `lib/api.ts::interceptedByEdge` and cannot be produced
 * by any ordinary ingress failure; see `mutationFailureCopy`.
 *
 * 403 IS DELIBERATELY LEFT TO ITS OWN CASE HERE, unlike at the other write sites
 * that pass 403 to `mutationFailureCopy`. On THIS path a 403 has a documented,
 * non-auth meaning — `routes.py::post_csv_preview` answers 403
 * `runtime_mode_denied` when the deployment is not synthetic-only, and it says
 * "Nothing was read" — so claiming a signed-out session would be a guess where a
 * true sentence already exists. ISAAC's own authentication middleware
 * (`apps/api/isaac_api/auth.py:54`) answers 401 and only 401, and an edge answers
 * with the intercept above, so neither of the two real session-expiry signals is
 * lost by leaving 403 alone.
 */
function safeErrorMessage(err: ApiError): string {
  if (err.htmlIntercept || err.status === 401) {
    return mutationFailureCopy(err, GENERIC_INGRESS_FAILURE);
  }
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
      return GENERIC_INGRESS_FAILURE;
  }
}

export function CsvReconcilePanel({
  experimentId,
  version,
  onGoToComplete,
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
        {/* R1b — was "Synthetic or public data only — do not upload real or
            private data." The first clause named a runtime mode the reader has no
            way to check and the product never defines for them; the instruction is
            the part that carries the governance boundary, and it is what the app
            can honestly ask for. Nothing here inspects the file to judge whether
            it is real (there is no such detection anywhere in the codebase), so
            this is a request, not a check. */}
        <p className="csv-recon-banner csv-recon-banner-warn">
          Do not upload real or private data — nothing here checks the file to tell the difference.
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
        tabIndex={-1}
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
          onGoToComplete={onGoToComplete}
        />
      )}
    </section>
  );
}

function ReconResults({
  preview,
  stale,
  onDiscard,
  onGoToComplete,
}: {
  preview: ApiCsvPreview;
  stale: boolean;
  onDiscard: () => void;
  onGoToComplete?: () => void;
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

      {/* Top-level ingress warnings (e.g. skipped unrecognized field-rows) — a
          SEPARATE list from the unknown-header warnings above. Only the safe
          message + numeric count are rendered (never the raw object). */}
      {preview.warnings.length > 0 && (
        <ul className="csv-recon-warnings" aria-label="Processing warnings">
          {preview.warnings.map((w, i) => (
            <li key={`${w.code}-${i}`} className="csv-recon-warning">
              {warningText(w)}
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
        {/* R1b — the label read "Open Record" while the click navigated to
            Complete Missing Fields. Taken from LABELS so a rename of the screen
            carries the button with it, instead of the two drifting again. */}
        {onGoToComplete && (
          <button type="button" className="btn btn-secondary" onClick={onGoToComplete}>
            {LABELS.screenComplete} →
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

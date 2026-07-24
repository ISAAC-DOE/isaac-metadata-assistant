import './record-validator.css';
import { useRef, useState } from 'react';
import { VerdictCard } from './VerdictCard';
import { LoadingPanel, BackendDown } from './FetchStates';
import { Upload, FileJson, TriangleAlert } from './icons';
import { api, ApiError } from '../lib/api';
import type { ApiValidateRecordResult, ValidationResult } from '../lib/types';

/**
 * P36.3 — the standalone Governance & Safety validator.
 *
 * Paste or upload a candidate JSON record; it is checked, server-side, against
 * the official ISAAC schema via the SAME authoritative `validate_official` that
 * backs `isaac validate --official` and the record-level validate route — this
 * component computes NO pass/fail itself and reuses `VerdictCard` (the same
 * hard-gate rendering used elsewhere) rather than a second verdict presentation.
 *
 * Read-only and local: nothing here is uploaded to a model or persisted — the
 * candidate JSON is validated in memory and discarded (see routes.py docstring).
 */

const MAX_BYTES = 512 * 1024; // mirrors the server's bound; enforced client-side FIRST

type Phase = 'idle' | 'validating' | 'result' | 'rejected' | 'backend_down';

/** Read a (small) JSON file to text — same fallback as CsvReconcilePanel's
 * `readFileText`, duplicated locally since that helper is component-private. */
function readFileText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text();
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error ?? new Error('The file could not be read.'));
    reader.readAsText(file);
  });
}

function byteLength(s: string): number {
  return new TextEncoder().encode(s).length;
}

function toValidationResult(v: ApiValidateRecordResult): ValidationResult {
  return {
    verdict: v.ok ? 'pass' : 'fail',
    ok: v.ok,
    schemaVersion: v.schema_version,
    exitCode: v.ok ? 0 : 1,
    errors: v.errors,
  };
}

export function RecordValidator() {
  const [text, setText] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [outcome, setOutcome] = useState<ApiValidateRecordResult | null>(null);
  const [rejection, setRejection] = useState<string | null>(null);
  const [backendError, setBackendError] = useState<ApiError | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function resetOutcome() {
    setOutcome(null);
    setRejection(null);
    setBackendError(null);
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const input = e.currentTarget;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    resetOutcome();
    setPhase('idle');
    if (file.size > MAX_BYTES) {
      setRejection('That file is too large to validate here (over 512 KB). Upload a smaller record.');
      setPhase('rejected');
      return;
    }
    try {
      const content = await readFileText(file);
      setText(content);
    } catch {
      setRejection('That file could not be read.');
      setPhase('rejected');
    }
  }

  async function onValidateClick() {
    resetOutcome();
    const trimmed = text.trim();
    if (trimmed.length === 0) {
      setRejection('Paste or upload a JSON record first.');
      setPhase('rejected');
      return;
    }
    if (byteLength(text) > MAX_BYTES) {
      setRejection('That record is too large to validate here (over 512 KB).');
      setPhase('rejected');
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setRejection("That isn't valid JSON — check for a missing bracket, quote, or trailing comma.");
      setPhase('rejected');
      return;
    }
    setPhase('validating');
    try {
      const result = await api.validateRecord(parsed);
      setOutcome(result);
      setPhase('result');
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError('The record could not be validated.');
      if (err.unreachable) {
        setBackendError(err);
        setPhase('backend_down');
      } else {
        setRejection(err.message || 'The record could not be validated.');
        setPhase('rejected');
      }
    }
  }

  return (
    <section className="rec-val card" aria-labelledby="rec-val-heading">
      <header className="rec-val-head">
        <FileJson size={18} strokeWidth={2} aria-hidden="true" className="rec-val-icon" />
        <div>
          <h2 id="rec-val-heading">Standalone Validator</h2>
          <p className="rec-val-sub">
            Paste or upload a candidate ISAAC record — checked against the official
            schema, the same gate <code className="mono">isaac validate --official</code> runs.
          </p>
        </div>
      </header>

      <p className="rec-val-scope-note" id="rec-val-scope-note-id">
        Synthetic/local validator: the record is checked in memory and discarded. Nothing here is
        uploaded to a model, indexed, or stored.
      </p>

      <div className="rec-val-input-row">
        <label className="rec-val-label" htmlFor="rec-val-textarea">
          Candidate record (JSON)
        </label>
        <textarea
          id="rec-val-textarea"
          className="rec-val-textarea mono"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (phase !== 'validating') {
              setPhase('idle');
              resetOutcome();
            }
          }}
          placeholder='{ "isaac_record_version": "1.05", "record_id": "…", … }'
          spellCheck={false}
          rows={12}
          aria-describedby="rec-val-scope-note-id"
        />
        <div className="rec-val-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={14} strokeWidth={2.2} aria-hidden="true" />
            Upload JSON File
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            className="rec-val-visually-hidden"
            aria-label="Upload a candidate ISAAC record (JSON)"
            tabIndex={-1}
            onChange={onFileChange}
          />
          <button
            type="button"
            className="btn btn-primary"
            onClick={onValidateClick}
            disabled={phase === 'validating'}
          >
            Validate
          </button>
        </div>
      </div>

      {/* No outer aria-live wrapper: each state below already carries its own live
          region (LoadingPanel role="status", BackendDown/rejected role="alert",
          VerdictCard role="status") — wrapping again would double-announce. */}
      <div className="rec-val-result">
        {phase === 'validating' && (
          <LoadingPanel label="Validating against the official ISAAC schema…" />
        )}

        {phase === 'backend_down' && <BackendDown error={backendError ?? undefined} />}

        {phase === 'rejected' && rejection && (
          <div className="rec-val-rejected" role="alert">
            <TriangleAlert size={16} strokeWidth={2.2} aria-hidden="true" />
            <p>{rejection}</p>
          </div>
        )}

        {phase === 'result' && outcome && (
          <div className="rec-val-outcome">
            <VerdictCard result={toValidationResult(outcome)} />
            <p className="rec-val-schema-line mono">
              Checked against official ISAAC schema v{outcome.schema_version}
            </p>
            <details className="rec-val-summary-details">
              <summary>Full validator summary</summary>
              <pre className="mono rec-val-summary-pre">{outcome.summary}</pre>
            </details>
          </div>
        )}

        {phase === 'idle' && (
          <p className="rec-val-empty">No record checked yet — paste or upload JSON, then Validate.</p>
        )}
      </div>
    </section>
  );
}

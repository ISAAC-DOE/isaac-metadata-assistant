import './signals.css';
import { Check, TriangleAlert } from './icons';
import { LABELS } from '../lib/labels';
import type { ValidationResult } from '../lib/types';

interface VerdictCardProps {
  result: ValidationResult;
  onRevalidate?: () => void;
  onBackToComplete?: () => void;
}

/**
 * The hard gate — the single most prominent status element, the deterministic
 * PASS/FAIL against official ISAAC schema v1.05. Reserved green/red, used
 * nowhere else. On FAIL, export disappears and a Back to Complete route appears
 * with the exact schema errors. Strength comes from size/saturation, no rail.
 *
 * R1b — WHAT THIS CARD MUST NOT DO. It used to render, in a monospace
 * command-styled block, `isaac validate --official · exit {result.exitCode}`. No
 * CLI is ever invoked: the verdict comes from a route that calls the Python
 * function `isaac_records.official.validate_official` in-process, and `exitCode`
 * was a client-side literal (`ok ? 0 : 1`) in three separate places. Rendering a
 * command line and an exit code that no process produced is a fabricated
 * observation — on the one surface that gates export, which is the worst place
 * for one. It is gone, along with the whole `exitCode` field.
 *
 * The PARITY claim is different and is kept: the `verdict-hint` says this is the
 * same gate that backs export, which is true by construction — the export path
 * and this verdict call the one `validate_official` over the one vendored schema.
 * Pinned by `__tests__/verdict-no-fabricated-cli.test.tsx`.
 */
export function VerdictCard({ result, onRevalidate, onBackToComplete }: VerdictCardProps) {
  const pass = result.verdict === 'pass';
  return (
    <div>
      <section
        className={`verdict ${pass ? 'verdict-pass' : 'verdict-fail'}`}
        role="status"
        aria-label={`Validation ${pass ? 'PASS' : 'FAIL'}`}
      >
        <div className="verdict-tile" aria-hidden="true">
          {pass ? <Check size={28} strokeWidth={2.6} /> : <TriangleAlert size={28} strokeWidth={2.4} />}
        </div>
        <div className="verdict-body">
          <div className="verdict-head">
            <div>
              <div className="verdict-word">{pass ? LABELS.chipPass : LABELS.chipFail}</div>
              <p className="verdict-claim">
                {pass
                  ? 'Valid against official ISAAC schema v1.05.'
                  : `Invalid against official ISAAC schema v1.05 — ${result.errors.length} error${
                      result.errors.length === 1 ? '' : 's'
                    }. Export blocked.`}
              </p>
            </div>
            {pass && onRevalidate && (
              <button type="button" className="btn btn-secondary" onClick={onRevalidate}>
                {LABELS.actionRevalidate}
              </button>
            )}
          </div>
          {pass && <p className="verdict-hint">this is the same gate that backs export.</p>}
        </div>
      </section>

      {!pass && (
        <div className="card schema-errors">
          <h2>Schema Errors</h2>
          {result.errors.map((err) => (
            <div className="schema-error-row" key={err.path}>
              <span className="schema-error-path mono">{err.path}</span> — {err.message}
            </div>
          ))}
          {onBackToComplete && (
            <button
              type="button"
              className="btn btn-primary"
              style={{ marginTop: 14 }}
              onClick={onBackToComplete}
            >
              {LABELS.actionBackToComplete} →
            </button>
          )}
          <p className="verdict-hint">
            Fix the field paths in the draft. Nothing was written — and there is no override.
          </p>
        </div>
      )}
    </div>
  );
}

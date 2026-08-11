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
 *
 * WHICH GATE REFUSED — the second thing this card must not get wrong, and it did.
 * The headline claim used to be a straight `pass ? valid : invalid-against-the-
 * official-schema`, which was safe only while `ok` was the schema's own verdict
 * everywhere. `POST /api/validate/record` now also applies ISAAC's anchored-pattern
 * exactness gate, so a real response reads `ok: false`, `schema_ok: true`,
 * `errors: []`, `exactness_errors: [1]` — and this card rendered, verbatim,
 * "Invalid against official ISAAC schema v1.05 — 0 errors. Export blocked." above
 * an empty error list, contradicting the `schema_ok: true` in the same response.
 * The trigger is a trailing newline on a tag: a copy-paste artefact, not exotic.
 *
 * That is not a cosmetic defect. The schema is upstream-owned (`CLAUDE.md` §1),
 * and `exactness.py` calls the "not a schema rule" wording load-bearing precisely
 * because a surface that blurs the two attributes an ISAAC policy to upstream. So
 * the headline now branches on `schemaOk`, the exactness findings render under
 * their own heading that says what they are, and an empty error list renders no
 * card at all. The distinction `isaac validate --official` prints — schema verdict
 * first and verbatim, ISAAC gate after it under its own heading — is visible here
 * without expanding anything. Pinned by `__tests__/validator-exactness.test.tsx`.
 */
export function VerdictCard({ result, onRevalidate, onBackToComplete }: VerdictCardProps) {
  const pass = result.verdict === 'pass';
  // Absent means "same as `ok`" — the reading that was true before the field
  // existed, and still true of every producer that does not run the ISAAC gate.
  const schemaOk = result.schemaOk ?? result.ok;
  const exactnessErrors = result.exactnessErrors ?? [];

  // Never "invalid against the official schema — 0 errors". Each branch states the
  // gate that actually refused, and the third exists so that a response this client
  // cannot explain says so rather than blaming upstream by default.
  let failClaim: string;
  if (!schemaOk) {
    failClaim = `Invalid against official ISAAC schema v1.05 — ${result.errors.length} error${
      result.errors.length === 1 ? '' : 's'
    }. Export blocked.`;
  } else if (exactnessErrors.length > 0) {
    failClaim =
      `Valid against official ISAAC schema v1.05, and refused by ISAAC — ` +
      `${exactnessErrors.length} anchored-pattern exactness finding${
        exactnessErrors.length === 1 ? '' : 's'
      }. That is an ISAAC gate, not a schema error. Export blocked.`;
  } else {
    failClaim =
      'Refused — and not by the official ISAAC schema, whose verdict on this record is ' +
      'PASS. No reason was supplied with this result.';
  }

  // The action + closing hint appear ONCE, at the bottom of whichever detail card
  // is last. Rendering them per card would offer the same route twice.
  const failFooter = (
    <>
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
    </>
  );

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
                {pass ? 'Valid against official ISAAC schema v1.05.' : failClaim}
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

      {/* NO EMPTY CARD. `result.errors.length > 0`, not `!pass`: an exactness-only
          refusal has no schema errors, and a "Schema Errors" heading over zero rows
          is the surface half of the same false claim the headline used to make. */}
      {!pass && result.errors.length > 0 && (
        <div className="card schema-errors">
          <h2>Schema Errors</h2>
          {/* `err.path` is NOT unique — a record missing several required properties
              produces one error per property, all reported at `$`. React keys must be
              unique among siblings, so the index is part of the key. It is stable here
              because this list is only ever replaced wholesale by a fresh validation
              result, never reordered or spliced in place. Nothing renders wrong today;
              a duplicate key is one refactor away from silently collapsing schema
              errors on the surface that reports the export gate. */}
          {result.errors.map((err, i) => (
            <div className="schema-error-row" key={`${i}:${err.path}`}>
              <span className="schema-error-path mono">{err.path}</span> — {err.message}
            </div>
          ))}
          {exactnessErrors.length === 0 && failFooter}
        </div>
      )}

      {/* ISAAC's OWN gate, under ISAAC's own heading. Deliberately NOT merged into
          "Schema Errors" and deliberately not worded as a schema violation: the
          vendored schema, read as written, ACCEPTS these values. It reuses the
          `.schema-errors` row markup — one vocabulary for "a path and what is wrong
          with it", the same reuse `isaac validate --official` makes of one renderer
          for both verdicts — with a modifier class for anything that needs to look
          different. */}
      {!pass && exactnessErrors.length > 0 && (
        <div className="card schema-errors exactness-errors">
          <h2>Anchored-Pattern Exactness — an ISAAC gate, not a schema rule</h2>
          <p className="verdict-hint exactness-note">
            {schemaOk
              ? 'The official ISAAC schema accepts this record as written. ISAAC refuses it anyway, under a gate of its own, and blocks export. This is not an upstream schema error.'
              : 'ISAAC also refuses these values under a gate of its own. They are listed apart from the schema errors above because the official schema accepts them.'}
          </p>
          {exactnessErrors.map((err, i) => (
            <div className="schema-error-row" key={`${i}:${err.path}`}>
              <span className="schema-error-path mono">{err.path}</span> — {err.message}
            </div>
          ))}
          {failFooter}
        </div>
      )}
    </div>
  );
}

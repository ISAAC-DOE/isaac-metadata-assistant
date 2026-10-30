import './record-validator.css';
import { useRef, useState } from 'react';
import { VerdictCard } from './VerdictCard';
import { Widget } from './Widget';
import { LoadingPanel, BackendDown } from './FetchStates';
import { Upload, FileJson, TriangleAlert } from './icons';
import { api, ApiError } from '../lib/api';
import { mutationFailureCopy } from '../lib/mutationErrors';
import type { ApiValidateRecordResult, ValidationResult } from '../lib/types';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import { ProposeTermLink, useSchemaVocabulary } from './ProposeTermLink';
import { canProposeTerm, categoryKeyOf } from '../lib/schemaProposals';

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
 *
 * P36R S8 — COPY ONLY. The distinct purpose (validate a record WITHOUT adding
 * it to My Experiments) is now stated, and the four things it is actually for
 * are listed in a disclosure so it stays a secondary Governance utility rather
 * than the visual centre of the app. The request path, the 512 KB bound
 * (client-side first, and again server-side), the no-persistence /
 * no-content-logging guarantees, the structured errors, and the synthetic/
 * private-data boundary copy are all UNCHANGED — there is still exactly one
 * validator implementation, and it is the authoritative one.
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

/**
 * The response, mapped WITHOUT losing which gate refused.
 *
 * This used to drop `schema_ok` and `exactness_errors` on the floor — they were
 * absent from `ApiValidateRecordResult`, so TypeScript actively prevented reading
 * them — and the card downstream had only `ok` and an empty `errors` to work with.
 * It said "Invalid against official ISAAC schema v1.05 — 0 errors" about a record
 * the same response reported as `schema_ok: true`. The only statement of the real
 * reason was inside the collapsed "Full validator summary" disclosure below.
 *
 * `?? v.ok` and `?? []` are the compatibility path for a response predating the
 * exactness gate: absent `schema_ok` means `ok` IS the schema verdict, which is
 * what it was.
 */
function toValidationResult(v: ApiValidateRecordResult): ValidationResult {
  return {
    verdict: v.ok ? 'pass' : 'fail',
    ok: v.ok,
    schemaOk: v.schema_ok ?? v.ok,
    schemaVersion: v.schema_version,
    errors: v.errors,
    exactnessErrors: v.exactness_errors ?? [],
  };
}

export function RecordValidator() {
  const [text, setText] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [outcome, setOutcome] = useState<ApiValidateRecordResult | null>(null);
  const [rejection, setRejection] = useState<string | null>(null);
  const [backendError, setBackendError] = useState<ApiError | null>(null);
  /*
   * B-07 — WHICH FILE, IF ANY, THE TEXTAREA'S CONTENT CAME FROM. Three facts were
   * missing and each produced a measured defect: a rejected selection left the
   * previous file loaded (so Validate passed a file the reader had just been told was
   * not accepted), no file name was ever shown (so a verdict could not say what it was
   * about), and a name that outlived an edit would have claimed a file the text no
   * longer is. So it is set when a file's text lands in the box, cleared by ANY edit,
   * and is also the only thing that tells a rejection which content is the file's to
   * clear — text the reader typed is theirs and survives a rejected file.
   */
  const [loadedFile, setLoadedFile] = useState<string | null>(null);
  /** The file a rejection is about (never the previous one) — named in the alert. */
  const [rejectedFile, setRejectedFile] = useState<string | null>(null);
  /** What the CURRENT verdict checked: a file's name, or `null` for pasted/typed text. */
  const [checkedFile, setCheckedFile] = useState<string | null>(null);
  /** The parsed record the CURRENT verdict is about, so an error's own value can be read back. */
  const [checkedRecord, setCheckedRecord] = useState<unknown>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function resetOutcome() {
    setOutcome(null);
    setRejection(null);
    setRejectedFile(null);
    setBackendError(null);
  }

  /** A selection was refused: whatever an EARLIER file put in the box goes, so the
   *  next Validate cannot return a verdict for a file the reader was just told no
   *  about. Text the reader typed or pasted is left exactly as it was. */
  function rejectFile(name: string, message: string) {
    if (loadedFile !== null) {
      setText('');
      setLoadedFile(null);
    }
    setRejection(message);
    setRejectedFile(name);
    setPhase('rejected');
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const input = e.currentTarget;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    resetOutcome();
    setPhase('idle');
    if (file.size > MAX_BYTES) {
      rejectFile(
        file.name,
        'That file is too large to validate here (over 512 KB). Upload a smaller record.',
      );
      return;
    }
    try {
      const content = await readFileText(file);
      setText(content);
      setLoadedFile(file.name);
    } catch {
      rejectFile(file.name, 'That file could not be read.');
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
    // Captured NOW: the verdict describes the text sent, so the name it carries must be
    // the one that text had when it was sent, not whatever the box holds later.
    const sentFrom = loadedFile;
    try {
      const result = await api.validateRecord(parsed);
      setOutcome(result);
      setCheckedFile(sentFrom);
      setCheckedRecord(parsed);
      setPhase('result');
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError('The record could not be validated.');
      if (err.unreachable) {
        setBackendError(err);
        setPhase('backend_down');
      } else {
        // A sign-in page answered in place of the API is not a verdict about the
        // pasted record, so it must not be shown as one.
        setRejection(
          mutationFailureCopy(err, err.message || 'The record could not be validated.'),
        );
        setPhase('rejected');
      }
    }
  }

  return (
    /* ── ONE WIDGET SINCE 2026-10-12 ─────────────────────────────────────────
       The Validator is a Widget like the Settings surfaces it is launched from:
       the title, a one-line description, the state as the headline ("no record
       checked yet" until there is a verdict), the always-visible privacy line,
       the input, and Validate as the page's one primary action. The parity
       statement (`isaac validate --official`) and "When to use this" are
       explanation, not state, so they are behind the info toggle — still in the
       DOM, still read by every guard that reads it.

       The widget section carries the walkthrough's anchor attribute, and the
       heading is a programmatic focus target (`tabIndex={-1}` — never a tab
       stop) so an arrival from elsewhere — the Assistant's Open Validator action,
       or a `?tab=validator` deep link — can land the reader on the Validator's own
       heading. Both were a wrapper `<div>` and a ref callback until the shared
       Widget gained `headingProps` and `data-*` passthrough (2026-10-18). */
      <Widget
        id="rec-val-heading"
        className="rec-val"
        data-tutorial-anchor={TUTORIAL_ANCHORS.standaloneValidator}
        headingProps={{ tabIndex: -1 }}
        title="Standalone Validator"
        icon={<FileJson size={18} strokeWidth={2} />}
        sub="Validate a record without adding it to My Experiments."
        info={
          <>
            <p>
              Paste or upload a candidate ISAAC record — checked against the official schema, the
              same gate <code className="mono">isaac validate --official</code> runs.
            </p>
            <p className="widget-info-heading">When to Use This</p>
            <ul className="rec-val-purpose-list">
              <li>Inspect an external JSON object that is not — and need not become — a record here.</li>
              <li>
                Confirm API and CLI validation parity: this route reuses the same{' '}
                <code className="mono">validate_official</code> gate as{' '}
                <code className="mono">isaac validate --official</code>.
              </li>
              <li>Diagnose structured schema errors by path before fixing a draft.</li>
              <li>Independently verify an artifact you already exported.</li>
            </ul>
            <p className="rec-val-purpose-note">
              To build a record — draft, evidence, guided completion, export — start from My
              Experiments instead. Nothing checked here is created, saved, or changed.
            </p>
          </>
        }
        headline={
          phase === 'idle' ? (
            <span className="widget-state rec-val-empty">No Record Checked Yet</span>
          ) : undefined
        }
      >
      {/* Was "Synthetic/local validator", which asserted the reader's machine on
          a build that also runs hosted; then "Synthetic-mode validator", a claim
          about the BUILD's configured mode.

          R1b drops those two words entirely. They named a runtime configuration
          flag, told the reader nothing about what this control does, and invited
          exactly the misreading the flag does not support — the app cannot tell
          real data from synthetic by looking at it, and nothing here tries to.
          What is left is verified against `routes.py::post_validate_record`: the
          body is "never written anywhere and its content is never logged; only the
          outcome and error count are". It stays VISIBLE: it is a privacy state. */}
      <p className="rec-val-scope-note" id="rec-val-scope-note-id">
        The record is checked in memory and discarded. Nothing here is uploaded to a model, indexed,
        or stored.
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
            // An edit makes the text no longer the file's, so the name is dropped.
            setLoadedFile(null);
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
        <p className="rec-val-hint">Accepts JSON up to 512 KB.</p>
        {loadedFile !== null && (
          <p className="rec-val-file-line">
            Loaded file: <span className="mono rec-val-file-name">{loadedFile}</span>
          </p>
        )}
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
            <div>
              <p>{rejection}</p>
              {rejectedFile !== null && (
                <p className="rec-val-rejected-file">
                  File: <span className="mono rec-val-file-name">{rejectedFile}</span> — nothing
                  from it was loaded.
                </p>
              )}
            </div>
          </div>
        )}

        {phase === 'result' && outcome && (
          <div className="rec-val-outcome">
            <VerdictCard result={toValidationResult(outcome)} />
            <OffListTerms record={checkedRecord} errors={outcome.errors} />
            {/* What the verdict is ABOUT. A verdict that does not say which input it
                describes invites the reader to attach it to whatever they last picked
                (B-07). The file name is shown as TEXT, never as a link or a path. */}
            <p className="rec-val-source-line">
              Checked:{' '}
              {checkedFile !== null ? (
                <>
                  the file <span className="mono rec-val-file-name">{checkedFile}</span>
                </>
              ) : (
                'the pasted or typed text'
              )}
            </p>
            <p className="rec-val-schema-line mono">
              Checked against official ISAAC schema v{outcome.schema_version}
            </p>
            {/*
              R2 — the ADVISORY tier, rendered BELOW the verdict and visibly separate
              from it.

              Why it is here at all: this route used to call schema validation and
              nothing else, so a record with `measurement.series: []` came back as an
              unqualified PASS — schema-valid with zero errors, and no signal anywhere
              that it contained no measured data. The per-record route had always run
              these checks; the standalone validator, the surface an operator actually
              points at a file, was the one place they were invisible.

              Why it is styled as a note and not as an error: advisory means advisory.
              The heading says so, `gating: false` comes from the server, and the
              verdict above is unchanged by anything here. A reader must not come away
              thinking a warning blocked something.
            */}
            {outcome.warnings && outcome.warnings.length > 0 && (
              <section className="rec-val-advisory" aria-labelledby="rec-val-advisory-h">
                <h3 id="rec-val-advisory-h" className="rec-val-advisory-h">
                  Advisory notes ({outcome.warnings.length}) — these do not affect the verdict
                </h3>
                <ul className="rec-val-advisory-list">
                  {outcome.warnings.map((w) => (
                    <li key={`${w.code}:${w.where}`} className="rec-val-advisory-item">
                      <code className="mono rec-val-advisory-where">{w.where}</code>
                      <span className="rec-val-advisory-msg">{w.message}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <details className="rec-val-summary-details">
              <summary>Full validator summary</summary>
              <pre className="mono rec-val-summary-pre">{outcome.summary}</pre>
            </details>
          </div>
        )}

        {phase === 'idle' && <p className="rec-val-idle-hint">Paste or upload JSON, then Validate.</p>}
      </div>
      </Widget>
  );
}

/** The value at a validator error's dotted path (`a.b.0.c`), or `undefined`. */
function valueAt(record: unknown, path: string): unknown {
  let node: unknown = record;
  for (const seg of path.split('.')) {
    if (node === null || typeof node !== 'object') return undefined;
    if (Array.isArray(node)) {
      if (!/^\d+$/.test(seg)) return undefined;
      node = node[Number(seg)];
    } else {
      node = (node as Record<string, unknown>)[seg];
    }
  }
  return node;
}

/**
 * VALUES THIS RECORD HOLDS OUTSIDE A PORTAL TERM LIST, each with a link to propose it.
 *
 * Read from the RECORD, not from the error message: for each schema error, the value at its
 * own path is looked up in the record that was checked, and a link is offered only when that
 * value is a string the portal vocabulary's list for the field does not hold. An error message
 * is never parsed (its wording is the validator's, and a value inside it could be anything).
 * Renders nothing when there is no such value or the vocabulary cannot be read.
 */
function OffListTerms({ record, errors }: { record: unknown; errors: { path: string; message: string }[] }) {
  const candidates: { path: string; category: string; term: string }[] = [];
  const seen = new Set<string>();
  for (const e of errors) {
    const value = valueAt(record, e.path);
    if (typeof value !== 'string' || value.trim() === '') continue;
    const category = categoryKeyOf(e.path);
    const key = `${category}\u0000${value}`;
    if (seen.has(key)) continue;
    seen.add(key);
    candidates.push({ path: e.path, category, term: value });
  }
  const vocabulary = useSchemaVocabulary(candidates.length > 0);
  if (vocabulary === null) return null;
  const offered = candidates.filter((c) => canProposeTerm(vocabulary, c.category, c.term));
  if (offered.length === 0) return null;
  return (
    <div className="rec-val-propose" role="note">
      <p className="rec-val-propose-lead">
        {offered.length === 1 ? 'This value is' : 'These values are'} not in the list for{' '}
        {offered.length === 1 ? 'its field' : 'their fields'} in the ISAAC portal vocabulary snapshot
        {vocabulary.sources.portal.snapshot_commit ? ` ${vocabulary.sources.portal.snapshot_commit}` : ''} (a copy
        taken at one point in time, not the live portal). If the list is missing a term you need, you can draft a
        proposal; nothing is sent.
      </p>
      <ul className="rec-val-propose-list">
        {offered.map((c) => (
          <li key={`${c.category}:${c.term}`}>
            <span className="mono">{c.path}</span>: <span className="mono">{c.term}</span>{' '}
            <ProposeTermLink fieldPath={c.path} term={c.term} from="validator" vocabulary={vocabulary} />
          </li>
        ))}
      </ul>
    </div>
  );
}

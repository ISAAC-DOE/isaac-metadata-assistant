import { useEffect, useId, useState } from 'react';
import { HelpTip } from './HelpTip';
import { api, ApiError } from '../lib/api';
import { IMPORT_STAGE_COPY } from '../lib/historicalImportContent';
import { recordFieldFacts } from '../lib/recordFields';
import { enumOptionLabel } from '../lib/runFields';

const COPY = IMPORT_STAGE_COPY;
const TECHNIQUE = 'system.technique';

/** One thing the import read about how the measurements were made. */
export interface TechniqueEvidence {
  /** The literal a source wrote — a macro's name, a filename token. Never a technique. */
  value: string;
  /** How many places in the import say it. */
  places: number;
}

/**
 * THE RECORD'S TECHNIQUE, CHOSEN BY THE SCIENTIST (2026-10-18, QA `C-10`).
 *
 * The mapping registry has long said the technique "is a scientist's to choose, and the
 * options are named below so that choice is one word" — and no control anywhere on the
 * import screen let anyone make it. This is that control.
 *
 * WHAT IT IS, AND WHAT IT IS NOT:
 *
 *   * a USER CONFIRMATION written through the record's existing answer route
 *     (`POST /experiments/{id}/answers`, or `/edit` to correct a value the record already
 *     holds) — exactly what `RecordDescriptionPanel` sends for the same field, with the
 *     record's own `If-Match`. It is not a proposal and mints none;
 *   * a choice from the vendored schema's OWN list, read from `GET /api/schema` — never a
 *     transcribed copy. When that read fails the picker says so and offers nothing, rather
 *     than a free-text box whose off-list value would block export;
 *   * NEVER PRESELECTED. The four the registry names come first as a short list; nothing
 *     is chosen, and the import's evidence is shown BESIDE the picker as what the files
 *     say — a macro name is not a technique, and nothing here maps one to the other.
 */
export function TechniqueChooser({
  experimentId,
  recordTitle,
  evidence,
  shortList,
}: {
  experimentId: string;
  recordTitle: string | undefined;
  evidence: readonly TechniqueEvidence[];
  /** The registry's `allowed_values` for the acquisition method (served, not transcribed). */
  shortList: readonly string[];
}) {
  const id = useId();
  const [allowed, setAllowed] = useState<string[] | null | 'failed'>(null);
  const [stored, setStored] = useState<string | null | undefined>(undefined);
  const [choice, setChoice] = useState('');
  const [state, setState] = useState<
    { kind: 'idle' } | { kind: 'saving' } | { kind: 'saved'; value: string } | { kind: 'failed'; message: string }
  >({ kind: 'idle' });

  useEffect(() => {
    let live = true;
    api
      .getSchema()
      .then((r) => {
        if (live) {
          const found = recordFieldFacts(r.schema, TECHNIQUE).allowed;
          setAllowed(found ? [...found] : 'failed');
        }
      })
      .catch(() => {
        if (live) setAllowed('failed');
      });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    let live = true;
    setStored(undefined);
    setChoice('');
    setState({ kind: 'idle' });
    if (!experimentId) return;
    api
      .getDraft(experimentId)
      .then((draft) => {
        if (!live) return;
        let value: string | null = null;
        for (const group of draft.groups ?? [])
          for (const field of group.fields ?? [])
            if (field.path === TECHNIQUE && typeof field.value === 'string' && field.value) value = field.value;
        setStored(value);
      })
      .catch(() => {
        if (live) setStored(null);
      });
    return () => {
      live = false;
    };
  }, [experimentId]);

  if (!experimentId) {
    return (
      <section className="hi-technique" aria-labelledby={`${id}-title`}>
        <h4 className="hi-block-title" id={`${id}-title`}>
          {COPY.techniqueTitle}
        </h4>
        <p className="hi-note">{COPY.techniqueNeedsRecord}</p>
      </section>
    );
  }

  const options = Array.isArray(allowed) ? allowed : [];
  const short = shortList.filter((t) => options.includes(t));
  const rest = options.filter((t) => !short.includes(t));

  const save = async () => {
    if (!choice) return;
    setState({ kind: 'saving' });
    try {
      // THE RECORD'S OWN VERSION, read immediately before the write.
      const detail = await api.getExperiment(experimentId);
      const answers = { [TECHNIQUE]: choice };
      if (stored) await api.editField(experimentId, answers, detail.version);
      else await api.submitAnswer(experimentId, answers, detail.version);
      setStored(choice);
      setState({ kind: 'saved', value: choice });
      setChoice('');
    } catch (err) {
      const body = err instanceof ApiError ? (err.body as Record<string, unknown> | undefined) : undefined;
      const message =
        typeof body?.message === 'string' && body.message
          ? body.message
          : 'The technique could not be saved, and the record was not changed.';
      setState({ kind: 'failed', message });
    }
  };

  return (
    <section className="hi-technique" aria-labelledby={`${id}-title`}>
      <div className="hi-stage-sub-head">
        <h4 className="hi-block-title" id={`${id}-title`}>
          {COPY.techniqueTitle}
        </h4>
        <HelpTip subject={COPY.techniqueTitle}>{COPY.techniqueHelp}</HelpTip>
      </div>
      <p className="hi-note">{COPY.techniqueLead}</p>
      <p className="hi-technique-evidence">
        <span className="hi-field-label">{COPY.techniqueEvidence}</span>{' '}
        {evidence.length === 0 ? (
          <span className="hi-sub">{COPY.techniqueNoEvidence}</span>
        ) : (
          evidence.map((e, index) => (
            <span key={e.value}>
              {index > 0 ? ' · ' : ''}
              <code>{e.value}</code>
              {e.places > 1 ? <span className="hi-sub"> ({e.places} places)</span> : null}
            </span>
          ))
        )}
      </p>
      {stored && state.kind !== 'saved' && <p className="hi-sub">{COPY.techniqueCurrent(stored)}</p>}
      {allowed === 'failed' ? (
        <p className="hi-note" role="note">
          {COPY.techniqueUnavailable}
        </p>
      ) : (
        <div className="hi-technique-row">
          <label className="hi-field">
            <span className="hi-field-label">{COPY.techniqueLabel}</span>
            <select
              className="hi-input"
              value={choice}
              disabled={allowed === null}
              onChange={(event) => setChoice(event.target.value)}
            >
              <option value="">{allowed === null ? 'Reading the schema…' : COPY.techniqueChoose}</option>
              {short.length > 0 && (
                <optgroup label={COPY.techniqueShortList}>
                  {short.map((t) => (
                    <option key={t} value={t}>
                      {enumOptionLabel(t)}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label={COPY.techniqueAll}>
                {rest.map((t) => (
                  <option key={t} value={t}>
                    {enumOptionLabel(t)}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={!choice || state.kind === 'saving' || choice === stored}
            onClick={() => void save()}
          >
            {state.kind === 'saving' ? 'Saving…' : COPY.techniqueSave}
          </button>
        </div>
      )}
      <p className="hi-technique-status" role="status" aria-live="polite">
        {state.kind === 'saved'
          ? COPY.techniqueSaved(state.value, recordTitle ?? 'the record')
          : state.kind === 'failed'
            ? state.message
            : ''}
      </p>
    </section>
  );
}

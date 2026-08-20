import { useState } from 'react';
import {
  DESCRIPTOR_KINDS,
  DESCRIPTOR_NAME_SUGGESTIONS,
  DESCRIPTOR_SOURCES,
} from '../lib/types';

/**
 * The two controls that let a scientist supply a value the app will never generate.
 *
 * WHY THIS EXISTS
 * ===============
 * A `series` or `descriptor` blocker renders as a "structured" question, and the only
 * way to answer one was to CONFIRM a worked-example value. A record a scientist
 * created has no example — `demo_answer` is null outside the walkthrough — so the
 * screen said "No example value is available for this field — leave it honestly
 * missing" and offered no control at all. Both questions are REQUIRED for an evidence
 * record (the official schema's `allOf` requires descriptors; a measurement needs its
 * series), so a record made in this application could be taken to that screen and no
 * further.
 *
 * `experiment_repository.blank_draft`'s docstring recorded the general shape of this:
 * "a new experiment cannot yet be completed to the point of export. That is a real
 * limit of the product". This is that limit being lifted for the two blockers that
 * actually stand in the way.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 * ================================
 * It generates nothing, defaults nothing scientific, and pre-selects nothing. Every
 * field is blank until a person fills it, `kind` and `source` are unset selects rather
 * than a helpful first option, and the value is refused rather than coerced when it is
 * empty. The vocabulary list is a `datalist` — a suggestion the schema does not
 * enforce and neither does this.
 *
 * The two controls are shaped differently because the two values are. A descriptor is
 * a handful of named scalars a person genuinely knows and can type. A reduced spectrum
 * is thousands of points that come out of a pipeline; nobody types one, so the honest
 * control is a place to put the reduction product's own JSON, validated against the
 * same shape rule the server applies rather than against a second copy of it.
 */

/** Mirrors `complete.is_series_shaped`: a NON-EMPTY list of objects. */
export function seriesShapeError(parsed: unknown): string | null {
  if (!Array.isArray(parsed)) return 'The value must be a list of series objects.';
  if (parsed.length === 0) {
    // The server refuses `[]` for a stated reason: deleting a confirmed measurement is
    // not a correction. Saying so here means the refusal is explained where it happens.
    return 'An empty list would record no measurement at all.';
  }
  if (!parsed.every((item) => item !== null && typeof item === 'object' && !Array.isArray(item))) {
    return 'Every entry must be a series object.';
  }
  return null;
}

/**
 * A typed value from a text field: a number when the text IS one, otherwise the text.
 *
 * Stated rather than silent, because it is a type decision made on a scientist's
 * behalf. `9001.2` typed for an edge energy has to reach the record as a number — a
 * string there is wrong, and the schema's `value` accepts either — while a
 * `categorical` descriptor's value is legitimately a word. Parsing when it parses is
 * the only rule that serves both, and the form says so on screen.
 */
export function typedValue(text: string): unknown {
  const trimmed = text.trim();
  if (trimmed === '') return null;
  const asNumber = Number(trimmed);
  return Number.isFinite(asNumber) && trimmed !== '' ? asNumber : trimmed;
}

export interface DescriptorDraft {
  name: string;
  kind: string;
  source: string;
  value: string;
  unit: string;
  sigma: string;
  sigmaUnit: string;
  basis: string;
}

export const EMPTY_DESCRIPTOR: DescriptorDraft = {
  name: '',
  kind: '',
  source: '',
  value: '',
  unit: '',
  sigma: '',
  sigmaUnit: '',
  basis: '',
};

/** The four the schema marks required, plus a value that is not blank. */
export function descriptorIsComplete(d: DescriptorDraft): boolean {
  return (
    d.name.trim() !== '' && d.kind !== '' && d.source !== '' && d.value.trim() !== ''
  );
}

/** The `descriptors[]` item this form describes — omitting what was left blank. */
export function descriptorPayload(d: DescriptorDraft): Record<string, unknown> {
  const uncertainty: Record<string, unknown> = {
    // `null` rather than an omitted key when no sigma was given. The schema allows
    // `sigma: null`, and it is the difference between "no uncertainty was reported"
    // and "this descriptor has none" — the first is true, the second would be a claim.
    sigma: d.sigma.trim() === '' ? null : (typedValue(d.sigma) as number),
  };
  if (d.sigmaUnit.trim() !== '') uncertainty.unit = d.sigmaUnit.trim();
  if (d.basis.trim() !== '') uncertainty.basis = d.basis.trim();

  const out: Record<string, unknown> = {
    name: d.name.trim(),
    kind: d.kind,
    source: d.source,
    value: typedValue(d.value),
    uncertainty,
  };
  if (d.unit.trim() !== '') out.unit = d.unit.trim();
  return out;
}

interface DescriptorFormProps {
  value: DescriptorDraft;
  onChange: (next: DescriptorDraft) => void;
  idPrefix: string;
}

export function DescriptorForm({ value, onChange, idPrefix }: DescriptorFormProps) {
  const set = (key: keyof DescriptorDraft) => (next: string) =>
    onChange({ ...value, [key]: next });

  return (
    <div className="structured-entry">
      <p className="structured-entry-lead">
        No example value exists for a record you created, so this asks for the descriptor
        directly. Nothing is filled in for you.
      </p>

      <div className="structured-entry-grid">
        <label className="structured-field" htmlFor={`${idPrefix}-name`}>
          <span className="structured-label">
            Name <abbr title="required">*</abbr>
          </span>
          <input
            id={`${idPrefix}-name`}
            className="input"
            list={`${idPrefix}-names`}
            value={value.name}
            onChange={(e) => set('name')(e.target.value)}
            placeholder="e.g. inflection_point_energy"
          />
          {/* A SUGGESTION LIST, not a constraint. The schema constrains this by pattern
              and the vocabulary file calls itself "an extraction/authoring aid only", so
              a datalist — which accepts anything typed — is the honest control. */}
          <datalist id={`${idPrefix}-names`}>
            {DESCRIPTOR_NAME_SUGGESTIONS.map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>
        </label>

        <label className="structured-field" htmlFor={`${idPrefix}-kind`}>
          <span className="structured-label">
            Kind <abbr title="required">*</abbr>
          </span>
          <select
            id={`${idPrefix}-kind`}
            className="input"
            value={value.kind}
            onChange={(e) => set('kind')(e.target.value)}
          >
            <option value="">— choose —</option>
            {DESCRIPTOR_KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>

        <label className="structured-field" htmlFor={`${idPrefix}-source`}>
          <span className="structured-label">
            Source <abbr title="required">*</abbr>
          </span>
          <select
            id={`${idPrefix}-source`}
            className="input"
            value={value.source}
            onChange={(e) => set('source')(e.target.value)}
          >
            <option value="">— choose —</option>
            {DESCRIPTOR_SOURCES.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>

        <label className="structured-field" htmlFor={`${idPrefix}-value`}>
          <span className="structured-label">
            Value <abbr title="required">*</abbr>
          </span>
          <input
            id={`${idPrefix}-value`}
            className="input"
            value={value.value}
            onChange={(e) => set('value')(e.target.value)}
            placeholder="e.g. 9001.2"
          />
        </label>

        <label className="structured-field" htmlFor={`${idPrefix}-unit`}>
          <span className="structured-label">Unit</span>
          <input
            id={`${idPrefix}-unit`}
            className="input"
            value={value.unit}
            onChange={(e) => set('unit')(e.target.value)}
            placeholder="e.g. eV"
          />
        </label>

        <label className="structured-field" htmlFor={`${idPrefix}-sigma`}>
          <span className="structured-label">Uncertainty (σ)</span>
          <input
            id={`${idPrefix}-sigma`}
            className="input"
            value={value.sigma}
            onChange={(e) => set('sigma')(e.target.value)}
            placeholder="leave blank if not reported"
          />
        </label>

        <label className="structured-field" htmlFor={`${idPrefix}-sigma-unit`}>
          <span className="structured-label">Uncertainty unit</span>
          <input
            id={`${idPrefix}-sigma-unit`}
            className="input"
            value={value.sigmaUnit}
            onChange={(e) => set('sigmaUnit')(e.target.value)}
            placeholder="e.g. eV"
          />
        </label>

        <label className="structured-field" htmlFor={`${idPrefix}-basis`}>
          <span className="structured-label">Uncertainty basis</span>
          <input
            id={`${idPrefix}-basis`}
            className="input"
            value={value.basis}
            onChange={(e) => set('basis')(e.target.value)}
            placeholder="e.g. reported"
          />
        </label>
      </div>

      <p className="structured-entry-note">
        A value that reads as a number is recorded as one; anything else is recorded as
        text. Leaving σ blank records that no uncertainty was reported — not that there
        is none.
      </p>
    </div>
  );
}

interface SeriesEntryProps {
  text: string;
  onChange: (next: string) => void;
  idPrefix: string;
}

export function SeriesEntry({ text, onChange, idPrefix }: SeriesEntryProps) {
  const [touched, setTouched] = useState(false);
  const error = text.trim() === '' ? null : seriesParseError(text);

  return (
    <div className="structured-entry">
      <p className="structured-entry-lead">
        A reduced spectrum comes out of your reduction pipeline — nobody types one. Paste
        the reduction product&rsquo;s <code>measurement.series</code> JSON here. It is
        stored exactly as given.
      </p>
      <label className="structured-field" htmlFor={`${idPrefix}-series`}>
        <span className="structured-label">Series JSON</span>
        <textarea
          id={`${idPrefix}-series`}
          className="input structured-entry-json"
          rows={8}
          spellCheck={false}
          value={text}
          onBlur={() => setTouched(true)}
          onChange={(e) => onChange(e.target.value)}
          placeholder={'[{"series_id": "averaged_spectrum", "independent_variables": [...]}]'}
          aria-describedby={`${idPrefix}-series-status`}
        />
      </label>
      <p
        id={`${idPrefix}-series-status`}
        className={error ? 'structured-entry-error' : 'structured-entry-note'}
        role={error && touched ? 'alert' : undefined}
      >
        {error ??
          'The shape is checked here and again on the server; the values themselves are never inspected or altered.'}
      </p>
    </div>
  );
}

/** Parse + shape check in one, returning the message to show or `null` when usable. */
export function seriesParseError(text: string): string | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    // The parser's own message is not shown: it names character offsets in a blob the
    // reader cannot see line numbers for, and reads as a failure of the app.
    return 'That is not valid JSON.';
  }
  return seriesShapeError(parsed);
}

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

/**
 * A NON-EMPTY list of objects.
 *
 * ~~"Mirrors `complete.is_series_shaped`"~~ — STRUCK, because it claimed parity this
 * function does not have, and an independent review measured the gap. The server's
 * guard has a THIRD clause this one does not: `complete.is_series_shaped` also
 * refuses an item whose `series_id` is present and not hashable, because
 * `[{"series_id": {"a": 1}}]` was admitted once, written, and then raised
 * `TypeError: unhashable type: 'dict'` out of `draft_validator`, leaving the record
 * permanently unreadable (`complete.py:324-336`).
 *
 * So the honest description is that this is STRICTLY WEAKER than the server's rule:
 * `[{"series_id": {"a": 1}}]` arms Confirm here and is refused on submit. That is
 * the safe direction of the two — a client guard that under-refuses ends in the
 * server's refusal, which `GuidedCompletion` already renders honestly ("this field
 * still holds the value it held before, and nothing was written"), whereas one that
 * over-refuses would block a value the record would have accepted and no server
 * response could correct it.
 *
 * The USER-FACING copy was already honest and is unchanged; only the comment
 * claimed a parity that was never implemented. Restating the server's hashability
 * rule here would create the second definition `complete.py:342-345` warns about —
 * "copying IS restating" — for a case the server already handles end to end.
 */
/**
 * The one key this form REQUIRES, and a deliberately narrower gate than the
 * schema's full `required` list.
 *
 * `schema/isaac_record_v1.json` marks THREE keys required on a series item --
 * `series_id`, `independent_variables`, `channels`. This form checks only the
 * first, and the reason is where each is best enforced:
 *
 *  * `series_id` is what the DRAFT validator keys evidence by, and its absence
 *    is the accept-then-refuse defect actually measured
 *    (`docs/evidence/end-to-end-demo-walk-2026-09-15.md`): the answer was taken,
 *    pending fell 3 to 1, and only export said `series has no series_id`.
 *  * The other two are enforced by OFFICIAL validation at export, which already
 *    names each missing key and its allowed values precisely -- measured in the
 *    same walk, on `channels[0].unit` and on three enum values.
 *
 * REQUIRING ALL THREE HERE WAS BUILT AND NARROWED, because the cost told me the
 * gate was at the wrong layer: it turned 13 tests in three files red, none of
 * them about series validation -- prefill, Confirm arming, DOM ids, bounded
 * pending, refused corrections -- each of which would have had to carry full
 * schema detail it does not care about. Every REAL fixture and canonical seed
 * already carries all three (checked across `tests/fixtures/**`), so the strict
 * version blocked no shipped data; it only made incidental scaffolding verbose.
 *
 * Pinned by `src/__tests__/structured-value-schema-parity.test.ts`, which asserts
 * this key really is one the schema requires -- so the gate stays grounded in the
 * authority (`CLAUDE.md` section 1) rather than being this file's opinion.
 */
export const SERIES_REQUIRED_KEYS = ['series_id'] as const;

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

  /*
   * THE OFFICIAL SCHEMA'S OWN REQUIRED KEYS, CHECKED HERE BECAUSE THE RECORD
   * OTHERWISE BECOMES QUIETLY UN-EXPORTABLE.
   *
   * Measured over HTTP on a record created through the product: answering this
   * question with `[{"energy_eV": 8979, "mu": 0.412}]` -- a list of objects,
   * which is all this function used to require -- was ACCEPTED. The pending
   * count fell from 3 to 1 and the question read as answered. Export then
   * refused with `series has no series_id — cannot key its evidence`, twice,
   * once per entry. So a scientist could complete every question and hold a
   * record that cannot leave the building, with the reason surfacing only at
   * the end.
   *
   * `schema/isaac_record_v1.json` declares `required: ["series_id",
   * "independent_variables", "channels"]` on each series item. This form gates
   * on `series_id` alone; see `SERIES_REQUIRED_KEYS` for why the other two are
   * left to official validation at export, and for the measurement that
   * narrowed this from all three.
   *
   * The ASYMMETRY BEHIND IT IS NOT CLOSED and is named rather than implied:
   * `src/isaac_records/complete.py:239-240` skips evidence for a series with no
   * `series_id` (`if series_id is None: continue`) and accepts the answer, while
   * `draft_validator.py:592` makes the same absence an export error. An API
   * caller can still reach that. Closing it belongs in the truth path, which
   * `CLAUDE.md` section 13 puts behind its own slice and its own review; this
   * closes the path a scientist can actually type into.
   */
  const missing = new Map<string, string[]>();
  for (const item of parsed as Record<string, unknown>[]) {
    for (const key of SERIES_REQUIRED_KEYS) {
      if (item[key] === undefined || item[key] === null) {
        missing.set(key, [...(missing.get(key) ?? []), '']);
      }
    }
  }
  if (missing.size > 0) {
    const names = SERIES_REQUIRED_KEYS.filter((k) => missing.has(k));
    return (
      `Every series needs ${names.map((n) => `\`${n}\``).join(', ')} — the official ISAAC ` +
      `schema requires ${names.length === 1 ? 'it' : 'them'}, and a series without ` +
      `${names.length === 1 ? 'it' : 'them'} cannot be exported.`
    );
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

/**
 * The four a PERSON has to type, plus a value that is not blank.
 *
 * ~~"The four the schema marks required"~~ — STRUCK. The behaviour is right and the
 * stated reason was wrong, which is the more dangerous of the two failures because
 * the next reader would have trusted the count. Measured against the vendored
 * schema at `/properties/descriptors/properties/outputs/items/properties/descriptors/items`:
 *
 *     required: ['name', 'kind', 'source', 'value', 'uncertainty']   ← FIVE
 *
 * The fifth, `uncertainty`, is not in this test because nobody has to type it:
 * `descriptorPayload` ALWAYS emits an `uncertainty` object, with `sigma: null` when
 * no σ was given — deliberately, because "no uncertainty was reported" and "this
 * descriptor has none" are different claims and only the first is true of a blank
 * field. So the form can be complete without it and the payload can still satisfy
 * the schema. The count is corrected rather than the check.
 */
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

/**
 * The INVERSE of {@link descriptorPayload} — a confirmed descriptor value back into
 * the form that produced it.
 *
 * WHY IT HAD TO EXIST, and what shipped without it. `GuidedCompletion` renders every
 * confirmed answer read-only with an Edit button, and its own comment says an edit
 * "swaps that row for an inline GuidedPrompt prefilled with the current value". For a
 * `descriptor` or `series` answer on a record with NO worked example — i.e. every
 * record a scientist creates, which is the case this whole module exists for — the
 * value was never passed down at all, so the editor opened BLANK and, because
 * `entryReady` is computed from the form and not from `initialStaged`, Save was
 * disabled with nothing on screen saying why. Measured:
 *
 *     SERIES     editor value = ""                              SAVE DISABLED = true
 *     DESCRIPTOR Name="" Kind="" Source="" Value="" Unit=""     SAVE DISABLED = true
 *
 * Correcting one field of a descriptor therefore meant retyping all of it. The `qc`
 * half of the same defect was fixed by passing `rawValue` through for a verdict; this
 * is the other half.
 *
 * WHY IT IS A FUNCTION AND NOT A CAST — the trap an independent review flagged before
 * anyone fell into it. `GuidedPrompt` used to reach for `initialValue as
 * DescriptorDraft` on `'name' in initialValue`, and TWO different shapes satisfy that
 * test:
 *
 *   * a `DescriptorDraft` — every field a string, `sigma`/`sigmaUnit`/`basis` present.
 *     This is what `onStagedChange` reports mid-edit, so it is what survives a Refresh.
 *   * a `descriptorPayload` — `value` is a NUMBER when it read as one, there is no
 *     `sigma` key at all, and the σ lives inside `uncertainty`.
 *
 * Casting the second to the first puts a number where `descriptorIsComplete` calls
 * `.trim()` and an `undefined` where it reads `d.sigma`, so the editor would THROW on
 * open — a worse failure than the blank form it replaced. Every field is therefore
 * read defensively and stringified, and anything unrecognised degrades to
 * {@link EMPTY_DESCRIPTOR} rather than to a half-populated form: a blank field the
 * reader must fill is honest, a field silently holding the wrong thing is not.
 *
 * NOTHING IS INVENTED HERE. A key the payload does not carry becomes an empty field,
 * which is exactly what it meant — `unit` omitted means no unit was given, and
 * `sigma: null` means no uncertainty was reported. Round-tripping a payload through
 * this and back through `descriptorPayload` restores the same payload, which is the
 * property `structured-value-entry.test.tsx` pins.
 */
export function descriptorDraftFrom(value: unknown): DescriptorDraft {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return EMPTY_DESCRIPTOR;
  }
  const src = value as Record<string, unknown>;
  if (!('name' in src)) return EMPTY_DESCRIPTOR;

  /* A scalar becomes the text a person would have typed for it; anything else — an
     object, a list, a null — becomes blank, because there is no text form of it that
     `typedValue` would turn back into the same thing. */
  const asText = (v: unknown): string =>
    typeof v === 'string' ? v : typeof v === 'number' || typeof v === 'boolean' ? String(v) : '';

  /* The DRAFT shape reports σ in three flat fields; the PAYLOAD shape nests them. Both
     are read, in that order, so a mid-edit draft and a confirmed payload both restore. */
  const nested =
    src.uncertainty !== null && typeof src.uncertainty === 'object' && !Array.isArray(src.uncertainty)
      ? (src.uncertainty as Record<string, unknown>)
      : {};

  return {
    name: asText(src.name),
    kind: asText(src.kind),
    source: asText(src.source),
    value: asText(src.value),
    unit: asText(src.unit),
    sigma: asText('sigma' in src ? src.sigma : nested.sigma),
    sigmaUnit: asText('sigmaUnit' in src ? src.sigmaUnit : nested.unit),
    basis: asText('basis' in src ? src.basis : nested.basis),
  };
}

/**
 * The INVERSE of the `series` entry control — a confirmed spectrum back into the text
 * box that produced it. The other half of {@link descriptorDraftFrom}'s defect.
 *
 * TWO SHAPES ARRIVE HERE, for the same reason they do above. Mid-edit, the staged copy
 * is the RAW TEXT the reader typed — kept as text on purpose, because half-written JSON
 * is still their work and reparsing it to restore it would lose exactly the state a
 * Refresh most needs to preserve. After confirmation, `rawValue` is the PARSED array,
 * because `handleConfirm` submits `JSON.parse(seriesText)`.
 *
 * A parsed array is re-serialised with two-space indentation rather than reproduced
 * byte-for-byte, and that is a real loss stated rather than hidden: the reader's own
 * whitespace and key order do not survive a confirm. The VALUES do — `JSON.stringify`
 * of a parsed document is the same document — and the alternative was an empty box.
 * Anything else returns '', which leaves the reader where they were before this change
 * rather than putting a `[object Object]` in a field the record will store verbatim.
 */
export function seriesTextFrom(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      /* A circular structure cannot come off the wire, so this is defensive only —
         but an exception thrown while OPENING an editor is the failure mode this
         whole function exists to prevent, so it is caught rather than assumed away. */
      return '';
    }
  }
  return '';
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
          <span className="structured-label">Uncertainty Unit</span>
          <input
            id={`${idPrefix}-sigma-unit`}
            className="input"
            value={value.sigmaUnit}
            onChange={(e) => set('sigmaUnit')(e.target.value)}
            placeholder="e.g. eV"
          />
        </label>

        <label className="structured-field" htmlFor={`${idPrefix}-basis`}>
          <span className="structured-label">Uncertainty Basis</span>
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
      {/*
        ── THE SLOT FOR CONDITIONS THE FIVE QUESTIONS DO NOT ASK ABOUT ───────
        *"there should be an option to add more conditions to the run, not just
        those 5 things … make sure there is an option for the scientist to add
        custom conditions"* — project owner, 2026-09-14.

        THE OFFICIAL SCHEMA ALREADY HAS THE SLOT, which is why this is a hint
        rather than a new field. `schema/isaac_record_v1.json` declares
        `measurement.series[].conditions` as `type: object` with NO declared
        properties and NO `additionalProperties: false`, described as "Operating
        conditions specific to this series when they differ from context". So
        arbitrary keys are legal there and they EXPORT — verified by reading the
        vendored schema, and pinned by
        `structured-value-schema-parity.test.ts`, which fails if a future
        refresh closes the object.

        It is stated here, on the control that writes the series, because that is
        the only place a scientist can put them today. It is NOT a promise that
        ISAAC interprets them: a condition is carried through to the record
        verbatim, and nothing reads it. Anything with no schema home at all still
        belongs in Unmapped Notes, which is the surface built for exactly that.
      */}
      <p className="structured-entry-note">
        Conditions the questions above do not cover go in each series&apos;{' '}
        <code className="mono">conditions</code> object — your own keys, for example{' '}
        <code className="mono">{'{"control_mode": "potentiostatic", "flow_sccm": 20}'}</code>.
        The official schema accepts them there and they are exported verbatim;
        ISAAC does not interpret them.
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

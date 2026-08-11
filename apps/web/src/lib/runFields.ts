/*
 * THE RUN-LEVEL FIELD SET THE RUN WORKSPACE EDITS — and the evidence for every
 * entry in it.
 *
 * FIVE fields — the whole of the writable set, and not one more. Two independent sources had to agree before a path
 * could appear here, and NOTHING is here because it seemed useful:
 *
 *   1. `routes.RUN_WRITABLE_FIELD_PATHS` decides what can be written per run. It is
 *      `EXTRACTOR_FIELD_MAP`'s paths intersected with `field_level(path) ==
 *      LEVEL_RUN`, and it resolves to a CLOSED SET OF FIVE: `context.environment`,
 *      `context.temperature_K`, `context.thermodynamics.atmosphere`,
 *      `timestamps.acquired_start_utc`, `timestamps.acquired_end_utc`. The PATCH
 *      route refuses — 422, never a silent no-op — any key not in that set.
 *
 *      THIS PARAGRAPH USED TO CREDIT `field_level()` ALONE, and that was the gate
 *      the backend ABANDONED AS A BUG. `field_level` is a segment-aware PREFIX test:
 *      applied by itself it accepted `context.typo_K`, stored it with a fabricated
 *      `user_confirmation` evidence entry, and left the run permanently unexportable
 *      ("Additional properties are not allowed"). Finding I2 of `90b432d` replaced it
 *      with membership in the derived set; this file was written in `ef76291` and was
 *      not updated, so it went on naming the superseded mechanism. `field_level` is
 *      still how the set is DERIVED — it is no longer what the route checks.
 *   2. `schema/isaac_record_v1.json` decides the SHAPE. `context.environment`
 *      is `{"type": "string", "enum": ["operando","in_situ","ex_situ",
 *      "in_silico"]}` and `context.temperature_K` is `{"type": "number"}` —
 *      both listed in `context.required`. `timestamps.acquired_start_utc` is
 *      `{"type": "string", "format": "date-time"}`.
 *
 * THE LIST IS NOW THE WHOLE WRITABLE SET — five fields, not three, and the two that
 * were added are the two this comment used to explain the absence of:
 *
 *   * `timestamps.acquired_end_utc` was withheld because "a second timestamp
 *     demonstrates nothing the first does not". That was a reason to keep a DEMO
 *     small; it is not a reason to withhold half of a scientist's acquisition window
 *     once the surface is the real one. It needs no new machinery — same `datetime`
 *     kind, same format gate.
 *   * `context.thermodynamics.atmosphere` was withheld with "three fields were asked
 *     for, and this is the fourth", which that comment itself called the weaker of the
 *     two reasons. It is `{"type": "string"}` in the official schema with NO enum, so
 *     it is offered as free text. A curated dropdown here would be this file inventing
 *     a vocabulary the schema does not define.
 *
 * Neither addition widens what the SERVER accepts: both were already members of
 * `RUN_WRITABLE_FIELD_PATHS`, so the PATCH route accepted them before this file
 * offered them. What changed is only whether a scientist can reach them.
 *
 * WHAT IS STILL DELIBERATELY ABSENT, and why each absence is a decision:
 *   * `context.electrochemistry.*` is under a run-level PREFIX but is NOT in the
 *     writable set — measured, not assumed — so the route would 422 every path in it.
 *     That puts it in the same category as `system.configuration.*` below rather than
 *     the category this bullet used to claim: the earlier wording said it "is
 *     run-level by prefix", which implied it could be offered and was being held back
 *     for MVP-scope reasons (`CLAUDE.md` §15). Both reasons are true, but only one is
 *     load-bearing, and the load-bearing one is that a control here would be a
 *     control whose only outcome is a refusal.
 *   * `system.configuration.*` is UNCLASSIFIED, not run-level.
 *     `field_level()` documents that as a real answer rather than an oversight
 *     — whether two runs may legitimately differ in detector model is a
 *     scientific question this repository has no answer to — and the PATCH
 *     route refuses it with a typed 422. It is not offered here, so a reader is
 *     never handed a control whose only outcome is a refusal.
 *
 * The enum values below are TRANSCRIBED from the vendored official schema, not
 * invented and not curated. If the schema changes, this list is wrong and the
 * server's own validation is what will say so — this file never validates.
 */

import type { ApiRunCheckFinding, ApiRunFieldEnvelope, ApiRunView } from './types';

/** How one run-level field is entered. Drives the control, nothing else. */
export type RunFieldKind = 'enum' | 'number' | 'datetime' | 'text';

export interface RunFieldSpec {
  /** The dotted OFFICIAL path, sent verbatim as a `fields` key. */
  path: string;
  /** The human label. The path is shown too, demoted, never instead. */
  label: string;
  kind: RunFieldKind;
  /** Enum members, verbatim from the official schema. `enum` kind only. */
  options?: readonly string[];
  /** The unit the schema's path name already encodes (`_K`). Display only. */
  unit?: string;
  /** A format hint. It describes a FORMAT; it never suggests a value. */
  hint?: string;
}

export const RUN_FIELDS: readonly RunFieldSpec[] = [
  {
    path: 'context.environment',
    label: 'Environment',
    kind: 'enum',
    // schema/isaac_record_v1.json → properties.context.properties.environment.enum
    options: ['operando', 'in_situ', 'ex_situ', 'in_silico'],
  },
  {
    path: 'context.temperature_K',
    label: 'Temperature',
    kind: 'number',
    unit: 'K',
  },
  {
    path: 'context.thermodynamics.atmosphere',
    label: 'Atmosphere',
    // schema/isaac_record_v1.json -> properties.context.properties.thermodynamics
    // .properties.atmosphere is `{"type": "string"}` with NO enum, so this is free
    // text and not a picker. Offering a curated list here would be this file
    // inventing a vocabulary the official schema does not define.
    kind: 'text',
  },
  // THE TWO TIMESTAMPS ARE NOT CHECKED AGAINST EACH OTHER, and that is a recorded
  // open decision rather than an oversight. There is no `start <= end` check here, in
  // the card, in the PATCH route, or in official validation. MEASURED, not assumed:
  // a PATCH carrying `acquired_start_utc: 2026-01-31T12:00:00Z` with
  // `acquired_end_utc: 2026-01-01T00:00:00Z` returns 200 and stores both verbatim;
  // Check Run reports nothing about either path; and a record that validates
  // `ok: true` still validates `ok: true`, with zero errors, once its window is
  // inverted. So nothing downstream will catch it — do not read the schema reference
  // above as implying otherwise. The schema declares each field's TYPE and FORMAT and
  // says nothing about their relative order, and there is no cross-field constraint
  // for it to say it in.
  //
  // It is NEWLY REACHABLE through the product, which is the only thing this slice
  // changed about it: `acquired_end_utc` previously had no control, so a scientist
  // could not enter a window at all, inverted or otherwise. The behaviour is older
  // than the control.
  //
  // NOT FIXED HERE ON PURPOSE. Whether an inverted window is an error, a legitimate
  // encoding of something, or a question to ask is a scientific-validity judgement,
  // and this file's whole doctrine is that it does not make those (see the atmosphere
  // entry above, which declines to invent a vocabulary for the same reason). A gate
  // added here would also sit in the wrong place: the client is not where validity is
  // decided, and one added only here would be silent for every other writer.
  //
  // Related, and deliberately not contradicted: `official.py` installs no
  // `FormatChecker`, so `format: date-time` is unenforced repo-wide by design
  // (`apps/api/isaac_api/format_shadow.py` documents that and shadows it without
  // changing it). ISO_DATETIME below is therefore STRICTER than the downstream stack,
  // not a local restatement of it.
  {
    path: 'timestamps.acquired_start_utc',
    label: 'Acquisition start',
    kind: 'datetime',
    hint: 'ISO 8601 UTC, e.g. YYYY-MM-DDTHH:MM:SSZ',
  },
  {
    path: 'timestamps.acquired_end_utc',
    label: 'Acquisition end',
    kind: 'datetime',
    hint: 'ISO 8601 UTC, e.g. YYYY-MM-DDTHH:MM:SSZ',
  },
] as const;

/**
 * A deliberately permissive ISO-8601 date-time shape.
 *
 * It is a FORMAT gate and nothing more: it stops a plainly unparseable string
 * being sent as a timestamp, and it does not decide whether a well-formed
 * timestamp is the right one. The server's official-schema check is what
 * decides that, and this never stands in for it.
 */
const ISO_DATETIME =
  /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$/;

/** The result of turning one raw input string into something sendable. */
export type ParsedRunField =
  | { ok: true; value: unknown }
  | { ok: false; error: string };

/**
 * Raw input text -> the value to PATCH, or a typed refusal to send.
 *
 * AN EMPTY BOX IS `null`, WHICH IS THE CONTRACT'S "CLEAR THIS FIELD" — not an
 * omission and not an empty string. Clearing a value a person entered has to be
 * possible, and the only honest encoding of it is the one the server defines.
 *
 * A malformed entry returns `{ok:false}` and is NOT sent. That is a formatting
 * check, not a scientific one: it never completes what was typed, never rounds it and
 * never applies a scientific judgement to it.
 *
 * IT DOES REINTERPRET, THOUGH, AND THE EARLIER WORDING ("never rewrites, rounds,
 * coerces") DENIED IT. `Number()` accepts more grammars than a decimal literal:
 * `1e3` becomes `1000`, `0x12C` becomes `300`, `Infinity` is rejected only because
 * `Number.isFinite` catches it afterwards. So what is STORED can differ in
 * presentation from what was TYPED. Two things keep that honest rather than hidden:
 * the value is only ever the one `Number()` produced (nothing is invented), and the
 * card now drops its local text once the server acknowledges a field, so the box
 * shows the stored value instead of the typed string. The alternative — send it and let the 422 come back — turns a
 * typo into a red failure state, which reads as the app rejecting the science.
 */
export function parseRunField(spec: RunFieldSpec, raw: string): ParsedRunField {
  const text = raw.trim();
  if (text === '') return { ok: true, value: null };
  switch (spec.kind) {
    case 'number': {
      // `Number('')` is 0 and `Number(' 12 ')` is 12 — the empty case is already
      // returned above, and the trim is why the second is not a surprise.
      const n = Number(text);
      if (!Number.isFinite(n)) return { ok: false, error: 'Enter a number.' };
      return { ok: true, value: n };
    }
    case 'datetime':
      if (!ISO_DATETIME.test(text)) {
        return { ok: false, error: 'Enter an ISO 8601 date-time, e.g. 2026-01-31T09:00:00Z.' };
      }
      return { ok: true, value: text };
    case 'enum':
      if (spec.options && !spec.options.includes(text)) {
        return { ok: false, error: 'Choose one of the listed values.' };
      }
      return { ok: true, value: text };
    case 'text':
      // The schema says `{"type": "string"}` and nothing else, so there is nothing
      // to check. It is returned trimmed and otherwise untouched: no casing, no
      // vocabulary, no normalisation. The empty case became `null` above, which is
      // the contract's "clear this field".
      return { ok: true, value: text };
  }
}

/** The scalar inside a field envelope, or `null` when there is nothing there. */
export function envelopeValue(env: ApiRunFieldEnvelope | undefined): unknown {
  if (env === undefined || env === null) return null;
  return env.value ?? null;
}

/** A field's current value as input text. `null`/absent renders as empty. */
export function envelopeText(env: ApiRunFieldEnvelope | undefined): string {
  const value = envelopeValue(env);
  if (value === null || value === undefined) return '';
  return String(value);
}

/** How many of {@link RUN_FIELDS} this run has a value for. */
export function runFilledCount(run: ApiRunView): number {
  return RUN_FIELDS.filter((spec) => envelopeValue(run.fields?.[spec.path]) !== null).length;
}

/**
 * The one-line conditions summary on a collapsed card.
 *
 * It states only what the run actually carries, in the order the fields are
 * entered, and returns `null` when the run carries none of them — a collapsed
 * card then says so in words rather than showing an empty slot that reads like
 * a rendering failure.
 */
export function runConditionsSummary(run: ApiRunView): string | null {
  const parts = RUN_FIELDS.map((spec) => {
    const value = envelopeValue(run.fields?.[spec.path]);
    if (value === null || value === undefined) return null;
    return spec.unit ? `${String(value)} ${spec.unit}` : String(value);
  }).filter((p): p is string => p !== null);
  return parts.length > 0 ? parts.join(' · ') : null;
}

/**
 * The displayable text of one check finding, or `null` when there is none.
 *
 * The contract does not pin the element shape of `blockers`, so this reads the
 * fields a finding plausibly carries in a fixed order and gives up honestly
 * rather than guessing. `null` is rendered by the caller as a stated inability
 * to describe the finding — a finding is never silently dropped, because the
 * count of things blocking a run is the one number on this surface that must
 * not quietly shrink.
 */
export function runFindingText(finding: ApiRunCheckFinding): string | null {
  if (typeof finding === 'string') return finding.trim() || null;
  if (finding === null || typeof finding !== 'object') return null;
  const text = finding.message ?? finding.question ?? finding.label ?? finding.path ?? finding.id;
  return typeof text === 'string' && text.trim() !== '' ? text.trim() : null;
}

/**
 * The `field:`-addressed inherited entries, in a stable order, for display.
 *
 * `block:` addresses (`attribution`, `tags`) are excluded: their payloads are
 * whole objects and arrays, and this surface has no honest one-line rendering
 * for them — showing a truncated one would be a claim about their content.
 * `absent` entries are excluded too: nothing was inherited, so there is nothing
 * to attribute to the experiment.
 */
export function inheritedFieldRows(
  run: ApiRunView,
): { address: string; path: string; state: string; text: string }[] {
  const entries = Object.entries(run.inherited ?? {});
  const rows: { address: string; path: string; state: string; text: string }[] = [];
  for (const [address, resolution] of entries) {
    if (!address.startsWith('field:')) continue;
    if (!resolution || resolution.state === 'absent') continue;
    const payload = resolution.payload;
    const value =
      payload !== null && typeof payload === 'object' && 'value' in payload
        ? (payload as { value: unknown }).value
        : payload;
    if (value === null || value === undefined) continue;
    rows.push({
      address,
      path: address.slice('field:'.length),
      state: resolution.state,
      text: String(value),
    });
  }
  rows.sort((a, b) => a.path.localeCompare(b.path));
  return rows;
}

/*
 * PER-RUN OVERRIDES OF INHERITED RECORD-LEVEL VALUES — the pure half.
 *
 * WHAT THIS FILE IS NOT, stated first because it is the constraint that shaped
 * every function in it. It does NOT resolve inheritance, and it must never learn
 * how. Resolution is `workspace.resolve_inherited` — read-time, by reference,
 * never a copy — and the server publishes its answer per address under
 * `run.inherited[address]` as `{state, payload, inherited_payload,
 * displaced_payload}`. Everything below READS that answer. Nothing below
 * computes "what would this value be if it were inherited", merges a record
 * value into a run, or decides which of the two wins. A second copy of that rule
 * living in TypeScript would be a copy that can disagree with the one that
 * exports the record.
 *
 * THE THREE STATES ARE THE SERVER'S OWN WORDS (`routes._resolution_state`):
 *
 *   `inherited`  — this run records no override, so it reads the record's value
 *                  live. A later change to the record changes what this run has.
 *   `overridden` — this run recorded its own value. The record's current value is
 *                  still reported beside it (`inherited_payload`), and it may have
 *                  moved since; `displaced_payload` is what the override displaced
 *                  at the moment it was recorded, and is history, never refreshed.
 *   `absent`     — neither the run nor the record carries anything there.
 *
 * WHAT AN OVERRIDE PAYLOAD HAS TO BE, and why this file assembles one at all.
 * `POST …/overrides` takes the whole draft field envelope from the client and
 * stores it verbatim — unlike the run-field PATCH, which composes the envelope
 * SERVER-side (`routes._apply_run_field`). So a client cannot avoid building one.
 * It is built to exactly the shape that route's own tests use
 * (`test_run_api._envelope`), and it is the deterministic draft validator — not
 * this file — that decides whether it is acceptable: the route probes the payload
 * through `validate_draft` and refuses with the validator's own words. This file
 * therefore never validates, and a refusal is always rendered from the server's
 * reply.
 */

import type { ApiRunInherited, ApiRunView, RunInheritedState } from './types';

/** The namespace prefix a record-level FIELD address carries on the wire. */
export const FIELD_ADDRESS_PREFIX = 'field:';

/**
 * The scalar inside a `field:` payload, or `null`.
 *
 * A `field:` payload is a draft field envelope; a `block:` payload is the block
 * itself. Only `field:` addresses reach this function — see {@link overrideRows}
 * for why blocks are excluded from this surface entirely.
 */
export function payloadValue(payload: unknown): unknown {
  if (payload === null || payload === undefined) return null;
  if (typeof payload === 'object' && 'value' in (payload as object)) {
    return (payload as { value: unknown }).value ?? null;
  }
  return payload;
}

/** A value as one line of display text. `null`/absent has no text at all. */
export function valueText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  // An object or array at a `field:` address is not something this row can render
  // in one line, and a truncated rendering would be a claim about its content.
  return null;
}

/**
 * TRUE when a value IS there and this row cannot render it — never for absence.
 *
 * `valueText` returns `null` for two different facts: the address carries
 * nothing, and the address carries an object or an array. A row that reports
 * both as "carries no value" states the first when the second is true, which is
 * a false statement about a scientist's record rather than a rendering
 * shortcoming. Latent rather than live today — every one of the overridable
 * `field:` addresses is coerced to `str`/`float` server-side — but the two
 * sentences are different and the panel says whichever one holds.
 */
export function isUnrenderableValue(value: unknown): boolean {
  return value !== null && value !== undefined && valueText(value) === null;
}

/**
 * One row of the inherited panel: what this run holds at one record-level
 * address, where it came from, and what the record says about it now.
 *
 * Every field here is READ from the server's resolution. `recordMovedSince` is
 * the one derived value, and it derives nothing about inheritance: it compares
 * two payloads the server sent in the same response — what the override
 * displaced, and what the record carries now — so the row can say that the
 * record has changed since the override was recorded instead of showing two
 * numbers with no explanation of why they differ.
 */
export interface OverrideRow {
  /** The namespaced address, spelt exactly as the server spells it. */
  address: string;
  /** The dotted official path — the address with its namespace removed. */
  path: string;
  state: RunInheritedState;
  /** What this run actually has at the address, as text. */
  text: string | null;
  /** The RECORD's current value, as text. `null` when it carries none. */
  recordText: string | null;
  /**
   * True when the record DOES carry a value here and it is not one line of text
   * (an object or an array). Distinguishes "carries nothing" from "carries
   * something this row cannot show" — see {@link isUnrenderableValue}.
   */
  recordUnrenderable: boolean;
  /** What the override displaced when recorded, as text. History, never refreshed. */
  displacedText: string | null;
  /** True when the record's value has moved away from what the override displaced. */
  recordMovedSince: boolean;
  /** The whole resolution, for the payload builder's type reference. */
  resolution: ApiRunInherited;
}

/**
 * The `field:`-addressed rows of one run's inherited map, in a stable order.
 *
 * `block:` ADDRESSES ARE EXCLUDED, and that is a deliberate scope boundary
 * rather than an oversight. `block:attribution` and `block:tags` are overridable
 * server-side, but their payloads are whole objects and arrays: this surface has
 * no honest one-line rendering for them and no control that could author one, so
 * offering an override button beside a value it cannot show would be a control
 * whose outcome the reader could not predict. They stay read-only here.
 *
 * `absent` ROWS ARE EXCLUDED for the reason they always were: nothing is
 * inherited and nothing is overridden, so there is nothing to attribute and
 * nothing to revert to.
 *
 * AN OVERRIDDEN ROW WITH NO VALUE IS KEPT. `{value: null, status:
 * "needs_confirmation"}` is a legitimate override the route accepts by name — it
 * is how a run says "my value differs and I cannot yet say what it is" — and
 * dropping it would hide a recorded act and its Revert control with it.
 */
export function overrideRows(run: ApiRunView): OverrideRow[] {
  const rows: OverrideRow[] = [];
  for (const [address, resolution] of Object.entries(run.inherited ?? {})) {
    if (!address.startsWith(FIELD_ADDRESS_PREFIX)) continue;
    if (!resolution || resolution.state === 'absent') continue;
    const recordValue = payloadValue(resolution.inherited_payload);
    const text = valueText(payloadValue(resolution.payload));
    const recordText = valueText(recordValue);
    const displacedText = valueText(payloadValue(resolution.displaced_payload));
    if (text === null && resolution.state !== 'overridden') continue;
    rows.push({
      address,
      path: address.slice(FIELD_ADDRESS_PREFIX.length),
      state: resolution.state,
      text,
      recordText,
      recordUnrenderable: isUnrenderableValue(recordValue),
      displacedText,
      recordMovedSince:
        resolution.state === 'overridden' &&
        resolution.displaced_payload !== undefined &&
        displacedText !== null &&
        recordText !== null &&
        displacedText !== recordText,
      resolution,
    });
  }
  rows.sort((a, b) => a.path.localeCompare(b.path));
  return rows;
}

/* ── the payload ───────────────────────────────────────────────────────────── */

/** What {@link buildOverridePayload} produces: something sendable, or a refusal. */
export type OverridePayloadResult =
  | { ok: true; payload: unknown }
  | { ok: false; error: string };

/**
 * The JSON type this address should be sent as, taken from what the RECORD
 * already carries there — `'number'` or `'text'`.
 *
 * READ THIS BEFORE CHANGING IT, because the obvious source is the wrong one.
 * Three of the fifteen overridable addresses are numeric in practice
 * (`sample.geometry.pellet_diameter_mm`, `sample.composition.*_mass_fraction`)
 * and the official schema declares NO type for any of them: `sample.geometry`
 * and `sample.composition` are open-by-design namespaces (measured against
 * `schema/isaac_record_v1.json`, and pinned server-side by
 * `test_the_overridable_field_paths_include_the_schemas_OPEN_namespaces`). So a
 * client-side numeric gate justified by "the schema says number" would be
 * inventing a constraint the schema does not impose — the same invention
 * `runFields.ts` refuses when it declines to curate a vocabulary for
 * `context.thermodynamics.atmosphere`.
 *
 * The justification is narrower and is about CONSISTENCY, not validity: the run
 * is overriding ONE value of a field the record already holds, and silently
 * changing its JSON type from number to string is a change nobody asked for. It
 * would export `"8.5"` from this run beside `8.0` from its siblings, and no
 * validator anywhere would object. So the type is mirrored from the record's own
 * current value, the reader is TOLD that is what is happening, and a text entry
 * that cannot be that type is refused on screen rather than sent — a format
 * check, never a scientific judgement.
 *
 * IT DOES REINTERPRET, THOUGH, AND THE EARLIER WORDING ("a format check, exactly
 * like `parseRunField`'s") DENIED IT — while `parseRunField`'s own header was
 * amended to say the opposite. `Number()` accepts more grammars than a decimal
 * literal, so this gate is a format check AND a reinterpretation: `0x10` is sent
 * as `16` and `1e3` as `1000`, which makes the `user_confirmation.answer` this
 * file writes read `"16"` for text nobody typed. Three things keep that honest
 * rather than hidden. The value is only ever the one `Number()` produced, so
 * nothing is invented; `Infinity` and `NaN` are refused outright by
 * `Number.isFinite`; and it is the same reinterpretation the SERVER records for a
 * run's own fields (`routes._confirmation_answer` stringifies the stored value,
 * not the keystrokes), so the two answers agree rather than diverging. Once the
 * write lands the row shows the STORED value back — `16`, not `0x10` — which is
 * where the reader sees what was recorded.
 *
 * The reference is the RECORD's value where there is one, and the run's own
 * override where the record carries nothing (an override may sit at an address
 * the record does not carry). Absent both, text.
 */
export function overrideValueKind(resolution: ApiRunInherited): 'number' | 'text' {
  const reference =
    payloadValue(resolution.inherited_payload) ?? payloadValue(resolution.payload);
  return typeof reference === 'number' ? 'number' : 'text';
}

/**
 * The evidence question this override records itself as answering.
 *
 * It names the ACT — an override on this run — and not a scientific proposition.
 * It is stable for a given path, which is what makes a re-recorded override
 * byte-identical to the stored one; see {@link buildOverridePayload}.
 */
export function overrideQuestion(path: string): string {
  return `Override ${path} on this run?`;
}

/**
 * Raw entry text → the draft field envelope to send, or a refusal to send it.
 *
 * THE ENVELOPE CARRIES A `user_confirmation` ENTRY AND NO TIMESTAMP, and both
 * halves of that are decisions.
 *
 * · The entry is REQUIRED. A `verified` value with an empty evidence list is
 *   refused by the route, in the deterministic draft validator's own words
 *   ("verified field has no observed evidence or user confirmation") — that is
 *   `CLAUDE.md` §5 enforced at the boundary that writes. The entry is not
 *   manufactured evidence for the SCIENCE: it records the only thing this
 *   application actually observed, which is that a person entered this value on
 *   this run and confirmed it. That is exactly what `routes._apply_run_field`
 *   records server-side for a run's own fields, with the same `source_type`.
 *
 * · The TIMESTAMP IS OMITTED ON PURPOSE. Every other `user_confirmation` in this
 *   repository is stamped with the SERVER's clock; a browser's clock is not an
 *   authority this app has any reason to trust, and writing one would put an
 *   unverified fact into stored evidence. The route accepts an entry without one
 *   (measured — `{"source_type": "user_confirmation", "question": …, "answer": …}`
 *   is stored with 200), and the authoritative time of the act is recorded by
 *   the server anyway, as the override's own `recorded_utc`.
 *
 *   It also buys the idempotence the route documents. `set_run_override` compares
 *   the new payload against the stored one and no-ops when they are equal, so a
 *   payload containing a fresh clock reading would defeat that on every
 *   re-record: the value would look changed, the run's revision would advance and
 *   the recorded time would be restamped. Omitting the timestamp makes this
 *   function a pure function of the path and the value, so re-recording the same
 *   value builds a byte-identical envelope and the write really is the no-op the
 *   contract promises.
 *
 * WHAT IT NEVER DOES: complete a partial entry, round it, apply a unit, or supply
 * a value nobody typed. An empty box is refused rather than sent as `null` —
 * unlike a run-level field, where `null` is the contract's "clear this field",
 * an override IS the act of recording a value, and a blank one records nothing.
 */
export function buildOverridePayload(row: OverrideRow, raw: string): OverridePayloadResult {
  const text = raw.trim();
  if (text === '') {
    return {
      ok: false,
      error: 'Enter the value this run holds. An override records a value; it never records a blank.',
    };
  }
  let value: unknown = text;
  if (overrideValueKind(row.resolution) === 'number') {
    const n = Number(text);
    if (!Number.isFinite(n)) {
      return { ok: false, error: 'Enter a number — the record holds a number at this path.' };
    }
    value = n;
  }
  return {
    ok: true,
    payload: {
      value,
      status: 'verified',
      evidence: [
        {
          source_type: 'user_confirmation',
          question: overrideQuestion(row.path),
          answer: typeof value === 'string' ? value : JSON.stringify(value),
        },
      ],
    },
  };
}

/* ── refusals ──────────────────────────────────────────────────────────────── */

/**
 * What the server said about a refusal, for display — never a generic failure.
 *
 * EVERY 422 THIS OPERATION RETURNS CARRIES A `message`, and most carry the
 * `address` as well: `not_overridable` (the address cannot hold an override at
 * all), `invalid_envelope` (with the draft validator's own `findings`),
 * `invalid_block_payload`, `unrepresentable_value` and `confirmation_required`.
 * The server's sentence is shown VERBATIM rather than paraphrased, because it is
 * the one that names what was refused and why — and because a paraphrase here is
 * a second copy of a rule this client does not own. `null` when the failure
 * carried no readable typed body (an unreachable backend, an edge intercept),
 * which the caller must render as its own honest "could not be reached", never
 * as a refusal the server did not make.
 */
export interface OverrideRefusal {
  reason?: string;
  address?: string;
  message: string;
  findings: string[];
}

export function readOverrideRefusal(body: unknown): OverrideRefusal | null {
  if (body === null || typeof body !== 'object') return null;
  const b = body as Record<string, unknown>;
  const message = typeof b.message === 'string' && b.message.trim() !== '' ? b.message.trim() : null;
  if (message === null) return null;
  const findings = Array.isArray(b.findings)
    ? b.findings.filter((f): f is string => typeof f === 'string' && f.trim() !== '')
    : [];
  return {
    reason: typeof b.error === 'string' ? b.error : undefined,
    address: typeof b.address === 'string' ? b.address : undefined,
    message,
    findings,
  };
}

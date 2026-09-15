/*
 * ACQUISITION TIMESTAMPS — a picker a scientist can use, over the SAME stored
 * string the text box always produced.
 *
 * The project owner, 2026-09-15: *"I'm putting this sample information into the
 * run — that acquisition start, acquisition end, no idea, like why. Maybe that
 * is the actual format it requires, so maybe that's something separate."* He is
 * right that the format is separate, and he should still not be hand-typing
 * `2026-01-31T09:00:00Z`.
 *
 * ── THE CONTRACT THIS MODULE EXISTS TO NOT BREAK ───────────────────────────
 *
 * THE STORED FORMAT DOES NOT CHANGE. Every value this module produces is fed
 * through the same `parseRunField` gate and PATCHed as the same string a typed
 * entry produced. `parseRunField`'s `ISO_DATETIME` is deliberately STRICTER than
 * the downstream stack — `official.py` installs no `FormatChecker`, so
 * `format: date-time` is unenforced repo-wide by design — and nothing here
 * loosens it.
 *
 * NO `start <= end` CHECK, AND THAT IS A RECORDED DECISION RATHER THAN AN
 * OVERSIGHT. `runFields.ts` carries the measurement: an inverted window PATCHes
 * 200, Check Run reports nothing about either path, and a record that validated
 * `ok: true` still validates `ok: true` with zero errors once its window is
 * inverted. Whether an inverted window is an error, a legitimate encoding, or a
 * question to ask is a scientific-validity judgement, and a gate added only in
 * this client would be silent for every other writer. A picker makes an
 * inverted window EASIER TO PRODUCE — two clicks rather than two typed strings
 * — and that is disclosed rather than closed here.
 *
 * ── WHY THERE IS NO `Date` OBJECT ANYWHERE IN THIS FILE ────────────────────
 *
 * `new Date('2026-01-31T09:00:00+02:00')` resolves against the READER'S zone, so
 * every function below would answer differently on a different machine and a
 * scientist in Menlo Park and one in Hamburg would read different clock times
 * off the same record. Every function here reads the literal components the
 * stored string already carries and re-spells them. That also makes the whole
 * module deterministic under test, which a `Date`-based one could not be.
 */

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const;

/**
 * The shape this module can read: a date, a time, optional seconds and
 * fractional seconds, and an optional zone that is either `Z` or an offset.
 */
const PARTS =
  /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$/;

/**
 * A stored ISO-8601 date-time as something a person reads — or, unchanged, the
 * string that was stored.
 *
 *   `2026-01-31T09:00:00Z`       -> `Jan 31, 2026 · 09:00 UTC`
 *   `2026-01-31T09:00:00+02:00`  -> `Jan 31, 2026 · 09:00 +02:00`
 *   `2026-01-31T09:00:00`        -> `Jan 31, 2026 · 09:00`   (no zone claimed)
 *   anything else                -> returned VERBATIM
 *
 * The last line is the rule: a string this shape does not describe is handed
 * back untouched, because re-spelling something you could not read is how a
 * surface ends up showing a value nobody entered. A month number outside 1–12
 * also falls through to verbatim rather than indexing off the end of the list.
 *
 * TWENTY-FOUR HOUR, NOT `9:00 AM`, and the choice is deliberate: an acquisition
 * timestamp is an instrument reading, `09:00` and `21:00` are never one keystroke
 * apart in it, and `12:00 AM` is the one clock notation a reader has to stop and
 * think about. It is ALSO the only such renderer in the app — the Record Map row
 * and the run editor's read-back are the same function — so the two can never
 * show one stored value in two spellings.
 */
export function formatStoredDatetime(raw: string): string {
  const m = PARTS.exec(raw.trim());
  if (m === null) return raw;
  const [, year, month, day, hh, mm, ss, , zone] = m;
  const monthName = MONTHS[Number(month) - 1];
  if (monthName === undefined) return raw;
  // Seconds are shown only when the stored value carries a non-zero value for
  // them: `:00` is noise on every row, and dropping a real `:37` would be a
  // rendering that quietly disagrees with the record.
  const clock = ss !== undefined && ss !== '00' ? `${hh}:${mm}:${ss}` : `${hh}:${mm}`;
  const suffix = zone === undefined ? '' : zone === 'Z' ? ' UTC' : ` ${zone}`;
  return `${monthName} ${Number(day)}, ${year} · ${clock}${suffix}`;
}

/**
 * The stored string as an `<input type="datetime-local">` value, or `null` when
 * the picker cannot represent it.
 *
 * `null` IS THE COMMON AND CORRECT ANSWER FOR THREE REAL CASES, and each one is
 * why the ISO text path beside the picker is not decoration:
 *
 *   * an explicit numeric OFFSET (`+02:00`). `datetime-local` has no zone at
 *     all, so the picker could only show the wall clock and then re-serialize it
 *     as UTC — silently moving the instant by two hours.
 *   * NO ZONE AT ALL. Re-serializing would ADD a `Z` the scientist never wrote,
 *     turning "unspecified" into a claim about UTC. The field is named `_utc`
 *     and that is still not this module's assertion to make.
 *   * anything the shape above does not match, including a half-typed string
 *     the reader is still holding.
 *
 * A value the picker CAN represent is `Z`-suffixed, and the picker round-trips
 * it exactly: `2026-01-31T09:00:00Z` -> `2026-01-31T09:00:00` -> back to
 * `2026-01-31T09:00:00Z`.
 */
export function isoToPickerValue(raw: string): string | null {
  const text = raw.trim();
  if (text === '') return '';
  const m = PARTS.exec(text);
  if (m === null) return null;
  const [, year, month, day, hh, mm, ss, frac, zone] = m;
  if (zone !== 'Z') return null;
  // Fractional seconds are dropped by `datetime-local` in every browser, so a
  // value carrying them is not round-trippable and belongs in the text path.
  if (frac !== undefined) return null;
  return `${year}-${month}-${day}T${hh}:${mm}:${ss ?? '00'}`;
}

/**
 * A `datetime-local` value as the official string to store.
 *
 * The browser hands back `YYYY-MM-DDTHH:mm` or `YYYY-MM-DDTHH:mm:ss` (never a
 * zone, and never anything else — the control sanitizes its own value, which is
 * why this needs no validation of its own and does no guessing). Seconds are
 * filled to `:00` when the control omitted them, and `Z` is appended, because
 * the control is LABELLED as UTC on the screen: the reader is entering a UTC
 * wall clock, so recording it as one adds no claim they did not make.
 *
 * An empty control returns `''`, which `parseRunField` turns into `null` — the
 * contract's "clear this field", and the only honest reading of an emptied box.
 */
export function pickerValueToIso(value: string): string {
  const text = value.trim();
  if (text === '') return '';
  const withSeconds = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(text) ? `${text}:00` : text;
  return `${withSeconds}Z`;
}

/* ── the three sentences the run editor's datetime fields carry ─────────────
 *
 * Here rather than inline for the reason `casing-registers.test.tsx` exists:
 * copy authored at the call site is copy nobody re-reads. All three are
 * Register 2 prose — they explain a mechanism, they name no value, and none of
 * them is a verdict.
 */

/**
 * WHY THE ZONE IS STATED AND NOT ASSUMED. `datetime-local` has no timezone of
 * its own — the browser shows and returns a bare wall clock — so the ONLY thing
 * telling a reader which clock they are entering is this sentence and the `UTC`
 * marker beside the control. Without it the field is genuinely ambiguous, and
 * the value is being appended with a `Z` regardless.
 */
export const RUN_DATETIME_ZONE_HINT =
  'Entered and stored as UTC. This control shows exactly what you typed — it never ' +
  'converts to or from your computer’s timezone.';

/** The text path's disclosure. It names both acts, because both are real. */
export const RUN_DATETIME_TEXT_SUMMARY = 'Enter or paste ISO 8601 text';

/**
 * Shown when the stored value is one the picker cannot hold. It says WHICH
 * value the record has (the one in the box below) rather than leaving an empty
 * picker to read as an empty field.
 */
export const RUN_DATETIME_UNPICKABLE =
  'The stored value carries a timezone offset, fractional seconds, or a shape this ' +
  'picker cannot show, so the picker is unavailable and the text below is what the ' +
  'record holds.';

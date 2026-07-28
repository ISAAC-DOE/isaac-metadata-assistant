/*
 * P36V.1 Unit B — DISPLAY-ONLY humanization of validation/blocker locations.
 *
 * Why this module exists
 * ---------------------
 * The deterministic truth core renders a root-level JSON Schema violation as the
 * literal string `$`:
 *
 *   src/isaac_records/official.py:71
 *     path=".".join(str(p) for p in err.absolute_path) or "$",
 *
 * For a root-level violation (a missing required TOP-LEVEL property, a root type
 * error, a root `additionalProperties` error) `err.absolute_path` is an empty
 * deque, the join yields `""`, and the `or "$"` fallback substitutes the literal.
 * That is correct for a JSONPath locator and it is NOT changed here: `official.py`
 * is truth core. Two Assistant producers were echoing that locator straight into
 * a user-facing sentence — "1 path is listed as blocking export: $." — which reads
 * as a field name and names nothing a reader can act on.
 *
 * This module is the display layer for that. It changes NO validator semantics,
 * NO blocker semantics and NO validation result: it maps an already-computed
 * locator to (a) a human-facing location phrase and (b) the EXACT technical
 * locator, preserved byte-for-byte for a `Technical Details` disclosure.
 *
 * Cross-language equivalence
 * --------------------------
 * The second producer is Python (`apps/api/isaac_api/assistant_paths.py`). Literal
 * code sharing across the two runtimes is impossible, so there are two
 * implementations with IDENTICAL behaviour, and the equivalence is locked by ONE
 * shared case table — `apps/web/src/test/validation-path-cases.json` — replayed by
 * BOTH test suites (`apps/web/src/lib/assistantPaths.test.ts` and
 * `apps/api/tests/test_assistant_paths.py`). A change to one implementation that
 * is not mirrored in the other fails the other language's suite.
 *
 * The equivalence claim is BOUNDED, and the bound is stated rather than implied
 * (P36V.1 review, M1): the two implementations agree on every input in the shared
 * table and in each suite's adversarial corpus — dot-joined JSON locators, root
 * markers, and degenerate/absent values. They are NOT claimed equal over arbitrary
 * Unicode: `String.prototype.trim()` and Python's `str.strip()` have different
 * whitespace sets (JS strips the BOM `\ufeff`; Python strips `\x1c`–`\x1f` and
 * `\x85`; neither strips the other's). The characters the reviewer measured
 * diverging on are removed explicitly by `INVISIBLE_RE` in BOTH implementations, so
 * those inputs now agree; some other exotic code point may still resolve
 * differently in the two runtimes. The deterministic validator emits only `$` or a
 * dot-join of schema property names and array indices, so no reachable locator
 * depends on the difference.
 *
 * Safety properties deliberately held:
 *   · a field name is never INVENTED — every rendered segment comes verbatim from
 *     the locator (segments are not title-cased, and `_` is not rewritten, so two
 *     distinct locators can never be humanized onto one label);
 *   · distinct locators are never COLLAPSED, over the locator shapes that reach
 *     this module: the mapping is injective over dot-joined locators whose segments
 *     contain neither `.` nor the rendered separator `" → "` — which is every
 *     locator `official.py` can emit. It is NOT injective in general (M2):
 *     `{'$','$.','$..','$ '}` all render as `RECORD_LEVEL_LABEL`, and
 *     `{'a → b','a.b','a..b'}` all render as `a → b`. Each such collision either
 *     denotes the SAME JSON location or needs a segment containing the separator
 *     glyph, so no collision can misdescribe a location — but the property is
 *     stated as it holds, not as a blanket guarantee;
 *   · the raw `$` never reaches a primary label — only the details disclosure. This
 *     now holds UNIVERSALLY, not just for the table's inputs: a `$` is a
 *     record-level location as the LEADING root marker, and a locator with a `$`
 *     inside any segment (`$$`, `a.$.b`, `assets.$`, `$$$`) yields the honest unknown
 *     location rather than being echoed verbatim (M2 — that echo used to falsify
 *     this very claim, and both suites now enforce it over a generated corpus);
 *   · nothing here states a verdict. The summary is hedged ("may be blocking
 *     export") and passes `hasVerdictLanguage` / the backend's `has_verdict_language`.
 */

/** How a validation locator identifies its location. */
export type ValidationLocationKind = 'record' | 'field' | 'unknown';

export interface ValidationLocation {
  kind: ValidationLocationKind;
  /** The human-facing location phrase. NEVER a bare `$`. */
  label: string;
  /**
   * The EXACT reported locator, byte-for-byte, for the `Technical Details`
   * disclosure only. `NO_PATH_TECHNICAL` when nothing usable was reported.
   */
  technical: string;
}

/** The phrase that replaces the raw root locator `$` in user-facing copy. */
export const RECORD_LEVEL_LABEL = 'the record itself';

/** The phrase used when a blocker carries no usable location at all. */
export const UNKNOWN_LOCATION_LABEL = 'an unreported location';

/** The `Technical Details` stand-in when no locator string was reported. */
export const NO_PATH_TECHNICAL = '(no path reported)';

/** Rendered between locator segments in a humanized label. */
export const SEGMENT_SEPARATOR = ' → ';

/** The honest empty answer, shared verbatim with the Python producer. */
export const NO_BLOCKING_ISSUES =
  'No blocking validation issues are listed in the current validation response.';

/**
 * The literal root locator the deterministic validator emits for a root-level
 * violation (`src/isaac_records/official.py:71`).
 */
export const ROOT_MARKER = '$';

/**
 * The FIXED message the API emits when the validation dry-run ITSELF failed to run.
 * `apps/api/isaac_api/routes.py` — `post_validate` (which feeds this composer) and
 * the assistant's own dry-run — both return
 * `[{ path: '$', message: 'Validation could not be completed.' }]` from their
 * defensive `except`. That list is a CRASH SENTINEL, not a validation finding: no
 * schema violation was located, so rendering it through the locator formatter and
 * saying "1 record-level validation issue may be blocking export" would state
 * something the validator never reported (CLAUDE.md §3/§5). The producer is not
 * changed — this constant is how a READER of the response tells the sentinel apart.
 */
export const VALIDATION_UNAVAILABLE_MESSAGE = 'Validation could not be completed.';

/**
 * The honest sentence for that case, shared verbatim with the Python producer. It
 * claims NO location, states NO count of issues, and states no verdict.
 */
export const VALIDATION_UNAVAILABLE_SUMMARY =
  'The deterministic schema check could not be completed for this record, so no ' +
  'blocking locations can be listed.';

/**
 * Invisible characters the two runtimes' trim primitives disagree about: JS's
 * `trim()` removes the BOM `\ufeff` but not `\x1c`–`\x1f` / `\x85`; Python's
 * `str.strip()` does the opposite. Removing this explicit set FIRST, in both
 * implementations, keeps them in agreement on those inputs and stops an
 * all-invisible "locator" from being rendered as a location label a reader sees as
 * blank (P36V.1 review, M1). The reported string is still preserved byte-for-byte
 * in `technical`; only the LABEL derivation is affected.
 */
const INVISIBLE_RE = /[\ufeff\x1c\x1d\x1e\x1f\x85]/g;

/** Trim, with the cross-runtime invisible set removed first. */
function trim(value: string): string {
  return value.replace(INVISIBLE_RE, '').trim();
}

/**
 * True iff `errors` is the API's validation-CRASH sentinel rather than a list of
 * validation findings.
 *
 * Detection keys on the MESSAGE, not the path: the message is the distinguishing
 * field (the `$` path is incidental, and a real root-level violation carries a
 * `jsonschema` message). Whitespace-tolerant, and total for any shape. Returns
 * `false` for an empty list, so "no errors" stays the honest empty answer.
 */
export function isValidationUnavailable(errors: unknown): boolean {
  if (!Array.isArray(errors) || errors.length === 0) return false;
  return errors.every((err) => {
    const message = (err as { message?: unknown } | null)?.message;
    return typeof message === 'string' && trim(message) === VALIDATION_UNAVAILABLE_MESSAGE;
  });
}

/**
 * Deterministic pluralization: "1 field" / "2 fields". `plural` defaults to
 * `singular + 's'`. No `field(s)` / `entr(y/ies)` placeholders ever survive to
 * rendered output. (Owned here, imported by the composer, so there is exactly ONE
 * implementation per language.)
 */
export function count(n: number, singular: string, plural?: string): string {
  const word = n === 1 ? singular : (plural ?? `${singular}s`);
  return `${n} ${word}`;
}

/** Join the first ≤3 items with ", "; append ", …and K more" for the remainder. */
export function joinCapped(items: string[]): string {
  const shown = items.slice(0, 3);
  const rest = items.length - shown.length;
  const base = shown.join(', ');
  return rest > 0 ? `${base}, …and ${rest} more` : base;
}

/**
 * Classify ONE reported locator into a human-facing location + its exact
 * technical form. Total: never throws, whatever it is handed.
 */
export function classifyValidationPath(raw: unknown): ValidationLocation {
  const reported = typeof raw === 'string' ? raw : '';
  const trimmed = trim(reported);
  // Nothing usable was reported (absent key, null, a non-string, an empty or
  // whitespace-only value). Honest: no location is claimed and none is invented.
  if (trimmed === '') {
    return { kind: 'unknown', label: UNKNOWN_LOCATION_LABEL, technical: NO_PATH_TECHNICAL };
  }

  const technical = reported;
  const rootMarked = trimmed.startsWith(ROOT_MARKER);
  let body = rootMarked ? trimmed.slice(1) : trimmed;
  if (body.startsWith('.')) body = body.slice(1);
  body = trim(body);

  const segments = body
    .split('.')
    .map((s) => trim(s))
    .filter((s) => s !== '');

  if (segments.length === 0) {
    // A bare root marker (`$`, `$.`) — the case that produced the reported
    // defect. It is a RECORD-level location, not a field.
    if (rootMarked) return { kind: 'record', label: RECORD_LEVEL_LABEL, technical };
    // A reported-but-unusable locator (e.g. "."): keep the exact string for the
    // disclosure, but claim no location.
    return { kind: 'unknown', label: UNKNOWN_LOCATION_LABEL, technical };
  }

  if (segments.some((s) => s.includes(ROOT_MARKER))) {
    // A `$` that survived INSIDE a segment rather than as the leading root marker
    // (`$$`, `a.$.b`, `assets.$`, `$$$`). Only the LEADING marker is stripped
    // above, so this used to be emitted verbatim into the primary label — "1
    // validation issue may be blocking export: assets → $." — which is exactly the
    // raw-locator defect this module exists to prevent, and it falsified this
    // module's own documented invariant (P36V.1 review, M2). The honest answer is
    // that no location can be named; the exact string is still preserved for the
    // disclosure. Rejecting the whole GLYPH (not just a `$`-only segment) is what
    // makes `!label.includes('$')` hold universally, and it downgrades nothing
    // reachable: every locator `official.py` emits is `$` itself or a dot-join of
    // ISAAC-schema property names and array indices, and no property name in
    // `schema/isaac_record_v1.json` contains `$` or `.` (all 219 checked).
    return { kind: 'unknown', label: UNKNOWN_LOCATION_LABEL, technical };
  }

  return { kind: 'field', label: segments.join(SEGMENT_SEPARATOR), technical };
}

/** Classify every reported locator, order preserved (never deduplicated). */
export function classifyValidationPaths(raws: readonly unknown[]): ValidationLocation[] {
  return raws.map(classifyValidationPath);
}

/**
 * The EXACT technical locators, order preserved — the `Technical Details` payload.
 * This is the ONLY place a raw `$` is allowed to surface.
 */
export function technicalPaths(raws: readonly unknown[]): string[] {
  return classifyValidationPaths(raws).map((l) => l.technical);
}

/**
 * The primary, user-facing blocker sentence.
 *
 * · no locators            → `NO_BLOCKING_ISSUES`
 * · every locator is root  → "N record-level validation issues may be blocking export."
 * · otherwise              → "N validation issues may be blocking export: <≤3 locations>."
 *
 * It states a COUNT and WHERE — never a validity conclusion, never `validate.ok`,
 * and never a bare `$`.
 */
export function blockingSummary(raws: readonly unknown[]): string {
  const locations = classifyValidationPaths(raws);
  if (locations.length === 0) return NO_BLOCKING_ISSUES;
  if (locations.every((l) => l.kind === 'record')) {
    return `${count(locations.length, 'record-level validation issue')} may be blocking export.`;
  }
  const labels = joinCapped(locations.map((l) => l.label));
  return `${count(locations.length, 'validation issue')} may be blocking export: ${labels}.`;
}

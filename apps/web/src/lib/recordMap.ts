/*
 * THE RECORD MAP MODEL — what a run carries, what it does not, and what this
 * build cannot see. Pure functions only; no React, no fetch, no formatting of
 * anything it did not read.
 *
 * ── WHY IT IS A SEPARATE MODULE ────────────────────────────────────────────
 *
 * `RunSchemaMirror` used to compute its whole state ladder inline, which made
 * the one claim that matters — "not shown here", never "nothing yet", for a
 * block this payload cannot see — reachable only through a rendered component
 * and a stubbed `fetch`. The rule is worth a unit test of its own, so it lives
 * here and the component renders what this returns.
 *
 * ── THE STATE VOCABULARY, AND WHAT EACH WORD IS ALLOWED TO MEAN ────────────
 *
 *   filled       the RUN ITSELF carries a value at this path (`run.fields`)
 *   inherited    the run resolves this address from the RECORD (`run.inherited`)
 *   needsReview  a finding from the LAST CHECK on THIS run version names it
 *   missing      an OBSERVABLE path this run carries nothing at
 *   notShown     this payload cannot see the block at all — see below
 *
 * `notShown` is the load-bearing one and it is inherited verbatim from the
 * component this model was extracted from. `run.fields` is keyed by dotted
 * official path and holds THE FIVE RUN CONDITION FIELDS (`RUN_FIELDS`) and
 * nothing else. Measured over HTTP: after answering `qc` on a run, `run.fields`
 * was still `{}` and `inherited` carried only `block:attribution` — the qc,
 * series and descriptor answers live in the run's DRAFT, which the run-list
 * payload does not serve. So a block with no observable path says it cannot be
 * seen; saying "nothing yet" about `measurement` on a run whose spectrum and QC
 * verdict are recorded would be this product's signature defect.
 *
 * NOTHING HERE VALIDATES, and no state is a verdict. "Filled" means a key is
 * present with a non-null value — official validation is the only thing that
 * decides whether that value is right, and it runs at export.
 */

import { RUN_FIELDS, envelopeValue, type RunFieldSpec } from './runFields';
import type { ApiRunCheckFinding, ApiRunView } from './types';

export type RecordMapState = 'filled' | 'inherited' | 'needsReview' | 'missing' | 'notShown';

/**
 * The words on screen. Title Case, one per state, and every one of them is
 * rendered BESIDE a shape — never as a colour on its own.
 */
export const RECORD_MAP_STATE_LABEL: Record<RecordMapState, string> = {
  filled: 'Filled',
  inherited: 'Inherited',
  needsReview: 'Needs Review',
  missing: 'Missing',
  notShown: 'Not Shown Here',
};

/** One line in the map. A FIELD row addresses a path; a BLOCK row a schema block. */
export interface RecordMapRow {
  /** Dotted official path (field row) or a top-level block name (block row). */
  path: string;
  /** The human label. The path is shown too, demoted, never instead. */
  label: string;
  state: RecordMapState;
  /**
   * The run's own value as display text, or `null` when there is none to show.
   * A value is only ever present on a `filled` row: this model never reads a
   * value out of the record to show against a run, and never invents one.
   */
  value: string | null;
  /** The unit the schema's path name already encodes (`_K`). Display only. */
  unit?: string;
  /**
   * True only for the five paths `RUN_FIELDS` offers a control for — the ONE
   * condition under which a row may be a button that focuses an input. Every
   * other row is inert, and must not look otherwise.
   */
  editable: boolean;
  /**
   * When the state is `needsReview`, the finding text that says so — the
   * server's own words, verbatim. `null` in every other state.
   */
  reviewNote: string | null;
}

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const;

/**
 * A stored ISO-8601 date-time as something a person reads — or, unchanged, the
 * string that was stored.
 *
 * IT DOES NOT PARSE A DATE. There is no `Date` object anywhere in here, and
 * that is deliberate rather than frugal: `new Date(...)` would resolve an
 * offset against the reader's own zone, so `2026-01-31T09:00:00+02:00` would
 * render as a DIFFERENT CLOCK TIME than the one the scientist entered, and the
 * rendering would change with the machine it ran on. This reads the literal
 * components the string already carries and re-spells them.
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
 */
export function formatStoredDatetime(raw: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$/.exec(
    raw.trim(),
  );
  if (m === null) return raw;
  const [, year, month, day, hh, mm, zone] = m;
  const monthName = MONTHS[Number(month) - 1];
  if (monthName === undefined) return raw;
  const suffix = zone === undefined ? '' : zone === 'Z' ? ' UTC' : ` ${zone}`;
  return `${monthName} ${Number(day)}, ${year} · ${hh}:${mm}${suffix}`;
}

/**
 * One stored run-field value as display text.
 *
 * A `datetime` is re-spelled by {@link formatStoredDatetime} (which returns the
 * raw string whenever it cannot read it). Everything else is `String(value)`
 * and nothing more: no rounding, no unit appended into the text (the unit is a
 * separate field on the row), no casing, no vocabulary.
 */
export function runFieldDisplayValue(spec: RunFieldSpec, value: unknown): string {
  const text = String(value);
  return spec.kind === 'datetime' ? formatStoredDatetime(text) : text;
}

/**
 * Does any key of a `run.fields` / `run.inherited` bag address this block?
 *
 * Both namespaced (`block:attribution`, `field:sample.material.name`) and bare
 * dotted forms are admitted, because the two payloads key differently and this
 * model reads both.
 */
function bagTouchesBlock(bag: Record<string, unknown>, block: string): boolean {
  return Object.keys(bag).some(
    (key) =>
      key === block ||
      key.startsWith(`${block}.`) ||
      key === `block:${block}` ||
      key === `field:${block}` ||
      key.startsWith(`field:${block}.`),
  );
}

/** The `path` a finding names, or `null` when it names none. Never inferred. */
export function findingPath(finding: ApiRunCheckFinding): string | null {
  if (typeof finding !== 'object' || finding === null) return null;
  const path = finding.path;
  return typeof path === 'string' && path.trim() !== '' ? path.trim() : null;
}

/** The message a finding carries, verbatim, or `null`. Never composed. */
function findingMessage(finding: ApiRunCheckFinding): string | null {
  if (typeof finding === 'string') return finding.trim() || null;
  if (typeof finding !== 'object' || finding === null) return null;
  const text = finding.message;
  return typeof text === 'string' && text.trim() !== '' ? text.trim() : null;
}

/**
 * The findings a check produced, indexed by the path each one NAMES.
 *
 * A finding that names no path indexes nothing — it is not attributed to a row
 * by guesswork, and `FindingList` shows it in full regardless. A path is
 * matched EXACTLY: `timestamps` does not mark `timestamps.acquired_start_utc`,
 * because "the timestamps block has a problem" and "this field has a problem"
 * are different claims and only the server can tell them apart.
 */
export function findingsByPath(
  findings: readonly ApiRunCheckFinding[],
): Map<string, string> {
  const byPath = new Map<string, string>();
  for (const finding of findings) {
    const path = findingPath(finding);
    if (path === null || byPath.has(path)) continue;
    const message = findingMessage(finding);
    if (message === null) continue;
    byPath.set(path, message);
  }
  return byPath;
}

/**
 * What a check found, scoped to the run version it was taken on.
 *
 * `runVersion` is `ApiRunCheckResponse.checked_run_version`, and the caller is
 * expected to have compared it with the run's own `version` before passing it —
 * see `RunSchemaMirror`, which drops the whole thing when they differ rather
 * than marking a row from a read of a document that has since moved.
 */
export interface RecordMapCheck {
  runVersion: string;
  /** `draft.errors` + `official.errors` — the findings that carry a `path`. */
  errors: readonly ApiRunCheckFinding[];
}

/**
 * The five run-level field rows, in the order the editor offers them.
 *
 * ORDERING IS THE EDITOR'S, NOT A PRIORITY. Re-sorting by state would move a
 * row under the reader as they fill it in, and the map exists to be read
 * alongside the form rather than instead of it.
 */
export function runFieldRows(
  run: ApiRunView | null,
  check: RecordMapCheck | null,
): RecordMapRow[] {
  const byPath = check === null ? new Map<string, string>() : findingsByPath(check.errors);
  return RUN_FIELDS.map((spec) => {
    const value = run === null ? null : envelopeValue(run.fields?.[spec.path]);
    const note = byPath.get(spec.path) ?? null;
    const has = value !== null && value !== undefined;
    /*
     * A FINDING BEATS A VALUE, and that order is the whole point of the state.
     * A path that holds a value the validators objected to is exactly the row a
     * scientist needs to see, and reading `Filled` over it would be this
     * surface telling them the opposite of what the server just said.
     */
    const state: RecordMapState = note !== null ? 'needsReview' : has ? 'filled' : 'missing';
    return {
      path: spec.path,
      label: spec.label,
      state,
      value: has ? runFieldDisplayValue(spec, value) : null,
      unit: spec.unit,
      editable: true,
      reviewNote: note,
    };
  });
}

/**
 * One row per top-level schema block, for the blocks this payload can speak to.
 *
 * `blocks` is the caller's list (the component reads it off `GET /api/schema`,
 * so the names are the official document's own and not a transcription).
 * A block with no observable path is `notShown` — see this module's header.
 */
export function blockRows(
  blocks: readonly string[],
  run: ApiRunView | null,
): RecordMapRow[] {
  const own = (run?.fields ?? {}) as Record<string, unknown>;
  const inherited = (run?.inherited ?? {}) as Record<string, unknown>;
  const observable = new Set(RUN_FIELDS.map((spec) => spec.path.split('.')[0]));
  return blocks.map((block) => {
    const state: RecordMapState = bagTouchesBlock(own, block)
      ? 'filled'
      : bagTouchesBlock(inherited, block)
        ? 'inherited'
        : observable.has(block)
          ? 'missing'
          : 'notShown';
    return {
      path: block,
      label: block,
      state,
      // A BLOCK row never carries a value. `run.fields` is keyed by FIELD path
      // and `inherited` payloads are objects and lists; this surface has no
      // honest one-line rendering for either, and inventing a summary of a
      // scientist's data is exactly what this pane must not do.
      value: null,
      editable: false,
      reviewNote: null,
    };
  });
}

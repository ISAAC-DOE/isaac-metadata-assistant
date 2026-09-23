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

import { formatStoredDatetime } from './runDatetime';
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
/**
 * THE HUMAN NAME OF EACH TOP-LEVEL BLOCK (2026-09-22, owner QA R3).
 *
 * The map used to print the schema's own lowercase block names (`sample`,
 * `system`, `links`…) as row labels. These are the names the record screen already
 * gives the same blocks — `serialize._GROUP_TITLES` for the draft sections, and
 * the record-level panels for `links` (Relationships) and `assets` (Asset
 * References) — so a scientist meets one name per block across the product. The
 * schema's own name is still shown, behind the row's `?` and in the full-schema
 * listing, never removed.
 */
export const RECORD_MAP_BLOCK_LABEL: Readonly<Record<string, string>> = Object.freeze({
  measurement: 'Measurement',
  timestamps: 'Timestamps',
  descriptors: 'Descriptors',
  context: 'Environment & Context',
  sample: 'Sample',
  system: 'System & Instrument',
  attribution: 'Attribution',
  links: 'Relationships',
  assets: 'Asset References',
  tags: 'Tags',
});

export function recordMapBlockLabel(block: string): string {
  return RECORD_MAP_BLOCK_LABEL[block] ?? block;
}

/**
 * A HUMAN NAME FOR A DOTTED OFFICIAL PATH: the block's name, then the last
 * segment humanized exactly as the server humanizes a draft row
 * (`serialize._label`: underscores to spaces, title case). So
 * `sample.material.name` reads "Sample · Name" and `system.facility.site` reads
 * "System & Instrument · Site". A presentation of the path, never a claim about
 * what the field means — the path itself stays one `?` away.
 */
/*
 * THREE CORRECTIONS (review #277, I-9), each a presentation of the path and never a
 * claim about meaning:
 *  - a SINGLE-segment path is a block, so it reads as the block's own name —
 *    `context` is "Environment & Context", not "Context";
 *  - an INDEXED path keeps its index rather than naming the array's element by a
 *    number alone — `tags.0` reads "Tags · 0";
 *  - a GENERIC last word (`status`, `name`, `value` …) is prefixed with the segment
 *    it belongs to, and known acronyms keep their case — `measurement.qc.status`
 *    reads "Measurement · QC Status", not "Measurement · Status".
 */
const PATH_ACRONYMS: Readonly<Record<string, string>> = {
  qc: 'QC',
  utc: 'UTC',
  uri: 'URI',
  url: 'URL',
  id: 'ID',
  sha256: 'SHA-256',
  xanes: 'XANES',
  xas: 'XAS',
};
const GENERIC_LAST_SEGMENTS = new Set([
  'status',
  'name',
  'value',
  'values',
  'id',
  'type',
  'kind',
  'unit',
  'units',
  'basis',
  'label',
  'role',
]);

function humanizeSegment(segment: string): string {
  return segment
    .split('_')
    .filter((word) => word !== '')
    .map((word) => {
      const acronym = PATH_ACRONYMS[word.toLowerCase()];
      if (acronym !== undefined) return acronym;
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(' ');
}

function blockName(block: string): string {
  return block in RECORD_MAP_BLOCK_LABEL ? recordMapBlockLabel(block) : humanizeSegment(block);
}

export function fieldPathLabel(path: string): string {
  const parts = path.split('.').filter((part) => part !== '');
  if (parts.length === 0) return path;
  const block = parts[0];
  if (parts.length === 1) return blockName(block);
  const rest = parts.slice(1);
  const isIndex = (segment: string) => /^\d+$/.test(segment);
  let nameAt = -1;
  for (let i = rest.length - 1; i >= 0; i -= 1) {
    if (!isIndex(rest[i])) {
      nameAt = i;
      break;
    }
  }
  if (nameAt === -1) return `${blockName(block)} · ${rest.join(' · ')}`;
  let name = humanizeSegment(rest[nameAt]);
  if (GENERIC_LAST_SEGMENTS.has(rest[nameAt].toLowerCase())) {
    let parentAt = -1;
    for (let i = nameAt - 1; i >= 0; i -= 1) {
      if (!isIndex(rest[i])) {
        parentAt = i;
        break;
      }
    }
    if (parentAt !== -1 && rest[parentAt] !== block) {
      name = `${humanizeSegment(rest[parentAt])} ${name}`;
    }
  }
  const trailingIndex = rest.slice(nameAt + 1).filter(isIndex);
  return trailingIndex.length > 0
    ? `${blockName(block)} · ${name} · ${trailingIndex.join(' · ')}`
    : `${blockName(block)} · ${name}`;
}

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

/**
 * The `path` a finding names, or `null` when it names none. Never inferred.
 *
 * `$` IS NOT A PATH. It is `official.py:98`'s sentinel for an error with an
 * EMPTY `absolute_path` — a whole-document finding — and `routes.py` writes it
 * at seven sites for a fail-closed no-verdict. Indexing it would change no
 * outcome here (no row is addressed `$`), and it is excluded anyway so that
 * this reader and `findingPresentation`'s agree on what a path IS rather than
 * agreeing by coincidence. See that module's `ROOT_PATH` for the measurement
 * that prompted it.
 */
export function findingPath(finding: ApiRunCheckFinding): string | null {
  if (typeof finding !== 'object' || finding === null) return null;
  const path = finding.path;
  if (typeof path !== 'string') return null;
  const trimmed = path.trim();
  return trimmed !== '' && trimmed !== '$' ? trimmed : null;
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
      label: recordMapBlockLabel(block),
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

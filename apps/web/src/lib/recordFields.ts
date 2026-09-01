/*
 * THE RECORD-LEVEL FIELDS AND BLOCKS THE RECORD SCREEN CAN CAPTURE.
 *
 * WHAT WAS MISSING. A scientist creating a record in-product could not enter a
 * facility, a sample or a contributor ON THE RECORD by any request. The twelve
 * facility/sample paths were accepted at exactly one route — a RUN's override, which
 * records a divergence from a value the record does not hold — and `system.domain` /
 * `system.technique` had a record-level route that NO screen reached. This module is
 * the client half of closing that.
 *
 * ── TWO SOURCES, AND EXACTLY ONE OF THEM IS TRANSCRIBED ──────────────────────
 *
 * 1. WHICH PATHS ARE OFFERED is declared below, as `RECORD_FIELDS`. It has to be:
 *    the answer depends on `workspace.field_level`'s EXPERIMENT/RUN classification,
 *    which is a decision this repository makes and the official schema does not
 *    express, so no amount of reading the schema would produce it. The drift that
 *    invites is closed the way this repository already closes it for the run
 *    workspace: `apps/api/tests/test_record_campaign_fields.py` parses THIS FILE and
 *    asserts the declared set equals what the two record-level write operations
 *    actually accept. A path the server accepts and this file omits is an unreachable
 *    field; a path this file offers and the server refuses is a control whose only
 *    outcome is a 422. Both are failures, so the assertion is set EQUALITY.
 *
 * 2. EVERYTHING ELSE ABOUT A FIELD IS READ FROM THE VENDORED SCHEMA AT RUNTIME —
 *    its declared JSON type, whether it is closed with an enum, and which values that
 *    enum admits — through `GET /api/schema`, the existing read-only route that
 *    serves the same document `official.py` validates against. **NOTHING here
 *    transcribes an enum.** `system.technique` has 37 values; a copy of them in
 *    TypeScript would be a second expression of the schema's vocabulary, free to drift
 *    from the document `CLAUDE.md` §1 makes the authority, and it would go stale
 *    silently on a schema refresh. `contributorRoleOptions` reads the four contributor
 *    roles the same way.
 *
 * ── WHAT THIS MODULE DELIBERATELY DOES NOT DO ────────────────────────────────
 *
 * IT NEVER VALIDATES. `recordFieldFacts` reports what the schema DECLARES; the server
 * decides whether a value is acceptable, and its refusal is what the panel renders.
 * The one thing done client-side is turning a typed string into a value of the
 * declared type, and where the schema declares NO type nothing is converted at all —
 * see `parseRecordField`.
 *
 * IT NEVER INVENTS A TYPE. Three of the offered paths sit under namespaces the
 * official schema declares OPEN BY DESIGN in its own descriptions
 * (`sample.composition`, `sample.geometry`), so it declares no type for them. A
 * number-looking name is not a declaration, and `CLAUDE.md` §5 forbids this
 * application deciding what the schema declined to say — so those are plain text
 * boxes whose content is sent verbatim, and the panel says so rather than quietly
 * coercing.
 */

import type { ApiDraftResponse, JsonSchemaNode } from './types';

/** Which section of the panel a field belongs to. Presentation only. */
export type RecordFieldGroupId = 'classification' | 'facility' | 'sample' | 'other';

export interface RecordFieldSpec {
  /** The dotted OFFICIAL path, sent verbatim as the answer key. */
  path: string;
  /** The human label. The path is shown too, demoted, never instead. */
  label: string;
  group: RecordFieldGroupId;
}

export const RECORD_FIELD_GROUPS: readonly { id: RecordFieldGroupId; title: string }[] = [
  { id: 'classification', title: 'Classification' },
  { id: 'facility', title: 'Facility' },
  { id: 'sample', title: 'Sample' },
  /*
   * WHERE A PATH THE SERVER ACCEPTS AND THIS FILE DOES NOT DECLARE IS RENDERED.
   *
   * It exists so that widening the server's record-level write surface cannot make a
   * field UNREACHABLE while this file is being updated to name it. Empty today, and the
   * panel renders no fieldset for a group with no fields, so a reader sees it only when
   * the server has genuinely widened past what `RECORD_FIELDS` describes — which is
   * exactly when they should.
   */
  { id: 'other', title: 'Other record-level values' },
];

export const RECORD_FIELDS: readonly RecordFieldSpec[] = [
  { path: 'system.domain', label: 'Domain', group: 'classification' },
  { path: 'system.technique', label: 'Technique', group: 'classification' },
  { path: 'system.facility.site', label: 'Site', group: 'facility' },
  { path: 'system.facility.facility_name', label: 'Facility name', group: 'facility' },
  { path: 'system.facility.organization', label: 'Organization', group: 'facility' },
  { path: 'system.facility.beamline', label: 'Beamline', group: 'facility' },
  { path: 'system.facility.endstation', label: 'Endstation', group: 'facility' },
  { path: 'sample.material.name', label: 'Material name', group: 'sample' },
  { path: 'sample.material.formula', label: 'Formula', group: 'sample' },
  { path: 'sample.material.provenance', label: 'Provenance', group: 'sample' },
  { path: 'sample.sample_form', label: 'Sample form', group: 'sample' },
  {
    path: 'sample.composition.CuO2_mass_fraction',
    label: 'CuO₂ mass fraction',
    group: 'sample',
  },
  {
    path: 'sample.composition.sucrose_mass_fraction',
    label: 'Sucrose mass fraction',
    group: 'sample',
  },
  {
    path: 'sample.geometry.pellet_diameter_mm',
    label: 'Pellet diameter (mm)',
    group: 'sample',
  },
] as const;

/* ── THE INVENTORY IS DERIVED FROM THE SERVED CONTRACT ─────────────────────────
 *
 * WHAT `RECORD_FIELDS` ABOVE IS, AND IS NOT, AS OF THIS SLICE. It is PRESENTATION —
 * a human label and a section — for the paths this build expects. It is **no longer
 * the inventory**. The inventory is whatever `GET /api/experiments/{id}/draft` reports
 * as record-writable, and the four functions below are the whole of that derivation.
 *
 * WHY IT HAD TO CHANGE. `RECORD_FIELDS` was the inventory, and its only guard against
 * going stale was `apps/api/tests/test_record_campaign_fields.py` — a PYTHON test that
 * regex-parses this TypeScript file and compares the literal to
 * `routes._record_writable_fields()`. That guard is real, it is good, and it caught the
 * defect it was written for; it is also in the other suite, so a frontend author running
 * `vitest` alone gets a green run over a stale list. Worse, a stale list fails in the
 * direction that hurts: a path the server accepts and this file omits is a field a
 * scientist has no way to reach, and nothing in the running product says so.
 *
 * WHAT THE SERVED CONTRACT IS, PRECISELY, AND WHY IT IS THIS ONE.
 * `GET .../draft` returns `capture.record_writable` on EVERY field row — the server's
 * own per-path answer, computed in `routes.capture_facts` from
 * `_record_writable_fields()`, which is the identical expression the two record-level
 * write operations gate on. It is already in a payload this panel fetches.
 *
 * IT IS DELIBERATELY **NOT** `record_writable_field_paths`, which is the other served
 * key naming this capability, and the difference is measurable rather than stylistic:
 * that key (on `GET .../notes`) is `NOTE_MAPPABLE_PATHS_WRITABLE_ON_THE_RECORD`, the
 * INTERSECTION with the paths a note can be mapped to, and it holds **13** paths where
 * the write routes accept **14**. The one it drops is `system.domain`, which is absent
 * from `EXTRACTOR_FIELD_MAP` and so is not a note's target — but IS record-writable, and
 * IS one of the two closed enums this panel offers a picker for. Deriving from that key
 * would have silently removed a working control. Two served keys answer "which paths are
 * the record's" differently on purpose; a surface must pick the one whose question
 * matches its own.
 *
 * FAIL-CLOSED, IN THE DIRECTION THE SERVER ALREADY CHOSE. `_record_writable_fields()`
 * returns an EMPTY mapping when the vendored schema cannot be read, so every write is
 * then refused as `unrecognized_field` and every `record_writable` arrives `false`. The
 * derivation follows it to zero fields, and the panel says so in words — which is
 * correct: offering a box whose only outcome is a 422 is the defect `CLAUDE.md` §11
 * records as *"a panel told the scientist to enter a value on 25 fields, and 7 accept
 * none"*.
 *
 * "SAID FALSE" AND "SAID NOTHING" ARE DIFFERENT, and only the first is a classification.
 * A draft whose rows carry NO `capture` object at all is a server that has not spoken
 * this contract, not a server reporting that nothing is writable — the same distinction
 * `serialize._UNKNOWN_CAPTURE` draws with `level: null`. In that case the derivation
 * falls back to the declared list and the panel DISCLOSES that it is doing so, rather
 * than either offering nothing or claiming server backing it does not have.
 */

/** The presentation for a served path this file does not declare. Formatting only. */
export function derivedRecordFieldSpec(path: string): RecordFieldSpec {
  const last = path.split('.').pop() ?? path;
  const words = last.replace(/_/g, ' ').trim();
  return {
    path,
    /*
     * THE PATH, RE-SPACED — NOT A MEANING. `sample.material.purity` becomes "Purity"
     * because that is what the last segment says; nothing is looked up, expanded or
     * interpreted, and the full dotted path is rendered beside every box anyway. A
     * label invented from anywhere else would be this client describing a field the
     * schema describes.
     */
    label: words === '' ? path : words.charAt(0).toUpperCase() + words.slice(1),
    group: path.startsWith('system.facility.')
      ? 'facility'
      : path.startsWith('sample.')
        ? 'sample'
        : path.startsWith('system.')
          ? 'classification'
          : 'other',
  };
}

/** What the served draft says about where a record-level value may be entered. */
export interface ServedRecordWritable {
  /** The paths the server reports a RECORD-level operation accepts a value at. */
  paths: readonly string[];
  /**
   * Whether the server answered the question at all.
   *
   * `false` means no row carried a `capture` object — the server did not speak this
   * contract. It is NOT the same as an empty `paths` with `reported: true`, which is
   * the server saying it accepts a value nowhere.
   */
  reported: boolean;
}

/** Read the served contract off a draft response. Reads only; decides nothing. */
export function servedRecordWritablePaths(
  draft: ApiDraftResponse | null | undefined,
): ServedRecordWritable {
  const paths: string[] = [];
  let reported = false;
  for (const group of draft?.groups ?? []) {
    for (const field of group?.fields ?? []) {
      const capture = field?.capture;
      if (capture === undefined || capture === null) continue;
      reported = true;
      if (capture.record_writable === true) paths.push(field.path);
    }
  }
  return { paths: [...new Set(paths)].sort(), reported };
}

/** The offered inventory: which boxes this panel may render, and on whose authority. */
export interface OfferedRecordFields {
  fields: readonly RecordFieldSpec[];
  /** `true` when the set came from the server; `false` when it is the declared fallback. */
  served: boolean;
}

/**
 * The paths the panel offers, in a stable order, derived from the served draft.
 *
 * ORDER: the declared paths the server confirms, in `RECORD_FIELDS` order (so the
 * familiar screen does not reshuffle), then any path the server accepts that this file
 * does not declare, sorted, with a derived label. A declared path the server does NOT
 * report is dropped — a control the routes would refuse is worse than an absent one.
 */
export function offeredRecordFields(
  draft: ApiDraftResponse | null | undefined,
): OfferedRecordFields {
  const served = servedRecordWritablePaths(draft);
  if (!served.reported) return { fields: RECORD_FIELDS, served: false };
  const accepted = new Set(served.paths);
  const declared = RECORD_FIELDS.filter((spec) => accepted.has(spec.path));
  const known = new Set(declared.map((spec) => spec.path));
  const extra = served.paths.filter((path) => !known.has(path)).map(derivedRecordFieldSpec);
  return { fields: [...declared, ...extra], served: true };
}

/** The two record-level BLOCK addresses, spelt exactly as the write operations take them. */
export const RECORD_ATTRIBUTION_ADDRESS = 'block:attribution';
export const RECORD_TAGS_ADDRESS = 'block:tags';

/** What the vendored schema DECLARES about one path. Never what this app decided. */
export interface RecordFieldFacts {
  /** The declared JSON type, or `null` where the schema declares none. */
  declaredType: string | null;
  /** The values the schema admits, or `null` where it closes the field with no list. */
  allowed: readonly string[] | null;
}

const NO_FACTS: RecordFieldFacts = { declaredType: null, allowed: null };

function resolve(schema: JsonSchemaNode | null | undefined, path: string): JsonSchemaNode | null {
  let node: JsonSchemaNode | undefined = schema ?? undefined;
  for (const segment of path.split('.')) {
    const properties = node?.properties;
    if (!properties || !Object.prototype.hasOwnProperty.call(properties, segment)) return null;
    node = properties[segment];
  }
  return node ?? null;
}

/**
 * What the schema says about one offered path — type and enum, or two nulls.
 *
 * TWO NULLS IS A REAL ANSWER AND NOT AN ERROR. It is what the schema returns for the
 * three paths under its own open-by-design namespaces, and it is also what this
 * returns when the schema could not be loaded at all. The panel distinguishes those
 * two by whether it HAS a schema, and says the honest thing in each case: an open
 * namespace gets a plain text box, and a failed load gets a stated inability to offer
 * the closed-list controls rather than a free-text box standing in for a picker.
 */
export function recordFieldFacts(
  schema: JsonSchemaNode | null | undefined,
  path: string,
): RecordFieldFacts {
  const node = resolve(schema, path);
  if (node === null) return NO_FACTS;
  const declaredType = typeof node.type === 'string' ? node.type : null;
  const allowed = Array.isArray(node.enum)
    ? node.enum.filter((v): v is string => typeof v === 'string')
    : null;
  return { declaredType, allowed: allowed && allowed.length > 0 ? allowed : null };
}

/**
 * The contributor roles the official schema admits, or `null` when it could not say.
 *
 * READ, NOT LISTED, for the reason the technique enum is: it is the schema's own
 * vocabulary. `null` means the panel offers no role picker and says why — it never
 * falls back to a free-text role, because a role outside the schema's list produces a
 * contributor an exported record cannot hold.
 */
export function contributorRoleOptions(
  schema: JsonSchemaNode | null | undefined,
): readonly string[] | null {
  const role = schema?.properties?.attribution?.properties?.contributors?.items?.properties
    ?.role;
  const values = Array.isArray(role?.enum)
    ? role.enum.filter((v): v is string => typeof v === 'string')
    : [];
  return values.length > 0 ? values : null;
}

/** The result of turning one raw input string into something sendable. */
export type ParsedRecordField =
  | { ok: true; value: unknown }
  | { ok: false; error: string };

/**
 * Raw input text -> the value to send, or a typed refusal to send it.
 *
 * AN EMPTY BOX IS "NO CHANGE", NOT "CLEAR". The record-level write operations
 * deliberately do not build clearing — un-saying a confirmed record-level value is a
 * real operation with its own questions (what it means for a run that inherited it),
 * and the server drops a blank rather than removing the field. So the panel never
 * sends a blank, and a reader is told that emptying a box does not erase the stored
 * value rather than being allowed to believe it did.
 *
 * WHERE THE SCHEMA DECLARES NO TYPE, NOTHING IS CONVERTED. The typed string is sent
 * verbatim. That is the honest reading of an open-by-design namespace: coercing
 * `"0.5"` to `0.5` at a path the schema never typed would be this client deciding
 * what the document declined to say.
 */
export function parseRecordField(facts: RecordFieldFacts, raw: string): ParsedRecordField {
  const text = raw.trim();
  if (text === '') return { ok: true, value: null };
  if (facts.declaredType === 'number' || facts.declaredType === 'integer') {
    const n = Number(text);
    if (!Number.isFinite(n)) return { ok: false, error: 'Enter a number.' };
    if (facts.declaredType === 'integer' && !Number.isInteger(n)) {
      return { ok: false, error: 'Enter a whole number.' };
    }
    return { ok: true, value: n };
  }
  if (facts.allowed && !facts.allowed.includes(text)) {
    return { ok: false, error: 'Choose one of the values the official schema allows.' };
  }
  return { ok: true, value: text };
}

/** One contributor row as the panel edits it. `name`/`role` are what the schema requires. */
export interface ContributorRow {
  name: string;
  role: string;
}

/**
 * The stored `attribution` payload, read as rows the panel can edit.
 *
 * READ TOLERANTLY, WRITTEN STRICTLY. A persisted block of any shape is handed back by
 * the server rather than refused (a reader did nothing to deserve a record that
 * vanishes), so this reads what it can and reports what it could not: an entry that is
 * not an object, or whose `name`/`role` are not strings, is COUNTED as unreadable
 * rather than silently dropped — a contributor list that quietly shrinks is the one
 * thing this panel must never do.
 */
export function contributorRows(payload: unknown): {
  rows: ContributorRow[];
  unreadable: number;
} {
  if (typeof payload !== 'object' || payload === null) {
    return { rows: [], unreadable: payload === undefined || payload === null ? 0 : 1 };
  }
  const list = (payload as { contributors?: unknown }).contributors;
  if (list === undefined || list === null) return { rows: [], unreadable: 0 };
  if (!Array.isArray(list)) return { rows: [], unreadable: 1 };
  const rows: ContributorRow[] = [];
  let unreadable = 0;
  for (const entry of list) {
    if (typeof entry !== 'object' || entry === null) {
      unreadable += 1;
      continue;
    }
    const { name, role } = entry as { name?: unknown; role?: unknown };
    if (typeof name !== 'string' || typeof role !== 'string') {
      unreadable += 1;
      continue;
    }
    rows.push({ name, role });
  }
  return { rows, unreadable };
}

/** The stored `tags` payload, read as strings, with what could not be read counted. */
export function tagRows(payload: unknown): { rows: string[]; unreadable: number } {
  if (payload === undefined || payload === null) return { rows: [], unreadable: 0 };
  if (!Array.isArray(payload)) return { rows: [], unreadable: 1 };
  const rows: string[] = [];
  let unreadable = 0;
  for (const entry of payload) {
    if (typeof entry === 'string') rows.push(entry);
    else unreadable += 1;
  }
  return { rows, unreadable };
}

/**
 * Does the record already hold a value here? Decides `/answers` vs `/edit`.
 *
 * THE SERVER DRAWS THIS LINE AND REFUSES THE WRONG SIDE OF IT: answering a confirmed
 * field is `422 already_answered`, correcting an unanswered one is `422
 * not_yet_answered`. So the panel has to route each key, and it routes on the value it
 * READ from the server rather than on anything it remembers — a value the panel wrote
 * in an earlier save is re-read before the next one.
 *
 * `null` and `undefined` are both "holds nothing". A field whose stored value is
 * literally `null` is not a confirmed value: the server's own predicate requires a
 * non-null value and a status other than `missing`.
 */
export function holdsAValue(current: unknown): boolean {
  return current !== null && current !== undefined && current !== '';
}

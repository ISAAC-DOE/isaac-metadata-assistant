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

import type { JsonSchemaNode } from './types';

/** Which section of the panel a field belongs to. Presentation only. */
export type RecordFieldGroupId = 'classification' | 'facility' | 'sample';

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

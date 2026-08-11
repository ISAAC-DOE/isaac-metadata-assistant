/*
 * THE RECORD'S OWN IDENTITY — the top-level values that describe the RECORD
 * rather than the science in it — and the `links` block, which is the one part
 * of an official record that is not a dotted field at all.
 *
 * ─── WHY THIS FILE EXISTS, AND WHAT IT IS NOT ────────────────────────────────
 *
 * IT IS NOT A SECOND GROUPING ENGINE. `apps/api/isaac_api/serialize.py`
 * (`draft_to_groups` / `_GROUP_TITLES`) is the only one, it buckets a draft's
 * DOTTED `fields` map by top-level segment into the eight stable sections plus
 * `Other`, and the record screen renders its output verbatim through
 * `adapt.draftGroupsToFieldGroups` → `FieldGroup`. Nothing here re-groups
 * anything, and nothing here reads a draft field except ONE lookup
 * (`timestamps.created_utc`, below) which asks the groups what they already
 * carry.
 *
 * The gap it fills is the one that grouping engine structurally cannot: it
 * groups `draft["fields"]`, and every value below lives somewhere else —
 * `record_type` / `record_domain` / `source_type` are in the draft's `meta`
 * block, `isaac_record_version` and `record_id` are written by the exporter, and
 * `links` is a top-level ARRAY OF OBJECTS. None of them is a dotted field, so
 * none of them has ever appeared in a section, and a scientist had no surface
 * that named them at all.
 *
 * ─── HOW THE FIELD LIST WAS DETERMINED (measured, not chosen) ────────────────
 *
 * `schema/isaac_record_v1.json` is the authority (CLAUDE.md §1). Read from the
 * vendored file:
 *
 *   $.required                     == ["isaac_record_version", "record_id",
 *                                       "record_type", "record_domain",
 *                                       "source_type", "timestamps"]
 *   $.properties.timestamps.required == ["created_utc"]
 *
 * So the closed set is those five top-level scalars plus the one required
 * member of the one required object — SIX addresses, and not one more. Nothing
 * optional is here: `tags`, `computation`, `attribution` and the rest are either
 * already inside a rendered section or are out of this slice's scope.
 *
 * Each `description` below is TRANSCRIBED from that schema file, verbatim,
 * including its absence — `isaac_record_version` and `timestamps.created_utc`
 * carry no `description` in the schema and therefore carry none here. This file
 * never writes a definition the schema did not.
 *
 * ─── WHERE EACH VALUE COMES FROM, AND WHY MOST ROWS SAY "NOT ENTERED HERE" ───
 *
 * `src/isaac_records/export.py::transform` is the only writer:
 *
 *   * `isaac_record_version` — the module constant `ISAAC_VERSION`, unconditional.
 *     The schema declares the property as `{"type": "string", "const": "1.05"}`,
 *     so there is exactly one legal value and no one is asked for it.
 *   * `record_id`            — `record_id or new_record_id()`: a ULID, minted at
 *     export unless the caller supplies one.
 *   * the classification trio — `meta[key]`, copied only `if meta.get(key) is not
 *     None`. `experiment_repository.blank_draft` sets `meta` from
 *     `isaac_records.extract.draft_builder._META`, a STORED RULE: this build
 *     supports one path (evidence · characterization · facility) and stamps it on
 *     every draft, so the trio is derived rather than entered.
 *   * `timestamps.created_utc` — `record["timestamps"].setdefault("created_utc",
 *     now)`. `docs/run-scope-decision-packet.md` §3 settles the semantics on
 *     evidence: it is *"a record-creation stamp, not an inherited scientific
 *     value"*, the schema makes it required, and the exporter already supplies
 *     it. It is presented as a stamp here, and no control offers to edit it.
 *
 * WHAT THIS SCREEN CAN ACTUALLY SEE. Only `GET /api/experiments/{id}/artifacts`
 * serves an official record's own top-level values, and it serves them only once
 * the record exists. No route serves the draft's `meta` block — verified by
 * search: `record_type`, `record_domain` and `source_type` appear nowhere in
 * `apps/api/isaac_api/serialize.py` and nowhere in `routes.py` outside the
 * unrelated `by_record_type` aggregate. So before export those three rows say
 * they are not read here, which is a statement about THIS SCREEN. They do not
 * say the value is missing, because that would be a claim about the record and
 * this code has no basis for it (CLAUDE.md §5).
 *
 * ─── LINKS ──────────────────────────────────────────────────────────────────
 *
 * `$.properties.links` is `{"type": "array", "items": {...}}` with
 * `required: ["rel", "target", "basis"]`, `additionalProperties: false`, closed
 * enums on `rel` (8 members) and `basis` (12), a free-text `notes`, and
 * `target: {"type": "string", "pattern": "^[0-9A-Z]{26}$"}` — the SAME pattern
 * `record_id` carries. Both enums below are transcribed from that file. This
 * file never invents a relation name, and where the schema leaves something open
 * (`notes`) it fabricates no closed list for it.
 */

import type {
  ApiArtifactsResponse,
  ApiDraftGroup,
  ApiExperimentDetail,
  ApiExperimentSummary,
} from './types';

/* ────────────────────────── record ids ────────────────────────────────────── */

/**
 * The record-id shape, as the truth core defines it.
 *
 * THIS IS THE TYPESCRIPT MIRROR OF `src/isaac_records/ids.py::RECORD_ID_RE`, and
 * it is written as one shared constant precisely so a third spelling does not
 * grow. That module's `RECORD_ID_RE` is `\A[0-9A-Z]{26}\Z` rather than the
 * schema's `^[0-9A-Z]{26}$` because Python's `$` also matches immediately before
 * a trailing newline, so the schema's own pattern accepts `"A"*26 + "\n"`.
 *
 * JavaScript does NOT share that hole: without the `m` flag, `$` matches at the
 * end of input and nowhere else, so `^…$` here is already exact and is
 * equivalent to Python's `\A…\Z`. That equivalence is not left to a reader's
 * memory — `__tests__/record-identity.test.ts` pins the trailing-newline case.
 *
 * IT IS DELIBERATELY NOT `portalMetricsContract.ULID_PATTERN`. That one is
 * `\b[0-9A-HJKMNP-TV-Z]{26}\b` — unanchored, and Crockford-restricted so it
 * EXCLUDES `I`, `L`, `O` and `U`. It exists to spot a leaked id inside arbitrary
 * text, where a false negative is the dangerous direction. Reusing it here would
 * reject a target the official schema accepts, and this file must not be
 * stricter than the schema it reports on.
 */
export const RECORD_ID_PATTERN = /^[0-9A-Z]{26}$/;

/** Whether `value` is a record id in exactly the shape the schema declares. */
export function isRecordId(value: unknown): value is string {
  return typeof value === 'string' && RECORD_ID_PATTERN.test(value);
}

/* ───────────────────── the six top-level addresses ────────────────────────── */

/**
 * Where the value on a row came from. A CLOSED set — every member is rendered
 * through an explicit lookup with a stated fallback, never a direct index (see
 * `RecordInfoPanel`), because a map miss on a direct index renders
 * `undefined.label` and blanks the screen.
 */
export type RecordInfoSource =
  /** Read out of the exported official record. */
  | 'from_record'
  /** The record exists and does NOT carry this value. A statement about the file. */
  | 'missing_from_record'
  /** Carried on the draft, and the exporter will keep it. */
  | 'from_draft'
  /** Not written yet; the exporter supplies it when the record is written. */
  | 'written_at_export'
  /** Real, but this screen does not read it before export. Not a claim of absence. */
  | 'not_read_here'
  /** This experiment's runs each export their own record, so there is no single value. */
  | 'no_single_value';

export interface RecordInfoSpec {
  /** The official dotted path, shown demoted beside the label. */
  path: string;
  label: string;
  /** The schema's OWN description, verbatim. Empty when the schema gives none. */
  description: string;
  /** Where the value comes from when no exported record is readable. */
  beforeExport: RecordInfoSource;
  /** Why it is not on screen yet / how it is produced. Never a value. */
  beforeExportNote: string;
  /** True for a value the exporter owns outright — rendered as a stamp. */
  stamp?: boolean;
}

export const RECORD_INFO_SPECS: readonly RecordInfoSpec[] = [
  {
    path: 'isaac_record_version',
    label: 'ISAAC record version',
    description: '',
    beforeExport: 'written_at_export',
    beforeExportNote:
      'The exporter writes the one version the vendored schema fixes for every record. Nobody is asked for it.',
    stamp: true,
  },
  {
    path: 'record_id',
    label: 'Record identifier',
    // schema/isaac_record_v1.json → properties.record_id.description
    description: 'ULID identifier for the record.',
    beforeExport: 'written_at_export',
    beforeExportNote: 'The exporter mints this when the record is written.',
    stamp: true,
  },
  {
    path: 'record_type',
    // schema/isaac_record_v1.json → properties.record_type.description
    description: 'Fundamental nature of the record.',
    label: 'Record type',
    beforeExport: 'not_read_here',
    beforeExportNote:
      'Derived by a stored rule — this build supports one path and stamps the same classification on every draft. This screen reads it from the exported record, so it is shown once the record is written.',
  },
  {
    path: 'record_domain',
    label: 'Record domain',
    // schema/isaac_record_v1.json → properties.record_domain.description
    description: 'Scientific domain of the record content.',
    beforeExport: 'not_read_here',
    beforeExportNote:
      'Derived by the same stored rule as the record type, and read from the exported record.',
  },
  {
    path: 'source_type',
    label: 'Source type',
    // schema/isaac_record_v1.json → properties.source_type.description
    description: 'Origin of the data acquisition.',
    beforeExport: 'not_read_here',
    beforeExportNote:
      'Derived by the same stored rule as the record type, and read from the exported record.',
  },
  {
    path: 'timestamps.created_utc',
    label: 'Record created',
    description: '',
    beforeExport: 'written_at_export',
    beforeExportNote:
      'A record-creation stamp, not a measurement time. The exporter stamps it when the record is written.',
    stamp: true,
  },
] as const;

export interface RecordInfoRow extends RecordInfoSpec {
  /** The value as text, or `null` when this screen has none to show. */
  value: string | null;
  source: RecordInfoSource;
  /** The sentence under the row. Derived from the state, never from the value. */
  note: string;
}

/** The draft field path this panel reads from the already-fetched groups. */
const CREATED_UTC_PATH = 'timestamps.created_utc';

/**
 * `record[path]` for a dotted path, when it is a JSON scalar. Otherwise `null`.
 *
 * Objects and arrays return `null` rather than `[object Object]`: a required
 * top-level scalar holding a container is a record this reader cannot describe,
 * and saying "not present in the exported record" about it is closer to true
 * than printing a shape.
 */
function readScalar(record: Record<string, unknown> | null, path: string): string | null {
  if (record === null) return null;
  let cursor: unknown = record;
  for (const segment of path.split('.')) {
    if (cursor === null || typeof cursor !== 'object' || Array.isArray(cursor)) return null;
    cursor = (cursor as Record<string, unknown>)[segment];
  }
  if (typeof cursor === 'string') return cursor === '' ? null : cursor;
  if (typeof cursor === 'number' || typeof cursor === 'boolean') return String(cursor);
  return null;
}

/** The draft's own `timestamps.created_utc`, if the groups already carry one. */
function createdUtcOnDraft(groups: readonly ApiDraftGroup[]): string | null {
  for (const group of groups) {
    for (const field of group.fields) {
      if (field.path !== CREATED_UTC_PATH) continue;
      if (field.status === 'missing' || field.status === 'rejected') continue;
      if (typeof field.value === 'string' && field.value !== '') return field.value;
    }
  }
  return null;
}

export interface RecordInfoInput {
  detail: ApiExperimentDetail;
  groups: readonly ApiDraftGroup[];
  artifacts: ApiArtifactsResponse;
}

/**
 * The six rows, each with the ONE state this app can actually justify.
 *
 * Precedence, and every branch is a different claim:
 *
 *  1. An exported record is readable → the value is read out of it, or the row
 *     says the record does not carry it. Both are statements about a file that
 *     exists.
 *  2. No readable record, but `artifact_refs.reason` is present → this
 *     experiment's runs each exported their own record, so there is no single
 *     value. The server's own sentence is shown verbatim rather than reworded.
 *  3. Otherwise the spec's own `beforeExport` state applies, with one exception:
 *     `timestamps.created_utc` is shown from the DRAFT when the draft carries
 *     one, because then the exporter's `setdefault` will keep that value rather
 *     than stamping the export time.
 */
export function recordInfoRows(input: RecordInfoInput): RecordInfoRow[] {
  const { detail, groups, artifacts } = input;
  const record = artifacts.record;
  const fanOutReason = detail.artifact_refs.reason;

  return RECORD_INFO_SPECS.map((spec): RecordInfoRow => {
    if (record !== null) {
      const value = readScalar(record, spec.path);
      if (value !== null) {
        return {
          ...spec,
          value,
          source: 'from_record',
          note: spec.stamp
            ? 'Written by the exporter into the official record. It is not entered here.'
            : 'Read from the exported record.',
        };
      }
      return {
        ...spec,
        value: null,
        source: 'missing_from_record',
        note: 'The exported record does not carry this value. The official schema requires it, so the schema check is where that is decided — this panel only reports what the file holds.',
      };
    }

    if (typeof fanOutReason === 'string' && fanOutReason !== '') {
      return { ...spec, value: null, source: 'no_single_value', note: fanOutReason };
    }

    if (spec.path === CREATED_UTC_PATH) {
      const drafted = createdUtcOnDraft(groups);
      if (drafted !== null) {
        return {
          ...spec,
          value: drafted,
          source: 'from_draft',
          note: 'Carried on the draft. The exporter keeps a value the draft already holds, and stamps the export time only when it holds none.',
        };
      }
    }

    return { ...spec, value: null, source: spec.beforeExport, note: spec.beforeExportNote };
  });
}

/* ────────────────────────────── links ─────────────────────────────────────── */

/**
 * The eight relations the official schema defines, transcribed from
 * `schema/isaac_record_v1.json` → `properties.links.items.properties.rel.enum`.
 * The schema is the authority; nothing is added to this list here.
 */
export const LINK_RELATIONS: readonly string[] = [
  'derived_from',
  'intended_comparison_target',
  'calibration_of',
  'same_sample_as',
  'replica_of',
  'follows',
  'validates',
  'invalidates',
];

/**
 * The twelve bases, transcribed from
 * `schema/isaac_record_v1.json` → `properties.links.items.properties.basis.enum`.
 */
export const LINK_BASES: readonly string[] = [
  'same_absorber_edge',
  'matched_operating_conditions',
  'matched_computational_method',
  'shared_reference_state',
  'same_workflow_version',
  'identical_geometry',
  'analysis_pipeline_output',
  'replicate_preparation',
  'same_sample_id',
  'shared_analysis_method',
  'shared_material_batch',
  'unspecified',
];

/** One enum-valued member of a link, as it actually arrived. */
export interface LinkTerm {
  /** The stored token, verbatim, or `null` when the link carries none. */
  token: string | null;
  /** The token with underscores opened up. Mechanical — never a rename. */
  text: string | null;
  /** Whether the token is one the schema's own enum declares. */
  known: boolean;
}

export type LinkTarget =
  /** No `target` at all. The schema requires one, so the link is incomplete. */
  | { state: 'absent' }
  /** Present, and not the shape a record id has. Shown verbatim, never repaired. */
  | { state: 'malformed'; text: string }
  | { state: 'ok'; id: string };

export interface LinkView {
  /** Position in the record's `links` array — the only stable handle a link has. */
  index: number;
  rel: LinkTerm;
  basis: LinkTerm;
  target: LinkTarget;
  notes: string | null;
  /** True when the schema's three required members are all present and well-formed. */
  complete: boolean;
}

function term(raw: unknown, vocabulary: readonly string[]): LinkTerm {
  if (typeof raw !== 'string' || raw.trim() === '') {
    return { token: null, text: null, known: false };
  }
  const token = raw.trim();
  return { token, text: token.replace(/_/g, ' '), known: vocabulary.includes(token) };
}

function targetOf(raw: unknown): LinkTarget {
  if (raw === undefined || raw === null || raw === '') return { state: 'absent' };
  if (isRecordId(raw)) return { state: 'ok', id: raw };
  // A non-string `target` is malformed in exactly the way a wrong-shaped string
  // is, and is described the same way rather than being silently dropped.
  return { state: 'malformed', text: typeof raw === 'string' ? raw : JSON.stringify(raw) };
}

/**
 * The record's `links`, read defensively.
 *
 * Anything that is not an array yields an empty list, and a non-object element
 * is skipped: this reads a file the process did not write, and a malformed one
 * must not take the screen down. What it never does is REPAIR — a missing
 * `target` stays missing and is reported as an incomplete link (CLAUDE.md §5).
 */
export function readLinks(record: Record<string, unknown> | null): LinkView[] {
  if (record === null) return [];
  const raw = record.links;
  if (!Array.isArray(raw)) return [];
  const out: LinkView[] = [];
  raw.forEach((element, index) => {
    if (element === null || typeof element !== 'object' || Array.isArray(element)) return;
    const link = element as Record<string, unknown>;
    const rel = term(link.rel, LINK_RELATIONS);
    const basis = term(link.basis, LINK_BASES);
    const target = targetOf(link.target);
    const notesRaw = link.notes;
    out.push({
      index,
      rel,
      basis,
      target,
      notes: typeof notesRaw === 'string' && notesRaw.trim() !== '' ? notesRaw.trim() : null,
      complete: rel.token !== null && basis.token !== null && target.state === 'ok',
    });
  });
  return out;
}

/**
 * What a well-formed target points at, as far as THIS app can tell.
 *
 * `not_in_workspace` is deliberately not called "missing" or "invalid". The set
 * searched is the workspace's experiment list, which does not include the
 * per-run records a fan-out export writes and never includes a record held
 * anywhere else. The copy at the call site names that limit instead of implying
 * the target does not exist.
 */
export type TargetResolution =
  | { state: 'resolved'; experimentId: string; title: string }
  | { state: 'not_in_workspace' }
  | { state: 'unreadable' };

export function resolveTarget(
  id: string,
  experiments: readonly ApiExperimentSummary[] | null,
): TargetResolution {
  if (experiments === null) return { state: 'unreadable' };
  const hit = experiments.find((e) => e.record_id === id);
  return hit === undefined
    ? { state: 'not_in_workspace' }
    : { state: 'resolved', experimentId: hit.id, title: hit.title };
}

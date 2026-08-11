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
 * ─── AND WHY A FAN-OUT IS NOT ONE STATE FOR ALL SIX ─────────────────────────
 *
 * `routes.py::_detail` sets `fan_out = bool(exp.runs)` and stamps
 * `artifact_refs["reason"]` for ANY experiment that has a run, exported or not;
 * `export_units()` then exports one record per run under `target_id=run.id` and
 * never sets the experiment's own `record_id`, so `exported()` stays false and
 * this screen never gets a single record to read. That is a fact about THE
 * RECORD FILE. It is not automatically a fact about a VALUE, and the two must
 * not be collapsed — this branch once applied `no_single_value` to all six rows,
 * which told a reader that four values with one provable value had none:
 *
 *   * `isaac_record_version` — `export.py::transform` writes the module constant
 *     `ISAAC_VERSION` into EVERY record unconditionally, and the schema declares
 *     the property `{"type": "string", "const": "1.05"}`. It cannot differ
 *     between runs.
 *   * the classification trio — `meta` is `draft_builder._META`, a module-level
 *     constant; `resolved_run_draft` layer 3 copies the experiment's `meta` onto
 *     any run that carries none, and the only route that makes a run calls
 *     `exp.add_run(label=label)` with no draft at all. `workspace.block_level`
 *     states it outright: `meta` is "the record-type stamp that is the same for
 *     every run by construction". It cannot differ between runs either.
 *
 * So four rows keep their ordinary before-export state in a fan-out, and only
 * two take `no_single_value`:
 *
 *   * `record_id` — each unit exports under its own `target_id`, so the ids are
 *     distinct by construction.
 *   * `timestamps.created_utc` — it is on NEITHER `EXPERIMENT_LEVEL_FIELD_PATHS`
 *     nor `RUN_LEVEL_FIELD_PATHS`, so `resolved_run_draft` does not carry the
 *     experiment's stamp onto a run, and each run's record is stamped by
 *     `transform`'s own `setdefault` when that run is exported. That is also why
 *     the fan-out branch is tested BEFORE the draft-stamp branch below: the
 *     draft's stamp reaches no per-run record, so showing it here would present a
 *     value no exported record will carry.
 *
 * Every row's fan-out sentence is its own (`RecordInfoSpec.fanOut.note`), and the
 * server's sentence is appended to it verbatim rather than reworded. The server's
 * sentence is about the FILE; each row now states its own claim first, so a
 * file-level sentence is never left standing in for a value-level one.
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
  /**
   * This value is minted per record AND this experiment's runs each export their
   * own record, so the experiment has no single one. Both halves are required: a
   * fan-out alone does not make a value multi-valued, and a value the exporter
   * fixes for every record it writes keeps its ordinary state in a fan-out.
   */
  | 'no_single_value';

/** The state and the sentence one row takes when this experiment's runs fan out. */
export interface RecordInfoFanOut {
  source: RecordInfoSource;
  /**
   * The row's OWN claim. The server's `artifact_refs.reason` is appended to it
   * verbatim, so the file-level sentence supports a value-level one rather than
   * standing in for it.
   */
  note: string;
}

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
  /**
   * What this row says when this experiment's runs each export their own record.
   *
   * REQUIRED, not optional with a shared default, because the shared default is
   * exactly the defect: one blanket state for all six rows asserted "no single
   * value" for four values that provably have one. A future row has to answer
   * the question rather than inherit an answer.
   */
  fanOut: RecordInfoFanOut;
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
    // NOT `written_at_export` here: in a fan-out whose runs have already exported,
    // "not written yet" is false — every one of those records carries this value.
    // `not_read_here` is a claim about this screen alone, and it holds whether or
    // not the runs have exported.
    fanOut: {
      source: 'not_read_here',
      note: 'The exporter writes the same schema-fixed version into every record it writes, so it cannot differ between this experiment’s runs. This screen reads it out of a record, and this experiment has no single one to read.',
    },
    stamp: true,
  },
  {
    path: 'record_id',
    label: 'Record identifier',
    // schema/isaac_record_v1.json → properties.record_id.description
    description: 'ULID identifier for the record.',
    beforeExport: 'written_at_export',
    beforeExportNote: 'The exporter mints this when the record is written.',
    fanOut: {
      source: 'no_single_value',
      note: 'Each run exports its own record under its own identifier, so this experiment has no single one.',
    },
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
    // The trailing clause of `beforeExportNote` — "shown once the record is
    // written" — is a promise a fan-out never keeps, because no experiment-level
    // record is ever written for one. The state is unchanged; the sentence is.
    fanOut: {
      source: 'not_read_here',
      note: 'The stored rule stamps the same classification on every draft and the export carries it onto every run, so it cannot differ between this experiment’s runs. This screen reads it out of a record, and this experiment has no single one to read.',
    },
  },
  {
    path: 'record_domain',
    label: 'Record domain',
    // schema/isaac_record_v1.json → properties.record_domain.description
    description: 'Scientific domain of the record content.',
    beforeExport: 'not_read_here',
    beforeExportNote:
      'Derived by the same stored rule as the record type, and read from the exported record.',
    fanOut: {
      source: 'not_read_here',
      note: 'Derived by the same stored rule as the record type, so it cannot differ between this experiment’s runs. This screen reads it out of a record, and this experiment has no single one to read.',
    },
  },
  {
    path: 'source_type',
    label: 'Source type',
    // schema/isaac_record_v1.json → properties.source_type.description
    description: 'Origin of the data acquisition.',
    beforeExport: 'not_read_here',
    beforeExportNote:
      'Derived by the same stored rule as the record type, and read from the exported record.',
    fanOut: {
      source: 'not_read_here',
      note: 'Derived by the same stored rule as the record type, so it cannot differ between this experiment’s runs. This screen reads it out of a record, and this experiment has no single one to read.',
    },
  },
  {
    path: 'timestamps.created_utc',
    label: 'Record created',
    description: '',
    beforeExport: 'written_at_export',
    beforeExportNote:
      'A record-creation stamp, not a measurement time. The exporter stamps it when the record is written.',
    fanOut: {
      source: 'no_single_value',
      note: 'Each run’s record is stamped when that run is exported, and this experiment’s own draft stamp is not carried onto any of them, so this experiment has no single one.',
    },
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
 *     experiment's runs each export their own record. The row takes ITS OWN
 *     fan-out state — `no_single_value` for the two values minted per record,
 *     and the ordinary before-export state for the four the exporter or the
 *     stored rule fixes identically for every run (see the file header). The
 *     server's own sentence is appended verbatim rather than reworded.
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
      return {
        ...spec,
        value: null,
        source: spec.fanOut.source,
        note: `${spec.fanOut.note} ${fanOutReason}`,
      };
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

/**
 * One enum-valued member of a link, as it actually arrived.
 *
 * THE SAME THREE STATES `LinkTarget` HAS, and deliberately so. This used to be a
 * single shape with a nullable token, which collapsed two different facts into
 * one: a link carrying no `rel` and a link carrying `rel: 5` both read
 * "No relation. The official schema requires one." — a false statement about the
 * second, where a relation IS present and is merely not text.
 *
 * It also used to `trim()` before testing enum membership, so the stored token
 * `"derived_from "` — which the schema's enum does NOT contain, the enum holding
 * exact strings — was reported as one the schema lists. `targetOf` had already
 * taken the opposite and correct decision for `target`; this now matches it. A
 * stored value is reported as stored, never trimmed into validity.
 */
export type LinkTerm =
  /** No `rel` / `basis` at all. The schema requires one, so the link is incomplete. */
  | { state: 'absent' }
  /** Present and not text at all. Shown verbatim, never coerced into a token. */
  | { state: 'malformed'; text: string }
  /**
   * Present as text. `known` is membership of the schema's own enum tested on the
   * stored string, with nothing stripped from it first.
   */
  | {
      state: 'present';
      /** The stored token, verbatim. */
      token: string;
      /** The token with underscores opened up. Mechanical — never a rename. */
      text: string;
      known: boolean;
    };

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
  /**
   * True when the schema's three required members are each PRESENT and of the
   * kind the schema declares — a text relation, a text basis, a record-id target.
   *
   * Enum membership is deliberately NOT folded in. A `rel` the schema does not
   * list is reported on its own row ("Not one of the eight relations the official
   * schema lists"), and calling the link "Incomplete" for it would name a
   * different defect from the one it has. This flag drives that one word.
   */
  complete: boolean;
}

function term(raw: unknown, vocabulary: readonly string[]): LinkTerm {
  // The same absence test `targetOf` applies, for the same reason: `''` is the
  // one string a JSON document uses to mean "nothing here", and treating it as a
  // present-but-unlisted token would report an emptiness as a vocabulary error.
  // Nothing else is trimmed away — a whitespace-only token is a token that is not
  // in the enum, exactly as ` ${id} ` is a target that is not a record id.
  if (raw === undefined || raw === null || raw === '') return { state: 'absent' };
  if (typeof raw !== 'string') return { state: 'malformed', text: JSON.stringify(raw) };
  return {
    state: 'present',
    token: raw,
    text: raw.replace(/_/g, ' '),
    known: vocabulary.includes(raw),
  };
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
      complete: rel.state === 'present' && basis.state === 'present' && target.state === 'ok',
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

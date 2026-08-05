/*
 * Statistics — the PURE derivation layer for the read-only Statistics dashboard.
 *
 * Every figure that screen states is computed HERE, from four read-only
 * responses the app ALREADY serves, so no number on the page can be authored by
 * hand and drift from the running app:
 *
 *   · `GET /api/runtime/records`  (`api.getRuntimeRecords()`) — the SAFE
 *     cross-record projection (`apps/api/isaac_api/runtime_records.py`). Called
 *     with NO filters, because `limit` defaults to `None` server-side
 *     (`apps/api/isaac_api/routes.py:2584-2590`) and a partial page would
 *     silently undercount. The page owns that call; this module never fetches.
 *   · `GET /api/graph/status`     (`api.getGraphStatus()`)
 *   · `GET /api/openapi`          (`api.getOpenApi()`)
 *   · `GET /api/about`            (`api.getAbout()`) — consumed directly by the
 *     page's provenance rows; it needs no derivation and has none here.
 *
 * Governance, and the whole reason this layer is separate from the screen:
 *
 *   · COUNTS AND PROVENANCE STRINGS ONLY. No derivation ever emits a record
 *     title, an experiment or record id, a draft field value, a scientific
 *     value, an evidence body, a per-field classification, or a filesystem
 *     path. The input projection already withholds most of that; this layer
 *     reduces what remains to integers.
 *   · NOT telemetry. There is no request count, visit, session, user, IP,
 *     latency, uptime or database figure anywhere here, and no such signal
 *     exists to read.
 *   · A missing value becomes `null`, never `0` and never a plausible string
 *     (the rule `ProjectMemory.tsx:468` states as "Only figures the live
 *     response actually returned — nothing is ever defaulted").
 *   · No verdict. Export readiness is reported as the backend's own derived
 *     STATUS distribution; this module invents no PASS/FAIL and no "not run"
 *     state, because no stored validation verdict exists to report.
 *   · PURE: no fetch, no React, no clock, no locale, no `Math.random`. The
 *     dashboard's "last updated" timestamp is captured by the PAGE, deliberately
 *     outside these functions, so the same input always yields the same output.
 */

import { METHOD_ORDER, flattenOpenApi } from './apiDocsModel';
import { CANONICAL_STEPS } from './workflowSteps';
import type { RuntimeRecord } from './crossRecordTriage';
import type { ApiGraphStatus, ApiOpenApiResponse, OpenApiMethod } from './types';

/* The four derived workspace statuses, mirroring the module-level constants at
   `apps/api/isaac_api/workspace.py:72-76`. They are MUTUALLY EXCLUSIVE and
   exhaustive by construction: `Experiment.status()` (`workspace.py:400-417`)
   returns exactly one of them per record, on read, from the current draft. */
const NEEDS_ATTENTION = 'needs_attention';
const IN_REVIEW = 'in_review';
const READY_TO_EXPORT = 'ready_to_export';
const DONE = 'done';

/** A finite number, or `null` for anything else (absent, `null`, NaN). Never 0. */
function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** A non-empty string, or `null`. Never a placeholder. */
function stringOrNull(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

// --- workspace totals --------------------------------------------------------

export interface WorkspaceTotals {
  /** The server's own denominator (`body.total`), NOT `records.length`. */
  total: number;
  needsAttention: number;
  inReview: number;
  readyToExport: number;
  /** The `done` bucket: a written official record exists for the experiment. */
  exported: number;
  /** Any status outside the four — surfaced, never folded into a known bucket. */
  unknownStatus: number;
}

/**
 * The status distribution of the whole workspace.
 *
 * Mirrors `apps/api/isaac_api/workspace.py:400-417` (`Experiment.status()`) over
 * the projection at `apps/api/isaac_api/runtime_records.py:96-99`.
 *
 * `total` is the server's `body.total` — the count AFTER filtering and BEFORE
 * pagination (`routes.py:2596-2610`) — and is kept distinct from
 * `records.length` so a truncated page could never be presented as the whole
 * workspace.
 *
 * Bucketing is a single switch over the ONE mutually-exclusive `status` string,
 * so `needsAttention + inReview + readyToExport + exported + unknownStatus`
 * always equals `records.length`. The `exported` bucket counts `status === 'done'`
 * rather than the `exported` boolean: `status()` returns `DONE` if and only if
 * `Experiment.exported()` is true (`workspace.py:394-395, 411-412`), so the two
 * are equivalent for any consistent body — and driving it from the exclusive
 * status is what makes the invariant structural instead of assumed. A record
 * carrying a future status the client does not know lands in `unknownStatus`,
 * where it is visible, instead of being miscounted as one of the four.
 */
export function deriveWorkspaceTotals(body: {
  records: readonly RuntimeRecord[];
  total: number;
}): WorkspaceTotals {
  const totals: WorkspaceTotals = {
    total: body.total,
    needsAttention: 0,
    inReview: 0,
    readyToExport: 0,
    exported: 0,
    unknownStatus: 0,
  };
  for (const record of body.records) {
    switch (record.status) {
      case NEEDS_ATTENTION:
        totals.needsAttention += 1;
        break;
      case IN_REVIEW:
        totals.inReview += 1;
        break;
      case READY_TO_EXPORT:
        totals.readyToExport += 1;
        break;
      case DONE:
        totals.exported += 1;
        break;
      default:
        totals.unknownStatus += 1;
        break;
    }
  }
  return totals;
}

// --- workflow stage distribution --------------------------------------------

export interface StageBucket {
  id: string;
  label: string;
  count: number;
}

/** The bucket for a record whose workflow has no current step left. */
export const ALL_COMPLETE_STAGE_ID = 'all_complete';
export const ALL_COMPLETE_STAGE_LABEL = 'All Steps Complete';

/** The bucket for a `current_step` id this client does not recognise. Emitted
 *  ONLY when at least one record is in it (see {@link deriveWorkflowStages}). */
export const UNRECOGNIZED_STAGE_ID = 'unrecognized_step';
export const UNRECOGNIZED_STAGE_LABEL = 'Unrecognized Step';

/**
 * How many records sit at each workflow stage.
 *
 * Mirrors `apps/api/isaac_api/workflow.py:72-75` (`current_step` — the FIRST
 * unsatisfied step in `CANONICAL_ORDER`, or `None` when every step is
 * satisfied) as projected at `apps/api/isaac_api/runtime_records.py:105-111`.
 *
 * `current_step` is the ONLY signal used. The projection's `blocked` and
 * `reopened` booleans are deliberately ignored: they are OR-reductions over all
 * five steps (`runtime_records.py:107-111`) and per-step `blocked`/`reopened`
 * are not mutually exclusive of one another (`workflow.py:93-97`), so counting
 * records by them would double-count the same record.
 *
 * All six buckets are emitted in canonical order INCLUDING zeros, so the
 * visualization has a stable axis that does not reshape as records move. A
 * seventh {@link UNRECOGNIZED_STAGE_ID} bucket is appended only if a record
 * reports a step id this client does not know — that keeps the buckets summing
 * to `records.length` instead of silently dropping such a record, which is the
 * same honesty rule `unknownStatus` exists for. It is absent for every body the
 * current backend produces.
 */
export function deriveWorkflowStages(records: readonly RuntimeRecord[]): StageBucket[] {
  const counts = new Map<string, number>();
  for (const step of CANONICAL_STEPS) counts.set(step.id, 0);
  counts.set(ALL_COMPLETE_STAGE_ID, 0);
  let unrecognized = 0;

  for (const record of records) {
    const step = record.workflow?.current_step;
    if (typeof step === 'string' && counts.has(step)) {
      counts.set(step, (counts.get(step) ?? 0) + 1);
    } else if (step === null) {
      counts.set(ALL_COMPLETE_STAGE_ID, (counts.get(ALL_COMPLETE_STAGE_ID) ?? 0) + 1);
    } else {
      // A step id (or absent workflow) this client cannot place. Counted, never
      // guessed into a canonical bucket and never dropped.
      unrecognized += 1;
    }
  }

  const buckets: StageBucket[] = CANONICAL_STEPS.map((step) => ({
    id: step.id,
    label: step.label,
    count: counts.get(step.id) ?? 0,
  }));
  buckets.push({
    id: ALL_COMPLETE_STAGE_ID,
    label: ALL_COMPLETE_STAGE_LABEL,
    count: counts.get(ALL_COMPLETE_STAGE_ID) ?? 0,
  });
  if (unrecognized > 0) {
    buckets.push({
      id: UNRECOGNIZED_STAGE_ID,
      label: UNRECOGNIZED_STAGE_LABEL,
      count: unrecognized,
    });
  }
  return buckets;
}

// --- evidence totals ---------------------------------------------------------

export interface EvidenceTotals {
  supported: number;
  inferredCandidate: number;
  insufficientEvidence: number;
  conflictingEvidence: number;
  unknown: number;
  /** The sum of the five — a count of FIELDS across records, never of records. */
  totalFields: number;
  /** How many records contributed to the sums above. */
  recordsCounted: number;
}

/**
 * The five evidence-support classes in DISPLAY PRECEDENCE — the order
 * `apps/api/isaac_api/runtime_records.py:30-38` declares them, which is NOT
 * sorted by count. Each entry pairs the backend's own histogram key with the
 * {@link EvidenceTotals} field carrying its sum, so a consumer iterates the
 * five in precedence order without restating the order itself.
 */
export const EVIDENCE_CLASSES: readonly {
  readonly key: keyof RuntimeRecord['evidence_counts'];
  readonly field: 'supported' | 'inferredCandidate' | 'insufficientEvidence' | 'conflictingEvidence' | 'unknown';
}[] = [
  { key: 'supported', field: 'supported' },
  { key: 'inferred_candidate', field: 'inferredCandidate' },
  { key: 'insufficient_evidence', field: 'insufficientEvidence' },
  { key: 'conflicting_evidence', field: 'conflictingEvidence' },
  { key: 'unknown', field: 'unknown' },
] as const;

/**
 * Evidence support across the workspace, in FIELDS.
 *
 * Mirrors `apps/api/isaac_api/runtime_records.py:61-73` (`_evidence_counts`) —
 * the 5-class histogram of `evidence_classify.classify_fields`, counts only.
 * Per-field classifications, values, evidence bodies and source locators never
 * leave the server, and nothing here reconstructs them.
 *
 * Summing across records is arithmetically valid because the classification is
 * per-field and exhaustive: every classified field of every record falls in
 * exactly one of the five classes. The unit is therefore FIELDS, and
 * `recordsCounted` is carried alongside so a label can never quietly read the
 * field total as a record total.
 */
export function deriveEvidenceTotals(records: readonly RuntimeRecord[]): EvidenceTotals {
  const totals: EvidenceTotals = {
    supported: 0,
    inferredCandidate: 0,
    insufficientEvidence: 0,
    conflictingEvidence: 0,
    unknown: 0,
    totalFields: 0,
    recordsCounted: records.length,
  };
  for (const record of records) {
    for (const { key, field } of EVIDENCE_CLASSES) {
      const count = numberOrNull(record.evidence_counts?.[key]);
      if (count === null) continue; // absent class: contributes nothing, invents nothing
      totals[field] += count;
      totals.totalFields += count;
    }
  }
  return totals;
}

// --- export gate -------------------------------------------------------------

export interface ExportGate {
  /** `done`: a written official record exists. The SAME field
   *  {@link WorkspaceTotals.exported} counts — see the note below. */
  exported: number;
  /** `ready_to_export`: pending == 0 AND the official export dry-run passes. */
  readyNow: number;
  /** `in_review`: no open questions remain, but the dry-run does NOT pass. */
  blockedByGate: number;
  /** `needs_attention`: open questions remain, so the gate is not even reached. */
  blockedByQuestions: number;
  /** `artifact_state === 'stale'` — NOT exclusive of the four above. */
  staleArtifacts: number;
}

/**
 * The export gate, as the backend derives it.
 *
 * Mirrors `apps/api/isaac_api/workspace.py:400-417` (`Experiment.status()`) plus
 * `apps/api/isaac_api/dependencies.py` `artifact_state` as projected at
 * `apps/api/isaac_api/runtime_records.py:113-115`.
 *
 * There is deliberately no `passed` / `failed` / `not_run` field. No validation
 * verdict is stored anywhere: status is DERIVED on read from an in-memory
 * `export_draft` dry-run and nothing is persisted (`workspace.py:15-16`,
 * `workspace.py:410-417`). A "not run" count would therefore describe a state
 * the system does not have — it would be fabricated. What CAN be stated
 * honestly is where each record stands right now, which is what this returns.
 *
 * `staleArtifacts` is a separate axis, not a fifth bucket: an exported record
 * whose draft has since changed is both `exported` and stale, so this count
 * overlaps by design and must never be added to the four status counts. It
 * overlaps EXACTLY ONE of them — `exported` — and is in fact a subset of it:
 * `artifact_state` returns `none` unless `exp.exported()`
 * (`apps/api/isaac_api/dependencies.py:56-57`), and `status()` is `DONE` iff
 * `exported()` (`workspace.py:549-566`). A record cannot be stale while counted
 * under `readyNow`, `blockedByGate` or `blockedByQuestions`.
 *
 * That is a BACKEND invariant, and no frontend test can enforce it — this
 * function would happily count a body that violated it. What holds it is the
 * CODE guarantee cited above: `artifact_state` returns `none` unless
 * `exp.exported()` (`apps/api/isaac_api/dependencies.py:56-57`), which is
 * unconditional and covers `stale` as well as `current`.
 *
 * THE TEST CITED HERE IS NARROWER THAN THIS COMMENT USED TO SAY, and the
 * difference matters because it is the difference between an asserted invariant
 * and an unasserted one. It read "which asserts `exported is True` for every
 * record with a non-`none` artifact state".
 * `apps/api/tests/test_runtime_records.py::test_artifact_filter_current_only_for_exported`
 * queries `?artifact=current` and asserts `artifact_state == 'current'` and
 * `exported is True` for THAT SUBSET ONLY. No test pairs `artifact_state ==
 * 'stale'` with `exported` — the canonical seed produces no stale artifact, so
 * there is nothing for such a test to observe. The invariant still holds; it is
 * the code, not the test, that holds all of it.
 *
 * ONE FIELD FOR ONE WORD. `exported` reads `status === 'done'` — the same field
 * {@link deriveWorkspaceTotals} buckets on — and NOT the `exported` boolean it
 * previously read. The two are equivalent for every body the backend produces
 * (`status()` returns `DONE` iff `Experiment.exported()` is true,
 * `workspace.py:394-395, 411-412`), but they are not equivalent for an
 * INCONSISTENT body: a row carrying `exported: true` under a status this client
 * cannot place used to be counted here and not there, so the page stated two
 * different numbers under the one word "Exported". Reading the exclusive status
 * in both places makes that impossible, and keeps this function's four status
 * counts a partition of the recognised records for exactly the same reason
 * `deriveWorkspaceTotals` bucketed that way.
 */
export function deriveExportGate(records: readonly RuntimeRecord[]): ExportGate {
  const gate: ExportGate = {
    exported: 0,
    readyNow: 0,
    blockedByGate: 0,
    blockedByQuestions: 0,
    staleArtifacts: 0,
  };
  for (const record of records) {
    if (record.status === DONE) gate.exported += 1;
    if (record.status === READY_TO_EXPORT) gate.readyNow += 1;
    if (record.status === IN_REVIEW) gate.blockedByGate += 1;
    if (record.status === NEEDS_ATTENTION) gate.blockedByQuestions += 1;
    if (record.artifact_state === 'stale') gate.staleArtifacts += 1;
  }
  return gate;
}

// --- Project Memory facts ----------------------------------------------------

/**
 * Whether the served memory snapshot can be shown to describe THIS build.
 *
 * `undetermined` is a first-class answer, not a fallback: the deployed commit is
 * absent in a local run, and `current` is never manufactured from a comparison
 * that could not be made.
 */
export type MemoryFreshness = 'current' | 'point_in_time' | 'undetermined';

export interface MemoryFacts {
  /** The served PATH SET size (`file_count`). See the note on scope below. */
  servedFiles: number | null;
  concepts: number | null;
  communities: number | null;
  nodes: number | null;
  edges: number | null;
  sourceGraphCommit: string | null;
  deployedAppCommit: string | null;
  snapshotSchemaVersion: number | null;
  freshness: MemoryFreshness;
}

/** The shortest prefix that makes a commit comparison meaningful. Below this,
 *  two commits are treated as NOT comparable rather than as equal. */
const MIN_COMMIT_PREFIX = 7;

/**
 * The Project Memory plane's own reported facts.
 *
 * Mirrors the body assembled at `apps/api/isaac_api/routes.py:1975-2005`
 * (`GET /api/graph/status`).
 *
 * SCOPE, and the one trap in this endpoint: the response carries TWO different
 * file counts and they are deliberately different sets.
 *
 *   · `file_count` (`routes.py:2000`, from `overview["served_file_count"]`) is
 *     the served PATH SET — every repo-relative path the memory plane may
 *     describe.
 *   · `served_file_count` (`routes.py:1984`, from `status()`) is the served
 *     CONTENT MANIFEST — path + raw-bytes sha256, the drift-detection basis. It
 *     self-excludes the snapshot file it would otherwise hash, so it is smaller
 *     by one.
 *
 * `servedFiles` reads `file_count` ONLY, and its label must name that scope
 * (the path set). The two are never averaged, substituted, or presented as
 * interchangeable — see `CLAUDE.md` §17.
 *
 * Every figure is whatever the live response returned, or `null`: the endpoint
 * itself sets the additive fields to `null` when no overview is available
 * (`routes.py:2002-2003`), and a null count is stated as unavailable rather
 * than rendered as zero.
 *
 * `freshness` compares the snapshot's `source_graph_commit` with the build's
 * `deployed_app_commit` on their shared prefix (min {@link MIN_COMMIT_PREFIX}
 * chars, since either may be abbreviated). Both present and matching ⇒
 * `current`; both present and differing ⇒ `point_in_time`; anything else ⇒
 * `undetermined`, which the UI must render as "cannot be determined in this
 * environment" and never as current. Note this is a VERSION comparison only:
 * the endpoint keeps `deployed_app_commit` out of its own `memory_policy` /
 * `indexed_sources` freshness (`routes.py:1955-1965`), and so does this — the
 * value is not read as, or blended into, the snapshot's integrity signals.
 */
export function deriveMemoryFacts(g: ApiGraphStatus): MemoryFacts {
  const sourceGraphCommit = stringOrNull(g?.source_graph_commit);
  const deployedAppCommit = stringOrNull(g?.deployed_app_commit);

  let freshness: MemoryFreshness = 'undetermined';
  if (sourceGraphCommit !== null && deployedAppCommit !== null) {
    const shared = Math.min(sourceGraphCommit.length, deployedAppCommit.length);
    if (shared >= MIN_COMMIT_PREFIX) {
      freshness =
        sourceGraphCommit.slice(0, shared) === deployedAppCommit.slice(0, shared)
          ? 'current'
          : 'point_in_time';
    }
  }

  return {
    // `file_count` — the served PATH SET. NOT `served_file_count`.
    servedFiles: numberOrNull(g?.file_count),
    concepts: numberOrNull(g?.concept_count),
    communities: numberOrNull(g?.community_count),
    nodes: numberOrNull(g?.node_count),
    edges: numberOrNull(g?.edge_count),
    sourceGraphCommit,
    deployedAppCommit,
    snapshotSchemaVersion: numberOrNull(g?.snapshot_schema_version),
    freshness,
  };
}

// --- API surface -------------------------------------------------------------

export interface ApiSurfaceFacts {
  operationCount: number;
  groupCount: number;
  /** Present methods only, in {@link METHOD_ORDER}. Sums to `operationCount`. */
  byMethod: { method: OpenApiMethod; count: number }[];
  /** Groups in the document's own tag-registration order. */
  byGroup: { group: string; count: number }[];
}

/**
 * The shape of this app's own API, from this app's own contract.
 *
 * Built on `apps/web/src/lib/apiDocsModel.ts:127` (`flattenOpenApi`) — the
 * existing derivation layer over `GET /api/openapi`, whose header states there
 * is deliberately no second hand-maintained endpoint catalog in the client.
 * This module therefore does NOT re-parse the document and hard-codes no count:
 * grouping (the document's real `tags`), tag-registration ordering and the
 * untagged bucket all keep working exactly as the Endpoint Explorer's do,
 * because they are the same code.
 *
 * `byGroup` follows `flattenOpenApi`'s own row order, which is already the
 * document's tag-registration order (`apiDocsModel.ts:106-112`, `153-162`), so
 * first appearance gives registration order without re-reading `tags`.
 * `byMethod` lists only methods the contract actually documents — a method with
 * no operations is omitted rather than shown as a zero the document never
 * mentions.
 */
export function deriveApiSurface(doc: ApiOpenApiResponse): ApiSurfaceFacts {
  const rows = flattenOpenApi(doc);

  const methodCounts = new Map<OpenApiMethod, number>();
  // Insertion order == flattenOpenApi's row order == tag-registration order.
  const groupCounts = new Map<string, number>();
  for (const row of rows) {
    methodCounts.set(row.method, (methodCounts.get(row.method) ?? 0) + 1);
    groupCounts.set(row.group, (groupCounts.get(row.group) ?? 0) + 1);
  }

  /* Method display order — GET first, DELETE last — is IMPORTED from
     `apiDocsModel.ts`, not restated: `METHOD_ORDER` is the same constant
     `flattenOpenApi` iterates when it reads the document, so this list can
     never fall out of step with the methods that actually get flattened, and
     the Statistics breakdown orders methods exactly as the Endpoint Explorer
     does. There is one ordering, in one place. */
  const byMethod = METHOD_ORDER.filter((method) => methodCounts.has(method)).map((method) => ({
    method,
    count: methodCounts.get(method) ?? 0,
  }));
  const byGroup = Array.from(groupCounts, ([group, count]) => ({ group, count }));

  return {
    operationCount: rows.length,
    groupCount: byGroup.length,
    byMethod,
    byGroup,
  };
}

/*
 * Client types mirroring the Task 1 FastAPI serializations
 * (see .superpowers/sdd/task-1-report.md). Truth state (validation / coverage /
 * advisory / field status / evidence) is server-derived and read-only in the
 * client; the UI renders these shapes, it never computes them.
 */

// P30.3 — the SAFE cross-record runtime projection (GET /api/runtime/records).
// Defined next to the pure triage consumer that owns its contract; re-exported
// here so it reads alongside the other Api* shapes.
export type { RuntimeRecord } from './crossRecordTriage';

// --- primitives -------------------------------------------------------

export type Mode = 'synthetic';

export type SourceType =
  | 'spreadsheet'
  | 'file_listing'
  | 'derivation'
  | 'user_confirmation'
  | 'document'
  | 'screenshot'
  | 'web_form';

export type FieldStatus =
  | 'verified'
  | 'inferred'
  | 'needs_confirmation'
  | 'missing'
  | 'rejected';

// One evidence entry (draft envelope / sidecar). Fields vary by source_type.
export interface FieldEvidence {
  source_type: SourceType;
  source_file?: string;
  locator?: string;
  quote?: string;
  // user_confirmation adds question / answer / timestamp:
  question?: string;
  answer?: string;
  timestamp?: string;
  // derivation adds rule:
  rule?: string;
}

// --- draft (grouped fields; from build_draft) -------------------------

export interface DraftField {
  path: string; // official dotted JSON-path, e.g. system.facility.beamline
  label: string; // humanized last segment, e.g. Beamline
  value: unknown; // mono value; null when honestly missing
  unit?: string | null;
  status: FieldStatus;
  evidence_count: number;
  source_types: SourceType[];
  evidence?: FieldEvidence[]; // compact citation for the field row
  helper?: string; // inferred/needs-you helper copy (sentence case)
}

export interface FieldGroupData {
  block: string; // record block: system | sample | measurement | assets | descriptors
  humanLabel: string; // Facility & Beamline
  summary: string; // "3 fields · all verified" | "1 field needs you"
  needsYouCount: number;
  collapsedByDefault: boolean;
  fields: DraftField[];
}

// --- pending blockers (draft.pending[] → S4 questions) ----------------

export type BlockerKind = 'asset' | 'series' | 'descriptor' | 'edge' | string;
// hash → paste a sha256 (asset). structured → confirm a synthetic demo value the
// user can't type (series/descriptor objects). text → a short free-text value.
export type CompletionInputType = 'hash' | 'text' | 'structured';

export interface DemoAnswer {
  // A sha256 string for assets; a structured object (series list / descriptor
  // dict) for series/descriptor blockers — sent back verbatim on confirm.
  value: unknown;
  label: string; // "Demo answer (synthetic)"
}

export interface PendingBlocker {
  id: string; // uri for assets, else kind
  kind: BlockerKind;
  question: string; // verbatim from draft.pending[]
  label: string; // short Title Case label for the question
  path: string; // JSON path token
  about?: string;
  context?: string; // sentence-case context for the question card
  inputType: CompletionInputType;
  demo_answer?: DemoAnswer;
}

// --- the three signals (never merged) ---------------------------------

export type Verdict = 'pass' | 'fail' | 'pending';

export interface ValidationResult {
  verdict: Verdict; // hard gate
  ok: boolean;
  schemaVersion: string; // v1.05
  exitCode: number;
  errors: { path: string; message: string }[];
}

export interface AuditResult {
  resolved: number;
  total: number;
  uncovered: string[];
  dangling: string[];
}

export interface AdvisoryWarning {
  code: string; // NO_LINKS
  where: string;
  message: string;
}

// Deliberately no `ok`/verdict field (mirrors PortalWarningReport).
export interface AdvisoryResult {
  advisory: true;
  gating: false;
  warnings: AdvisoryWarning[];
}

export interface Signals {
  validation: ValidationResult | 'pending';
  coverage: AuditResult | 'pending';
  advisory: AdvisoryResult;
}

// --- evidence trail (S5) ----------------------------------------------

export interface EvidenceTrailEntry {
  key: string; // dotted path OR namespaced (assets: / descriptors: / implicit:)
  label: string;
  value?: string;
  status: FieldStatus;
  sourceTypes: SourceType[];
  evidence: FieldEvidence[]; // raw entries, passed through faithfully
  namespaced: boolean; // outside the N/N coverage count
  resolved: boolean;
}

export interface SourcePreviewLine {
  n: number;
  text: string;
}

export interface SourcePreview {
  file: string;
  lines: SourcePreviewLine[];
  citedLine?: number;
}

// --- memory / assistant -----------------------------------------------

// P24.10 separated memory-plane axes. `availability` is the PRIMARY axis; the
// old single conflated freshness `status` is gone. Each axis is individually
// honest and advisory — none is ever a validation verdict.
export type MemoryAvailability = 'available' | 'unavailable';
export type SnapshotIntegrity = 'verified' | 'malformed' | 'unsupported' | 'unknown';
export type MemoryConsistency = 'current' | 'stale' | 'unknown';

// Additive (P25.1): `advisory` (soft, non-gating warnings) and `workflow`
// (record/experiment status, pending items, artifacts) join the machine-stable
// enum. No source label ever implies the assistant itself validates.
export type AssistantSource =
  | 'schema'
  | 'audit'
  | 'git'
  | 'graph'
  | 'files'
  | 'advisory'
  | 'workflow';

/**
 * P36V S-B — a bounded, deterministic NAVIGATION action an assistant answer may
 * offer. It is a closed enum of one: the ONLY thing an action can do is send the
 * reader to an in-app client route. It cannot mutate a record, run a validation,
 * change a validation result, or authorize an export — the panel renders it as an
 * explicit user-activated control in the proposed-action region and follows `to`
 * through the SAME client-route allowlist every cited source passes.
 */
export type AssistantActionKind = 'open-validator';

export interface AssistantAction {
  kind: AssistantActionKind;
  /** The VISIBLE Title-Case control label (e.g. "Open Validator"). */
  label: string;
  /** An in-app client route (allowlisted at render time); never an external URL. */
  to: string;
}

export interface AssistantMessage {
  text: string; // sentence case; never renders PASS/FAIL
  answeredFrom: AssistantSource;
  /**
   * P36V S-B — an OPTIONAL navigation action offered alongside this answer. It
   * replaced the dead "Open Validate to run the deterministic schema check."
   * PROSE that used to be appended to the routed truth answers: a sentence that
   * named a control the app never rendered.
   */
  action?: AssistantAction;
}

export interface SuggestedPrompt {
  text: string;
  answeredFrom: AssistantSource;
  // The STATIC, source-labeled sample answer shown when this prompt is clicked.
  // A guided prompt with no answer stays display-only (never fabricates one).
  answer?: AssistantMessage;
}

// --- grounded assistant query (P34.1 endpoint / P34.2 composer) --------
// POST /api/experiments/{id}/assistant/query — the READ-ONLY grounded resolver.
// It never mutates the record; it resolves a free-form question against the
// current record/evidence/workflow/memory context and returns a source-labeled
// answer. The client parses this shape; it never computes an answer or a verdict.

export interface AssistantQueryRequest {
  question: string;
  grounded_rev?: string | null;
  history?: unknown[] | null;
}

// How the resolver handled the question — NOT a validity verdict.
export type AssistantQueryResult =
  | 'answered'
  | 'insufficient_context'
  | 'unsupported'
  | 'ambiguous';

// One cited source: a display label + an optional in-app navigation target.
export interface AssistantQuerySource {
  label: string;
  navigate_to: string | null;
}

export interface AssistantQueryResponse {
  answer: string;
  result: AssistantQueryResult;
  // The source planes the answer drew on (schema | audit | files | advisory |
  // workflow | graph). The first entry drives the `answered from:` label.
  grounding: AssistantSource[];
  sources: AssistantQuerySource[];
  // The record-scope endpoint carries a numeric rev + version token; the
  // record-agnostic Project-Memory endpoint (P34.4) has no record, so both are
  // null there (and `stale` is always false — there is no revision to be stale
  // against). A numeric rev is what drives the live-answer stale badge.
  record_rev: number | null;
  version: string | null;
  stale: boolean;
  followups: string[];
}

// --- grounded assistant composer (P25.1) ------------------------------
// The composer is a pure, synchronous function over the bundle a screen has
// ALREADY fetched — zero new fetches, zero backend endpoint, zero truth-path
// change. The full union is TYPE-declared here; only `review` is wired at P25.1.

export type ScreenContext = 'review' | 'export' | 'evidence' | 'complete' | 'memory';

export type GroundingState =
  | { context: 'review'; bundle: RecordBundle }
  | { context: 'export'; bundle: ExportReadinessBundle }
  | { context: 'evidence'; bundle: EvidenceBundle; selectedPath?: string }
  | {
      context: 'complete';
      detail: ApiExperimentDetail;
      pending: ApiPendingItem[];
      selectedPendingId?: string;
    }
  | { context: 'memory'; graph: ApiGraphStatus };

export interface GroundedChip {
  id: string; // stable key
  label: string; // chip text (verb-first, one question)
  source: AssistantSource; // the plane/category this answers from
  routed?: boolean; // truth-question chips that ALWAYS route, never echo a verdict
  resolve(state: GroundingState): AssistantMessage | null; // null → data absent → chip disabled
}

export interface ComposerOutput {
  reply: AssistantMessage;
  prompts: SuggestedPrompt[];
}

// --- export artifacts (S6) --------------------------------------------

export interface Artifact {
  kind: 'record' | 'sidecar';
  path: string;
  verdict?: 'pass'; // record card only
  pathCount?: number; // sidecar card only
}

// --- queue / experiments (S1) -----------------------------------------

export type QueueGroupKey = 'needsAttention' | 'inReview' | 'ready' | 'done';

export interface ExperimentTrailing {
  needsYouCount?: number;
  mentorReview?: boolean;
  coverage?: { resolved: number; total: number };
  verdict?: 'pass';
  exported?: boolean;
}

export interface ExperimentSummary {
  id: string;
  title: string; // authored with real subscripts (CuO₂)
  technique: string; // Cu K-edge XANES
  idOrDraft: string; // mono ULID or "draft · name"
  meta?: string; // "updated 2099-04-02" | "with G. Hopper"
  // P33 S1 — the dashboard card's ONE lifecycle badge (Draft/Exported), distinct
  // from the queue `group` (needsAttention/inReview/ready/done).
  lifecycle: 'draft' | 'exported';
  // P33 S1 — the neutral created-date badge; a display string plus a full,
  // unambiguous accessible string. Undefined when the server sent no created_utc.
  date?: { iso: string; display: string; accessible: string };
  group: QueueGroupKey;
  trailing: ExperimentTrailing;
}

export interface QueueGroup {
  key: QueueGroupKey;
  label: string;
  count: number;
  rows: ExperimentSummary[];
}

// --- staged runner (S2) -----------------------------------------------

export type RunnerStageState = 'done' | 'current' | 'upcoming';

export interface RunnerStage {
  key: string;
  label: string; // Title Case
  command: string; // real command, mono
  state: RunnerStageState;
  result?: string; // right-aligned result, e.g. "2 sources", "26 fields"
  subResult?: string; // secondary result line, e.g. "12 verified · 3 inferred"
  detail?: string; // blocker explanatory copy (sentence case)
  isBlocker?: boolean;
}

// --- workflow spine ---------------------------------------------------

// --- experiment detail (record surfaces) ------------------------------

export interface ExperimentDetail {
  id: string;
  title: string;
  technique: string;
  draftName: string; // mono draft filename or record filename
  mode: Mode;
  groups: FieldGroupData[];
  pending: PendingBlocker[];
  signals: Signals;
  artifacts: Artifact[];
}

// --- API wire types (exact Task 1 FastAPI serializations) -------------
// These mirror apps/api/isaac_api/{routes,serialize}.py 1:1. The typed client
// (lib/api.ts) returns these raw shapes; adapters (lib/adapt.ts) map them onto
// the UI types above. Truth (verdict / coverage / advisory / status) is
// server-derived — the client parses, it never computes.

export type ApiExperimentStatus =
  | 'needs_attention'
  | 'in_review'
  | 'ready_to_export'
  | 'done';

export interface ApiExperimentSummary {
  id: string;
  title: string;
  status: ApiExperimentStatus;
  created_utc: string;
  pending_count: number;
  evidenced_field_count: number;
  exported: boolean;
  record_id: string | null;
}

// P27.5 — the optimistic-concurrency version triplet the backend now returns on
// record detail and on every accepted mutation (POST /answers, POST /export).
// `version` is the opaque If-Match token the client echoes back (wrapped in
// double quotes) on the NEXT mutation; `rev`/`updated_utc` are informational.
export interface VersionFields {
  rev: number;
  updated_utc: string;
  version: string;
}

// P28.1 — the fixed canonical workflow, DERIVED by the backend from current
// record truth and shipped inside every detail bundle. The client renders it
// verbatim; it never re-derives step order or completion.
export type ApiWorkflowStepState = 'completed' | 'current' | 'reopened' | 'blocked';

export interface ApiWorkflowStep {
  id: string;
  label: string;
  state: ApiWorkflowStepState;
  current: boolean;
  reopened: boolean;
  blocked: boolean;
  reason: string | null;
}

export interface ApiWorkflow {
  ordered_steps: ApiWorkflowStep[];
  current_step: string | null;
  record_rev: number;
}

// P28.2 — derived exported-artifact freshness, carried on every detail bundle.
// `none` = nothing exported; `current` = the on-disk record still matches the
// current draft; `stale` = the record changed after export (or is unreadable) —
// records are immutable, so a stale artifact must never be presented as current.
export type ApiArtifactStateName = 'none' | 'current' | 'stale';

export interface ApiArtifactState {
  state: ApiArtifactStateName;
  reason: string | null;
}

// P28.2 — the downstream-invalidation summary a mutation (POST /answers,
// POST /export) returns, reported at the post-mutation revision. A byte-stable
// no-op reports `changed:false` with empty `changed_fields`/`reopened_steps`.
export interface ApiInvalidation {
  changed: boolean;
  rev: number;
  changed_fields: string[];
  reopened_steps: string[];
  artifact: ApiArtifactState;
  reason: string;
}

export interface ApiExperimentDetail extends ApiExperimentSummary, VersionFields {
  draft_ok: boolean;
  // P30.6 — safe basenames only (e.g. "<id>.json"), never an absolute
  // server/mount path. Null when not yet exported.
  artifact_refs: { record_filename: string | null; sidecar_filename: string | null };
  source_files: string[];
  workflow: ApiWorkflow;
  artifact: ApiArtifactState;
}

export interface ApiDraftField {
  path: string;
  label: string;
  value: unknown;
  status: FieldStatus;
  evidence_count: number;
  source_types: SourceType[];
}

export interface ApiDraftGroup {
  title: string;
  fields: ApiDraftField[];
}

export interface ApiDraftResponse {
  groups: ApiDraftGroup[];
}

export interface ApiDemoAnswer {
  // string sha256 for assets; structured object for series/descriptor blockers.
  value: unknown;
  label: string; // "Demo answer (synthetic)"
}

export interface ApiPendingItem {
  id: string; // uri for assets, else kind
  kind: BlockerKind;
  question: string;
  about?: string | null;
  demo_answer?: ApiDemoAnswer | null;
}

export interface ApiPendingResponse {
  pending: ApiPendingItem[];
}

export interface ApiValidateResult {
  ok: boolean;
  errors: { path: string; message: string }[];
  schema: string; // "ISAAC v1.05"
  dry_run: boolean; // true until the record is exported
}

// P36.3 — the standalone validator (POST /api/validate/record). No experiment,
// no draft: a pasted/uploaded candidate record checked against the same
// official schema, via the same `validate_official`, as `ApiValidateResult`
// above — just a different envelope shape (`summary` + `schema_version`).
export interface ApiValidateRecordResult {
  ok: boolean;
  summary: string;
  errors: { path: string; message: string }[];
  schema_version: string; // "1.05"
}

// A clean, typed rejection from POST /api/validate/record (non-object body,
// malformed JSON, or an oversized body) — never a stack trace.
export interface ApiValidateRecordError {
  error: string; // e.g. "not_a_json_object" | "invalid_json" | "request_too_large"
  message: string;
}

export interface ApiAuditRecord {
  name: string;
  ok: boolean;
  schema_errors: { path: string; message: string }[];
  evidence_present: number;
  evidence_expected: number;
  uncovered: string[];
  dangling: string[];
}

export interface ApiAuditResponse {
  records: ApiAuditRecord[];
  text: string;
  message?: string; // present when nothing is exported yet
}

// Advisory, non-gating channel. Deliberately no ok/valid/passed field.
export interface ApiWarningsResponse {
  advisory: true;
  gating: false;
  warnings: AdvisoryWarning[];
  dry_run?: boolean;
}

export interface ApiEvidenceEntry {
  path: string; // dotted path OR namespaced (assets: / descriptors: / implicit:)
  value?: unknown;
  status: FieldStatus;
  evidence: FieldEvidence[]; // raw entries, passed through faithfully
}

export interface ApiEvidenceResponse {
  evidence: ApiEvidenceEntry[];
}

// P28.5 — the deterministic evidence-SUPPORT classification (a display view over
// the P28.4 classifier). This is a THIRD axis, distinct from schema validity /
// workflow completion / advisory warnings — the wire body deliberately carries
// none of `valid`/`ok`/`exportable`/`complete`/`blocking`/`warnings`. Bound to
// `record_rev` so the client can detect a stale view. Mirrors
// apps/api/isaac_api/routes.py `get_evidence_classification` + evidence_classify.py.
export type EvidenceClass =
  | 'supported'
  | 'inferred_candidate'
  | 'insufficient_evidence'
  | 'conflicting_evidence'
  | 'unknown';

export type EvidenceValueState = 'confirmed' | 'candidate' | 'none';

// One safe, already-present source reference (never a raw answer/quote/secret/
// absolute path — the backend strips those in evidence_classify._safe_locator).
export interface ApiClassificationSource {
  source_type: SourceType;
  locator?: string;
}

export interface ApiFieldClassification {
  field: string; // dotted path OR namespaced (assets: / descriptors: / implicit:)
  classification: EvidenceClass;
  value_state: EvidenceValueState;
  explanation: string; // deterministic, human-readable
  sources: ApiClassificationSource[];
}

export interface ApiEvidenceClassification {
  record_rev: number; // authoritative rev the view is bound to
  field_results: ApiFieldClassification[];
  // same-axis histogram of the 5 classes (sum === field_results.length).
  counts: Record<EvidenceClass, number>;
}

// P31.3 — CSV reconciliation (RECONCILIATION-ONLY). A synthetic campaign-sheet
// CSV is previewed against the CURRENT record: every mapped value is reconciled
// as EVIDENCE and NEVER written. The three states are the only verdict this
// surface carries; it decides nothing about validity/completion/export. Mirrors
// the backend POST /experiments/{id}/ingestion/csv/preview response.
export type ReconciliationState =
  | 'matches_current'
  | 'conflicts_with_current'
  | 'absent_from_record';

// One unknown CSV column the parser ignored (never mapped to an official field).
export interface ApiCsvUnknownHeaderWarning {
  code: string;
  header: string;
  message: string;
}

// One top-level ingress warning (DISTINCT from a per-column unknown-header
// warning): a stable `code`, a SAFE human `message`, and an optional `count`
// (e.g. the number of unrecognized field-rows skipped). Authoritative mirror of
// the backend `warnings[]` contract (apps/api/isaac_api/csv_ingest.py).
export interface ApiCsvWarning {
  code: string;
  message: string;
  count?: number;
}

// One reconciled candidate: an official dotted field, its proposed CSV value, the
// current record value (when present), and the reconciliation verdict + safe
// provenance. Read-only evidence — there is no editable/confirmable CSV field.
//
// This interface is a FAITHFUL 1:1 mirror of the backend reconcile-item wire shape
// (apps/api/isaac_api/csv_ingest.py). Fields are kept as-shipped even when the panel
// does not read every one — do not trim the interface field-by-field to match
// current component usage (see `stale` below).
export interface ApiCsvReconcileItem {
  field: string; // official dotted path (FIELD_MAP output)
  field_label: string;
  experiment_id: string;
  proposed_value: unknown; // from the CSV
  current_value: unknown; // from the record (null when absent)
  reconciliation_state: ReconciliationState;
  evidence_classification: EvidenceClass;
  locator: string; // e.g. "row 3, field=formula" — never an absolute path
  column: string;
  source_name: string;
  source_format: string;
  parser_id: string;
  parser_version: string;
  source_record_rev: number;
  // Deliberate wire mirror of the backend field (always `false` at build time).
  // The panel does NOT read this — it derives staleness itself by comparing the
  // live record version against the previewed one. Kept for a faithful 1:1 shape;
  // do not delete it to "fix" the unused field.
  stale: boolean;
  value_state: EvidenceValueState;
  status: FieldStatus;
  explanation: string;
}

export interface ApiCsvPreview {
  format: string; // e.g. 'isaac_campaign_csv'
  source_name: string;
  parser_id: string;
  parser_version: string;
  source_record_rev: number;
  row_count: number;
  recognized_header_count: number;
  unknown_header_warnings: ApiCsvUnknownHeaderWarning[];
  candidate_count: number;
  reconciliation_summary: {
    matches_current: number;
    conflicts_with_current: number;
    absent_from_record: number;
  };
  candidates: ApiCsvReconcileItem[];
  warnings: ApiCsvWarning[];
}

// GET /source-preview?source= — the real fixture lines + the line numbers cited
// by the experiment's evidence (empty for a fixture cited by field, not by line).
export interface ApiSourcePreview {
  name: string;
  media_type: string;
  lines: SourcePreviewLine[];
  cited_lines: number[];
}

// GET /artifacts — the written record + sidecar JSON for an exported experiment;
// all null for a non-exported experiment (200, not an error).
export interface ApiArtifactsResponse {
  record: Record<string, unknown> | null;
  sidecar: Record<string, unknown> | null;
  // P30.6 — safe basenames only, never an absolute server/mount path.
  record_filename: string | null;
  sidecar_filename: string | null;
}

export interface ApiDemoStep {
  name: string; // build_draft | validate_draft | apply_answers | export_draft
  detail: string;
  ok: boolean;
}

export interface ApiDemoRunResponse {
  experiment_id: string;
  steps: ApiDemoStep[];
  status: ApiExperimentStatus;
}

export interface ApiUploadsBlocked {
  blocked: boolean;
  reason: string;
}

// GET /api/graph/status — the P24.10 separated-freshness contract
// (apps/api/isaac_api/routes.py `graph_status()`). The old single conflated
// `status` field and `source_graph_sha256` are removed. Each axis is
// individually honest: `availability` is primary, `integrity` describes only
// whether the snapshot artifact is well-formed + schema-supported (NOT its
// contents), and `memory_policy` / `indexed_sources` are separately-provable
// freshness axes. `deployed_app_commit` is version metadata ONLY — never a
// freshness input. Additive counts carry real values when the reader is
// available, else explicit `null` (never omitted, for shape stability).
export interface ApiGraphStatus {
  plane: 'memory';
  availability: MemoryAvailability;
  integrity: SnapshotIntegrity;
  provider: string; // provider_kind when available, else 'unavailable'
  memory_policy: MemoryConsistency;
  indexed_sources: MemoryConsistency;
  policy_fingerprint: string | null;
  served_manifest_fingerprint: string | null;
  served_file_count: number | null;
  freshness_scope: string;
  freshness_basis: string;
  source_graph_commit: string | null;
  snapshot_schema_version: number | null;
  deployed_app_commit: string | null;
  note: string;
  node_count: number | null;
  edge_count: number | null;
  community_count: number | null;
  file_count: number | null;
  concept_count: number | null;
  graph_mtime: number | null;
}

// P24.4 — Source Index (memory plane; metadata/provenance only, never file
// content). Mirrors GET /api/memory/files and GET /api/memory/file?path=
// (apps/api/isaac_api/routes.py "16. memory") 1:1. `file_type` is `null` when
// a served file carries no graph nodes of its own kind (present in the
// manifest but zero indexed nodes) — never invented, rendered as "Other".
export interface ApiMemoryFileSummary {
  path: string;
  file_type: string | null;
  community_id: string | null;
  community_name: string | null;
  node_count: number;
  on_disk: boolean;
}

export interface ApiMemoryFileDetail extends ApiMemoryFileSummary {
  local_reference: string;
}

export interface ApiMemoryRelatedFile {
  path: string;
  relation: string | null;
  file_type: string | null;
}

export interface ApiMemoryRelatedConcept {
  id: string;
  label: string | null;
  relation: string | null;
}

export interface ApiMemoryRelated {
  files: ApiMemoryRelatedFile[];
  concepts: ApiMemoryRelatedConcept[];
}

export type ApiMemoryUnavailableReason = 'graph_absent' | 'graph_unreadable';

export interface ApiMemoryFilesResponse {
  plane: 'memory';
  note: string;
  available: boolean;
  reason?: ApiMemoryUnavailableReason;
  files: ApiMemoryFileSummary[];
}

export interface ApiMemoryFileResponse {
  plane: 'memory';
  note: string;
  available: boolean;
  reason?: ApiMemoryUnavailableReason;
  file: ApiMemoryFileDetail | null;
  related: ApiMemoryRelated;
  rationales: string[];
}

// P24.5 — Concept Lookup (memory plane; metadata/provenance only). Mirrors
// GET /api/memory/concepts and GET /api/memory/concepts/{id}
// (apps/api/isaac_api/routes.py "16. memory") 1:1. `related` reuses the exact
// `ApiMemoryRelated` shape the file endpoints already emit (files/concepts
// leads, each ≤25). Against the real local graph all 19 concepts currently
// have zero edges, so `related.files`/`related.concepts` are both empty for
// every real concept — the UI must render that honestly, never invent leads.
export interface ApiMemoryConceptSummary {
  id: string;
  label: string;
  community_id: string | null;
  community_name: string | null;
  // `null` when the graph anchor points at a governance-excluded / secret path
  // (P24.9): the concept is still surfaced but its excluded anchor is withheld.
  source_file: string | null;
  on_disk: boolean;
}

export interface ApiMemoryConceptsResponse {
  plane: 'memory';
  note: string;
  available: boolean;
  reason?: ApiMemoryUnavailableReason;
  concepts: ApiMemoryConceptSummary[];
}

export interface ApiMemoryConceptResponse {
  plane: 'memory';
  note: string;
  available: boolean;
  reason?: ApiMemoryUnavailableReason;
  concept: ApiMemoryConceptSummary | null;
  related: ApiMemoryRelated;
}

// GET /api/memory/graph — P36.2 Project Memory "Graph" tab: a deterministic,
// capped, served-file REFERENCE projection (apps/api/isaac_api/memory_graph.py
// `build_graph_projection`). This is NOT the full source graph — the snapshot
// embeds no edge list; `meta.underlying_graph` is the honest disclosure that a
// LARGER, un-embedded source graph exists. Edges come ONLY from each file's
// own `related.files[]`; a concept is always an isolated node here (real data
// carries zero concept edges). `relations` preserves the real backend values
// verbatim (references / imports / calls / imports_from / shares_data_with,
// or any future value) — the client never collapses or invents a label.
export type ApiMemoryGraphNodeKind = 'file' | 'concept';

export interface ApiMemoryGraphFileNode {
  id: string; // the file's repo-relative path
  kind: 'file';
  label: string;
  file_type: string | null;
  community_id: string | null;
  community_name: string | null;
  node_count: number;
  on_disk: boolean;
}

export interface ApiMemoryGraphConceptNode {
  id: string;
  kind: 'concept';
  label: string | null;
  community_id: string | null;
  community_name: string | null;
  on_disk: boolean;
  // The concept's anchor source file, when governance-served (mirrors
  // ApiMemoryConceptSummary.source_file — null when withheld).
  source_file: string | null;
}

export type ApiMemoryGraphNode = ApiMemoryGraphFileNode | ApiMemoryGraphConceptNode;

export interface ApiMemoryGraphEdge {
  source: string; // node id (always a file path — edges never touch a concept)
  target: string; // node id
  // Every real relation value seen for this pair, sorted + de-duplicated —
  // NEVER a single hardcoded label. May be empty if the backend ever emits a
  // null/absent relation, but never fabricated.
  relations: string[];
}

export interface ApiMemoryGraphCommunity {
  id: string;
  name: string | null;
  file_count: number;
}

export interface ApiMemoryGraphCounts {
  files: number;
  concepts: number;
  reference_edges: number;
  files_with_references: number;
  isolated_files: number;
  communities_rendered: number;
}

export interface ApiMemoryGraphUnderlying {
  embedded: false;
  node_count: number | null;
  edge_count: number | null;
  community_count: number | null;
  note: string;
}

export interface ApiMemoryGraphProvenance {
  built_at_commit: string | null;
  source_graph_sha256: string | null;
  snapshot_schema_version: number | null;
  provider: string; // provider_kind when available, else 'unavailable'
  integrity: SnapshotIntegrity;
}

export interface ApiMemoryGraphMeta {
  counts: ApiMemoryGraphCounts;
  underlying_graph: ApiMemoryGraphUnderlying;
  provenance: ApiMemoryGraphProvenance;
}

export interface ApiMemoryGraphResponse {
  plane: 'memory';
  note: string;
  available: boolean;
  reason?: ApiMemoryUnavailableReason;
  truncated: boolean;
  nodes: ApiMemoryGraphNode[];
  edges: ApiMemoryGraphEdge[];
  communities: ApiMemoryGraphCommunity[];
  meta: ApiMemoryGraphMeta;
}

// GET /api/search — grouped truth+memory search (P26.3 backend envelope).
// One query fans out to two independently-honest groups: `workspace` (truth
// plane, the experiment/record store) and `memory` (advisory leads from the
// snapshot graph). Neither group's availability/degradation affects the
// other; the client parses this shape, it never merges or ranks the groups.
export type ApiSearchScope = 'all' | 'workspace' | 'memory';
export type ApiSearchTier = 'exact' | 'prefix' | 'token' | 'substring';

export interface ApiSearchMatch {
  field: string;
  snippet: string;
  reason: string;
  tier: ApiSearchTier;
  offsets: [number, number][];
}

export interface ApiWorkspaceSearchResult {
  kind: 'experiment' | 'record_id' | 'draft_field' | 'evidence' | 'artifact' | 'source_ref';
  experiment_id: string;
  record_id: string | null;
  title: string;
  label: string;
  status: string | null;
  match: ApiSearchMatch;
  navigate_to: string;
  plane: 'truth';
  source: string;
}

export interface ApiMemorySearchResult {
  kind: 'concept' | 'file' | 'rationale';
  id: string | null;
  path: string | null;
  label: string;
  community_name: string | null;
  match: ApiSearchMatch;
  navigate_to: string;
  plane: 'memory';
  source: string;
}

export type ApiWorkspaceSearchReason = null | 'query_too_short';
export type ApiMemorySearchReason = null | 'query_too_short' | 'graph_absent' | 'graph_unreadable';

export interface ApiWorkspaceSearchGroup {
  plane: 'truth';
  provider: string;
  available: boolean;
  reason: ApiWorkspaceSearchReason;
  total: number;
  returned: number;
  limit: number;
  offset: number;
  results: ApiWorkspaceSearchResult[];
}

export interface ApiMemorySearchGroup {
  plane: 'memory';
  provider: string;
  note: string;
  available: boolean;
  reason: ApiMemorySearchReason;
  total: number;
  returned: number;
  limit: number;
  offset: number;
  results: ApiMemorySearchResult[];
}

export interface ApiSearchResponse {
  query: string;
  normalized_query: string;
  scope: ApiSearchScope;
  workspace: ApiWorkspaceSearchGroup;
  memory: ApiMemorySearchGroup;
}

export interface ApiHealth {
  status: string;
  mode: string;
  core: string;
  version: string;
}

// POST /api/demo/reset — the guarded synthetic-demo reset (DemoResetResponse in
// apps/api/isaac_api/routes.py). The SAME shape carries both success (status
// "ok") and a safe refusal (status "refused"), returned at HTTP 200/403/409.
// Every field is a server-derived count/id; the client renders them, it never
// computes a reset decision.
export interface ApiDemoResetResult {
  status: 'ok' | 'refused';
  mode: 'preview' | 'execute';
  previous_count: number;
  canonical_count: number;
  legacy_count: number;
  ambiguous_count: number;
  removed_count: number;
  final_count: number;
  canonical_ids: string[];
  removable: { id: string; title: string }[];
  state_counts: Record<string, number>;
}

// Everything S3 needs, fetched concurrently but kept as separate values so the
// three signals are never merged (each still renders in its own component).
export interface RecordBundle {
  detail: ApiExperimentDetail;
  groups: ApiDraftGroup[];
  pending: ApiPendingItem[];
  validate: ApiValidateResult;
  audit: ApiAuditResponse;
  warnings: ApiWarningsResponse;
  evidence: ApiEvidenceEntry[];
  graph: ApiGraphStatus;
}

// POST /answers response — the recomputed pending list + fresh derived status,
// plus the P27.5 version triplet (the new If-Match token to adopt for the next
// mutation).
export interface ApiAnswersResponse extends VersionFields {
  pending: ApiPendingItem[];
  status: ApiExperimentStatus;
  // P28.2 — the post-mutation workflow + downstream-invalidation summary.
  workflow: ApiWorkflow;
  invalidation: ApiInvalidation;
}

export interface ApiReportError {
  path?: string;
  where?: string;
  message: string;
}

// POST /export response (export_result_to_dict + route enrichment). On success
// `ok:true` with record/sidecar/record_id/artifact_refs; on a gated failure
// `ok:false` with a flat `errors` list. A 409 (already exported) is thrown as an
// ApiError(status:409) by the client and never reaches this shape.
export interface ApiExportResponse extends VersionFields {
  ok: boolean;
  draft_report: { ok: boolean; errors: ApiReportError[]; warnings: ApiReportError[] };
  official_report: { ok: boolean; errors: { path: string; message: string }[] } | null;
  record?: Record<string, unknown>;
  sidecar?: Record<string, unknown>;
  errors?: { path: string; message: string }[];
  record_id?: string;
  // P30.6 — safe basenames only, never an absolute server/mount path.
  artifact_refs?: { record_filename: string; sidecar_filename: string };
  // P28.2 — the post-export workflow + downstream-invalidation summary (present
  // on both the success and the gated-failure paths).
  workflow?: ApiWorkflow;
  invalidation?: ApiInvalidation;
}

// Everything S6 needs to render the three signals + the export gate, fetched
// concurrently but kept as separate values (signals never merged). `artifacts`
// carries the written record + sidecar so View/Download work on a fresh load of
// an already-exported experiment (null before export).
export interface ExportReadinessBundle {
  detail: ApiExperimentDetail;
  pending: ApiPendingItem[];
  validate: ApiValidateResult;
  audit: ApiAuditResponse;
  warnings: ApiWarningsResponse;
  graph: ApiGraphStatus;
  artifacts: ApiArtifactsResponse;
}

// Everything S5 needs: the evidence trail, the exported record/sidecar content
// (null pre-export), the previews of every cited source fixture, and the memory
// freshness. Source previews are keyed by fixture basename.
export interface EvidenceBundle {
  detail: ApiExperimentDetail;
  evidence: ApiEvidenceEntry[];
  artifacts: ApiArtifactsResponse;
  graph: ApiGraphStatus;
  sourcePreviews: Record<string, ApiSourcePreview>;
  // P28.5 — the evidence-support classification for this record, fetched in the
  // SAME bundle so it stays coherent with `detail` across live-sync refetches.
  classification: ApiEvidenceClassification;
}

// --- P36.4 Settings: Help / About + API Documentation --------------------

// GET /api/about — non-sensitive app/provenance metadata (apps/api/isaac_api/
// routes.py `about()`). Every field is server-derived; the client renders it
// verbatim and computes nothing. Deliberately excludes hostnames, k8s/
// Authentik/ingress internals, env dumps, secrets, and absolute paths.
export interface ApiAboutResponse {
  app_version: string;
  build_commit: string | null;
  record_schema_version: string;
  runtime_mode: string;
  persistence: string;
  data_regime: string;
  core: string;
}

// GET /api/openapi — a MINIMAL subset of the OpenAPI 3 shape: only what the
// API Documentation card renders (method -> summary/description/parameters
// per path). The real response carries more (components, schemas, etc.);
// this type intentionally does not model those, and the reader must not
// assume any key beyond `paths` is present.
export interface OpenApiParameter {
  name: string;
  in: string;
  required?: boolean;
  description?: string;
}

/** One media type entry (`content["application/json"]`). Only the keys the
 *  browser renders are modeled; every value is displayed verbatim. */
export interface OpenApiMediaType {
  schema?: unknown;
  example?: unknown;
  examples?: Record<string, { summary?: string; description?: string; value?: unknown }>;
}

export interface OpenApiRequestBody {
  description?: string;
  required?: boolean;
  content?: Record<string, OpenApiMediaType>;
}

export interface OpenApiResponse {
  description?: string;
  content?: Record<string, OpenApiMediaType>;
}

export interface OpenApiOperation {
  summary?: string;
  description?: string;
  tags?: string[];
  operationId?: string;
  parameters?: OpenApiParameter[];
  requestBody?: OpenApiRequestBody;
  /** Keyed by status code as a STRING, exactly as OpenAPI emits it. */
  responses?: Record<string, OpenApiResponse>;
}

// Only the HTTP methods this prototype's API actually uses; an unlisted key
// (e.g. a future PATCH) is simply not read by the renderer, never guessed.
export type OpenApiMethod = 'get' | 'post' | 'put' | 'delete';

export type OpenApiPathItem = Partial<Record<OpenApiMethod, OpenApiOperation>>;

export interface ApiOpenApiResponse {
  openapi: string;
  info?: { title?: string; version?: string; summary?: string };
  paths: Record<string, OpenApiPathItem>;
  /** The document's registered tags, in declaration order. P36V PR3 slice C
   *  groups the endpoint list by these REAL tags and takes each group's
   *  description from here — replacing the path-segment inference that predated
   *  the backend assigning tags. Absent/empty is handled, never assumed. */
  tags?: { name: string; description?: string }[];
  /** Present in the real generated document. Used ONLY to resolve a local
   *  `#/components/schemas/<Name>` reference back to the schema it names — no
   *  other interpretation, and never a fabricated shape when the target is
   *  absent (the raw `$ref` is then shown as-is). */
  components?: { schemas?: Record<string, unknown> };
}

// GET /api/schema — P36.6 read-only Schema Reference browser (renamed from
// "Schema & Vocabulary" by P36R S8). Serves the
// vendored official schema (loaded via `isaac_records.official.schema_path`,
// never re-derived) plus every `vocabulary/*.json`, verbatim. This is the
// reference plane (schema/vocabulary), NOT the portal Ontology system — no
// propose/review/approve/edit affordance exists anywhere in this app for it.
// `schema` is a JSON-Schema (draft 2020-12) document; only the shape the
// browser actually reads is modeled below — an index signature keeps the type
// permissive so it never claims more structure than the vendored file has.
export interface JsonSchemaConditional {
  if?: JsonSchemaNode;
  then?: JsonSchemaNode;
}

export interface JsonSchemaNode {
  type?: string | string[];
  title?: string;
  description?: string;
  enum?: unknown[];
  const?: unknown;
  required?: string[];
  properties?: Record<string, JsonSchemaNode>;
  items?: JsonSchemaNode;
  oneOf?: JsonSchemaNode[];
  allOf?: JsonSchemaConditional[];
  additionalProperties?: boolean;
  [key: string]: unknown;
}

export interface ApiSchemaResponse {
  schema_title: string | null;
  schema_version: string;
  schema: JsonSchemaNode;
  // Keyed by vocabulary filename stem (e.g. "descriptor_class"); each value is
  // the parsed vocabulary/*.json content verbatim — shape is per-file, so this
  // stays a permissive `unknown`.
  vocabularies: Record<string, unknown>;
}

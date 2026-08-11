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

/**
 * The five explicit inferability states, mirroring
 * `apps/api/isaac_api/inferability.py`. A CONCRETE value may accompany
 * `supported_suggestion` and nothing else — the backend enforces that in
 * `Inferability.__post_init__`, and `sanitizeInferability` (lib/adapt.ts)
 * re-checks it on arrival, because a client that trusts the shape it was promised
 * has no way to notice when the promise breaks.
 */
export type InferabilityState =
  | 'supported_suggestion'
  | 'needs_user_input'
  | 'ambiguous'
  | 'contradictory_evidence'
  | 'not_inferable';

/** Machine-checkable justification for a supported suggestion. */
export interface SuggestionProvenance {
  supporting_fields: string[];
  supporting_evidence: { source_type?: string; [k: string]: unknown }[];
  rule: string;
  unique: boolean;
  alternatives_excluded: string[];
  requires_user_confirmation: boolean;
}

export interface Inferability {
  field: string;
  state: InferabilityState;
  explanation: string;
  /** Non-null ONLY for `supported_suggestion`. */
  value: unknown;
  provenance: SuggestionProvenance | null;
  /** Counts, constraint text, conflicting source names — never a candidate value. */
  detail: Record<string, unknown>;
}

/** What an example answer IS, carried with it so no reader has to infer it. */
export interface ExampleAnswerProvenance {
  source: string;
  is_evidence_for_this_record: boolean;
  auto_applied: boolean;
  requires_user_confirmation: boolean;
}

export interface DemoAnswer {
  // A sha256 string for assets; a structured object (series list / descriptor
  // dict) for series/descriptor blockers — sent back verbatim on confirm.
  value: unknown;
  label: string; // "Example answer"
  // Present on every server-sent example answer. Optional in the type only so
  // older recorded fixtures keep compiling.
  provenance?: ExampleAnswerProvenance;
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
  // Why the app cannot determine this value itself. Always present from a
  // current backend; optional so pre-existing fixtures still typecheck.
  inferability?: Inferability;
}

// --- the three signals (never merged) ---------------------------------

export type Verdict = 'pass' | 'fail' | 'pending';

/**
 * R1b — `exitCode: number` was removed. Nothing ever exited with it: every
 * producer computed the literal `ok ? 0 : 1`, and its only reader rendered it as
 * if it were captured CLI output (see `components/VerdictCard.tsx`). A field that
 * can only ever hold a restatement of `ok`, and that invites being displayed as
 * an observation, is worse than absent.
 */
export interface ValidationResult {
  verdict: Verdict; // hard gate
  ok: boolean;
  schemaVersion: string; // v1.05
  errors: { path: string; message: string }[];

  // WHICH GATE REFUSED. `ok` is no longer the official schema's verdict on every
  // producer: `POST /api/validate/record` also applies ISAAC's anchored-pattern
  // exactness gate, so `ok: false` there can sit above `schema_ok: true` and an
  // EMPTY `errors`. `VerdictCard` used to read that as "invalid against official
  // ISAAC schema v1.05 — 0 errors", asserting that the upstream schema rejected a
  // record it accepted, about a document CLAUDE.md §1 makes not ours to speak for.
  //
  // Both fields are OPTIONAL, and that is deliberate rather than lazy: the
  // per-experiment validate route returns neither, and its `ok` IS the schema
  // verdict. An absent `schemaOk` therefore means "same as `ok`" — the reading
  // that was true before this pair existed — and an absent `exactnessErrors`
  // means the producer does not run that gate, which is different from running it
  // and finding nothing.
  schemaOk?: boolean;
  exactnessErrors?: { path: string; message: string }[];
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
  status: EvidenceEntryStatus;
  sourceTypes: SourceType[];
  evidence: FieldEvidence[]; // raw readable entries, passed through faithfully
  namespaced: boolean; // outside the N/N coverage count
  resolved: boolean;
  /** This ONE entry could not be fully read — rendered as unavailable, never dropped. */
  unavailable?: boolean;
  /** The truthful reason, from the backend when it has one, else this client's own. */
  unavailableReason?: string;
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
  /**
   * P36V.1 Unit B — the EXACT technical locators behind a humanized answer, shown
   * ONLY inside the collapsed `Technical Details` disclosure. The primary answer
   * text carries human-facing location phrases (`the record itself`, `sample →
   * material → formula`); the raw JSONPath — including the truth core's literal
   * root marker `$` — lives here and nowhere else in the rendered answer.
   */
  technicalPaths?: string[];
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

/**
 * P36V.1 Unit B — a navigation action carried by a FREE-FORM answer.
 *
 * Before this slice `AssistantQueryResponse` had no action field at all, so a
 * free-form answer structurally could not render the working Open Validator
 * control: the backend instead emitted a cited-source chip labelled
 * "Open Validate" whose `navigate_to` was the record already on screen, which is
 * why clicking it appeared to do nothing.
 *
 * `kind` is the contract; `label` and `to` make the API response self-describing.
 * The client does NOT trust them for rendering — `resolveAssistantAction`
 * (assistantComposer.ts) maps `kind` to this build's own frozen descriptor, so the
 * visible label and the client route the router resolves under its `basename` stay
 * frontend-owned. An unknown `kind` is dropped, never rendered.
 */
export interface AssistantQueryAction {
  kind: string;
  label: string;
  to: string;
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
  /**
   * P36V.1 Unit B — the OPTIONAL bounded navigation action this answer offers
   * (today only Open Validator, on the export-blocker / export-readiness intents).
   * `null` on every other answer.
   */
  action?: AssistantQueryAction | null;
  /**
   * P36V.1 Unit B — the EXACT validation locators behind a humanized blocker
   * answer, for the `Technical Details` disclosure only. Empty on every answer
   * that reports no locators.
   */
  technical_paths?: string[] | null;
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
  // Server-supplied scenario label for a canonical synthetic seed; undefined for
  // every other record, in which case the row renders nothing for it.
  scenario?: string;
  // OPTIONAL, and normally absent. No list endpoint sends a technique, so the
  // adapter no longer invents one (see the note in `adapt.ts`). Kept in the type
  // because it is a legitimate field for a server that one day does send it —
  // when a value is present it must have come from a response, never a constant.
  technique?: string;
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
  detail?: string; // the step's own explanatory copy (sentence case)
  // R1b — `isBlocker?: boolean` was removed. Nothing ever set it; its only reader
  // was a `StagedRunner` CTA whose handler was never passed and whose field count
  // was hard-coded. See components/StagedRunner.tsx.
}

// --- workflow spine ---------------------------------------------------

// --- experiment detail (record surfaces) ------------------------------

export interface ExperimentDetail {
  id: string;
  title: string;
  // Optional for the same reason as on `ExperimentSummary`: never fabricated.
  technique?: string;
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
  // The backend's DERIVED, never-stored scenario label for one of the five
  // canonical synthetic seeds (e.g. "Scenario 4 · seeded: descriptor
  // uncertainty omitted"). `null`/absent for every user-created record.
  // It names how the seeded fixture was MATERIALISED, in the past tense, and is
  // deliberately never refreshed — so advancing the record changes `status`
  // below without falsifying the label. Invariance alone would not be enough:
  // an invariant present-tense state description over a mutating record is
  // guaranteed to go false.
  // The text is authored server-side; the client only renders it.
  scenario?: string | null;
  status: ApiExperimentStatus;
  created_utc: string;
  pending_count: number;
  evidenced_field_count: number;
  exported: boolean;
  record_id: string | null;
}

/**
 * WHY THE EXPERIMENT LIST COULD BE SHORT — present ONLY when it could be.
 *
 * `GET /api/experiments` restores working copies from this deployment's database
 * before it enumerates them, and that restore can fail two ways. The list does not
 * fail with it (a reader with three readable records should still see three), so
 * without this block a short list is indistinguishable from a small workspace.
 *
 * `store_unavailable` — the database did not answer. `/api/health` reports
 * `experiment_storage.state: "unavailable"` in this state too.
 * `restore_failed` — everything else that stops the restore: a working copy that
 * could not be written, a stored row the server refused as unplaceable, or a
 * store it could not resolve. The database is typically healthy in all three, so
 * `/api/health` correctly still says `durable`, and this response is the ONLY
 * place the shortfall is visible. That is the mode this type exists for. Its
 * message deliberately does not promise that retrying clears it.
 *
 * `missing_count` is always `null`, and it is carried rather than omitted because
 * "unknown" is the answer: a restore that stopped part-way does not know how many
 * rows it never reached, and the client must never render a number for it.
 */
export type ApiListIncompleteReason = 'store_unavailable' | 'restore_failed';

export interface ApiListIncomplete {
  /** A reason this build recognises, or any other string a later server sends. */
  reason: string;
  /** Always `null` — the count is genuinely unknown. Never rendered as a number. */
  missing_count: number | null;
  /** The server's own fixed sentence. Names no host, path or credential. */
  message: string;
}

/**
 * The `GET /api/experiments` envelope. `incomplete` is `null` when the server
 * said nothing about completeness — which is what a whole list looks like, and
 * also what a server too old to carry the block looks like. Both mean "no claim
 * that anything is missing", which is the only reading the UI acts on.
 */
export interface ApiExperimentList {
  experiments: ApiExperimentSummary[];
  incomplete: ApiListIncomplete | null;
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
  //
  // `reason` is present ONLY for a record whose runs each export their own official
  // record: the filenames are null there because the field is SINGULAR and such a
  // record has several, which is a different statement from "nothing was exported"
  // and now says so rather than being inferred from two nulls.
  artifact_refs: {
    record_filename: string | null;
    sidecar_filename: string | null;
    reason?: string;
  };
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
  label: string; // "Example answer"
  provenance?: ExampleAnswerProvenance;
}

export interface ApiPendingItem {
  id: string; // uri for assets, else kind
  kind: BlockerKind;
  question: string;
  about?: string | null;
  // Example-scope records ONLY. `null`/absent on every ordinary record.
  demo_answer?: ApiDemoAnswer | null;
  inferability?: Inferability;
}

export interface ApiPendingResponse {
  pending: ApiPendingItem[];
}

export interface ApiValidateResult {
  ok: boolean;
  errors: { path: string; message: string }[];
  schema: string; // "ISAAC v1.05"
  dry_run: boolean; // true until the record is exported
  // Present ONLY for a record whose runs each export their own official record:
  // one verdict per run, because a flat list of N records' errors is not
  // addressable. `ok` above is true only when every entry is; `dry_run` above is
  // true if ANY entry's verdict came from an in-memory candidate.
  runs?: {
    run_id: string | null;
    run_label: string | null;
    record_id: string;
    ok: boolean;
    errors: { path: string; message: string }[];
    dry_run: boolean;
    // NO VERDICT COULD BE PRODUCED — set by `_validate_unit` on the two branches
    // whose own comment reads "no verdict, not a schema violation": an unreadable
    // written artifact, and an exception during the dry run. `ok` is `false` on
    // both (fail-closed), so a client keying on `ok` alone renders a refusal as a
    // schema failure. THAT is why the flag exists, and omitting it from this type
    // made TypeScript prevent a client from reading it — leaving the fixed English
    // sentence in `errors[0].message` as the only reachable signal. Optional
    // because the field is absent on every verdict that IS a verdict.
    unavailable?: boolean;
  }[];
}

// P36.3 — the standalone validator (POST /api/validate/record). No experiment,
// no draft: a pasted/uploaded candidate record checked against the same
// official schema, via the same `validate_official`, as `ApiValidateResult`
// above — just a different envelope shape (`summary` + `schema_version`).
export interface ApiValidateRecordResult {
  ok: boolean;
  summary: string;
  errors: { path: string; message: string }[]; // SCHEMA errors only
  schema_version: string; // "1.05"

  // The official schema's OWN verdict, preserved beside `ok`. Optional because a
  // response predating the exactness gate carries neither this nor
  // `exactness_errors`; absent means "same as `ok`".
  schema_ok?: boolean;
  // ISAAC's anchored-pattern exactness findings. NOT schema errors, and kept in
  // their own list for exactly that reason: all five `pattern` gates in the
  // vendored schema are written `^...$` and Python's `$` also matches before one
  // trailing newline, so the schema accepts values its own pattern text refuses.
  // Merging these into `errors` would attribute an ISAAC policy to upstream.
  exactness_errors?: { path: string; message: string }[];

  // R2 — the ADVISORY tier, which this route did not previously run at all. Optional
  // in the type because a cached/older response shape must not break the client, and
  // because the two 422 rejection paths (malformed JSON, non-object body) legitimately
  // carry no warnings: there is no record to advise on.
  //
  // `ok` above is never combined with the warning count — that half of this note is
  // unchanged and still load-bearing. A warning must not be able to turn a PASS into a
  // FAIL, or this tier becomes a second authority on validity beside the vendored schema.
  //
  // ~~"`ok` above is computed from schema validation ALONE"~~ — WAS TRUE, IS NOT. The
  // old wording is kept struck through rather than deleted, because it read as a
  // guarantee and a future reader who remembers it would be wrong. `ok` is now
  // `schema_ok && exactness_ok`. Advisory warnings are still excluded; the exactness
  // gate is the ONE non-schema input, and it is a hard gate rather than an opinion —
  // `export_draft` refuses the same records, so a `true` here would have made this
  // route the one surface that says yes to something the product says no to.
  advisory?: boolean;
  gating?: boolean;
  warnings?: AdvisoryWarning[];
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
  // Present ONLY for a record whose runs each export their own official record.
  // The advice used to be computed from the experiment-level half — never exported,
  // no measurement block — so it reported NO_MEASUREMENT_SERIES about records that
  // all carry one. `warnings` above is the deduplicated union over these entries,
  // which is safe here (and is NOT what `ApiValidateResult` does) precisely because
  // this channel carries no verdict: aggregating advice cannot turn a pass into a
  // fail. `dry_run` above is true if ANY entry's advice came from a candidate.
  runs?: {
    run_id: string | null;
    run_label: string | null;
    record_id: string;
    warnings: AdvisoryWarning[];
    dry_run: boolean;
  }[];
}

/**
 * `status` on a trail entry is NOT the draft's `FieldStatus` alone. The backend
 * serves `'unavailable'` for an entry whose stored evidence it could not read
 * (`serialize.UNAVAILABLE_STATUS`) — a distinct value on purpose, so an
 * unreadable entry can never be mistaken for a verified one. Kept out of
 * `FieldStatus` itself because a DRAFT field's status can never take this value.
 */
export type EvidenceEntryStatus = FieldStatus | 'unavailable';

export interface ApiEvidenceEntry {
  path: string; // dotted path OR namespaced (assets: / descriptors: / implicit:)
  value?: unknown;
  status: EvidenceEntryStatus;
  evidence: FieldEvidence[]; // raw readable entries, passed through faithfully
  /**
   * Present (and `true`) when part or all of this ONE entry's stored evidence
   * could not be read. The entry is still served, still carries its own path,
   * and carries no invented value or citation in place of what failed. Every
   * other entry in the same trail is unaffected — that isolation is the point.
   */
  unavailable?: boolean;
  /** Why this entry is unavailable, in the backend's own words. Never generic. */
  unavailable_reason?: string;
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
  | 'unknown'
  // The entry's stored evidence could not be read, so its support is UNKNOWN TO
  // THE SERVER. Deliberately not folded into `unknown`, which asserts that
  // nothing defensible is recorded — see `evidence_classify._classify_entry`
  // rule 0.
  | 'unreadable';

export type EvidenceValueState = 'confirmed' | 'candidate' | 'none' | 'unreadable';

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
  // same-axis histogram of the 6 classes (sum === field_results.length).
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
  // P4 — the SAME derived freshness block the detail endpoint serves under the
  // same key. A null `record`/`sidecar` alone is ambiguous: it means either "never
  // exported" (`state: 'none'`) or "exported, but the artifact file is missing or
  // unreadable" (`state: 'stale'`). This is the field that tells them apart.
  artifact: ApiArtifactState;
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

/**
 * `POST /api/tutorial/sessions` — a freshly opened worked-example workspace.
 *
 * `record_ids` is read back from the session that was just created, so it states
 * what is actually there rather than what was intended: a caller must use these
 * ids and must not assume a fixed set.
 */
export interface ApiTutorialSession {
  session_id: string;
  record_ids: string[];
  ttl_hours: number;
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

// Slice 2A — the outcome of the most recent read-only reconnaissance scan IN
// THIS SERVER PROCESS (`_db_recon_last_summary` in apps/api/isaac_api/routes.py).
// It is an in-process memo, NOT a live probe: `/api/health` performs zero I/O.
// `at` mirrors the scan envelope's `generated_at`.
export type ApiDbReconStatus = 'ok' | 'not_configured' | 'busy' | 'refused' | 'error';

export interface ApiHealthLastRecon {
  status: ApiDbReconStatus;
  at: string | null;
}

/**
 * Slice 2A — the `database` block on GET /api/health
 * (apps/api/isaac_api/routes.py `health()`). Derived from CONFIGURATION ALONE:
 * the handler never opens a connection, issues a query, or waits on one, so
 * `configured: true` means "this deployment is set up to run the protected
 * read-only diagnostic", NEVER "a database is currently reachable".
 *
 * The block deliberately carries no host, port, database name, user, or
 * credential — `classification` is a fixed code constant
 * ("isolated-app-postgres"), not an identifier of a real server. The UI must
 * not render it verbatim either (see components/TopBar.tsx).
 *
 * Optional here because a build/deployment predating Slice 2A — and a health
 * body the client failed to fetch — simply has no such block. Absent is read
 * as "no database", never guessed.
 */
export interface ApiHealthDatabase {
  configured: boolean;
  classification: string | null;
  contains_production_derived_records: true | null;
  /** "closed" — hosted per-record display is closed pending a visibility decision. */
  record_display: string;
  last_recon: ApiHealthLastRecon | null;
}

/**
 * The `experiment_storage` block on GET /api/health
 * (apps/api/isaac_api/routes.py `health()` → `experiment_repository.storage_status`).
 *
 * WHAT IT IS FOR. It is the only honest basis for the sentence My Experiments
 * shows about where a new experiment goes. Hard-coding either answer would make
 * that sentence false on half the deployments — the deployed pod stores
 * experiments in its own PostgreSQL database, a developer checkout and CI store
 * them in a workspace directory, and on the pod that directory is an `emptyDir`
 * that a restart empties.
 *
 * THE HANDLER OPENS NO CONNECTION — same discipline as the sibling `database`
 * block, because `/api/health` is the container readiness probe and a database
 * problem must never be able to fail it.
 *
 * IT IS NOT "DERIVED FROM CONFIGURATION ALONE", AND THIS COMMENT USED TO SAY IT
 * WAS. That was true of the first implementation and it is exactly what made the
 * defect invisible: the deployed pod has `PGHOST` and `PGDATABASE` set, so the
 * durable backend selected itself, while the migration had not been applied — the
 * table did not exist, every read and write against it failed, and this block
 * went on reporting `durable: true`. The block now also carries an OBSERVATION
 * recorded when a real read or write failed. It still probes nothing; it reports
 * what has already happened.
 *
 * `state` is the field to branch on. `durable` is kept, and kept consistent with
 * it, so a client reading only the boolean is never left on the optimistic
 * branch — but three states cannot be reconstructed from two booleans without a
 * truth table at every call site, and truth tables reconstructed at call sites
 * eventually disagree.
 *
 * Optional here because a build predating this block, and a health body the
 * client failed to fetch, simply have none. Absent is read as "unknown", and the
 * UI then claims NEITHER durability nor ephemerality — see `ExperimentsHome`.
 * `state` is separately optional from the block, because a deployment running the
 * first version of this block has `configured`/`durable` and no `state`.
 */
export interface ApiHealthExperimentStorage {
  configured: boolean;
  /** "postgres" | "filesystem" — an implementation name, never rendered verbatim.
   *  It reports what is SELECTED, not whether it is working: a pod whose database
   *  has stopped answering still has the postgres backend selected, because it
   *  keeps trying, which is what lets it recover. */
  backend: string;
  durable: boolean;
  /**
   * "ephemeral" (no database configured) | "durable" | "unavailable" (a database
   * IS configured and experiments are not going into it — the name was refused,
   * or it stopped answering). Widened to `string` so an unrecognised future value
   * is a type-level possibility rather than a surprise; `ExperimentsHome` treats
   * anything it does not recognise as unknown and says nothing.
   */
  state?: string;
}

export interface ApiHealth {
  status: string;
  mode: string;
  core: string;
  version: string;
  database?: ApiHealthDatabase;
  experiment_storage?: ApiHealthExperimentStorage;
}

// POST /api/demo/reset — the guarded example-workspace reset (DemoResetResponse in
// apps/api/isaac_api/routes.py). The SAME shape carries both success (status
// "ok") and a safe refusal (status "refused"), returned at HTTP
// 200/403/409/412/428. Every field is a server-derived count/id; the client renders
// them, it never computes a reset decision.

/** Why the server declined. The five reasons are NOT interchangeable: two of them
 *  are recoverable by looking again, one by typing correctly, and two are dead ends.
 *  `null` on success. Mirrors `DemoResetRefusal` in routes.py. */
export type ApiDemoResetRefusal =
  | 'not_synthetic_only'
  | 'confirmation_required'
  | 'plan_digest_required'
  | 'plan_digest_stale'
  | 'ambiguous_records_present';

/** The confirmed work a reset would discard. Server-DERIVED from persisted state
 *  (the answer log, each example's content versus its original, exported records) —
 *  the client renders these numbers and never estimates one. */
export interface ApiDemoResetAtRisk {
  confirmed_answers: number;
  examples_with_progress: number;
  exported_artifacts: number;
}

export interface ApiDemoResetResult {
  status: 'ok' | 'refused';
  mode: 'preview' | 'execute';
  refusal_reason: ApiDemoResetRefusal | null;
  previous_count: number;
  canonical_count: number;
  legacy_count: number;
  ambiguous_count: number;
  removed_count: number;
  final_count: number;
  canonical_ids: string[];
  removable: { id: string; title: string }[];
  state_counts: Record<string, number>;
  /** The precondition an execute must carry back. Always the CURRENT one, so a
   *  stale refusal already contains the value a fresh attempt needs. */
  plan_digest: string;
  at_risk: ApiDemoResetAtRisk;
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
  // The exported record + sidecar, from the SAME existing `/artifacts` route the
  // export-readiness and evidence bundles already read. It is the only source of
  // an official record's own top-level values and of its `links` block; both are
  // rendered by the record-identity sections on the record screen. `record` is
  // null before export, and null for a fan-out (whose runs each write their own
  // record) — `detail.artifact_refs.reason` is what tells those two apart.
  artifacts: ApiArtifactsResponse;
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
  // NULL, not absent, for a fan-out: both are SINGULAR by name and a record whose
  // runs each export their own official record has several. The type said `?:
  // string` and the wire says `null`, which is how a screen came to test
  // `resp.record && resp.sidecar` and route a successful fan-out export to its
  // `failed` phase.
  record_id?: string | null;
  // P30.6 — safe basenames only, never an absolute server/mount path.
  artifact_refs?: { record_filename: string; sidecar_filename: string } | null;
  // P28.2 — the post-export workflow + downstream-invalidation summary (present
  // on both the success and the gated-failure paths).
  workflow?: ApiWorkflow;
  invalidation?: ApiInvalidation;
  // Present ONLY on the success path of a record with runs. `records` is what THIS
  // export wrote — already-materialised runs are skipped and deliberately absent.
  records?: {
    run_id: string | null;
    run_label: string | null;
    record_id: string | null;
    record_filename: string | null;
    sidecar_filename: string | null;
  }[];
  // The three-way prune outcome. `pruned_record_ids` alone could not distinguish
  // "nothing was orphaned" from "an orphan is KEPT because a surviving record still
  // links to it" (the normal case once two runs share a sample id, and previously
  // invisible) from "a kept record could not be read, so nothing was examined".
  pruned_record_ids?: string[];
  protected_record_ids?: string[];
  prune_declined?: boolean;
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

/**
 * Everything the EXPERIMENT-SCOPED graph needs, fetched concurrently from SEVEN
 * endpoints that all already existed. No route was added or changed for this
 * surface — the graph is a projection of data the record screens already hold,
 * assembled client-side and re-derived per render so it can never be stale.
 *
 * The seven are the union of `RecordBundle` and `EvidenceBundle` minus what the
 * graph does not read: the memory-graph status (a different plane entirely),
 * the pending list (the workflow already reports what is blocking), the audit
 * (post-export coverage, reported on its own screen) and the cited-source
 * previews (file CONTENT, which the graph links to rather than embeds).
 */
export interface ExperimentGraphBundle {
  detail: ApiExperimentDetail;
  groups: ApiDraftGroup[];
  evidence: ApiEvidenceEntry[];
  artifacts: ApiArtifactsResponse;
  validate: ApiValidateResult;
  warnings: ApiWarningsResponse;
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

// --- Runs (Run workspace, Slice A) ---------------------------------------
//
// The wire shapes of the five Run routes, transcribed from the frozen Slice-A
// Run API contract. They are declared here rather than derived from anything on
// the client, because the client is a THIN reader of them: it never computes a
// run's version, its inheritance, or its check verdict.
//
// Two of these types are deliberately loose, and the looseness is a statement
// about what the contract pins rather than laziness:
//
//   * `ApiRunFieldEnvelope.value` is `unknown`. A draft field envelope carries
//     whatever the official schema declares at that path — a string for
//     `context.environment`, a number for `context.temperature_K` — and this
//     module has no business narrowing that.
//   * `ApiRunCheckFinding` is a union including a bare string. The contract
//     freezes `blockers` as `[...]` and does not say what an element is; a type
//     that guessed one shape would make the compiler agree with a guess. See
//     `runFindingText` in `lib/runFields.ts` for how an element that carries no
//     describable text is rendered — as an honest "cannot describe", never
//     dropped.

/** One draft field envelope inside a run: `{value, status, evidence[]}`. */
export interface ApiRunFieldEnvelope {
  value: unknown;
  status?: string;
  evidence?: unknown[];
}

/**
 * How one experiment-level address resolves for this run.
 *
 * `inherited` — the run has no override and reads the experiment's value.
 * `overridden` — the run carries its own value in place of the experiment's.
 * `absent` — neither carries anything at that address.
 */
export type RunInheritedState = 'inherited' | 'overridden' | 'absent';

export interface ApiRunInherited {
  state: RunInheritedState;
  /** What this run actually has at the address (an envelope for a `field:`). */
  payload: unknown;
  /** What the experiment carried when this was resolved. */
  inherited_payload: unknown;
  /** What an override displaced when it was recorded. */
  displaced_payload?: unknown;
  /**
   * THE SERVER'S OWN ANSWER to whether this run may record an override here.
   *
   * It is not derivable on this side and must not be re-derived: the key set of
   * `inherited` is every experiment-level address, while the set the route accepts
   * an override at is narrower (a `field:` must also be in the backend's extractor
   * map). `field:system.domain` is in the first and not the second. A client that
   * guessed would be keeping a second copy of a backend classification, free to
   * drift from it silently.
   *
   * OPTIONAL IN THE TYPE, FAIL-CLOSED AT THE READ. A response without it is a
   * server that cannot answer, and {@link runOverrides.overrideRows} treats that as
   * "not overridable" rather than assuming yes — matching the fail-closed doctrine
   * `EXPERIMENT_OVERRIDABLE_ADDRESSES` states for itself. It is optional only so a
   * fixture or an older response is a type error nobody has to silence, never as
   * licence to omit it.
   */
  overridable?: boolean;
}

export interface ApiRunView {
  id: string;
  experiment_id: string;
  label: string;
  ordinal: number;
  created_utc: string;
  updated_utc: string;
  rev: number;
  /** `"<generation>.<rev>"` — the run's OWN optimistic-concurrency token. */
  version: string;
  record_id: string | null;
  /** Keyed by dotted official path. */
  fields: Record<string, ApiRunFieldEnvelope>;
  /** Keyed by namespaced draft address (`field:sample.material.name`). */
  inherited: Record<string, ApiRunInherited>;
}

export interface ApiRunsResponse {
  runs: ApiRunView[];
  /** The EXPERIMENT's version token — the `If-Match` a run CREATE must carry. */
  experiment_version: string;
}

export interface ApiRunCreated {
  run: ApiRunView;
  /** The experiment's NEW version after the create. */
  experiment_version: string;
}

export interface ApiRunResponse {
  run: ApiRunView;
}

/**
 * What `POST …/runs/{id}/overrides` returns: the refreshed run, and WHEN the
 * override was recorded.
 *
 * `recorded_utc` is the SERVER's clock and is the authoritative time of the act.
 * It is returned only by this operation — the run read path publishes each
 * address's `state`, `payload`, `inherited_payload` and `displaced_payload` and
 * does NOT republish the recorded time — so a screen may show it for a write it
 * just performed and must not claim it for an override it merely read back.
 */
export interface ApiRunOverrideResponse {
  run: ApiRunView;
  override: { address: string; recorded_utc: string };
}

/**
 * What `POST …/runs/{id}/overrides/clear` returns.
 *
 * `cleared: false` is a SUCCESS, not a refusal: clearing an address that carries
 * no override writes nothing and does not advance the run, which is what makes
 * the operation safe to repeat or to retry after a dropped response.
 */
export interface ApiRunOverrideCleared {
  run: ApiRunView;
  cleared: boolean;
}

/** One entry of `blockers` / `errors` — see the note above on why this is a union. */
export type ApiRunCheckFinding =
  | string
  | {
      message?: string;
      question?: string;
      label?: string;
      path?: string;
      id?: string;
    };

export interface ApiRunCheckVerdict {
  ok: boolean;
  errors?: ApiRunCheckFinding[];
  /**
   * WHICH DOCUMENT WAS CHECKED — present on the `official` verdict only, and it was
   * MISSING FROM THIS TYPE WHILE THE SCREEN HARD-CODED "(dry run)".
   *
   * `_validate_unit` (`apps/api/isaac_api/routes.py:3901`) returns `false` whenever
   * the unit is materialised: in that branch it validates the record ALREADY WRITTEN
   * to `records/`, not a candidate. The card said "Official schema (dry run)"
   * unconditionally, so after an export a scientist read errors about a filed
   * artifact as errors about a hypothetical one. Dropping the field from this
   * interface is what made the mislabel invisible to the compiler.
   */
  dry_run?: boolean;
  /**
   * TRUE when no verdict could be reached — distinct from "the schema rejected it".
   *
   * The route's own comment calls this "no verdict, not a schema violation"
   * (`routes.py:3917`), and it still sets `ok: false` to fail closed. Without this
   * flag the only signal was a fixed English sentence in `errors[0].message`, so the
   * card rendered an unreadable artifact as `Check Failed` — a verdict the server
   * explicitly declined to give. `ok` is deliberately still `false`: this makes the
   * REASON legible without turning a non-verdict into a pass.
   */
  unavailable?: boolean;
}

export interface ApiRunCheckResponse {
  ok: boolean;
  draft: ApiRunCheckVerdict;
  official: ApiRunCheckVerdict;
  blockers: ApiRunCheckFinding[];
  /** The run version the check was computed over. It does NOT advance. */
  checked_run_version: string;
}

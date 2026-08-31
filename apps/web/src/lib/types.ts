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
  /** See `ApiDraftField.present` — passed through, never computed from `status`. */
  present?: boolean;
  /** See `ApiDraftField.capture` — passed through, never re-derived. */
  capture?: DraftFieldCapture;
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
export type CompletionInputType = 'hash' | 'text' | 'structured' | 'verdict';

/**
 * The official `measurement.qc.status` enum, mirroring `complete._QC_STATUSES`.
 *
 * WRITTEN HERE RATHER THAN TYPED FREELY because a QC verdict is the one blocker the
 * API refuses unless it arrives as `{status, evidence}` with `status` inside this set
 * — `complete.is_qc_shaped`. A free-text field sent `"valid"` as a bare string, which
 * the server declined, leaving the question open with nothing on screen to say why.
 *
 * The order is the schema's, not a ranking, and `valid` is FIRST but never
 * preselected: the blocker's own text says "there is no default and none is assumed —
 * not even 'valid'", and a preselected control would assume one on the scientist's
 * behalf by doing nothing.
 */
export const QC_VERDICTS = ['valid', 'compromised', 'failed', 'pending'] as const;

export type QcVerdict = (typeof QC_VERDICTS)[number];

/**
 * The exact shape `POST /answers` and `POST /edit` accept for a `qc` answer —
 * `complete.is_qc_shaped`. A bare string is declined by the server and leaves the
 * question open, which is the defect the verdict control exists to prevent.
 */
export interface QcAnswer {
  status: QcVerdict;
  evidence: string;
}

/**
 * The official `descriptors[].kind` and `.source` enums, mirroring
 * `schema/isaac_record_v1.json`. Both are REQUIRED by the schema and neither is
 * preselected in the form: a descriptor is a scientific claim, and choosing its kind
 * for the scientist would be the app asserting something about their measurement.
 */
export const DESCRIPTOR_KINDS = [
  'absolute',
  'differential',
  'categorical',
  'similarity',
  'model',
  'theoretical_metric',
] as const;

export const DESCRIPTOR_SOURCES = ['auto', 'manual', 'imported'] as const;

/**
 * Canonical spectroscopy descriptor class tokens, transcribed from
 * `vocabulary/descriptor_class.json`.
 *
 * OFFERED AS SUGGESTIONS, NEVER ENFORCED — and the distinction is that file's own:
 * "The official schema + portal validator remain authoritative; this file is an
 * extraction/authoring aid only." The schema constrains `name` by PATTERN, not by an
 * enumeration, so a name outside this list is perfectly valid and the control must
 * accept it. Only the `spectroscopy` class is listed because the MVP scope is the
 * XANES / characterization path; offering electrochemistry tokens would suggest a
 * capability this build does not have.
 */
export const DESCRIPTOR_NAME_SUGGESTIONS = ["edge_position", "edge_shift", "inflection_point_energy", "oxidation_state", "white_line_energy", "white_line_intensity"] as const;

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
  /**
   * Verbatim from `draft.pending[]` — and `null` when the stored entry carries none.
   *
   * The server authors no question text it was not given, so an entry with a kind and
   * no prose arrives as `null`. Widened rather than defaulted to `''`: the two render
   * identically (React draws nothing for either), and an empty string would be this
   * client asserting the draft holds an empty question when it holds no question at all.
   *
   * ~~"The KIND label above the prose carries the identity in that case."~~ **STRUCK —
   * measured false, and it was the stated mitigation for the widening.** `label` reaches
   * exactly ONE render site, `GuidedPrompt.tsx:443`, and it is an `aria-label` on the
   * input. Nothing VISIBLE above the prose carries it, so a prose-less blocker renders
   * an empty `<h2 className="guided-question">` on the prompt card. What IS true, and is
   * a different surface: the QUEUE rows go through `adapt.pendingSummary`, whose
   * `KIND_LABEL[item.kind] ?? item.question ?? item.id` ladder does name such an entry —
   * so it is identified in the list and unnamed on the card. Giving the card a visible
   * label is a `GuidedPrompt.tsx` change and is named as residue rather than made here.
   */
  question: string | null;
  label: string; // short Title Case label for the question
  path: string; // JSON path token
  about?: string;
  context?: string; // sentence-case context for the question card
  inputType: CompletionInputType;
  /**
   * The run that OWNS this question, when a run does.
   *
   * `GET /pending` tags every run-sourced entry, because once a record has runs each
   * run is a record of its own and the record-level answer route refuses a run-owned
   * key with `409 belongs_to_a_run`. The screen carries this through so a scientist
   * answering a question never has to know which entity it belongs to.
   */
  runId?: string;
  runLabel?: string;
  /**
   * The IDENTITY key, unique across owners — unlike {@link PendingBlocker.id}, which is
   * the blocker KIND and is the key that goes in the `answers` body.
   *
   * Three runs each needing a spectrum produce three blockers whose `id`, `question`
   * and `label` are byte-identical. Every piece of per-question state on the completion
   * screen must therefore be keyed by THIS: staged input, the skipped set, React keys,
   * and the "was this applied?" test. Keying by `id` was measured reporting an answer
   * as NOT APPLIED because another run's identical entry was still in the list, and
   * sharing one typed value across every run's question.
   */
  key: string;
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
  /**
   * Set by the session scrubber when it withheld this message's `text` from browser
   * storage — the text contained a credential, an absolute path, or a long hex
   * digest, and is genuinely gone. The flag exists so the archived message renders as
   * withheld instead of as an EMPTY bubble, which is what it did before.
   *
   * DECLARED HERE FOR COMPLETENESS AND READ ELSEWHERE: `ConversationMessage` takes
   * `assistantSession.Msg`, which carries its own copy, so nothing consumes this
   * member today. An independent review flagged it as dead; it is kept rather than
   * removed because `AssistantMessage` is the shape a precomposed answer uses and a
   * withheld answer is representable in it — but the comment now says which
   * declaration the renderer actually reads, instead of leaving that to be guessed.
   */
  textWithheld?: boolean;
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

/**
 * A runner stage's state.
 *
 * `failed` EXISTS BECAUSE ITS ABSENCE WAS A DEFECT. The API reports each step's own
 * `ok`, and `demoStepsToStages` used to map `ok: false` to `current` — which
 * `StagedRunner` then collapsed into `done` and rendered with this app's success
 * check mark. So a step the server had reported as FAILING got a tick, beside its
 * own failure text ("official schema valid: False"). The failure signal was
 * computed and then discarded, and the amber treatment that would have shown it had
 * been removed earlier along with a dead CTA.
 */
export type RunnerStageState = 'done' | 'current' | 'upcoming' | 'failed';

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

/**
 * WHERE — IF ANYWHERE — A VALUE MAY BE ENTERED AT ONE FIELD PATH.
 *
 * Served per row by `GET /api/experiments/{id}/draft`, derived in `routes.capture_facts`
 * from the same three sets the write routes gate on. **Never re-derived in this client**,
 * for the reason `UnmappedNotesPanel`'s `valueWriteHint` already documents: a client-side
 * list of "which paths take a value" is free to drift the moment the server's derivation
 * changes, and nothing would fail.
 *
 * THE THREE BOOLEANS ARE THREE DIFFERENT OPERATIONS AND MUST NOT BE COLLAPSED. Measured
 * over HTTP across all 26 skeleton paths and all six write routes: 2 are
 * `record_writable`, 5 are `run_field_writable`, 13 are `run_overridable`, and 7 are none
 * of them. A row where all three are false must render no control at all — that is the
 * defect `CLAUDE.md` §11 records ("a panel told the scientist to enter a value on 25
 * fields, and 7 accept none"), and this shape exists so it cannot recur.
 *
 * `run_overridable` IS NOT "the record's value can be entered here". An override records
 * ONE RUN's divergence from a record-level value; it is not a way to say what the record
 * is. Copy built on it must say "on a run".
 */
export interface DraftFieldCapture {
  /** This build's experiment/run classification, or `null` if it did not say. */
  level: 'experiment' | 'run' | 'unclassified' | null;
  /** `POST /api/experiments/{id}/answers`, corrected at `.../edit`. */
  record_writable: boolean;
  /** `PATCH /api/experiments/{id}/runs/{run_id}` — a run's own field. */
  run_field_writable: boolean;
  /** `POST .../runs/{run_id}/overrides` — one run's divergence, not the record's value. */
  run_overridable: boolean;
  /** The official schema's own closed set, where it declares one. Never invented here. */
  choices: string[] | null;
  /**
   * The vendored schema namespace this path sits in that declares NO members, or `null`.
   *
   * It exists so one sentence is not said about two different things. Seven skeleton
   * paths accept a value from no route: the six `system.configuration.*`, whose scope is
   * an OPEN SCIENTIFIC QUESTION because the schema enumerates no members for that
   * namespace, and `timestamps.created_utc`, which is a declared property the exporter
   * stamps and whose scope is not an open question at all. `workspace.field_level`'s own
   * docstring warns against pooling them; this is how the copy avoids it.
   */
  open_namespace?: string | null;
}

export interface ApiDraftField {
  path: string;
  label: string;
  value: unknown;
  status: FieldStatus;
  evidence_count: number;
  source_types: SourceType[];
  /**
   * Whether the draft actually CARRIES an envelope at this path.
   *
   * `false` is the group skeleton: the shape of a value this record does not have,
   * served so a created record renders its fields instead of nothing. A `false` row is
   * not a field the record gained, and no consumer may report it as one.
   *
   * Optional so a fixture written before the server served it still type-checks;
   * `undefined` is read as "the server did not say", and every consumer that must know
   * treats that the same way it treats a `missing` status.
   */
  present?: boolean;
  capture?: DraftFieldCapture;
}

export interface ApiDraftGroup {
  title: string;
  fields: ApiDraftField[];
}

export interface ApiDraftResponse {
  groups: ApiDraftGroup[];
  /**
   * The record-level BLOCK payloads, keyed by the same namespaced address the write
   * operations take (`block:attribution`, `block:tags`). `null` means the record
   * carries nothing there.
   *
   * THEY ARE NOT `fields`, so they can appear in no group — and a client that could
   * read a facility name but not the contributors beside it would have to overwrite a
   * block it had never seen in order to add to it. The value is whatever is stored,
   * unshaped: `CLAUDE.md` §11's read-path doctrine keeps a malformed persisted block
   * readable, and a client about to REPLACE one needs to see what it is replacing.
   */
  record_blocks: Record<string, unknown>;
}

export interface ApiDemoAnswer {
  // string sha256 for assets; structured object for series/descriptor blockers.
  value: unknown;
  label: string; // "Example answer"
  provenance?: ExampleAnswerProvenance;
}

/**
 * ONE ENTRY OF `GET /pending`, INCLUDING THE ONE THAT IS NOT A QUESTION.
 *
 * `id`, `kind` and `question` are nullable because the server serves an entry it cannot
 * present as an answerable question rather than failing the whole request: one stored
 * blocker in, one served entry out, marked `unavailable: true` with an
 * `unavailable_reason` saying why, and the entry stays COUNTED so the record keeps
 * being refused. See `serialize._unreadable_blocker` for the measured 500s this
 * replaced and for the alternatives that were rejected.
 *
 * TWO DIFFERENT CASES ARRIVE ON THAT ONE FLAG, and conflating them was a shipped
 * defect:
 *
 *  - **Unreadable.** The stored entry is not a question at all (a number, a string, a
 *    mapping whose `kind` is unhashable). Nothing is invented — every field is `null`
 *    — and `unavailable_reason` names the SHAPE that was found.
 *  - **Readable but unanswerable.** The stored entry carries prose and no `kind`. The
 *    server read it, so `question` IS present; but the answer key is the kind, so there
 *    is no key to submit under, and the reason says exactly that. Rendering
 *    "could not be read" over this entry — while the same response carried the
 *    scientist's own sentence — is the defect `pendingSummary` was corrected for.
 *
 * A consumer that needs an answerable question uses `adapt.isAnswerablePendingItem`,
 * which narrows to `ApiAnswerablePendingItem` below. Widening these three fields rather
 * than declaring them non-null is deliberate: it makes every consumer decide what it
 * does with an unreadable entry instead of discovering `"Null"` on screen. **That claim
 * was measurably NOT true for one consumer** — `assistantComposer.explain_pending_item`
 * interpolated `${item.question}` under a comment asserting the field was non-optional,
 * which the widening commit had itself deleted, and `tsc` passed because a template
 * literal accepts `null`. Widening a type does not force a template literal to handle
 * it; only a test does. `assistant-composer-null-safety.test.ts` is that test.
 */
export interface ApiPendingItem {
  id: string | null; // uri for assets, else kind; `null` when `unavailable`
  kind: BlockerKind | null;
  question: string | null;
  about?: string | null;
  // Example-scope records ONLY. `null`/absent on every ordinary record.
  demo_answer?: ApiDemoAnswer | null;
  // `null` on an unreadable entry: no inferability decision is made about a blocker
  // this server could not read, and asserting one would be inventing a refusal about a
  // field nobody can name. Every other entry carries the real decision.
  inferability?: Inferability | null;
  // Present when a RUN owns this question. `null` for a record-level one.
  run_id?: string | null;
  run_label?: string | null;
  // Unique across owners; `id` is not. See `PendingBlocker.key`.
  blocker_key?: string | null;
  /**
   * THE SERVER'S DISCRIMINATOR for an entry it could not read as a question. Optional
   * because it is absent on every ordinary entry — its presence, not a pattern of
   * nulls, is what a consumer branches on.
   */
  unavailable?: boolean;
  /**
   * The server's own words for WHAT SHAPE was found — never the stored value, which is
   * arbitrary content and is deliberately never echoed back.
   */
  unavailable_reason?: string | null;
}

/**
 * A pending entry that IS a question: `id` and `kind` proved present, and `question`
 * proved to be prose or absent.
 *
 * Produced only by `adapt.isAnswerablePendingItem`. Everything that renders a prompt,
 * derives an input type, or submits an answer takes this type.
 *
 * ~~"so an unreadable entry cannot reach any of them by accident — it is a compile
 * error rather than a `"Null"` label on screen"~~ — **struck, because it was FALSE FOR
 * `question` in the commit that wrote it, and the falsity was worse than the label it
 * described.** The narrowing covered `id` and `kind` only, so
 * `{"kind": "qc", "question": {"a": 1}}` — an entry the API genuinely accepts an answer
 * for (measured: `POST /answers` with key `qc` answers **200**) — satisfied the
 * predicate and put an OBJECT into `<h2>{blocker.question}</h2>`. React throws
 * "Objects are not valid as a React child", there is no ErrorBoundary anywhere in this
 * application, and the whole page blanks. A `null` label is a bad row; a thrown render
 * is no application.
 *
 * `question` is `string | null` here rather than `string`, and that is deliberate
 * rather than a leftover: a stored entry may legitimately carry a kind and no prose,
 * and the server authors none it was not given. What the type now guarantees is that it
 * is never anything ELSE. `undefined` is admitted for recorded fixtures that omit the
 * key entirely.
 */
export type ApiAnswerablePendingItem = ApiPendingItem & {
  id: string;
  kind: BlockerKind;
  question: string | null;
};

/**
 * THE SELF-DESCRIPTION A BOUNDED QUESTION LIST CARRIES.
 *
 * A record's open questions grow with its runs — measured at 1,000 runs,
 * `GET /pending` was 1,772,692 bytes over 3,000 entries and a single
 * `POST /runs/{id}/answers` was 1,773,294. So both can now be bounded, and this block
 * is what makes bounding SAFE: it states how many questions there are, how many came
 * back, how many were WITHHELD, and whether the list is the whole set. A client can
 * never mistake a page for the record's state.
 *
 * `record_total` is not redundant beside `total`: under a `run_id` filter `total` is
 * that run's count, and a screen rendering it as "N still to confirm" would understate
 * the record. Unfiltered the two are equal by construction.
 */
export interface ApiPendingPage {
  /** Open questions matching the filter (the whole record when unfiltered). */
  total: number;
  /** Entries in `pending`. */
  returned: number;
  offset: number;
  /** The bound the server applied, or `null` when none was. */
  limit: number | null;
  /** `total - offset - returned`, never negative. `> 0` means this is NOT the set. */
  withheld: number;
  /** `pending` IS the whole matching set. The signal to key "nothing left" off. */
  complete: boolean;
  run_id: string | null;
  /** The WHOLE record's open question count, whatever the filter. */
  record_total: number;
}

export interface ApiPendingResponse {
  pending: ApiPendingItem[];
  /**
   * Present ONLY on a BOUNDED read — one that sent `run_id`, `offset` or `limit`.
   * An unbounded `GET /pending` is byte-identical to what it always was, deliberately:
   * a consumer that never learned to page is handed nothing new to interpret, and is
   * never handed a page it might read as the whole set. Absent therefore MEANS
   * complete; it is not an unknown.
   */
  pending_page?: ApiPendingPage;
}

export interface ApiValidateResult {
  ok: boolean;
  errors: { path: string; message: string }[];
  schema: string; // "ISAAC v1.05"
  dry_run: boolean; // true until the record is exported
  /**
   * DID THE OFFICIAL VALIDATOR PRODUCE THE `errors` BESIDE THIS VERDICT?
   *
   * The discriminator four surfaces needed and none of them had. `dry_run` does not
   * answer it — a dry-run PASS does require `validate_official`, a dry-run FAILURE may
   * never have reached it, because `export.py` returns `official_report=None` on the
   * two paths that precede it (a failed no-guessing report, and ISAAC's own
   * anchored-pattern exactness gate, whose findings it folds into `draft_report`). So
   * `errors` carried three kinds of finding under one key and `schema: "ISAAC v1.05"`
   * was stamped over all of them.
   *
   * `false` IS NOT A VERDICT. It says the vendored schema did not speak — never that
   * it refused. `CLAUDE.md` §1 makes that schema not ours to speak for, and §12: "no
   * surface may report an exactness refusal as an official-schema error."
   *
   * DO NOT READ THIS FIELD DIRECTLY. `lib/officialAttribution.ts` is the one place it
   * is read, and `__tests__/official-attribution-discriminator.test.ts` fails if a
   * second file reads it. Fixing this defect surface-by-surface has already recurred
   * four times; one decision point is the fix.
   *
   * Optional because a response predating the field carries neither it nor any
   * substitute — `officialFindingSource` degrades to the old ordering rule and, where
   * even that is silent, answers `unnamed` rather than guessing.
   */
  official_validator_ran?: boolean;
  /**
   * NO VERDICT COULD BE PRODUCED, AT THE TOP LEVEL — the same claim the `runs[]`
   * entries below have always carried, and it was MISSING here while the route
   * returned the state it describes.
   *
   * `post_validate` returns it on two branches: an exported record whose written
   * artifact cannot be read, and an exception during the dry run. Both were
   * previously indistinguishable from "one of ISAAC's own gates refused", because
   * `official_validator_ran: false` is true of a gate refusal too. Absent on every
   * verdict that IS a verdict; `ok` stays `false` either way, so this explains a
   * refusal without softening it. Read through `officialFindingSource`.
   */
  unavailable?: boolean;
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
    // PER UNIT, describing THAT unit's `errors`. The top-level flag above describes
    // the top-level `errors`, which are the FIRST FAILING unit's — so for a specific
    // run's findings, read the run's own flag. See `lib/officialAttribution.ts`.
    official_validator_ran?: boolean;
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
  /**
   * THE STAGE-2b RUN-PROJECTION BLOCK. Declared because the route serves it and a
   * type that does not describe what is on the wire is a type that will be
   * believed instead of the wire. Nothing in this application reads it yet — it is
   * additive, and nothing breaks without it.
   *
   * `authoritative` IS CONFIGURATION AND `last_pass` IS AN OBSERVATION, and they
   * are deliberately not merged. The first is the `ISAAC_RUN_ROWS_AUTHORITATIVE`
   * kill switch, read on every request so an operator's edit takes effect without
   * a redeploy. The second is the per-experiment state distribution the most
   * recent classifying hydration pass measured.
   *
   * `last_pass: null` MEANS NO PASS HAS CLASSIFIED ANYTHING — which is NOT the
   * same claim as a pass that classified none, and a renderer that collapsed the
   * two would report a measurement that was never taken. It is also `null` while
   * the kill switch is off, deliberately: labelling disabled experiments
   * `never_projected` would report a state the reader never measured.
   *
   * COUNTS ONLY: no ids, no titles, no record content. Keys are the five outcomes
   * of the contract's four states plus `mismatch`; typed as an index signature
   * because a future outcome must be a value a client can ignore rather than a
   * shape change. AND NOTHING HERE MAY BE READ AS "THE CUTOVER IS COMPLETE" — an
   * all-`unavailable` or all-`never_projected` distribution is the reader working
   * correctly, not the reader being off.
   *
   * Optional for the same reason the block above it is: a build predating it, and
   * a health body the client failed to fetch, simply have none.
   */
  run_projection?: {
    authoritative: boolean;
    last_pass: Record<string, number> | null;
  };
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

/** Why the server declined. The six reasons are NOT interchangeable: two of them
 *  are recoverable by looking again, one by typing correctly, and three are dead ends.
 *  `null` on success. Mirrors `DemoResetRefusal` in routes.py.
 *
 *  `malformed_records_present` is deliberately NOT a variant of `plan_digest_stale`,
 *  even though the server used to answer the latter for it: `plan_digest_stale` means
 *  "preview again and retry", and for a malformed record the retry can never succeed.
 *  `malformed_ids` names the records. */
export type ApiDemoResetRefusal =
  | 'not_synthetic_only'
  | 'confirmation_required'
  | 'plan_digest_required'
  | 'plan_digest_stale'
  | 'ambiguous_records_present'
  | 'malformed_records_present';

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
  /** The ids whose stored document the reset's two readers disagree about; `[]` on
   *  every other outcome. Server-derived, ids only — never a title, which for a
   *  malformed document comes from the read path's fallbacks and not from the
   *  document. */
  malformed_ids: string[];
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
  /**
   * The recomputed question list — BOUNDED, and read `pending_page` beside it.
   *
   * At most the first `PENDING_WINDOW` (50) of the record's open questions, PLUS every
   * still-open question of the unit this write addressed. That anchor is what keeps
   * `answerWasApplied` sound: it decides "did my answer land?" by asking whether its
   * question is still in this list, and on a 1,000-run record a plain head-of-list
   * window would not contain run 900's question at all — so an answer the core REFUSED
   * would have read as applied and the screen would have shown a "Confirmed by You"
   * chip over a value the record does not hold.
   */
  pending: ApiPendingItem[];
  /**
   * ALWAYS present here, unlike on `ApiPendingResponse`, and the asymmetry is the
   * point. This response is bounded whether the caller asked or not, so it must say so
   * unconditionally — including when the window IS the whole set (`complete: true`),
   * so a client never has to infer completeness from an absent key.
   */
  pending_page: ApiPendingPage;
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

/**
 * `GET /experiments/{id}/runs` — a PAGE of runs, and the four numbers that say
 * what the page is a page OF.
 *
 * THE TWO TOTALS ARE DIFFERENT NUMBERS AND MUST NEVER BE SHOWN AS ONE. `total`
 * is how many runs EXIST in the record and ignores `q` and the filters
 * entirely; `matched` is how many satisfy the criteria the client sent. They
 * are equal when nothing is filtering, which is exactly why conflating them is
 * easy to do and invisible until someone types in the search box — at which
 * point "320 runs" silently becomes "87 runs" and a scientist reads a filtered
 * count as the size of their record.
 *
 * `returned` is stated rather than left to be derived from `runs.length`, so a
 * truncation bug surfaces as a disagreement between two numbers instead of
 * being invisible; `offset` is echoed so a client can tell which window it got.
 *
 * OMITTING `limit` STILL RETURNS EVERYTHING — paging is something a caller asks
 * for, and the server-side contract note in `routes.py` is explicit that
 * `RUN_PAGE_MAX` bounds one RESPONSE and is not a limit on how many runs a
 * record may have.
 */
export interface ApiRunsResponse {
  runs: ApiRunView[];
  /** The EXPERIMENT's version token — the `If-Match` a run CREATE must carry. */
  experiment_version: string;
  /** How many runs EXIST in this record. Ignores `q` and every filter. */
  total: number;
  /** How many runs match the criteria that were sent. Equals `total` when none were. */
  matched: number;
  /** How many runs are in THIS page. */
  returned: number;
  /** The offset this page was read from, echoed. */
  offset: number;
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
 * What `POST …/runs/{id}/remove` returns.
 *
 * `ordinals_compacted` IS ON THE WIRE ON PURPOSE, and it is always `false` today.
 * The remaining runs keep their numbers, so a record whose runs were 1, 2 and 3
 * reads 1 and 3 afterwards. A client that had to infer that from two list reads
 * could not tell "they were not renumbered" apart from "this build forgot to
 * renumber them", and the gap is visible on screen.
 *
 * `asset_references_dropped` names the asset ids this run cited and no longer
 * does. The record's asset LIBRARY keeps every entry — an asset can be cited by
 * other runs and by the record itself — so this is a list of associations that
 * ended, never of files that were deleted. No file is deleted by anything here.
 */
export interface ApiRunRemoved {
  removed_run_id: string;
  removed_run_label: string;
  removed_run_ordinal: number;
  /** NAMED rather than counted, exactly as the asset removal names its runs. */
  asset_references_dropped: string[];
  remaining_run_count: number;
  ordinals_compacted: boolean;
  /** The experiment's NEW version after the removal. */
  experiment_version: string;
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
      /**
       * THE SERVER'S OWN BLOCKER TAXONOMY, on `blockers` entries only.
       *
       * `post_run_check` builds `blockers` by spreading
       * `serialize.pending_to_list(...)["pending"]`, and every element of that list
       * carries `kind` verbatim from the draft's own `pending[]` entry — the same
       * `BlockerKind` (`'asset' | 'series' | 'descriptor' | 'edge'`) that
       * `ApiPendingItem` already declares for the record-level `/pending` route.
       *
       * IT IS DECLARED OPTIONAL AND MUST BE READ AS SUCH. The frozen contract text
       * for this route says only that every element carries a non-empty `message`;
       * it does not specify the rest of the element, and `_blocker_message`'s last
       * branch exists precisely for a persisted blocker that records no `kind` at
       * all. So a reader groups by it when it is there and says nothing when it is
       * not — it is never defaulted, and no kind is inferred from the message text.
       * Absent on `errors`/`warnings` entries, which are `{path, message}` pairs.
       */
      kind?: string;
    };

export interface ApiRunCheckVerdict {
  ok: boolean;
  errors?: ApiRunCheckFinding[];
  /**
   * THE NO-GUESSING VALIDATOR'S OWN ADVISORY CHANNEL — on the `draft` verdict only,
   * and it has been on the wire the whole time while this type omitted it.
   *
   * `post_run_check` builds `draft_verdict` with THREE keys — `ok`, `errors` and
   * `warnings` — from `DraftReport.errors` and `DraftReport.warnings`
   * (`routes.py`, and the same shape on its own exception branch). Only the first
   * two were declared here, so TypeScript actively prevented a client from reading
   * the third: the same mechanism that hid `dry_run` and `unavailable` below, and
   * the same one that hid `schema_ok`/`exactness_errors` from the Validator until
   * a surface shipped a false claim on top of the gap.
   *
   * IT CANNOT GATE ANYTHING, and that is the reason it must be shown APART from
   * `errors` rather than beside them. `DraftReport.ok` is `not self.errors` — it
   * does not read this list at all — so `export_draft` refuses on `errors` and
   * never on a warning. Rendering the two under one heading would make a
   * non-gating note read as a blocker; rendering neither is what shipped.
   *
   * Optional because the `official` verdict legitimately carries no such key.
   */
  warnings?: ApiRunCheckFinding[];
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
  /**
   * DID THE OFFICIAL VALIDATOR PRODUCE THE `errors` BESIDE THIS VERDICT?
   *
   * The discriminator four surfaces needed and none of them had. `dry_run` does not
   * answer it — a dry-run PASS does require `validate_official`, a dry-run FAILURE may
   * never have reached it, because `export.py` returns `official_report=None` on the
   * two paths that precede it (a failed no-guessing report, and ISAAC's own
   * anchored-pattern exactness gate, whose findings it folds into `draft_report`). So
   * `errors` carried three kinds of finding under one key and `schema: "ISAAC v1.05"`
   * was stamped over all of them.
   *
   * `false` IS NOT A VERDICT. It says the vendored schema did not speak — never that
   * it refused. `CLAUDE.md` §1 makes that schema not ours to speak for, and §12: "no
   * surface may report an exactness refusal as an official-schema error."
   *
   * DO NOT READ THIS FIELD DIRECTLY. `lib/officialAttribution.ts` is the one place it
   * is read, and `__tests__/official-attribution-discriminator.test.ts` fails if a
   * second file reads it. Fixing this defect surface-by-surface has already recurred
   * four times; one decision point is the fix.
   *
   * Optional because a response predating the field carries neither it nor any
   * substitute — `officialFindingSource` degrades to the old ordering rule and, where
   * even that is silent, answers `unnamed` rather than guessing.
   */
  official_validator_ran?: boolean;
}

export interface ApiRunCheckResponse {
  ok: boolean;
  draft: ApiRunCheckVerdict;
  official: ApiRunCheckVerdict;
  blockers: ApiRunCheckFinding[];
  /** The run version the check was computed over. It does NOT advance. */
  checked_run_version: string;
}

/*
 * --- Unmapped Notes ----------------------------------------------------------
 *
 * Content a scientist captured that has no confident schema home. The wire shape
 * is `isaac_api/notes.py`'s `Note.to_state()` plus `display_text`.
 *
 * THE FOUR CONSTANTS ARE PART OF THE TYPE ON PURPOSE. They are typed as their
 * literal `false` / `'unmapped_note'` rather than as `boolean` / `string`, so a
 * component that tries to branch on "is this note a confirmed value?" is a
 * compile error rather than a branch that can never be taken. The server serialises
 * them for the same reason: a JSON reader cannot see a class invariant.
 */

/** The four review states. `dismissed` is a STATE — there is no delete. */
export type ApiNoteState = 'unreviewed' | 'mapped' | 'kept' | 'dismissed';

/** The acts that appear in a note's history. `capture` opens every note. */
export type ApiNoteAction = 'capture' | 'map' | 'edit' | 'keep' | 'dismiss';

/** One act in a note's life. Append-only; nothing rewrites an entry. */
export interface ApiNoteTransition {
  action: ApiNoteAction;
  at: string;
  /** The state before this act. `null` only for `capture`. */
  from_state: ApiNoteState | null;
  to_state: ApiNoteState;
  /** For `map`: the path the scientist named. Never inferred. */
  field_path: string | null;
  /** For `edit`: the exact wording this act replaced. Nothing is lost. */
  superseded_text: string | null;
  /** For `dismiss`: the reason, when one was given. Never composed for them. */
  reason: string | null;
}

export interface ApiNote {
  id: string;
  experiment_id: string;
  /** The run this note belongs to WHEN KNOWN. Never inferred from the only run. */
  run_id: string | null;
  source: string;
  /** THE VERBATIM CAPTURE. Never trimmed, normalised or truncated. */
  text: string;
  /** A corrected wording stored BESIDE `text`, never replacing it. */
  revised_text: string | null;
  captured_utc: string;
  state: ApiNoteState;
  /**
   * The path something DETERMINISTIC proposed, with the rule that produced it.
   * `null` means nothing proposed a home — never a plausible-looking guess.
   */
  candidate_field_path: string | null;
  candidate_rule: string | null;
  /** The path a SCIENTIST named. Distinct from the machine's proposal above. */
  mapped_field_path: string | null;
  history: ApiNoteTransition[];
  /** Always this literal. Deliberately not one of the draft field statuses. */
  status: 'unmapped_note';
  /** Always `false`. Typed as the literal so no code can branch on it being true. */
  verified: false;
  is_evidence: false;
  is_field_value: false;
  /** `revised_text` when there is one, else `text`. A convenience, not a substitute. */
  display_text: string;
}

/**
 * `GET /experiments/{id}/notes`.
 *
 * `total` is how many notes EXIST and ignores the `state` filter; `returned` is
 * how many are in this response. They are different numbers for the same reason
 * `ApiRunsResponse`'s two totals are, and a filtered list that showed `returned`
 * as the record's size would let a scientist read "no notes" off a record that
 * holds several.
 */
export interface ApiNotesResponse {
  notes: ApiNote[];
  total: number;
  returned: number;
  by_state: Record<ApiNoteState, number>;
  /**
   * Stored entries this build could not read. They are preserved verbatim in the
   * record and COUNTED rather than rendered, because their content cannot be
   * reported without inventing it. Showing zero while the record holds some would
   * be the silent discard this feature exists to end.
   */
  unreadable_entries: number;
  /** The server's own list of paths a note may be mapped to. Never transcribed here. */
  mappable_field_paths: string[];
  /**
   * The SUBSET of those a write route in this build accepts a value at — 18 of the 25
   * at time of writing. Mapping and entering a value are different acts, and a client
   * that tells a person to do the second must know whether it is possible.
   */
  value_writable_field_paths: string[];
  /**
   * The sub-subset of THOSE that a RECORD-level operation accepts — 1 of the 18 at
   * time of writing (`system.technique`). A path in it can be given a value on a
   * record with no runs; a path outside it needs a run first. It exists because
   * "the value is entered on a run of this record" was true of every writable path
   * when that copy was written and stopped being true when the record-level enum
   * write shipped, and a client cannot tell WHICH from the wider subset alone.
   */
  /*
   * OPTIONAL ON PURPOSE, corrected 2026-08-30. This was declared required while
   * `UnmappedNotesPanel.tsx` reads it `?? []` "because this key is newer than the
   * others: a server that predates it must degrade". Under a required type that
   * branch is unreachable and the type and the guard disagreed about the contract.
   * The guard is the one that is right — the key IS newer — so the type follows it.
   */
  record_writable_field_paths?: string[];
  sources: string[];
  /** The EXPERIMENT's version token — the `If-Match` every note write must carry. */
  experiment_version: string;
}

export interface ApiNoteCaptured {
  note: ApiNote;
  experiment_version: string;
}

export interface ApiNoteResponse {
  note: ApiNote;
}

export interface ApiNoteReviewed {
  note: ApiNote;
  experiment_version: string;
}

/* --------------------------------------------------------------------------
 * Evidence conflicts, and the ONE recorded human decision about each.
 *
 * `GET /experiments/{id}/conflicts` and `POST .../conflicts/resolve`. Every shape
 * here is the server's, transcribed from `apps/api/isaac_api/conflict_resolution.py`
 * and the two route handlers; nothing in this block is computed on this side.
 *
 * THE ONE THING A READER OF THESE TYPES MUST NOT INFER. A resolution is a record
 * of WHICH competing answer a person stands behind. It is NOT the field's value,
 * NOT an evidence entry, and recording one changes no scientific content — the
 * backend states this in three places and serialises `is_field_value` and
 * `is_evidence` on the wire so the guarantee survives the boundary. They are typed
 * as the literal `false` below so no code on this side can branch on either being
 * true.
 * ------------------------------------------------------------------------ */

/** `resolved` — a person chose. `deferred` — a person looked and declined to. */
export type ApiResolutionOutcome = 'resolved' | 'deferred';

/**
 * Whether the chosen value was one of the recorded answers or a new one.
 *
 * The two are DIFFERENT CLAIMS and the backend refuses to collapse them: "I picked
 * the second citation" and "all the citations are wrong and the value is this" are
 * not the same statement, and a value nothing asserted cannot be labelled
 * `candidate`.
 */
export type ApiResolutionChosenFrom = 'candidate' | 'edited';

/**
 * The four derived states. ONLY `current` clears a conflict.
 *
 * `stale` is a `resolved` decision made over a DIFFERENT set of competing answers —
 * more competing evidence has arrived since — so the address is conflicting again
 * and the superseded decision is kept and disclosed rather than deleted.
 * `deferred` leaves the conflict standing by definition.
 */
export type ApiResolutionState = 'absent' | 'current' | 'stale' | 'deferred';

/** The safe source projection: a type, and a locator when there is a safe one. */
export interface ApiConflictSource {
  source_type: string;
  locator?: string;
}

/**
 * One competing answer, WITH the citations that assert it.
 *
 * Grouped by value rather than listed per evidence entry, because the conflict
 * rule counts DISTINCT answers: two citations asserting the same value are one
 * candidate, and listing them twice would show a scientist a choice between
 * identical options.
 *
 * `evidence_count` AND `sources.length` CAN DISAGREE, and that is disclosed rather
 * than hidden. The safe projection skips an entry with no `source_type` — there is
 * nothing safe to name — so a candidate can read `evidence_count: 1` with
 * `sources: []`. `uncited_evidence_count` is exactly that difference, stated, so a
 * reader never concludes a citation was withheld.
 */
export interface ApiConflictCandidate {
  /** The stable text the conflict rule compares. Not for display. */
  canonical: string;
  /** The answer as it is stored. Send THIS back as `chosen_value` for a candidate. */
  value: unknown;
  evidence_count: number;
  uncited_evidence_count: number;
  sources: ApiConflictSource[];
}

/** One act in a decision's life. Appended, never rewritten. */
export interface ApiResolutionTransition {
  action: 'record' | 'revise';
  at: string;
  /** The outcome before this act. `null` only for the opening `record`. */
  from_outcome: ApiResolutionOutcome | null;
  to_outcome: ApiResolutionOutcome;
  /** What a revision superseded, so no decision is lost. */
  superseded_chosen_value: unknown;
  /** The competing set that superseded value was chosen from. */
  superseded_competing_digest: string | null;
}

/** One recorded decision, with its whole history and its DERIVED state. */
export interface ApiConflictResolution {
  resolution_id: string;
  address: string;
  run_id: string | null;
  outcome: ApiResolutionOutcome;
  /** `null` for `deferred`, which carries no choice at all. */
  chosen_value: unknown;
  chosen_from: ApiResolutionChosenFrom | null;
  /** The competing answers AT THE MOMENT OF THE DECISION, canonicalised. */
  competing_values: string[];
  competing_digest: string;
  rationale: string | null;
  /** The canonical username when a trusted boundary established one, else `null`. */
  subject: string | null;
  trust_basis: string;
  recorded_utc: string;
  history: ApiResolutionTransition[];
  /** Always `false`. Typed as the literal so nothing can branch on it being true. */
  is_field_value: false;
  /** Always `false`. A decision about citations is not itself a citation. */
  is_evidence: false;
  /** DERIVED on every read against the address's CURRENT competing set. */
  state: ApiResolutionState;
  stale: boolean;
  attributed: boolean;
}

/**
 * One conflicting address.
 *
 * AN ALREADY-DECIDED ADDRESS IS STILL LISTED. Nothing in this API removes an
 * evidence entry, so the competing citations remain stored forever and the address
 * goes on classifying as conflicting; hiding it would hide the decision along with
 * the disagreement. `resolution_state` is what a reader branches on, never the
 * absence of a row.
 */
export interface ApiConflict {
  address: string;
  /** `null` when the address belongs to the record's own fields. */
  run_id: string | null;
  candidates: ApiConflictCandidate[];
  distinct_value_count: number;
  evidence_count: number;
  /** This entry's stored evidence was only PARTLY readable. */
  unavailable: boolean;
  /** The server's own deterministic sentence. It quotes no value. */
  explanation: string;
  resolution_state: ApiResolutionState;
  resolved: boolean;
  resolution_stale: boolean;
  resolution: ApiConflictResolution | null;
}

/** A stored decision whose address this subject carries no conflict at. */
export interface ApiResolutionWithoutConflict {
  address: string;
  run_id: string | null;
  outcome: ApiResolutionOutcome;
  resolution_id: string;
  /** The run this decision belongs to has been removed from the record. */
  orphaned_run: boolean;
}

export interface ApiConflictCounts {
  conflicting_addresses: number;
  resolved: number;
  deferred: number;
  stale: number;
  /**
   * Written out by the server rather than left to subtraction, because deriving it
   * at three call sites is how three call sites come to disagree about whether
   * `stale` counts as unresolved. IT DOES, and so does `deferred`.
   */
  unresolved: number;
}

/** `GET /experiments/{id}/conflicts` (optionally `?run=`). */
export interface ApiConflictsResponse {
  experiment_id: string;
  /** The run this describes, or `null` for the record's own fields. */
  run_id: string | null;
  record_rev: number;
  scope: string;
  conflicts: ApiConflict[];
  counts: ApiConflictCounts;
  resolutions_without_conflict: ApiResolutionWithoutConflict[];
  /**
   * Stored decisions this build could not read. Preserved verbatim in the record
   * and COUNTED rather than rendered, for the reason
   * `ApiNotesResponse.unreadable_entries` is: saying what one contains would mean
   * inventing it.
   */
  unreadable_resolution_entries: number;
  /** THE SERVER'S OWN CLOSED VOCABULARIES, served rather than transcribed. */
  outcomes: ApiResolutionOutcome[];
  chosen_from_values: ApiResolutionChosenFrom[];
  states: ApiResolutionState[];
  /** The EXPERIMENT's version token — the `If-Match` a decision must carry. */
  experiment_version: string;
}

export interface ApiConflictResolved {
  resolution: ApiConflictResolution;
  experiment_version: string;
}

/* --------------------------------------------------------------------------
 * Transcript capture.
 *
 * THE FOUR OUTCOMES ARE A CLOSED UNION AND ARE NOT INTERCHANGEABLE. A
 * clarification is a question with alternatives; a review is two proposals the
 * reader refused to choose between; an abstention is a subject it recognised
 * and declined; an unmapped note is text nothing matched. Rendering them under
 * one heading would lose exactly the distinction the server went to trouble to
 * make.
 * ------------------------------------------------------------------------ */

export type ApiCaptureOutcome =
  | 'clarification'
  | 'needs_review'
  | 'abstention'
  | 'unmapped';

/** One run offered as an answer to a clarification. Identifiers only. */
export interface ApiCaptureRunOption {
  run_id: string;
  label: string;
  ordinal: number;
}

/* ── submission revision history (read-only) ────────────────────────────────
 *
 * WHY `availability` EXISTS AND WHY IT IS ON EVERY ONE OF THESE SHAPES. The
 * submission-history tables are created by a migration an OPERATOR applies,
 * separately from the image rollout, and on this deployment they have not been
 * applied. So a running build meeting a database without them is the normal case.
 * "This record was never submitted" and "this server could not find out" are
 * different statements, and the API refuses to give the first when the second is
 * true — the rows key is ABSENT rather than empty on every unavailable answer,
 * which is why `revisions` and `changes` below are OPTIONAL. A consumer that
 * reads them without checking `availability.state` is reading a key that is not
 * there, not an empty list.
 */

export type RevisionHistoryState = 'available' | 'unavailable' | 'not_applicable';

/**
 * Why the history is not `available`. Three of the four are inabilities with
 * three different operator remedies; `worked_example_session` is not an
 * inability at all — a worked-example record is never submitted, so it HAS no
 * history, and that answer arrives as `200`.
 */
export type RevisionHistoryReason =
  | 'no_durable_storage'
  | 'tables_absent'
  | 'database_unavailable'
  | 'worked_example_session';

export interface ApiHistoryAvailability {
  state: RevisionHistoryState;
  reason: RevisionHistoryReason | null;
  /** The server's own sentence. Rendered verbatim; never paraphrased here. */
  message: string;
}

/**
 * WHO IS ON RECORD — including, honestly, nobody.
 *
 * `subject` is `null` whenever `trust_basis` is `unattributed`; the database
 * enforces that pairing in both directions. No surface may substitute a
 * placeholder name, and `trust_basis` is carried so a reader can see what the
 * attribution is WORTH: `test_fixture` is a real shipped basis and is not proof
 * anyone authenticated.
 */
export interface ApiRevisionActor {
  subject: string | null;
  trust_basis: string | null;
  attributed: boolean;
}

export interface ApiRevisionSubmission {
  submission_id: string;
  submitted_utc: string | null;
  unit_count: number | null;
  idempotency_key_used: boolean;
  actor: ApiRevisionActor;
  conflict_summary: Record<string, unknown>;
}

export interface ApiRevisionSummary {
  revision_no: number;
  revision_id: string;
  reason: string;
  created_utc: string | null;
  experiment_rev: number;
  content_signature: string;
  actor: ApiRevisionActor;
  /** `added` / `removed` / `modified` counts. Absent kinds are simply not keys. */
  change_counts: Record<string, number>;
  submission: ApiRevisionSubmission | null;
}

/** One run snapshot inside a revision. `label` is `null` when none was stored. */
export interface ApiRunRevision {
  run_revision_id: string;
  run_id: string;
  ordinal: number | null;
  rev: number | null;
  generation: string;
  created_utc: string | null;
  label: string | null;
}

export type RevisionChangeKind = 'added' | 'removed' | 'modified';

export interface ApiRecordedChange {
  unit_id: string;
  address: string;
  change_kind: RevisionChangeKind;
}

export interface ApiRevisionDetail {
  experiment_id: string;
  revision_no: number;
  availability: ApiHistoryAvailability;
  revision?: ApiRevisionSummary & {
    run_revisions: ApiRunRevision[];
    /** What this revision differed from ITS PREDECESSOR at, as recorded then. */
    changes: ApiRecordedChange[];
    changes_scope: string;
    submission_runs: { unit_id: string; run_id: string | null; record_id: string }[];
  };
  error?: string;
}

export interface ApiRevisionValueChange extends ApiRecordedChange {
  /** The value the REVISION recorded. `null` when it recorded none. */
  previous_value: unknown;
  /** The value the record holds NOW. `null` when it holds none. */
  current_value: unknown;
}

export interface ApiRevisionDiff {
  experiment_id: string;
  revision_no: number;
  record_rev: number;
  current_content_signature: string;
  changes_scope: string;
  availability: ApiHistoryAvailability;
  /** `false` when the stored snapshot could not be read back. `changes` is then absent. */
  comparable?: boolean;
  comparable_note?: string;
  /**
   * The STRONGER statement, covering more than `changes` does. An empty `changes`
   * beside `content_signature_matches: false` is a real state: something outside
   * draft field values differs, and the comparison did not look there.
   */
  content_signature_matches?: boolean;
  revision?: ApiRevisionSummary & { run_labels: Record<string, string> };
  changes?: ApiRevisionValueChange[];
  change_counts?: Record<string, number>;
  units?: { comparable: boolean; added: string[]; removed: string[]; unchanged: string[] };
  current_run_labels?: Record<string, string | null>;
  error?: string;
}

export type LifecycleState = 'draft' | 'needs_review' | 'ready_to_submit' | 'submitted';

/**
 * The DERIVED submission lifecycle. Never stored, recomputed on every read.
 *
 * `submitted` means a submission is on record for exactly the content the record
 * holds NOW. It is never derived from whether the record was exported — export is
 * a mechanical transform any caller can perform, and treating it as a submission
 * would attribute a declaration nobody made.
 *
 * `submission_blocked_by_deployment` is reported SEPARATELY and never lowers
 * `state`. A record whose science is finished reads `ready_to_submit` even on a
 * deployment that can accept no submission at all — which is every deployment
 * shipped today, because no edge-trust verifier is configured.
 */
export interface ApiLifecycle {
  state: LifecycleState;
  label: string;
  reasons: { code: string; message: string }[];
  scientific_readiness: {
    blocked: boolean;
    pending_count: number;
    failing_unit_count: number;
    failing_units: {
      unit_id: string;
      run_id: string | null;
      run_label: string | null;
      errors: unknown[];
    }[];
  };
  submission: {
    known: boolean;
    /** `null` — never `false` — when the history could not be read. */
    submitted_for_current_content: boolean | null;
    unknown_reason: string | null;
  };
  submission_blocked_by_deployment: {
    blocked: boolean;
    blockers: string[];
    basis: string;
    requires_attributable_actor: boolean;
    actor_trust_basis: string | null;
    message: string;
  };
}

export interface ApiRevisionHistory {
  experiment_id: string;
  record_rev: number;
  current_content_signature: string;
  signature_scope: string;
  limit: number;
  availability: ApiHistoryAvailability;
  lifecycle: ApiLifecycle;
  /** ABSENT unless `availability.state === 'available'`. Never an empty stand-in. */
  revisions?: ApiRevisionSummary[];
  /** How many revisions EXIST, whatever the bounded list returned. */
  total?: number;
  returned?: number;
  current_submission?: ApiRevisionSubmission | null;
  error?: string;
}

/*
 * --- Asset references ---------------------------------------------------------
 *
 * Metadata ABOUT files. No bytes travel over any of these shapes, and this
 * application never reads, fetches or hashes the file at a `uri`.
 */

/** One of the twelve `content_role` values the official ISAAC schema enumerates. */
export type ApiAssetContentRole = string;

/*
 * Structurally identical to `ApiCaptureRunOption` above, and deliberately NOT
 * merged with it: one names a run a reader may pick as the subject of a
 * transcript, the other names a run an asset is used by. A shared alias would
 * couple two unrelated contracts, so narrowing either would silently narrow the
 * other. Their identical shape is why the two slices collided here at all.
 */
export interface ApiAssetRunUse {
  run_id: string;
  label: string;
  ordinal: number;
}

export interface ApiCaptureClarification {
  outcome: 'clarification';
  kind: string;
  question: string;
  /** The words that raised it, or `null` when the question is about the capture. */
  quote: string | null;
  options: ApiCaptureRunOption[];
  segment_index: number | null;
}

export interface ApiCaptureAbstention {
  outcome: 'abstention';
  kind: string;
  reason: string;
  quote: string;
  segment_index: number;
}

export interface ApiCaptureReviewRequired {
  outcome: 'needs_review';
  kind: string;
  field_path: string;
  reason: string;
  /** Indexes into `candidates`. Every one of them is still present there. */
  candidate_indexes: number[];
}

/**
 * A PROPOSED field value. Never a value.
 *
 * The four constants are typed as literals so no code can branch on one of them
 * being true — the same technique `ApiNote` uses, and for the same reason: the
 * guarantee has to survive the boundary rather than stopping at it.
 */
export interface ApiFieldCandidate {
  field_path: string;
  proposed_value: unknown;
  /** The words this came from, verbatim, so a reader checks the transcript. */
  quote: string;
  start_char: number;
  end_char: number;
  origin: string;
  produced_by: string;
  /** The rule that read the quote, stated in full rather than as an id. */
  rule: string;
  provenance: Record<string, unknown>;
  status: 'needs_confirmation';
  verified: false;
  is_evidence: false;
  requires_user_confirmation: true;
}

/** A retention state this build does not offer, with the reason it does not. */
export interface ApiCaptureRetentionAbsent {
  state: string;
  reason: string;
}

export interface ApiCaptureRetention {
  /** The ONE state this storage enforces. */
  state: string;
  notes_captured: number;
  /** Always `false`: nothing in this application removes a note. */
  deletable: boolean;
  description: string;
  not_implemented: ApiCaptureRetentionAbsent[];
  raw_audio: { stored: boolean; reason: string };
}

export interface ApiTranscriptCapture {
  capture: {
    finalized: boolean;
    run_id: string | null;
    segments: number;
    retention: ApiCaptureRetention;
  };
  /** Always `false`. This operation writes no field, anywhere. */
  applied: boolean;
  candidates: ApiFieldCandidate[];
  clarifications: ApiCaptureClarification[];
  abstentions: ApiCaptureAbstention[];
  review_required: ApiCaptureReviewRequired[];
  notes: ApiNote[];
  ambiguity_policy: { kind: string; outcome: ApiCaptureOutcome; rule: string }[];
  /** The server's own statement of where accepting a candidate writes. */
  accept_contract: {
    method: string;
    path: string;
    requires: string[];
    message: string;
  };
  experiment_version: string;
}

/* --------------------------------------------------------------------------
 * Model-seam capability report.
 * ------------------------------------------------------------------------ */

export interface ApiProviderSeam {
  seam: string;
  implementation: string;
  /** Read off the resolved implementation. Nothing in the build sets it true. */
  configured: boolean;
  is_test_double: boolean;
  reason: string;
  /** The name of the variable that selects it. Never its value. */
  selected_by: string;
}

export interface ApiProviderCapabilities {
  any_provider_configured: boolean;
  decision_reference: string;
  seams: ApiProviderSeam[];
  note: string;
  /** Always `true`: reading a finalized transcript depends on no provider. */
  manual_transcript_available: boolean;
}

/** A seam declining to act, with the missing items named. Never an empty result. */
export interface ApiProviderRefusal {
  refused: true;
  seam: string;
  reason: string;
  missing: string[];
  message: string;
  decision_reference: string;
}

export interface ApiTranscriptSegment {
  index: number;
  text: string;
  start_char: number;
  end_char: number;
}

export interface ApiTranscriptionResult {
  refused: false;
  text: string;
  segments: ApiTranscriptSegment[];
  produced_by: string;
  /** `true` when the text is exactly what the caller supplied. */
  verbatim: boolean;
  language: string | null;
}

/**
 * Where an asset actually reaches an exported record.
 *
 * `none` is the value that has to exist and the one a UI must never hide: an
 * experiment that HAS runs exports one record per run, composed from that run's own
 * blocks, and `assets` is run-level — so a library entry associated with no run is
 * invisible to export. A scientist who recorded a file, saw it listed, and is not
 * told this would never find out.
 */
export type ApiAssetExportReach = 'record' | 'runs' | 'none';

export interface ApiAsset {
  asset_id: string;
  content_role: ApiAssetContentRole;
  uri: string;
  /** The digest THE SCIENTIST SUPPLIED. Never computed, completed or repaired. */
  sha256: string;
  media_type?: string;
  notes?: string;
  citation?: Record<string, unknown>;
  caption_verbatim?: string;
  caption_highlights?: Record<string, unknown>;
  paper_conclusions_about_figure?: string[];
  figure_label?: string;
  page?: number | string;
  /*
   * The RAW draft evidence entries, exactly as stored — `FieldEvidence`, not
   * `ApiEvidenceEntry`. The latter is the evidence-TRAIL wrapper (a path, a status
   * and a list); an asset carries the list itself, and typing it as the wrapper
   * made every field the UI reads — `question`, `source_file`, `timestamp` —
   * invisible to the compiler.
   */
  evidence: FieldEvidence[];
  evidence_count: number;
  /**
   * Whether the stored digest is 64 lowercase hexadecimal characters.
   *
   * A STATEMENT ABOUT THE STRING, NOT ABOUT THE FILE. Named for what it measures,
   * so no reader of this type can mistake it for a verification result — nothing in
   * ISAAC has opened the file at the `uri`.
   */
  sha256_wellformed: boolean;
  used_by_runs: ApiAssetRunUse[];
  export_reach: ApiAssetExportReach;
}

/** `GET /experiments/{id}/assets`. */
export interface ApiAssetsResponse {
  assets: ApiAsset[];
  total: number;
  /**
   * Stored entries this build cannot present — not an object, or carrying no
   * `asset_id`. Preserved in the record and COUNTED rather than rendered, for the
   * reason `ApiNotesResponse.unreadable_entries` is.
   */
  unreadable_entries: number;
  /** The official schema's own enumeration, served rather than transcribed here. */
  content_roles: ApiAssetContentRole[];
  /** This record's runs, so the association control can be drawn in one read. */
  runs: { id: string; label: string; ordinal: number }[];
  /** The EXPERIMENT's version token — the `If-Match` every asset write must carry. */
  experiment_version: string;
}

export interface ApiAssetWritten {
  asset: ApiAsset;
  experiment_version: string;
}

export interface ApiAssetRemoved {
  removed_asset_id: string;
  /** The runs it was detached from, NAMED rather than counted. */
  detached_from_runs: string[];
  experiment_version: string;
}

/*
 * --- `GET /experiments/{id}/provenance` ---------------------------------------
 *
 * MOVED HERE FROM `lib/api.ts` (2026-08-27), where a comment had recorded that they
 * belonged here and asked the next slice that owned this file to move them. See that
 * comment's replacement in `api.ts` for the reason it was more than housekeeping: a
 * SECOND, differently-typed declaration of this same contract existed in
 * `lib/provenance.ts` with nothing enforcing agreement, and has been removed.
 *
 * TWO INDEPENDENT DIMENSIONS, NEVER COMBINED INTO ONE VALUE — the same contract
 * `lib/provenance.ts` mirrors for surfaces that already hold an evidence entry.
 * `origins` is a SET, because one address can carry several citations of different
 * kinds; `primary_origin` picks one of them by a fixed documented order.
 *
 * `origins`, `primary_origin` and `review_state` are `string`, NOT the closed unions
 * `provenance.ts` declares for its own in-client derivation. `originLabel`'s
 * `ORIGIN_LABEL[origin] ?? origin` fallback depends on an unrecognised origin being
 * representable; a closed union would turn a server-side addition into a compile error
 * here and a silent one on screen.
 */
export interface ApiProvenanceEntry {
  /** A record address, or `note:<id>` for a note that has no schema home yet. */
  address: string;
  /** Every origin the stored citations at this address produce. Never empty. */
  origins: string[];
  /** One of `origins`, chosen by the server's fixed precedence — never array order. */
  primary_origin: string;
  /** What, if anything, ESTABLISHES the value. Not a validity or export verdict. */
  review_state: string;
  evidence_count: number;
  /** True when the RUN does not hold the value and resolves the record's. */
  inherited: boolean;
  /** Ids of notes a person MAPPED here. Never a machine's proposal. */
  note_refs: string[];
  /** The stored payload was only PARTLY readable, so it is not plain support. */
  unavailable: boolean;
  /** One of `conflict_resolution.RESOLUTION_STATES`, derived on read. */
  resolution_state: string;
}

export interface ApiProvenanceResponse {
  experiment_id: string;
  /** The run described, or `null` for the record itself. */
  run_id: string | null;
  record_rev: number;
  entries: ApiProvenanceEntry[];
  /**
   * WHAT IS NOT LISTED, COUNTED RATHER THAN OMITTED. A reviewed note is not an
   * entry, because none of the review states is true of it.
   */
  notes_summary: { total: number; listed_as_unmapped: number };
  /** Blocks that carry no value envelope to describe. Owned up to, not passed over. */
  blocks_not_described: string[];
}

/*
 * --- The record CHANGE FEED --------------------------------------------------
 *
 * A COALESCING STATE FEED, and the name is the contract rather than a label. Each
 * entry says "this entity is at a version later than your cursor"; none of them
 * says "here is an act that happened". Ten edits to one run between two reads are
 * ONE entry, and nothing in this shape can tell a client how many there were.
 *
 * There is deliberately no `deleted` / `removed` kind, and its absence is not an
 * omission to be filled in later: the feed is derived from the record document's
 * CURRENT state, and a removed run is simply gone from it. See the operation's own
 * description, which says so in the same words the server's `DELETION_LIMITATION`
 * constant does.
 */

export interface ApiChangeEntry {
  /** `experiment` or `run` today. DERIVED server-side; read `kinds`, never assume. */
  kind: string;
  entity_id: string;
  /** `<generation>.<rev>` — the same value every other route publishes as `version`. */
  version: string;
  rev: number;
  /** Minted fresh at genuine (re)creation, so a delete->recreate is visible at rev 0. */
  generation: string;
  updated_utc: string;
}

export interface ApiChangeFeedPage {
  changes: ApiChangeEntry[];
  /**
   * ALWAYS PRESENT, including on an empty page — where it is the position the
   * caller was already at, so a poller that keeps sending it back makes no
   * progress and loses nothing. Opaque: never construct or parse one.
   */
  next_cursor: string;
  has_more: boolean;
  /** The EFFECTIVE limit, after the server clamped what was asked for. */
  limit: number;
  returned: number;
  /** Entities after this page. `has_more` is `remaining > 0`, stated not inferred. */
  remaining: number;
  /** The kinds this deployment serves, derived server-side from its collectors. */
  kinds: string[];
}

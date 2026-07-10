/*
 * Client types mirroring the Task 1 FastAPI serializations
 * (see .superpowers/sdd/task-1-report.md). Truth state (validation / coverage /
 * advisory / field status / evidence) is server-derived and read-only in the
 * client; the UI renders these shapes, it never computes them.
 */

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
export type CompletionInputType = 'hash' | 'enum' | 'number';

export interface DemoAnswer {
  value: string;
  label: string; // "Demo answer (synthetic)"
}

export interface AssistantSuggestion {
  text: string;
  answeredFrom: AssistantSource;
  locator?: string; // e.g. raw_scan_listing.txt · L12
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
  enumOptions?: string[]; // from schema/isaac_record_v1.json
  unit?: string;
  demo_answer?: DemoAnswer;
  suggestion?: AssistantSuggestion;
}

// A confirmed answer (stored as user_confirmation evidence).
export interface CompletionAnswer {
  id: string;
  label: string;
  storedValue: string;
  confirmed: boolean;
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

export type GraphFreshness = 'fresh' | 'stale' | 'missing' | 'unavailable';

export interface GraphStatus {
  status: GraphFreshness;
  plane: 'memory';
  note?: string;
}

export type AssistantSource = 'schema' | 'audit' | 'git' | 'graph' | 'files';

export interface AssistantMessage {
  text: string; // sentence case; never renders PASS/FAIL
  answeredFrom: AssistantSource;
}

export interface SuggestedPrompt {
  text: string;
  answeredFrom: AssistantSource;
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

export type SpineStepState = 'done' | 'active' | 'locked';

export interface SpineStep {
  key: string;
  label: string;
  state: SpineStepState;
  meta?: string;
  number?: number; // numbered variant (S4: "2 of 5 answered")
}

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

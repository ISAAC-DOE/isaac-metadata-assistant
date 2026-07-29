/*
 * Pure adapters: raw API wire shapes (lib/types.ts, from apps/api) -> the UI
 * render types the components already consume. These are presentation mappings
 * ONLY. They never invent a verdict, coverage figure, or advisory — those arrive
 * from the server and are passed through faithfully.
 */

import { LABELS, formatCreatedDate, titleCase } from './labels';
import type {
  AdvisoryResult,
  ApiAuditResponse,
  ApiDemoStep,
  ApiDraftGroup,
  ApiEvidenceEntry,
  ApiExperimentStatus,
  ApiExperimentSummary,
  ApiPendingItem,
  ApiValidateResult,
  ApiWarningsResponse,
  AuditResult,
  BlockerKind,
  CompletionInputType,
  DraftField,
  EvidenceTrailEntry,
  ExperimentSummary,
  ExperimentTrailing,
  FieldEvidence,
  FieldGroupData,
  PendingBlocker,
  QueueGroup,
  QueueGroupKey,
  RunnerStage,
  SourceType,
  ValidationResult,
} from './types';

// The MVP is a single characterization path; the row tag is a display label, not
// a server field. (The list endpoint carries no technique — it is Cu K-edge XANES.)
const TECHNIQUE = 'Cu K-edge XANES';

const STATUS_TO_GROUP: Record<ApiExperimentStatus, QueueGroupKey> = {
  needs_attention: 'needsAttention',
  in_review: 'inReview',
  ready_to_export: 'ready',
  done: 'done',
};

const GROUP_ORDER: { key: QueueGroupKey; label: string }[] = [
  { key: 'needsAttention', label: LABELS.groupNeedsAttention },
  { key: 'inReview', label: LABELS.groupInReview },
  { key: 'ready', label: LABELS.groupReady },
  { key: 'done', label: LABELS.groupDone },
];

// --- S1 queue -----------------------------------------------------------

// P33 S1 (D1) — the server-authored title carries a trailing lifecycle suffix
// (e.g. "… · New Draft"). The dashboard card now shows its own lifecycle badge,
// so a KNOWN suffix is stripped for display; anything else (unrecognized or
// absent) is a safe fallback that keeps the full title untouched.
const KNOWN_TITLE_SUFFIXES = [
  ' · New Draft',
  ' · Partially Completed',
  ' · Export Review Required',
  ' · Ready to Export',
  ' · Exported Record',
] as const;

export function stripLifecycleSuffix(title: string): string {
  const hit = KNOWN_TITLE_SUFFIXES.find((suffix) => title.endsWith(suffix));
  return hit ? title.slice(0, -hit.length) : title;
}

/** Exported for direct unit testing (P33 S1); not otherwise used outside this file. */
export function trailingFor(s: ApiExperimentSummary, group: QueueGroupKey): ExperimentTrailing {
  switch (group) {
    case 'needsAttention':
      return { needsYouCount: s.pending_count };
    default:
      // in_review / ready / done: the group header (and, for done, the lifecycle
      // badge) already names the state; no PASS/exported chip is claimed on a
      // row (the reserved verdict only appears after real validation, on S6).
      return {};
  }
}

/** Exported for direct unit testing (P33 S1); the queue mapping below is the
 * only real caller. */
export function toExperimentSummary(s: ApiExperimentSummary): ExperimentSummary {
  const group = STATUS_TO_GROUP[s.status];
  return {
    id: s.id,
    title: stripLifecycleSuffix(s.title),
    // Passed through verbatim — the label text is authored by the backend from the
    // same seed spec that builds the title. Nothing here parses a title to recover
    // it, and a missing/null value stays undefined so the row renders nothing.
    scenario: s.scenario ?? undefined,
    technique: TECHNIQUE,
    idOrDraft: s.exported && s.record_id ? s.record_id : 'draft',
    meta: s.created_utc ? `created ${s.created_utc.slice(0, 10)}` : undefined,
    lifecycle: s.exported ? 'exported' : 'draft',
    date: s.created_utc ? formatCreatedDate(s.created_utc) : undefined,
    group,
    trailing: trailingFor(s, group),
  };
}

/** Group the live experiment list by server status; empty groups are hidden. */
export function summariesToQueueGroups(summaries: ApiExperimentSummary[]): QueueGroup[] {
  const rows = summaries.map(toExperimentSummary);
  return GROUP_ORDER.map(({ key, label }) => {
    const groupRows = rows.filter((r) => r.group === key);
    return { key, label, count: groupRows.length, rows: groupRows };
  }).filter((g) => g.count > 0);
}

/** The subcount line under the S1 title, e.g. "3 experiments · 1 ready to export". */
export function queueSubcount(summaries: ApiExperimentSummary[]): string {
  const total = summaries.length;
  const ready = summaries.filter((s) => s.status === 'ready_to_export').length;
  return `${total} experiment${total === 1 ? '' : 's'} · ${ready} ready to export`;
}

// --- S3 draft groups ----------------------------------------------------

function blockOf(g: ApiDraftGroup): string {
  const first = g.fields[0]?.path;
  return first ? first.split('.')[0] : g.title.toLowerCase();
}

function summarize(fields: DraftField[], needsYouCount: number): string {
  const n = fields.length;
  if (needsYouCount > 0) {
    return `${needsYouCount} field${needsYouCount === 1 ? '' : 's'} need you`;
  }
  const kinds = new Set(fields.map((f) => f.status));
  const detail =
    kinds.has('inferred') && kinds.size > 1
      ? 'verified & inferred'
      : kinds.has('inferred')
        ? 'inferred'
        : 'all verified';
  return `${n} field${n === 1 ? '' : 's'} · ${detail}`;
}

/**
 * Map the grouped draft into `FieldGroupData`, enriching each field with the raw
 * evidence entries from the /evidence endpoint (the /draft endpoint carries only
 * counts + source types, not the citations themselves).
 */
export function draftGroupsToFieldGroups(
  groups: ApiDraftGroup[],
  evidenceByPath: Map<string, ApiEvidenceEntry>,
): FieldGroupData[] {
  return groups.map((g) => {
    const fields: DraftField[] = g.fields.map((f) => ({
      path: f.path,
      label: f.label,
      value: f.value,
      status: f.status,
      evidence_count: f.evidence_count,
      source_types: f.source_types,
      evidence: evidenceByPath.get(f.path)?.evidence,
    }));
    const needsYouCount = fields.filter((f) => f.status === 'needs_confirmation').length;
    return {
      block: blockOf(g),
      humanLabel: g.title,
      summary: summarize(fields, needsYouCount),
      needsYouCount,
      collapsedByDefault: false,
      fields,
    };
  });
}

// --- the three signals (passed through, never computed) -----------------

export function toValidationResult(v: ApiValidateResult): ValidationResult {
  return {
    verdict: v.ok ? 'pass' : 'fail',
    ok: v.ok,
    schemaVersion: v.schema,
    exitCode: v.ok ? 0 : 1,
    errors: v.errors,
  };
}

export function toAuditResult(a: ApiAuditResponse): AuditResult {
  const resolved = a.records.reduce((n, r) => n + r.evidence_present, 0);
  const total = a.records.reduce((n, r) => n + r.evidence_expected, 0);
  // The audit endpoint reports the honest record-derived denominator plus the
  // uncovered/dangling target names; both are passed through faithfully.
  const uncovered = a.records.flatMap((r) => r.uncovered);
  const dangling = a.records.flatMap((r) => r.dangling);
  return { resolved, total, uncovered, dangling };
}

export function toAdvisoryResult(w: ApiWarningsResponse): AdvisoryResult {
  return { advisory: true, gating: false, warnings: w.warnings };
}

// --- S4 completion blockers ---------------------------------------------
// The /pending items (id / kind / question / about / demo_answer) become the
// render blockers. Asset blockers take a pasted sha256; series/descriptor carry
// a structured value the user can only *confirm* from the labeled demo answer —
// the UI never lets the assistant type a scientific value.

const KIND_LABEL: Record<string, string> = {
  asset: 'Asset Hash',
  series: 'Reduced Spectrum',
  descriptor: 'Scientific Descriptor',
  edge: 'Absorption Edge',
};

// Sentence-case helper copy (never a scientific value) explaining each blocker
// and reinforcing the no-guessing contract.
const KIND_CONTEXT: Record<string, string> = {
  asset:
    'An asset can only be cited once it carries a hash. Paste the sha256 — the system will never generate this value for you.',
  series:
    'A structured reduced-spectrum value the system will never generate for you. Confirm the synthetic demo value, or leave it honestly missing.',
  descriptor:
    'A structured scientific descriptor the system will never generate for you. Confirm the synthetic demo value, or leave it honestly missing.',
};

function inputTypeForKind(kind: BlockerKind): CompletionInputType {
  if (kind === 'asset') return 'hash';
  if (kind === 'series' || kind === 'descriptor') return 'structured';
  return 'text';
}

function pathTokenFor(item: ApiPendingItem): string {
  if (item.kind === 'asset') return item.about || item.id; // the asset uri
  if (item.kind === 'series') return 'measurement.series';
  if (item.kind === 'descriptor') return 'descriptors';
  return item.about || item.id;
}

/** Map one live /pending item onto the render blocker the GuidedPrompt consumes. */
export function pendingItemToBlocker(item: ApiPendingItem): PendingBlocker {
  return {
    id: item.id,
    kind: item.kind,
    question: item.question,
    label: KIND_LABEL[item.kind] ?? titleCase(String(item.kind)),
    path: pathTokenFor(item),
    about: item.about ?? undefined,
    context: KIND_CONTEXT[item.kind],
    inputType: inputTypeForKind(item.kind),
    demo_answer: item.demo_answer
      ? { value: item.demo_answer.value, label: item.demo_answer.label }
      : undefined,
  };
}

/**
 * P33 S4 (D9/C2) — the presentation-only summary for one /pending item in the
 * S3 missing-fields banner. It NEVER rewrites, guesses, or parses meaning from
 * the backend question:
 *  - `label` is a CONCISE label read straight from the structured `kind`
 *    (reusing KIND_LABEL). When `kind` is not a known structured kind, it falls
 *    back to the FULL original question verbatim — never a re-cased/parsed guess.
 *  - `locator` is the technical locator (`about`) surfaced exactly once, or null.
 * Pure: it does not mutate the item, and the underlying question is unchanged.
 */
export function pendingSummary(item: ApiPendingItem): { label: string; locator: string | null } {
  return {
    label: KIND_LABEL[item.kind] ?? item.question,
    locator: item.about ?? null,
  };
}

/**
 * A short, honest one-line summary of a confirmed/demo value — never invented.
 * A pasted sha256 is truncated; a structured series/descriptor object is
 * summarized from its own fields.
 */
export function answerValuePreview(kind: BlockerKind, value: unknown): string {
  if (typeof value === 'string') {
    return value.length > 20 ? `${value.slice(0, 16)}…` : value;
  }
  if (kind === 'series' && Array.isArray(value)) {
    const first = value[0] as { series_id?: string; channels?: unknown[] } | undefined;
    const id = first?.series_id ?? 'series';
    const channels = Array.isArray(first?.channels) ? first.channels.length : 0;
    return `${id} · ${channels} channel${channels === 1 ? '' : 's'}`;
  }
  if (kind === 'descriptor' && value && typeof value === 'object') {
    const d = value as { value?: unknown; unit?: string; uncertainty?: { sigma?: unknown } };
    const unit = d.unit ? ` ${d.unit}` : '';
    const sigma = d.uncertainty?.sigma != null ? ` · σ ${d.uncertainty.sigma}` : '';
    return `${String(d.value)}${unit}${sigma}`;
  }
  return 'structured value';
}

// --- S5 evidence trail --------------------------------------------------
// The live /evidence entries (dotted JSON-paths + namespaced assets:/descriptors:/
// implicit: keys) become the browsable Evidence Trail. Values, statuses and the
// raw citations are server-derived and passed through faithfully — nothing here
// invents provenance. Namespaced keys are explicitly outside the N/N coverage set.

const _LINE_RE = /\bline\s+(\d+)\b/i;

function distinctSourceTypes(evidence: FieldEvidence[]): SourceType[] {
  const seen: SourceType[] = [];
  for (const ev of evidence) {
    if (ev.source_type && !seen.includes(ev.source_type)) seen.push(ev.source_type);
  }
  return seen;
}

function trailLabel(path: string, namespaced: boolean): string {
  if (!namespaced) return path; // dotted JSON-paths render mono, verbatim
  const name = path.slice(path.indexOf(':') + 1);
  return titleCase(name.replace(/_/g, ' '));
}

function trailValue(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined;
  return typeof value === 'string' ? value : JSON.stringify(value);
}

/** Map the live /evidence entries onto the browsable Evidence Trail entries. */
export function evidenceEntriesToTrail(entries: ApiEvidenceEntry[]): EvidenceTrailEntry[] {
  return entries.map((e) => {
    const namespaced = e.path.includes(':');
    const evidence = e.evidence ?? [];
    return {
      key: e.path,
      label: trailLabel(e.path, namespaced),
      value: trailValue(e.value),
      status: e.status,
      sourceTypes: distinctSourceTypes(evidence),
      evidence,
      namespaced,
      // A dotted path with no resolved value is a dangling/integrity case; every
      // path we render here resolves, so "resolved" tracks a non-null value.
      resolved: e.value !== null && e.value !== undefined,
    };
  });
}

/** The source fixture a trail entry's evidence cites (first one with a file). */
export function primarySourceFile(entry: EvidenceTrailEntry): string | undefined {
  return entry.evidence.find((ev) => ev.source_file)?.source_file;
}

/**
 * 1-based line numbers the entry's evidence cites in `sourceFile`. A spreadsheet
 * fixture cites by field (no line), so it yields none — expected, not an error.
 */
export function citedLinesForEntry(entry: EvidenceTrailEntry, sourceFile?: string): number[] {
  if (!sourceFile) return [];
  const lines = new Set<number>();
  for (const ev of entry.evidence) {
    if (ev.source_file !== sourceFile) continue;
    const m = _LINE_RE.exec(ev.locator ?? '');
    if (m) lines.add(Number(m[1]));
  }
  return [...lines].sort((a, b) => a - b);
}

const _SOURCE_PHRASE: Record<string, string> = {
  spreadsheet: 'read from the campaign spreadsheet (spreadsheet)',
  file_listing: 'identified in the archive listing (file_listing)',
  derivation: 'derived by a documented rule (derivation)',
  user_confirmation: 'confirmed by you (user_confirmation)',
};

/**
 * A short, honest provenance sentence from the entry's source types — never a
 * verdict. When machine evidence and a human confirmation both appear, it names
 * that both are preserved side by side (the machine lead and the human confirm).
 */
export function provenanceFor(entry: EvidenceTrailEntry): string {
  const phrases = entry.sourceTypes
    .map((st) => _SOURCE_PHRASE[st] ?? `cited from ${st}`)
    .filter(Boolean);
  if (phrases.length === 0) return 'This entry carries no citation.';
  const joined =
    phrases.length === 1
      ? `${phrases[0][0].toUpperCase()}${phrases[0].slice(1)}.`
      : `${phrases[0][0].toUpperCase()}${phrases[0].slice(1)}, and ${phrases
          .slice(1)
          .join(', and ')}.`;
  const hasBoth =
    entry.sourceTypes.includes('user_confirmation') &&
    entry.sourceTypes.some((st) => st !== 'user_confirmation');
  return hasBoth
    ? `${joined} Two sources are preserved side by side — the machine lead and the human confirmation.`
    : joined;
}

// --- S2 demo runner -----------------------------------------------------

/** Render the real demo/run steps as the staged progress list. */
export function demoStepsToStages(steps: ApiDemoStep[]): RunnerStage[] {
  return steps.map((s) => ({
    key: s.name,
    label: titleCase(s.name.replace(/_/g, ' ')),
    command: s.name,
    state: s.ok ? 'done' : 'current',
    detail: s.detail,
  }));
}

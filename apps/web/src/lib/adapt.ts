/*
 * Pure adapters: raw API wire shapes (lib/types.ts, from apps/api) -> the UI
 * render types the components already consume. These are presentation mappings
 * ONLY. They never invent a verdict, coverage figure, or advisory — those arrive
 * from the server and are passed through faithfully.
 */

import { LABELS, titleCase } from './labels';
import type {
  AdvisoryResult,
  ApiAuditResponse,
  ApiDemoStep,
  ApiDraftGroup,
  ApiEvidenceEntry,
  ApiExperimentStatus,
  ApiExperimentSummary,
  ApiValidateResult,
  ApiWarningsResponse,
  AuditResult,
  DraftField,
  ExperimentSummary,
  ExperimentTrailing,
  FieldGroupData,
  QueueGroup,
  QueueGroupKey,
  RunnerStage,
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

function trailingFor(s: ApiExperimentSummary, group: QueueGroupKey): ExperimentTrailing {
  switch (group) {
    case 'needsAttention':
      return { needsYouCount: s.pending_count };
    case 'done':
      return { exported: true };
    default:
      // in_review / ready: the group header names the state; no PASS is claimed on
      // a row (the reserved verdict only appears after real validation, on S6).
      return {};
  }
}

function toExperimentSummary(s: ApiExperimentSummary): ExperimentSummary {
  const group = STATUS_TO_GROUP[s.status];
  return {
    id: s.id,
    title: s.title,
    technique: TECHNIQUE,
    idOrDraft: s.exported && s.record_id ? s.record_id : 'draft',
    meta: s.created_utc ? `created ${s.created_utc.slice(0, 10)}` : undefined,
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
  // The audit endpoint reports counts, not the dangling path names, so the list is
  // empty; unresolved coverage still shows as resolved < total in the figure.
  return { resolved, total, dangling: [] };
}

export function toAdvisoryResult(w: ApiWarningsResponse): AdvisoryResult {
  return { advisory: true, gating: false, warnings: w.warnings };
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

/*
 * P30.3 — cross-record deterministic triage (the consumer for the P30.1 provider).
 *
 * A PURE, deterministic function over the SAFE runtime-record projection served by
 * GET /api/runtime/records (see apps/api/isaac_api/runtime_records.py). It answers
 * a small set of cross-record triage intents — "which records need attention / are
 * blocked / have conflicts / are exportable now" — with SAFE summaries plus a
 * navigate handoff.
 *
 * Deliberate boundaries (the whole point of this consumer):
 *  - It NEVER reads current-record scientific truth: opening a match hands off to a
 *    direct Workspace load via `navigate_to = /record/<experiment_id>`. The summary
 *    is a lead, not the record truth.
 *  - It NEVER presents an inferred candidate as a confirmed fact, NEVER picks a
 *    conflict winner, NEVER renders a verdict (no PASS/FAIL, no "confirmed value",
 *    no resolved/winner language). A conflict is only COUNTED and flagged for human
 *    resolution.
 *  - Each match carries ONLY {experiment_id, title, navigate_to, reason} — no draft
 *    values, no evidence bodies, no per-field classifications.
 *  - An unknown intent returns an honest empty result, never a fabricated match.
 *
 * It never mutates its input and is Graphify-free.
 */

/** The SAFE cross-record projection — mirrors apps/api runtime_records `_project_one`.
 * Only the confirmed-facts allow-set plus freshness metadata; no draft values,
 * evidence bodies, or per-field classifications ever appear here. */
export interface RuntimeRecord {
  experiment_id: string;
  title: string;
  status: string;
  pending_count: number;
  exported: boolean;
  record_id: string | null;
  workflow: {
    current_step: string | null;
    blocked: boolean;
    reopened: boolean;
  };
  evidence_counts: {
    supported: number;
    inferred_candidate: number;
    insufficient_evidence: number;
    conflicting_evidence: number;
    unknown: number;
  };
  artifact_state: string;
  record_rev: number;
  updated_utc: string;
  navigate_to: string;
}

/** A single triage match: ONLY safe summary fields plus the direct handoff route. */
export interface TriageMatch {
  experiment_id: string;
  title: string;
  navigate_to: string;
  reason: string;
}

export interface TriageResult {
  text: string;
  matches: TriageMatch[];
}

/** The recognized cross-record triage intents (the consumer's chip set). */
export type TriageIntent = 'needs_attention' | 'blocked' | 'has_conflict' | 'exportable';

export const TRIAGE_INTENTS: readonly TriageIntent[] = [
  'needs_attention',
  'blocked',
  'has_conflict',
  'exportable',
] as const;

/** Small pluralizer for honest, verdict-free summary text. */
function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/**
 * One intent's definition: the deterministic predicate over a projected record and
 * a SAFE per-match reason builder. Reasons flag/count only — never a scientific
 * value, never "confirmed value", never a resolved conflict winner.
 */
interface IntentSpec {
  match: (r: RuntimeRecord) => boolean;
  reason: (r: RuntimeRecord) => string;
  /** Verdict-free summary for N matched records. */
  summary: (n: number) => string;
}

const INTENTS: Record<TriageIntent, IntentSpec> = {
  needs_attention: {
    match: (r) => r.status === 'needs_attention',
    reason: (r) => `${plural(r.pending_count, 'field needs', 'fields need')} attention`,
    summary: (n) =>
      n === 0
        ? 'No records currently need attention.'
        : `${plural(n, 'record needs', 'records need')} attention.`,
  },
  blocked: {
    match: (r) => r.workflow.blocked,
    reason: () => 'a workflow step is blocked',
    summary: (n) =>
      n === 0
        ? 'No records have a blocked workflow step.'
        : `${plural(n, 'record has', 'records have')} a blocked workflow step.`,
  },
  has_conflict: {
    match: (r) => r.evidence_counts.conflicting_evidence >= 1,
    // Count + flag for a human — never asserts which value is right.
    reason: (r) =>
      `${plural(r.evidence_counts.conflicting_evidence, 'conflicting evidence item', 'conflicting evidence items')} — needs human review`,
    summary: (n) =>
      n === 0
        ? 'No records have conflicting evidence.'
        : `${plural(n, 'record has', 'records have')} conflicting evidence that needs human review.`,
  },
  exportable: {
    match: (r) => r.status === 'ready_to_export',
    reason: () => 'ready to export',
    summary: (n) =>
      n === 0
        ? 'No records are ready to export.'
        : `${plural(n, 'record is', 'records are')} ready to export.`,
  },
};

function isTriageIntent(intent: string): intent is TriageIntent {
  return Object.prototype.hasOwnProperty.call(INTENTS, intent);
}

/**
 * Triage a scan of SAFE projected records for one intent. Pure and deterministic:
 * it reads the input in order and returns a fresh result, never mutating `records`.
 *
 * The handoff route is ALWAYS reconstructed as `/record/<experiment_id>` (a client
 * route, never a filesystem path) so a match cannot smuggle a foreign navigation
 * target — opening it loads the authoritative record directly.
 */
export function crossRecordTriage(records: RuntimeRecord[], intent: string): TriageResult {
  if (!isTriageIntent(intent)) {
    return {
      text: `“${intent}” is not a recognized cross-record triage request — no leads to show. Try: needs attention, blocked, has conflicts, or ready to export.`,
      matches: [],
    };
  }

  const spec = INTENTS[intent];
  const matches: TriageMatch[] = records
    .filter((r) => spec.match(r))
    .map((r) => ({
      experiment_id: r.experiment_id,
      title: r.title,
      navigate_to: `/record/${r.experiment_id}`,
      reason: spec.reason(r),
    }));

  return { text: spec.summary(matches.length), matches };
}

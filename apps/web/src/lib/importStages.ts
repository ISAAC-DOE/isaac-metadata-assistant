import type {
  ApiImportCandidate,
  ApiImportSession,
  ApiImportSignalSelection,
  ApiImportUnitRow,
  ApiImportUnsentCandidate,
} from './types';
import type { Bl15Conflict, Bl15Reading } from './bl15Review';
import type { SemanticState } from '../components/SemanticStatus';
import { RECORD_FIELDS } from './recordFields';
import { conceptLabel, bl15Humanize } from './bl15ReviewContent';

/**
 * THE HISTORICAL IMPORT STAGE FLOW — pure derivations, no React (owner QA H1,
 * 2026-09-22).
 *
 * The opened session used to render every stage at once: a 43,994 px page for a
 * five-measurement synthetic archive. The owner's brief replaces that with SIX
 * STAGES, one in focus at a time — Source Bundle → What ISAAC Read → Runs &
 * Candidates → Conflicts → Review → Add to Experiment — and summary counts first.
 *
 * Everything a surface decides about a candidate's state comes from the SERVER
 * (`review_status`, `agreement`, `proposable`); nothing here re-derives whether
 * sources agree. What this module adds is presentation: which stage a session
 * opens on, the counts, human labels in place of schema paths, and the reading
 * of a conflict source by source.
 */

export const IMPORT_STAGES = [
  'sources',
  'read',
  'runs',
  'conflicts',
  'review',
  'add',
] as const;
export type ImportStageId = (typeof IMPORT_STAGES)[number];

/**
 * Each stage's SERVER workflow step, for "how far has this session got" and for the
 * one step the server may declare unbuilt. `conflicts` has no step of its own: it is
 * part of what reconstruction reports, so it follows `reconstruct`.
 */
export const STAGE_WORKFLOW_STEP: Readonly<Record<ImportStageId, string>> = {
  sources: 'sources',
  read: 'parse',
  runs: 'reconstruct',
  conflicts: 'reconstruct',
  review: 'review',
  add: 'add_to_experiments',
};

/** The server's step order, read from its own list so a new step cannot desynchronise. */
export function stepIndex(session: Pick<ApiImportSession, 'workflow'>, stepId: string): number {
  return session.workflow.findIndex((step) => step.id === stepId);
}

/** Whether the session has reached a stage's step — a fact the server derives. */
export function stageReached(session: ApiImportSession, stage: ImportStageId): boolean {
  const reached = stepIndex(session, session.furthest_step);
  const mine = stepIndex(session, STAGE_WORKFLOW_STEP[stage]);
  return reached >= 0 && mine >= 0 && mine <= reached;
}

/**
 * The stage a session OPENS on: the first one with work to do. A new session opens
 * on its sources; a read one on what was read; a reconstructed one on its runs.
 */
export function defaultStage(session: ApiImportSession): ImportStageId {
  if (session.sources.length === 0) return 'sources';
  if (session.reconstruction !== null && session.reconstruction.candidates.length > 0) return 'runs';
  const read = session.source_counts.parsed > 0 || Boolean(session.corpus_review);
  if (read) return 'runs';
  return 'read';
}

/* ── candidates ───────────────────────────────────────────────────────────── */

export type CandidateBucket = 'ready' | 'needsReview' | 'conflict' | 'unmapped' | 'resolved';

/**
 * A candidate's review bucket, from the server's own `review_status` when served,
 * and otherwise from the three fields that decide it — the same order the server
 * uses (`historical_import.SemanticCandidate.review_status`).
 */
export function candidateBucket(candidate: ApiImportCandidate): CandidateBucket {
  switch (candidate.review_status) {
    case 'ready':
      return 'ready';
    case 'sources_conflict':
      return 'conflict';
    case 'unmapped':
      return 'unmapped';
    case 'resolved':
      return 'resolved';
    case 'needs_review':
      return 'needsReview';
    default:
      break;
  }
  if (candidate.unresolved_reason) return 'conflict';
  if (candidate.proposable) return 'ready';
  if (candidate.kind === 'field' && candidate.target_field_path === null) return 'unmapped';
  return 'needsReview';
}

export const BUCKET_STATE: Readonly<Record<CandidateBucket, SemanticState>> = {
  ready: 'ready',
  needsReview: 'needsReview',
  conflict: 'conflict',
  unmapped: 'unmapped',
  resolved: 'complete',
};

export const BUCKET_ORDER: readonly CandidateBucket[] = [
  'ready',
  'conflict',
  'needsReview',
  'resolved',
  'unmapped',
];

export function bucketCounts(candidates: readonly ApiImportCandidate[]): Record<CandidateBucket, number> {
  const out: Record<CandidateBucket, number> = {
    ready: 0,
    needsReview: 0,
    conflict: 0,
    unmapped: 0,
    resolved: 0,
  };
  for (const c of candidates) out[candidateBucket(c)] += 1;
  return out;
}

/** The concept an ARCHIVE candidate carries in its id (`<stem>::<concept>[::resolved]`). */
export function candidateConcept(candidate: ApiImportCandidate): string | null {
  const parts = candidate.candidate_id.split('::');
  if (parts.length < 2) return null;
  const last = parts[parts.length - 1] === 'resolved' ? parts[parts.length - 2] : parts[parts.length - 1];
  if (last === 'unit' || last === 'conflict' || /^\d+$/.test(last ?? '')) return null;
  return last ?? null;
}

const FIELD_LABELS = new Map(RECORD_FIELDS.map((f) => [f.path, f.label]));

/**
 * A human name for a candidate — never the raw schema path, which stays available
 * as a detail. Archive candidates name their concept; example-source candidates
 * name their field (the record screen's own label when it has one, else the path's
 * last segment in words); structural candidates say what they are.
 */
export function candidateLabel(candidate: ApiImportCandidate): string {
  if (candidate.kind === 'run') return 'Candidate run';
  if (candidate.kind === 'experiment') return 'Candidate experiment';
  const concept = candidateConcept(candidate);
  if (concept) {
    /* ONE CASE FOR EVERY NAME: the registry's labels are sentence case ("Acquisition
       timestamp"), and a concept it does not label is humanized to the same case
       rather than Title Case, so two neighbouring rows never differ only in casing. */
    const label = conceptLabel(concept);
    return label.charAt(0).toUpperCase() + label.slice(1).toLowerCase();
  }
  const path = candidate.target_field_path;
  if (path) {
    const known = FIELD_LABELS.get(path);
    if (known) return known;
    const last = path.split('.').filter(Boolean).pop() ?? path;
    const words = bl15Humanize(last.replace(/\[\]$/, ''));
    return words.charAt(0).toUpperCase() + words.slice(1).toLowerCase();
  }
  return 'Unplaced value';
}

/** A candidate's value as text, or `null` when no value has been selected. */
export function candidateValue(candidate: ApiImportCandidate): string | null {
  const v = candidate.proposed_value;
  if (v === null || v === undefined) return null;
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

/** How many distinct files stand behind a candidate, from the server's own count. */
export function sourceCount(candidate: ApiImportCandidate): number {
  if (typeof candidate.distinct_sources === 'number') return candidate.distinct_sources;
  return new Set(candidate.supporting_source_ids).size;
}

/* ── summary ──────────────────────────────────────────────────────────────── */

export interface SummaryItem {
  id: string;
  value: number;
  label: string;
}

const plural = (n: number, one: string, many: string) => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;

/**
 * The counts a session opens with. For an archive: measurements, sample groups,
 * conflicts, and the review buckets. For example sources: sources, read,
 * candidates, conflicts, ready. Every number comes from the payload.
 */
export function summaryItems(session: ApiImportSession): SummaryItem[] {
  const candidates = session.reconstruction?.candidates ?? [];
  const counts = bucketCounts(candidates);
  const conflicts = conflictCount(session);
  const out: SummaryItem[] = [];
  const digest = session.corpus_digest;
  if (digest) {
    out.push({ id: 'measurements', value: digest.measurement_units, label: digest.measurement_units === 1 ? 'measurement' : 'measurements' });
    out.push({ id: 'groups', value: digest.sample_groups, label: digest.sample_groups === 1 ? 'sample group' : 'sample groups' });
  } else {
    out.push({ id: 'sources', value: session.sources.length, label: session.sources.length === 1 ? 'source' : 'sources' });
    out.push({ id: 'read', value: session.source_counts.parsed, label: 'read' });
  }
  if (session.reconstruction !== null) {
    out.push({ id: 'candidates', value: candidates.length, label: candidates.length === 1 ? 'candidate' : 'candidates' });
  }
  out.push({ id: 'conflicts', value: conflicts, label: conflicts === 1 ? 'conflict' : 'conflicts' });
  if (session.reconstruction !== null) {
    out.push({ id: 'needs-review', value: counts.needsReview, label: 'need review' });
    out.push({ id: 'ready', value: counts.ready, label: 'ready to send' });
  }
  return out;
}

export function summarySentence(items: readonly SummaryItem[]): string {
  return items.map((i) => `${i.value.toLocaleString('en-US')} ${i.label}`).join(' · ');
}

/* ── conflicts ────────────────────────────────────────────────────────────── */

/**
 * ONE CONFLICT, SOURCE BY SOURCE — a structural disagreement from the archive's
 * relationships, or a field whose sources disagree. Both render the same way.
 */
export interface ConflictView {
  key: string;
  kind: 'structural' | 'field';
  /** The conflict kind (structural) or the concept (field). */
  topic: string;
  subject: string;
  /** The server's explanation, verbatim (structural only). */
  explanation: string | null;
  readings: ConflictReading[];
  /** Tokens that differ between readings, when every reading is a filename-like stem. */
  distinct: string[] | null;
  recommendation: Bl15Conflict['recommendation'] | null;
  resolution: Record<string, unknown> | null;
  /** `conflict_id` for a structural conflict, `candidate_id` for a field. */
  target: { conflict_id: string } | { candidate_id: string } | null;
  /** A resolution recorded here takes effect only for archive readings. */
  resolvable: boolean;
  forbidden: boolean;
  stem: string | null;
  groupToken: string | null;
}

export interface ConflictReading {
  value: string;
  role: string | null;
  roleMeaning: string | null;
  sources: { path: string; locator: string }[];
  sourceType: string | null;
}

export const SOURCE_ROLE_LABELS: Readonly<Record<string, string>> = {
  human_label: 'Filename',
  instrument_header: 'Header',
  planned_acquisition: 'Macro',
  retrospective_note: 'Beamtime notes',
  absence_of_a_source: 'Not stated',
  other_source: 'Other source',
};

export function roleLabel(role: string | null, sourceType: string | null): string {
  if (role && SOURCE_ROLE_LABELS[role]) return SOURCE_ROLE_LABELS[role];
  if (sourceType === 'beamtime_notes') return 'Beamtime notes';
  if (sourceType === 'macro') return 'Macro';
  return 'Source';
}

/** The roles a recurring resolution may choose by (server: `_CHOOSABLE_ROLES`). */
export const CHOOSABLE_ROLES: ReadonlySet<string> = new Set([
  'human_label',
  'instrument_header',
  'planned_acquisition',
  'retrospective_note',
]);

/**
 * The underscore-separated tokens that differ between readings — `after400Cycling`
 * vs `after500Cycling` — so a conflict between two long filenames reads as the one
 * word that differs. `null` when the readings are not stems or nothing differs.
 */
export function distinctTokens(values: readonly string[]): string[] | null {
  if (values.length < 2) return null;
  if (!values.every((v) => /^[\w.-]+$/.test(v) && v.includes('_'))) return null;
  const split = values.map((v) => v.split('_'));
  const common = split.reduce<Set<string>>(
    (acc, tokens) => new Set(tokens.filter((t) => acc.has(t))),
    new Set(split[0]),
  );
  const out = split.map((tokens) => tokens.filter((t) => !common.has(t)).join('_'));
  if (out.some((t) => t.length === 0) || new Set(out).size < 2) return null;
  return out;
}

function structuralReadings(readings: readonly Bl15Reading[]): ConflictReading[] {
  return readings.map((r) => ({
    value: r.value,
    role: r.source_role ?? null,
    roleMeaning: r.source_role_meaning ?? null,
    sources: [{ path: r.source_path, locator: r.locator }],
    sourceType: r.source_type,
  }));
}

/** Every conflict in a session: archive structure first, then field disagreements. */
export function conflictViews(session: ApiImportSession): ConflictView[] {
  const out: ConflictView[] = [];
  const review = session.corpus_review;
  const archiveIds = archiveCandidateIds(session);
  if (review) {
    const push = (conflict: Bl15Conflict, stem: string | null, groupToken: string | null) => {
      const values = conflict.readings.map((r) => r.value);
      out.push({
        key: conflict.conflict_id ?? `${conflict.kind}:${conflict.subject}`,
        kind: 'structural',
        topic: conflict.kind,
        subject: conflict.subject,
        explanation: conflict.explanation,
        readings: structuralReadings(conflict.readings),
        distinct: distinctTokens(values),
        recommendation: conflict.recommendation ?? null,
        resolution: conflict.resolution ?? null,
        target: conflict.conflict_id ? { conflict_id: conflict.conflict_id } : null,
        resolvable: Boolean(conflict.conflict_id),
        forbidden: conflict.recommendation?.status === 'forbidden' || conflict.kind === 'duplicate_legacy_number',
        stem,
        groupToken,
      });
    };
    for (const unit of review.relationships.units) for (const c of unit.conflicts) push(c, unit.stem, unit.group_token);
    for (const c of review.relationships.corpus_conflicts) push(c, null, null);
  }
  const sourceName = new Map(session.sources.map((s) => [s.source_id, s.filename]));
  for (const candidate of session.reconstruction?.candidates ?? []) {
    if (candidate.kind !== 'field' || candidate.disagreement.length === 0) continue;
    // A structural conflict's `run` candidate is the SAME conflict as the one above.
    const values = candidate.disagreement.map((d) => d.value);
    out.push({
      key: candidate.candidate_id,
      kind: 'field',
      topic: candidateLabel(candidate),
      subject: candidate.candidate_id.includes('::') ? candidate.candidate_id.split('::')[0] ?? '' : '',
      explanation: null,
      readings: candidate.disagreement.map((d) => ({
        value: d.value,
        role: null,
        roleMeaning: null,
        sources: d.source_ids.map((id, i) => ({ path: sourceName.get(id) ?? id, locator: d.locators[i] ?? d.locators[0] ?? '' })),
        sourceType: null,
      })),
      distinct: distinctTokens(values),
      recommendation: null,
      resolution: candidate.resolved_by_rule ? { rule_id: candidate.resolved_by_rule, applied: true } : null,
      target: { candidate_id: candidate.candidate_id },
      resolvable: archiveIds.has(candidate.candidate_id),
      forbidden: false,
      stem: candidate.candidate_id.includes('::') ? candidate.candidate_id.split('::')[0] ?? null : null,
      groupToken: null,
    });
  }
  return out;
}

export function conflictCount(session: ApiImportSession): number {
  return conflictViews(session).filter((c) => !isResolved(c)).length;
}

export function isResolved(view: ConflictView): boolean {
  return view.resolution !== null && view.resolution !== undefined;
}

/** Candidate ids that belong to an archive reading (resolutions only apply to those). */
export function archiveCandidateIds(session: ApiImportSession): Set<string> {
  const out = new Set<string>();
  const archive = session.archive;
  if (!archive) return out;
  for (const row of archive.units_page.rows) for (const id of row.candidate_ids) out.add(id);
  for (const id of archive.shared_candidate_ids) out.add(id);
  // A derived `::resolved` candidate is listed by the unit too, but be lenient.
  for (const c of session.reconstruction?.candidates ?? []) if (c.candidate_id.includes('::')) out.add(c.candidate_id);
  return out;
}

/* ── conventions ──────────────────────────────────────────────────────────── */

/** A convention's short name: the part before its " — measured on …" clause. */
export function shortConventionName(displayName: string): string {
  const cut = displayName.split(' — ')[0] ?? displayName;
  return cut.trim();
}

export const SCOPE_LABELS: Readonly<Record<string, string>> = {
  facility: 'Facility',
  beamline: 'Beamline',
  acquisition_system: 'Acquisition system',
  experiment: 'Whole import',
  source_family: 'Source family',
  run_subset: 'Some runs',
  source: 'One source',
};

export const BASIS_LABELS: Readonly<Record<string, string>> = {
  build_default: 'Build default',
  import_session_choice: 'Chosen for this import',
  confirmed_rule: 'Confirmed rule',
  mixed: 'Mixed',
};

export const RULE_SCOPE_LABELS: Readonly<Record<string, string>> = {
  import: 'Only this import',
  experiment: 'This experiment',
  profile: 'This convention',
};

export const RULE_KIND_LABELS: Readonly<Record<string, string>> = {
  profile_binding: 'Naming convention',
  conflict_resolution: 'Resolved conflict',
  signal_assignment: 'Signal channel',
};

/* ── HERFD signal ─────────────────────────────────────────────────────────── */

/**
 * A signal selection's state. A `proposed` channel is a SUGGESTION awaiting a
 * scientist — never shown as decided.
 */
export function signalState(selection: ApiImportSignalSelection): { state: SemanticState; label: string } {
  switch (selection.status) {
    case 'proposed':
      return { state: 'awaitingJudgment', label: 'Suggested' };
    case 'confirmed':
      return { state: 'complete', label: 'Confirmed' };
    case 'needs_review':
      return { state: 'needsReview', label: 'Needs Review' };
    default:
      return { state: 'needsReview', label: 'Not Resolved' };
  }
}

export function liveChannels(selection: ApiImportSignalSelection): string[] {
  return selection.channels.filter((c) => c.liveness === 'live').map((c) => c.channel);
}

/* ── add to experiment ────────────────────────────────────────────────────── */

/**
 * WHY A CANDIDATE WAS NOT SENT, IN WORDS — the server's `error` code named for a
 * scientist. The server's own sentence stays available beside it.
 */
export const NOT_SENT_REASONS: Readonly<Record<string, string>> = {
  candidate_unresolved: 'Sources disagree — decide in Conflicts first',
  candidate_not_proposable: 'Nowhere to write it in this build',
  target_requires_a_run: 'Needs a run to belong to',
};

export function notSentReason(row: Pick<ApiImportUnsentCandidate, 'error'>): string {
  return NOT_SENT_REASONS[row.error] ?? 'Could not be sent';
}

/** Group a batch's unsent rows by reason, in a stable order. */
export function groupNotSent(rows: readonly ApiImportUnsentCandidate[]): { reason: string; rows: ApiImportUnsentCandidate[] }[] {
  const out = new Map<string, ApiImportUnsentCandidate[]>();
  for (const row of rows) {
    const reason = notSentReason(row);
    const list = out.get(reason);
    if (list) list.push(row);
    else out.set(reason, [row]);
  }
  return [...out.entries()].map(([reason, list]) => ({ reason, rows: list }));
}

/** What the batch WOULD not send, grouped the same way, before anything is sent. */
export function wouldNotSend(candidates: readonly ApiImportCandidate[]): { reason: string; count: number }[] {
  const out = new Map<string, number>();
  for (const c of candidates) {
    if (c.proposable) continue;
    const reason = c.unresolved_reason
      ? NOT_SENT_REASONS.candidate_unresolved
      : c.kind !== 'field'
        ? 'A run or experiment, not a value'
        : c.target_field_path === null
          ? 'No field in the official schema'
          : 'Nowhere to write it in this build';
    out.set(reason, (out.get(reason) ?? 0) + 1);
  }
  return [...out.entries()].map(([reason, count]) => ({ reason, count }));
}

export const MATCHED_BY_LABELS: Readonly<Record<string, string>> = {
  acquisition_identity: 'found by the file’s own identity',
  label_before_origins_existed: 'found by its label (made before identities were recorded)',
};

/** A measurement row's candidates, in the session's own order. */
export function unitCandidates(
  unit: ApiImportUnitRow,
  byId: ReadonlyMap<string, ApiImportCandidate>,
): ApiImportCandidate[] {
  return unit.candidate_ids.map((id) => byId.get(id)).filter((c): c is ApiImportCandidate => c !== undefined);
}

export { plural };

import type {
  ApiImportCandidate,
  ApiImportSession,
  ApiImportSignalSelection,
  ApiImportUnitRow,
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
  /* "Need review" and "ready to send" are counted over FIELD candidates, exactly as the
     Review stage and its tab count them — a structural candidate ("a measurement
     exists") is never sent, so counting it here made the header disagree with the tab. */
  const counts = bucketCounts(candidates.filter((c) => c.kind === 'field'));
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
    // WHAT CAN STILL GO FORWARD: the batch's own sendable set, less what this import has
    // already sent — so the header drops after a send instead of repeating the old count.
    out.push({ id: 'ready', value: readyToSend(session).length, label: 'ready to send' });
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
/**
 * The name a READING goes by on a conflict row. A structural reading has a source
 * ROLE (Filename, Header, Macro…); a field disagreement's readings have none, and
 * "Source · Source · Source" told a reader nothing — so those are named by the file
 * that states them, its base name only (the full path is in Source Facts).
 */
export function readingLabel(reading: Pick<ConflictReading, 'role' | 'sourceType' | 'sources'>): string {
  if (reading.role !== null && SOURCE_ROLE_LABELS[reading.role]) return SOURCE_ROLE_LABELS[reading.role];
  if (reading.role === null && reading.sourceType === null) {
    const path = reading.sources[0]?.path;
    if (path) return path.split('/').filter(Boolean).pop() ?? path;
  }
  return roleLabel(reading.role, reading.sourceType);
}

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
/**
 * WHY A CANDIDATE IS NOT SENT — ONE CATEGORISATION, before and after (2026-09-23).
 *
 * The Add stage used to predict with one rule ("Nowhere to write it: 37") and report
 * with another (89 under the same words). Both now run THIS function over the same four
 * facts — the batch's error code, the candidate's kind, its target field and its reason —
 * whether the facts come from the published `send_plan` or from the batch's `not_sent`
 * rows. A structural finding is never counted as a conflict to decide: it is not a value.
 */
export type UnsentCategory =
  | 'field_conflict'
  | 'structural'
  | 'measurement'
  | 'experiment'
  | 'not_a_run'
  | 'whole_import'
  | 'local_time'
  | 'no_field'
  | 'no_write_route'
  | 'needs_decision'
  | 'needs_a_run'
  | 'other';

export const UNSENT_CATEGORY_ORDER: readonly UnsentCategory[] = [
  'field_conflict',
  'needs_decision',
  'whole_import',
  'needs_a_run',
  'not_a_run',
  'local_time',
  'no_write_route',
  'no_field',
  'measurement',
  'experiment',
  'structural',
  'other',
];

export const UNSENT_CATEGORY_LABELS: Readonly<Record<UnsentCategory, string>> = {
  field_conflict: 'Field values whose sources disagree — decide them in Conflicts first',
  /*
   * THREE SETS, THREE NAMES (review of #279, I4). The Conflicts stage counts FINDINGS
   * about which measurement a file is — including corpus-wide ones (a legacy number used
   * twice) that no candidate stands for. The rows below count CANDIDATES, so they must not
   * reuse those words: "8 findings" here beside "5 findings" there was two sets under one
   * name. A measurement is not a disagreement either, so it has its own row.
   */
  structural: "Disagreements about one measurement's identity — decided in Conflicts, never sent as values",
  measurement: 'Measurements this import found — not values (the Runs you create come from them)',
  experiment: 'The experiment this import describes — not a value',
  not_a_run: 'Values of a measurement that is not a Run (an alignment scan or a standard)',
  whole_import: 'Stated for the whole import — send each to the run you mean, from Review',
  local_time: 'Local times with no time zone — never sent to a UTC field',
  no_field: 'No field in the official schema takes them — kept as evidence',
  no_write_route: 'Official fields this build has no write route for',
  needs_decision: 'Need a decision before they can go forward',
  needs_a_run: 'Need a run to belong to',
  other: 'Could not be sent',
};

/*
 * The server's own sentences a reason is recognised by. Each is a constant in
 * `historical_import.py` (named beside it) and is compared by its opening words, so a
 * reworded tail does not silently move a candidate between categories.
 */
const REASON_PREFIXES: readonly [UnsentCategory, string][] = [
  // CANDIDATE_NOT_PROPOSABLE_NOT_A_RUN
  ['not_a_run', 'This value belongs to a measurement this import does not offer as a Run'],
  // CANDIDATE_NOT_PROPOSABLE_LOCAL_TIME
  ['local_time', "This time is written in the instrument's local clock"],
  // CANDIDATE_NOT_PROPOSABLE_NO_WRITE_PATH
  ['no_write_route', 'This IS an official ISAAC field, and no write operation'],
];

export interface UnsentFacts {
  error: string;
  kind: string;
  target_field_path: string | null;
  reason: string | null;
}

export function unsentCategory(facts: UnsentFacts): UnsentCategory {
  if (facts.kind !== 'field') {
    if (facts.error === 'candidate_unresolved') return 'structural';
    return facts.kind === 'experiment' ? 'experiment' : 'measurement';
  }
  if (facts.error === 'candidate_unresolved') return 'field_conflict';
  if (facts.error === 'no_run_for_this_candidate') return 'whole_import';
  if (facts.error === 'target_requires_a_run') return 'needs_a_run';
  if (facts.error === 'candidate_not_proposable') {
    for (const [category, prefix] of REASON_PREFIXES) {
      if (facts.reason?.startsWith(prefix)) return category;
    }
    if (facts.target_field_path === null) return 'no_field';
    return 'needs_decision';
  }
  return 'other';
}

/** Group rows by category, in the fixed order. */
export function groupUnsent<T extends UnsentFacts>(rows: readonly T[]): { category: UnsentCategory; label: string; rows: T[] }[] {
  const out = new Map<UnsentCategory, T[]>();
  for (const row of rows) {
    const category = unsentCategory(row);
    const list = out.get(category);
    if (list) list.push(row);
    else out.set(category, [row]);
  }
  return UNSENT_CATEGORY_ORDER.filter((c) => out.has(c)).map((category) => ({
    category,
    label: UNSENT_CATEGORY_LABELS[category],
    rows: out.get(category)!,
  }));
}

/**
 * The batch's plan for THIS session, as rows the categorisation reads — from the
 * published `send_plan` (the batch's own partition) and each candidate's own facts.
 * `alreadySent` are the candidates this import already sent (the session remembers
 * them in `proposed`), and are neither "can be sent" nor "will not be sent".
 */
export function planFor(session: ApiImportSession, createRuns: boolean) {
  const candidates = session.reconstruction?.candidates ?? [];
  const byId = new Map(candidates.map((c) => [c.candidate_id, c]));
  const plan = session.send_plan;
  const sent = session.proposed ?? {};
  const sendable = plan
    ? plan.sendable
    : candidates.filter((c) => c.proposable).map((c) => c.candidate_id);
  const noRun = new Set(createRuns && plan ? plan.no_run_when_creating_runs : []);
  const notSentEntries: [string, string][] = plan
    ? Object.entries(plan.not_sent)
    : candidates
        .filter((c) => !c.proposable)
        .map((c) => [c.candidate_id, c.unresolved_reason ? 'candidate_unresolved' : 'candidate_not_proposable']);
  const unsent: (UnsentFacts & { candidate_id: string })[] = [];
  for (const [id, error] of notSentEntries) {
    const c = byId.get(id);
    if (!c) continue;
    unsent.push({
      candidate_id: id,
      error,
      kind: c.kind,
      target_field_path: c.target_field_path,
      reason: c.not_proposable_reason,
    });
  }
  for (const id of noRun) {
    const c = byId.get(id);
    if (!c || sent[id]) continue;
    unsent.push({ candidate_id: id, error: 'no_run_for_this_candidate', kind: c.kind, target_field_path: c.target_field_path, reason: null });
  }
  return {
    willSend: sendable.filter((id) => !sent[id] && !noRun.has(id)),
    alreadySent: sendable.filter((id) => Boolean(sent[id])),
    unsent,
  };
}

/** Candidates that can go forward and have not been sent yet — the "ready to send" count. */
export function readyToSend(session: ApiImportSession): string[] {
  return planFor(session, false).willSend;
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

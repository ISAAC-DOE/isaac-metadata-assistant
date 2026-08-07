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
  Inferability,
  PendingBlocker,
  QueueGroup,
  QueueGroupKey,
  RunnerStage,
  SourceType,
  ValidationResult,
} from './types';

// REMOVED: `const TECHNIQUE = 'Cu K-edge XANES'`, which every adapted row carried
// as `technique`. It was a scientific value invented in the client — the list
// endpoint carries no technique field, so nothing in any response supported it —
// and its own comment said so ("a display label, not a server field") as though
// that made it safe. It did not: `technique` is a real, schema-governed scientific
// property (`system.technique`, an enum), and a hard-coded one would have been
// wrong for any record that was not Cu K-edge XANES with no signal that it was
// fabricated. It was never rendered, which is luck, not design — it sat one JSX
// line away from the queue row. `technique` is now optional and simply absent:
// the honest representation of a value the server does not send.

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

/**
 * The advisory code the backend emits when a record carries no measured series —
 * `src/isaac_records/portal_warnings.py::_no_measurement_series`. Declared ONCE
 * here because two surfaces that show the coverage figure key on it, and a second
 * copy of the literal is a second thing to forget when the code is renamed.
 * `apps/api/tests/test_coverage_denominator_disclosure.py` pins this file against
 * the code the Python check actually emits, so a rename on either side fails.
 */
export const NO_MEASUREMENT_SERIES_CODE = 'NO_MEASUREMENT_SERIES';

/**
 * WHY THE COVERAGE FIGURE NEEDS THIS, stated where the predicate lives.
 *
 * `isaac_records.audit` enumerates the coverage DENOMINATOR from the record's own
 * content — one block target per series present, so a record whose
 * `measurement.series` is `[]` contributes NO series target at all. Measured on the
 * canonical worked example: 33 / 33 expected targets with its series, 32 / 32 with
 * the series emptied. Both read as full coverage. So the number alone cannot
 * distinguish "everything is evidenced" from "there is less to evidence", and a
 * record holding no measured data can reach a reader as 100 % complete.
 *
 * The sentence states only what is observable from the record and from the
 * enumeration rule. It deliberately does NOT say the record is invalid,
 * incomplete, or not applicable: `measurement.series` has no `minItems` in the
 * vendored schema, so `[]` validates with zero errors, and which of those four
 * meanings an empty series has is a scientific decision for a domain owner. It is
 * not made here, and nothing here gates on it.
 *
 * Position-neutral on purpose: the badge renders it under the figure, the
 * StatusBar footer puts it beside the figure, and the Assistant appends it to a
 * sentence — so it must not say "above".
 *
 * WHAT THE SENTENCE UNDERSTATES, measured, and why it is not broadened.
 * `NO_MEASUREMENT_SERIES` fires on TWO record shapes, and the denominator loses a
 * different amount in each. Measured on `qa/validator-upload-package/
 * complete-valid-record.json` via `_scalar_targets` + `_block_targets`:
 *
 *     unmodified                    → 35 targets
 *     `measurement.series` == []    → 34  (removed: series:merged_normalized_spectrum)
 *     `measurement` deleted         → 31  (also removed: qc:status, and the two
 *                                          scalars measurement.processing
 *                                          .recipe_link.{rel,target})
 *
 * The advisory code is IDENTICAL for both shapes, so this module cannot tell them
 * apart, and the sentence therefore names only the loss both shapes share — the
 * series target. On the second shape it is true but incomplete. It is deliberately
 * not broadened: asserting a dropped QC target would be FALSE on the far more
 * common `series: []` shape, where `qc:status` is still counted. The general
 * caveat that covers the remainder is the badge's second static line ("A full
 * count means every target this record has is evidenced — not that any particular
 * target exists"), which is unconditional and true of both. Closing the gap
 * properly needs a shape-distinguishing signal the backend does not emit today.
 */
export const NO_SERIES_COVERAGE_NOTE =
  'This record carries no measurement series, so no series target is counted.';

/**
 * The same disclosure, shortened for the StatusBar footer — DERIVED from the
 * sentence above, never a second literal.
 *
 * `.statusbar` is a fixed 52px single-line flex row (`components/chrome.css`) with
 * no wrap: three signal segments plus a right tail already fill it, and dropping a
 * 74-character sentence in squeezes the other two segments rather than adding a
 * line. So the footer shows ONE clause and carries the whole sentence in an
 * `.sr-only` span and a `title`, so nothing is only available to a hovering mouse.
 *
 * WHICH CLAUSE, AND WHY IT CHANGED (F6). This was the CONSEQUENCE clause, "no
 * series target is counted", on the reasoning that it is the half that qualifies
 * the number. Read alone — which is exactly how it renders, immediately after
 * `evidence 32/32 · Coverage` — it has no antecedent, so it reads as "the coverage
 * metric does not count series": a claim about the METRIC, and the opposite of
 * `CoverageBadge`'s "Counted from what this record contains: … series …". Both
 * strings render simultaneously on Export Readiness, so an ambiguity that inverts
 * one of them is not survivable. The footer therefore shows the OBSERVATION clause,
 * which carries its own subject and cannot be read as a statement about the metric.
 * It is 41 characters against the consequence's 27 and the full sentence's 74 — the
 * reason for shortening at all is the fixed row, and this is still 33 characters
 * shorter than the sentence. That trade-off is a visual judgement, and no test in
 * this repo measures it: the seeded records all carry a series, so no e2e surface
 * renders this segment at any viewport.
 *
 * The split is on the sentence's own `, so ` hinge and FAILS SAFE: if a future
 * edit removes that hinge, this falls back to the full sentence (visually long in
 * the footer, still true) rather than to a truncated or empty string.
 * `apps/api/tests/test_coverage_denominator_disclosure.py` pins that both halves
 * of the sentence survive the derivation, and that the half shown here keeps a
 * subject.
 */
export const NO_SERIES_COVERAGE_NOTE_SHORT = ((): string => {
  const hinge = ', so ';
  const i = NO_SERIES_COVERAGE_NOTE.indexOf(hinge);
  if (i < 0) return NO_SERIES_COVERAGE_NOTE;
  return NO_SERIES_COVERAGE_NOTE.slice(0, i);
})();

/**
 * The verdict words the coverage disclosure may not contain — ONE list, imported
 * by every guard that checks the sentence.
 *
 * It existed in three hand-maintained copies (this repo's Python guard plus two
 * vitest files) and had already drifted: `error` was in the Python list and in
 * neither TypeScript one. That is the same defect the shared sentence constant
 * exists to prevent, one level up, so the list is shared the same way. The Python
 * guard reads this array out of this file rather than restating it; see
 * `_forbidden_verdict_words` in
 * `apps/api/tests/test_coverage_denominator_disclosure.py`.
 *
 * `missing` and `needs` are here because they were absent from all three copies
 * while carrying a normative implication — "the measurement series is missing"
 * passes a list built only of verdict nouns, and *missing* is one of the four
 * candidate meanings (invalid / incomplete / not applicable / deliberately empty)
 * that belong to a domain owner.
 *
 * WHAT THIS LIST CANNOT DO. It is a blacklist over one sentence, so it cannot
 * establish that the sentence classifies nothing — only that it uses none of
 * these words. A novel classifying phrasing ("no usable spectrum was recorded",
 * "this record has nothing to evidence") passes every entry. A human reviewer
 * remains the backstop; the tests that use it are named for the mechanism, not
 * for the universal.
 */
export const VERDICT_WORDS_FORBIDDEN_IN_DISCLOSURE = [
  'invalid',
  'incomplete',
  'not applicable',
  'failed',
  'compromised',
  'suspicious',
  'should',
  'must',
  'error',
  'missing',
  'needs',
] as const;

/** True when the advisory reports that this record carries no measured series. */
export function carriesNoMeasurementSeries(advisory: AdvisoryResult): boolean {
  return advisory.warnings.some((w) => w.code === NO_MEASUREMENT_SERIES_CODE);
}

// --- S4 completion blockers ---------------------------------------------
// The /pending items (id / kind / question / about / demo_answer) become the
// render blockers. Asset blockers take a pasted sha256; series/descriptor carry
// a structured value the user can only *confirm* from the labeled example answer —
// the UI never lets the assistant type a scientific value.

const KIND_LABEL: Record<string, string> = {
  asset: 'Asset Hash',
  series: 'Reduced Spectrum',
  descriptor: 'Scientific Descriptor',
  edge: 'Absorption Edge',
};

// Sentence-case helper copy (never a scientific value) explaining each blocker
// and reinforcing the no-guessing contract.
// TWO variants per structured kind, because the example answer is no longer
// present on every record. Scoping it to the built-in walkthrough records made
// the old single sentence FALSE wherever it was withheld: "Confirm the example
// value, or leave it honestly missing" told the reader to confirm something not
// on screen. A `managed_legacy` record (workspace.py) is a real, reachable case.
// The `withExample` copy is used only when a `demo_answer` actually arrived.
//
// A SECOND review then caught the replacement over-claiming in the other
// direction. It said "Leave it honestly missing UNLESS YOU CAN SUPPLY IT", which
// invites the reader to supply a value the screen gives them no way to supply:
// for a structured blocker with no example, `GuidedPrompt` renders a hint and
// nothing else — the input row, and the Confirm button inside it, are behind
// `{demo && (…)}` (`GuidedPrompt.tsx`), and the edit path is gated the same way
// (`GuidedCompletion.tsx` passes `initialStaged` but the Save control lives in
// that same `demo` branch). So the copy now states the dead end plainly instead
// of pointing at a control that is not rendered. It deliberately does NOT name a
// screen where the value CAN be entered: no such path was verified, and naming an
// unverified one would repeat the defect at one remove. Building a structured
// input is a feature, and out of scope for this slice.
const KIND_CONTEXT: Record<string, string> = {
  asset:
    'An asset can only be cited once it carries a hash. Paste the sha256 — the system will never generate this value for you.',
  series:
    'A structured reduced-spectrum value the system will never generate for you. No example is available for this record, and this screen has no way to enter one, so the field stays honestly missing here.',
  descriptor:
    'A structured scientific descriptor the system will never generate for you. No example is available for this record, and this screen has no way to enter one, so the field stays honestly missing here.',
};

const KIND_CONTEXT_WITH_EXAMPLE: Record<string, string> = {
  series:
    'A structured reduced-spectrum value the system will never generate for you. Confirm the example value, or leave it honestly missing.',
  descriptor:
    'A structured scientific descriptor the system will never generate for you. Confirm the example value, or leave it honestly missing.',
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

/**
 * Evidence source types that DO speak about the record in hand — a POSITIVE
 * allowlist mirroring `inferability.RECORD_EVIDENCE_SOURCE_TYPES`
 * (`draft_validator.OBSERVED_SOURCE_TYPES` plus `derivation`).
 *
 * It replaces a denylist of the ten known non-evidence types, and the difference
 * is not cosmetic: a denylist passes everything it has not heard of, so
 * `source_type: 'literature'` — a value this repo's own fixtures use — and an
 * outright invented `'vibes'` both sailed through while the backend's positive
 * allowlist refused them. An unrecognised source type is now refused here too.
 *
 * The duplication of the server's list is deliberate. This guard exists to hold
 * when the server's copy does not, so deriving it from the response would defeat
 * the point. `suggestion-provenance.test.tsx` pins the two in step.
 */
const RECORD_EVIDENCE_SOURCE_TYPES = new Set([
  'document',
  'spreadsheet',
  'screenshot',
  'web_form',
  'file_listing',
  'user_confirmation',
  'derivation',
]);

/** Confidence-like keys, mirroring `inferability._CONFIDENCE_KEYS`. */
const CONFIDENCE_KEYS = new Set(['confidence', 'probability', 'score']);

/**
 * True if any confidence-like key appears anywhere in `node`'s tree.
 *
 * Recursive for the same reason the server's scan is: this repo's corpus nests
 * the key one level down (`"uncertainty": {"confidence": 0.86}`), so a top-level
 * check misses the shape it was written for. Depth-bounded — evidence entries are
 * small, hand-authored objects.
 */
function hasConfidenceKey(node: unknown, depth = 0): boolean {
  if (depth > 12 || node === null || typeof node !== 'object') return false;
  if (Array.isArray(node)) return node.some((v) => hasConfidenceKey(v, depth + 1));
  return Object.entries(node as Record<string, unknown>).some(
    ([k, v]) => CONFIDENCE_KEYS.has(k) || hasConfidenceKey(v, depth + 1),
  );
}

/**
 * Re-check, on arrival, the clauses that let an `Inferability` carry a concrete
 * value. A value may accompany `supported_suggestion` and no other state, and only
 * with a provenance that survives every check below.
 *
 * The backend enforces this in `Inferability.__post_init__` and `_check_evidence`;
 * this is a deliberate SECOND check on the same rules. What it guards against is
 * not a backend bug we know of — it is a future response shape that quietly grows
 * a value where the client does not expect one. It fails closed by nulling the
 * value AND detaching the provenance that failed to justify it.
 *
 * Scope, stated precisely because an earlier version of this comment claimed
 * "every clause the backend checks" and did not deliver it: this mirrors the
 * server's state/value pairing, provenance completeness, `unique`, `rule`, the
 * evidence source-type allowlist, the nested confidence scan, the
 * derivation-needs-a-rule rule, and the non-empty `explanation`. It does NOT
 * re-check `detail` against the server's per-state key allowlist (`_DETAIL_SCHEMA`)
 * — `detail` cannot carry a value past the server's own type checks, and
 * duplicating a five-state key map here would be a third copy to keep in step.
 */
export function sanitizeInferability(inf: Inferability | undefined): Inferability | undefined {
  if (!inf) return undefined;
  const p = inf.provenance;
  const evidenceSpeaksAboutThisRecord = (e: { source_type?: string }) =>
    typeof e?.source_type === 'string' &&
    RECORD_EVIDENCE_SOURCE_TYPES.has(e.source_type) &&
    // A derivation must state the rule it applied; an unstated one is a bare assertion.
    (e.source_type !== 'derivation' || !!(e as { rule?: string }).rule) &&
    !hasConfidenceKey(e);

  const justified =
    inf.state === 'supported_suggestion' &&
    typeof inf.explanation === 'string' &&
    inf.explanation.length > 0 &&
    !!p &&
    p.unique === true &&
    !!p.rule &&
    Array.isArray(p.supporting_fields) &&
    p.supporting_fields.length > 0 &&
    Array.isArray(p.supporting_evidence) &&
    p.supporting_evidence.length > 0 &&
    p.supporting_evidence.every(evidenceSpeaksAboutThisRecord);

  if (justified) return inf;
  // Nothing to strip only when there is neither a value nor an unjustified
  // provenance. Leaving provenance attached to a non-supported state was itself a
  // hole: it presents a justification for a value the state says does not exist.
  if ((inf.value === null || inf.value === undefined) && !p) return inf;
  return { ...inf, value: null, provenance: null };
}

/** Map one live /pending item onto the render blocker the GuidedPrompt consumes. */
export function pendingItemToBlocker(item: ApiPendingItem): PendingBlocker {
  const hasExample = !!item.demo_answer;
  return {
    id: item.id,
    kind: item.kind,
    question: item.question,
    label: KIND_LABEL[item.kind] ?? titleCase(String(item.kind)),
    path: pathTokenFor(item),
    about: item.about ?? undefined,
    // The "confirm the example value" wording is used ONLY when an example value
    // actually arrived — see the note on KIND_CONTEXT_WITH_EXAMPLE.
    context:
      (hasExample ? KIND_CONTEXT_WITH_EXAMPLE[item.kind] : undefined) ?? KIND_CONTEXT[item.kind],
    inputType: inputTypeForKind(item.kind),
    demo_answer: item.demo_answer
      ? {
          value: item.demo_answer.value,
          label: item.demo_answer.label,
          // Carried through, not re-derived. The client must never be the thing
          // that decides an example answer counts as evidence.
          provenance: item.demo_answer.provenance,
        }
      : undefined,
    inferability: sanitizeInferability(item.inferability),
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

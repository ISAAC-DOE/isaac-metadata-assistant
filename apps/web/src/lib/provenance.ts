/*
 * UNIFIED PROVENANCE — the client mirror of `apps/api/isaac_api/provenance.py`.
 *
 * TWO INDEPENDENT DIMENSIONS, and they are never combined into one value:
 *
 *   ORIGIN        where a value came from
 *   REVIEW STATE  what, if anything, establishes it
 *
 * THE SERVER IS AUTHORITATIVE. `GET /api/experiments/{id}/provenance` computes
 * both dimensions from stored content; the pure helpers below exist so a surface
 * that ALREADY holds an evidence entry (the evidence trail, a field row) can show
 * the same two dimensions without a second request. They are a display mirror,
 * never a second source of truth — and `provenance.test.ts` asserts, against the
 * Python source itself, that the two vocabularies and the precedence order match.
 *
 * WHY ORIGIN CARRIES NO COLOUR. See `ORIGIN_CHIP` in `status.ts`: every origin
 * chip is neutral, and only the review-state chip is coloured. Where a value came
 * from says nothing about whether it is backed, so an origin must not be able to
 * read as an approval — not through its words and not through its palette.
 *
 * WHAT THIS FILE DOES NOT CLAIM. `voice` and `assistant` are members of the
 * dimension because the dimension is closed and describable; nothing in this build
 * transcribes speech and nothing produces an assistant-written value. No surface
 * may list them as available capabilities — they render only when data says so.
 */

import type { FieldEvidence, FieldStatus, SourceType } from './types';

// --- dimension 1: origin -----------------------------------------------------

export const PROVENANCE_ORIGINS = [
  'manual',
  'file',
  'voice',
  'inherited',
  'assistant',
  'derived',
  'evidence',
  'unknown',
] as const;

export type ProvenanceOrigin = (typeof PROVENANCE_ORIGINS)[number];

/**
 * Every ISAAC evidence `source_type`, mapped. `web_form` is a FILE, not a manual
 * entry: it is an ingested capture of a form filled in elsewhere (it always cites
 * a source file and a locator), and `user_confirmation` is the only evidence type
 * this application mints for a person's own act.
 */
export const SOURCE_TYPE_ORIGIN: Record<SourceType, ProvenanceOrigin> = {
  user_confirmation: 'manual',
  document: 'file',
  spreadsheet: 'file',
  screenshot: 'file',
  file_listing: 'file',
  web_form: 'file',
  derivation: 'derived',
};

/** Every note `source`, mapped. Mirrors the backend table of the same name. */
export const NOTE_SOURCE_ORIGIN: Readonly<Record<string, ProvenanceOrigin>> = {
  typed_note: 'manual',
  transcript: 'voice',
  csv_column: 'file',
  file_listing_line: 'file',
  extraction_residue: 'file',
};

/**
 * The order `primaryOrigin` reads, highest first — NEVER array position.
 *
 * A mixed-origin value is announced under the origin a reader most needs to know
 * about, which is the one carrying the least direct human accountability, so a
 * value that is partly machine-produced is never headlined by the human half.
 * `inherited` leads as a structural exception (the run does not hold the value at
 * all) and `unknown` is last (any determinate origin outranks it).
 */
export const ORIGIN_PRECEDENCE: readonly ProvenanceOrigin[] = [
  'inherited',
  'assistant',
  'evidence',
  'derived',
  'voice',
  'file',
  'manual',
  'unknown',
];

/** Product words. None of them says "verified" — that word belongs to the core. */
export const ORIGIN_LABEL: Record<ProvenanceOrigin, string> = {
  // Not "Entered by you": this build stamps no actor, so it cannot say WHO.
  manual: 'Entered by a person',
  file: 'From a file',
  voice: 'From a transcript',
  inherited: 'Inherited from the record',
  assistant: 'From an assistant',
  derived: 'Derived by a rule',
  evidence: 'From recorded evidence',
  unknown: 'Origin not recorded',
};

export const ORIGIN_MEANING: Record<ProvenanceOrigin, string> = {
  manual: 'Someone answered a question about this in this application.',
  file: 'Read out of a file — a document, a spreadsheet, a screenshot, a file listing, or a captured form.',
  voice: 'Captured from a transcript.',
  inherited:
    'This run does not hold the value itself; it resolves to the record-level value, which flows through whenever the record changes.',
  assistant: 'Recorded as produced by an assistant.',
  derived: 'Produced by a documented derivation rule. A rule is a mechanism, not an acceptance.',
  evidence:
    'A stored citation backs this, but it does not say what kind of source produced it.',
  unknown:
    'Nothing stored here says where the value came from. That is a statement about the record, not a guess.',
};

// --- dimension 2: review state -----------------------------------------------

export const PROVENANCE_REVIEW_STATES = [
  'supported',
  'needs_review',
  'conflict',
  'unmapped',
  // A conflict a PERSON decided, and only while that decision still covers the
  // answers a reader is looking at. Declaration order mirrors the backend tuple
  // exactly — `provenance.test.tsx` reads that tuple out of the Python source and
  // compares it element for element, so this list is not free to be tidied.
  'resolved',
] as const;

export type ProvenanceReviewState = (typeof PROVENANCE_REVIEW_STATES)[number];

export const REVIEW_STATE_LABEL: Record<ProvenanceReviewState, string> = {
  supported: 'Supported',
  needs_review: 'Needs review',
  conflict: 'Conflicting',
  unmapped: 'Not yet placed',
  resolved: 'Conflict decided',
};

export const REVIEW_STATE_MEANING: Record<ProvenanceReviewState, string> = {
  supported:
    'The stored status is verified and at least one citation backs it. This is not a statement about schema validity, completion, or whether the record can be exported.',
  needs_review:
    'Something is outstanding — an unconfirmed value, a value with no citation, or content this application cannot place on its own.',
  conflict: 'Two or more citations assert values that cannot both be right. A person must decide.',
  unmapped: 'Captured content that has no schema home and that nobody has reviewed yet.',
  resolved:
    'The citations still disagree, and a person recorded which answer they stand behind. Nothing was removed and the field\u2019s own value is unchanged; if further competing evidence arrives, this returns to Conflicting.',
};

// --- pure derivations (mirrors of the backend, for data already on screen) ----

/**
 * The SET of origins one item's citations imply, sorted and deduplicated.
 *
 * An unrecognised or absent `source_type` yields `evidence`, deliberately NOT
 * `unknown`: a citation demonstrably exists and only its channel cannot be named.
 * An empty list yields `[]`; callers decide whether that becomes `unknown`.
 */
export function originsFromEvidence(evidence: readonly FieldEvidence[] | undefined): ProvenanceOrigin[] {
  const found = new Set<ProvenanceOrigin>();
  for (const entry of evidence ?? []) {
    if (!entry || typeof entry !== 'object') continue;
    const mapped = SOURCE_TYPE_ORIGIN[entry.source_type as SourceType];
    found.add(mapped ?? 'evidence');
  }
  return PROVENANCE_ORIGINS.filter((o) => found.has(o)).sort();
}

/** The origin a note's `source` implies, or `unknown` when it names none we map. */
export function originForNoteSource(source: string | undefined): ProvenanceOrigin {
  return (source && NOTE_SOURCE_ORIGIN[source]) || 'unknown';
}

/** The single headline origin, by `ORIGIN_PRECEDENCE`. Never by array position. */
export function primaryOrigin(origins: readonly string[] | undefined): ProvenanceOrigin {
  const present = new Set(origins ?? []);
  for (const origin of ORIGIN_PRECEDENCE) {
    if (present.has(origin)) return origin;
  }
  return 'unknown';
}

/** A key-stable stringify, so object answers compare the way the server compares them. */
function stableKey(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value) ?? 'null';
  if (Array.isArray(value)) return `[${value.map(stableKey).join(',')}]`;
  const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
    a < b ? -1 : a > b ? 1 : 0,
  );
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${stableKey(v)}`).join(',')}}`;
}

/**
 * Whether an item's citations assert values that cannot both be right — the
 * client's mirror of the backend conflict rule: two or more DISTINCT non-null
 * asserted answers.
 */
export function hasConflictingEvidence(evidence: readonly FieldEvidence[] | undefined): boolean {
  const asserted = new Set<string>();
  for (const entry of evidence ?? []) {
    if (!entry || typeof entry !== 'object') continue;
    if (entry.answer === undefined || entry.answer === null) continue;
    asserted.add(stableKey(entry.answer));
  }
  return asserted.size >= 2;
}

/**
 * The review state for an item this client already holds.
 *
 * Precedence, mirroring the backend: conflict, then unmapped, then supported
 * (which needs BOTH a `verified` status AND at least one citation), then
 * `needs_review` for everything else — including every status this mirror does
 * not recognise. The catch-all is deliberately the conservative one.
 *
 * `status` is deliberately typed loosely: the evidence trail can carry
 * `'unavailable'`, which is not a field status and must land in `needs_review`
 * rather than being coerced into something reassuring.
 */
// THIS MIRROR NEVER RETURNS `resolved`, DELIBERATELY. A recorded decision is not
// in the data this function is given — it lives in the record's own document and
// reaches a client only through the provenance response's `review_state` and
// `resolution_state`. Deriving `resolved` from evidence alone is impossible, and
// guessing it would be the one thing this mirror must not do.
export function reviewStateFor(item: {
  status?: FieldStatus | 'unavailable' | string | null;
  evidence?: readonly FieldEvidence[];
  noteState?: string | null;
}): ProvenanceReviewState {
  if (hasConflictingEvidence(item.evidence)) return 'conflict';
  if (item.noteState === 'unreviewed') return 'unmapped';
  if (item.status === 'verified' && (item.evidence?.length ?? 0) >= 1) return 'supported';
  return 'needs_review';
}

// --- the wire shape ----------------------------------------------------------
//
// REMOVED 2026-08-27: `ApiProvenanceEntry` and `ApiProvenance` were declared HERE and
// AGAIN in `lib/api.ts`, both for `GET /api/experiments/{id}/provenance`, with
// different types — this pair closed `origins`/`primary_origin`/`review_state` to the
// unions above and omitted `unavailable` and `resolution_state` — and NOTHING enforced
// agreement between them. Nothing was broken only because this pair had no importer,
// which is luck rather than design: the next consumer to reach for the nearer of the
// two would have got a shape the server does not send.
//
// THE SURVIVING DECLARATION IS IN `lib/types.ts`, with the OPEN `string` typing. That
// is the deliberate half of the choice: `originLabel` below does
// `ORIGIN_LABEL[origin] ?? origin`, and that fallback needs an unrecognised origin to
// be representable. The unions in this module remain correct for what they describe —
// this client's own derivation from an evidence entry it already holds — and are
// unchanged. Do not re-declare a wire shape here.

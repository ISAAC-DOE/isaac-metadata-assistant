/*
 * Single source of truth mapping core field status → UI StatusChip kind, plus
 * each chip kind's Title Case label and palette class. Keeping this in one place
 * guarantees needs_confirmation → Needs You and user_confirmation → Confirmed by
 * You render consistently everywhere (react-build-notes.md).
 */

import type {
  EvidenceClass,
  FieldStatus,
  ReconciliationState,
  SourceType,
} from './types';
import { LABELS } from './labels';
// The two provenance dimensions own their own product words, next to the pure
// helpers that produce them — so a chip label and the dimension it names cannot
// drift apart, and the cross-language parity test has one file to check.
import {
  ORIGIN_LABEL,
  REVIEW_STATE_LABEL,
  type ProvenanceOrigin,
  type ProvenanceReviewState,
} from './provenance';

export type ChipKind =
  | 'verified'
  | 'confirmed'
  | 'inferred'
  | 'missing'
  | 'needsYou'
  | 'pass'
  | 'fail'
  | 'exported'
  | 'mentorReview'
  | 'draft'
  // P28.5 — the evidence-SUPPORT axis (distinct from field status above). These
  // six never mean schema-valid / complete / exportable; they describe only how
  // well a value is backed by evidence — or, for `evUnreadable`, that the server
  // could not read the evidence and so states nothing about its support.
  | 'evSupported'
  | 'evCandidate'
  | 'evInsufficient'
  | 'evConflicting'
  | 'evUnknown'
  | 'evUnreadable'
  // P31.3 — the CSV reconciliation axis (RECONCILIATION-ONLY). These describe
  // only how a proposed CSV value compares to the CURRENT record; they never
  // mean valid / complete / exportable, and no reconciled field is editable.
  | 'reconMatch'
  | 'reconConflict'
  | 'reconAbsent'
  // The unified-provenance ORIGIN axis — WHERE a value came from. Eight kinds,
  // and every one of them is visually NEUTRAL by design (see `ORIGIN_CHIP`):
  // where a value came from says nothing about whether anything establishes it,
  // so an origin must not be able to read as an approval, through its words or
  // through its palette.
  | 'origManual'
  | 'origFile'
  | 'origVoice'
  | 'origInherited'
  | 'origAssistant'
  | 'origDerived'
  | 'origEvidence'
  | 'origUnknown'
  // The unified-provenance REVIEW axis — what, if anything, establishes the
  // value. This is the half that carries colour, and it is still not a validity,
  // completion or export verdict.
  | 'revSupported'
  | 'revNeedsReview'
  | 'revConflict'
  | 'revUnmapped'
  | 'revResolved';

export interface ChipMeta {
  label: string;
  className: string; // palette class defined in StatusChip.css
}

export const CHIP_META: Record<ChipKind, ChipMeta> = {
  verified: { label: LABELS.chipVerified, className: 'chip-verified' },
  confirmed: { label: LABELS.chipConfirmed, className: 'chip-confirmed' },
  inferred: { label: LABELS.chipInferred, className: 'chip-inferred' },
  missing: { label: LABELS.chipMissing, className: 'chip-missing' },
  needsYou: { label: LABELS.chipNeedsYou, className: 'chip-needsyou' },
  pass: { label: LABELS.chipPass, className: 'chip-pass' },
  fail: { label: LABELS.chipFail, className: 'chip-fail' },
  exported: { label: LABELS.chipExported, className: 'chip-exported' },
  mentorReview: { label: LABELS.chipMentorReview, className: 'chip-mentor' },
  draft: { label: LABELS.chipDraft, className: 'chip-draft' },
  // Evidence-support axis (P28.5). `evCandidate`/`evUnknown` are dashed so an
  // unconfirmed candidate is never styled as a confirmed fact.
  evSupported: { label: LABELS.chipEvSupported, className: 'chip-ev-supported' },
  evCandidate: { label: LABELS.chipEvCandidate, className: 'chip-ev-candidate' },
  evInsufficient: { label: LABELS.chipEvInsufficient, className: 'chip-ev-insufficient' },
  evConflicting: { label: LABELS.chipEvConflicting, className: 'chip-ev-conflicting' },
  evUnknown: { label: LABELS.chipEvUnknown, className: 'chip-ev-unknown' },
  // Dashed like `evUnknown`/`evCandidate`, because this is likewise not
  // established support — but its own palette and its own words, so a reader is
  // never told "Unknown" about an entry that was merely unreadable.
  evUnreadable: { label: LABELS.chipEvUnreadable, className: 'chip-ev-unreadable' },
  // Reconciliation axis (P31.3). `reconAbsent` is dashed so an unmatched value is
  // never styled as an established fact.
  reconMatch: { label: LABELS.chipReconMatch, className: 'chip-recon-match' },
  reconConflict: { label: LABELS.chipReconConflict, className: 'chip-recon-conflict' },
  reconAbsent: { label: LABELS.chipReconAbsent, className: 'chip-recon-absent' },
  // ORIGIN axis. SEVEN of the eight share ONE neutral palette class, and that
  // repetition is the assertion, not an oversight: no origin may be styled as
  // reassuring or as alarming. `origUnknown` gets the dashed variant of the same
  // neutral palette because it is an ABSENCE, which is a different fact from any
  // of the seven — not a different level of confidence in the value.
  origManual: { label: ORIGIN_LABEL.manual, className: 'chip-origin' },
  origFile: { label: ORIGIN_LABEL.file, className: 'chip-origin' },
  origVoice: { label: ORIGIN_LABEL.voice, className: 'chip-origin' },
  origInherited: { label: ORIGIN_LABEL.inherited, className: 'chip-origin' },
  origAssistant: { label: ORIGIN_LABEL.assistant, className: 'chip-origin' },
  origDerived: { label: ORIGIN_LABEL.derived, className: 'chip-origin' },
  origEvidence: { label: ORIGIN_LABEL.evidence, className: 'chip-origin' },
  origUnknown: { label: ORIGIN_LABEL.unknown, className: 'chip-origin-absent' },
  // REVIEW axis. `revUnmapped` is dashed for the same reason `missing` is: it is
  // content that has not been placed, never an established fact.
  revSupported: { label: REVIEW_STATE_LABEL.supported, className: 'chip-rev-supported' },
  revNeedsReview: { label: REVIEW_STATE_LABEL.needs_review, className: 'chip-rev-needsreview' },
  revConflict: { label: REVIEW_STATE_LABEL.conflict, className: 'chip-rev-conflict' },
  revUnmapped: { label: REVIEW_STATE_LABEL.unmapped, className: 'chip-rev-unmapped' },
  // A conflict a person DECIDED. It borrows the `confirmed` palette — "somebody
  // said so" — and deliberately NOT the `verified` palette `revSupported` wears:
  // a recorded decision about which citation to stand behind is not the same fact
  // as a value with established evidence support, and one shade apart is how two
  // different facts come to read as one.
  revResolved: { label: REVIEW_STATE_LABEL.resolved, className: 'chip-rev-resolved' },
};

/**
 * Map an ORIGIN to its chip kind (single source). Kept strictly apart from
 * `REVIEW_STATE_CHIP` below — the two dimensions are independent, and no code
 * path derives one from the other.
 */
export const ORIGIN_CHIP: Record<ProvenanceOrigin, ChipKind> = {
  manual: 'origManual',
  file: 'origFile',
  voice: 'origVoice',
  inherited: 'origInherited',
  assistant: 'origAssistant',
  derived: 'origDerived',
  evidence: 'origEvidence',
  unknown: 'origUnknown',
};

/** Map a REVIEW STATE to its chip kind (single source). */
export const REVIEW_STATE_CHIP: Record<ProvenanceReviewState, ChipKind> = {
  supported: 'revSupported',
  needs_review: 'revNeedsReview',
  conflict: 'revConflict',
  unmapped: 'revUnmapped',
  resolved: 'revResolved',
};

/**
 * Map a CSV reconciliation state to its chip kind (single source). A separate
 * axis from field status and evidence support — a reconciled value is only ever
 * read-only evidence, never a write to the record.
 */
export const RECONCILE_STATE_CHIP: Record<ReconciliationState, ChipKind> = {
  matches_current: 'reconMatch',
  conflicts_with_current: 'reconConflict',
  absent_from_record: 'reconAbsent',
};

/**
 * Map an evidence-support class to its chip kind (single source). Kept separate
 * from `mapFieldStatus` because evidence support is a DIFFERENT axis from field
 * status — a field can be `verified` (status) yet only `inferred_candidate`
 * (support), and the UI must never conflate the two.
 */
export const EVIDENCE_CLASS_CHIP: Record<EvidenceClass, ChipKind> = {
  supported: 'evSupported',
  inferred_candidate: 'evCandidate',
  insufficient_evidence: 'evInsufficient',
  conflicting_evidence: 'evConflicting',
  unknown: 'evUnknown',
  unreadable: 'evUnreadable',
};

/** Map a core field envelope status to the UI chip kind. */
export function mapFieldStatus(status: FieldStatus): ChipKind {
  switch (status) {
    case 'verified':
      return 'verified';
    case 'inferred':
      return 'inferred';
    case 'needs_confirmation':
      return 'needsYou';
    case 'missing':
    case 'rejected':
      return 'missing';
    default:
      return 'missing';
  }
}

/**
 * When a field's evidence is human-supplied (user_confirmation), the chip reads
 * "Confirmed by You" (the human motif) rather than machine "Verified".
 */
export function fieldChipKind(
  status: FieldStatus,
  sourceTypes: SourceType[] = [],
): ChipKind {
  if (status === 'verified' && sourceTypes.includes('user_confirmation')) {
    return 'confirmed';
  }
  return mapFieldStatus(status);
}

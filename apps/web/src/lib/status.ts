/*
 * Single source of truth mapping core field status → UI StatusChip kind, plus
 * each chip kind's Title Case label and palette class. Keeping this in one place
 * guarantees needs_confirmation → Needs You and user_confirmation → Confirmed by
 * You render consistently everywhere (react-build-notes.md).
 */

import type { EvidenceClass, FieldStatus, SourceType } from './types';
import { LABELS } from './labels';

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
  // five never mean schema-valid / complete / exportable; they describe only how
  // well a value is backed by evidence.
  | 'evSupported'
  | 'evCandidate'
  | 'evInsufficient'
  | 'evConflicting'
  | 'evUnknown';

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

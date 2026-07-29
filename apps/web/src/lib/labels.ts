/*
 * Centralized label vocabulary + casing helpers.
 *
 * Registers (design-handoff/05-design-system/casing-and-copy.md):
 *   1. Title Case for labels / titles / chips / nav / tabs / steps / headers.
 *   2. sentence case for body / helper / replies (authored inline, not here).
 *   3. technical identifiers rendered VERBATIM, never re-cased (mono).
 *
 * `titleCase()` and `isTechnical()` are the single source of truth so a
 * technical token (XANES, sha256, JSON paths, v1.05) is never Title-Cased.
 */

import { VERSION_BADGE } from './runtimeContext';

// Technical identifiers that must render exactly as written (never re-cased).
export const TECHNICAL: readonly string[] = [
  'ISAAC',
  'XANES',
  'CuO',
  'CuO2',
  'Cu',
  'Cu K-edge',
  'K-edge',
  'HERFD-XAS',
  'JSON',
  'CSV',
  'sha256',
  'ULID',
  'NO_LINKS',
  'QC_NONVALID_WITHOUT_EVIDENCE',
  'Graphify',
  'v1.05',
  'K',
  'L3',
  'eV',
  'spreadsheet',
  'file_listing',
  'derivation',
  'user_confirmation',
];

const TECHNICAL_SET = new Set(TECHNICAL);

// Small words that stay lowercase in Title Case unless they lead the phrase.
const MINOR_WORDS = new Set([
  'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'in', 'of', 'on', 'or',
  'the', 'to', 'vs', 'via', 'with',
]);

/**
 * A token is technical (render verbatim, never re-case) when it is a known
 * identifier, or structurally looks like one: a dotted JSON path, a file path,
 * a snake_case token, a version like `v1.05`, a `[CODE]`, or a long hex hash.
 */
export function isTechnical(token: string): boolean {
  if (TECHNICAL_SET.has(token)) return true;
  const bare = token.replace(/^\[|\]$/g, '');
  if (TECHNICAL_SET.has(bare)) return true;
  if (/[._/]/.test(token) && !/\s/.test(token)) return true; // path or dotted.path
  if (/_/.test(token)) return true; // snake_case enum / code
  if (/^v\d/.test(token)) return true; // version token
  if (/^[0-9a-f]{16,}$/i.test(token)) return true; // hash-ish
  if (/[A-Z]{2,}/.test(token) && token === token.toUpperCase()) return true; // ALLCAPS code
  return false;
}

function capitalizeWord(word: string): string {
  if (word.length === 0) return word;
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
}

/**
 * Title-Case a label while preserving technical tokens verbatim.
 * Whole-string technical identifiers (e.g. `Cu K-edge`, `sha256`, `v1.05`)
 * pass through unchanged.
 */
export function titleCase(input: string): string {
  const trimmed = input.trim();
  if (trimmed.length === 0) return trimmed;
  if (isTechnical(trimmed)) return trimmed;

  const words = trimmed.split(/\s+/);
  return words
    .map((word, index) => {
      if (isTechnical(word)) return word;
      const lower = word.toLowerCase();
      if (index !== 0 && MINOR_WORDS.has(lower)) return lower;
      // Preserve internal hyphenation (Title-Case each hyphen segment).
      if (word.includes('-')) {
        return word
          .split('-')
          .map((seg) => (isTechnical(seg) ? seg : capitalizeWord(seg)))
          .join('-');
      }
      return capitalizeWord(word);
    })
    .join(' ');
}

// Approved Title Case UI labels (verbatim from casing-and-copy.md).
export const LABELS = {
  // App / brand
  brand: 'ISAAC',
  // Derived, never a literal: the old `isaac v0.1.0 · local` rendered on the
  // hosted deployment too, where "local" is false. See `lib/runtimeContext.ts`.
  version: VERSION_BADGE,

  // Nav destinations
  navExperiments: 'My Experiments',
  navMemory: 'Project Memory',
  navGovernance: 'Governance & Safety',
  navSettings: 'Settings',

  // Screen titles
  screenExperiments: 'My Experiments',
  screenLoad: 'Load Materials',
  screenReview: 'Review Record',
  screenComplete: 'Complete Missing Fields',
  screenEvidence: 'Evidence & File Preview',
  screenExport: 'Ready to Export',

  // Queue groups
  groupNeedsAttention: 'Needs Attention',
  groupInReview: 'In Review',
  groupReady: 'Ready to Export',
  groupDone: 'Done',

  // Workflow steps
  stepDraft: 'Draft',
  stepComplete: 'Complete',
  stepExport: 'Export',
  stepValidate: 'Validate',
  stepAudit: 'Audit',
  workflowEyebrow: 'Workflow',

  // Status chips
  chipVerified: 'Verified',
  chipConfirmed: 'Confirmed by You',
  chipInferred: 'Inferred',
  chipMissing: 'Missing',
  chipNeedsYou: 'Needs You',
  chipPass: 'PASS',
  chipFail: 'FAIL',
  chipExported: 'Exported',
  chipMentorReview: 'Mentor Review',
  chipDraft: 'Draft',
  modeSynthetic: 'Synthetic',

  // Evidence-support classes (P28.5) — a separate axis from the status chips above.
  chipEvSupported: 'Supported',
  chipEvCandidate: 'Inferred Candidate',
  chipEvInsufficient: 'Insufficient Evidence',
  chipEvConflicting: 'Conflicting Evidence',
  chipEvUnknown: 'Unknown',

  // CSV reconciliation states (P31.3) — a separate axis again. These never mean
  // valid / complete / exportable; they only compare a proposed CSV value to the
  // current record, and the value is always read-only evidence.
  chipReconMatch: 'Matches Record',
  chipReconConflict: 'Conflicts',
  chipReconAbsent: 'Absent From Record',

  // Signals
  signalValidation: 'Validation',
  signalCoverage: 'Coverage',
  signalAdvisory: 'Advisory',
  evidenceAudit: 'Evidence Audit',

  // Actions
  actionRunDemo: 'Run Synthetic Demo',
  actionRunDemoShort: 'Run Demo',
  actionNewRecord: 'New Record',
  actionResetDemo: 'Reset Demo',
  actionCancel: 'Cancel',

  // Guarded synthetic-demo reset (P26.0b)
  resetDialogTitle: 'Reset Shared Synthetic Demo',
  resetConfirmAction: 'Reset Shared Demo',
  resetCountCurrent: 'Current Experiments',
  resetCountCanonical: 'Canonical Scenarios Preserved',
  resetCountLegacy: 'Legacy Demo Records Removed',
  resetCountAmbiguous: 'Ambiguous Records',
  resetCountFinal: 'Final Experiments',
  actionReviewAnswer: 'Review & Answer',
  actionConfirm: 'Confirm',
  actionEdit: 'Edit',
  actionSave: 'Save',
  actionRevalidate: 'Re-Validate',
  actionDownload: 'Download',
  actionViewJson: 'View JSON',
  actionView: 'View',
  actionOpenSource: 'Open Source File',
  actionReadPolicy: 'Read Policy',
  actionBackToComplete: 'Back to Complete',
  actionLoadLocal: 'Load Local Structured Files',
  actionDontKnow: "I don't know — leave honestly missing",

  // Evidence / preview
  evidence: 'Evidence',
  evidenceTrail: 'Evidence Trail',
  directFields: 'Direct Fields',
  namespaced: 'Namespaced',
  tabSource: 'Source File',
  tabRecord: 'Record JSON',
  tabSidecar: 'Sidecar JSON',
  cited: 'Cited',
  readOnly: 'read-only',

  // Assistant
  assistant: 'Assistant',
  assistantSuggestion: 'Assistant Suggestion',
  suggestedQuestions: 'Suggested Questions',
  actionStageAnswer: 'Stage Answer',

  // Export artifacts
  officialRecord: 'Official Record',
  sidecarConvention: 'sidecar · assistant convention, not an official ISAAC standard',
  sidecarNotOfficial: 'assistant convention — not official',
} as const;

export type LabelKey = keyof typeof LABELS;

// --- date formatting (P33 S1) ------------------------------------------
// Fixed month-name arrays (never `Date`/`Intl` locale formatting) so the
// dashboard card's date badge is deterministic across environments.
const SHORT_MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];
const FULL_MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export interface FormattedDate {
  iso: string; // "2026-07-12" — machine-readable, for <time dateTime>
  display: string; // "Jul 12, 2026"
  accessible: string; // "Created July 12, 2026"
}

/**
 * Parse the `YYYY-MM-DD` prefix of an ISO date/datetime string into a
 * deterministic machine + display + accessible triple. Never uses `Date`
 * parsing/locale — a fixed month-name lookup keeps rendering identical in every
 * environment. `iso` is the exact date prefix so a `<time dateTime>` carries a
 * valid machine value.
 */
export function formatCreatedDate(isoDate: string): FormattedDate | undefined {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!m) return undefined;
  const [, year, monthStr, dayStr] = m;
  const monthIndex = Number(monthStr) - 1;
  const day = Number(dayStr);
  if (monthIndex < 0 || monthIndex > 11 || Number.isNaN(day) || day < 1 || day > 31) {
    return undefined;
  }
  const shortMonth = SHORT_MONTHS[monthIndex];
  const fullMonth = FULL_MONTHS[monthIndex];
  return {
    iso: `${year}-${monthStr}-${dayStr}`,
    display: `${shortMonth} ${day}, ${year}`,
    accessible: `Created ${fullMonth} ${day}, ${year}`,
  };
}

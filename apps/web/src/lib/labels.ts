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
  navStatistics: 'Statistics',
  // Names what the destination actually holds — runtime status plus programmatic
  // access — rather than promising preferences this build does not have. This is
  // the SINGLE authored string: the nav label and the page <h1> both read it.
  navSettings: 'Settings & API',

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
  /*
   * The mode chip's BASE label.
   *
   * "workspace" scopes the claim to what the reader is looking at: since Slice 2A
   * the deployment may additionally run a protected read-only diagnostic over an
   * isolated test database, so an unqualified whole-deployment claim would
   * over-claim. That scoping is why the word "workspace" is load-bearing and must
   * survive any rewording.
   *
   * R0 replaced the first word. "Synthetic" is the name of the runtime MODE — it
   * is what `GET /api/health` reports, it is what `runtime_mode.py` refuses to
   * boot without, and none of that changed — but as the persistent chip on every
   * screen it was the app describing itself in the vocabulary of its own test
   * harness. "Example workspace" is the product-facing name for the same thing.
   *
   * THE CLAIM THE OLD WORD CARRIED IS NOT DROPPED, it is moved somewhere it fits:
   * `CHIP_ARIA_DETAIL` in `components/TopBar.tsx` now spells out, in plain
   * language, that the records are rebuilt from reference files committed to the
   * build, that file upload is refused, and that no official institutional record
   * is shown. The full disclosure still lives in the Governance banner, the
   * Governance & Safety policy tab and the Help panel, whose exact technical
   * wording is deliberately UNCHANGED — a chip is not the place to make a
   * governance guarantee, but it must not be the place a guarantee quietly
   * disappears either.
   */
  modeSynthetic: 'Example workspace',
  // Deliberate register exception (see the header: register 1 is Title Case).
  // These two are QUALIFIERS appended after "·" to the base chip label above,
  // not standalone labels — Title-Casing them ("Test DB Diagnostics") would read
  // as the name of a feature the app does not have. "DB" is a generic word, not
  // a database name; neither string names a host, database, user, or secret.
  modeTestDbDiagnostics: 'test DB diagnostics',
  // NOT "unavailable": /api/health does zero I/O, so this reflects the last
  // diagnostic RUN recorded in the server process, which may be stale. See the
  // reasoning comment in components/TopBar.tsx before changing this wording.
  modeTestDbCheckFailed: 'test DB check failed',

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
  actionRunDemo: 'Open the Worked Example',
  actionRunDemoShort: 'Run the Worked Example',
  // The /load breadcrumb. NOT "New Record": nothing on that screen can create a
  // record — its second on-ramp is a permanent governance refusal — so the
  // breadcrumb names what the screen actually offers.
  actionOpenRecord: 'Open a Record',
  actionResetDemo: 'Reset Workspace',
  actionCancel: 'Cancel',

  // Guarded example-workspace reset (P26.0b)
  resetDialogTitle: 'Reset the Shared Workspace',
  resetConfirmAction: 'Reset Shared Workspace',
  resetCountCurrent: 'Current Experiments',
  resetCountCanonical: 'Built-in Examples Restored',
  resetCountLegacy: 'Additional Records Removed',
  resetCountAmbiguous: 'Ambiguous Records',
  resetCountFinal: 'Final Experiments',

  // R1 — the DERIVED at-risk disclosure. Every number in the sentence this heads is
  // computed by the server from persisted state and rendered verbatim; the UI adds
  // no estimate, no rounding, and no reassurance the numbers do not support. The
  // heading is deliberately second person and blunt: the previous dialog stated a
  // record COUNT and left the operator to infer what a count of five meant for the
  // afternoon's work.
  resetAtRiskLabel: 'What you would lose',
  resetAtRiskNothing:
    'Nothing. None of the built-in examples has been changed since it was set up.',

  // R1 — the workspace moved between opening this window and pressing the button, so
  // the server refused and wrote nothing. This copy has three jobs and does all
  // three: say plainly that no records changed, say WHY the refusal happened in
  // terms of the workspace rather than of HTTP, and send the operator back to the
  // refreshed numbers. It must NEVER offer a one-click retry: the figures the
  // operator approved are no longer the figures that apply, so re-approving is the
  // whole point rather than a formality.
  resetStaleTitle: 'Nothing was reset — this workspace changed',
  resetStaleBody:
    'Something in this workspace changed after this window opened, so the reset was ' +
    'refused and no records were changed. The figures below have been refreshed. ' +
    'Please read them again and confirm again if you still want to reset.',

  // The worked example refused to re-run because its target record has been
  // edited (POST /api/demo/run → 409 `demo_target_drifted`). The server protected
  // the edits instead of overwriting them, so this copy states three things and
  // guesses nothing further: the example did NOT run, why, and that Reset
  // Workspace is the deliberate — and equally destructive — way back to the
  // baseline. It must never read as a backend failure (the server answered,
  // correctly) and must never imply anything was lost. The remedy sentence names
  // the reset control by its EXACT rendered label (`actionResetDemo`) — if that
  // label changes, this string changes with it.
  demoDriftedTitle: 'Example not re-run — this record has been edited',
  demoDriftedBody:
    'The built-in example is restored from fixed reference files. This record has been ' +
    'edited since it was created, and restoring it would discard those edits — so the ' +
    'server refused. Nothing ran and nothing changed.',
  demoDriftedRemedy:
    'To return to the baseline deliberately, use Reset Workspace on My Experiments. That ' +
    'restores all five built-in examples and discards these edits with them.',
  demoDriftedScenario: 'Edited record',
  actionGoToExperiments: 'Go to My Experiments',
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

  /*
   * Guided walkthrough (R0). Deliberately NOT placed beside the reset labels
   * above: a walkthrough replay and a workspace reset are different in kind, and
   * nothing here is allowed to grow into a control that changes a record.
   *
   * "Skip for Now" is the offer's decline, and its wording is the contract: it
   * says "not now", and the code honours exactly that — the completion flag is not
   * written, so the offer returns on the next visit, and it stays hidden for the
   * rest of this session so the reader is not asked twice.
   */
  actionStartTutorial: 'Start Tutorial',
  actionSkipForNow: 'Skip for Now',
  actionSkipTutorial: 'Skip Tutorial',
  actionTutorialBack: 'Back',
  actionTutorialNext: 'Next',
  actionTutorialFinish: 'Finish',
  actionCloseTutorial: 'Close Tutorial',
  actionReplayTutorial: 'Replay Tutorial',

  tutorialOfferTitle: 'Take the Guided Walkthrough',
  tutorialOfferBody:
    'A short guided tour of this app, pointing at the real controls on the real screens: what this ' +
    'list holds, how a record shows what it still needs, how evidence and confirmation work, and ' +
    'why export stays closed until a record earns it. It only reads — it answers nothing and ' +
    'changes nothing.',

  // The mandated completion copy. Sentence case is deliberate here: it is an
  // outcome statement rather than the name of a surface, and it matches
  // `demoDriftedTitle` above, the other outcome statement in this file.
  tutorialCompleteTitle: 'Tutorial complete',
  tutorialCompleteBody:
    'That is the whole workflow. Nothing you have looked at was changed, and any work already in ' +
    'this workspace is untouched. You can reopen this walkthrough from Settings & API → Help & ' +
    'Tutorial at any time.',

  settingsTabHelp: 'Help & Tutorial',

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

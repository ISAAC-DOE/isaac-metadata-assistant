/*
 * The guided walkthrough's step catalog — the ONE place its content lives.
 *
 * A step is not a slide. Every entry names a REAL control that exists in this
 * build, addressed by a `data-tutorial-anchor` attribute on that control, and
 * the walkthrough navigates to the surface the control lives on before it points
 * at it. Nothing here describes a feature the build does not have, and nothing
 * here is illustrated with a picture of a control instead of the control.
 *
 * TWO KINDS OF "NOT AVAILABLE", kept apart on purpose:
 *
 *   1. A step needs a record in a particular state (unanswered fields, or all
 *      fields answered and not yet exported) and the workspace has none. That is
 *      an ordinary, honest outcome of a shared workspace, and the step says so in
 *      its own words — see `unavailable`. The walkthrough NEVER answers a
 *      question, exports a record, or resets anything to manufacture the state it
 *      wants to demonstrate.
 *
 *   2. The anchor is genuinely absent from the surface it is supposed to be on.
 *      That is a REGRESSION, not a state, and it is caught two ways: a source
 *      scan asserts every token below is really rendered somewhere in
 *      `apps/web/src` (`__tests__/tutorial-anchors.test.tsx`), and at runtime the
 *      step degrades to a visible explanation rather than a coach mark pointing
 *      at nothing.
 *
 * STEPS THAT WERE DELIBERATELY NOT BUILT, and why — recorded here so a later
 * reader does not "restore" them by inventing an anchor:
 *
 *   · EDITING A CONFIRMED VALUE. The only edit affordance in this build is the
 *     Edit button on an ALREADY-CONFIRMED answer row, and that row exists only
 *     after a confirmation made in the current session. Anchoring a step to it
 *     would require the walkthrough to confirm a scientific value on the reader's
 *     behalf, which the no-guessing rules forbid outright. The behaviour is
 *     described inside the confirmation step instead of being pointed at.
 *
 *   · CONFLICTS AND STALE CHANGES. The "this record changed elsewhere" notice and
 *     the stale-artifact note render only when a concurrent change has actually
 *     happened. There is no honest way to anchor them without provoking one, so
 *     the walkthrough does not claim to show them.
 */

/**
 * Every anchor token the walkthrough may address. Tokens are values, not
 * free-form strings at the call sites, so a typo is a type error rather than a
 * step that silently points at nothing.
 */
export const TUTORIAL_ANCHORS = {
  experimentsQueue: 'experiments-queue',
  experimentRow: 'experiment-row',
  recordWorkflow: 'record-workflow',
  recordSignals: 'record-signals',
  recordPending: 'record-pending',
  recordEvidenceTrail: 'record-evidence-trail',
  completionQuestion: 'completion-question',
  completionConfirm: 'completion-confirm',
  completionDontKnow: 'completion-dont-know',
  exportValidation: 'export-validation',
  exportGate: 'export-gate',
  exportRepair: 'export-repair',
  exportAction: 'export-action',
  standaloneValidator: 'standalone-validator',
  settingsSections: 'settings-sections',
  tutorialReplay: 'tutorial-replay',
} as const;

export type TutorialAnchor = (typeof TUTORIAL_ANCHORS)[keyof typeof TUTORIAL_ANCHORS];

/** The CSS selector for one anchor token. The single place the attribute name is
 *  written, so the engine and the tests cannot disagree about it. */
export const TUTORIAL_ANCHOR_ATTRIBUTE = 'data-tutorial-anchor';

export function tutorialAnchorSelector(anchor: string): string {
  return `[${TUTORIAL_ANCHOR_ATTRIBUTE}="${anchor}"]`;
}

/**
 * Which record a step needs, if any.
 *
 *   none          — a surface that exists regardless of what the workspace holds
 *   anyRecord     — any record at all will do
 *   pendingRecord — a record with at least one unanswered field, not yet exported
 *   readyRecord   — a record with zero unanswered fields, not yet exported
 */
export type TutorialTargetKind = 'none' | 'anyRecord' | 'pendingRecord' | 'readyRecord';

/** The records the walkthrough resolved by READING the experiment list. Any of
 *  them may be null; a null is a reason to explain, never a reason to guess. */
export interface TutorialTargets {
  anyRecord: string | null;
  pendingRecord: string | null;
  readyRecord: string | null;
}

export const NO_TARGETS: TutorialTargets = Object.freeze({
  anyRecord: null,
  pendingRecord: null,
  readyRecord: null,
});

export interface TutorialStep {
  id: string;
  /** Title Case, register 1 — this is a label. */
  title: string;
  /** sentence case, register 2 — this is body copy. */
  body: string;
  anchor: TutorialAnchor;
  target: TutorialTargetKind;
  /**
   * The surface this step lives on, given the resolved record id (null when the
   * step needs no record). Returns a router path INCLUDING any query the surface
   * needs — never an absolute URL and never a base path, so the deployed
   * `basename` keeps working untouched.
   */
  path: (recordId: string | null) => string;
  /**
   * What the reader is told when the step cannot be shown. It must state the
   * reason and must state that nothing was changed to force it — a walkthrough
   * that quietly skips is indistinguishable from a walkthrough that is broken.
   */
  unavailable: string;
}

/** The generic reason for a step that needs no record and still cannot find its
 *  control: that is a defect in this build, and saying so is more useful than a
 *  mark pointing at empty space. */
const CONTROL_MISSING =
  'this part of the app did not load, so there is nothing to point at. Nothing was changed. ' +
  'You can carry on to the next step.';

const NEEDS_PENDING_RECORD =
  'this step needs a record that still has unanswered fields, and none of the records in this ' +
  'workspace has any right now. Nothing was un-answered or reset to create one.';

const NEEDS_READY_RECORD =
  'this step needs a record whose fields are all answered and which has not been exported yet, ' +
  'and the workspace has none right now. Nothing was answered or exported to create one.';

const NEEDS_ANY_RECORD =
  'this step needs a record to look at, and the workspace list could not be read. Nothing was ' +
  'created to stand in for one.';

/**
 * The walkthrough, in order.
 *
 * The copy is deliberately in product language: a reader opening this app is a
 * scientist, not a maintainer of its test harness. It still makes the app's real
 * claims — records come from reference files committed to the build, file upload
 * is refused, no official institutional record is shown — because dropping a true
 * claim in the course of simplifying the words would be a worse defect than the
 * jargon it replaced.
 */
export const TUTORIAL_STEPS: readonly TutorialStep[] = [
  {
    id: 'experiments-overview',
    title: 'What My Experiments Contains',
    body:
      'Every record in this workspace is listed here, grouped by what it needs next — needs ' +
      'attention, in review, ready to export, or done. Each group is derived from the record’s own ' +
      'state, so nothing here is a score, a trend, or a health rating.',
    anchor: TUTORIAL_ANCHORS.experimentsQueue,
    target: 'none',
    path: () => '/experiments',
    unavailable: CONTROL_MISSING,
  },
  {
    id: 'open-example',
    title: 'Opening a Worked Example',
    body:
      'Each row opens one record. The records here are worked examples rebuilt from reference ' +
      'files committed to this build — you can read them and work through them, and nothing you do ' +
      'here reaches an institutional system.',
    anchor: TUTORIAL_ANCHORS.experimentRow,
    target: 'anyRecord',
    path: () => '/experiments',
    unavailable: NEEDS_ANY_RECORD,
  },
  {
    id: 'record-readiness',
    title: 'How Readiness Is Shown',
    body:
      'The workflow beside the record is its own progress: load, complete, review evidence, review ' +
      'readiness, export. The current step is marked, finished steps link back, and a step you have ' +
      'not reached yet is not clickable. Both the order and each state come from the server — this ' +
      'screen never works them out for itself.',
    anchor: TUTORIAL_ANCHORS.recordWorkflow,
    target: 'anyRecord',
    path: (id) => `/record/${id}`,
    unavailable: NEEDS_ANY_RECORD,
  },
  {
    id: 'record-signals',
    title: 'The Trust Readout',
    body:
      'Along the bottom sit three separate signals: schema validation, evidence coverage, and ' +
      'advisory notes. They stay separate because they mean different things — only validation ' +
      'gates export, and an advisory note never blocks or authorises anything.',
    anchor: TUTORIAL_ANCHORS.recordSignals,
    target: 'anyRecord',
    path: (id) => `/record/${id}`,
    unavailable: NEEDS_ANY_RECORD,
  },
  {
    id: 'record-missing',
    title: 'Finding What Is Still Missing',
    body:
      'This lists the fields the system refused to fill in for you. A missing value is expected ' +
      'rather than an error: it stays empty until you supply it or confirm it, and it is never ' +
      'filled from a plausible guess.',
    anchor: TUTORIAL_ANCHORS.recordPending,
    target: 'pendingRecord',
    path: (id) => `/record/${id}`,
    unavailable: NEEDS_PENDING_RECORD,
  },
  {
    id: 'record-evidence',
    title: 'How Evidence Works',
    body:
      'Every value that is filled in cites where it came from, and this opens the whole record’s ' +
      'evidence trail. A value with nothing to cite is left empty instead — which is why the trail ' +
      'can be read as a record of what is actually supported.',
    anchor: TUTORIAL_ANCHORS.recordEvidenceTrail,
    target: 'anyRecord',
    path: (id) => `/record/${id}`,
    unavailable: NEEDS_ANY_RECORD,
  },
  {
    id: 'complete-question',
    title: 'Answering a Question',
    body:
      'Completion asks one question at a time, and only the questions that actually block export. ' +
      'Where a reference answer exists it is shown beside the field and clearly labelled — it is ' +
      'not part of the record until you confirm it, and it is never typed in for you.',
    anchor: TUTORIAL_ANCHORS.completionQuestion,
    target: 'pendingRecord',
    path: (id) => `/record/${id}/complete`,
    unavailable: NEEDS_PENDING_RECORD,
  },
  {
    id: 'complete-confirm',
    title: 'How Confirmation Works',
    body:
      'Confirming is the moment a value becomes part of the record, and it is always yours to ' +
      'make. What you confirm is stored with the field, so a later reader can tell a value a ' +
      'person confirmed from a value that was read out of a file. Correcting a confirmed value ' +
      'later is an explicit Edit on that answer, never a silent overwrite.',
    anchor: TUTORIAL_ANCHORS.completionConfirm,
    target: 'pendingRecord',
    path: (id) => `/record/${id}/complete`,
    unavailable: NEEDS_PENDING_RECORD,
  },
  {
    id: 'complete-dont-know',
    title: 'When You Do Not Know',
    body:
      '“I don’t know” is a real answer here, not a failure to finish. It writes nothing, leaves ' +
      'the field honestly empty, and keeps export closed until the field is resolved — which is ' +
      'exactly what it is for.',
    anchor: TUTORIAL_ANCHORS.completionDontKnow,
    target: 'pendingRecord',
    path: (id) => `/record/${id}/complete`,
    unavailable: NEEDS_PENDING_RECORD,
  },
  {
    id: 'export-validation',
    title: 'How Validation Works',
    body:
      'Before anything is written, the record is checked against the official ISAAC v1.05 schema. ' +
      'Ahead of export that check is a dry run: it tells you whether export would pass, and it ' +
      'writes nothing either way.',
    anchor: TUTORIAL_ANCHORS.exportValidation,
    target: 'anyRecord',
    path: (id) => `/record/${id}/export`,
    unavailable: NEEDS_ANY_RECORD,
  },
  {
    id: 'export-blocked',
    title: 'Why Export Can Be Blocked',
    body:
      'While fields are still unanswered, export is closed and says how many are holding it. ' +
      'There is no override and no way to sign off past it — the gate is what makes a finished ' +
      'record worth trusting.',
    anchor: TUTORIAL_ANCHORS.exportGate,
    target: 'pendingRecord',
    path: (id) => `/record/${id}/export`,
    unavailable: NEEDS_PENDING_RECORD,
  },
  {
    id: 'export-repair',
    title: 'Repairing What Blocks Export',
    body:
      'This takes you back to the questions holding export closed, so a blocked record is never a ' +
      'dead end. Resolving the cause is the only way forward, and that is deliberate.',
    anchor: TUTORIAL_ANCHORS.exportRepair,
    target: 'pendingRecord',
    path: (id) => `/record/${id}/export`,
    unavailable: NEEDS_PENDING_RECORD,
  },
  {
    id: 'export-available',
    title: 'How Export Becomes Available',
    body:
      'Once every field is resolved and the dry run would pass, export opens. It writes the ' +
      'official record together with an evidence sidecar beside it. Official records are written ' +
      'once and never overwritten, so exporting is a decision rather than a save.',
    anchor: TUTORIAL_ANCHORS.exportAction,
    target: 'readyRecord',
    path: (id) => `/record/${id}/export`,
    unavailable: NEEDS_READY_RECORD,
  },
  {
    id: 'standalone-validator',
    title: 'Where the Standalone Validator Lives',
    body:
      'Governance & Safety holds a validator you can paste any ISAAC record into. It runs the same ' +
      'official schema check and reports the same errors, and it changes nothing in this ' +
      'workspace.',
    anchor: TUTORIAL_ANCHORS.standaloneValidator,
    target: 'none',
    path: () => '/governance?tab=validator',
    unavailable: CONTROL_MISSING,
  },
  {
    id: 'settings-and-api',
    title: 'Where Settings and API Access Live',
    body:
      'Settings & API reports what this build actually is — its version, where its records come ' +
      'from, what it refuses, and how to reach it as a program. Nothing on it is adjustable; it is ' +
      'a readout, and it says so plainly.',
    anchor: TUTORIAL_ANCHORS.settingsSections,
    target: 'none',
    path: () => '/settings',
    unavailable: CONTROL_MISSING,
  },
  {
    id: 'replay',
    title: 'Replaying This Walkthrough',
    body:
      'This walkthrough can be reopened here whenever you want it. Finishing it is remembered by ' +
      'this browser only — there is no account behind it, so another browser or another device ' +
      'will be offered it again.',
    anchor: TUTORIAL_ANCHORS.tutorialReplay,
    target: 'none',
    path: () => '/settings?tab=help',
    unavailable: CONTROL_MISSING,
  },
];

export const TUTORIAL_STEP_COUNT = TUTORIAL_STEPS.length;

/** The record id a step needs, or null when it needs none / none is available. */
export function targetForStep(step: TutorialStep, targets: TutorialTargets): string | null {
  switch (step.target) {
    case 'none':
      return null;
    case 'anyRecord':
      return targets.anyRecord;
    case 'pendingRecord':
      return targets.pendingRecord;
    case 'readyRecord':
      return targets.readyRecord;
  }
}

/** True when the step's required record is missing — knowable WITHOUT waiting on
 *  the DOM, so the honest explanation appears immediately instead of after a
 *  timeout that looks like a hang. */
export function stepNeedsMissingRecord(step: TutorialStep, targets: TutorialTargets): boolean {
  return step.target !== 'none' && targetForStep(step, targets) === null;
}

/** The router path for a step, or null when it cannot be routed (its record is
 *  missing). */
export function stepPath(step: TutorialStep, targets: TutorialTargets): string | null {
  if (stepNeedsMissingRecord(step, targets)) return null;
  return step.path(targetForStep(step, targets));
}

/**
 * Resolve the three target records from the experiment list. READ-ONLY: this is
 * a projection of a list the app already fetches, and it prefers a record that
 * is already in the state a step needs over changing anything to get there.
 */
export function resolveTutorialTargets(
  summaries: readonly {
    id: string;
    pending_count: number;
    exported: boolean;
  }[],
): TutorialTargets {
  const anyRecord = summaries[0]?.id ?? null;
  const pendingRecord =
    summaries.find((s) => s.pending_count > 0 && !s.exported)?.id ?? null;
  const readyRecord =
    summaries.find((s) => s.pending_count === 0 && !s.exported)?.id ?? null;
  return { anyRecord, pendingRecord, readyRecord };
}

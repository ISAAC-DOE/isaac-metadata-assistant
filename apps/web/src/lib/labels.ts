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
   * The mode chip's base label in the ORDINARY workspace.
   *
   * DELIBERATELY NEUTRAL, and this replaces "Example workspace" — which was a
   * FALSE label here, not merely a stale one. The five built-in examples used to
   * be materialised into the ordinary workspace on every read; they are created
   * only inside a worked-example session, so on every ordinary screen "Example
   * workspace" named this scope after content this build never puts there.
   *
   * PHRASED AS WHAT THE BUILD DOES, never as what the directory holds. "The
   * ordinary workspace contains no examples at all" is what this comment used to
   * say, and it is a claim about CONTENTS that nothing measures:
   * `list_experiments(None)` enumerates whatever is on disk and there is no startup
   * migration, so a workspace that already held the five still lists them. See
   * `ORDINARY_ONLY` in `components/TopBar.tsx`, where two successive versions of
   * that contents claim had to be retired, and note that the second was written by
   * a reader of the first correction.
   *
   * A chip is still rendered rather than nothing, for two reasons that are about
   * truth rather than decoration: it is the ONLY surface that reports an
   * UNEXPECTED `health.mode` (see `anomalousMode` in `components/TopBar.tsx` — this
   * cited `modeLabel`, which that file no longer has), and its
   * accessible name is where this deployment's two unconditional claims — file
   * upload is refused, no official institutional record is shown — are carried on
   * every screen. Neither has anywhere else to go on a record surface.
   *
   * "workspace" scopes the claim to what the reader is looking at: since Slice 2A
   * the deployment may additionally run a protected read-only diagnostic over an
   * isolated test database, so an unqualified whole-deployment claim would
   * over-claim. That scoping is why the word "workspace" is load-bearing and must
   * survive any rewording.
   *
   * The full governance disclosure still lives in the Governance banner, the
   * Governance & Safety policy tab and the Help panel, whose exact technical
   * wording is deliberately UNCHANGED — a chip is not the place to make a
   * governance guarantee, but it must not be the place a guarantee quietly
   * disappears either.
   */
  modeOrdinaryWorkspace: 'Workspace',
  /*
   * Shown INSTEAD of `modeOrdinaryWorkspace` while a worked-example session is
   * open — the one scope in which example records really are present.
   *
   * The temporariness of the scope (these records are discarded when the
   * walkthrough ends) is stated in the accessible name rather than crammed into
   * the label, and the persistent worked-example bar states it in visible text
   * beside the controls that act on the scope.
   */
  modeWorkedExample: 'Worked Example',
  // Deliberate register exception (see the header: register 1 is Title Case).
  // "DB" is a generic word, not a database name; neither string names a host,
  // database, user, or secret.
  //
  // THESE ARE NO LONGER APPENDED TO THE CHIP'S VISIBLE TEXT. They were, as
  // "Example workspace · test DB diagnostics", which put an infrastructure
  // disclosure in the primary header of every product screen. The disclosure did
  // not move OUT of the chip — it is still derived from `health.database` and
  // still stated in the chip's accessible name, alongside four other surfaces
  // that already carry it at length (the Governance banner, Governance & Safety →
  // Policy, the Help panel, and Settings → Data & Privacy). Only the visible
  // suffix is gone. Retained as labels because the accessible name and the
  // technical surfaces still read them, and because `product-facing-language`
  // pins their exact wording.
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
  /*
   * The guarded reset, RENAMED because the thing it resets changed.
   *
   * It was "Reset Workspace", on My Experiments, when the five examples lived in
   * the ordinary workspace. `POST /api/demo/reset` now REQUIRES a worked-example
   * session and refuses without one, so the control lives in the worked-example
   * bar and acts on that session alone. "Reset Workspace" would name the wrong
   * scope — a reader would reasonably read it as "reset everything I have".
   *
   * `demoDriftedRemedy` below names this control by this label; the two are pinned
   * to each other in `__tests__/demo-run-drift-refusal.test.tsx`.
   */
  actionResetDemo: 'Reset Worked Example',
  actionCancel: 'Cancel',

  /*
   * Guarded worked-example reset (P26.0b), rescoped.
   *
   * "Shared" is deliberately gone from both strings. It was true of the old single
   * ordinary workspace, and it is FALSE of a worked-example session: sessions are
   * one directory each and are mutually invisible (`test_two_sessions_are_
   * independently_mutable_and_mutually_invisible`), so nothing another reader does
   * can appear here and nothing done here can appear to them.
   *
   * The confirm action is deliberately NOT the same string as the trigger: two
   * controls with one accessible name would be indistinguishable in a screen
   * reader's control list while the dialog is open.
   */
  resetDialogTitle: 'Reset the Worked Example',
  resetConfirmAction: 'Reset Example Records',
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
  // guesses nothing further: the example did NOT run, why, and that Reset Worked
  // Example is the deliberate — and equally destructive — way back to the
  // baseline. It must never read as a backend failure (the server answered,
  // correctly) and must never imply anything was lost. The remedy sentence names
  // the reset control by its EXACT rendered label (`actionResetDemo`) — if that
  // label changes, this string changes with it.
  //
  // WHERE IT POINTS ALSO CHANGED, and that is a correctness fix rather than a
  // rewording: it used to say "on My Experiments", where the control no longer is.
  // `POST /api/demo/run` now requires a worked-example session, so this refusal can
  // only be seen while one is open — and the reset control is therefore already on
  // screen, in the worked-example bar, when this sentence is read.
  demoDriftedTitle: 'Example not re-run — this record has been edited',
  demoDriftedBody:
    'The built-in example is restored from fixed reference files. This record has been ' +
    'edited since it was created, and restoring it would discard those edits — so the ' +
    'server refused. Nothing ran and nothing changed.',
  demoDriftedRemedy:
    'To return to the baseline deliberately, use Reset Worked Example in the worked-example ' +
    'bar above. That restores all five built-in examples in this session and discards these ' +
    'edits with them.',
  demoDriftedScenario: 'Edited record',

  /*
   * The OTHER typed 409 on `POST /api/demo/run`: no worked-example session was open,
   * so the built-in examples this operation acts on do not exist to act on
   * (`_TUTORIAL_REQUIRED_MESSAGE` / `tutorial_scope_required` in
   * `apps/api/isaac_api/routes.py`).
   *
   * THIS COPY EXISTS BECAUSE THE SCREEN WAS CALLING A HEALTHY BACKEND DEAD.
   * `LoadMaterials.startDemo` recognised only `demo_target_drifted`, so this refusal
   * fell through to the error state and rendered "Backend Not Running" about a
   * backend that had answered correctly and instantly.
   *
   * THREE THINGS IT MUST NOT SAY, each because the alternative would be false: it
   * must not name a backend failure (there was none), it must not suggest anything
   * was written (the server's own message ends "Nothing was written."), and it must
   * not restate the server's API-facing remedy — a reader is not going to send an
   * HTTP header, so the remedy names the product control that opens a session.
   */
  demoScopeRequiredTitle: 'Example not run — no worked example is open',
  demoScopeRequiredBody:
    'The built-in example records exist only inside a worked example of their own, and none is ' +
    'open right now — so there was nothing here for this to run. Nothing was written and nothing ' +
    'changed.',
  demoScopeRequiredRemedy:
    'Opening the guided walkthrough opens a worked example, and this control works inside one. ' +
    'It lives in Settings & API → Help & Tutorial.',
  actionGoToHelpAndTutorial: 'Go to Help & Tutorial',
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

  /*
   * THE EMPTY STATE'S OWN PRIMARY, and it needed a THIRD name rather than either of
   * the two that already exist, because both were already spoken for on surfaces a
   * reader can reach.
   *
   * Not `actionReplayTutorial`: that is the Settings control, and
   * `tutorial-session-lifecycle.test.tsx` pins its ABSENCE from My Experiments so the
   * name identifies exactly one control in the app. Not `actionStartTutorial`: that
   * belongs to the first-run offer card, and two controls sharing a name on one screen
   * is the same collision one step smaller.
   *
   * It is a verb that describes what the button DOES. The control it replaces was
   * `actionGoToHelpAndTutorial`, which named navigation because navigation was all it
   * did; this one starts a session, so naming it after a destination would repeat, in
   * the other direction, the mismatch that removed its predecessor.
   *
   * The supporting line is NOT new copy. It is the last two sentences of
   * `tutorialOfferBody` verbatim, and it is quoted rather than paraphrased on purpose:
   * that wording was audited into its current form (see the comment above
   * `tutorialOfferTitle`), and a fresh paraphrase on a second surface is exactly how
   * the earlier false claims got in. Note what it does NOT say, and must not grow into
   * saying: that the ordinary workspace is empty. It is a statement about this
   * button's reach — `_materialise_seed`, `reset_to_canonical_seed` and
   * `ensure_tutorial_seeded` all refuse a `None` session id — not about what exists.
   *
   * "VERBATIM" IS NOW ENFORCED, AND SO IS THE COPY ITSELF. Both were claims resting on
   * a comment: `tutorial-flow.test.tsx`'s honesty ratchet queried `section.tutorial-offer`
   * only, so this string could have been replaced with the retired false absolute
   * ("It only reads — it answers nothing and changes nothing") and a wrong record count
   * with every test still green — on the surface that this same slice makes the ONLY one
   * a reader on an empty workspace ever sees. Two pins close it: the ratchet now runs the
   * identical positive and negative matchers over the rendered EMPTY state, and
   * `tutorialOfferBody.endsWith(launchGuidedDemoBody)` is asserted, so a change to either
   * string that breaks the quotation fails rather than drifts.
   */
  /*
   * CREATE EXPERIMENT — the first record-creation control this product has had.
   *
   * The verb is the same one the whole flow uses, start to finish: the button says
   * "Create Experiment", the form's submit says "Create Experiment", and the screen
   * it lands on is the record it created. An action keeps its name through the flow.
   *
   * WHAT THE COPY MUST NOT DO. It must not describe what the record CONTAINS,
   * because it contains nothing — a title and a set of open questions. "Start a new
   * record and fill it in" would promise a filling-in surface for fields that have
   * no capture form in this build. `createExperimentHint` therefore says what
   * genuinely happens next: the record opens with its questions already listed.
   */
  actionCreateExperiment: 'Create Experiment',
  createExperimentHint:
    'Starts an empty record with the questions ISAAC needs already listed, and opens it.',

  /** The form's own heading, distinct from the button that opens it, so a screen
   *  reader announcing the expanded region is not told "Create Experiment" twice. */
  createExperimentFormTitle: 'Name your experiment',
  createExperimentTitleLabel: 'Experiment title',
  createExperimentDescriptionLabel: 'What is it? (optional)',
  /*
   * The one place a create form is allowed to be opinionated: it tells the reader
   * what this box is NOT for. Without it, "What is it?" invites exactly the
   * unsourced scientific assertion the no-guessing contract exists to keep out of
   * a record — someone types "Cu K-edge, 8979 eV" and reasonably expects those to
   * become fields. They do not; this text is stored as the record's source
   * description and is never parsed.
   */
  createExperimentDescriptionHint:
    'A note for you. It is stored with the record and is never read as a scientific value.',
  createExperimentSubmit: 'Create Experiment',
  createExperimentCancel: 'Cancel',
  /** Shown when the title is empty. States the fix, not the failure. */
  createExperimentTitleRequired: 'Give the experiment a title to create it.',

  /*
   * MY EXPERIMENTS, EMPTY — an invitation to act, not a report of absence.
   *
   * THE SENTENCE THIS REPLACES WAS "This deployment cannot yet create or import a
   * record, so nothing has been added." It was true when it was written and it is
   * now FALSE: `POST /api/experiments` exists. It is not softened or reworded, it
   * is gone, and nothing that implies it may come back.
   *
   * The title asks for the first action rather than naming the empty set. "No
   * experiments yet" describes the reader's screen back to them; a person who has
   * just arrived can see that it is empty.
   */
  emptyExperimentsTitle: 'Start your first experiment',
  emptyExperimentsBody:
    'Create your first experiment, validate an existing record, or explore ISAAC with the ' +
    'guided demo.',

  actionOpenValidator: 'Open Validator',
  openValidatorHint:
    'Check a record file you already have against the official ISAAC schema.',

  /*
   * WHERE A NEW EXPERIMENT GOES — one short line, and it is DERIVED, never assumed.
   *
   * Both sentences exist because both are true somewhere. The deployed pod stores
   * experiments in this application's own PostgreSQL database; a developer
   * checkout and CI store them in a workspace directory, and on the pod that
   * directory is an `emptyDir` a restart empties. Shipping either sentence alone
   * would put a false promise on half the deployments.
   *
   * THERE IS DELIBERATELY NO THIRD SENTENCE for the unknown case. When
   * `/api/health` has not been read, or predates the `experiment_storage` block,
   * `ExperimentsHome` renders NEITHER — because the only honest thing to say about
   * durability you have not established is nothing. A "storage is being
   * determined…" line would be a claim about the app's state dressed as a claim
   * about the reader's data.
   *
   * "cleared when the server restarts" rather than "when the pod restarts":
   * `emptyDir`, pods and deployments are our vocabulary, not the reader's. The
   * consequence is the same and the consequence is the part they need.
   */
  storageDurable:
    'Experiments you create are saved in this deployment’s database and stay here across ' +
    'restarts.',
  storageEphemeral:
    'Experiments you create live in this server’s workspace and are cleared when the server ' +
    'restarts.',
  /*
   * THE THIRD SENTENCE, AND IT IS NOT A REASSURING ONE ON PURPOSE.
   *
   * `unavailable` means a database IS configured for this deployment and
   * experiments are not going into it. The temptation is to soften that into
   * "storage is being set up" or to drop it and render nothing. Both would be
   * worse than saying it: the reader is about to press a button that will fail,
   * and the honest thing is to tell them before they press it rather than after.
   *
   * IT DESCRIBES THE CONSEQUENCE ACCURATELY, which took some care. Creating does
   * not silently produce a temporary record — `POST /api/experiments` returns 503
   * and writes nothing at all — so "may be lost" would be wrong in the direction
   * that matters. "Will not work until it does" is what actually happens.
   *
   * The two sentences above deliberately never mention this state, and the note
   * on `unknown` above still holds for `unknown` — that one renders nothing,
   * because there the app has established NOTHING. Here it has established
   * something bad, which is a different thing from knowing nothing.
   */
  storageUnavailable:
    'This deployment saves experiments in its own database, and that database is not ' +
    'answering. Creating an experiment will not work until it does.',

  actionLaunchGuidedDemo: 'Launch Guided Demo',
  launchGuidedDemoBody:
    'Starting it opens a worked example of its own — a temporary workspace holding five example ' +
    'records, discarded when the tour ends. No record of yours is created, changed, or removed.',

  /*
   * The reader walked away from the screen the current step describes.
   *
   * THIS EXISTS BECAUSE WALKING AWAY IS NOW ALLOWED. The overlay used to navigate
   * back to the step's own path on every render, so this state was unreachable — and
   * that pin is what made the worked-example bar's own controls dead. With the pin
   * gone, the step needs something true to say, and the step catalog's `unavailable`
   * copy is not it: those sentences explain a missing RECORD ("nothing was
   * un-answered or reset to create one"), which is a cause that has not occurred
   * here.
   *
   * It states only what is known — the control is on another screen and nothing was
   * changed — and names the two controls that are already in the mark, rather than
   * promising a "take me there" button that does not exist.
   */
  tutorialStepOffSurface:
    'this step points at a control on another screen, and you have moved away from it. Nothing ' +
    'was changed. Next and Back carry on through the walkthrough, and each step takes you to the ' +
    'screen it describes.',

  /*
   * The persistent worked-example bar (D2). It exists ONLY while a worked-example
   * session is open, and it is the one home of the two controls that act on the
   * built-in examples — both of which now REQUIRE the session header and refuse
   * without it (`POST /api/demo/run`, `POST /api/demo/reset`).
   *
   * THE BODY MADE THREE CLAIMS WHILE THIS COMMENT ENUMERATED TWO, AND THE
   * UNENUMERATED THIRD WAS THE FALSE ONE. It read "they are not visible in My
   * Experiments", which is not true and, because `AppShell` mounts this bar on every
   * surface, was rendered directly above the five rows it denied. Entering a session
   * changes the SCOPE every request carries, not the screen: `api.ts` attaches
   * `X-Isaac-Tutorial-Session` in its single `request()` choke point, `ExperimentsHome`
   * keys its fetch on the scope, and `e2e/specs/tutorial.spec.ts` asserts `.exp-row`
   * count 5 on `/experiments` immediately after a session opens (and 0 before).
   *
   * The three facts the body now states, each checked against code rather than
   * promised:
   *
   *  1. THE RECORDS ARE THIS SESSION'S OWN COPY. `_materialise_seed`
   *     (`apps/api/isaac_api/workspace.py:811`) takes a REQUIRED `session_id`, REFUSES
   *     `None` with `InvalidTutorialSession`, and writes under
   *     `workspace_root()/_tutorial/<id>/`.
   *
   *     THE REFUSAL IS NOT A RESTATEMENT OF THE REQUIREMENT, and this comment used to
   *     cite only the requirement. "Requires a `session_id`" establishes what a caller
   *     must pass, not what the function does with `None`: `scope_root(None)` returns
   *     `workspace_root()` silently, and an explicit `session_id=None` was measured
   *     writing a canonical record into the ordinary root. Note that this fact is about
   *     where THESE records live, which is why it survived that error — nothing here
   *     ever claimed the ordinary workspace was empty. The chip's ordinary-scope clause
   *     did, twice; see `components/TopBar.tsx`'s `ORDINARY_ONLY`.
   *  2. NO REQUEST MADE OUTSIDE THE SESSION REACHES THEM. A scope is a directory
   *     namespace, not a filter: `_experiment_dirs` enumerates one root and skips
   *     `_`-prefixed entries unconditionally (`:845-866`), so exclusion is
   *     structural. This is also why the bar says plainly that the app's record screens
   *     — My Experiments included — are showing this walkthrough while it is open.
   *
   *     "EVERY SCREEN THAT SHOWS RECORDS", not "every screen in the app", which is what
   *     this said and which over-claimed. `AppShell` mounts the bar everywhere, but
   *     Concepts, Schema Reference, Project Memory, the API docs and the Governance
   *     policy tab show neither scope's records, so "is showing this walkthrough rather
   *     than the ordinary workspace" is not a true description of them.
   *  3. THEY ARE DISCARDED WHEN THE WALKTHROUGH ENDS. Every exit path drops the
   *     scope and the pointer synchronously (`leaveTutorialScopeLocally`), so the
   *     reader's access ends unconditionally. The server-side DELETE is best effort
   *     (`disposeTutorialSession` swallows a failure) with `sweep_stale_tutorial_sessions`
   *     as the fallback — which is why this comment no longer claims "every exit path
   *     DELETEs", and why the function is `disposeTutorialSession`, not the
   *     `releaseTutorialSession` five sites used to cite and which never existed.
   */
  tutorialSessionBarTitle: 'Worked Example',
  tutorialSessionBarBody:
    'These five example records belong to this walkthrough only: they are its own copy, in a ' +
    'temporary workspace of its own, and no request made outside it reaches them. While this bar ' +
    'is showing, every screen that shows records — My Experiments included — is showing this ' +
    'walkthrough rather than the ordinary workspace. They are discarded when the walkthrough ends.',
  tutorialSessionBarRegion: 'Worked example session',

  /*
   * The three ways a worked-example session can fail the reader, stated to them.
   *
   * These exist because `tutorialController` set `sessionError` and NOTHING rendered
   * it — the field's own comment claimed it was "surfaced to the reader as a truthful
   * message; never silently swallowed" while the only reader-visible consequence of a
   * failed start was that nothing happened when they pressed the button.
   *
   * NO SENTENCE CLAIMS MORE THAN IS KNOWN, and the create case is the careful one.
   * A failed `POST /api/tutorial/sessions` does NOT establish that no session was
   * created: the request may have succeeded and its response been lost, leaving an
   * orphan the backend's TTL sweep reclaims. So the copy states what IS known — the
   * walkthrough did not start, and the ordinary workspace was not touched — and does
   * not assert that nothing was created anywhere.
   *
   * THE EXPIRED SENTENCE IS THE STRONGEST OF THE THREE, AND IT IS NOW EARNED. It
   * asserts the server no longer holds the workspace, which for a while was said on
   * the strength of a bare `catch` — a network blip, a 401 at the authenticating edge
   * and a 500 all produced it. It is now reached only when the backend has ANSWERED
   * `404` with `{"error": "tutorial_session_not_found"}` (see
   * `api.tutorialSessionState` and `tutorialController.resumeTutorialSession`), which
   * is the one observation that supports it.
   *
   * `resume_failed` is what everything else degrades into, and it is deliberately the
   * emptiest of the three. It names no cause, because from the client a blip, an edge
   * redirect and a 500 are indistinguishable; it does not say the session is gone,
   * because that is unknown; it does not say it is still there either. What it CAN say
   * is checkable: one GET was issued and nothing was written, the pointer is kept
   * (`resumeTutorialSession` does not clear `sessionStorage` on this branch), and
   * `api.ts` re-enters the persisted scope at module load — so a reload really is a
   * retry rather than advice that happens to sound helpful.
   */
  tutorialSessionCreateFailedTitle: 'The worked example could not be opened',
  tutorialSessionCreateFailedBody:
    'The walkthrough did not start, and nothing in My Experiments was changed. You can try ' +
    'again from Settings & API → Help & Tutorial.',
  tutorialSessionExpiredTitle: 'The worked example has expired',
  tutorialSessionExpiredBody:
    'The temporary workspace this walkthrough was using no longer exists, so its five example ' +
    'records are gone and the walkthrough has closed. Nothing in My Experiments was changed. ' +
    'You can start the walkthrough again from Settings & API → Help & Tutorial.',
  tutorialSessionResumeFailedTitle: 'The worked example could not be resumed',
  tutorialSessionResumeFailedBody:
    'Checking the walkthrough you had open did not succeed, so it has not been resumed. Whether ' +
    'it is still there is not something this screen can tell you. Nothing was written and ' +
    'nothing in My Experiments was changed. Reloading the page tries again, and you can start a ' +
    'new walkthrough from Settings & API → Help & Tutorial.',
  actionDismissTutorialNotice: 'Dismiss',

  /*
   * The first-run offer (`components/TutorialPromotion.tsx`).
   *
   * "It only reads — it answers nothing and changes nothing" WAS FALSE, and it sat
   * next to the button that made it false. `startTutorial` POSTs
   * `/api/tutorial/sessions`, and `create_tutorial_session` mints a new directory and
   * calls `ensure_tutorial_seeded`, which materialises five records into it. That is a
   * write. `screens/settings/HelpAndTutorial.tsx` had already identified this exact
   * defect and corrected its own copy while the offer — the surface almost every
   * reader meets first — went on making the claim.
   *
   * The reassurance is kept rather than deleted, and it is the true one: what is
   * protected is the READER's work, not the absence of a write. The precise form is
   * "no record of yours is created, changed, or removed", which is exactly what the
   * code enforces — `_materialise_seed`, `reset_to_canonical_seed` and
   * `ensure_tutorial_seeded` all REFUSE a `None` session id (`InvalidTutorialSession`),
   * so nothing this button does can address a record outside the session it opens.
   *
   * The citation used to be "requires a `session_id` and has no normal-scope form",
   * which is weaker than it reads: a required parameter says what a caller must pass,
   * and `scope_root(None)` returned `workspace_root()` without complaint, so an
   * explicit `None` reached the ordinary root. Note what this sentence does NOT claim,
   * and must not grow into claiming: that the ordinary workspace is empty. It says the
   * reader's records are untouched, which is a statement about this button's reach.
   */
  tutorialOfferTitle: 'Take the Guided Walkthrough',
  tutorialOfferBody:
    'A short guided tour of this app, pointing at the real controls on the real screens: what this ' +
    'list holds, how a record shows what it still needs, how evidence and confirmation work, and ' +
    'why export stays closed until a record earns it. Starting it opens a worked example of its ' +
    'own — a temporary workspace holding five example records, discarded when the tour ends. No ' +
    'record of yours is created, changed, or removed.',

  /*
   * The mandated completion copy. Sentence case is deliberate here: it is an
   * outcome statement rather than the name of a surface, and it matches
   * `demoDriftedTitle` above, the other outcome statement in this file.
   *
   * "Nothing you have looked at was changed" WAS FALSE at the moment it rendered.
   * `finishTutorial` drops the scope and the pointer and then DELETEs the session, so
   * by the time this panel is on screen the five records the reader spent the
   * walkthrough looking at are unreachable to them — destroyed, not unchanged. The
   * expired-session copy below already tells a reader plainly that its records are
   * gone; the SUCCESS path has to meet the same standard, or the app is honest only
   * when something goes wrong.
   *
   * "gone" rather than "deleted" is deliberate and is the weakest true word: the
   * reader's access ends unconditionally (`leaveTutorialScopeLocally` is synchronous),
   * whereas the server-side DELETE is best effort with the TTL sweep as its fallback.
   * And "start it again" replaces "reopen this walkthrough", because a replay mints a
   * NEW session at step one; the one just finished cannot be reopened.
   */
  tutorialCompleteTitle: 'Tutorial complete',
  tutorialCompleteBody:
    'That is the whole workflow. The worked example you were walking through is gone now, and so ' +
    'is anything you answered inside it — it was a temporary copy of the five examples, kept apart ' +
    'from your own work, and no record of yours was changed. You can start it again from ' +
    'Settings & API → Help & Tutorial at any time.',

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

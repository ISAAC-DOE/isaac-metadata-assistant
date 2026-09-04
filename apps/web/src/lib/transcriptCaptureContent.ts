/*
 * The transcript-capture panel's authored copy, in one place.
 *
 * IT FOLLOWS `mcpConnectContent.ts`'S RULE AND EXTENDS IT WITH ONE MORE. That
 * module's rule: never print a status, an address, or a date that nothing
 * measured. The addition here: **every claim about what the deployment can do
 * comes from the server**, not from this file. So there is no `statusLabel` and
 * no "not configured" string below — the panel renders
 * `GET /api/providers/capabilities` and the refusal body the transcription
 * operation returns, both of which are produced by the process that would
 * actually do the work. A string here saying "not configured" would be a claim
 * about a deployment this bundle has never met.
 *
 * WHAT IS IN HERE IS THEREFORE ONLY WHAT THIS CLIENT ITSELF KNOWS: how to speak
 * to the reader, what this browser does with audio, and what the controls mean.
 *
 * PR-D (2026-09-03): the panel became a state-driven interface — see
 * `TranscriptCapturePanel.tsx`'s own header for the nine-state table this copy
 * now serves. Renamed/added strings are marked below; nothing removed a claim
 * that used to be true, and every removed string had no remaining caller (dead
 * copy is the same defect as dead code — CLAUDE.md's own rule for both).
 */

/**
 * The first-use guidance sentence, verbatim.
 *
 * It is a named constant rather than inline JSX because a test asserts it
 * exactly: the wording was specified, and a well-meaning rephrase would quietly
 * change instructions a scientist was given.
 */
export const CAPTURE_GUIDANCE_SENTENCE =
  'Speak naturally, but identify the run and measurement conditions clearly.';

/**
 * The worked example shown beside the sentence.
 *
 * IT IS OBVIOUSLY SYNTHETIC AND IT IS NOT A RECORD. The values are illustrative
 * and the example says which parts the reader reads back — a worked example that
 * looked like real measurements would be indistinguishable from one, printed
 * next to a control that writes to a record.
 */
export const CAPTURE_GUIDANCE_EXAMPLE = {
  spoken:
    'Notes for run 2. Temperature was 300 K. Atmosphere was: dry nitrogen. ' +
    'The cryostat rattled about halfway through, worth checking.',
  reads: [
    'run 2 — checked against the run you selected, never used to pick one',
    'Temperature was 300 K — proposed for the temperature field, in kelvin',
    'Atmosphere was: dry nitrogen — proposed exactly as written',
  ],
  keeps: 'The cryostat rattled about halfway through, worth checking.',
} as const;

export const CAPTURE_COPY = {
  // Register 1 (Title Case): section heading.
  panelHeading: 'Transcript Capture',
  /*
   * ONE ENTRY ACTION, TITLE CASE, NAMING THE TASK RATHER THAN THE MECHANISM.
   * Replaces `start`/`close` ('Start a capture' / 'Close capture'), which named
   * the UI gesture ("a capture") rather than what pressing it does. This is the
   * one control a reader meets before opening the panel at all, so it carries
   * the panel's whole purpose in three words.
   */
  entryOpen: 'Capture Experiment Notes',
  entryClose: 'Close Capture',

  /*
   * SHORTENED, AND THE DETAIL IT DROPPED MOVED INTO THE GUIDANCE DISCLOSURE
   * BELOW RATHER THAN DISAPPEARING. The previous version of this string carried
   * the full transcription-needs-a-provider explanation as PERMANENT body copy,
   * visible even while the panel is collapsed — the opposite of progressive
   * disclosure. The seam's own status line (rendered from
   * `GET /api/providers/capabilities`) already states that fact truthfully and
   * specifically once the panel is open; restating it here in general terms was
   * redundant with a more accurate copy of itself one section down.
   *
   * C1 — CORRECTED, INDEPENDENT REVIEW OF PR-D. This sentence renders in the
   * COLLAPSED header (`TranscriptCapturePanel.tsx`, outside the `open` body),
   * so it is read BEFORE any seam status or provider qualification is visible
   * anywhere on screen. A version that said "...or record notes..." presented
   * recording as an equally-finished path to a proposal — it is not: finalize
   * posts TEXT only, and turning a recording into that text needs a
   * transcription provider this build never ships configured
   * (`ai-integration-decision-packet.md` §9 / `CLAUDE.md` §15). The collapsed
   * header therefore names only the path that always works — typing or
   * pasting — and says nothing about recording at all; the open body's Voice
   * Capture section, with its own seam status, is the only place recording is
   * introduced.
   */
  panelIntro:
    'Type or paste notes about a run, then finalize them to store a proposal ' +
    'for each value it can store. Nothing here writes a value directly.',

  guidanceHeading: 'Before you start',
  guidanceDismiss: 'Got it',
  guidanceReopen: 'Show capture guidance',
  guidanceStorageNote:
    'This browser remembers that you have seen this. It is not stored on the ' +
    'server and does not follow you to another device.',
  /*
   * THE DETAIL `panelIntro` USED TO CARRY, MOVED RATHER THAN DELETED. This is
   * the "one concise contextual help disclosure" the interface now uses instead
   * of permanent body text — closed by default, remembered per browser, exactly
   * as the guidance sentence above it already was.
   */
  /*
   * I7 — CORRECTED, INDEPENDENT REVIEW OF PR-D. "for each value it recognises"
   * overstated the server's own guarantee: `_MAX_PROPOSALS_PER_RECORD` and the
   * per-record byte ceiling both mean a value the extractor DID recognise can
   * still be disclosed as `unproposable` rather than stored — see
   * `TranscriptCapturePanel`'s own `summaryUnproposable`/`unproposableHeading`,
   * which exist precisely because "recognised" and "stored" are not the same
   * claim. This sentence now makes the claim the code can actually keep.
   */
  guidanceMechanism:
    'Recording keeps audio in this tab only — it is never uploaded. Turning a ' +
    'recording into text needs a transcription provider; this deployment reports ' +
    'whether one is configured next to the recording controls, before you rely on ' +
    'it. Typing or pasting always works, with no provider needed. Finalizing reads ' +
    'the text once and stores a proposal for each value it can store; values it ' +
    'cannot store are listed with the reason — never a value written directly to ' +
    'the record.',

  voiceHeading: 'Voice Capture',
  voiceSeamUnreported:
    'Transcription: not reported. This deployment has not told the page whether a ' +
    'transcription provider is configured — the capability report has not been read, ' +
    'or does not mention this seam — so treat turning a recording into text as ' +
    'unavailable until it does. Recording still keeps the audio in this tab, and ' +
    'nothing is sent anywhere.',
  voiceUnsupported:
    'This browser does not offer audio recording, so the voice controls are not ' +
    'shown. Typing or pasting a transcript below does the same work.',
  voiceAudioHandling:
    'Audio stays in this tab’s memory. It is never uploaded, never written to ' +
    'disk, and is discarded when you clear it, leave this record, or reload the ' +
    'page. This application declares no upload endpoint for it to reach.',

  // -- primary/secondary controls, per voice state --------------------------
  voiceRecord: 'Start Recording',
  voiceRequesting: 'Requesting…',
  voiceStop: 'Stop Recording',
  voiceDiscard: 'Discard Audio',
  voiceTranscribe: 'Request a Transcript',
  /** The `held`/`permission-denied` primary: focuses the textarea. No request. */
  voiceTypeWhatWasSaid: 'Type What Was Said',
  /** The `permission-denied` secondary: re-invokes `startRecording`. */
  voiceTryAgain: 'Try Recording Again',

  // -- live-region text, per voice state -------------------------------------
  voiceRecordingLive: 'Recording. Audio is being held in this tab.',
  voiceIdleLive: 'Not recording.',
  /** NEW — the `requesting-permission` state's own announcement. */
  voiceRequestingLive: 'Requesting microphone access…',
  voiceHeldLive: 'Recording stopped. Audio is held in this tab and has not been sent.',
  voiceDiscardedLive: 'Audio discarded.',
  /*
   * I8 — FOUR REASONS `getUserMedia` CAN FAIL, EACH ITS OWN SENTENCE, INDEPENDENT
   * REVIEW OF PR-D. The panel used to collapse every failure into one denial
   * sentence — true of a real refusal, false (or at best uninformative) of "no
   * microphone exists" and "something else is using it", which are different
   * facts calling for different reader reactions. Each doubles as the PERSISTENT
   * `permission-denied` notice AND the live announcement fired once on entering
   * that state — the two are the same sentence by design, per the state table
   * this panel's header cites. The last is the FAIL-CLOSED default: a browser can
   * throw a `DOMException` this list does not name, and that case must still say
   * something true rather than guess a specific cause.
   */
  voicePermissionRefused:
    'This browser did not grant microphone access, so nothing was recorded. ' +
    'Typing or pasting a transcript below does the same work.',
  voiceNoMicrophone:
    'No microphone was found, so nothing was recorded. Typing or pasting a ' +
    'transcript below does the same work.',
  voiceMicrophoneBusy:
    'The microphone is in use elsewhere, so nothing was recorded. Typing or ' +
    'pasting a transcript below does the same work.',
  voiceStartFailed:
    'Recording could not be started, so nothing was recorded. Typing or pasting ' +
    'a transcript below does the same work.',
  voiceAfterRefusal:
    'The audio is still held in this tab and was not sent anywhere. Type or ' +
    'paste what was said, and finalize that instead.',

  transcriptLabel: 'Transcript',
  transcriptHint:
    'Finalizing stores this text with the record and reads it. Editing it ' +
    'afterwards means finalizing again.',
  runLabel: 'Run These Notes Describe',
  runPlaceholder: 'Choose a run…',
  runHint:
    'Required before a run-scoped value can be proposed. It is never chosen for ' +
    'you, even when the record has exactly one run.',
  /*
   * "CREATE A RUN" IS NOW THE RUN SELECTOR'S OWN EMPTY STATE, NOT A PERMANENT
   * BUTTON BESIDE IT. Capturing notes never strictly requires a run — a
   * record-scoped value can still be proposed — so this is a placement decision
   * offered exactly when it is the honest next step, per `ia-brief.md` §6.
   */
  runCreate: 'Create a Run',
  runEmptyPrefix: 'This record has no runs yet.',
  runEmptySuffix: ', or capture notes without one.',
  /** Said when a run IS selected — states what proposals from THIS capture will target. */
  runTargetsRun: (label: string) => `Proposals from this transcript will target ${label}.`,
  /** Said when NO run is selected. Never implies a run is required. */
  runTargetsNone:
    'No run is selected. Proposals from this transcript will target the record ' +
    'itself — only run-scoped values need a run chosen first.',

  finalize: 'Finalize and Read',
  finalizeHint:
    'Reading happens only when you press this. Text you are still typing is ' +
    'never read and never stored.',
  /** NEW — the `processing` state's own announcement, distinct from a generic busy. */
  processingLive: 'Reading transcript…',

  // -- the `proposals-ready` summary card ------------------------------------
  summaryHeading: 'What This Reading Stored',
  candidatesEmpty:
    'Nothing was proposed from this transcript. Every word of it was stored ' +
    'with the record as notes.',
  /** `n` proposals, `m` notes — the two counts the state table's own row names. */
  summaryStored: (proposals: number, notes: number) =>
    `${proposals} ${proposals === 1 ? 'proposal' : 'proposals'}, ${notes} ` +
    `${notes === 1 ? 'note' : 'notes'} stored with this record.`,
  summaryUnproposable: (count: number) =>
    `${count} ${count === 1 ? 'value' : 'values'} read from this transcript could ` +
    `not be stored as ${count === 1 ? 'a proposal' : 'proposals'}; the words behind ` +
    `${count === 1 ? 'it are' : 'them are'} still stored as ${count === 1 ? 'a note' : 'notes'}.`,
  unproposableHeading: 'Not Stored As Proposals',
  reviewProposals: (n: number) => `Review ${n} ${n === 1 ? 'Proposal' : 'Proposals'}`,
  captureAnother: 'Capture Another Note',
  /** NEW — generic retry, re-invokes whichever action last failed. */
  tryAgain: 'Try Again',

  clarificationsHeading: 'Questions this reader will not answer for you',
  abstentionsHeading: 'Recognised and deliberately not proposed',
  reviewHeading: 'Contradictions to resolve',
  notesHeading: 'Stored with this record',
  notesNote:
    'Every segment of the finalized transcript is stored, including the ones ' +
    'that produced a proposal. Rejecting a proposal therefore never loses the ' +
    'words behind it.',
  retentionHeading: 'Retention',
} as const;

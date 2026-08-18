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
  panelHeading: 'Transcript capture',
  start: 'Start a capture',
  close: 'Close capture',
  panelIntro:
    'Type, paste, or dictate notes about a run, then finalize them. Nothing is ' +
    'read while you are still writing, and no value is written until you accept ' +
    'one.',

  guidanceHeading: 'Before you start',
  guidanceDismiss: 'Got it',
  guidanceReopen: 'Show capture guidance',
  guidanceStorageNote:
    'This browser remembers that you have seen this. It is not stored on the ' +
    'server and does not follow you to another device.',

  voiceHeading: 'Voice capture',
  voiceUnsupported:
    'This browser does not offer audio recording, so the voice controls are not ' +
    'shown. Typing or pasting a transcript below does the same work.',
  voiceAudioHandling:
    'Audio stays in this tab’s memory. It is never uploaded, never written to ' +
    'disk, and is discarded when you clear it, leave this record, or reload the ' +
    'page. This application declares no upload endpoint for it to reach.',
  voiceRecord: 'Start recording',
  voiceStop: 'Stop recording',
  voiceDiscard: 'Discard audio',
  voiceTranscribe: 'Request a transcript',
  voiceRecordingLive: 'Recording. Audio is being held in this tab.',
  voiceIdleLive: 'Not recording.',
  voiceHeldLive: 'Recording stopped. Audio is held in this tab and has not been sent.',
  voiceDiscardedLive: 'Audio discarded.',
  voicePermissionRefused:
    'This browser did not grant microphone access, so nothing was recorded. ' +
    'Typing or pasting a transcript below does the same work.',
  voiceAfterRefusal:
    'The audio is still held in this tab and was not sent anywhere. Type or ' +
    'paste what was said, and finalize that instead.',

  transcriptLabel: 'Transcript',
  transcriptHint:
    'Finalizing stores this text with the record and reads it. Editing it ' +
    'afterwards means finalizing again.',
  runLabel: 'Run these notes describe',
  runPlaceholder: 'Choose a run…',
  runHint:
    'Required before any value can be proposed. It is never chosen for you, ' +
    'even when the record has exactly one run.',
  runCreate: 'Create a run',
  finalize: 'Finalize and read',
  finalizeHint:
    'Reading happens only when you press this. Text you are still typing is ' +
    'never read and never stored.',

  candidatesHeading: 'Proposed values',
  candidatesEmpty:
    'Nothing was proposed from this transcript. Every word of it was stored ' +
    'with the record as notes.',
  candidateNotAValue:
    'A proposal, not a value. Nothing is written to the record until you accept ' +
    'it, and accepting it records your confirmation.',
  accept: 'Accept',
  reject: 'Reject',
  edit: 'Edit before accepting',
  undo: 'Undo',
  accepted: 'Accepted and written to the run.',
  rejected: 'Rejected. The words it came from are still stored as a note.',
  undone: 'Undone. The run holds the value it held before.',

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

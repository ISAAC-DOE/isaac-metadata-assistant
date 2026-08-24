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
  /*
   * IT USED TO OFFER "dictate" AS AN EQUAL THIRD OPTION, and it is the one string
   * in this module that broke the module's own rule at the top of the file.
   *
   * The old sentence read: "Type, paste, or dictate notes about a run, then
   * finalize them. Nothing is read while you are still writing, and no value is
   * written until you accept one." It sits in the panel HEADER
   * (`TranscriptCapturePanel.tsx:500`), which renders BEFORE the panel is opened —
   * so the promise of dictation was on screen while the seam status that qualifies
   * it, and the refusal body that explains it, were both still inside the collapsed
   * body.
   *
   * AND DICTATION CANNOT WORK IN A SHIPPED DEPLOYMENT. `POST /api/transcription`
   * answers `501` with `reason: no_provider_configured`, and that is not a
   * misconfiguration to be corrected: `providers/config.py::_selected` resolves
   * unset, empty and unrecognised values all to `unconfigured`, while
   * `validate_provider_config_or_raise` REFUSES to boot an app whose seam is set to
   * `deterministic-fake` (DECISION D6). So the only implementation a running
   * application can hold is the unconfigured one. `ai-integration-decision-packet.md`
   * §9 — "build nothing that implies any of it exists" — binds per `CLAUDE.md` §15,
   * and an unqualified "dictate" implied exactly that.
   *
   * WHAT IS SAID INSTEAD, and why it does not break the rule it is fixing: typing
   * and pasting are named as the working path because this client does that work
   * itself; recording is named because this client does that too (`MediaRecorder`,
   * audio held in the tab); and turning audio into text is named as needing a
   * provider WITHOUT asserting whether this deployment has one. That last part is
   * still the server's to say, and the panel still says it from
   * `GET /api/providers/capabilities`. The recorder is deliberately NOT gated or
   * removed — a provider-ready recording UX may exist, provided the copy around it
   * is true.
   */
  panelIntro:
    'Type or paste notes about a run, then finalize them. You can also record ' +
    'audio here, but turning a recording into text needs a transcription ' +
    'provider — the panel reports what this deployment has before you rely on ' +
    'it. Nothing is read while you are still writing, and no value is written ' +
    'until you accept one.',

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

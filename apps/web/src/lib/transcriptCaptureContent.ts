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
  /*
   * THE STATE WORD ON THE RECORDING/HELD BAR — 2026-09-10.
   *
   * `voiceRecordingBadge` IS EXACTLY `'Recording'` AND MUST STAY SO. The bar
   * renders `<state> · <m:ss>` inside `.capture-elapsed`, and
   * `e2e/mutation/capture-microphone.spec.ts` asserts that element's text is
   * `Recording · 0:01` (`:901`) and matches `/Recording · (?!0:00)\d+:\d\d/`
   * (`:774`), and parses `/(\d+):(\d\d)\s*$/` off its `innerText` (`:510`).
   * Those three are the reason the separator is a literal ` · ` and the time is
   * LAST. Changing this word, the separator, or the order breaks a real-Chromium
   * spec that this slice was fenced out of editing.
   *
   * `voiceHeldBadge` EXISTS BECAUSE `held` HAD NO VISIBLE STATE AT ALL. On Stop
   * the elapsed indicator disappeared and the ONLY statement that audio was
   * still held was the `sr-only` live region — so a screen-reader user was
   * better informed than a sighted one, which is the inversion this fixes.
   */
  voiceRecordingBadge: 'Recording',
  voiceHeldBadge: 'Held',
  /*
   * `voicePausedBadge` — THE FOURTH STATE WORD, added 2026-09-11.
   *
   * It is the ONLY signal on the bar that is fully independent of both colour
   * and shape, which is why it is a word and not a glyph. `Paused` must not be
   * a synonym of `Held`: `Held` means the microphone is CLOSED and a finished
   * clip is in the tab; `Paused` means the microphone is STILL OPEN and the
   * recorder will add to the same clip when it resumes. Those are different
   * facts about a device, and the panel says which one is true.
   *
   * It follows the same `<state> · <m:ss>` shape as the other two, so the
   * fenced real-Chromium spec's parse (`/(\d+):(\d\d)\s*$/`, `:510`) keeps
   * working in this state as well — it was never state-specific.
   */
  voicePausedBadge: 'Paused',
  /** The persistent, VISIBLE held statement. Says what the live region says. */
  voiceHeldPersistent:
    'This audio is held in this tab’s memory and has not been sent anywhere. ' +
    'Play it back below, type what was said, or discard it.',
  /*
   * THE VISIBLE `paused` STATEMENT — and the one thing about pausing that a
   * scientist is most likely to get wrong.
   *
   * `MediaRecorder.pause()` DOES NOT RELEASE THE MICROPHONE. The spec suspends
   * the recorder; the `MediaStream`'s tracks stay `live`, and in a browser that
   * shows a recording indicator that indicator STAYS ON. Somebody who pauses in
   * order to have a private conversation at the instrument would be wrong about
   * what this control did for them, and no other surface in this panel would
   * correct them. So the sentence names the release act explicitly: Stop is what
   * closes the device.
   *
   * It deliberately does NOT promise that the clip resumes "seamlessly" or
   * "without a gap" — the recorder concatenates what it captured, so the pause
   * is simply absent from the audio, and describing the join in any more detail
   * than that would be a claim about a container this code never inspects.
   */
  voicePausedPersistent:
    'Nothing is being captured while this says Paused. The microphone is still ' +
    'open — Stop Recording is what releases it. What was recorded before the ' +
    'pause is held in this tab and has not been sent anywhere; resuming adds to ' +
    'the same recording, and the paused time is not part of it.',
  /*
   * LOCAL PLAYBACK — added 2026-09-10, and the two things it deliberately does
   * NOT do are named here because both would falsify copy this panel ships.
   *
   * NO DOWNLOAD. Chrome's default `<audio controls>` overflow menu carries a
   * Download item; the element sets `controlsList="nodownload …"` to suppress
   * it, because `voiceAudioHandling` promises the audio is "never written to
   * disk" and a download would make that false.
   *
   * NO REMOTE PLAYBACK. `noremoteplayback` plus the `disableRemotePlayback`
   * property stop the browser offering to cast the clip to another device —
   * which would be audio leaving this tab by a route no HTTP assertion watches.
   */
  voicePlaybackLabel: 'Play back the audio held in this tab',
  /*
   * I-3 — SCOPED TO THE BUILD, NOT TO THE BROWSER. This read "the player
   * offers no download and no casting to another device", which is a claim
   * about what every engine DOES. `controlsList` and `disableRemotePlayback`
   * are Chromium features: Firefox supports neither, and an engine that
   * ignores them shows its own native download control, at which point the
   * sentence is simply false. This repository's browser tests run chromium
   * only, so nothing here could have caught that.
   *
   * "is configured to offer" is a claim about what THIS BUILD ASKS FOR, which
   * is true in every engine — the attributes are on the element whether or not
   * a UA honours them. Same correction shape as the three scoped-not-deleted
   * upload claims `CLAUDE.md` §11 records: narrow the claim to what is
   * verifiable, do not delete the reassurance.
   *
   * The FIRST half is unconditional and stays unqualified: no request is made
   * to play the audio, in any engine, because an object URL is a
   * same-document reference and nothing here fetches anything.
   */
  voicePlaybackNote:
    'Playback happens entirely in this tab: no request is made to play it, and ' +
    'this player is configured to offer no download and no casting to another device.',
  voiceSeamUnreported:
    'Transcription: not reported. This deployment has not told the page whether a ' +
    'transcription provider is configured — the capability report has not been read, ' +
    'or does not mention this seam — so treat turning a recording into text as ' +
    'unavailable until it does. Recording still keeps the audio in this tab, and ' +
    'nothing is sent anywhere.',
  voiceUnsupported:
    'This browser does not offer audio recording, so the voice controls are not ' +
    'shown. Typing or pasting a transcript below does the same work.',
  /*
   * R1b — CORRECTED, INDEPENDENT REVIEW, TWICE. This used to end "This
   * application declares no upload endpoint for it to reach," which is
   * false: `POST /api/uploads` IS declared (`apps/api/isaac_api/routes.py`).
   *
   * The FIRST correction replaced it with "...so there is nowhere for it to
   * be sent even by mistake" — still false, in a subtler way an independent
   * review caught: that is an application-wide existential negative inferred
   * from a fact about ONE route. Refusing `/uploads` establishes nothing
   * about `/api/transcription`, whose `audio_ref` field is a free `str` with
   * no length or content constraint (`routes.py:14671`) — nothing but
   * `isinstance` stops a future bug in this panel from putting a data URL
   * there. "Even by mistake" is exactly a claim about what a mistake could
   * do, and this build does not support it.
   *
   * This version instead states the ONE fact that genuinely is
   * application-wide, and that `/api/transcription`'s own description
   * already asserts about itself: "this application declares no multipart
   * form anywhere" (`routes.py:14620`). Paired with the one upload route's
   * unconditional refusal, that is the strongest true claim available: no
   * multipart body exists anywhere in this build, and the one route that
   * might otherwise take one refuses outright — so there is nowhere in this
   * capture path for audio to be sent, full stop, with no route-specific
   * inference needed. See `__tests__/upload-claim-parity.test.tsx` §5, which
   * bans the retired existential-negative shape across all five upload-claim
   * sites and pins the affirmative claim tolerantly.
   */
  voiceAudioHandling:
    'Audio stays in this tab’s memory. It is never uploaded, never written to ' +
    'disk, and is discarded when you clear it, leave this record, or reload the ' +
    'page. This application declares no multipart form anywhere, and its one ' +
    'upload route refuses every request outright — so nothing in this capture ' +
    'path has anywhere to send it.',

  /*
   * ── THE INTAKE CHOOSER (project owner, 2026-09-13) ────────────────────────
   *
   * "Data capture should be the first step, and this is where scientists can
   * make a choice whether they want to upload files that they have from their
   * own experiments, or if they want to use the voice assistant thing and we
   * record it directly with the transcription model."
   *
   * THREE ROUTES, NOT TWO, AND THE THIRD IS THE ONE THAT WORKS TODAY. The two
   * the owner named are the intended ones; measured over HTTP, both are
   * externally blocked in this build and typing is not:
   *
   *   POST .../transcript        -> 200   text becomes a note, and candidates
   *                                       become proposals
   *   POST /api/transcription    -> 501   no_provider_configured
   *   POST /api/uploads          -> 403   unconditional
   *
   * So a chooser offering only the owner's two would offer a scientist two doors
   * that do not open. Writing it down is listed first and styled primary because
   * it is the one that reaches a proposal today.
   *
   * *** NOTHING HERE IMPLIES TRANSCRIPTION WORKS. *** `CLAUDE.md` §15 and
   * `ai-integration-decision-packet.md` §6 are explicit — no fake `Connected`
   * state, and 'build nothing that implies any of it exists'. Dean DEFERRED
   * D1–D9 on 2026-08-12, so there is no approved provider, endpoint or
   * credential, and no application change can create one. The recorder is real
   * and useful anyway (hands-free capture, in-tab playback), and this copy says
   * exactly which half is missing and whose decision it is.
   *
   * The file wording is deliberately 'record where each file lives' rather than
   * 'upload': `upload-claim-parity.test.tsx` bans absolute no-read phrasings,
   * and Historical Import keeps a pointer, a checksum and the reader's notes
   * WITHOUT reading bytes. That is a real capability, described as what it is.
   */
  intakeHeading: 'How do you want to get this experiment in?',
  /*
   * "Four ways in", not three — the fourth card was added 2026-09-14.
   *
   * The project owner: *"the runs should be a part of the initial capture and
   * proposals."* He was describing a real gap rather than a preference: this
   * screen asks "How do you want to get this experiment in?" and then offered
   * three routes, none of which was the one that records WHAT WAS MEASURED. A
   * scientist could answer the question honestly, use every route on offer, and
   * still have entered no scan. Runs were a sibling workspace pill instead.
   */
  intakeIntro:
    'Four ways in, and you can use more than one on the same record. Everything ' +
    'you put in stays exactly as you wrote it — ISAAC proposes values from it and ' +
    'you accept, correct or refuse each one.',

  /*
   * THE THREE CARD TITLES ARE REGISTER 1 — casing conformance, 2026-09-14.
   *
   * ~~'Write it down'~~ / ~~'Record at the instrument'~~ / ~~'Bring files you
   * already have'~~ were Sentence case. They are CARD TITLES, which
   * `casing-and-copy.md:10` lists in Register 1 ("page titles, section titles,
   * card titles, empty-state titles"), and they render at the same 15px/600
   * card-title tier (`typography.md:49`) as `.notes-title` ("Unmapped Notes")
   * and `.proposals-title` ("Ingestion Proposals") — two Title Case siblings
   * that sit on the same screen. One tier cannot carry two conventions, so the
   * three moved to the convention the spec names for the tier rather than the
   * other two moving to the one it does not.
   *
   * `at` and `the` stay lowercase: both are in `labels.ts`'s `MINOR_WORDS`, and
   * the spec's own approved examples do the same ("Confirmed by You").
   *
   * `intakeHeading` above is DELIBERATELY NOT TOUCHED. It is a nine-word
   * question ending in `?` — prose by `casing-and-copy.md:22` ("anything longer
   * than a label"), not a label — and Title-Casing a question would be the
   * error in the other direction.
   */
  /*
   * THE DIRECT ROUTE, AND THE ONLY ONE THAT WRITES A VALUE ITSELF.
   *
   * The other three all end in a PROPOSAL a person decides on. This one is the
   * scientist typing the conditions they set, so the honest body says so rather
   * than implying a proposal step that does not exist here. Title Case per
   * Register 1, same 15px/600 card tier as its three siblings.
   *
   * "one run per set of measurement conditions" is the Runs workspace's own
   * subtitle, reused verbatim so the card and its destination agree about what a
   * run IS -- the vocabulary drift this repo keeps finding comes from paraphrasing
   * a definition that already exists somewhere else.
   */
  intakeRunTitle: 'Enter the Scan Directly',
  intakeRunBody:
    'Type the conditions you set — one run per set of measurement conditions. ' +
    'Unlike the other three routes this is you entering the value, not ISAAC ' +
    'proposing one, so nothing here needs your confirmation afterwards.',
  intakeRunAction: 'Add Run',

  intakeWriteTitle: 'Write It Down',
  intakeWriteBody:
    'Type or paste what happened at the instrument. ISAAC reads it for values, ' +
    'asks about anything it will not guess, and keeps your exact words either way.',
  intakeWriteAction: 'Start Writing',
  intakeWriteAvailable: 'Ready to use',

  intakeVoiceTitle: 'Record at the Instrument',
  intakeVoiceBody:
    'Record while your hands are busy. The audio stays in this tab and is never ' +
    'uploaded — you can play it back here and type from it.',
  intakeVoiceAction: 'Open Recorder',
  /*
   * THE LIMIT, ATTRIBUTED. It names WHAT is missing (an approved provider), WHO
   * decides (not this application), and what the control still does — so a reader
   * can tell a deferred decision from a broken feature.
   */
  intakeVoiceLimit:
    'Speech-to-text is not turned on in this deployment: it needs a transcription ' +
    'provider that has been approved for scientific audio, which is an ' +
    'institutional decision rather than a setting here. Recording and playback ' +
    'work now; the words have to be typed.',

  intakeFilesTitle: 'Bring Files You Already Have',
  intakeFilesBody:
    'Record where each file lives, with its checksum and your notes, so the record ' +
    'points at the real material. One layout is read today; everything else is kept ' +
    'as a reference for a later build that can read it.',
  intakeFilesAction: 'Go to Historical Import',

  // -- primary/secondary controls, per voice state --------------------------
  voiceRecord: 'Start Recording',
  voiceRequesting: 'Requesting…',
  voiceStop: 'Stop Recording',
  /*
   * PAUSE/RESUME — 2026-09-11. Both labels carry the noun, for the same reason
   * every other control here does: "Pause" and "Resume" alone are ambiguous on
   * a screen that also plays audio back, and an accessible name read out of
   * context ("Resume") should still say what resumes.
   *
   * NEITHER IS RENDERED UNLESS THE RECORDER THIS BROWSER ACTUALLY BUILT CARRIES
   * BOTH METHODS — see `pauseSupported` in the panel. A control that does
   * nothing is worse than no control, and `MediaRecorder.pause` is well
   * supported but not universal.
   */
  voicePause: 'Pause Recording',
  voiceResume: 'Resume Recording',
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
  /*
   * THE `paused` AND RESUMED ANNOUNCEMENTS — polite, through the ONE existing
   * status region, exactly as every other state change here is.
   *
   * `voicePausedLive` repeats the microphone fact rather than assuming the
   * reader saw the visible line: a live region announces a CHANGE, and the
   * change a screen-reader user most needs at this moment is that the device
   * is still open.
   *
   * `voiceResumedLive` is its own sentence rather than a reuse of
   * `voiceRecordingLive`. Two reasons, and the second is mechanical. (1)
   * "resumed" is the fact — a reader who hears "Recording." cannot tell whether
   * their Resume press worked or whether they are hearing the start of a NEW
   * recording that lost the first part. (2) `e2e/mutation/capture-microphone.spec.ts:526`
   * asserts the exact sentence `voiceRecordingLive` appears EXACTLY ONCE on the
   * page; keeping resume's text distinct means a resumed recording cannot
   * introduce a second copy of a string a fenced spec counts.
   */
  voicePausedLive:
    'Recording paused. Nothing is being captured; the microphone is still open. ' +
    'The audio so far is held in this tab.',
  voiceResumedLive: 'Recording resumed. Audio is being held in this tab.',
  /*
   * THE TWO REFUSAL SENTENCES, AND THEY ARE NOT DECORATION.
   *
   * `pause()`/`resume()` can throw `InvalidStateError`, and a UA is free to
   * leave the recorder's `state` unchanged. The panel VERIFIES the transition
   * by re-reading `recorder.state` rather than assuming the call worked, so
   * there is a real branch in which the press did nothing — and the only
   * dishonest thing available at that point would be to paint the bar `Paused`
   * over a recorder that is still capturing. Each sentence therefore states
   * what is still true, not what was attempted.
   */
  voicePauseRefusedLive:
    'This browser did not pause the recording, so it is still recording. Stop ' +
    'Recording still works.',
  voiceResumeRefusedLive:
    'This browser did not resume the recording, so it is still paused. Stop ' +
    'Recording still works.',
  /*
   * THE RECORDING ENDED WITHOUT ANYONE PRESSING STOP — added after independent
   * review measured `voicePausedPersistent` making a claim a real browser can
   * falsify.
   *
   * MEASURED IN CHROME: pause, then end the track (unplug the device, or have
   * the OS revoke it). `recorder.state` becomes `inactive` and
   * `track.readyState` becomes `ended`, while the bar still says `Paused` and
   * the visible line still says "The microphone is still open". Both false at
   * that moment, and the old resume refusal made it worse by insisting the
   * recording was "still paused".
   *
   * This sentence is what the panel says instead, and it is paired with an
   * actual transition to `held` — announcing an ended recording while leaving
   * the microphone-still-open paragraph on screen would have replaced one
   * false claim with a self-contradiction.
   */
  voiceRecordingEndedLive:
    'This recording has ended — the microphone is no longer available to this ' +
    'tab. What was recorded is held here and has not been sent anywhere.',
  /*
   * THE TWO CAPABILITY REFUSALS. Neither is reachable in a browser that
   * carries both methods, and neither is reachable through the rendered
   * controls in one that carries neither — `pauseSupported` requires BOTH, so
   * no Pause is offered at all. They exist because the alternative at those
   * two early returns was a SILENT `return`: a control that does nothing and
   * says nothing, which is the one outcome this panel's own header forbids.
   */
  voicePauseUnavailableLive:
    'This browser cannot pause a recording, so nothing changed. It is still ' +
    'recording, and Stop Recording still works.',
  voiceResumeUnavailableLive:
    'This browser cannot resume a paused recording, so nothing changed. Stop ' +
    'Recording keeps what was recorded before the pause.',
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

  /*
   * THE TRANSCRIPTION REFUSAL, LED IN THE SCIENTIST'S REGISTER — 2026-09-10.
   *
   * THE HONESTY IS UNCHANGED; THE AUDIENCE WAS WRONG. The server's own sentence
   * names `decision D9`, `decision D4`, `decisions D6, D8` and a governance
   * document — every word of it accurate, and the wrong first thing to hand
   * somebody standing at a beamline mid-experiment. NOTHING THE SERVER SAID IS
   * DELETED OR PARAPHRASED AWAY: its message, its `missing` list and its
   * `decision_reference` all still render, verbatim, behind a `Why?` disclosure
   * for the reader who needs them. What changes is which of the two a reader
   * meets first.
   *
   * EACH LEAD IS SELECTED BY THE SERVER'S OWN `reason` CODE, never by this
   * client guessing a cause — the same shape `voiceDenialCopy` already uses to
   * turn a `DOMException.name` into a sentence. `voiceRefusalOther` is the
   * FAIL-CLOSED default and names no cause at all, because `REFUSAL_REASONS`
   * (`apps/api/isaac_api/providers/refusal.py`) can grow a reason this list does
   * not know, and a lead that guessed would be exactly the invention §5 forbids.
   *
   * NONE OF THE THREE CLAIMS A PROVIDER EXISTS, is coming, or could be retried —
   * the same prohibition `_FORBIDDEN_MESSAGE_SUBSTRINGS` puts on the server side.
   */
  voiceRefusalNoProvider:
    'This installation cannot turn speech into text: it reports no transcription ' +
    'service configured.',
  voiceRefusalInputMissing:
    'The transcription request had nothing to work with, so no text was produced.',
  voiceRefusalOther: 'This installation did not turn the speech into text.',
  voiceRefusalWhy: 'Why?',
  voiceRefusalDetailIntro:
    'Below is what this deployment itself said, unedited. This page adds nothing ' +
    'to it and takes nothing away.',

  /*
   * ── THE ROUTE THAT CAN ACTUALLY PRODUCE TEXT ──────────────────────────────
   *
   * The project owner's reasoning, 2026-09-14: *"the recording is held but it
   * becomes kind of useless, i think how it should be is that yeah sure they can
   * record on the site but at the end of the day if they cant transcribe its
   * useless right so instead we give them instructions of how to setup the mcp
   * instead on their claude and then tell em how to use it and specific verbage
   * on what to say instead and for that put it behind a collapsible thing"*.
   *
   * That is correct about this build and will stay correct until a provider is
   * approved: `POST /api/transcription` answers `501 no_provider_configured` in
   * every deployment, and `requestTranscript` sends
   * `audio_ref: "held-in-tab:<n>"` — an integer no provider could dereference
   * even if one existed. So in-browser audio can be played back and typed from,
   * and nothing else.
   *
   * A CLAUDE APP CAN DO IT, because the transcription happens THERE and only
   * text crosses the boundary: `isaac_capture_transcript` takes a finalized
   * transcript, stores every segment as a note and mints one proposal per
   * extracted candidate. Measured over real JSON-RPC: 5 notes, 3 candidates, 3
   * proposals.
   *
   * ── WHAT THIS COPY MAY NOT DO ────────────────────────────────────────────
   *
   * `CLAUDE.md` §15 and `ai-integration-decision-packet.md` §9 forbid building
   * anything that implies the agent path exists here. The MCP transport is
   * UNMOUNTED in every deployment (`ISAAC_MCP_DEPLOYMENT` unset), so every
   * sentence below is CONDITIONAL and the precondition is stated first, not
   * buried: there is no endpoint yet, and whether there is one is the
   * deployment's decision. It points at Settings → Connect Your Agent rather
   * than restating the procedure, so the two surfaces cannot drift.
   */
  mcpRouteHeading: 'Transcribe With Your Claude App Instead',
  mcpRouteLead:
    'Speech becomes text in your Claude app, not here — so the words never ' +
    'reach this deployment as audio, only as text you have seen.',
  mcpRoutePrecondition:
    'This needs an agent endpoint, and this deployment publishes none yet. ' +
    'Whether it does is an organization decision — Settings → Connect Your ' +
    'Agent reports the current state and the full setup steps.',
  mcpRouteSayLabel: 'What to say, once it is connected',
  /*
   * A WORKED SENTENCE rather than a description of one. The owner asked for
   * "specific verbage on what to say". It names the record and dictates values
   * in the phrasing the extractor actually recognises — measured: a sentence
   * pairing a start word with a full UTC instant yields a candidate, and
   * "held at 301 K in vacuum" yields the temperature and environment.
   */
  mcpRouteSayExample:
    '"Add these notes to my ISAAC experiment <name>, run 1: sample held at ' +
    '301 K in vacuum, acquisition started 2026-09-15T02:00:00Z."',
  mcpRouteOutcome:
    'Your words are stored word for word as notes on the record. Any value ' +
    'ISAAC can read from them becomes a proposal you review here — nothing is ' +
    'written to a field until you accept it.',

  transcriptLabel: 'Transcript',
  transcriptHint:
    'Finalizing stores this text with the record and reads it. Editing it ' +
    'afterwards means finalizing again.',
  runLabel: 'Run These Notes Describe',
  runPlaceholder: 'Choose a run…',
  /*
   * "run-scoped" WAS DROPPED FROM THIS SENTENCE — 2026-09-10, AND THE REASON IS
   * THAT THIS BUILD SHIPPED TWO STRINGS THAT COULD NOT BOTH BE TRUE.
   *
   * This hint and `runTargetsNone` said "only run-scoped values need a run
   * chosen first", which tells a reader their values may not need one. The
   * server's own `run_target_required` clarification said the opposite —
   * "Every value this reader can propose belongs to a run". Both shipped.
   *
   * MEASURED, rather than argued, at `65f5ebd3`:
   *
   *     .venv/bin/python -c "import sys; sys.path.insert(0,'apps/api');
   *       from isaac_api import transcript_capture as tc, routes;
   *       print({p: routes._PROPOSAL_WRITER_SCOPE.get(routes._proposal_writer_for(p))
   *              for p in sorted(tc.READABLE_FIELD_PATHS)})"
   *
   * All FIVE readable paths — `context.environment`, `context.temperature_K`,
   * `context.thermodynamics.atmosphere`, `timestamps.acquired_start_utc`,
   * `timestamps.acquired_end_utc` — resolve to writer `run_field`, scope `run`.
   * The SERVER'S sentence was the true one; these two were the false ones.
   *
   * THE REPLACEMENT DELIBERATELY DOES NOT RESTATE THE SERVER'S CLAIM. It states
   * the BEHAVIOUR instead — nothing is proposed without a run — because that
   * rests on a stronger and simpler invariant that cannot drift: with no run,
   * `read_transcript` inserts a `run_target_required` clarification, `settled`
   * is False, and the candidate loop is skipped whole (`if not settled:
   * continue`). That holds even if a record-scoped readable path is ever added,
   * whereas "every value belongs to a run" would silently become false.
   */
  runHint:
    'Required before any value can be proposed from a transcript. It is never ' +
    'chosen for you, even when the record has exactly one run.',
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
  /*
   * Said when NO run is selected. The old wording — "Proposals from this
   * transcript will target the record itself — only run-scoped values need a
   * run chosen first" — was wrong twice over: no proposal is minted at all
   * without a run, and none of the five readable paths is record-scoped. See
   * the measurement recorded on `runHint` above.
   */
  runTargetsNone:
    'No run is selected. Nothing will be proposed from this transcript until ' +
    'you choose one — the text itself is still stored with the record as notes.',

  finalize: 'Finalize and Read',
  finalizeHint:
    'Reading happens only when you press this. Text you are still typing is ' +
    'never read and never stored.',
  /*
   * THE PRE-FLIGHT BESIDE THE BUTTON, not a reason to disable it. Finalizing
   * with no run stores every word as notes, which is genuinely valuable and is
   * the whole reason the run selector is allowed to stay empty. What was
   * missing was any warning at the point of action that THIS press proposes
   * nothing — a reader previously found out from a summary card reading
   * "Nothing was proposed from this transcript."
   */
  finalizePreflightNoRun:
    'No run selected — this will be stored as notes only, and will propose nothing.',
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

/*
 * Transcript capture — the scientist workflow, and a voice surface that tells the
 * truth about itself.
 *
 * PR-D (2026-09-03) MADE THIS A STATE-DRIVEN INTERFACE. The table below has NINE
 * ROWS, matching `ia-brief.md` §6's required shape (which itself matches the
 * orchestrating brief's own enumeration). Three are new relative to the PR-A build
 * this replaces (marked NEW below); the rest keep their existing meaning and most
 * keep their existing copy verbatim.
 *
 * NINE ROWS IS NOT NINE STATES, AND THIS HEADER USED TO SAY IT WAS. `type
 * VoiceState` below has exactly SIX members; the other three rows are DERIVED
 * booleans computed from `busyKind`, `reading` and `error`/`retryTag`. The
 * distinction is load-bearing rather than pedantic: the six are mutually exclusive
 * by construction (`voice` is one value), while a derived row can be true AT THE
 * SAME TIME as one of the six — a reader can be recording while a finalize error
 * is on screen. That is exactly why the primary-action slot has to be COMPUTED in
 * priority order (see `showErrorPrimary` and its comment below) and cannot be read
 * off this table row by row. The file conceded the mismatch in that comment while
 * this header still claimed nine states; the `Kind` column is the fix.
 *
 * | State                  | Kind | Shown                                  | Primary                | Secondary                                  | Announcement (`role="status"`) |
 * |-------------------------|------|-----------------------------------------|-------------------------|----------------------------------------------|----------------------------------|
 * | idle                    | `VoiceState` | run selector (or its own empty state), textarea, seam status | Start Recording | run selector; textarea; Create a Run (0 runs only) | "Not recording." |
 * | requesting-permission NEW| `VoiceState` | Start button disabled + busy-labeled    | *(none — busy)*         | textarea remains usable                        | "Requesting microphone access…" |
 * | recording                | `VoiceState` | live indicator + elapsed time           | Stop Recording          | textarea remains editable in parallel          | "Recording. Audio is being held in this tab." |
 * | held                     | `VoiceState` | Request/Discard both enabled            | Type What Was Said      | Request a Transcript; Discard Audio            | "Recording stopped. Audio is held in this tab and has not been sent." |
 * | permission-denied        | `VoiceState` | same as idle + persistent notice        | Type What Was Said      | Try Recording Again                            | `voicePermissionRefused` (same sentence, persistent AND announced once) |
 * | unsupported               | `VoiceState` | voice controls absent; textarea only    | *(typing is the only path)* | none                                        | `voiceUnsupported` (static, not live) |
 * | processing NEW           | DERIVED: `busyKind === 'finalize'` (`formLocked`) | Finalize disabled + busy-labeled; the rest of the form disables | *(none — busy, no cancel)* | none | "Reading transcript…" |
 * | proposals-ready          | DERIVED: `reading !== null && !formLocked` | a compact summary card, replacing the old inline candidate list; text stays in the box | Review N Proposals | Capture Another Note; Discard This Transcript | "Finalized. N segment(s) stored…, M value(s) proposed." |
 * | recoverable-error        | DERIVED: `error !== null && retryTag !== null` | the specific `FALLBACK.*` sentence      | Try Again (re-invokes the same action) | every unaffected control stays live | the `FALLBACK.*` string, reused verbatim |
 *
 * THREE THINGS THIS COMPONENT WILL NOT DO
 * =======================================
 *
 * **It never reads unfinished text.** There is no debounce, no timer, no
 * `onChange` that calls the server. `captureTranscript` is reachable from exactly
 * one button, and the server refuses a body without `finalized: true` in any case.
 *
 * **It never writes a value by itself, and it no longer accepts one either.**
 * Finalizing mints a DURABLE ingestion proposal per candidate, server-side, in the
 * same lock and the same save as the notes. This panel therefore lists what was
 * stored and says where it is reviewed; it calls no write path of its own. The
 * separate proposals surface (`IngestionProposalsPanel`, directly below this one on
 * every mount this application has) is where a person accepts or rejects.
 *
 * **It never claims a capability the deployment does not have.** The transcription
 * status is rendered from `GET /api/providers/capabilities` and from the refusal
 * body the transcription operation returns — both produced by the process that
 * would do the work. There is no hardcoded "not configured" string, no "Connected",
 * no "Ready", and no spinner that outlives a refusal.
 *
 * AUDIO NEVER LEAVES THE TAB, AND THE UI SAYS SO RATHER THAN IMPLYING IT.
 * `MediaRecorder` chunks are held in a ref, counted only to build the opaque
 * handle below — the count is NOT rendered — and dropped on discard, on close, on
 * record change, and on unmount. The drop detaches `ondataavailable` BEFORE calling
 * `stop()`, because `stop()` emits its last chunk asynchronously and would
 * otherwise refill a buffer the live region had just announced as empty. Nothing
 * serialises them, nothing puts them in a request body, and there is no upload
 * endpoint in this application for them to reach. The one request that mentions
 * audio sends an opaque handle — a string this component minted — and never the
 * audio.
 *
 * WHAT THIS COMPONENT DELIBERATELY DOES NOT HANDLE, NAMED RATHER THAN SILENT.
 * **Second-tab/second-instance protection is out of scope.** Nothing here detects
 * a second tab of the same record also recording; the duplicate-session guard
 * below is only "this component's own render cannot show two Start buttons at
 * once" (`voice` is a single value, so exactly one control set renders). **This
 * component does not watch document visibility.** If a future screen mounts this
 * panel behind a hidden-but-still-mounted destination (the multi-destination IA
 * brief's `?view=capture`), a recording in progress KEEPS RUNNING — there is no
 * `visibilitychange` listener here to interrupt it, which is deliberate: the state
 * table above requires recording to survive being hidden, not to stop.
 *
 * CORRECTED, INDEPENDENT REVIEW OF PR-D: an earlier version of this paragraph
 * also claimed the live region "keeps announcing state correctly" while hidden.
 * That is false under the `hidden` attribute (the mechanism PR-B's `?view=`
 * destinations use to keep an inactive workspace mounted): a `hidden` ancestor
 * removes its whole subtree from the accessibility tree, so nothing inside it —
 * including this panel's `role="status"` regions — is announced by assistive
 * technology while hidden, however many times its text changes. The accurate
 * claim is narrower: recording continues in the background, nothing is
 * auto-stopped, and once the workspace is shown again the live regions resume
 * announcing on the next state change — there is no missed-announcement replay,
 * because a live region announces a CHANGE, not a history.
 */

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { ApiError, api, providerRefusalOf } from '../lib/api';
import { mutationFailureCopy } from '../lib/mutationErrors';
import {
  CAPTURE_COPY,
  CAPTURE_GUIDANCE_EXAMPLE,
  CAPTURE_GUIDANCE_SENTENCE,
} from '../lib/transcriptCaptureContent';
import {
  isCaptureGuidanceSeen,
  markCaptureGuidanceSeen,
} from '../lib/transcriptCapturePreference';
import { markSelfMintedProposals } from '../lib/selfMintedProposals';
import type {
  ApiProviderCapabilities,
  ApiProviderRefusal,
  ApiRunView,
  ApiTranscriptCapture,
} from '../lib/types';
import { DiscardStaged } from './DiscardStaged';
import { DISCARD_COPY } from '../lib/discardContent';
import './transcriptCapture.css';

/** The SIX voice states — the six `VoiceState` rows of this panel's header table.
 *  The table's other three rows are derived, not members here; see the header. */
type VoiceState =
  | 'unsupported'
  | 'idle'
  | 'requesting-permission'
  | 'recording'
  | 'held'
  | 'permission-denied';

/** What is in flight, so `processing` (finalize only) is distinguishable from a
 *  transcription or run-create request — the three are refused independently and
 *  disable different things. */
type BusyKind = 'transcribe' | 'finalize' | 'createRun' | null;

/**
 * WHICH ACTION LAST FAILED — a TAG, not a captured closure.
 *
 * I1, INDEPENDENT REVIEW OF PR-D: this used to be `retry: (() => void) | null`,
 * set with `setRetry(() => finalize)`. That closure captures `experimentId`,
 * `experimentVersion`, `text` and `selectedRun` AT THE MOMENT OF THE FAILURE —
 * every one of which is stale the instant anything changes afterwards. Measured
 * consequence: a 412 already calls `loadRuns()` to adopt the record's current
 * version, so the very next click of "Try Again" re-sent the OLD, already-known-
 * stale version and was refused again, forever — the stale-closure retry could
 * never recover from the one failure it exists to recover from. A failure that
 * merely refused (not 412) re-sent whatever `text` was typed AT FAILURE TIME,
 * silently discarding anything typed since.
 *
 * The fix is a TAG, which cannot go stale, dispatched through `retryAction`
 * below — a function defined fresh on every render, closing over THIS render's
 * state. Calling `finalize()` (etc.) through it always reads the current
 * `experimentVersion`/`text`/`selectedRun`, exactly as pressing the ORIGINAL
 * button would.
 */
type RetryTag = 'runs' | 'transcribe' | 'finalize' | 'createRun' | null;

/**
 * WHY A REASON RATHER THAN A BOOLEAN — I8, INDEPENDENT REVIEW OF PR-D.
 * `getUserMedia` failing is not one fact: no permission, no device, a device
 * already claimed by another application, and "something else" are four
 * different situations calling for four different reader reactions, and the
 * panel used to collapse all of them into one "permission" sentence — wrong for
 * three of the four. `'unknown'` is the deliberate FAIL-CLOSED default: a
 * browser can throw a `DOMException` this list does not name, and that case
 * must still say something true (`voiceStartFailed` names no cause) rather than
 * guess a specific one it cannot back.
 */
type VoiceDenialReason = 'denied' | 'no-device' | 'device-busy' | 'unknown';

/**
 * Classifies a `getUserMedia` rejection by its `DOMException.name`, per the
 * MDN-documented exception names for that API. Never inspects `message` —
 * browsers do not standardise it, and `name` is the contract.
 *
 * READS `name` STRUCTURALLY, NOT VIA `instanceof Error`. A real `DOMException`
 * is an `Error` in every environment this has been checked against, but
 * `instanceof` is a REALM-SENSITIVE check — an object built by a different
 * global/iframe/worker context (or a test double that never claims to be an
 * `Error`) can carry a perfectly good `.name` and still fail it. Since this
 * function reads exactly one field, checking for that field directly is both
 * more robust and no less safe: an object with no `name` at all still falls
 * through to `'unknown'`, same as before.
 */
function classifyGetUserMediaError(cause: unknown): VoiceDenialReason {
  const name =
    typeof cause === 'object' && cause !== null && 'name' in cause
      ? String((cause as { name: unknown }).name)
      : '';
  if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') {
    return 'denied';
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError' || name === 'DevicesNotFoundError') {
    return 'no-device';
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return 'device-busy';
  }
  return 'unknown';
}

/** The sentence for each {@link VoiceDenialReason}. */
function voiceDenialCopy(reason: VoiceDenialReason): string {
  if (reason === 'denied') return CAPTURE_COPY.voicePermissionRefused;
  if (reason === 'no-device') return CAPTURE_COPY.voiceNoMicrophone;
  if (reason === 'device-busy') return CAPTURE_COPY.voiceMicrophoneBusy;
  return CAPTURE_COPY.voiceStartFailed;
}

/*
 * THE FALLBACK SENTENCE FOR EACH FAILURE, and each one states WHAT WAS NOT DONE.
 *
 * `mutationFailureCopy` handles the cases it can name (a sign-in page returned in
 * place of the API, a 401, a 403) and returns this otherwise. A generic "something
 * went wrong" would leave the reader unable to tell whether their transcript was
 * stored, which is the one question that matters here. Reused VERBATIM from the
 * build this replaces — the state table's own "recoverable-error" row calls this
 * "already a strength".
 */
const FALLBACK = {
  runs: 'This record’s runs could not be read, so no run can be selected yet. Nothing was changed.',
  transcription: 'The transcription request could not be completed. No audio was sent and nothing was changed.',
  finalize:
    'This transcript was NOT stored and nothing was read from it. Your text is still in the box above.',
  createRun: 'No run was created. Nothing else was changed.',
} as const;

/** Whether this browser can record at all. Asked, never assumed. */
function audioRecordingAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  const recorder = (window as { MediaRecorder?: unknown }).MediaRecorder;
  const devices = typeof navigator === 'undefined' ? undefined : navigator.mediaDevices;
  return typeof recorder === 'function' && typeof devices?.getUserMedia === 'function';
}

/** `mm:ss`, for the recording indicator. Never rounds up — a listener who glances
 *  mid-second should see time that has actually elapsed, not time that is about to. */
function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

export function TranscriptCapturePanel({ experimentId }: { experimentId: string }) {
  const ids = useId();
  const transcriptId = `${ids}-transcript`;
  const runId = `${ids}-run`;
  const guidanceId = `${ids}-guidance`;

  /*
   * THE PANEL IS CLOSED UNTIL A READER OPENS IT, AND IT FETCHES NOTHING WHILE
   * CLOSED. Starting a capture is a deliberate act, so a control that says "start
   * one" is a truer surface than a form that is always half-filled — and a record
   * screen already issues a bundle of reads on mount; a section that quietly added
   * two more (a run listing, a capability report) would change every screen it
   * appears on, for readers who never dictate anything.
   */
  const [open, setOpen] = useState(false);
  const [guidanceOpen, setGuidanceOpen] = useState<boolean>(() => !isCaptureGuidanceSeen());
  const [capabilities, setCapabilities] = useState<ApiProviderCapabilities | null>(null);
  const [runs, setRuns] = useState<ApiRunView[]>([]);
  const [experimentVersion, setExperimentVersion] = useState('');
  const [selectedRun, setSelectedRun] = useState('');
  const [text, setText] = useState('');
  const [reading, setReading] = useState<ApiTranscriptCapture | null>(null);
  const [busyKind, setBusyKind] = useState<BusyKind>(null);
  const [error, setError] = useState<string | null>(null);
  /** WHICH action last failed. `null` when nothing has. See `RetryTag` above —
   *  this is a tag dispatched through `retryAction`, never a captured closure. */
  const [retryTag, setRetryTag] = useState<RetryTag>(null);
  const [announcement, setAnnouncement] = useState<string>('');

  const [voice, setVoice] = useState<VoiceState>('idle');
  const [voiceLive, setVoiceLive] = useState<string>(CAPTURE_COPY.voiceIdleLive);
  const [voiceDenialReason, setVoiceDenialReason] = useState<VoiceDenialReason | null>(null);
  const [refusal, setRefusal] = useState<ApiProviderRefusal | null>(null);
  const [heldChunks, setHeldChunks] = useState(0);
  const [elapsedSec, setElapsedSec] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const transcriptRef = useRef<HTMLTextAreaElement | null>(null);
  const runSelectRef = useRef<HTMLSelectElement | null>(null);
  const elapsedIntervalRef = useRef<number | null>(null);
  const loadGenerationRef = useRef(0);
  /**
   * THE RECORD GENERATION, bumped whenever this component is told to show a
   * different record. Every `await` here is a place that can happen.
   *
   * WHAT THIS ACTUALLY RESCUES, MEASURED IN REAL CHROMIUM — THE PENDING-
   * PERMISSION ORPHAN. Press Start Recording and leave the record before the
   * browser resolves the permission prompt. The panel unmounts (see the reset
   * effect below for why), its cleanup runs `dropAudio()` and finds
   * `streamRef.current === null` because no stream exists yet, and THEN
   * `getUserMedia` resolves into the closure of a dead component: it assigns
   * the stream and calls `recorder.start()`. Nothing holds a reference to
   * either, so nothing can ever stop them. Measured at `0650bd46` with an
   * instrumented `MediaStreamTrack.prototype.stop` and a real fake audio
   * device: the track stayed `live` for a full 15-second poll with ZERO
   * `stop()` calls. With the guard in `startRecording` it is `ended`, stopped
   * by the stale-generation branch. Spec:
   * `apps/web/e2e/mutation/capture-microphone.spec.ts`.
   *
   * WHY THE GENERATION BUMPS AT ALL WHEN THE PANEL IS ABOUT TO UNMOUNT, which
   * is the non-obvious part: react-router commits the new `:id` BEFORE the
   * bundle hook sets `loading`, so there is exactly one commit in which this
   * panel is mounted carrying the NEW `experimentId`. That commit runs the
   * reset effect and bumps this counter, which is what the already-in-flight
   * `getUserMedia` then compares itself against.
   *
   * THE OTHER FOUR PATHS ARE HAZARD-CLASS DEFENCE, NOT REPRODUCED DEFECTS —
   * stated rather than implied; see {@link recordScope}.
   */
  const recordGenerationRef = useRef(0);
  /**
   * Mirrors `voice` for the record-change reset below, which must READ the
   * current voice to decide whether to keep it — but must NOT re-run when voice
   * changes, or every stop/discard would drop the audio a second time. A ref
   * kept in sync by its own effect is how it reads without depending.
   */
  const voiceRef = useRef<VoiceState>(voice);
  /** The record the reset effect below last ran for, so it can tell a genuine
   *  record CHANGE from its own first run. See that effect for why mount must
   *  not be treated as a change. */
  const lastRecordRef = useRef(experimentId);

  /** `processing` — the ONE state that locks the whole form, not only its own button. */
  const formLocked = busyKind === 'finalize';

  /**
   * OPENS A RECORD SCOPE FOR ONE ASYNCHRONOUS ACTION. Call it BEFORE the first
   * `await`; the predicate it returns answers "is this still the record I was
   * started for?" afterwards. See {@link recordGenerationRef} for what goes
   * wrong without it.
   *
   * ONE HELPER RATHER THAN FIVE COPIES, DELIBERATELY. The check is two lines,
   * so four repetitions would not be long — but they would be four independent
   * chances to capture the generation in the wrong place (after the `await`,
   * where it always matches and the guard is inert), and an inert guard is
   * indistinguishable from a working one until a record change is actually
   * raced. Making "capture" and "compare" a single call means the mistake
   * cannot be written: there is nowhere to put the capture except before the
   * await, because the predicate does not exist until it has happened.
   *
   * `loadRuns` deliberately does NOT use this helper and inlines the same two
   * lines instead: it is a `useCallback`, and depending on a function redefined
   * every render would either break its memoisation or need an exhaustive-deps
   * suppression. Refs need no dependency.
   *
   * WHAT EACH USE IS WORTH, MEASURED RATHER THAN ASSERTED. `startRecording`'s
   * use fixes a defect a real browser reproduces (see
   * {@link recordGenerationRef}). The four uses in `requestTranscript`,
   * `finalize`, `createRun` and `loadRuns` are HAZARD-CLASS DEFENCE and are
   * NOT known to fix anything reachable in this application: measured in
   * jsdom through the caller's real mount sequence, a record switch unmounts
   * this panel, React 18 no-ops a `setState` on an unmounted component, and
   * the next record gets a FRESH instance — so a late response cannot reach
   * it. Removing `requestTranscript`'s guard and re-running that measurement
   * left the next record's transcript box empty either way. They are kept
   * because a stale callback writing into a live component is a real hazard
   * class, the guard costs one comparison, and a future caller that keeps this
   * panel mounted would make every one of them load-bearing at once. They are
   * not kept because they were observed to fix something.
   */
  function recordScope(): () => boolean {
    const opened = recordGenerationRef.current;
    return () => recordGenerationRef.current === opened;
  }

  /* ---- elapsed timer, owned entirely here, cleared on every exit from `recording` --- */

  const stopElapsedTimer = useCallback(() => {
    if (elapsedIntervalRef.current !== null) {
      window.clearInterval(elapsedIntervalRef.current);
      elapsedIntervalRef.current = null;
    }
  }, []);

  const startElapsedTimer = useCallback(() => {
    stopElapsedTimer();
    setElapsedSec(0);
    elapsedIntervalRef.current = window.setInterval(() => {
      setElapsedSec((seconds) => seconds + 1);
    }, 1000);
  }, [stopElapsedTimer]);

  useEffect(() => () => stopElapsedTimer(), [stopElapsedTimer]);

  /* ---- audio lifecycle. Everything here DROPS audio; nothing sends it. ---- */

  const dropAudio = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder) {
      // DETACH THE HANDLER BEFORE STOPPING — `stop()` emits its final
      // `dataavailable` ASYNCHRONOUSLY, on a later task, and the handler closes
      // over the stable `chunksRef`; nulling the ref does not unbind a DOM event
      // handler, so this ordering is what stops a discarded recording refilling
      // its own buffer a tick later.
      recorder.ondataavailable = null;
      if (recorder.state !== 'inactive') {
        try {
          recorder.stop();
        } catch {
          /* already stopping; the tracks below are what actually release the mic */
        }
      }
    }
    recorderRef.current = null;
    chunksRef.current = [];
    setHeldChunks(0);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    stopElapsedTimer();
  }, [stopElapsedTimer]);

  /*
   * UNMOUNT DROPS AUDIO — and ONLY unmount, because `dropAudio`'s identity is
   * stable (its one dependency, `stopElapsedTimer`, is `useCallback(…, [])`) and
   * `experimentId` appears nowhere in that chain.
   *
   * THIS IS THE EFFECT THAT ACTUALLY RELEASES THE MICROPHONE WHEN A SCIENTIST
   * LEAVES A RECORD IN THE APPLICATION, and it did so before this slice existed.
   * `RecordWorkbench` mounts this panel only while its bundle has data, so a
   * record switch deletes the subtree and lands here — captured in real Chromium
   * inside `commitPassiveUnmountInsideDeletedTreeOnFiber`. The record-change
   * reset below is a SECOND, caller-independent path to the same guarantee, not
   * the one an in-app switch takes. An earlier version of this comment claimed
   * both were needed for that; see the reset effect for the correction.
   *
   * The one case unmount CANNOT cover is a `getUserMedia` that has not resolved
   * yet: there is no stream to stop when this runs. That gap is closed by the
   * generation guard in `startRecording`, not here.
   */
  useEffect(() => () => dropAudio(), [dropAudio]);

  /*
   * Keeps {@link voiceRef} current, so the two resets below can READ the voice
   * without DEPENDING on it — depending on it would re-run them on every
   * stop/discard and drop the audio a second time.
   *
   * AN EARLIER VERSION OF THIS COMMENT CLAIMED THE DECLARATION ORDER WAS
   * LOAD-BEARING ("declared BEFORE the record-change reset so that…"). An
   * independent review MEASURED that false: moving this effect below the reset
   * leaves the whole suite green, and it does so for a reason, not by luck.
   * The order would only matter if `voice` and `experimentId` changed in the
   * SAME commit, and they cannot: `voice` is this component's own state and
   * `experimentId` is a prop, so a commit that changes the record carries no
   * pending voice change and the ref is already correct whichever effect runs
   * first. The order below is defensive habit, NOT a correctness requirement,
   * and it is written down that way because a comment asserting a load-bearing
   * invariant invites a future reader to build on one that does not exist.
   */
  useEffect(() => {
    voiceRef.current = voice;
  }, [voice]);

  /**
   * THE ONE PLACE THAT DECIDES WHICH VOICE STATES SURVIVE LEAVING.
   *
   * Both ways of leaving — changing record, and closing the panel — drop the
   * audio, and both must then say something true about what is left. Four of
   * the six states describe THIS session's audio (`idle`,
   * `requesting-permission`, `recording`, `held`) and are meaningless once it
   * is gone, so they return to `idle`. `unsupported` and `permission-denied`
   * describe THE BROWSER AND ITS DEVICES, not the session: `unsupported` means
   * no `MediaRecorder`/`getUserMedia` exists at all (resetting it would render
   * a "Start Recording" button that cannot work), and `permission-denied`
   * records a real `getUserMedia` refusal classified from an actual
   * `DOMException`. Neither fact is changed by leaving, and asserting
   * otherwise would be a guess. `permission-denied` keeps its own "Try
   * Recording Again", so nothing is stuck.
   *
   * Shared by both callers so the two ways of leaving cannot drift apart —
   * they already had, which is how a panel honest about changing record stayed
   * dishonest about closing.
   */
  const resetVoiceAfterLeaving = useCallback(() => {
    const left = voiceRef.current;
    if (left === 'unsupported' || left === 'permission-denied') return;
    setVoice('idle');
    setVoiceLive(CAPTURE_COPY.voiceIdleLive);
  }, []);

  /*
   * CLOSING THE PANEL RELEASES THE MICROPHONE — a deliberate act distinct from
   * this panel merely being hidden by a caller (see the header note on
   * `visibilitychange`). "Close Capture" does not unmount this component, only
   * its body, and the Stop/Discard controls and the recording live region all
   * live inside that body.
   *
   * I3, INDEPENDENT REVIEW — IT RELEASED THE MICROPHONE AND LEFT `voice` SAYING
   * `recording`. This effect dropped the audio and never touched the state, so
   * reopening the panel showed "Stop Recording", an elapsed indicator reading
   * `Recording · 0:00`, and a live region still saying "Recording. Audio is
   * being held in this tab." — with no stream, no recorder and no buffer behind
   * any of it. That is the same defect class as leaving a record by navigating,
   * one effect away: the panel would have been honest about one way of leaving
   * and dishonest about the other. Nothing is announced by the reset, because
   * the live region lives inside the body this branch has just unmounted.
   */
  useEffect(() => {
    if (!open) {
      dropAudio();
      resetVoiceAfterLeaving();
    }
  }, [open, dropAudio, resetVoiceAfterLeaving]);

  useEffect(() => {
    if (!audioRecordingAvailable()) setVoice('unsupported');
  }, []);

  /* ---- reads ------------------------------------------------------------- */

  /*
   * THE GUARD LIVES HERE, INSIDE THE READ, so all three callers get it from one
   * place — the panel's own load, `finalize`'s refresh, and `createRun`'s.
   *
   * HAZARD-CLASS DEFENCE, AND SCOPED HONESTLY. If this panel is ever held
   * mounted across a record change, a late response would show the wrong runs
   * AND hand the next write another record's `If-Match` token — which is why
   * the guard is worth its one comparison. But no caller in this application
   * does that: a record switch unmounts the panel, so in the shipped app this
   * has no defect to prevent. Do not cite it as a fix.
   */
  const loadRuns = useCallback(async () => {
    const opened = recordGenerationRef.current;
    const listed = await api.listRuns(experimentId);
    if (recordGenerationRef.current !== opened) return;
    setRuns(listed.runs);
    setExperimentVersion(listed.experiment_version);
  }, [experimentId]);

  /** Loads runs, and on failure leaves a `Try Again` behind that re-attempts THIS
   *  call — never a stale generation's error clobbering a newer attempt's state. */
  const loadRunsAttempt = useCallback(() => {
    const generation = ++loadGenerationRef.current;
    const opened = recordGenerationRef.current;
    setError(null);
    setRetryTag(null);
    loadRuns().catch((cause: unknown) => {
      if (loadGenerationRef.current !== generation) return;
      // TWO DIFFERENT GENERATIONS, AND BOTH ARE NEEDED. `loadGenerationRef`
      // separates attempts at the SAME record, so an older attempt's failure
      // cannot clobber a newer one's. This one separates RECORDS: `FALLBACK.runs`
      // says "This record's runs could not be read", which would be a failure
      // reported about a record the reader is no longer looking at — and it
      // would leave a `Try Again` on screen for it.
      if (recordGenerationRef.current !== opened) return;
      setError(mutationFailureCopy(cause, FALLBACK.runs));
      setRetryTag('runs');
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadRuns]);

  /*
   * RESETTING IS KEYED ON THE RECORD, NEVER ON THE PANEL BEING OPENED — see the
   * PR-A history this replaces: resetting on `open` silently wiped an in-progress
   * transcript the moment a reader collapsed the panel to scroll.
   */
  useEffect(() => {
    /*
     * MOUNT IS NOT A CHANGE, and skipping it is required rather than tidy. On
     * mount every value this effect writes is ALREADY its initial value, so the
     * writes are no-ops — except one. The `audioRecordingAvailable()` effect
     * above is declared earlier and therefore runs earlier in the same commit;
     * its `setVoice('unsupported')` and this effect's `setVoice('idle')` batch
     * together, and the later write wins. Running on mount would silently undo
     * unsupported-browser detection on every mount (measured: the voice controls
     * reappeared in jsdom, which has no `MediaRecorder`). This effect exists for
     * a record CHANGE; a ref is what lets it tell one from its own first run.
     */
    const changed = lastRecordRef.current !== experimentId;
    lastRecordRef.current = experimentId;
    if (!changed) return;

    /*
     * A RECORD CHANGE DROPS AUDIO — AND THE ORIGINAL JUSTIFICATION FOR THIS WAS
     * WRONG, MEASURED IN A REAL BROWSER. It is corrected here rather than
     * quietly reworded, because the wrong version was this slice's own headline
     * claim and this file exists to stop exactly that.
     *
     * WHAT WAS CLAIMED: that `RecordWorkbench` renders this panel with no `key`
     * under a single `/record/:id` route, so an in-app record switch re-uses
     * this instance and left a live `MediaRecorder`, an open microphone track
     * and the previous record's buffer in place. The hook-chain reading behind
     * that was correct in every particular (`dropAudio`'s identity IS stable, so
     * the unmount cleanup fires on unmount alone) and still reached the wrong
     * conclusion, because it was a component-level reading of a SCREEN-level
     * fact.
     *
     * WHAT IS MEASURED: `RecordWorkbench.tsx:397-412` renders the panel only
     * while `bundle.status === 'data'`. A record switch refetches, status goes
     * `'loading'`, and the whole subtree is DELETED — so this panel unmounts and
     * the pre-existing unmount cleanup already released the microphone. In real
     * Chromium at `0650bd46`, with an instrumented
     * `MediaStreamTrack.prototype.stop`, the stop was captured inside
     * `commitPassiveUnmountInsideDeletedTreeOnFiber`. THE IN-APP RECORD SWITCH
     * WAS NEVER LEAKING. Spec: `apps/web/e2e/mutation/capture-microphone.spec.ts`
     * — whose in-app-switch test passes at `0650bd46` too, and is labelled an
     * invariant guard rather than a regression guard for that reason.
     *
     * WHY THE TEARDOWN STAYS ANYWAY, and it is not sunk cost. (1) The panel
     * PUBLISHES the claim — `CAPTURE_COPY.voiceAudioHandling` says the audio is
     * discarded when you "leave this record" — and a component should keep its
     * own promise without depending on a screen it does not control to unmount
     * it. A caller holding it mounted is not hypothetical in kind: every test in
     * this file is one. (2) It is what BUMPS THE GENERATION, and that is load-
     * bearing for a defect a real browser does reproduce — see
     * {@link recordGenerationRef} for the pending-permission orphan, which is
     * the one thing here that was measured broken and measured fixed.
     *
     * So: the bump must precede `dropAudio()`, and the honest summary of the
     * two lines below is "this panel is correct independently of its caller,
     * and this is where the generation moves" — not "this stops a leak".
     *
     * M3, INDEPENDENT REVIEW — `setElapsedSec(0)` USED TO BE HERE AND IS GONE.
     * It was unobservable and its comment asserted an effect that cannot
     * occur: `formatElapsed` renders only inside `voice === 'recording'`, and
     * the only entry to `recording` is `startRecording`, which calls
     * `startElapsedTimer()` — that zeroes the count in the same batch as
     * `setVoice('recording')`, so no render can ever show a carried-over
     * duration. A write nobody can see, defended by a comment describing an
     * unreachable state, is worse than no write.
     */
    recordGenerationRef.current += 1;
    dropAudio();

    setReading(null);
    setSelectedRun('');
    setText('');
    setError(null);
    setRetryTag(null);
    /*
     * The refusal card is cleared because its own words stop being true. It ends
     * with `voiceAfterRefusal` — "The audio is still held in this tab and was not
     * sent anywhere" — and the audio has just been dropped. Same reason for the
     * finalize announcement: `reading` is reset one line above, so leaving the
     * "Finalized. N segment(s) stored…" sentence in a live region would have it
     * describing a reading whose card is no longer on screen, about a record the
     * reader has left. Clearing to `''` announces nothing.
     */
    setRefusal(null);
    setAnnouncement('');

    /*
     * I1 / I2, INDEPENDENT REVIEW — THREE MORE, AND THE OMISSION WAS THE POINT.
     * An earlier version of this enumeration listed what it reset and why, and
     * silently left these three out. In a comment whose whole value is being
     * exhaustive, an omission reads as "considered and excluded" when it was
     * "not considered". All three are reset, and the reasons are different:
     *
     * `busyKind` — under a caller that keeps this panel mounted, a record
     * change during `finalize` leaves the next record's ENTIRE FORM LOCKED
     * (submit reading "Reading…", `aria-busy="true"`, textarea and run select
     * disabled) while nothing is being read for it. Observed through a
     * rerender, which is not what this application does — the panel unmounts
     * and the next record's form is new and unlocked — so this is the same
     * caller-independence argument as the rest of this effect, not a shipped
     * defect. It is safe to clear only because every asynchronous path above
     * now checks `recordScope()` before writing, including in its `finally`;
     * clearing it without those guards would unlock a form that a stale
     * response could then write into.
     *
     * `runs` and `experimentVersion` — both are record-scoped facts, and the
     * second is the token the next write sends as `If-Match`. Held mounted,
     * the previous record's run list stays rendered until the new record's
     * fetch resolves, so on a slow connection a scientist could select ANOTHER
     * RECORD'S RUN on this record's screen while holding another record's
     * version token — a wrong-target write rather than cosmetic staleness.
     * Same scoping as `busyKind`: that window does not exist in the shipped
     * app, because the panel unmounts.
     *
     * WHAT CLEARING `runs` COSTS, STATED RATHER THAN GLOSSED: for the length of
     * B's fetch the panel renders its zero-runs branch, which tells the reader
     * this record has no runs — not yet known to be true. That claim is NOT
     * introduced here. `runs` initialises to `[]`, so every first open of every
     * record already shows it for exactly the same window; this makes a record
     * change behave like a fresh open instead of like another record. Removing
     * it altogether needs a third "not read yet" rendering state and a string
     * for it, which is a copy change outside this slice.
     *
     * DELIBERATELY NOT RESET, so the next reader knows these were considered:
     * `capabilities` (a deployment fact — whether a transcription provider is
     * configured does not vary by record); `open` and `guidanceOpen` (panel
     * furniture belonging to the reader, not the record — and collapsing or
     * re-expanding the panel under someone mid-navigation is exactly the churn
     * the "never keyed on `open`" note above exists to prevent); and `voice`,
     * which is not unconditional and is handled just below.
     */
    setBusyKind(null);
    setRuns([]);
    setExperimentVersion('');

    /*
     * WHICH VOICE STATES SURVIVE IS DECIDED IN ONE PLACE, shared with the
     * close-the-panel path — see {@link resetVoiceAfterLeaving} for why
     * `unsupported` and `permission-denied` are kept and the other four are not.
     *
     * ACCESSIBILITY, AND IT IS SPECIFIC TO THIS CALLER. The panel is OPEN here,
     * so the live region is mounted and a change to its text really is spoken.
     * The two preserved states keep their sentence unchanged, so a record change
     * announces nothing at all for them — a live region announces a change, and
     * there is none. The resetting branch says "Not recording.", which is true of
     * the record now on screen; it deliberately does NOT reuse
     * `voiceDiscardedLive` ("Audio discarded."), which would announce, to
     * somebody who has just navigated, an event belonging to the record they
     * left.
     */
    resetVoiceAfterLeaving();
  }, [experimentId, dropAudio, resetVoiceAfterLeaving]);

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    loadRunsAttempt();
    api
      .getProviderCapabilities()
      .then((payload) => {
        if (live) setCapabilities(payload);
      })
      .catch(() => {
        // A capability report that could not be read is left ABSENT rather than
        // defaulted. `null` renders as "this could not be read"; defaulting to
        // "not configured" would state, from the client, a fact about the server
        // the client does not have.
        if (live) setCapabilities(null);
      });
    return () => {
      live = false;
    };
  }, [experimentId, open, loadRunsAttempt]);

  const transcription = useMemo(
    () => capabilities?.seams.find((seam) => seam.seam === 'transcription') ?? null,
    [capabilities],
  );

  /* ---- voice --------------------------------------------------------------
   *
   * EACH FUNCTION BELOW GUARDS AGAINST BEING RE-ENTERED WHILE ITS OWN STATE
   * DOES NOT PERMIT IT — a second click cannot start a second recording or
   * finalize a second time, because the control that would trigger it is not
   * rendered in the state that follows the first click. The guard here is a
   * second line of defence for a stray call, not the primary mechanism.
   */

  async function startRecording() {
    if (voice === 'recording' || voice === 'requesting-permission' || formLocked) return;
    setVoice('requesting-permission');
    setVoiceLive(CAPTURE_COPY.voiceRequestingLive);
    setRefusal(null);
    setVoiceDenialReason(null);
    // THE RECORD THIS REQUEST BELONGS TO. Anything after the `await` below must
    // check it before touching shared state — see `recordGenerationRef`.
    const isSameRecord = recordScope();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!isSameRecord()) {
        /*
         * The reader left this record while the browser was still deciding.
         * Release THIS stream's own tracks and return without touching
         * `streamRef`, `recorderRef` or any state: the record now on screen may
         * have started its own recording in the meantime, and adopting — or
         * dropping — anything on its behalf would be acting for a record that
         * did not ask. Nothing is announced, because nothing happened to the
         * record the reader is now looking at.
         */
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
          setHeldChunks(chunksRef.current.length);
        }
      };
      recorder.start();
      setVoice('recording');
      setVoiceLive(CAPTURE_COPY.voiceRecordingLive);
      startElapsedTimer();
    } catch (cause: unknown) {
      // CLASSIFIED BY `DOMException.name` — see `classifyGetUserMediaError`. No
      // permission, no device, a device already claimed elsewhere, and "some
      // other reason" are four different facts, and only the first is really a
      // "permission" refusal. ANNOUNCED ONCE, in the status region only — the
      // persistent notice below (`voice === 'permission-denied'`) renders the
      // SAME sentence as plain text, not a second live region.
      if (!isSameRecord()) {
        /*
         * Same staleness check as the success path, and it matters MORE here:
         * `dropAudio()` below operates on the SHARED refs, so a refusal arriving
         * after the reader moved on would tear down a recording the NEW record
         * had legitimately started. There is nothing to release — the browser
         * granted no stream — so returning is the whole of the correct handling.
         */
        return;
      }
      dropAudio();
      const reason = classifyGetUserMediaError(cause);
      setVoice('permission-denied');
      setVoiceDenialReason(reason);
      setVoiceLive(voiceDenialCopy(reason));
    }
  }

  function stopRecording() {
    if (voice !== 'recording') return;
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    stopElapsedTimer();
    setVoice('held');
    setVoiceLive(CAPTURE_COPY.voiceHeldLive);
  }

  function discardAudio() {
    dropAudio();
    setVoice('idle');
    setRefusal(null);
    setVoiceLive(CAPTURE_COPY.voiceDiscardedLive);
  }

  function focusTranscript() {
    transcriptRef.current?.focus();
  }

  async function requestTranscript() {
    if (busyKind !== null || voice !== 'held') return;
    setBusyKind('transcribe');
    setRefusal(null);
    setError(null);
    setRetryTag(null);
    /*
     * C1 — RAISED AS "ONE RECORD'S DICTATION LANDS IN ANOTHER'S BOX", AND THAT
     * IS NOT REACHABLE IN THIS APPLICATION. Recorded as a correction because it
     * is the more serious claim and it was nearly committed.
     *
     * It was produced by re-rendering ONE panel instance with a new
     * `experimentId`. No caller does that: a record switch unmounts the panel
     * (see the record-change reset), React 18 no-ops a `setState` on an
     * unmounted component, and the next record is served by a FRESH instance
     * with its own empty `text`. Measured through the caller's real mount
     * sequence, with this guard REMOVED, the next record's transcript box was
     * still empty — so the guard is not what makes that true; the unmount is.
     *
     * KEPT AS HAZARD-CLASS DEFENCE, not as a fix. Were the panel ever held
     * mounted across a record change, this line is what would stop a scientist
     * being handed words they never said on this record — one Finalize away
     * from being stored as its notes and proposals. That is worth one
     * comparison. It is not worth a comment claiming it happens.
     */
    const isSameRecord = recordScope();
    try {
      // AN OPAQUE HANDLE, MINTED HERE, NAMING AUDIO THIS TAB HOLDS. No bytes, no
      // blob, no object URL that a server could dereference — the handle is
      // meaningful only to a provider that this deployment would have to be
      // configured with, and there is none.
      const result = await api.requestTranscription({ audioRef: `held-in-tab:${heldChunks}` });
      if (!isSameRecord()) return;
      setText(result.text);
      transcriptRef.current?.focus();
    } catch (cause: unknown) {
      // The refusal branch needs the guard just as much as the success one: the
      // refusal card ends with `voiceAfterRefusal` — "The audio is still held in
      // this tab" — which the record change has already made false, and the
      // focus move would yank the caret into a box on a record the reader did
      // not ask about.
      if (!isSameRecord()) return;
      const stated = providerRefusalOf(cause);
      if (stated) {
        setRefusal(stated);
        // Focus moves to the text the reader can still use, so the refusal is not
        // a dead end for somebody working by keyboard.
        transcriptRef.current?.focus();
      } else {
        setError(mutationFailureCopy(cause, FALLBACK.transcription));
        setRetryTag('transcribe');
      }
    } finally {
      // `finally` RUNS AFTER AN EARLY `return`, so it needs its own guard. The
      // record-change reset has already cleared `busyKind` for the record now
      // on screen; clearing it again here would clear a DIFFERENT request that
      // the new record had legitimately started in the meantime, unlocking a
      // form whose write is still in flight.
      if (isSameRecord()) setBusyKind(null);
    }
  }

  /* ---- finalize ---------------------------------------------------------- */

  async function finalize() {
    if (busyKind !== null || text.trim() === '') return;
    setBusyKind('finalize');
    setError(null);
    setRetryTag(null);
    setAnnouncement(CAPTURE_COPY.processingLive);
    /*
     * C2 — SAME CORRECTION AS C1, SAME REASON. It was raised as "a stale
     * finalize announces one record's result on another's screen and swaps in
     * its runs and version token", reproduced by re-rendering one instance with
     * a new `experimentId`. In the shipped application the panel unmounts on a
     * record switch, so none of those writes can reach the next record.
     *
     * The guard stays: it is the same one comparison, and the consequence it
     * would prevent under a mounted-across-switch caller is the worst on this
     * panel — `experiment_version` is the token the NEXT write sends as
     * `If-Match`, so adopting another record's would aim a write at another
     * record's concurrency token. Defence against a hazard class, not a
     * reproduced defect.
     */
    const isSameRecord = recordScope();
    try {
      const payload = await api.captureTranscript(experimentId, {
        experimentVersion,
        text,
        ...(selectedRun ? { runId: selectedRun } : {}),
      });
      // SAME-TAB COURTESY, NOT A SERVER FACT. So `IngestionProposalsPanel`'s
      // arrival note (built for a colleague's change) does not fire for the
      // proposals THIS finalize just minted, on the same screen. See
      // `lib/selfMintedProposals.ts` for exactly what this can and cannot know.
      //
      // DELIBERATELY OUTSIDE THE GUARD BELOW, and this is the one call here that
      // belongs outside it. It closes over `experimentId` — record A, the record
      // these proposals were actually minted on — so it is correct wherever the
      // reader has gone, and it is what stops A's own arrival note firing when
      // the reader returns to A. Everything after the guard writes into THIS
      // PANEL, which is now showing someone else.
      markSelfMintedProposals(
        experimentId,
        payload.proposals.map((entry) => entry.proposal.proposal_id),
      );
      if (!isSameRecord()) return;
      setReading(payload);
      setExperimentVersion(payload.experiment_version);
      /*
       * I7, INDEPENDENT REVIEW OF PR-D — BOTH NUMBERS, AS THE BUILD THIS
       * REPLACES ALWAYS SAID. The summary used to name only what was STORED,
       * dropping the READ count the original announcement carried — and a
       * candidate the extractor read but could not store (the row-count or
       * byte ceiling; see `summaryUnproposable`) is real and disclosed
       * elsewhere on this same card, so the announcement must not imply every
       * read value became a proposal. It also directs to Ingestion Proposals
       * ONLY when there is something there to review — pointing a reader at
       * an empty destination is its own small dishonesty.
       */
      const storedCount = payload.proposals.length;
      const readCount = payload.candidates.length;
      setAnnouncement(
        `Finalized. ${payload.capture.segments} segment(s) stored with this record, ` +
          `${readCount} value(s) read, ${storedCount} stored as proposal(s)` +
          (storedCount > 0 ? '. Review them in Ingestion Proposals below.' : '.'),
      );
      await loadRuns();
    } catch (cause: unknown) {
      // `FALLBACK.finalize` reads "This transcript was NOT stored … Your text is
      // still in the box above" — two claims about a record the reader has left,
      // the second of which is false here because the reset emptied the box.
      if (!isSameRecord()) return;
      setError(mutationFailureCopy(cause, FALLBACK.finalize));
      setRetryTag('finalize');
      setAnnouncement('');
      if (cause instanceof ApiError && cause.status === 412) await loadRuns();
    } finally {
      // See `requestTranscript`'s `finally` for why this is guarded.
      if (isSameRecord()) setBusyKind(null);
    }
  }

  /**
   * `proposals-ready`'s primary action: move focus (and the viewport) to the
   * Ingestion Proposals heading, which sits directly below this panel on every
   * mount this application has. Never claims a count the heading does not carry
   * itself — it moves focus, and the panel below states its own numbers.
   *
   * m6, INDEPENDENT REVIEW OF PR-D — NEVER A DEAD CONTROL. The heading is
   * reached by DOM id, which is this component's own assumption about a
   * sibling it does not render; if that assumption is ever wrong (a future
   * layout, a test harness, a caller that omits `IngestionProposalsPanel`),
   * the button used to do NOTHING and say nothing — pressing it looked broken.
   * It now falls back to the proposals SECTION by class, and if neither is
   * found, it announces that truthfully rather than staying silent: the
   * proposals are stored regardless of whether this control can reach them.
   */
  function reviewProposals() {
    const heading = document.getElementById('ingestion-proposals-heading');
    if (heading !== null) {
      heading.scrollIntoView({ block: 'start' });
      heading.focus();
      return;
    }
    const section = document.querySelector('.proposals-section');
    if (section !== null) {
      section.scrollIntoView({ block: 'start' });
      setAnnouncement(
        'The Ingestion Proposals heading could not be found, so this scrolled to ' +
          'the proposals section instead. Your proposals are still stored.',
      );
      return;
    }
    setAnnouncement(
      'Ingestion Proposals could not be located on this screen. Your proposals ' +
        'are still stored with the record.',
    );
  }

  /** Starts a new segment: clears what this reading reported and the typed text,
   *  WITHOUT touching anything already stored (the notes and proposals stay on
   *  the record — this only clears what is on screen). */
  function captureAnother() {
    setReading(null);
    setText('');
    setAnnouncement('Ready for another note.');
    transcriptRef.current?.focus();
  }

  async function createRun() {
    if (busyKind !== null) return;
    setBusyKind('createRun');
    setError(null);
    setRetryTag(null);
    /*
     * The run is created on the record this call names, and creating it is not
     * undone by the reader navigating — but SELECTING it, announcing it, and
     * adopting its version token are all claims about the panel's CURRENT
     * record. Unguarded, "Created Run 3. It is now selected." would appear on a
     * record that has no Run 3, with `selectedRun` holding another record's run
     * id and focus yanked into its dropdown.
     */
    const isSameRecord = recordScope();
    try {
      const created = await api.createRun(experimentId, { experimentVersion });
      if (!isSameRecord()) return;
      setExperimentVersion(created.experiment_version);
      await loadRuns();
      setSelectedRun(created.run.id);
      runSelectRef.current?.focus();
      setAnnouncement(`Created ${created.run.label}. It is now selected.`);
    } catch (cause: unknown) {
      if (!isSameRecord()) return;
      setError(mutationFailureCopy(cause, FALLBACK.createRun));
      setRetryTag('createRun');
    } finally {
      // See `requestTranscript`'s `finally` for why this is guarded.
      if (isSameRecord()) setBusyKind(null);
    }
  }

  /**
   * Dispatches `retryTag` to the CURRENT version of the action it names —
   * defined fresh every render, so it always closes over this render's
   * `experimentVersion`/`text`/`selectedRun`, never a stale one. See the
   * `RetryTag` comment for the defect this replaces.
   */
  function retryAction() {
    if (retryTag === 'runs') loadRunsAttempt();
    else if (retryTag === 'transcribe') void requestTranscript();
    else if (retryTag === 'finalize') void finalize();
    else if (retryTag === 'createRun') void createRun();
  }

  function dismissGuidance() {
    markCaptureGuidanceSeen();
    setGuidanceOpen(false);
    transcriptRef.current?.focus();
  }

  /* ---- discard (typed input only; no request, ever) ----------------------- */

  const hasStagedCapture = text !== '';
  const discardCopy =
    reading === null ? DISCARD_COPY.transcriptUnsent : DISCARD_COPY.transcriptAfterFinalize;
  const discardStagedCapture = () => {
    setText('');
  };

  /* ---- proposals-ready summary numbers ------------------------------------ */

  const proposalsStored = reading?.proposals.length ?? 0;
  const notesStored = reading?.notes.length ?? 0;
  const unproposableCount = reading?.unproposable.length ?? 0;
  const selectedRunLabel = runs.find((run) => run.id === selectedRun)?.label ?? null;

  /*
   * I2, INDEPENDENT REVIEW OF PR-D — "ONE PRIMARY ACTION PER STATE" WAS
   * DOCUMENTED AND NOT DELIVERED. Measured: `idle` rendered THREE `btn-primary`
   * buttons at once (the entry toggle, Start Recording, and Finalize and Read),
   * and `proposals-ready` rendered four. Every `.btn-primary` on screen is now
   * derived from ONE set of mutually-exclusive booleans, in priority order —
   * an error takes precedence over everything (it is the most urgent thing to
   * act on), then `processing`'s own busy Finalize, then `proposals-ready`'s
   * Review/Capture Another Note, then the active voice state's own button, and
   * only then — when NONE of those claims the slot — does Finalize itself
   * become primary. `voice` and the finalize/reading lifecycle are genuinely
   * TWO INDEPENDENT state dimensions here (a reader can start a new recording
   * without pressing "Capture Another Note" first), which is why this cannot
   * be read off the nine-state table row by row; it is computed.
   */
  const showErrorPrimary = error !== null && retryTag !== null;
  const showReadingPrimary = !showErrorPrimary && !formLocked && reading !== null;
  const showVoicePrimary =
    !showErrorPrimary && !formLocked && !showReadingPrimary && voice !== 'unsupported';
  const showFinalizePrimary =
    !showErrorPrimary &&
    (formLocked || (!showReadingPrimary && !showVoicePrimary && text.trim() !== ''));
  const primaryClass = (isPrimary: boolean) => (isPrimary ? 'btn btn-primary' : 'btn btn-secondary');

  /* ---- render ------------------------------------------------------------ */

  return (
    <section className="capture-section" aria-labelledby={`${ids}-heading`}>
      <header className="capture-head">
        <h2 className="capture-title" id={`${ids}-heading`}>
          {CAPTURE_COPY.panelHeading}
        </h2>
        <p className="capture-sub">{CAPTURE_COPY.panelIntro}</p>
      </header>

      {/* Primary ONLY while collapsed — it is the one control on screen then.
          Once open, "Close Capture" is a secondary act (I2). */}
      <button
        type="button"
        className={primaryClass(!open)}
        aria-expanded={open}
        aria-controls={`${ids}-body`}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? CAPTURE_COPY.entryClose : CAPTURE_COPY.entryOpen}
      </button>

      {!open ? null : (
      <div id={`${ids}-body`}>
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>

      {error !== null && (
        <p className="capture-error" role="alert">
          {error}
          {retryTag !== null && (
            <>
              {' '}
              <button
                type="button"
                className={`${primaryClass(showErrorPrimary)} capture-error-retry`}
                onClick={retryAction}
              >
                {CAPTURE_COPY.tryAgain}
              </button>
            </>
          )}
        </p>
      )}

      {guidanceOpen ? (
        <div className="capture-guidance" id={guidanceId}>
          <h3 className="capture-guidance-title">{CAPTURE_COPY.guidanceHeading}</h3>
          <p className="capture-guidance-lead">{CAPTURE_GUIDANCE_SENTENCE}</p>
          <p className="capture-guidance-label">For example, saying:</p>
          <blockquote className="capture-guidance-example">
            {CAPTURE_GUIDANCE_EXAMPLE.spoken}
          </blockquote>
          <p className="capture-guidance-label">is read as:</p>
          <ul className="capture-guidance-list">
            {CAPTURE_GUIDANCE_EXAMPLE.reads.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="capture-guidance-keeps">
            The rest — “{CAPTURE_GUIDANCE_EXAMPLE.keeps}” — is stored with the record
            as a note. Nothing you say is discarded.
          </p>
          <p className="capture-guidance-mechanism">{CAPTURE_COPY.guidanceMechanism}</p>
          <p className="capture-guidance-storage">{CAPTURE_COPY.guidanceStorageNote}</p>
          <button type="button" className="btn btn-secondary" onClick={dismissGuidance}>
            {CAPTURE_COPY.guidanceDismiss}
          </button>
        </div>
      ) : (
        // No `aria-controls`: the element carrying `guidanceId` is UNMOUNTED in
        // this branch, and pointing at an id that is not in the document is a
        // dangling reference an assistive technology cannot follow. `aria-expanded`
        // alone is correct and sufficient here.
        <button
          type="button"
          className="capture-guidance-reopen"
          aria-expanded={false}
          onClick={() => setGuidanceOpen(true)}
        >
          {CAPTURE_COPY.guidanceReopen}
        </button>
      )}

      {/* ---- voice ---- */}
      <div className="capture-voice">
        <h3 className="capture-subhead">{CAPTURE_COPY.voiceHeading}</h3>
        <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {voiceLive}
        </p>
        {/*
          THE SEAM STATUS IS OUTSIDE THE RECORDER BRANCH AND RENDERED ON BOTH
          BRANCHES. A browser with no recorder — including every test environment
          — must still say whether this deployment can transcribe at all, which is
          a fact about the DEPLOYMENT, not about this browser.

          `data-configured="unreported"` rather than `"false"`: the three states
          are not the same claim, and a test that could not tell them apart would
          let a regression rename one into the other.
        */}
        {transcription !== null ? (
          <p className="capture-seam" data-configured={String(transcription.configured)}>
            <span className="capture-seam-label">Transcription:</span>{' '}
            {transcription.reason}
          </p>
        ) : (
          <p className="capture-seam" data-configured="unreported">
            {CAPTURE_COPY.voiceSeamUnreported}
          </p>
        )}
        {voice === 'unsupported' ? (
          <p className="capture-note">{CAPTURE_COPY.voiceUnsupported}</p>
        ) : (
          <>
            <p className="capture-note">{CAPTURE_COPY.voiceAudioHandling}</p>
            <div className="capture-voice-controls">
              {voice === 'idle' && (
                <button
                  type="button"
                  className={primaryClass(showVoicePrimary)}
                  onClick={startRecording}
                  disabled={formLocked}
                >
                  {CAPTURE_COPY.voiceRecord}
                </button>
              )}
              {voice === 'requesting-permission' && (
                <button
                  type="button"
                  className={primaryClass(showVoicePrimary)}
                  disabled
                  aria-busy="true"
                >
                  {CAPTURE_COPY.voiceRequesting}
                </button>
              )}
              {voice === 'recording' && (
                <>
                  <button
                    type="button"
                    className={primaryClass(showVoicePrimary)}
                    onClick={stopRecording}
                    disabled={formLocked}
                  >
                    {CAPTURE_COPY.voiceStop}
                  </button>
                  {/*
                    m5, INDEPENDENT REVIEW OF PR-D — NOT `aria-hidden` ANY MORE.
                    The one-shot live announcement on entering `recording`
                    ("Recording. Audio is being held in this tab.") never repeats
                    as the clock ticks — that would be noise — but a screen-reader
                    user who tabs to or reads this element AFTER that moment used
                    to find nothing here at all: `aria-hidden="true"` removed both
                    the state and the elapsed time from the accessibility tree.
                    The text now names both, so navigating to it answers "am I
                    still recording, and for how long" without waiting for a live
                    region that already fired once.
                  */}
                  <span className="capture-elapsed">
                    Recording · {formatElapsed(elapsedSec)}
                  </span>
                </>
              )}
              {voice === 'held' && (
                <>
                  <button
                    type="button"
                    className={primaryClass(showVoicePrimary)}
                    onClick={focusTranscript}
                    disabled={formLocked}
                  >
                    {CAPTURE_COPY.voiceTypeWhatWasSaid}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={requestTranscript}
                    disabled={formLocked || busyKind !== null}
                  >
                    {CAPTURE_COPY.voiceTranscribe}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={discardAudio}
                    disabled={formLocked}
                  >
                    {CAPTURE_COPY.voiceDiscard}
                  </button>
                </>
              )}
              {voice === 'permission-denied' && (
                <>
                  <button
                    type="button"
                    className={primaryClass(showVoicePrimary)}
                    onClick={focusTranscript}
                    disabled={formLocked}
                  >
                    {CAPTURE_COPY.voiceTypeWhatWasSaid}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={startRecording}
                    disabled={formLocked}
                  >
                    {CAPTURE_COPY.voiceTryAgain}
                  </button>
                </>
              )}
            </div>
            {/*
              I8, INDEPENDENT REVIEW OF PR-D — PLAIN TEXT, NOT A SECOND LIVE
              REGION. `role="alert"` carries an IMPLICIT `aria-live="assertive"`,
              so this used to announce the same sentence `voiceLive` (above) had
              already announced — twice, from two regions, for one event. The
              sentence is now said ONCE, through the ordinary status region, and
              this paragraph is plain, persistent, readable content: a sighted
              reader still sees it immediately, and a screen-reader user reaches
              it by navigating the page, exactly as they would any other text.
            */}
            {voice === 'permission-denied' && (
              <p className="capture-note capture-note-warn">
                {voiceDenialCopy(voiceDenialReason ?? 'unknown')}
              </p>
            )}
            {refusal !== null && (
              <div className="capture-refusal" role="alert">
                <p className="capture-refusal-message">{refusal.message}</p>
                <p className="capture-guidance-label">Missing:</p>
                <ul className="capture-guidance-list">
                  {refusal.missing.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <p className="capture-note">{CAPTURE_COPY.voiceAfterRefusal}</p>
                <p className="capture-note">
                  Recorded in <code>{refusal.decision_reference}</code>.
                </p>
              </div>
            )}
          </>
        )}
      </div>

      {/*
        ---- run + transcript ----

        I3a, INDEPENDENT REVIEW OF PR-D — A REAL `<form>`, SO THE IN-FLIGHT GUARD
        INSIDE `finalize()` IS WHAT A TEST (AND A REAL DOUBLE-SUBMIT) EXERCISES.
        `fireEvent.click` on a `disabled` button never dispatches in a browser or
        in jsdom, so a test driving the button alone can only ever prove the
        DISABLED ATTRIBUTE stops a second submit — not the `busyKind !== null`
        guard at the top of `finalize()` itself. `fireEvent.submit(form)` calls
        `onSubmit` directly, bypassing the button's disabled state exactly as a
        stray double Enter-press or a re-entrant call would, which is what makes
        the guard the thing under test. The button's own `disabled` attribute is
        UNCHANGED and still the first line of defence for an ordinary click.
      */}
      <form
        className="capture-form"
        onSubmit={(event) => {
          event.preventDefault();
          void finalize();
        }}
      >
        {runs.length === 0 ? (
          <>
            {/*
              m3, INDEPENDENT REVIEW OF PR-D — NOT A `<label htmlFor>` HERE. The
              select this label named does not exist in the empty-run state, so
              `htmlFor={runId}` pointed at an id nothing on screen carried — a
              dangling reference an assistive technology cannot follow. Plain
              text, same visual class, no association to break.
            */}
            <p className="capture-label">{CAPTURE_COPY.runLabel}</p>
            <p className="capture-run-empty" id={`${runId}-hint`}>
              {CAPTURE_COPY.runEmptyPrefix}{' '}
              {/*
                m2, INDEPENDENT REVIEW OF PR-D — A REAL BUTTON, TOKEN-STYLED. This
                used to be link-styled text on `--text-link`/`--text-body`, which
                this design system does not declare as buttons ever use — see
                `transcriptCapture.css`. It is now `.btn.btn-secondary`, the same
                idiom every other secondary control on this panel uses, sized
                down to sit inline in the sentence.
              */}
              <button
                type="button"
                className="btn btn-secondary capture-run-empty-create"
                onClick={createRun}
                disabled={formLocked || busyKind !== null}
              >
                {CAPTURE_COPY.runCreate}
              </button>
              {CAPTURE_COPY.runEmptySuffix}
            </p>
          </>
        ) : (
          <>
            <label className="capture-label" htmlFor={runId}>
              {CAPTURE_COPY.runLabel}
            </label>
            <select
              id={runId}
              ref={runSelectRef}
              className="capture-control"
              value={selectedRun}
              aria-describedby={`${runId}-hint ${runId}-target`}
              disabled={formLocked}
              onChange={(event) => setSelectedRun(event.target.value)}
            >
              <option value="">{CAPTURE_COPY.runPlaceholder}</option>
              {runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.label}
                </option>
              ))}
            </select>
            <p className="capture-hint" id={`${runId}-hint`}>
              {CAPTURE_COPY.runHint}
            </p>
          </>
        )}
        <p className="capture-hint" id={`${runId}-target`}>
          {selectedRunLabel !== null
            ? CAPTURE_COPY.runTargetsRun(selectedRunLabel)
            : CAPTURE_COPY.runTargetsNone}
        </p>

        <label className="capture-label" htmlFor={transcriptId}>
          {CAPTURE_COPY.transcriptLabel}
        </label>
        <textarea
          id={transcriptId}
          ref={transcriptRef}
          className="capture-control capture-textarea"
          rows={6}
          value={text}
          aria-describedby={`${transcriptId}-hint`}
          disabled={formLocked}
          onChange={(event) => setText(event.target.value)}
        />
        <p className="capture-hint" id={`${transcriptId}-hint`}>
          {CAPTURE_COPY.transcriptHint} {CAPTURE_COPY.finalizeHint}
        </p>
        <button
          type="submit"
          className={primaryClass(showFinalizePrimary)}
          disabled={busyKind !== null || text.trim() === ''}
          aria-busy={busyKind === 'finalize'}
        >
          {busyKind === 'finalize' ? 'Reading…' : CAPTURE_COPY.finalize}
        </button>
        {/* BELOW Finalize, quiet and right-aligned: this is the destructive-of-typing
            branch and must never sit where the primary action is expected. Closing the
            panel still keeps the text — that behaviour is deliberate (see the reset
            effect above) and this control is the explicit act it was missing, not a
            reason to make closing destructive. */}
        <DiscardStaged
          staged={hasStagedCapture && !formLocked}
          copy={discardCopy}
          onDiscard={discardStagedCapture}
          onAnnounce={setAnnouncement}
          onFocusAfterDiscard={() => transcriptRef.current?.focus()}
        />
      </form>

      {/* ---- proposals-ready: a compact summary, not the old inline candidate list ---- */}
      {reading !== null && !formLocked && (
        <div className="capture-reading">
          <h3 className="capture-subhead">{CAPTURE_COPY.summaryHeading}</h3>
          {reading.candidates.length === 0 ? (
            <p className="capture-note">{CAPTURE_COPY.candidatesEmpty}</p>
          ) : (
            <>
              <p className="capture-summary-line">
                {CAPTURE_COPY.summaryStored(proposalsStored, notesStored)}
              </p>
              {unproposableCount > 0 && (
                <>
                  <p className="capture-note">
                    {CAPTURE_COPY.summaryUnproposable(unproposableCount)}
                  </p>
                  {/* m4: h4 — a SUBSECTION of "What This Reading Stored" (h3)
                      above, not a sibling of it. */}
                  <h4 className="capture-subhead">{CAPTURE_COPY.unproposableHeading}</h4>
                  <ul className="capture-outcomes">
                    {reading.unproposable.map((entry) => (
                      <li key={`${entry.field_path}-${entry.candidate_index}`}>
                        <strong>{entry.field_path}</strong> — {entry.message}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
          {/*
            CAPTURE ANOTHER NOTE STAYS OFFERED EVEN WHEN NOTHING WAS PROPOSED —
            it was nested inside the `candidates.length > 0` branch above and was
            therefore UNREACHABLE on an all-prose reading (every word stored as a
            note, nothing recognised as a value): a scientist who dictated a note
            with no extractable value had no way back to a fresh box short of
            closing and reopening the whole panel. Found taking this slice's own
            screenshots. `reviewProposals` alone stays conditional — there is
            nothing to review when nothing was proposed.
          */}
          <div className="capture-reading-actions">
            {proposalsStored > 0 && (
              <button
                type="button"
                className={primaryClass(showReadingPrimary)}
                onClick={reviewProposals}
              >
                {CAPTURE_COPY.reviewProposals(proposalsStored)}
              </button>
            )}
            <button
              type="button"
              className={primaryClass(showReadingPrimary && proposalsStored === 0)}
              onClick={captureAnother}
            >
              {CAPTURE_COPY.captureAnother}
            </button>
          </div>

          {reading.review_required.length > 0 && (
            <>
              <h4 className="capture-subhead">{CAPTURE_COPY.reviewHeading}</h4>
              <ul className="capture-outcomes">
                {reading.review_required.map((entry) => (
                  <li key={entry.field_path} data-outcome={entry.outcome}>
                    <span className="capture-outcome-tag">Needs review</span>{' '}
                    <strong>{entry.field_path}</strong> — {entry.reason}
                  </li>
                ))}
              </ul>
            </>
          )}

          {reading.clarifications.length > 0 && (
            <>
              <h4 className="capture-subhead">{CAPTURE_COPY.clarificationsHeading}</h4>
              <ul className="capture-outcomes">
                {reading.clarifications.map((entry, index) => (
                  <li key={`${entry.kind}-${index}`} data-outcome={entry.outcome}>
                    <span className="capture-outcome-tag">Question</span> {entry.question}
                    {entry.quote !== null && (
                      <span className="capture-outcome-quote"> “{entry.quote}”</span>
                    )}
                    {entry.options.length > 0 && (
                      <ul className="capture-outcome-options">
                        {entry.options.map((option) => (
                          <li key={option.run_id}>{option.label}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}

          {reading.abstentions.length > 0 && (
            <>
              <h4 className="capture-subhead">{CAPTURE_COPY.abstentionsHeading}</h4>
              <ul className="capture-outcomes">
                {reading.abstentions.map((entry, index) => (
                  <li key={`${entry.kind}-${index}`} data-outcome={entry.outcome}>
                    <span className="capture-outcome-tag">Not proposed</span>{' '}
                    <span className="capture-outcome-quote">“{entry.quote}”</span> —{' '}
                    {entry.reason}
                  </li>
                ))}
              </ul>
            </>
          )}

          <h4 className="capture-subhead">{CAPTURE_COPY.notesHeading}</h4>
          <p className="capture-note">{CAPTURE_COPY.notesNote}</p>
          <ul className="capture-stored">
            {reading.notes.map((note) => (
              <li key={note.id}>{note.text}</li>
            ))}
          </ul>

          <h4 className="capture-subhead">{CAPTURE_COPY.retentionHeading}</h4>
          <p className="capture-note">{reading.capture.retention.description}</p>
          <p className="capture-note">{reading.capture.retention.raw_audio.reason}</p>
          <ul className="capture-outcomes">
            {reading.capture.retention.not_implemented.map((entry) => (
              <li key={entry.state}>
                <span className="capture-outcome-tag">Not offered</span>{' '}
                <strong>{entry.state}</strong> — {entry.reason}
              </li>
            ))}
          </ul>
          <p className="capture-note">
            {/* THE SERVER'S OWN SENTENCE AND THE SERVER'S OWN ROUTE. Neither the
                method nor the path is transcribed here — a second copy in this
                bundle would be free to drift from the operation that enforces it. */}
            {reading.accept_contract.message} Accepting one happens through{' '}
            <code>
              {reading.accept_contract.method} {reading.accept_contract.path}
            </code>
            , which is what the Ingestion Proposals surface calls.
          </p>
        </div>
      )}
      </div>
      )}
    </section>
  );
}

export default TranscriptCapturePanel;

/*
 * Transcript capture — the scientist workflow, and a voice surface that tells the
 * truth about itself.
 *
 * THE ORDER OF THE CONTROLS IS THE ORDER OF THE WORKFLOW, and it is not a layout
 * preference: choose the run, write or dictate the notes, finalize them, read what
 * was proposed and what was stored. ~~accept one at a time~~ — the last step USED to
 * be "accept one at a time" and it is struck rather than deleted because the
 * paragraph two below explains why that control is gone; accepting now happens on
 * the proposals surface, not here. A control that appears before the step it belongs
 * to invites the step to be skipped.
 *
 * THREE THINGS THIS COMPONENT WILL NOT DO
 * =======================================
 *
 * **It never reads unfinished text.** There is no debounce, no timer, no
 * `onChange` that calls the server. `captureTranscript` is reachable from exactly
 * one button, and the server refuses a body without `finalized: true` in any case.
 *
 * **It never writes a value by itself, and it no longer accepts one either.**
 * This paragraph used to read: "Accepting a proposal calls `api.updateRun` — the
 * existing confirmed-edit path, with the RUN's own `If-Match` — from a control the
 * reader activated." That control is GONE. It was correct while a candidate lived
 * only in this component's state, and it is the thing that made a candidate perish
 * on navigation: the value could only be accepted by the one tab holding it, and
 * a colleague could not see it at all.
 *
 * Finalizing now mints a DURABLE ingestion proposal per candidate, server-side,
 * in the same lock and the same save as the notes. This panel therefore lists what
 * was stored and says where it is reviewed; it calls no write path of its own, so
 * the claim above is now structural rather than a promise about one function. The
 * separate proposals surface is where a person accepts or rejects — which is also
 * what makes a rejection a recorded act instead of a click nobody else can see.
 *
 * **It never claims a capability the deployment does not have.** The transcription
 * status is rendered from `GET /api/providers/capabilities` and from the refusal
 * body the transcription operation returns — both produced by the process that
 * would do the work. There is no hardcoded "not configured" string, because a
 * string in this bundle describes the build the browser came from and not the
 * deployment it is talking to. There is no "Connected", no "Ready", and no
 * spinner that outlives a refusal.
 *
 * AUDIO NEVER LEAVES THE TAB, AND THE UI SAYS SO RATHER THAN IMPLYING IT.
 * `MediaRecorder` chunks are held in a ref, counted only to build the opaque
 * handle below — the count is NOT rendered, and an earlier version of this line
 * said "counted for the reader", which was not true of anything on screen — and
 * dropped on discard, on close, on record change, and on unmount. The drop
 * detaches `ondataavailable` BEFORE calling `stop()`, because `stop()` emits its
 * last chunk asynchronously and would otherwise refill a buffer the live region
 * had just announced as empty. Nothing serialises them, nothing
 * puts them in a request body, and there is no upload endpoint in this
 * application for them to reach. The one request that mentions audio sends an
 * opaque handle — a string this component minted — and never the audio.
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
import type {
  ApiProviderCapabilities,
  ApiProviderRefusal,
  ApiRunView,
  ApiTranscriptCapture,
  ApiTranscriptMintedProposal,
  ApiTranscriptUnproposable,
} from '../lib/types';
import { DiscardStaged } from './DiscardStaged';
import { DISCARD_COPY } from '../lib/discardContent';
import './transcriptCapture.css';

type VoiceState = 'unsupported' | 'idle' | 'recording' | 'held';

/*
 * THE FALLBACK SENTENCE FOR EACH FAILURE, and each one states WHAT WAS NOT DONE.
 *
 * `mutationFailureCopy` handles the cases it can name (a sign-in page returned in
 * place of the API, a 401, a 403) and returns this otherwise. A generic "something
 * went wrong" would leave the reader unable to tell whether their transcript was
 * stored, which is the one question that matters here.
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

/** A proposal rendered for a human. Never `[object Object]`, never invented. */
function displayValue(value: unknown): string {
  if (value === null) return '(cleared)';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

export function TranscriptCapturePanel({ experimentId }: { experimentId: string }) {
  const ids = useId();
  const transcriptId = `${ids}-transcript`;
  const runId = `${ids}-run`;
  const guidanceId = `${ids}-guidance`;

  /*
   * THE PANEL IS CLOSED UNTIL A READER OPENS IT, AND IT FETCHES NOTHING WHILE
   * CLOSED. Two reasons, and the second is the load-bearing one.
   *
   * Starting a capture is a deliberate act, so a control that says "start one" is
   * a truer surface than a form that is always half-filled. And a record screen
   * already issues a bundle of reads on mount; a section that quietly added two
   * more — a run listing and a capability report — would change the request
   * pattern of every screen it appears on, for readers who never dictate
   * anything. `ValidateReview` on the same screen took the same decision for the
   * same reason.
   */
  const [open, setOpen] = useState(false);
  const [guidanceOpen, setGuidanceOpen] = useState<boolean>(() => !isCaptureGuidanceSeen());
  const [capabilities, setCapabilities] = useState<ApiProviderCapabilities | null>(null);
  const [runs, setRuns] = useState<ApiRunView[]>([]);
  const [experimentVersion, setExperimentVersion] = useState('');
  const [selectedRun, setSelectedRun] = useState('');
  const [text, setText] = useState('');
  const [reading, setReading] = useState<ApiTranscriptCapture | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState<string>('');

  const [voice, setVoice] = useState<VoiceState>('idle');
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const [voiceLive, setVoiceLive] = useState<string>(CAPTURE_COPY.voiceIdleLive);
  const [refusal, setRefusal] = useState<ApiProviderRefusal | null>(null);
  const [heldChunks, setHeldChunks] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const transcriptRef = useRef<HTMLTextAreaElement | null>(null);
  const runSelectRef = useRef<HTMLSelectElement | null>(null);

  /* ---- audio lifecycle. Everything here DROPS audio; nothing sends it. ---- */

  const dropAudio = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder) {
      // DETACH THE HANDLER BEFORE STOPPING, and this ordering is the whole fix.
      //
      // `MediaRecorder.stop()` emits its final `dataavailable` ASYNCHRONOUSLY, on
      // a later task. The handler closes over the stable `chunksRef`, so the
      // previous version — which cleared the array, then called `stop()`, then
      // nulled `recorderRef` — announced "Audio discarded." to the live region
      // and then had the complete recording pushed straight back into the buffer
      // a tick later. Nulling the ref does not unbind a DOM event handler.
      //
      // The blob never left the tab either way (no request has ever carried it;
      // `requestTranscript` sends only an opaque `held-in-tab:<n>` handle), so
      // this was a retention and honesty defect rather than an exfiltration one
      // — the UI stated the audio was gone while it sat in memory for the rest
      // of the session with no control that could clear it.
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
    // Cleared AFTER the handler is detached, so nothing can repopulate it.
    chunksRef.current = [];
    setHeldChunks(0);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  // Unmount and record change both drop audio. Leaving a record must not leave a
  // live microphone or a buffer behind, and the panel says the audio is gone.
  useEffect(() => () => dropAudio(), [dropAudio]);

  /*
   * CLOSING THE PANEL RELEASES THE MICROPHONE.
   *
   * The unmount cleanup above is not enough: "Close capture" does not unmount
   * this component, it only stops rendering the body — and the Stop button, the
   * Discard button and the recording live region all live inside that body. So
   * closing mid-recording left `getUserMedia` tracks and a running
   * `MediaRecorder` alive with NO ISAAC-visible indicator and no way to stop
   * until the panel was reopened. The browser's own tab indicator would be the
   * only sign a scientist had that the microphone was still on.
   *
   * `dropAudio` is stable (`useCallback(…, [])`), so this effect fires exactly on
   * the open→closed transition and never spuriously.
   *
   * Deliberately NOT paired with anything that clears `text`: releasing the
   * microphone and discarding typed words are different acts, and only the first
   * belongs here. See the reset effect below.
   */
  useEffect(() => {
    if (!open) dropAudio();
  }, [open, dropAudio]);

  useEffect(() => {
    if (!audioRecordingAvailable()) setVoice('unsupported');
  }, []);

  /* ---- reads ------------------------------------------------------------- */

  const loadRuns = useCallback(async () => {
    const listed = await api.listRuns(experimentId);
    setRuns(listed.runs);
    setExperimentVersion(listed.experiment_version);
  }, [experimentId]);

  /*
   * RESETTING IS KEYED ON THE RECORD, NEVER ON THE PANEL BEING OPENED.
   *
   * These four setters used to sit at the top of the fetch effect below, whose
   * deps include `open` — and they ran BEFORE its `if (!open) return` guard. So
   * "Close capture" wiped the box. A scientist who typed several paragraphs and
   * then collapsed the panel to scroll, or hit the toggle by accident, lost every
   * word: finalize had not been pressed, so nothing had reached the server, and
   * there was nothing to recover from.
   *
   * That is the "scientist-entered text is never silently discarded" claim being
   * false, and it is the fourth path the three negative controls missed — they
   * cover empty candidates, a 412 on accept and a 412 on finalize, all real, and
   * none involving the toggle. It also contradicted this component's own
   * reasoning further down, that clearing the box "would make a reader who wants
   * to correct a sentence retype the lot".
   *
   * Changing RECORDS is a different matter and genuinely must reset: the runs,
   * the candidates and the text all belong to the record that was open.
   */
  useEffect(() => {
    setReading(null);
    setSelectedRun('');
    setText('');
    /* `decisions` and `edits` were reset here too and are GONE rather than left as
       dead setters: both existed for the in-panel Accept control, which no longer
       exists. The `edits` entry in particular was a review fix — it survived a record
       change and made the Discard trigger offer to clear something the reader could
       not see — so it is recorded here that the leak was closed by deleting the state,
       not by forgetting the fix. */
  }, [experimentId]);

  useEffect(() => {
    let live = true;
    if (!open) return undefined;
    loadRuns().catch((cause: unknown) => {
      if (live) setError(mutationFailureCopy(cause, FALLBACK.runs));
    });
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
  }, [experimentId, loadRuns, open]);

  const transcription = useMemo(
    () => capabilities?.seams.find((seam) => seam.seam === 'transcription') ?? null,
    [capabilities],
  );

  /* ---- voice ------------------------------------------------------------- */

  async function startRecording() {
    setVoiceNotice(null);
    setRefusal(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
    } catch {
      // NAMES NO CAUSE BEYOND WHAT IS KNOWN. A refusal and an absent device are
      // indistinguishable from here, and both mean the same thing to the reader.
      dropAudio();
      setVoice('idle');
      setVoiceNotice(CAPTURE_COPY.voicePermissionRefused);
      setVoiceLive(CAPTURE_COPY.voiceIdleLive);
    }
  }

  function stopRecording() {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setVoice('held');
    setVoiceLive(CAPTURE_COPY.voiceHeldLive);
  }

  function discardAudio() {
    dropAudio();
    setVoice('idle');
    setRefusal(null);
    setVoiceLive(CAPTURE_COPY.voiceDiscardedLive);
  }

  async function requestTranscript() {
    setBusy(true);
    setRefusal(null);
    setVoiceNotice(null);
    try {
      // AN OPAQUE HANDLE, MINTED HERE, NAMING AUDIO THIS TAB HOLDS. No bytes, no
      // blob, no object URL that a server could dereference — the handle is
      // meaningful only to a provider that this deployment would have to be
      // configured with, and there is none.
      const result = await api.requestTranscription({ audioRef: `held-in-tab:${heldChunks}` });
      setText(result.text);
      transcriptRef.current?.focus();
    } catch (cause: unknown) {
      const stated = providerRefusalOf(cause);
      if (stated) {
        setRefusal(stated);
        // Focus moves to the text the reader can still use, so the refusal is not
        // a dead end for somebody working by keyboard.
        transcriptRef.current?.focus();
      } else {
        setError(mutationFailureCopy(cause, FALLBACK.transcription));
      }
    } finally {
      setBusy(false);
    }
  }

  /* ---- finalize ---------------------------------------------------------- */

  async function finalize() {
    setBusy(true);
    setError(null);
    try {
      const payload = await api.captureTranscript(experimentId, {
        experimentVersion,
        text,
        ...(selectedRun ? { runId: selectedRun } : {}),
      });
      setReading(payload);
      setExperimentVersion(payload.experiment_version);
      // The transcript stays in the box on purpose. It is stored with the record
      // either way, and clearing it would make a reader who wants to correct a
      // sentence retype the lot.
      //
      // THE ANNOUNCEMENT COUNTS WHAT WAS STORED, NOT WHAT WAS READ, and the two can
      // differ: a candidate the server could not turn into a proposal is reported
      // under `unproposable`, and saying "2 proposed" over one stored proposal would
      // be the panel claiming an act the server declined. Both numbers are said.
      setAnnouncement(
        `Finalized. ${payload.capture.segments} segment(s) stored with this record, ` +
          `${payload.candidates.length} value(s) read, ` +
          `${payload.proposals.length} stored as proposal(s) for review.`,
      );
      await loadRuns();
    } catch (cause: unknown) {
      setError(mutationFailureCopy(cause, FALLBACK.finalize));
      if (cause instanceof ApiError && cause.status === 412) await loadRuns();
    } finally {
      setBusy(false);
    }
  }

  /* ---- what the capture stored ------------------------------------------- */

  /*
   * THERE IS NO ACCEPT, REJECT, EDIT OR UNDO HERE ANY MORE, AND NO WRITE PATH AT
   * ALL. `writeField`, `accept`, `reject` and `undo` all lived here and all called
   * `api.updateRun`; between them they were the only way to act on a candidate, and
   * they were reachable from exactly one tab, for exactly as long as that tab stayed
   * on this screen.
   *
   * The server now stores a durable proposal per candidate in the same save as the
   * notes, so acting on one is the proposals surface's job — where the act is
   * recorded, a rejection has a reason, and a colleague can see the queue. This
   * section is READ-ONLY: it pairs each candidate with what the server said it did
   * with it, and nothing below issues a request.
   *
   * A SEPARATE SLICE REBUILDS THIS PANEL'S INTERACTION. What is here is the minimum
   * that is TRUE — deliberately not a redesign, because a redesign made in the same
   * change as a contract move is a redesign nobody can review against the contract.
   */

  const mintedByCandidate = useMemo(() => {
    const map = new Map<number, ApiTranscriptMintedProposal>();
    for (const entry of reading?.proposals ?? []) map.set(entry.candidate_index, entry);
    return map;
  }, [reading]);

  const unproposableByCandidate = useMemo(() => {
    const map = new Map<number, ApiTranscriptUnproposable>();
    for (const entry of reading?.unproposable ?? []) map.set(entry.candidate_index, entry);
    return map;
  }, [reading]);


  async function createRun() {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createRun(experimentId, { experimentVersion });
      setExperimentVersion(created.experiment_version);
      await loadRuns();
      setSelectedRun(created.run.id);
      runSelectRef.current?.focus();
      setAnnouncement(`Created ${created.run.label}. It is now selected.`);
    } catch (cause: unknown) {
      setError(mutationFailureCopy(cause, FALLBACK.createRun));
    } finally {
      setBusy(false);
    }
  }

  function dismissGuidance() {
    markCaptureGuidanceSeen();
    setGuidanceOpen(false);
    transcriptRef.current?.focus();
  }

  /* ---- discard (typed input only; no request, ever) ----------------------- */

  /*
   * WHAT THE DISCARD CONTROL REACHES, AND — MORE IMPORTANTLY — WHAT IT DOES NOT.
   *
   * It clears `text` and `edits`. Both are things a person typed into a box on this
   * screen and never sent: `text` is read only when Finalize is pressed, and an `edits`
   * entry is a value typed over a proposal that has not been accepted.
   *
   * IT DELIBERATELY DOES NOT CLEAR `reading` OR `decisions`, and that is a decision
   * against the obvious "discard everything":
   *
   *   * `reading` is the SERVER'S ANSWER to a finalize — the proposals, the
   *     clarifications, the notes it stored. It is data that arrived, not a draft that
   *     was typed. Clearing it would hide the panel's own record of what was stored
   *     with the record moments earlier, which is the disclosure a reader most needs
   *     at exactly that moment.
   *
   * IT USED TO REACH `edits` TOO, AND `edits` IS GONE — with the Accept control it
   * belonged to. Two review fixes lived on that map (it survived a record change, and
   * it outlived the row that rendered it, both leaving Discard offering to clear
   * something invisible); they are recorded here rather than dropped, because the
   * defect they closed is a property of "offer a control only for state the reader can
   * see", not of that one map. `text` is now the whole of what Discard reaches, so the
   * predicate is the plainest form of that rule.
   *
   * The copy branches on the same condition for the same reason: once a finalize has
   * landed, the words ARE stored with the record as notes, and a sentence saying
   * nothing has been sent would be false. See `lib/discardContent.ts`.
   */
  const hasStagedCapture = text !== '';
  const discardCopy =
    reading === null ? DISCARD_COPY.transcriptUnsent : DISCARD_COPY.transcriptAfterFinalize;
  const discardStagedCapture = () => {
    setText('');
  };

  /* ---- render ------------------------------------------------------------ */

  return (
    <section className="capture-section" aria-labelledby={`${ids}-heading`}>
      <header className="capture-head">
        <h2 className="capture-title" id={`${ids}-heading`}>
          {CAPTURE_COPY.panelHeading}
        </h2>
        <p className="capture-sub">{CAPTURE_COPY.panelIntro}</p>
      </header>

      <button
        type="button"
        className="btn btn-secondary"
        aria-expanded={open}
        aria-controls={`${ids}-body`}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? CAPTURE_COPY.close : CAPTURE_COPY.start}
      </button>

      {!open ? null : (
      <div id={`${ids}-body`}>
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>

      {error !== null && (
        <p className="capture-error" role="alert">
          {error}
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
          THE SEAM STATUS IS OUTSIDE THE RECORDER BRANCH, and that is a
          correction rather than a layout choice. It was inside it, so a browser
          with no recorder — which includes every test environment — showed the
          audio controls' absence and said NOTHING about whether the deployment
          could transcribe at all. Those are two different facts about two
          different things, and the reader is entitled to both.
        */}
        {/*
          AND IT IS RENDERED ON BOTH BRANCHES NOW. The `!== null` guard meant the
          disclosure was conditional on the very thing it discloses: `transcription` is
          `null` while the capabilities fetch is in flight, after it rejects, and when
          the report names no such seam — and in all three the controls below rendered
          with nothing said about whether this deployment can transcribe. The D6
          supersession's whole argument is that the mitigation here is disclosure rather
          than prevention, "the seam's status renders ABOVE the controls, before any
          recording starts"; that was false in the exact window in which a reader
          decides whether to press Start.

          `data-configured="unreported"` rather than `"false"`: the three states are not
          the same claim, and a test that could not tell them apart would let a
          regression rename one into the other. See `voiceSeamUnreported` for why this
          says UNKNOWN and not "not configured".
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
              {voice === 'recording' ? (
                <button type="button" className="btn btn-secondary" onClick={stopRecording}>
                  {CAPTURE_COPY.voiceStop}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={startRecording}
                  disabled={busy}
                >
                  {CAPTURE_COPY.voiceRecord}
                </button>
              )}
              <button
                type="button"
                className="btn btn-secondary"
                onClick={requestTranscript}
                disabled={busy || voice !== 'held'}
              >
                {CAPTURE_COPY.voiceTranscribe}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={discardAudio}
                disabled={voice === 'idle'}
              >
                {CAPTURE_COPY.voiceDiscard}
              </button>
            </div>
            {voiceNotice !== null && (
              <p className="capture-note capture-note-warn" role="alert">
                {voiceNotice}
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

      {/* ---- run + transcript ---- */}
      <div className="capture-form">
        <label className="capture-label" htmlFor={runId}>
          {CAPTURE_COPY.runLabel}
        </label>
        <select
          id={runId}
          ref={runSelectRef}
          className="capture-control"
          value={selectedRun}
          aria-describedby={`${runId}-hint`}
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
        <button
          type="button"
          className="btn btn-secondary"
          onClick={createRun}
          disabled={busy}
        >
          {CAPTURE_COPY.runCreate}
        </button>

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
          onChange={(event) => setText(event.target.value)}
        />
        <p className="capture-hint" id={`${transcriptId}-hint`}>
          {CAPTURE_COPY.transcriptHint} {CAPTURE_COPY.finalizeHint}
        </p>
        <button
          type="button"
          className="btn btn-primary"
          onClick={finalize}
          disabled={busy || text.trim() === ''}
        >
          {CAPTURE_COPY.finalize}
        </button>
        {/* BELOW Finalize, quiet and right-aligned: this is the destructive-of-typing
            branch and must never sit where the primary action is expected. Closing the
            panel still keeps the text — that behaviour is deliberate (see the reset
            effect above) and this control is the explicit act it was missing, not a
            reason to make closing destructive. */}
        <DiscardStaged
          staged={hasStagedCapture}
          copy={discardCopy}
          onDiscard={discardStagedCapture}
          onAnnounce={setAnnouncement}
          onFocusAfterDiscard={() => transcriptRef.current?.focus()}
        />
      </div>

      {reading !== null && (
        <div className="capture-reading">
          <h3 className="capture-subhead">{CAPTURE_COPY.candidatesHeading}</h3>
          <p className="capture-note">{CAPTURE_COPY.candidateNotAValue}</p>
          {/* THE BLANKET "every one of them is stored" CLAIM IS CONDITIONAL, and the
              condition is the server's own `unproposable` list being empty. Rendered
              unconditionally it stood above rows the server had just declined to
              store — reachable in production through `too_many_proposals` and
              `proposals_too_large` — asserting storage one line above the sentence
              that denied it. Each row still carries its own label either way, which
              is what the lead paragraph now describes rather than claims. */}
          {reading.unproposable.length === 0 && reading.candidates.length > 0 && (
            <p className="capture-note">{CAPTURE_COPY.candidatesAllStored}</p>
          )}
          {reading.candidates.length === 0 ? (
            <p className="capture-note">{CAPTURE_COPY.candidatesEmpty}</p>
          ) : (
            <ul className="capture-candidates">
              {reading.candidates.map((candidate, index) => {
                const minted = mintedByCandidate.get(index);
                const refused = unproposableByCandidate.get(index);
                const conflicts = reading.review_required.filter((entry) =>
                  entry.candidate_indexes.includes(index),
                );
                const conflicted = conflicts.length > 0;
                /* WHETHER "Both are stored" IS TRUE OF THIS CONFLICT, measured over
                   every candidate the conflict names rather than assumed. A conflict
                   in which one side was refused (`too_many_proposals`,
                   `proposals_too_large`) used to be told "Both are stored" anyway. */
                const conflictAllStored = conflicts.every((entry) =>
                  entry.candidate_indexes.every((other) => mintedByCandidate.has(other)),
                );
                return (
                  <li
                    className="capture-candidate"
                    key={`${candidate.field_path}-${candidate.start_char}-${index}`}
                    /* `stored` / `refused` / `unaccounted`, and never `open`. There is
                       no undecided state on this screen any more: the server has
                       already said what it did with each candidate by the time this
                       renders. */
                    data-state={minted ? 'stored' : refused ? 'refused' : 'unaccounted'}
                  >
                    <p className="capture-candidate-path">{candidate.field_path}</p>
                    <p className="capture-candidate-value">
                      {displayValue(candidate.proposed_value)}
                    </p>
                    <p className="capture-candidate-quote">“{candidate.quote}”</p>
                    <p className="capture-candidate-rule">{candidate.rule}</p>
                    {conflicted && (
                      <p className="capture-candidate-conflict">
                        {conflictAllStored
                          ? CAPTURE_COPY.conflictBothStored
                          : CAPTURE_COPY.conflictNotAllStored}
                      </p>
                    )}
                    {minted ? (
                      <p className="capture-candidate-state">
                        {minted.deduplicated
                          ? CAPTURE_COPY.proposalAlreadyStored
                          : CAPTURE_COPY.proposalStored}
                      </p>
                    ) : refused ? (
                      /* THE SERVER'S OWN SENTENCE, not one composed here. A reason
                         written in this bundle would be this client explaining a
                         refusal it did not make. */
                      <p className="capture-candidate-state">{refused.message}</p>
                    ) : (
                      /* UNREACHABLE IF THE SERVER KEEPS ITS PROMISE — every candidate
                         index appears in exactly one of the two lists — and rendered
                         anyway, because the alternative to a sentence here is a row
                         that silently says nothing about what happened to a value. */
                      <p className="capture-candidate-state">
                        {CAPTURE_COPY.proposalMissing}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          {reading.review_required.length > 0 && (
            <>
              <h3 className="capture-subhead">{CAPTURE_COPY.reviewHeading}</h3>
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
              <h3 className="capture-subhead">{CAPTURE_COPY.clarificationsHeading}</h3>
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
              <h3 className="capture-subhead">{CAPTURE_COPY.abstentionsHeading}</h3>
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

          <h3 className="capture-subhead">{CAPTURE_COPY.notesHeading}</h3>
          <p className="capture-note">{CAPTURE_COPY.notesNote}</p>
          <ul className="capture-stored">
            {reading.notes.map((note) => (
              <li key={note.id}>{note.text}</li>
            ))}
          </ul>

          <h3 className="capture-subhead">{CAPTURE_COPY.retentionHeading}</h3>
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
            {/* THE SERVER'S OWN SENTENCE AND THE SERVER'S OWN ROUTE. This panel used
                to print the contract beside an Accept button it owned; the button is
                gone and the contract is still printed, because a reader who wants to
                know where their proposal can be accepted should not have to find out
                by clicking something. Neither the method nor the path is transcribed
                here — a second copy in this bundle would be free to drift from the
                operation that enforces it. */}
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

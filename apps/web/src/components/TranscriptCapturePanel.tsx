/*
 * Transcript capture — the scientist workflow, and a voice surface that tells the
 * truth about itself.
 *
 * THE ORDER OF THE CONTROLS IS THE ORDER OF THE WORKFLOW, and it is not a layout
 * preference: choose the run, write or dictate the notes, finalize them, review
 * what was proposed, accept one at a time. A control that appears before the step
 * it belongs to invites the step to be skipped.
 *
 * THREE THINGS THIS COMPONENT WILL NOT DO
 * =======================================
 *
 * **It never reads unfinished text.** There is no debounce, no timer, no
 * `onChange` that calls the server. `captureTranscript` is reachable from exactly
 * one button, and the server refuses a body without `finalized: true` in any case.
 *
 * **It never writes a value by itself.** Accepting a proposal calls
 * `api.updateRun` — the existing confirmed-edit path, with the RUN's own
 * `If-Match` — from a control the reader activated. There is no second write
 * path here and no batch "accept all": accepting is one decision about one value,
 * and a control that made five of them at once would be a confirmation nobody
 * gave five times.
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
import { RUN_FIELDS, envelopeValue, parseRunField } from '../lib/runFields';
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
  ApiFieldCandidate,
  ApiProviderCapabilities,
  ApiProviderRefusal,
  ApiRunView,
  ApiTranscriptCapture,
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
  accept:
    'This value was NOT written to the run. The run holds what it held before, and the words behind the proposal are still stored as a note.',
  undo: 'The run was NOT changed back. It still holds the value that was accepted.',
  createRun: 'No run was created. Nothing else was changed.',
} as const;

/** One reader decision about one proposal. `previous` is what the run held before. */
interface Decision {
  state: 'accepted' | 'rejected';
  previous?: unknown;
}

/** Whether this browser can record at all. Asked, never assumed. */
function audioRecordingAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  const recorder = (window as { MediaRecorder?: unknown }).MediaRecorder;
  const devices = typeof navigator === 'undefined' ? undefined : navigator.mediaDevices;
  return typeof recorder === 'function' && typeof devices?.getUserMedia === 'function';
}

function specFor(fieldPath: string) {
  return RUN_FIELDS.find((entry) => entry.path === fieldPath);
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
  const [decisions, setDecisions] = useState<Record<number, Decision>>({});
  const [edits, setEdits] = useState<Record<number, string>>({});
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
    setDecisions({});
    setSelectedRun('');
    setText('');
    /* `edits` belongs to the CANDIDATES of the record that was open — it is keyed by
       their position in that record's proposal list — so it belongs in this reset with
       them. It was missing, and while nothing rendered the stale entries (a proposal row
       needs `reading`, and `finalize` clears the map before setting it), they were enough
       to make `hasStagedCapture` true on the next record. Found in review of the Discard
       slice, which is what first made that leak visible. */
    setEdits({});
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
      setDecisions({});
      setEdits({});
      setExperimentVersion(payload.experiment_version);
      // The transcript stays in the box on purpose. It is stored with the record
      // either way, and clearing it would make a reader who wants to correct a
      // sentence retype the lot.
      setAnnouncement(
        `Finalized. ${payload.capture.segments} segment(s) stored with this record, ` +
          `${payload.candidates.length} value(s) proposed.`,
      );
      await loadRuns();
    } catch (cause: unknown) {
      setError(mutationFailureCopy(cause, FALLBACK.finalize));
      if (cause instanceof ApiError && cause.status === 412) await loadRuns();
    } finally {
      setBusy(false);
    }
  }

  /* ---- accept / reject / undo -------------------------------------------- */

  const targetRun = useMemo(
    () => runs.find((run) => run.id === (reading?.capture.run_id ?? '')) ?? null,
    [runs, reading],
  );

  async function writeField(fieldPath: string, value: unknown) {
    if (!targetRun) throw new Error('no run');
    const written = await api.updateRun(
      experimentId,
      targetRun.id,
      { fields: { [fieldPath]: value } },
      targetRun.version,
    );
    setRuns((current) =>
      current.map((run) => (run.id === written.run.id ? written.run : run)),
    );
  }

  async function accept(index: number, candidate: ApiFieldCandidate) {
    setBusy(true);
    setError(null);
    const spec = specFor(candidate.field_path);
    const raw = edits[index];
    let value: unknown = candidate.proposed_value;
    if (spec && raw !== undefined) {
      const parsed = parseRunField(spec, raw);
      if (!parsed.ok) {
        setError(parsed.error);
        setBusy(false);
        return;
      }
      value = parsed.value;
    }
    const previous = envelopeValue(targetRun?.fields?.[candidate.field_path]);
    try {
      await writeField(candidate.field_path, value);
      setDecisions((current) => ({ ...current, [index]: { state: 'accepted', previous } }));
      setAnnouncement(`${candidate.field_path}: ${CAPTURE_COPY.accepted}`);
    } catch (cause: unknown) {
      setError(mutationFailureCopy(cause, FALLBACK.accept));
      if (cause instanceof ApiError && cause.status === 412) await loadRuns();
    } finally {
      setBusy(false);
    }
  }

  function reject(index: number, candidate: ApiFieldCandidate) {
    setDecisions((current) => ({ ...current, [index]: { state: 'rejected' } }));
    setAnnouncement(`${candidate.field_path}: ${CAPTURE_COPY.rejected}`);
  }

  async function undo(index: number, candidate: ApiFieldCandidate) {
    const decision = decisions[index];
    if (!decision || decision.state !== 'accepted') return;
    setBusy(true);
    setError(null);
    try {
      // The SAME write path, with the value the run held before — `null` clears
      // the field, which is the contract's own meaning and is what "it held
      // nothing before" honestly restores.
      await writeField(candidate.field_path, decision.previous ?? null);
      setDecisions((current) => {
        const next = { ...current };
        delete next[index];
        return next;
      });
      setAnnouncement(`${candidate.field_path}: ${CAPTURE_COPY.undone}`);
    } catch (cause: unknown) {
      setError(mutationFailureCopy(cause, FALLBACK.undo));
      if (cause instanceof ApiError && cause.status === 412) await loadRuns();
    } finally {
      setBusy(false);
    }
  }

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
   *   * `decisions` holds the Undo path for proposals that were ACCEPTED — values
   *     already written to the run through `api.updateRun`. Dropping that map would
   *     take away the only control that reverses a real write, in the name of
   *     discarding something unsent. A control that quietly removed a remedy would be
   *     doing the opposite of what it says.
   *
   * The copy branches on the same condition for the same reason: once a finalize has
   * landed, the words ARE stored with the record as notes, and a sentence saying
   * nothing has been sent would be false. See `lib/discardContent.ts`.
   */
  /*
   * `edits` COUNTS ONLY WHILE THE PROPOSALS IT EDITS ARE ON SCREEN, and the guard is a
   * review fix rather than belt-and-braces. An `edits` entry is only reachable, and only
   * rendered, from a proposal row — and those exist only while `reading !== null`. The
   * map survived a record change (the reset below did not clear it), so a reader who
   * edited a proposal on one record and moved to another met a Discard trigger over an
   * EMPTY box, offering to clear something they could not see, under the copy that says
   * "This clears the transcript box". The reset now drops the map as well; tying the
   * predicate to what is rendered is the structural half of the same fix, so the control
   * can never be offered for state the branch below is not describing.
   */
  const hasStagedCapture =
    text !== '' || (reading !== null && Object.keys(edits).length > 0);
  const discardCopy =
    reading === null ? DISCARD_COPY.transcriptUnsent : DISCARD_COPY.transcriptAfterFinalize;
  const discardStagedCapture = () => {
    setText('');
    setEdits({});
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
          {reading.candidates.length === 0 ? (
            <p className="capture-note">{CAPTURE_COPY.candidatesEmpty}</p>
          ) : (
            <ul className="capture-candidates">
              {reading.candidates.map((candidate, index) => {
                const decision = decisions[index];
                const spec = specFor(candidate.field_path);
                const conflicted = reading.review_required.some((entry) =>
                  entry.candidate_indexes.includes(index),
                );
                return (
                  <li
                    className="capture-candidate"
                    key={`${candidate.field_path}-${candidate.start_char}-${index}`}
                    data-state={decision?.state ?? 'open'}
                  >
                    <p className="capture-candidate-path">{candidate.field_path}</p>
                    <p className="capture-candidate-value">
                      {displayValue(candidate.proposed_value)}
                    </p>
                    <p className="capture-candidate-quote">“{candidate.quote}”</p>
                    <p className="capture-candidate-rule">{candidate.rule}</p>
                    {conflicted && (
                      <p className="capture-candidate-conflict">
                        This transcript proposes another value for the same field.
                        Accept at most one.
                      </p>
                    )}
                    {decision?.state === 'accepted' ? (
                      <p className="capture-candidate-state">
                        <span aria-hidden="true">✓ </span>
                        {CAPTURE_COPY.accepted}{' '}
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={() => undo(index, candidate)}
                          disabled={busy}
                        >
                          {CAPTURE_COPY.undo}
                        </button>
                      </p>
                    ) : decision?.state === 'rejected' ? (
                      <p className="capture-candidate-state">
                        <span aria-hidden="true">— </span>
                        {CAPTURE_COPY.rejected}
                      </p>
                    ) : (
                      <div className="capture-candidate-actions">
                        {spec && (
                          <>
                            <label
                              className="capture-label"
                              htmlFor={`${ids}-edit-${index}`}
                            >
                              {CAPTURE_COPY.edit}
                            </label>
                            <input
                              id={`${ids}-edit-${index}`}
                              className="capture-control"
                              value={edits[index] ?? displayValue(candidate.proposed_value)}
                              onChange={(event) =>
                                setEdits((current) => ({
                                  ...current,
                                  [index]: event.target.value,
                                }))
                              }
                            />
                          </>
                        )}
                        <button
                          type="button"
                          className="btn btn-primary"
                          onClick={() => accept(index, candidate)}
                          disabled={busy || targetRun === null}
                        >
                          {CAPTURE_COPY.accept}
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={() => reject(index, candidate)}
                          disabled={busy}
                        >
                          {CAPTURE_COPY.reject}
                        </button>
                      </div>
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
            {reading.accept_contract.message} Accepting writes through{' '}
            <code>
              {reading.accept_contract.method} {reading.accept_contract.path}
            </code>
            .
          </p>
        </div>
      )}
      </div>
      )}
    </section>
  );
}

export default TranscriptCapturePanel;

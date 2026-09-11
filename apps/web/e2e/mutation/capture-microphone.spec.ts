/**
 * VOICE CAPTURE, IN A REAL BROWSER, AGAINST A REAL (SYNTHETIC) MICROPHONE.
 *
 * ── WHY THIS FILE EXISTS ────────────────────────────────────────────────────
 *
 * Before it, NO browser test in this repository had ever called `getUserMedia`
 * or constructed a `MediaRecorder`. Measured:
 *
 *     rg -an 'getUserMedia|MediaRecorder|fake-device|fake-ui|grantPermissions' \
 *        apps/web/e2e apps/web/playwright*.config.ts
 *
 * returned exactly one hit, and it was a WORD-LIST assertion in
 * `e2e/trusted/two-actor-real-browser.spec.ts`, not a media call. Every
 * microphone test was a jsdom component test driving a hand-written
 * `FakeMediaRecorder` (`src/__tests__/transcript-capture.test.tsx`).
 *
 * ── THE DEFECT THIS FILE WAS COMMISSIONED FOR, AND WHAT MEASURING IT FOUND ──
 *
 * The brief was: at `0650bd46`, `TranscriptCapturePanel`'s only audio teardown
 * is `useEffect(() => () => dropAudio(), [dropAudio])`, and `dropAudio`'s
 * identity is STABLE (its one dependency is an empty-dep `useCallback`), so that
 * cleanup fires on UNMOUNT and on nothing else. `experimentId` appears nowhere
 * in the chain and the `[experimentId]` reset effect never called `dropAudio()`.
 * `RecordWorkbench` renders the panel with no `key` under a single
 * `/record/:id` route. Conclusion drawn from the code: moving from record A to
 * record B in-app leaves a live microphone open.
 *
 * MEASURED IN A REAL BROWSER, AT `0650bd46`: THAT PARTICULAR OUTCOME DOES NOT
 * HAPPEN, and the reason is a screen-level fact the component-level reading
 * could not see. `RecordWorkbench` renders `<LoadedWorkbench>` only while
 * `bundle.status === 'data'`; a record switch refetches, the status becomes
 * `'loading'`, and the whole subtree — capture panel included — is DELETED and
 * later rebuilt. So the unmount cleanup does fire, and it releases the
 * microphone. Captured from the instrumented `MediaStreamTrack.prototype.stop`
 * at the moment of the switch, at `0650bd46`:
 *
 *     at TranscriptCapturePanel.tsx  (dropAudio, stopping the stream's tracks)
 *     at safelyCallDestroy
 *     at commitHookEffectListUnmount
 *     at commitPassiveUnmountInsideDeletedTreeOnFiber      <- a DELETED subtree
 *     at commitPassiveUnmountEffectsInsideOfDeletedTree_begin
 *
 * `already recording` below therefore passes at `0650bd46` as well as at HEAD,
 * and its own comment says so. IT IS NOT A REGRESSION GUARD FOR THAT DEFECT.
 * It is kept because the invariant it states — leaving a record releases the
 * microphone — is the user-facing promise `CAPTURE_COPY.voiceAudioHandling`
 * makes ("…is discarded when you clear it, LEAVE THIS RECORD, or reload the
 * page"), and it must not regress whichever mechanism keeps it.
 *
 * ── AND A REAL LEAK ON THE SAME NAVIGATION, WHICH DOES REPRODUCE ────────────
 *
 * The same measurement found a microphone that really is orphaned, on the same
 * user action, and `permission still pending` below is the test for it.
 *
 * If the reader presses Start Recording and moves to another record BEFORE the
 * browser has decided the permission — a wait that in reality is a human
 * reading a prompt, or a device already in use — then at `0650bd46`:
 *
 *   1. the panel unmounts, and its cleanup calls `dropAudio()`, which finds
 *      `streamRef.current === null`, because the stream does not exist yet;
 *   2. `getUserMedia` then RESOLVES, into the closure of a component that no
 *      longer exists. Nothing checks that. It assigns the granted stream to the
 *      dead component's `streamRef`, constructs a `MediaRecorder` and calls
 *      `start()`;
 *   3. and there is now a LIVE microphone track that nothing in the application
 *      holds a reference to, so nothing can ever stop it. Only closing the tab
 *      will.
 *
 * Measured, same spec, two trees, same commit of this file:
 *
 *   `0650bd46`      → track `readyState: "live"`, `stop()` called ZERO times
 *   the fix at HEAD → track `readyState: "ended"`, stopped from inside
 *                     `startRecording` — the `audioGenerationRef` stale branch
 *
 * That branch is reachable for a reason worth writing down, because it is not
 * obvious and a future reader may assume it is dead code: react-router commits
 * the new `:id` BEFORE the bundle hook's effect can set `status: 'loading'`, so
 * there is exactly one commit in which the panel is still mounted and already
 * carrying the NEW `experimentId`. The record-change effect runs in it, bumps
 * the generation, and that is what the in-flight `getUserMedia` later compares
 * itself against.
 *
 * ── WHAT IS REAL HERE AND WHAT IS NOT — read this before citing any result ──
 *
 * REAL, in every test in this file:
 *   · a real Chromium (`channel: 'chromium'`, the full browser — see the note
 *     on the headless shell below), doing a real client-side React Router
 *     navigation;
 *   · a real `navigator.mediaDevices.getUserMedia`, answered by Chromium's own
 *     synthetic capture device (`--use-fake-device-for-media-stream`), which
 *     reports `label: "Fake Default Audio Input"`;
 *   · a real `MediaRecorder`, producing real `audio/webm;codecs=opus` bytes
 *     (measured: ~12,000 B for a ~1.2 s take);
 *   · a real permission DECISION. `--use-fake-ui-for-media-stream` is
 *     DELIBERATELY NOT PASSED, because it auto-accepts and would make the
 *     refusal test a fiction. Grant is `context.grantPermissions(['microphone'])`;
 *     refusal is simply not granting, and Chromium then rejects with a genuine
 *     `DOMException` `NotAllowedError: Permission denied`. **No test in this
 *     file stubs `getUserMedia`, `MediaRecorder`, or any media API.**
 *
 * NOT REAL, and named rather than implied:
 *   · the microphone is synthetic. There is no OS capture device involved, so
 *     nothing here proves anything about a physical microphone's indicator
 *     light or about how a specific operating system reports capture.
 *   · `installMicProbe` below WRAPS `getUserMedia` and SUBCLASSES
 *     `MediaRecorder` to keep handles and byte counts. It is INSTRUMENTATION,
 *     not substitution: the wrapper delegates to the original and returns the
 *     original's own `MediaStream`, and the subclass calls `super()` and only
 *     adds a listener. The app still talks to the real implementations. What
 *     the probe changes is that the test can SEE them.
 *
 * ── THE OBSERVATION SIGNAL FOR "THE MICROPHONE IS RELEASED", AND ITS LIMITS ──
 *
 * `MediaStreamTrack.readyState`, read on the exact track objects the app's own
 * `getUserMedia` call returned.
 *
 * WHAT IT PROVES. `readyState` is `"live"` while the track's source may still
 * deliver frames, and becomes `"ended"` — permanently, per the Media Capture
 * spec — when `stop()` is called on it or the source ends. So `"ended"` on
 * every track the app ever obtained is a direct statement that the app called
 * `stop()` on each of them, i.e. that it released capture. And `"live"` on a
 * track whose owning component is gone is a direct statement that it did NOT —
 * which is exactly the reading `permission still pending` gets at `0650bd46`.
 *
 * WHAT IT DOES NOT PROVE. It is a fact about the track OBJECT inside this
 * renderer, not an observation of the operating system. It cannot see a second
 * tab, an extension, or a capture started outside the page. It also cannot
 * distinguish "the app stopped the track" from "the synthetic source ended on
 * its own" — though nothing in this suite ends the fake device, and the
 * `0650bd46` run of `permission still pending` shows the track staying `live`
 * for the full 15 s poll, which is what makes the distinction moot in practice.
 *
 * WHY NOT SOMETHING MORE DIRECT. Chromium's tab recording indicator is browser
 * chrome and is not reachable from CDP in a way Playwright exposes;
 * `navigator.mediaDevices.enumerateDevices()` does not report whether capture
 * is ACTIVE; and there is no page-visible "is the mic hot" API. `readyState`
 * on the app's own tracks is the most direct signal a page can observe, which
 * is why it was chosen.
 *
 * ── THIS SPEC MUTATES NO SERVER STATE, ON PURPOSE ─────────────────────────
 *
 * It lives in the mutation suite because it needs file-scoped launch options
 * and `workers: 1` (the read-only suite runs five viewport projects in
 * parallel and asserts canonical seed CONTENT). But it deliberately does NOT
 * finalize a transcript: finalizing mints durable notes and proposals on
 * `SEED.fresh`, which NINE other specs in this suite read — and this file's
 * position in the run order is not something to rely on, because changing a
 * worker-scoped option makes Playwright schedule it into a worker of its own
 * (measured: it ran LAST of the fifteen, not third alphabetically). Recording,
 * stopping and discarding write nothing; the one request that leaves the page
 * (`POST /api/transcription`) is refused `501` by design in every deployment.
 * Excluding finalize costs the privacy proof nothing — finalize sends TYPED
 * TEXT and never touches audio, which is the whole point being asserted.
 *
 * ── TWO CONFIGURATION FACTS THAT COST TIME TO FIND ────────────────────────
 *
 * 1. `channel: 'chromium'` IS REQUIRED. Playwright's default headless Chromium
 *    is the HEADLESS SHELL, and in it `getUserMedia({audio: true})` rejects
 *    with `NotSupportedError: Not supported` — before any permission is even
 *    considered, and with the fake-device flag set. Measured in this suite.
 *    `channel: 'chromium'` selects the full browser in new-headless mode, where
 *    it works. Since Playwright 1.49 `npx playwright install chromium` — which
 *    is exactly what `.github/workflows/ci.yml` runs — downloads BOTH builds,
 *    and this machine's browser cache holds both (`chromium-1234` beside
 *    `chromium_headless_shell-1234`), so no new install step is needed. STATED
 *    WITH ITS VANTAGE POINT: that cache was read HERE, on darwin. Nothing in
 *    this repository can observe the Linux CI runner's cache, so if a CI run
 *    fails in this file with `NotSupportedError` or a missing-executable error,
 *    this is the first thing to check.
 * 2. These are WORKER-scoped options, so `test.use` for them must be at the top
 *    level of the file, never inside a `describe`.
 */

import { test, expect, SEED } from './fixtures';
import { MUT_BASE_URL } from './env';
import type { Page } from '@playwright/test';

test.use({
  // See note 1 in the header: the headless shell cannot capture audio at all.
  channel: 'chromium',
  launchOptions: {
    args: [
      // A synthetic capture device. NOTE the absence of
      // `--use-fake-ui-for-media-stream`: that flag auto-ACCEPTS the permission
      // and would turn `refuses honestly` into a test of nothing.
      '--use-fake-device-for-media-stream',
    ],
  },
});

/* ------------------------------------------------------------------------ */
/* The probe                                                                 */
/* ------------------------------------------------------------------------ */

/** What `installMicProbe` publishes on `window`. */
interface MicProbeReading {
  /** A value minted once per DOCUMENT. If it changes, the page reloaded. */
  documentToken: string;
  /** How many times the APP called `getUserMedia`. */
  gumCalls: number;
  /** How many of those calls have RESOLVED. Distinct from `gumCalls` only
   *  while `permissionDelayMs` is holding one open — which is the whole
   *  premise of the `permission still pending` test. */
  gumResolutions: number;
  /** `DOMException.name` for each rejection the app received, in order. */
  gumRejections: string[];
  /** `readyState` of every track the app was ever handed, in order. */
  trackStates: string[];
  /** `label` of each of those tracks — proof the device is the fake one. */
  trackLabels: string[];
  /** `state` of every `MediaRecorder` the app constructed. */
  recorderStates: string[];
  /** How many `dataavailable` events fired, and how many bytes they carried. */
  chunkEvents: number;
  audioBytes: number;
  /** Constructor names of every body handed to `fetch`/XHR/`sendBeacon`. */
  outboundBodyKinds: string[];
  /** Non-HTTP egress channels, which `page.on('request')` cannot see. */
  rtcPeerConnections: number;
  webSockets: string[];
  /** Constructor name of every payload passed to any `WebSocket.send`. */
  webSocketSendKinds: string[];
}

/**
 * Instrumentation, installed before the app's own scripts run.
 *
 * IT SUBSTITUTES NOTHING. `getUserMedia` is wrapped and delegates to the
 * original, returning the original's stream unchanged. `MediaRecorder` is
 * SUBCLASSED — `super(...)` is the real constructor, and the subclass only adds
 * a `dataavailable` listener via `addEventListener`, which is deliberately
 * independent of the `recorder.ondataavailable = …` slot the app assigns and
 * later nulls. `fetch`, `XMLHttpRequest.send`, `sendBeacon`, `RTCPeerConnection`
 * and `WebSocket` are wrapped the same way, to record WHAT was handed to them
 * without changing what they do.
 *
 * The last three exist because `page.on('request')` sees HTTP only. Audio could
 * in principle leave a tab over WebRTC or a WebSocket without any HTTP request
 * appearing, and a privacy assertion that could not see those channels would be
 * weaker than it reads.
 */
function installMicProbe(permissionDelayMs: number) {
  interface Probe {
    documentToken: string;
    gumCalls: number;
    gumResolutions: number;
    gumRejections: string[];
    tracks: MediaStreamTrack[];
    recorders: MediaRecorder[];
    chunkEvents: number;
    audioBytes: number;
    outboundBodyKinds: string[];
    rtcPeerConnections: number;
    webSockets: string[];
    webSocketSendKinds: string[];
  }
  const scope = window as unknown as { __isaacMicProbe?: Probe };
  // Per DOCUMENT, not per navigation: `addInitScript` re-runs on every new
  // document, so a fresh token is exactly the reload signal the tests want.
  if (scope.__isaacMicProbe) return;

  const probe: Probe = {
    documentToken: `${Date.now()}-${Math.random()}`,
    gumCalls: 0,
    gumResolutions: 0,
    gumRejections: [],
    tracks: [],
    recorders: [],
    chunkEvents: 0,
    audioBytes: 0,
    outboundBodyKinds: [],
    rtcPeerConnections: 0,
    webSockets: [],
    webSocketSendKinds: [],
  };
  scope.__isaacMicProbe = probe;

  const devices = navigator.mediaDevices;
  if (devices && typeof devices.getUserMedia === 'function') {
    const original = devices.getUserMedia.bind(devices);
    devices.getUserMedia = async (constraints?: MediaStreamConstraints) => {
      probe.gumCalls += 1;
      try {
        const stream = await original(constraints);
        /*
         * THE ONLY TIMING INTERVENTION IN THIS FILE, AND IT IS ZERO BY DEFAULT.
         *
         * The call above is the REAL `getUserMedia` against the REAL synthetic
         * device, and `stream` is the browser's own `MediaStream` — nothing is
         * substituted or synthesised. What a non-zero delay changes is WHEN the
         * app is handed that stream, so a navigation can reliably win a race
         * that in reality is won by a human reading a permission prompt or by a
         * device that is already in use. A test that waited for the browser's
         * own sub-millisecond auto-grant could not observe the race at all.
         *
         * Note it delays the RESOLUTION, not the capture: the microphone is
         * already open during the delay, which is exactly the situation being
         * tested — a hot device with no owner yet.
         */
        if (permissionDelayMs > 0) {
          await new Promise((resolve) => setTimeout(resolve, permissionDelayMs));
        }
        probe.gumResolutions += 1;
        for (const track of stream.getTracks()) probe.tracks.push(track);
        return stream;
      } catch (cause) {
        probe.gumRejections.push((cause as DOMException)?.name ?? String(cause));
        throw cause;
      }
    };
  }

  const OriginalRecorder = window.MediaRecorder;
  if (typeof OriginalRecorder === 'function') {
    class ObservedMediaRecorder extends OriginalRecorder {
      constructor(stream: MediaStream, options?: MediaRecorderOptions) {
        super(stream, options);
        probe.recorders.push(this);
        this.addEventListener('dataavailable', (event) => {
          const blob = (event as BlobEvent).data;
          probe.chunkEvents += 1;
          probe.audioBytes += blob ? blob.size : 0;
        });
      }
    }
    window.MediaRecorder = ObservedMediaRecorder as unknown as typeof MediaRecorder;
  }

  const kindOf = (body: unknown): string => {
    if (body === null || body === undefined) return 'none';
    const name = (body as { constructor?: { name?: string } })?.constructor?.name;
    return typeof name === 'string' ? name : typeof body;
  };

  const originalFetch = window.fetch.bind(window);
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    probe.outboundBodyKinds.push(kindOf(init?.body));
    return originalFetch(input, init);
  }) as typeof window.fetch;

  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function send(body?: Document | XMLHttpRequestBodyInit | null) {
    probe.outboundBodyKinds.push(kindOf(body));
    return originalSend.call(this, body as never);
  };

  if (typeof navigator.sendBeacon === 'function') {
    const originalBeacon = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = ((url: string | URL, data?: BodyInit | null) => {
      probe.outboundBodyKinds.push(`beacon:${kindOf(data)}`);
      return originalBeacon(url, data);
    }) as typeof navigator.sendBeacon;
  }

  const OriginalPeerConnection = (window as { RTCPeerConnection?: unknown }).RTCPeerConnection;
  if (typeof OriginalPeerConnection === 'function') {
    const Ctor = OriginalPeerConnection as new (...args: unknown[]) => unknown;
    (window as { RTCPeerConnection?: unknown }).RTCPeerConnection = function Observed(
      ...args: unknown[]
    ) {
      probe.rtcPeerConnections += 1;
      return new Ctor(...args);
    } as unknown;
  }

  const OriginalWebSocket = window.WebSocket;
  if (typeof OriginalWebSocket === 'function') {
    const Ctor = OriginalWebSocket as unknown as new (...args: unknown[]) => WebSocket;
    window.WebSocket = function ObservedWebSocket(...args: unknown[]) {
      probe.webSockets.push(String(args[0]));
      return new Ctor(...args);
    } as unknown as typeof WebSocket;
    /*
     * AND WHAT IS SENT ON ONE. Recording only the socket URLs would be too
     * weak here: this suite runs against a VITE DEV SERVER, which opens its own
     * HMR socket on the page's origin, so "no socket was opened" is not an
     * available assertion. What IS available, and is the claim that matters, is
     * that no BINARY payload was ever pushed through any socket.
     */
    const originalWsSend = OriginalWebSocket.prototype.send;
    OriginalWebSocket.prototype.send = function send(data: unknown) {
      probe.webSocketSendKinds.push(kindOf(data));
      return originalWsSend.call(this, data as never);
    };
  }
}

/** Read the probe out of the page, flattening the live objects to plain data. */
async function readProbe(page: Page): Promise<MicProbeReading> {
  return page.evaluate(() => {
    const probe = (
      window as unknown as {
        __isaacMicProbe?: {
          documentToken: string;
          gumCalls: number;
          gumResolutions: number;
          gumRejections: string[];
          tracks: MediaStreamTrack[];
          recorders: MediaRecorder[];
          chunkEvents: number;
          audioBytes: number;
          outboundBodyKinds: string[];
          rtcPeerConnections: number;
          webSockets: string[];
          webSocketSendKinds: string[];
        };
      }
    ).__isaacMicProbe;
    if (!probe) throw new Error('the mic probe was never installed in this document');
    return {
      documentToken: probe.documentToken,
      gumCalls: probe.gumCalls,
      gumResolutions: probe.gumResolutions,
      gumRejections: [...probe.gumRejections],
      trackStates: probe.tracks.map((track) => track.readyState),
      trackLabels: probe.tracks.map((track) => track.label),
      recorderStates: probe.recorders.map((recorder) => recorder.state),
      chunkEvents: probe.chunkEvents,
      audioBytes: probe.audioBytes,
      outboundBodyKinds: [...probe.outboundBodyKinds],
      rtcPeerConnections: probe.rtcPeerConnections,
      webSockets: [...probe.webSockets],
      webSocketSendKinds: [...probe.webSocketSendKinds],
    };
  });
}

/* ------------------------------------------------------------------------ */
/* Page helpers                                                              */
/* ------------------------------------------------------------------------ */

const startButton = (page: Page) => page.getByRole('button', { name: 'Start Recording' });
const stopButton = (page: Page) => page.getByRole('button', { name: 'Stop Recording' });
const discardButton = (page: Page) => page.getByRole('button', { name: 'Discard Audio' });
const elapsed = (page: Page) => page.locator('.capture-elapsed');

/**
 * Open a record's Capture workspace with the probe installed, and expand the
 * capture panel.
 *
 * `addInitScript` is registered BEFORE the first `goto`, so it runs ahead of the
 * app's own bundle in every document this page loads. The auto-use `scope`
 * fixture has already attached the worked-example session header by this point;
 * the two do not interact.
 */
async function openCapture(page: Page, id: string, permissionDelayMs = 0) {
  await page.addInitScript(installMicProbe, permissionDelayMs);
  await page.goto(`/record/${id}?view=capture`);
  const entry = page.getByRole('button', { name: 'Capture Experiment Notes' });
  await expect(entry).toBeVisible();
  await entry.click();
  // The voice controls only render once the panel body is open AND the browser
  // reported a recorder — which is the state this whole file depends on.
  await expect(startButton(page)).toBeVisible();
}

/** Drive the real Start button and wait until the app CLAIMS it is recording. */
async function startRecordingThroughTheUi(page: Page) {
  await startButton(page).click();
  await expect(stopButton(page)).toBeVisible();
}

/* ------------------------------------------------------------------------ */
/* 1 · recording really establishes                                          */
/* ------------------------------------------------------------------------ */

test('a granted microphone really records, and the UI claims Recording only once it does', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['microphone'], { origin: MUT_BASE_URL });
  await openCapture(page, SEED.fresh);

  // BEFORE: nothing has been asked for. This is the negative half of the
  // assertion below — without it, "one live track" could be a pre-existing one.
  const before = await readProbe(page);
  expect(before.gumCalls).toBe(0);
  expect(before.trackStates).toEqual([]);
  await expect(elapsed(page)).toHaveCount(0);

  await startRecordingThroughTheUi(page);

  /*
   * THE CLAIM AND THE FACT ARE READ AT THE SAME MOMENT. `Stop Recording` being
   * on screen is the app's claim; the assertions here are the fact. The app
   * cannot pass this by rendering `recording` optimistically before the
   * permission resolves, because a `requesting-permission` render shows a
   * disabled `Requesting…` button and no Stop.
   */
  const recording = await readProbe(page);
  expect(recording.gumCalls).toBe(1);
  expect(recording.gumRejections).toEqual([]);
  expect(recording.trackStates).toEqual(['live']);
  // The device is Chromium's synthetic one — stated, not assumed.
  expect(recording.trackLabels[0]).toContain('Fake');
  expect(recording.recorderStates).toEqual(['recording']);

  /*
   * THE ELAPSED INDICATOR ADVANCES — asserted RELATIVE to whatever it read
   * first, not against a literal.
   *
   * `toHaveText('Recording · 0:02')` would have been the obvious form and is
   * subtly wrong: on a slow machine the first read can ALREADY be `0:02`, and
   * then both the "it started small" and the "it grew" assertions pass without
   * a single tick having been observed. Parsing the value and polling for a
   * strictly greater one cannot degrade that way.
   */
  const readElapsedSeconds = async () => {
    const text = await elapsed(page).innerText();
    const parts = /(\d+):(\d\d)\s*$/.exec(text);
    expect(parts, `the elapsed indicator did not read as m:ss — got "${text}"`).not.toBeNull();
    return Number(parts![1]) * 60 + Number(parts![2]);
  };
  const firstReading = await readElapsedSeconds();
  await expect
    .poll(readElapsedSeconds, {
      message: 'the elapsed indicator is not advancing while the app claims to be recording',
      timeout: 10_000,
    })
    .toBeGreaterThan(firstReading);

  // The live region says the true thing, and says it exactly once — a second
  // copy would announce the same event twice to a screen-reader user.
  await expect(
    page.getByText('Recording. Audio is being held in this tab.', { exact: true }),
  ).toHaveCount(1);

  // Leave nothing hot for the next test.
  await stopButton(page).click();
  await expect(discardButton(page)).toBeVisible();
});

/* ------------------------------------------------------------------------ */
/* 2 · leaving a record, the two ways it can go wrong                        */
/* ------------------------------------------------------------------------ */

/**
 * Move from the record on screen to another one THROUGH THE APP'S OWN UI.
 *
 * This matters more than anything else in the two tests below: a
 * `page.reload()` or a bare `page.goto()` destroys the document, which kills
 * every track for free and would make both assertions pass against the unfixed
 * code — vacuously.
 *
 * The route taken is the TopBar search palette, which is mounted on every
 * screen including this one. Selecting a result calls react-router's
 * `navigate('/record/<other id>')`: a `pushState`, the SAME document, the SAME
 * `/record/:id` route. It is the only way a scientist leaves one record for
 * another from inside this application, and it is the exact path the brief
 * identified.
 */
async function switchRecordThroughTheSearchPalette(page: Page, title: string, toId: string) {
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.getByRole('searchbox').first().fill(title);
  const result = page.getByRole('button').filter({ hasText: title });
  await expect(result.first()).toBeVisible();
  await result.first().click();
  await expect(page).toHaveURL(new RegExp(`/record/${toId}`));
}

/** Record 3's title — the record switched TO. Any of the five would do. */
const OTHER_RECORD_TITLE = 'XANES Example — CuO (Cu K-edge) · Ready to Export';

test('already recording: leaving a record in-app releases the microphone', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['microphone'], { origin: MUT_BASE_URL });
  await openCapture(page, SEED.fresh);
  await startRecordingThroughTheUi(page);

  const beforeSwitch = await readProbe(page);
  expect(beforeSwitch.trackStates).toEqual(['live']);
  const documentBefore = beforeSwitch.documentToken;

  /*
   * A HANDLE ON THE PANEL'S OWN DOM NODE, taken while it is still record A's.
   * `isConnected` on it after the switch is a fact about THIS element, so it
   * cannot be fooled by a replacement node with the same class — which is what
   * a `querySelector` re-run, or a `MutationObserver` whose callback batches a
   * removal and a re-insertion together, would silently accept.
   */
  const sectionBefore = await page.evaluateHandle(() =>
    document.querySelector('.capture-section'),
  );

  await switchRecordThroughTheSearchPalette(page, OTHER_RECORD_TITLE, SEED.ready);

  /*
   * POLL, DO NOT SAMPLE ONCE — CORRECTED 2026-09-10, after this line made
   * `main` RED on the very next merge.
   *
   * The release that ends the track is a React PASSIVE-EFFECT cleanup, which
   * runs on a later task than the navigation this test just awaited. A single
   * `readProbe` immediately after `switchRecordThroughTheSearchPalette`
   * therefore samples a race: it won locally and on this PR's own CI run, and
   * lost on the next run — a docs-only merge to `main`, where nothing about
   * this code had changed. The failure read
   * `the microphone obtained for the record the reader LEFT is still live`,
   * which is exactly the honest message, describing a test defect rather than
   * a product one.
   *
   * WHAT THE POLL DOES AND DOES NOT WEAKEN. It bounds how long the release may
   * take; it does not make the outcome true by construction. If the track never
   * ends, `expect.poll` fails with the sentence below, which is the same claim
   * the one-shot assertion made. The negative controls that give this test its
   * meaning — the unchanged `documentToken`, the track-array length, and
   * `isConnected` on record A's own node — are read AFTER the poll and are
   * unaffected by it: none of them can be satisfied by simply waiting.
   */
  await expect
    .poll(
      async () => (await readProbe(page)).trackStates.join(','),
      {
        message:
          'the microphone obtained for the record the reader LEFT is still live',
      },
    )
    .toBe('ended');

  const afterSwitch = await readProbe(page);

  /*
   * NEGATIVE CONTROL, AND IT IS LOAD-BEARING. `addInitScript` re-runs on every
   * new document, and `installMicProbe` mints a fresh `documentToken` when it
   * does. An unchanged token therefore PROVES the document survived — i.e. that
   * this is the in-app navigation described above and not a reload. Without
   * this line the test could silently degrade into the vacuous reload test.
   */
  expect(
    afterSwitch.documentToken,
    'the navigation reloaded the document, so this test proves nothing about ' +
      'in-app record switching — see the comment above',
  ).toBe(documentBefore);
  expect(
    afterSwitch.trackStates,
    'this is the same array of tracks, so a length change would mean a new ' +
      'getUserMedia the switch should never have triggered',
  ).toHaveLength(1);

  /*
   * THE INVARIANT. `CAPTURE_COPY.voiceAudioHandling` promises the audio "is
   * discarded when you clear it, LEAVE THIS RECORD, or reload the page", and
   * this is the "leave this record" half, measured rather than asserted in
   * prose.
   *
   * MEASURED, AND THE FILE HEADER EXPLAINS IT AT LENGTH: this ALSO passes at
   * `0650bd46`, so it is NOT a regression guard for the stable-`dropAudio`
   * dependency defect. `permission still pending` below is the test that is.
   */
  expect(
    afterSwitch.trackStates,
    'the microphone obtained for the record the reader LEFT is still live',
  ).toEqual(['ended']);
  /*
   * The recorder settles in the same cleanup as the track, but assert it with a
   * poll rather than off `afterSwitch`: the two are read in separate
   * `page.evaluate` round trips, so a one-shot read here would re-introduce a
   * narrower version of the race the poll above exists to remove.
   */
  await expect
    .poll(async () => (await readProbe(page)).recorderStates.join(','), {
      message: 'the recorder for the record the reader LEFT is not inactive',
    })
    .toBe('inactive');

  /*
   * WHY IT CURRENTLY HOLDS, PINNED SO IT CANNOT CHANGE SILENTLY.
   *
   * Today the release comes from the UNMOUNT cleanup, because
   * `RecordWorkbench` drops to a `LoadingPanel` while the new record's bundle
   * is fetched and deletes this whole subtree. This line records that.
   *
   * IT IS AN OBSERVATION OF THE MECHANISM, NOT A REQUIREMENT ON IT. If a future
   * change keeps the panel mounted across a record switch — stale-while-
   * revalidate on the record bundle would do it — this is the line that should
   * fail first, and the correct response is to DELETE it, not to restore the
   * unmount. At that moment the panel's own record-change teardown becomes
   * load-bearing and the assertion above becomes the real regression guard for
   * the original defect.
   */
  expect(
    await sectionBefore.evaluate((node) => (node as Element).isConnected),
    'the capture panel survived the record switch. That is not a failure in ' +
      'itself — see the comment above — but the mechanism this file measured ' +
      'has changed, so re-derive it before trusting the header.',
  ).toBe(false);
});

test('permission still pending: leaving a record must not orphan a live microphone', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['microphone'], { origin: MUT_BASE_URL });

  /*
   * THE RACE, AND WHY IT IS SET UP THIS WAY. The reader presses Start Recording
   * and moves on before the browser has decided — a wait that in reality is a
   * human reading a permission prompt, or a device already in use. Chromium
   * with a pre-granted permission answers in well under a millisecond, so the
   * race is unobservable unless the resolution is held open. `openCapture`'s
   * delay does exactly that and nothing else: the REAL `getUserMedia` runs, the
   * REAL device opens, and only the hand-off to the app is deferred. See the
   * long comment in `installMicProbe`.
   */
  await openCapture(page, SEED.fresh, 4000);

  await startButton(page).click();
  // The app is waiting on the browser — this is the state the race needs.
  await expect(page.getByRole('button', { name: 'Requesting…' })).toBeVisible();

  const pending = await readProbe(page);
  expect(pending.gumCalls).toBe(1);
  expect(
    pending.gumResolutions,
    'getUserMedia resolved before the navigation, so the race this test exists ' +
      'to create did not happen and nothing below would be meaningful. Raise ' +
      "openCapture's delay.",
  ).toBe(0);

  await switchRecordThroughTheSearchPalette(page, OTHER_RECORD_TITLE, SEED.ready);

  // Still the same document — the navigation was in-app, not a reload.
  expect((await readProbe(page)).documentToken).toBe(pending.documentToken);

  /*
   * THE ASSERTION THIS FILE WAS WRITTEN FOR, AND THE ONE THAT ACTUALLY FAILS
   * AGAINST THE UNFIXED CODE.
   *
   * Measured at `0650bd46`: `readyState: "live"`, and `MediaStreamTrack.stop`
   * called ZERO times for the whole page lifetime. The component that owned
   * that stream no longer exists, so no code path remains that could stop it —
   * the microphone stays open until the tab closes.
   *
   * `expect.poll` rather than a fixed wait: the stream is handed over when the
   * delay expires, and the only question is whether the app releases it at that
   * moment. Polling fails on the unfixed build by timing out with the track
   * still `live`, which is the honest description of the defect.
   */
  await expect
    .poll(
      async () => (await readProbe(page)).trackStates,
      {
        message:
          'the microphone granted for a record the reader had already left was ' +
          'adopted by a component that no longer exists, so nothing can stop it',
        timeout: 15_000,
      },
    )
    .toEqual(['ended']);

  // And the stream was really granted — otherwise "ended" would be vacuous.
  expect((await readProbe(page)).gumResolutions).toBe(1);
  expect((await readProbe(page)).gumRejections).toEqual([]);
});

/* ------------------------------------------------------------------------ */
/* 3 · stop, then discard                                                    */
/* ------------------------------------------------------------------------ */

test('Stop releases the microphone, and Discard drops the audio it captured', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['microphone'], { origin: MUT_BASE_URL });
  await openCapture(page, SEED.fresh);
  await startRecordingThroughTheUi(page);
  /*
   * Long enough that the recorder has real content to flush on stop. Written as
   * "anything past 0:00" rather than "exactly 0:01": on a slow machine the clock
   * can pass 0:01 between two polls, and `toHaveText('Recording · 0:01')` would
   * then retry until it TIMED OUT on a perfectly healthy recording.
   */
  await expect(elapsed(page)).toHaveText(/Recording · (?!0:00)\d+:\d\d/, { timeout: 10_000 });

  await stopButton(page).click();
  await expect(discardButton(page)).toBeVisible();

  const stopped = await readProbe(page);
  // Stop is where the microphone is released — before any discard.
  expect(stopped.trackStates).toEqual(['ended']);
  expect(stopped.recorderStates).toEqual(['inactive']);
  await expect(
    page.getByText('Recording stopped. Audio is held in this tab and has not been sent.', {
      exact: true,
    }),
  ).toBeAttached();

  /*
   * REAL AUDIO EXISTED. `MediaRecorder.start()` with no timeslice flushes one
   * blob on `stop()`, so this is the whole take. Asserting it is what makes the
   * privacy test below — and this discard — statements about actual bytes
   * rather than about an empty buffer.
   */
  expect(stopped.chunkEvents).toBeGreaterThan(0);
  expect(stopped.audioBytes).toBeGreaterThan(0);

  await discardButton(page).click();
  await expect(startButton(page)).toBeVisible();

  const discarded = await readProbe(page);
  // Still released — discard must not somehow re-open capture.
  expect(discarded.trackStates).toEqual(['ended']);
  expect(discarded.gumCalls).toBe(1);
  await expect(page.getByText('Audio discarded.', { exact: true })).toBeAttached();
});

/* ------------------------------------------------------------------------ */
/* 4 · a real refusal                                                        */
/* ------------------------------------------------------------------------ */

test('a browser that refuses the microphone is reported honestly, and typing still works', async ({
  page,
  context,
}) => {
  /*
   * A REAL REFUSAL BY THE BROWSER — NOT A STUBBED API. Nothing overrides
   * `getUserMedia` here (the probe wraps it and delegates). The permission is
   * simply never granted, and `--use-fake-ui-for-media-stream` is not among the
   * launch flags, so Chromium itself rejects the request with a genuine
   * `DOMException` named `NotAllowedError`. Measured in this suite before the
   * test was written, because a headless browser that silently auto-granted
   * would have made this test a fiction.
   */
  await context.clearPermissions();
  await openCapture(page, SEED.fresh);

  await startButton(page).click();

  /*
   * THE SPECIFIC, CLASSIFIED SENTENCE — not a generic failure, and asserted at
   * BOTH of the two places the panel deliberately renders it: the visible
   * persistent notice, and the polite status region that announces it once.
   * They are separate locators on purpose. A single `getByText` matches both
   * and fails strict mode, and "fixing" that with `.first()` would silently
   * stop checking whichever one happened to sort second — including the case
   * where the sighted notice disappears and only the announcement survives.
   */
  const refusalSentence =
    'This browser did not grant microphone access, so nothing was recorded. ' +
    'Typing or pasting a transcript below does the same work.';
  await expect(page.locator('p.capture-note-warn')).toHaveText(refusalSentence);
  await expect(page.locator('.capture-voice p[role="status"]')).toHaveText(refusalSentence);

  const refused = await readProbe(page);
  expect(refused.gumCalls).toBe(1);
  expect(refused.gumRejections).toEqual(['NotAllowedError']);
  expect(refused.trackStates).toEqual([]);
  expect(refused.recorderStates).toEqual([]);

  // NO FAKE `Recording`, and NO INFINITE SPINNER: the busy state
  // (`Requesting…`, `aria-busy`) must be gone, not merely superseded.
  await expect(stopButton(page)).toHaveCount(0);
  await expect(elapsed(page)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Requesting…' })).toHaveCount(0);
  await expect(page.locator('.capture-section [aria-busy="true"]')).toHaveCount(0);

  // Both recovery paths are offered.
  await expect(page.getByRole('button', { name: 'Try Recording Again' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Type What Was Said' })).toBeEnabled();

  // And the manual path REALLY works — typed, then read back from the DOM.
  const transcript = page.getByLabel('Transcript', { exact: true });
  await expect(transcript).toBeEditable();
  await transcript.fill('Refusal path: the scientist typed this instead of speaking it.');
  await expect(transcript).toHaveValue(
    'Refusal path: the scientist typed this instead of speaking it.',
  );
});

/* ------------------------------------------------------------------------ */
/* 5 · no audio ever leaves the browser                                      */
/* ------------------------------------------------------------------------ */

test('no request carries audio — over HTTP, WebRTC or a WebSocket', async ({ page, context }) => {
  await context.grantPermissions(['microphone'], { origin: MUT_BASE_URL });

  /*
   * EVERY REQUEST THE PAGE MAKES, from before the first navigation, with its
   * BODY BYTES. `postDataBuffer()` is used rather than `postData()` because the
   * question is whether anything BINARY went out, and `postData()` would hand
   * back a lossy string.
   */
  const sent: Array<{
    method: string;
    url: string;
    contentType: string;
    bytes: Buffer | null;
  }> = [];
  page.on('request', (req) => {
    sent.push({
      method: req.method(),
      url: req.url(),
      contentType: (req.headers()['content-type'] ?? '').toLowerCase(),
      bytes: req.postDataBuffer(),
    });
  });

  await openCapture(page, SEED.fresh);
  await startRecordingThroughTheUi(page);
  await expect(elapsed(page)).toHaveText('Recording · 0:01', { timeout: 10_000 });
  await stopButton(page).click();
  await expect(discardButton(page)).toBeVisible();

  // The one operation in this panel that mentions audio at all. It is refused
  // `501 no_provider_configured` in every deployment; what matters here is what
  // its REQUEST carried.
  await page.getByRole('button', { name: 'Request a Transcript' }).click();
  /*
   * WAIT ON THE REFUSAL, NOT ON THE BUTTON — corrected 2026-09-11.
   *
   * This barrier read `…toBeEnabled()`, which stopped being true by design: the
   * control is now DISABLED once it has refused, because a control that can never
   * succeed should not stay armed for a reader to press again. The assertion was
   * only ever a synchronisation barrier before `readProbe`, and waiting for the
   * refusal itself is the stricter one — `toBeEnabled` could pass before the
   * request had even resolved, whereas `.capture-refusal` cannot appear until the
   * server has answered.
   */
  await expect(page.locator('.capture-refusal')).toBeVisible();

  const probe = await readProbe(page);

  /*
   * THE PREMISE. Without this the rest is vacuous: a page that captured no
   * audio trivially sends none.
   */
  expect(probe.audioBytes).toBeGreaterThan(0);

  /*
   * (a) THE TWO NON-HTTP EGRESS CHANNELS, which `page.on('request')` cannot see
   *     at all — audio could leave a tab over either without one HTTP request
   *     appearing, and a privacy assertion blind to them would read stronger
   *     than it is.
   *
   *     WebRTC: no `RTCPeerConnection` was ever constructed, so there was no
   *     peer connection for a track to be added to.
   *
   *     WebSockets: this is measured against a VITE DEV SERVER, which opens its
   *     own HMR socket on the page's own origin — a dev-only channel that does
   *     not exist in the production build. So the assertion is not "no socket";
   *     it is that every socket opened was that one, on the page's origin, and
   *     that NOTHING BINARY was ever pushed through any socket. Audio would
   *     have to travel as a `Blob`/`ArrayBuffer`/typed array; every send here
   *     is a `String`.
   */
  expect(probe.rtcPeerConnections).toBe(0);
  const devServerSocket = `ws://${new URL(MUT_BASE_URL).host}/`;
  const foreignSockets = probe.webSockets.filter((url) => !url.startsWith(devServerSocket));
  expect(foreignSockets, 'a WebSocket was opened to something other than the dev server').toEqual(
    [],
  );
  const binarySocketSends = probe.webSocketSendKinds.filter(
    (kind) => kind !== 'none' && kind !== 'String',
  );
  expect(
    binarySocketSends,
    `a non-string payload was pushed through a WebSocket: ${binarySocketSends.join(', ')}`,
  ).toEqual([]);

  // (b) NOTHING BINARY WAS EVER HANDED TO fetch/XHR/sendBeacon. A `Blob`,
  //     `File`, `FormData`, `ArrayBuffer` or typed array is how audio would
  //     have to travel; every body this app sends is a `String`.
  const binaryKinds = probe.outboundBodyKinds.filter(
    (kind) => kind !== 'none' && kind !== 'String',
  );
  expect(binaryKinds, `unexpected outbound body kinds: ${binaryKinds.join(', ')}`).toEqual([]);

  // (c) NO REQUEST DECLARED A MEDIA OR OPAQUE-BINARY CONTENT TYPE.
  const mediaTyped = sent.filter(
    (req) =>
      req.contentType.startsWith('audio/') ||
      req.contentType.startsWith('video/') ||
      req.contentType.startsWith('multipart/') ||
      req.contentType.startsWith('application/octet-stream'),
  );
  expect(
    mediaTyped.map((r) => `${r.method} ${r.url} (${r.contentType})`),
    'a request declared a media content type',
  ).toEqual([]);

  // (d) EVERY BODY IS TEXT, AND CARRIES NO WEBM. The recorder's output is
  //     `audio/webm;codecs=opus`, whose container begins with the EBML magic
  //     `1A 45 DF A3` — so the raw bytes are searched for it directly, and each
  //     body is additionally required to round-trip as UTF-8 (binary would not).
  const EBML_MAGIC = Buffer.from([0x1a, 0x45, 0xdf, 0xa3]);
  const withBodies = sent.filter((req) => req.bytes !== null && req.bytes.length > 0);
  expect(withBodies.length, 'no request had a body at all — the flow did not run').toBeGreaterThan(
    0,
  );
  for (const req of withBodies) {
    const bytes = req.bytes as Buffer;
    expect(bytes.includes(EBML_MAGIC), `${req.method} ${req.url} carries a WebM header`).toBe(
      false,
    );
    const text = bytes.toString('utf8');
    expect(
      Buffer.from(text, 'utf8').equals(bytes),
      `${req.method} ${req.url} has a body that is not valid UTF-8, so it is binary`,
    ).toBe(true);
  }

  /*
   * (e) THE TRANSCRIPTION REQUEST CARRIES THE OPAQUE HANDLE AND NOTHING ELSE.
   *     `held-in-tab:<chunk count>` is a string this component minted; the count
   *     is the only thing about the audio that leaves, and it is a count.
   */
  const transcription = sent.filter((req) => req.url.endsWith('/api/transcription'));
  expect(transcription).toHaveLength(1);
  const body = JSON.parse((transcription[0].bytes as Buffer).toString('utf8'));
  expect(Object.keys(body).sort()).toEqual(['audio_ref']);
  expect(body.audio_ref).toMatch(/^held-in-tab:\d+$/);

  /*
   * (f) AND THE ARITHMETIC. Every request body in the whole session, added up,
   *     is smaller than the audio held in the tab — so the recording cannot have
   *     left even split across requests, even base64-encoded (which would cost
   *     4/3 of the raw size). Stated as a bound rather than as a spot check.
   */
  const totalBodyBytes = withBodies.reduce((sum, req) => sum + (req.bytes as Buffer).length, 0);
  expect(
    totalBodyBytes,
    `all request bodies together (${totalBodyBytes} B) must be smaller than the ` +
      `audio held in the tab (${probe.audioBytes} B)`,
  ).toBeLessThan(probe.audioBytes);
});

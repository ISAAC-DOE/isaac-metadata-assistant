/*
 * THE RUNS SECTION — a bounded browser over a record's runs, and the one control
 * that adds to it.
 *
 * WHY IT OWNS ITS OWN FETCH rather than joining the record bundle. The bundle
 * is eight concurrent reads that every record screen performs; runs are needed
 * by ONE of them. Fetching separately also means a Run API that is unavailable
 * degrades to a contained panel inside this section instead of taking the whole
 * record screen down with it — the field workbench above still renders, and the
 * reader is told which part is missing.
 *
 * IT USED TO DOWNLOAD EVERY RUN, AND THAT IS WHAT CHANGED HERE.
 * `docs/run-scale-measurements.md` located the cost precisely: a collapsed card
 * is ~12 DOM nodes and expand latency does NOT degrade at the tail, so the DOM
 * was never the problem — the response was. At 1000 runs it is 7.47 MiB, because
 * every run that overrides nothing carries a byte-identical copy of the same 15
 * record-level resolutions. So this section now asks for a PAGE, and searches and
 * filters where the data is (the server) rather than where it has already been
 * paid for (the client). The same document rules virtualization OUT for exactly
 * this reason: windowing would remove DOM nodes that are already cheap and would
 * not remove one byte.
 *
 * THE EXPERIMENT VERSION IS HELD HERE, and this is the one piece of state that
 * needs saying twice. Creating a run mutates the EXPERIMENT, so it carries the
 * experiment's `If-Match`; the create response returns the experiment's NEW
 * version, which is what the next create must carry. Reading it from the record
 * bundle's `detail.version` instead would be stale from the first create
 * onwards, and every subsequent Add Run would be a 412 the reader could do
 * nothing about.
 *
 * WHAT PAGING DOES NOT GIVE US, said here because a comment is the only place it
 * can be said once: OFFSET PAGING IS NOT SNAPSHOT-CONSISTENT. Each page is an
 * independent read. A run created or deleted by anyone — including this reader in
 * another tab — between two reads shifts every later offset, so a run can be
 * repeated (which the append dedupes) or MISSED (which nothing here can detect).
 * The list therefore says so on screen next to the control that causes it, rather
 * than presenting an accumulation as if it were one consistent read.
 *
 * UNMOUNTING A CARD IS SAFE, AND THAT IS LOAD-BEARING FOR THIS WHOLE SLICE.
 * Paging, searching, filtering and focusing all unmount cards. Autosave state
 * lives in the module-level store keyed `<experimentId>/<runId>`
 * (`lib/runAutosaveStore.ts`) and is disposed only by `RecordWorkbench` when the
 * record screen itself goes away — so an edit in flight when a filter changes
 * still reaches the server and its outcome still comes back. Nothing in this file
 * calls `disposeExperiment`, and nothing in it may start to.
 *
 * "SAFE" IS ABOUT SAVE STATE, NOT ABOUT EVERY CHARACTER IN THE CARD, and that
 * distinction is stated here because this paragraph is where a reader comes to check
 * it. An edit reaches the store only once `parseRunField` has accepted the text
 * (`RunCard.onFieldChange` returns first when it does not), so text this build cannot
 * shape lives in the card's own state and IS lost when paging, searching or filtering
 * unmounts the card. `RunCard` discloses that on screen while it holds such text. The
 * record's own view tabs no longer unmount anything (`RecordWorkbench` hides the
 * fields panel instead), so this list is now the only in-screen gesture that does.
 */

import './runs.css';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RunCard } from './RunCard';
import { RunCompare } from './RunCompare';
import { LoadingPanel, BackendDown } from './FetchStates';
import { Plus } from './icons';
import { api, ApiError } from '../lib/api';
import { disposeRun } from '../lib/runAutosaveStore';
import {
  RECORD_ADDRESS_PARAM,
  RECORD_COMPARE_PARAM,
  RECORD_RUN_PARAM,
  RUN_COMPARE_MAX,
} from '../lib/routes';
import type { RecordChangeSummary } from '../lib/recordChanges';
import type { ApiRunView } from '../lib/types';
import { RUNS_PAGE_SIZE } from '../lib/runPaging';
import { mutationFailureCopy } from '../lib/mutationErrors';

/*
 * RE-EXPORTED, NOT DEFINED HERE. The scale benchmark needs this number too, and
 * `e2e/tsconfig.json` does not set `jsx`, so it cannot import a `.tsx` module. The
 * decision and its justification live in `../lib/runPaging`; this line keeps every
 * existing importer of `RunsSection` working.
 */
export { RUNS_PAGE_SIZE };

/**
 * How long the search box waits before it becomes a request.
 *
 * A keystroke is not a query. 300 ms is the usual floor for "the typist has
 * paused" without the box feeling detached from the list; below ~200 ms an
 * ordinary typing rate still fires several requests per word.
 */
export const RUN_SEARCH_DEBOUNCE_MS = 300;

/** `''` is "not filtering"; the other two are the server's own vocabulary. */
type OverridesFilter = '' | 'any' | 'none';
/** `''` is "not filtering". Sent as the boolean the contract asks for. */
type ExportedFilter = '' | 'true' | 'false';

interface Loaded {
  runs: ApiRunView[];
  /**
   * How many run objects the SERVER has handed back for these criteria — the
   * offset the next page must be read from.
   *
   * Deliberately not `runs.length`. The append dedupes by id, so a repeated run
   * makes the array shorter than what was received; paging from the array length
   * would then re-request a window that overlaps the last one and, in the case
   * the dedupe exists for, could walk the same overlap forever.
   */
  received: number;
  /** Runs that EXIST in this record. Never the filtered count. */
  total: number;
  /** Runs matching the current search/filters. Equals `total` when none are set. */
  matched: number;
}

type ListState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; loaded: Loaded };

/**
 * How the ONE focused run was obtained.
 *
 * `page` means it is already in the loaded list and is rendered from there.
 * `fetched` means it was not, and was read directly — which is the whole point
 * of the state: a bounded list makes "not on the page" the ordinary case for a
 * deep link, and answering that with "no such run" would be a false 404 about a
 * run that exists.
 */
type FocusState =
  | { status: 'idle' }
  | { status: 'page' }
  | { status: 'loading' }
  | { status: 'missing'; error: ApiError }
  | { status: 'fetched'; run: ApiRunView };

/** The server's own words for a refusal it explained, or `null`.
 *
 *  Only a `message` the body actually carries is used, so a refusal with no explanation
 *  still falls through to the existing copy rather than to a blank. `mutationError` now
 *  reads a 409 body, which is what makes this reachable.
 */
function serverRefusalMessage(err: unknown): string | null {
  // 409 only, for the reason `GuidedCompletion.serverExplanation` gives: every other
  // status on this route already has copy chosen for it, and 409 had none.
  if ((err as { status?: number } | null)?.status !== 409) return null;
  const body = (err as { body?: unknown } | null)?.body;
  if (body === null || typeof body !== 'object') return null;
  const message = (body as { message?: unknown }).message;
  return typeof message === 'string' && message.trim() !== '' ? message : null;
}

export function RunsSection({
  experimentId,
  activity,
}: {
  experimentId: string;
  /**
   * THE CHANGE-FEED SUMMARY THIS SCREEN ALREADY HOLDS, OR NULL — see
   * `RecordChangeSummary`. IDS AND A REVISION ONLY, NEVER RUN CONTENT: this section
   * treats a signal as "something moved, go re-read the first page", never as a
   * value to render. The producer floors `experiment`/`run` entries at the rev this
   * section was mounted at, so a signal never replays history this section has
   * already adopted; `highestRev` is compared against this section's OWN loaded
   * rev below, which is a second, independent floor against exactly that replay.
   */
  activity?: RecordChangeSummary | null;
}) {
  return (
    <section className="runs-section" aria-labelledby="runs-heading">
      <div className="runs-head">
        <h2 className="runs-title" id="runs-heading">
          Runs
        </h2>
        {/*
          THE SECOND HALF WAS TRUE AND IS NOW ONLY MOSTLY TRUE, so it is corrected
          rather than left standing. It read "everything under Inherited from
          Experiment is read from the experiment" — flat, with no exception — and a
          run may now hold its own value at one of those addresses. The panel's own
          rows say which are which; this sentence states the default and names the
          exception instead of denying it.
        */}
        <p className="runs-sub">
          One run per set of measurement conditions. Values entered here belong to this run
          alone; everything under Inherited from the record is read live from the record,
          unless this run overrides it.
        </p>
      </div>

      {/* Keyed on the experiment so switching records rebuilds the browser's
          state — its page, its search, its filters — rather than carrying one
          record's list criteria into another's. A remount is also what "starts
          clean" means for the signal-handling refs below: they are declared with
          `useRef` inside `RunsBrowser`, so a new `experimentId` gives them fresh
          initial values along with everything else. */}
      <RunsBrowser key={experimentId} experimentId={experimentId} activity={activity ?? null} />
    </section>
  );
}

function RunsBrowser({
  experimentId,
  activity,
}: {
  experimentId: string;
  activity: RecordChangeSummary | null;
}) {
  const baseId = useId();
  const searchId = `${baseId}-search`;
  const searchHintId = `${baseId}-search-hint`;
  const overridesId = `${baseId}-overrides`;
  const exportedId = `${baseId}-exported`;

  const [searchParams, setSearchParams] = useSearchParams();
  const focusRunId = searchParams.get(RECORD_RUN_PARAM);
  /*
   * THE ADDRESS A LINK INTO FOCUS RUN IS ABOUT — see `RECORD_ADDRESS_PARAM`.
   *
   * Compare Runs writes it so that following a difference lands on the address it
   * was about rather than on a card carrying every address. It is a SCROLL TARGET
   * AND NOTHING ELSE: nothing is filtered, nothing is selected, and an address the
   * focused run does not render leaves the page exactly as it would otherwise be.
   */
  const focusAddress = searchParams.get(RECORD_ADDRESS_PARAM);

  /*
   * THE COMPARISON SELECTION IS THE URL, and `getAll` is why the parameter repeats
   * rather than carrying a delimiter — see `RECORD_COMPARE_PARAM`. It is read here
   * and never mirrored into state: one source, so a link, a Back press and a click
   * on a card cannot disagree about which two runs are being compared.
   *
   * DE-DUPLICATED, ORDER PRESERVED. `?compare=A&compare=A` is a link a person can
   * write, and comparing a run with itself is not a comparison. The FIRST
   * occurrence keeps its place, so "the first run" stays the first run.
   */
  const compareIds = [...new Set(searchParams.getAll(RECORD_COMPARE_PARAM))].filter(
    (id) => id !== '',
  );

  /** What is in the box. `query` is what has been SENT. */
  const [searchText, setSearchText] = useState('');
  const [query, setQuery] = useState('');
  const [overridesFilter, setOverridesFilter] = useState<OverridesFilter>('');
  const [exportedFilter, setExportedFilter] = useState<ExportedFilter>('');

  const [list, setList] = useState<ListState>({ status: 'loading' });
  const [experimentVersion, setExperimentVersion] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  /** True only for the stale-version refusal, which is the one a reload fixes. */
  const [addStale, setAddStale] = useState(false);
  /** Said on screen when a create cleared criteria out from under the reader. */
  const [addNote, setAddNote] = useState<string | null>(null);

  const [focus, setFocus] = useState<FocusState>({ status: 'idle' });
  /** The run whose card header should take keyboard focus when it next mounts. */
  const [cardFocusId, setCardFocusId] = useState<string | null>(null);

  /** The run whose removal is in flight. At most one at a time, by construction. */
  const [removingId, setRemovingId] = useState<string | null>(null);
  /** The last removal refusal, ADDRESSED TO THE RUN it was about. */
  const [removeError, setRemoveError] = useState<
    { runId: string; message: string; stale: boolean } | null
  >(null);
  /** Said on screen, in a live region, after a removal succeeds. */
  const [removeNote, setRemoveNote] = useState<string | null>(null);
  /**
   * True when a removal left no card for the caret to land on, so it goes to the
   * section's own furniture instead. See the effect that consumes it.
   */
  const [fallbackFocus, setFallbackFocus] = useState(false);

  const searchRef = useRef<HTMLInputElement>(null);
  const addRef = useRef<HTMLButtonElement>(null);

  const filtering = query !== '' || overridesFilter !== '' || exportedFilter !== '';

  /*
   * A GENERATION COUNTER, because a page can arrive after the criteria that asked
   * for it are gone. Type into the search box while a Load More is in flight and
   * the old page's `.then` would otherwise append runs from the PREVIOUS query
   * onto the new list — invisible in every test that does one thing at a time,
   * and exactly the kind of state a scientist would then read as a search result.
   */
  const generationRef = useRef(0);

  /*
   * The current runs, readable from an effect that must NOT re-run when they
   * change. The focus effect needs to know "is this run already on the page?"
   * and depending on the array would restart it on every append.
   */
  const runsRef = useRef<ApiRunView[]>([]);
  runsRef.current = list.status === 'data' ? list.loaded.runs : [];

  /*
   * A run this section just created, waiting for the reload it triggered.
   * Held in a ref rather than in state because the only reader is the reload's
   * own `.then`, and re-rendering on it would say nothing.
   *
   * IT CARRIES THE GENERATION OF THE READ IT IS WAITING FOR, and that is not
   * bookkeeping — it is the whole defence against a create HIJACKING a later,
   * unrelated read. The reload's `.then` used to return on a generation mismatch
   * BEFORE clearing this ref, so a create whose reload was superseded stayed
   * pending and was consumed by whatever landed next. Measured: Add Run on a
   * 120-run record, then type a search while the reload is in flight, and the
   * reader is thrown into Focus Run on `RUN121` with the query they just typed
   * silently discarded.
   *
   * Clearing the ref before the mismatch check would fix that case and open
   * another: a read issued BEFORE the create can land after it, and it would
   * throw away a create that is still legitimately pending on its own reload.
   * The generation says which read this run belongs to, so only that read — and
   * no other — can either consume it or drop it. `null` means "not yet claimed":
   * `addRun` sets the run, and the effect run it triggers stamps the generation.
   */
  const createdRef = useRef<{ run: ApiRunView; generation: number | null } | null>(null);

  /*
   * A run this section is about to focus and ALREADY HOLDS. The create response
   * carries the whole run, so re-reading it over HTTP purely to satisfy the focus
   * effect would be a request whose answer is already in memory — and one that
   * fails for its own reasons, turning a successful create into "no run with that
   * id is in this record". Consumed once, so a later focus on the same run still
   * reads the server.
   */
  const focusSeedRef = useRef<ApiRunView | null>(null);

  /*
   * A RELOAD AFTER A CREATE MUST NOT BLANK THE LIST. The reader just pressed a
   * button; replacing what they were looking at with a loading panel and then
   * putting it back is a worse answer than briefly showing the page they already
   * had. A criteria CHANGE still blanks, because there the old list is about to
   * be wrong and showing it is the dishonest option.
   */
  const silentRef = useRef(false);

  /*
   * THE CHANGE-FEED SIGNAL, AND THE THREE REFS THAT MAKE IT SAFE TO ACT ON.
   *
   * `activity` is a summary this screen already holds elsewhere on the record
   * screen, handed down as a prop rather than polled here — this section owns its
   * OWN fetch (see the file header) and stays that way; it only reacts to being
   * told something moved.
   *
   *   `lastRunsSignalKeyRef` — DEDUPE. The same `(highestRev, recordMoved, runIds)`
   *   triple twice must trigger nothing: the producer re-delivers the same summary
   *   on every poll until this screen's own rev catches up, and a card list is not
   *   something to silently re-fetch on every 8-second tick.
   *
   *   `runsReloadInFlightRef` — COALESCE. True from the moment the first-page fetch
   *   below leaves this component until its own response (or failure) is the
   *   authoritative one for its generation. A signal that arrives while it is true
   *   does not start a second request; it marks a follow-up instead.
   *
   *   `pendingSignalReloadRef` — the follow-up itself, consumed exactly once when
   *   the in-flight request settles, so N signals that arrive mid-flight produce
   *   AT MOST ONE extra request rather than N.
   */
  const lastRunsSignalKeyRef = useRef<string | null>(null);
  const runsReloadInFlightRef = useRef(false);
  const pendingSignalReloadRef = useRef(false);

  const setFocusRun = useCallback(
    (runId: string | null) => {
      /*
       * The repo's URL-state convention, copied exactly from `GovernancePage`,
       * `SettingsPage` and `ProjectMemory`: switch by COPYING the current
       * `URLSearchParams`, so `?view=graph` and anything else on the record URL
       * survives entering and leaving focus. `replace`, because focusing a run is
       * not a destination — pushing each focus and unfocus would bury the screen
       * the reader arrived from behind a stack of Back presses.
       */
      const next = new URLSearchParams(searchParams);
      if (runId === null) next.delete(RECORD_RUN_PARAM);
      else next.set(RECORD_RUN_PARAM, runId);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  /*
   * WRITING THE SELECTION BACK, by the same rule as `setFocusRun`: COPY the current
   * `URLSearchParams` so `?tab=`, `?view=` and `?run=` all survive, and `replace`
   * so choosing and unchoosing runs does not build a stack of Back presses between
   * the reader and the screen they arrived from.
   *
   * Every existing `compare` is deleted before the new set is appended. Mutating in
   * place would leave a stale repeat behind, and a repeated parameter is exactly
   * the shape where that is invisible until someone reads the URL.
   */
  const setCompareIds = useCallback(
    (ids: string[]) => {
      const next = new URLSearchParams(searchParams);
      next.delete(RECORD_COMPARE_PARAM);
      for (const id of ids) next.append(RECORD_COMPARE_PARAM, id);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  /*
   * ONE CARD'S TOGGLE. Selecting a run already selected takes it OUT — the same
   * gesture both ways, which is what `aria-pressed` on the control promises.
   *
   * A THIRD RUN IS REFUSED, NOT ABSORBED. Silently dropping one of the two already
   * chosen would answer a click with a change the reader did not ask for, and
   * silently comparing the first two of three would be the same defect the panel's
   * "this link names N runs" note exists to prevent. The card renders the refusal
   * as an `aria-disabled` control that says why; this is the second half of it, so
   * the rule holds even if a caller forgets to pass `compareFull`.
   */
  const compareIdsRef = useRef(compareIds);
  compareIdsRef.current = compareIds;
  const toggleCompare = useCallback(
    (runId: string) => {
      // Read through the ref rather than joining the ids into a dependency string:
      // a round trip through a delimiter is a second place for an id containing
      // that delimiter to break, and this file already reads live values this way
      // (`runsRef`, `loadedRef`).
      const current = compareIdsRef.current;
      if (current.includes(runId)) {
        setCompareIds(current.filter((id) => id !== runId));
        return;
      }
      if (current.length >= RUN_COMPARE_MAX) return;
      setCompareIds([...current, runId]);
    },
    [setCompareIds],
  );

  /*
   * The LATEST `setFocusRun`, for the one caller that is not a render: the
   * first-page read's `.then`, which may land long after the render that started
   * it. Calling the captured copy there would write a URL built from whichever
   * query parameters existed when the request left, silently dropping anything
   * that changed while it was in flight.
   */
  const setFocusRunRef = useRef(setFocusRun);
  setFocusRunRef.current = setFocusRun;

  // --- the first page, and every reset of it ------------------------------
  useEffect(() => {
    generationRef.current += 1;
    const generation = generationRef.current;
    if (createdRef.current !== null && createdRef.current.generation === null) {
      createdRef.current = { ...createdRef.current, generation };
    }
    /** Forget a create that was waiting on THIS read, now that this read is void. */
    const dropCreated = () => {
      if (createdRef.current !== null && createdRef.current.generation === generation) {
        createdRef.current = null;
      }
    };
    if (!silentRef.current) setList({ status: 'loading' });
    silentRef.current = false;
    setLoadingMore(false);
    setMoreError(null);

    /*
     * THIS EFFECT RUN'S OWN REQUEST IS NOW THE ONE IN FLIGHT. Every dependency
     * change re-enters this branch — a search, a filter, `reloadNonce` from Add
     * Run / Remove Run / a signal — so "in flight" here means exactly "this
     * component currently has an outstanding `listRuns` request", regardless of
     * what caused it. `runsSignalFollowUp` below reads it back once this request's
     * own response (or failure) has been accepted as authoritative for its
     * generation, never for a superseded one.
     */
    runsReloadInFlightRef.current = true;

    /**
     * Consume a pending signal-driven follow-up, if one arrived while this
     * request was outstanding. AT MOST ONE extra request per settle, never one
     * per signal — see `pendingSignalReloadRef`'s own comment.
     */
    const runsSignalFollowUp = () => {
      runsReloadInFlightRef.current = false;
      if (!pendingSignalReloadRef.current) return;
      pendingSignalReloadRef.current = false;
      silentRef.current = true;
      setReloadNonce((n) => n + 1);
    };

    let alive = true;
    api
      .listRuns(experimentId, {
        limit: RUNS_PAGE_SIZE,
        offset: 0,
        ...criteriaQuery(query, overridesFilter, exportedFilter),
      })
      .then((res) => {
        if (!alive || generation !== generationRef.current) {
          dropCreated();
          return;
        }
        runsSignalFollowUp();
        setExperimentVersion(res.experiment_version);
        setList({
          status: 'data',
          loaded: {
            runs: res.runs,
            received: res.runs.length,
            total: res.total,
            /*
             * `matched` FALLS BACK TO `total`, AND THE FALLBACK IS EXACT RATHER
             * THAN A GUESS. A server that does not report `matched` is a server
             * that does not implement the filter parameters either — it ignored
             * them and returned the whole list, for which "matching" and
             * "existing" are the same number by definition. The fallback is here
             * because this branch's own backend predates the filter half of the
             * contract; it is not licence to invent a count.
             */
            matched: res.matched ?? res.total,
          },
        });

        const pending = createdRef.current;
        if (pending === null || pending.generation !== generation) return;
        const created = pending.run;
        createdRef.current = null;
        if (res.runs.some((r) => r.id === created.id)) {
          // It is on the page the reader is looking at: put the caret on it and
          // leave the list alone.
          setCardFocusId(created.id);
        } else {
          /*
           * IT IS NOT ON THE FIRST PAGE, AND THIS IS THE CASE THAT WOULD OTHERWISE
           * LOOK LIKE A BROKEN BUTTON. Runs are ordered canonically, so a new run
           * is LAST — on a record with 320 runs it is on page seven, and clearing
           * the filters does nothing to make it visible. Focusing it shows the
           * reader the run they just asked for; leaving focus returns them to an
           * unfiltered list that really does contain it.
           */
          focusSeedRef.current = created;
          setFocusRunRef.current(created.id);
          setCardFocusId(created.id);
        }
      })
      .catch((err: unknown) => {
        dropCreated();
        if (!alive || generation !== generationRef.current) return;
        runsSignalFollowUp();
        setList({ status: 'error', error: asApiError(err) });
      });
    return () => {
      alive = false;
    };
    // The URL writer is reached through a ref, so entering or leaving focus does
    // NOT re-run the first-page read — the list a reader returns to has to be the
    // list they left, and refetching it would silently discard every page they
    // had loaded.
  }, [experimentId, query, overridesFilter, exportedFilter, reloadNonce]);

  /*
   * THE SIGNAL ITSELF — deciding whether `activity` means "reload the first page",
   * and never doing the reload here directly. Every actual fetch still goes
   * through the ONE effect above, by the same `reloadNonce` + `silentRef` path
   * `addRun`, `removeRun` and `reloadSection` already use — so a signal-driven
   * reload inherits everything that already makes those silent: cards keyed by id
   * are not remounted, autosave state (`lib/runAutosaveStore.ts`, keyed
   * `<experimentId>/<runId>`) is never touched here at all, and the search box and
   * filters are left exactly as they are, because this effect's dependencies do
   * not include them.
   *
   * A PROPOSAL-ONLY SIGNAL IS INVISIBLE HERE BY CONSTRUCTION, not by an explicit
   * check: `activity.runIds.length === 0 && !activity.recordMoved` is exactly
   * "nothing this section renders moved", the same distinction `needsCanonicalRefetch`
   * draws for the record bundle.
   *
   * ONLY THE FIRST PAGE IS EVER RE-READ. A reader who has pressed Load More several
   * times has pages beyond the first that this effect does not know about and does
   * not attempt to preserve — the existing Load More control re-fetches them, from
   * the new first page's `received` offset, exactly as it already does after any
   * other silent reload. Reconciling a signal against deep pagination would mean
   * this section tracking server-side state it does not own; the honest answer is
   * the one `runs-more-note` already gives for offset paging generally.
   */
  useEffect(() => {
    if (activity === null) return;
    if (activity.runIds.length === 0 && !activity.recordMoved) return;
    // No rev to compare against yet — the first load has not landed. Nothing is
    // marked consumed here, so this effect re-evaluates the same `activity` once
    // `experimentVersion` arrives (it is a dependency below).
    if (experimentVersion === null) return;

    const key = `${activity.highestRev}:${activity.recordMoved}:${activity.runIds.join(',')}`;
    // DEDUPE. The producer re-delivers the same summary every poll until this
    // screen's own rev catches up, and a repeat is not news a second time.
    if (key === lastRunsSignalKeyRef.current) return;

    // AT OR BELOW THIS SECTION'S OWN LOADED REV — covers this section's own Add
    // Run / Remove Run, which already adopted the version the signal is reporting,
    // and a replay of a batch this screen has already acted on for another reason.
    const dot = experimentVersion.lastIndexOf('.');
    const loadedRev = dot === -1 ? NaN : Number(experimentVersion.slice(dot + 1));
    if (Number.isFinite(loadedRev) && activity.highestRev <= loadedRev) {
      lastRunsSignalKeyRef.current = key;
      return;
    }

    lastRunsSignalKeyRef.current = key;

    if (runsReloadInFlightRef.current) {
      // COALESCE. One follow-up, consumed by `runsSignalFollowUp` above once the
      // in-flight request settles — not one request per signal that lands here.
      pendingSignalReloadRef.current = true;
      return;
    }
    silentRef.current = true;
    setReloadNonce((n) => n + 1);
  }, [activity, experimentVersion]);

  // --- one more page ------------------------------------------------------
  const loadMore = () => {
    if (list.status !== 'data' || loadingMore) return;
    const generation = generationRef.current;
    const offset = list.loaded.received;
    setLoadingMore(true);
    setMoreError(null);
    api
      .listRuns(experimentId, {
        limit: RUNS_PAGE_SIZE,
        offset,
        ...criteriaQuery(query, overridesFilter, exportedFilter),
      })
      .then((res) => {
        if (generation !== generationRef.current) return;
        setLoadingMore(false);
        setList((prev) => {
          if (prev.status !== 'data') return prev;
          /*
           * DEDUPE BY ID ON APPEND. Offset paging is not snapshot-consistent: a
           * run deleted between two reads shifts every later run one place
           * earlier, so the next page legitimately re-delivers a run already on
           * screen. Rendering it twice would give one run two cards, two autosave
           * readouts and two sets of controls over the same document — and React
           * would warn about the duplicate key and then render it anyway.
           */
          const seen = new Set(prev.loaded.runs.map((r) => r.id));
          const fresh = res.runs.filter((r) => !seen.has(r.id));
          const nextRuns = [...prev.loaded.runs, ...fresh];
          if (fresh.length > 0) {
            /*
             * FOCUS AFTER LOAD MORE. If the button survives, focus is already on
             * it and moving it would fight the reader. If this page was the last
             * one, the button is about to be removed from under their fingers —
             * that is the case where focus is genuinely lost, so it goes to the
             * first newly loaded run instead of to the top of the page.
             */
            const done = prev.loaded.received + res.runs.length >= prev.loaded.matched;
            if (done) setCardFocusId(fresh[0].id);
          }
          return {
            status: 'data',
            loaded: {
              ...prev.loaded,
              runs: nextRuns,
              received: prev.loaded.received + res.runs.length,
              total: res.total,
              matched: res.matched ?? res.total,
            },
          };
        });
      })
      .catch((err: unknown) => {
        if (generation !== generationRef.current) return;
        setLoadingMore(false);
        // The runs already loaded are deliberately left alone. A failed page is a
        // failed page, not a reason to throw away the ones that arrived.
        setMoreError(
          err instanceof Error ? err.message : 'The next page of runs could not be loaded.',
        );
      });
  };

  // --- debounce -----------------------------------------------------------
  useEffect(() => {
    const trimmed = searchText.trim();
    if (trimmed === query) return;
    const timer = setTimeout(() => setQuery(trimmed), RUN_SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchText, query]);

  // --- focus run ----------------------------------------------------------
  useEffect(() => {
    if (focusRunId === null || focusRunId === '') {
      setFocus({ status: 'idle' });
      return;
    }
    // A focused run is always shown open — the reader asked for this one run.
    setExpanded((prev) => (prev[focusRunId] === true ? prev : { ...prev, [focusRunId]: true }));
    setCardFocusId(focusRunId);

    if (runsRef.current.some((r) => r.id === focusRunId)) {
      setFocus({ status: 'page' });
      return;
    }
    const seed = focusSeedRef.current;
    if (seed !== null && seed.id === focusRunId) {
      focusSeedRef.current = null;
      setFocus({ status: 'fetched', run: seed });
      return;
    }
    /*
     * NOT ON THE LOADED PAGE, SO READ IT DIRECTLY. With a bounded list this is
     * the ORDINARY case for a deep link — the run the URL names is simply
     * further down than the first page — and "no such run" would be a false
     * statement about a run that exists. A deep-linked focus therefore costs one
     * extra request even when the run turns out to be on the first page, because
     * this effect runs before that page has arrived; that is a request, not a
     * wrong answer, and the alternative (waiting for the list before resolving
     * the URL) delays the one thing the reader asked for.
     */
    let alive = true;
    setFocus({ status: 'loading' });
    api
      .getRun(experimentId, focusRunId)
      .then((res) => {
        if (alive) setFocus({ status: 'fetched', run: res.run });
      })
      .catch((err: unknown) => {
        if (alive) setFocus({ status: 'missing', error: asApiError(err) });
      });
    return () => {
      alive = false;
    };
  }, [experimentId, focusRunId]);

  /*
   * WHERE FOCUS LANDS WHEN THE CARD IS NOT THERE TO TAKE IT. Leaving focus asks
   * for the caret to go back to the run's own card in the list; if that run is
   * not in the loaded page (it was reached by deep link, or by a create that
   * pushed it past the first page) there is no card, and the caret would be left
   * on a button that no longer exists — which drops it to the top of the
   * document. The search box is the section's first control and a stable place
   * to be.
   */
  useEffect(() => {
    if (cardFocusId === null || focusRunId !== null) return;
    if (list.status !== 'data') return;
    if (list.loaded.runs.some((r) => r.id === cardFocusId)) return;
    searchRef.current?.focus();
    setCardFocusId(null);
  }, [cardFocusId, focusRunId, list]);

  /*
   * ONE RUN IS REPLACED BY ID, and never by position. Two runs on one screen
   * each hold their own autosave state, their own version and their own edits;
   * a splice by index would attach one run's server response to whichever card
   * happened to be in that slot.
   */
  const replaceRun = useCallback((next: ApiRunView) => {
    setList((prev) =>
      prev.status === 'data'
        ? {
            status: 'data',
            loaded: {
              ...prev.loaded,
              runs: prev.loaded.runs.map((r) => (r.id === next.id ? next : r)),
            },
          }
        : prev,
    );
    // The directly-read focused run is a second copy of the same document and has
    // to move with it, or a save would be reflected in a list the reader cannot
    // currently see while the card in front of them showed the old value.
    setFocus((prev) =>
      prev.status === 'fetched' && prev.run.id === next.id ? { status: 'fetched', run: next } : prev,
    );
  }, []);

  const clearCriteria = () => {
    setSearchText('');
    setQuery('');
    setOverridesFilter('');
    setExportedFilter('');
  };

  const addRun = () => {
    if (experimentVersion === null) return;
    setAdding(true);
    setAddError(null);
    setAddStale(false);
    setAddNote(null);
    api
      .createRun(experimentId, { experimentVersion })
      .then((res) => {
        setAdding(false);
        setExperimentVersion(res.experiment_version);
        setExpanded((prev) => ({ ...prev, [res.run.id]: true }));
        /*
         * CREATING A RUN WHILE A SEARCH OR FILTER IS ACTIVE IS A REAL CONFLICT,
         * and both of the obvious answers are dishonest. A new run holds no
         * overrides and no record id, so it usually does NOT match — appending it
         * anyway would put a run in a filtered list that the filter excludes, and
         * dropping it would make the button look like it did nothing.
         *
         * So the criteria are CLEARED and the first page re-read. The cleared
         * boxes are how the reader is told, and the note below says it in words
         * so the change is not something they have to notice.
         */
        if (filtering) {
          setAddNote(
            'The search and filters were cleared so the new run is not hidden by them. ' +
              'A run created now matches neither an override filter nor an export filter.',
          );
          clearCriteria();
        }
        createdRef.current = { run: res.run, generation: null };
        silentRef.current = true;
        setReloadNonce((n) => n + 1);
      })
      .catch((err: unknown) => {
        setAdding(false);
        // The message is whatever could be ESTABLISHED. A 412 is named as what
        // it is — this experiment moved on — because the remedy differs from
        // every other failure: reload, do not retry.
        const status = err instanceof ApiError ? err.status : undefined;
        if (status === 412) {
          /*
           * "SOMEWHERE ELSE" WAS OFTEN THIS SCREEN, AND OFTEN THIS READER.
           *
           * `experimentVersion` is captured once and advanced only by a successful
           * create or a list read, while ANY experiment mutation bumps `exp.rev` —
           * and the Assistant panel mounted on this same screen writes through
           * `submitAnswer`/`editField`. RunsSection is not in the poller's refresh
           * path, so the sequence "confirm an Assistant proposal, then click Add
           * Run" produced a message blaming an unnamed third party for a change the
           * reader had just made, seconds earlier, a few hundred pixels away.
           *
           * And the remedy overstated what is needed: this section owns its own
           * fetch, so re-reading it is enough. `Reload This Section` re-runs the
           * first-page read and adopts the current `experiment_version` — no page
           * reload, no lost scroll position, and nothing typed elsewhere on the
           * screen is discarded.
           */
          setAddStale(true);
          setAddError(
            'The experiment has changed since this list was loaded, so the run was not created — ' +
              'this can be your own edit elsewhere on this screen. Reload this section to pick up ' +
              'the current version, then add the run again.',
          );
          return;
        }
        /* THE SERVER'S OWN SENTENCE WHEN IT WROTE ONE. `POST /runs` refuses with
           `409 already_exported_without_runs` on a record already exported under its
           own identity, and that body explains why: adding a run would move the
           exported identity onto the run and publish a second official record with the
           same science, and nothing withdraws the first. Before this, it surfaced as the
           bare "Request failed (409)." — a click whose only outcome was an unexplained
           refusal, which is precisely the residual this file names as a defect for
           Remove. Measured by an independent review on the exported worked example. */
        const explained = serverRefusalMessage(err);
        if (explained !== null) {
          setAddError(explained);
          return;
        }
        // A session that ended is named as such — the run was not created, and
        // the remedy is signing in again rather than retrying the form.
        setAddError(
          mutationFailureCopy(
            err,
            err instanceof Error ? err.message : 'The run could not be created.',
          ),
        );
      });
  };

  const reloadSection = () => {
    setAddError(null);
    setAddStale(false);
    setRemoveError(null);
    setReloadNonce((n) => n + 1);
  };

  /*
   * REMOVING ONE RUN, AND THE FOUR THINGS THAT HAVE TO RECOVER WITH IT.
   *
   * The removal itself is one request. What makes this longer than `addRun` is
   * that a run is referenced by four pieces of state that outlive its card, and
   * every one of them would otherwise be left pointing at a run the server has
   * forgotten:
   *
   *   1. FOCUS RUN is a query parameter. Removing the focused run would leave the
   *      reader on `?run=<dead id>`, which resolves to "No run with that id is in
   *      this record" — a true sentence, arrived at by the app's own action, over a
   *      screen the reader cannot get out of except by pressing Back.
   *   2. THE COMPARISON SELECTION is also in the URL and also by id.
   *   3. AUTOSAVE STATE lives in a module map keyed `<experimentId>/<runId>` and is
   *      disposed only when the record screen goes away.
   *   4. THE KEYBOARD CARET is on a control inside a card that is about to
   *      disappear. Left alone it drops to the top of the document.
   *
   * SEARCH AND FILTERS ARE DELIBERATELY LEFT ALONE, which is the opposite of what
   * `addRun` does. A create can produce a run the current criteria exclude, so the
   * criteria have to be cleared or the button looks broken. A removal cannot: the
   * remaining runs match exactly what they matched before. Clearing here would
   * throw away a search the reader is in the middle of, for no reason. The list is
   * re-read with the SAME criteria, so both counts move and an empty result still
   * offers its own Clear control.
   */
  const removeRun = useCallback(
    (run: ApiRunView): Promise<void> => {
      if (experimentVersion === null) return Promise.resolve();
      setRemovingId(run.id);
      setRemoveError(null);
      setRemoveNote(null);
      return api
        .removeRun(experimentId, run.id, { experimentVersion })
        .then((res) => {
          setRemovingId(null);
          setExperimentVersion(res.experiment_version);
          // (3) — stop reporting on a run that no longer exists.
          disposeRun(experimentId, run.id);

          // (2) — take it out of the comparison, or the panel keeps resolving a
          // dead id and renders its own not-found state about the app's own act.
          const selected = compareIdsRef.current;
          if (selected.includes(run.id)) {
            setCompareIds(selected.filter((id) => id !== run.id));
          }
          setExpanded((prev) => {
            if (!(run.id in prev)) return prev;
            const next = { ...prev };
            delete next[run.id];
            return next;
          });

          // (1) and (4). The successor is read from the page the reader is looking
          // at, BEFORE the reload replaces it, because that is the list the caret
          // is currently in. The run below is preferred over the run above for the
          // reason a list does: it now occupies the position the removed run held.
          const onPage = runsRef.current;
          const index = onPage.findIndex((r) => r.id === run.id);
          const successor =
            index === -1 ? undefined : onPage[index + 1] ?? onPage[index - 1];
          if (focusRunId === run.id) {
            setFocusRunRef.current(null);
            setCardFocusId(null);
            setFallbackFocus(true);
          } else if (successor !== undefined) {
            setCardFocusId(successor.id);
          } else {
            setCardFocusId(null);
            setFallbackFocus(true);
          }

          /*
           * WHAT THE NOTE MAY SAY. The counts are the SERVER's — `remaining_run_count`
           * — never a number this component decremented, because the list it is
           * holding may already be out of date. The asset clause is stated only when
           * there were any, and it says associations ended, not that files were
           * deleted: nothing here deletes a file, and this application has never
           * opened one.
           */
          const dropped = res.asset_references_dropped.length;
          /*
           * THE NUMBERING CLAUSE READS THE SERVER'S FLAG, it does not restate this
           * build's expectation. `ordinals_compacted` is `false` today and the
           * sentence would become false the day it is not, which is exactly the
           * kind of copy this project keeps finding stale. It is also withheld
           * entirely when nothing remains: "the others keep their numbers" is not
           * a statement about an empty set worth making.
           */
          const numbering =
            res.remaining_run_count === 0
              ? ''
              : res.ordinals_compacted
                ? ' The remaining runs were renumbered.'
                : ' The others keep their numbers.';
          setRemoveNote(
            `Removed ${res.removed_run_label}. ` +
              `${res.remaining_run_count} ${res.remaining_run_count === 1 ? 'run' : 'runs'} ` +
              `remain in this record.` +
              numbering +
              (dropped === 0
                ? ''
                : ` It no longer cites ${dropped} ${dropped === 1 ? 'file' : 'files'};` +
                  ` the record still lists ${dropped === 1 ? 'it' : 'them'}.`),
          );

          silentRef.current = true;
          setReloadNonce((n) => n + 1);
        })
        .catch((err: unknown) => {
          setRemovingId(null);
          const status = err instanceof ApiError ? err.status : undefined;
          if (status === 412) {
            setRemoveError({
              runId: run.id,
              message:
                'The record has changed since this list was loaded, so the run was not ' +
                'removed — this can be your own edit elsewhere on this screen. Reload this ' +
                'section to pick up the current version, then remove the run again.',
              stale: true,
            });
            return;
          }
          if (status === 409) {
            /*
             * THE COPY IS OURS, NOT THE SERVER'S, and that is a deliberate
             * narrowing rather than an oversight. `mutationError` parses a refusal
             * body only for 400/412/422, so `err.message` here is the bare
             * "Request failed (409)." — and widening that shared seam to reach one
             * screen is a change every other 409 consumer would inherit.
             *
             * WRITING OUR OWN IS SAFE HERE BECAUSE THIS ROUTE HAS EXACTLY ONE 409.
             * It is `run_exported`.
             *
             * IT SAYS *WHETHER*, NOT *WHEN*, AND THE EARLIER VERSION SAID WHEN.
             * This copy used to read "...has been exported ... SINCE THIS LIST WAS
             * LOADED", justified by the argument that the card only offers the
             * control when the run carries no `record_id`, so an export must have
             * happened after the read. THAT ARGUMENT IS INVALID, and it is invalid
             * because of the very guard this slice added: `_run_published_stem`
             * also refuses on the DISK-ONLY arm, where a record and/or sidecar sit
             * in `records/` under the run's own id and no `record_id` was ever
             * persisted. In that state `GET .../runs` reports `record_id: null`,
             * `RunCard` therefore renders Remove, the click returns 409 — and the
             * export happened BEFORE the list was read, not after.
             *
             * So the temporal clause was a claim this client cannot make, on a
             * destructive-action surface, and an independent review demonstrated the
             * state that falsifies it. The sentence now asserts only what the 409
             * itself establishes: an official record for this run exists NOW. Whether
             * it appeared before or after the read is not knowable here, and is not
             * claimed.
             *
             * `stale: false`, so NO `Reload This Section` remedy — and that is right
             * for a reason worth writing down, because "offer the reload" is the
             * reflex. On the disk-only arm a reload changes nothing: the run view
             * still reports `record_id: null`, so the list comes back identical and
             * the control comes back too. Offering a remedy that cannot remedy is the
             * same defect in a different place.
             *
             * KNOWN RESIDUAL, NAMED RATHER THAN IMPLIED FIXED. On that arm the card
             * goes on offering Remove, because `RunCard` gates the control on
             * `run.record_id === null` and that is all the run view exposes. So this
             * surface can offer a control whose only outcome is a refusal — which is
             * the written rule this file cites when it withholds Remove from a run
             * that DOES carry a `record_id`. Closing it properly means the run view
             * carrying the disk-only fact the server already computes in
             * `_run_published_stem`, which is an API contract change and its own
             * slice. The refusal is correct and nothing is destroyed; what is wrong
             * is that the affordance is offered. Not fixed here, and not pretended
             * fixed.
             */
            setRemoveError({
              runId: run.id,
              message:
                'An official ISAAC record for this run already exists, so it was not ' +
                'removed. A published record is never rewritten, and the run is what ' +
                'keeps it claimed. Reloading will not change this.',
              stale: false,
            });
            return;
          }
          setRemoveError({
            runId: run.id,
            message: mutationFailureCopy(
              err,
              err instanceof Error ? err.message : 'The run could not be removed.',
            ),
            stale: false,
          });
        });
    },
    [experimentId, experimentVersion, focusRunId, setCompareIds],
  );

  /*
   * WHERE THE CARET GOES WHEN A REMOVAL LEFT NO CARD FOR IT.
   *
   * Two cases reach this: the removed run was the focused one (so the whole
   * focused view is gone), or it was the last run on the page (so there is no
   * neighbour). The search box is the section's first control and is the same
   * landing place the deep-link recovery below already uses — but it is WITHHELD
   * from a record with no runs, so `Add Run` is the fallback's fallback. It waits
   * for the list to settle, because both controls are gated on a loaded list.
   */
  useEffect(() => {
    if (!fallbackFocus || list.status !== 'data') return;
    const target = searchRef.current ?? addRef.current;
    if (target === null) {
      /*
       * IT WAITS RATHER THAN GIVING UP, and this branch is here because the first
       * version did give up. Removing the FOCUSED run sets this flag in the same
       * handler that leaves focus mode, and the effect ran first — while the
       * focused view still owned the screen, where neither the search box nor
       * `Add Run` is rendered (the toolbar shows "Back to all runs" instead). Both
       * refs were null, the flag was consumed, and the caret was left on the
       * document body: the exact outcome this whole path exists to prevent.
       *
       * So the flag survives until the furniture is there. It is dropped only when
       * the section is out of focus mode AND still has nothing to focus, which is
       * a genuine dead end rather than a moment too early.
       */
      if (focusRunId !== null) return;
      setFallbackFocus(false);
      return;
    }
    setFallbackFocus(false);
    target.focus();
  }, [fallbackFocus, list, focusRunId]);

  const focused = focusRunId !== null && focusRunId !== '';
  const loaded = list.status === 'data' ? list.loaded : null;

  /*
   * THE FOCUSED RUN IS RESOLVED ONCE, HERE, because two surfaces describe it and
   * they were allowed to disagree. `FocusedRun` decided for itself whether the
   * run existed, while the count line asked only whether a run id was in the URL
   * — so a deep link to an id that is not in the record rendered the alert "No
   * run with the id NOPE is in this record" and, at the same moment, announced
   * "Viewing one run · 120 runs in this record". Two statements about one screen,
   * one of them false, and the false one is the one a screen reader speaks.
   */
  const focusedRun = !focused
    ? undefined
    : focus.status === 'fetched'
      ? focus.run
      : loaded?.runs.find((r) => r.id === focusRunId);

  /*
   * BRING THE ADDRESS A COMPARISON LINKED TO INTO VIEW, and mark it.
   *
   * `RunInheritedPanel` already renders `data-address` on every resolved row, so
   * this needs no change there and no new contract between the two: it queries the
   * attribute the panel already publishes. `focusedRun` is in the dependencies
   * because the card is not in the DOM until the run resolves — a deep link's read
   * lands after the first paint, and scrolling before it would scroll to nothing.
   *
   * EVERY PART OF IT IS OPTIONAL BEHAVIOUR AND NONE OF IT CHANGES WHAT IS SHOWN.
   * An address the run does not render finds no element and does nothing;
   * `scrollIntoView` is feature-detected because jsdom does not implement it; the
   * mark is removed on cleanup so a second link does not leave two.
   */
  useEffect(() => {
    if (!focused || focusAddress === null || focusAddress === '' || focusedRun === undefined) {
      return;
    }
    const target = document.querySelector(
      `[data-address="${CSS.escape(focusAddress)}"]`,
    );
    if (target === null) return;
    target.setAttribute('data-linked-address', 'true');
    if (typeof (target as HTMLElement).scrollIntoView === 'function') {
      (target as HTMLElement).scrollIntoView({ block: 'center' });
    }
    return () => {
      target.removeAttribute('data-linked-address');
    };
  }, [focused, focusAddress, focusedRun]);

  const countFocus: CountFocus = !focused
    ? 'none'
    : focus.status === 'loading'
      ? 'loading'
      : focusedRun === undefined
        ? 'missing'
        : 'viewing';

  /*
   * THE CONTROLS SURVIVE THEIR OWN REQUEST, and this ref is the whole reason.
   *
   * The controls row was gated on `loaded !== null`, and a criteria change sets the
   * list to `loading` — so typing in the search box made the search box DISAPPEAR
   * ~300 ms later and come back when the response landed, taking the caret with it.
   * A scientist typing a second term mid-search would find the field gone; the
   * keystrokes would go nowhere.
   *
   * It was invisible to every test because no test typed while a request was in
   * flight, and invisible in local development because the stub answers instantly.
   * It surfaced only when a test deliberately HELD a response open to exercise the
   * out-of-order guard — the race the test was written for was fine; the box was not.
   *
   * So the controls read the LAST loaded snapshot rather than the current one. They
   * are a stable frame around a list that is allowed to blank: `runsShown` below
   * still uses `loaded`, so the list itself shows its loading state honestly. Only
   * the furniture persists, and only after a first successful read — before that
   * there is genuinely nothing to search.
   */
  const lastLoadedRef = useRef<typeof loaded>(null);
  if (loaded !== null) lastLoadedRef.current = loaded;
  const controlsFrame = loaded ?? lastLoadedRef.current;

  /*
   * "THE FIRST PAGE HAS SETTLED" — and it LATCHES, which is the point.
   *
   * `RunCompare` waits for this before reading a deep-linked run directly, so that
   * a run the page is about to deliver is not also requested by id. A criteria
   * change sets the list back to `loading`, so the un-latched form would flip
   * true → false → true on every search; the panel's resolution effect would tear
   * down mid-flight and re-issue the same read on the way back. Whether the first
   * page has EVER arrived is the question being asked, and it only has one answer
   * per mount. The browser is keyed on the experiment, so switching records
   * rebuilds this with the rest of the state.
   */
  const listSettledRef = useRef(false);
  if (list.status !== 'loading') listSettledRef.current = true;

  return (
    <>
      {/*
        THE TOOLBAR IS THE SECOND PIECE OF FURNITURE THAT MUST OUTLIVE A READ, and
        for a sharper reason than the controls row below it: it holds the LIVE
        REGION. It was gated on `loaded !== null`, so a search or a filter change
        — which sets the list to `loading` — destroyed the `aria-live` node and
        built a new one when the response landed. A live region that arrives
        carrying its own content is generally not announced, so the one count
        change a reader most needs spoken, the one their own search caused, was
        the one least likely to be spoken. The comment below this claimed the node
        "survives … searching and paging"; measured, it did not.

        SO THE TOOLBAR FOLLOWS THE SNAPSHOT AND `Add Run` DOES NOT. The contract
        that `Add Run` appearing means the runs are loaded is relied on by this
        repo's unit and browser specs, and by every reader who would otherwise be
        offered a create with no experiment version to send. It stays gated on the
        LIVE `loaded`; only the region that has to persist persists.
      */}
      {controlsFrame !== null && (
      <div className="runs-toolbar">
        {loaded !== null &&
          (focused ? (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                // The list the reader had is untouched — focus never changed the
                // search or the filters, so leaving it returns them to exactly it.
                setCardFocusId(focusRunId);
                setFocusRun(null);
              }}
            >
              Back to all runs
            </button>
          ) : (
            <button
              ref={addRef}
              type="button"
              className="btn btn-primary"
              onClick={addRun}
              disabled={adding || experimentVersion === null}
            >
              <Plus size={15} strokeWidth={2.2} aria-hidden="true" />
              {adding ? 'Adding Run…' : 'Add Run'}
            </button>
          ))}
        {/*
          THE COUNTS, AND THE ONE ELEMENT THAT ANNOUNCES THEM.

          It is rendered in EVERY mode and at the same position, so the DOM node
          survives entering focus, leaving focus, searching and paging — a live
          region that is unmounted and remounted with its new text is not reliably
          announced, which would make the announcement present in the markup and
          absent in practice.

          IT GOES BLANK MID-READ RATHER THAN HOLDING ITS LAST NUMBERS, which is the
          one place this differs from the controls row. The controls can honestly
          show the last snapshot — a search box is a search box — but a count is a
          claim about a list that is, at that moment, not on screen. Blank also
          costs nothing in announcements: emptying a live region says nothing, so
          the reader hears exactly one utterance per search, the answer.

          `aria-live` rather than `role="status"` deliberately: this is a label for
          the list below it, not a transient status message, and the record screen
          already carries several `status` regions (one per run card) that an
          unnamed extra one would sit among.
        */}
        <p className="runs-count" aria-live="polite" aria-atomic="true">
          {countLine(loaded, filtering, countFocus)}
        </p>
      </div>
      )}

      {/*
        The controls are withheld from a record with no runs at all. Searching and
        filtering nothing is not a feature, and the empty state below says the one
        thing there is to say.
      */}
      {!focused && controlsFrame !== null && (controlsFrame.total > 0 || filtering) && (
        <div className="runs-controls">
          <div className="runs-control">
            <label className="runs-control-label" htmlFor={searchId}>
              Search runs
            </label>
            <input
              ref={searchRef}
              id={searchId}
              className="run-input"
              type="search"
              value={searchText}
              aria-describedby={searchHintId}
              onChange={(e) => setSearchText(e.target.value)}
            />
            {/*
              WHAT IT SEARCHES, STATED, because the honest scope is much narrower
              than a search box implies. The server matches a literal,
              case-insensitive substring of the run's label, its id and its
              exported record id, plus the run number when the whole query is
              digits. It does not read field values, it is not fuzzy, and it is
              not semantic — and a scientist who assumed any of those would read
              an empty result as "no run recorded that temperature".
            */}
            <span className="runs-control-hint" id={searchHintId}>
              Matches a run&apos;s name, number, id, or the id of the record it exported to.
              Not the scientific values inside a run.
            </span>
          </div>

          <div className="runs-control">
            <label className="runs-control-label" htmlFor={overridesId}>
              Overrides
            </label>
            <select
              id={overridesId}
              className="run-input"
              value={overridesFilter}
              onChange={(e) => setOverridesFilter(e.target.value as OverridesFilter)}
            >
              <option value="">Any run</option>
              <option value="any">Has an override</option>
              <option value="none">Has no override</option>
            </select>
          </div>

          <div className="runs-control">
            <label className="runs-control-label" htmlFor={exportedId}>
              Export
            </label>
            <select
              id={exportedId}
              className="run-input"
              value={exportedFilter}
              onChange={(e) => setExportedFilter(e.target.value as ExportedFilter)}
            >
              <option value="">Any run</option>
              <option value="true">Exported</option>
              <option value="false">Not exported</option>
            </select>
          </div>

          {filtering && (
            <button type="button" className="btn btn-secondary" onClick={clearCriteria}>
              Clear search and filters
            </button>
          )}
        </div>
      )}

      {/*
        MOUNTED IN EVERY STATE, AND OUTSIDE EVERY GATE ABOVE, because it owns a live
        region. A region that is unmounted and rebuilt carrying its content is not
        reliably announced — the defect measured on this section's own toolbar and
        fixed there. Gating this on `loaded !== null` would rebuild it on every
        search, which is precisely when the reader most needs to be told what
        happened to their selection.

        It renders nothing at all when no run is selected, and it is `hidden` while
        Focus Run owns the screen: a comparison needs two runs, and the focused view
        shows one.

        `loaded?.runs` and NOT the last snapshot: the panel keeps its own copy of a
        selected run (see its note on `fetched`), so it needs the LIVE page in order
        to prefer a run that is still on it — an edit saved through a card is then
        reflected here rather than being masked by a stale frame.
      */}
      <RunCompare
        experimentId={experimentId}
        compareIds={compareIds}
        loadedRuns={loaded?.runs ?? []}
        listReady={listSettledRef.current}
        hidden={focused}
        onSetCompareIds={setCompareIds}
      />

      {addNote !== null && (
        <p className="runs-note" role="status">
          {addNote}
        </p>
      )}

      {/*
        A REMOVAL IS ANNOUNCED IN WORDS, not only by a card disappearing. The caret
        has just moved to a different control, and a reader who cannot see the list
        would otherwise have nothing but silence to tell them the destructive act
        they confirmed actually happened. `role="status"` rather than `alert`: it
        is the successful outcome of something they asked for, not a problem.

        THE REFUSAL IS NOT HERE. It is rendered inside the card's own confirmation
        panel and associated with the button that caused it, because that is where
        the reader is and because a banner at the top of a fifty-card list is not a
        thing a keyboard reader will find.
      */}
      {removeNote !== null && (
        <p className="runs-note" role="status">
          {removeNote}
        </p>
      )}

      {addError !== null && (
        <div className="runs-error" role="alert">
          <p>{addError}</p>
          {addStale && (
            <button type="button" className="btn btn-secondary" onClick={reloadSection}>
              Reload This Section
            </button>
          )}
        </div>
      )}

      {list.status === 'loading' && <LoadingPanel label="Loading this experiment's runs…" />}
      {list.status === 'error' && <BackendDown error={list.error} onRetry={reloadSection} />}

      {loaded !== null &&
        (focused ? (
          <FocusedRun
            experimentId={experimentId}
            focusRunId={focusRunId}
            focus={focus}
            run={focusedRun}
            cardFocusId={cardFocusId}
            onCardFocused={() => setCardFocusId(null)}
            expanded={expanded[focusRunId] ?? true}
            onToggle={() =>
              setExpanded((prev) => ({ ...prev, [focusRunId]: !(prev[focusRunId] ?? true) }))
            }
            onRun={replaceRun}
            onRemove={removeRun}
            removingId={removingId}
            removeError={removeError}
            onReloadSection={reloadSection}
            onLeave={() => {
              setCardFocusId(focusRunId);
              setFocusRun(null);
            }}
          />
        ) : loaded.runs.length === 0 ? (
          <EmptyRuns total={loaded.total} filtering={filtering} onClear={clearCriteria} />
        ) : (
          <>
            <div className="runs-list">
              {loaded.runs.map((run) => (
                <RunCard
                  key={run.id}
                  experimentId={experimentId}
                  run={run}
                  expanded={expanded[run.id] ?? false}
                  onToggle={() =>
                    setExpanded((prev) => ({ ...prev, [run.id]: !(prev[run.id] ?? false) }))
                  }
                  onRun={replaceRun}
                  focusOnMount={cardFocusId === run.id}
                  onFocused={() => setCardFocusId(null)}
                  onFocusRun={() => setFocusRun(run.id)}
                  onCompare={() => toggleCompare(run.id)}
                  comparing={compareIds.includes(run.id)}
                  compareFull={compareIds.length >= RUN_COMPARE_MAX}
                  onRemove={() => removeRun(run)}
                  removing={removingId === run.id}
                  removeError={
                    removeError !== null && removeError.runId === run.id ? removeError : null
                  }
                  onReloadSection={reloadSection}
                />
              ))}
            </div>

            {moreError !== null && (
              <p className="runs-error" role="alert">
                {moreError} The {loaded.runs.length} runs already loaded are unchanged.
              </p>
            )}

            {/*
              THE GATE IS THE CURSOR, NOT THE LIST LENGTH, and the two are not the
              same number the moment a page re-delivers a run. It read
              `runs.length < matched` while paging from `received`; the dedupe
              drops a repeated run from the array but not from what the server has
              handed over, so after ONE duplicate `runs.length` trails `received`
              permanently and the condition can never close. Measured on the
              dedupe fixture: click three requests offset 120, and so does click
              four, and click eight — the same empty window, forever, with no
              message and nothing changing on screen. Reachable whenever a run is
              created or deleted while a reader pages.

              `received >= matched` is the server's own statement that the cursor
              has reached the end of what matches, which is exactly the question
              the button answers.
            */}
            {loaded.received < loaded.matched ? (
              <div className="runs-more">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={loadMore}
                  disabled={loadingMore}
                >
                  {loadingMore ? 'Loading more runs…' : 'Load more runs'}
                </button>
                {/*
                  THE HONEST LIMIT OF OFFSET PAGING, ON SCREEN AND NOT ONLY IN A
                  COMMENT. Each page is an independent read, so a run added or
                  removed while the reader pages shifts the window: a repeat is
                  discarded by the append, but a run that moves from an unread
                  page to an already-read one is simply never seen. Nothing here
                  can detect that, so the reader is told rather than being left to
                  trust a list that quietly cannot promise completeness.
                */}
                <span className="runs-more-note">
                  Pages are read one after another, not as one snapshot. If a run is added or
                  removed while you are loading more, this list can miss it — reload the record
                  for a fresh read.
                </span>
              </div>
            ) : (
              loaded.runs.length < loaded.matched && (
                /*
                 * THE MISS THE NOTE ABOVE WARNED ABOUT, ONCE IT HAS ACTUALLY
                 * HAPPENED. Every page has been read and fewer distinct runs
                 * arrived than match — which is the same shifted-window event the
                 * dedupe absorbs, seen from the other end: a run delivered twice
                 * is a run never delivered. The old gate hid this behind a button
                 * that re-read the same empty window; withdrawing the button
                 * without saying why would hide it behind silence instead, and
                 * this is the one moment the reader can act on it.
                 */
                <div className="runs-more">
                  <span className="runs-more-note">
                    All pages have been read, but {loaded.matched - loaded.runs.length} matching{' '}
                    {loaded.matched - loaded.runs.length === 1 ? 'run' : 'runs'} never arrived.
                    Pages are read one after another, not as one snapshot, so a run added or
                    removed while you were loading can shift out of every window — reload the
                    record for a fresh read.
                  </span>
                </div>
              )
            )}
          </>
        ))}
    </>
  );
}

/** The three criteria, as the query the API client expects. */
function criteriaQuery(
  query: string,
  overridesFilter: OverridesFilter,
  exportedFilter: ExportedFilter,
) {
  return {
    ...(query === '' ? {} : { q: query }),
    ...(overridesFilter === '' ? {} : { overrides: overridesFilter }),
    ...(exportedFilter === '' ? {} : { exported: exportedFilter === 'true' }),
  };
}

/**
 * What focus mode has actually resolved to — not merely whether a run id is in
 * the URL, which is what the count line used to ask.
 */
type CountFocus = 'none' | 'loading' | 'viewing' | 'missing';

/**
 * THE COUNT LINE — the sentence this slice is most able to make dishonest.
 *
 * TWO NUMBERS, NEVER ONE. `matched` is how many runs satisfy the current search
 * and filters; `total` is how many runs the record HAS. The toolbar used to read
 * `{runs.length} runs`, which was true only while the list was the whole list —
 * the moment it became a page, that string claimed a record had fifty runs when
 * it had three hundred and twenty. So the loaded count is always stated as a
 * count OF something, and when a filter is narrowing the list the record's own
 * total is stated beside it rather than replaced by it.
 *
 * Focus mode says the same thing from the other side: one run is on screen, and
 * the record's total is still named, so "Viewing one run" can never be mistaken
 * for "this record has one run".
 *
 * AND IT SAYS "VIEWING" ONLY WHEN A RUN IS BEING VIEWED. This branched on whether
 * the URL named a run, so a deep link to an id that does not resolve announced
 * "Viewing one run" over a panel that read "No run with the id NOPE is in this
 * record" — the alert and the live region contradicting each other about the same
 * screen. A run that is still being read is not being viewed either, and saying so
 * early would be the same defect a moment sooner.
 */
function countLine(loaded: Loaded | null, filtering: boolean, focus: CountFocus): string {
  if (loaded === null) return '';
  const runWord = loaded.total === 1 ? 'run' : 'runs';
  if (focus === 'viewing') {
    return `Viewing one run · ${loaded.total} ${runWord} in this record`;
  }
  if (focus === 'loading') {
    return `Loading one run · ${loaded.total} ${runWord} in this record`;
  }
  if (focus === 'missing') {
    return `No run with that id · ${loaded.total} ${runWord} in this record`;
  }
  if (loaded.total === 0) return 'No runs in this record yet';
  if (!filtering) {
    return `Showing ${loaded.runs.length} of ${loaded.total} ${runWord}`;
  }
  return (
    `Showing ${loaded.runs.length} of ${loaded.matched} matching · ` +
    `${loaded.total} ${runWord} in this record`
  );
}

/**
 * TWO DIFFERENT EMPTY LISTS, and collapsing them would be the same conflation the
 * count line exists to prevent: "this record has no runs" and "no run matches what
 * you asked for" are different facts, and only the second one has a remedy.
 */
function EmptyRuns({
  total,
  filtering,
  onClear,
}: {
  total: number;
  filtering: boolean;
  onClear: () => void;
}) {
  if (!filtering || total === 0) {
    return (
      <p className="runs-empty">
        No runs yet. Add one for the first set of conditions you measured.
      </p>
    );
  }
  return (
    <div className="runs-empty">
      <p>
        No run matches this search or these filters. This record has {total}{' '}
        {total === 1 ? 'run' : 'runs'}.
      </p>
      <button type="button" className="btn btn-secondary" onClick={onClear}>
        Clear search and filters
      </button>
    </div>
  );
}

/**
 * ONE RUN, ISOLATED — and the three ways that can go.
 *
 * It is on the loaded page (render it from there), it is not (it was read
 * directly), or the server says there is no such run. The third one degrades to
 * a sentence and a way back, never to a blank panel and never to a claim about
 * the RECORD: a run id that does not resolve says nothing at all about whether
 * the record exists, and the record screen around this section is proof that it
 * does.
 */
function FocusedRun({
  experimentId,
  focusRunId,
  focus,
  run,
  cardFocusId,
  onCardFocused,
  expanded,
  onToggle,
  onRun,
  onRemove,
  removingId,
  removeError,
  onReloadSection,
  onLeave,
}: {
  experimentId: string;
  focusRunId: string;
  focus: FocusState;
  /** Resolved by the browser above, so the count line cannot disagree with it. */
  run: ApiRunView | undefined;
  cardFocusId: string | null;
  onCardFocused: () => void;
  expanded: boolean;
  onToggle: () => void;
  onRun: (run: ApiRunView) => void;
  /**
   * REMOVAL IS OFFERED HERE, unlike Focus and Compare. Those two are withheld
   * because they would put the reader where they already are, or need a second
   * run; removal needs neither, and a reader who has isolated one run is the
   * likeliest to want it gone. The browser above returns them to the list.
   */
  onRemove: (run: ApiRunView) => Promise<void>;
  removingId: string | null;
  removeError: { runId: string; message: string; stale: boolean } | null;
  onReloadSection: () => void;
  onLeave: () => void;
}) {
  if (focus.status === 'loading') {
    return <LoadingPanel label="Loading this run…" />;
  }
  if (run === undefined) {
    return (
      <div className="runs-error" role="alert">
        <p>
          No run with the id <span className="mono">{focusRunId}</span> is in this record. It may
          have been deleted, or the link may be for a different record. Everything else on this
          record is unaffected.
          {focus.status === 'missing' && focus.error.status !== 404
            ? ` The server said: ${focus.error.message}`
            : ''}
        </p>
        <button type="button" className="btn btn-secondary" onClick={onLeave}>
          Back to all runs
        </button>
      </div>
    );
  }

  return (
    <div className="runs-list">
      {/*
        The card is the SAME card the list renders, with the same autosave, the
        same overrides panel and the same Check Run — focus is a filter on what is
        on screen, not a second, read-only rendering of a run. It OPENS expanded
        (the reader asked for this one run, and a collapsed one would make focus
        cost an extra click to be worth anything) and can still be collapsed,
        because the accordion means the same thing here as it does in the list.

        NO `onFocusRun`: the Focus control is withheld from the focused view. It
        would put the reader exactly where they already are.
      */}
      <RunCard
        experimentId={experimentId}
        run={run}
        expanded={expanded}
        onToggle={onToggle}
        onRun={onRun}
        focusOnMount={cardFocusId === run.id}
        onFocused={onCardFocused}
        onRemove={() => onRemove(run)}
        removing={removingId === run.id}
        removeError={
          removeError !== null && removeError.runId === run.id ? removeError : null
        }
        onReloadSection={onReloadSection}
      />
    </div>
  );
}

function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

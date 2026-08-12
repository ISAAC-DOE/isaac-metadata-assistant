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
 */

import './runs.css';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RunCard } from './RunCard';
import { LoadingPanel, BackendDown } from './FetchStates';
import { Plus } from './icons';
import { api, ApiError } from '../lib/api';
import { RECORD_RUN_PARAM } from '../lib/routes';
import type { ApiRunView } from '../lib/types';
import { RUNS_PAGE_SIZE } from '../lib/runPaging';

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

export function RunsSection({ experimentId }: { experimentId: string }) {
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
          record's list criteria into another's. */}
      <RunsBrowser key={experimentId} experimentId={experimentId} />
    </section>
  );
}

function RunsBrowser({ experimentId }: { experimentId: string }) {
  const baseId = useId();
  const searchId = `${baseId}-search`;
  const searchHintId = `${baseId}-search-hint`;
  const overridesId = `${baseId}-overrides`;
  const exportedId = `${baseId}-exported`;

  const [searchParams, setSearchParams] = useSearchParams();
  const focusRunId = searchParams.get(RECORD_RUN_PARAM);

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

  const searchRef = useRef<HTMLInputElement>(null);

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
   */
  const createdRef = useRef<ApiRunView | null>(null);

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
    if (!silentRef.current) setList({ status: 'loading' });
    silentRef.current = false;
    setLoadingMore(false);
    setMoreError(null);

    let alive = true;
    api
      .listRuns(experimentId, {
        limit: RUNS_PAGE_SIZE,
        offset: 0,
        ...criteriaQuery(query, overridesFilter, exportedFilter),
      })
      .then((res) => {
        if (!alive || generation !== generationRef.current) return;
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

        const created = createdRef.current;
        if (created === null) return;
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
        if (!alive || generation !== generationRef.current) return;
        createdRef.current = null;
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
        createdRef.current = res.run;
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
        setAddError(
          err instanceof Error ? err.message : 'The run could not be created.',
        );
      });
  };

  const reloadSection = () => {
    setAddError(null);
    setAddStale(false);
    setReloadNonce((n) => n + 1);
  };

  const focused = focusRunId !== null && focusRunId !== '';
  const loaded = list.status === 'data' ? list.loaded : null;

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

  return (
    <>
      {/*
        THE TOOLBAR EXISTS ONLY ONCE THE LIST HAS LANDED, and that is a contract
        this section has always kept rather than a rendering convenience: `Add Run`
        appearing means the runs are loaded. Rendering it disabled during the read
        would put an enabled-looking control on screen before there is an
        experiment version to send with it, and would break the one thing every
        caller — including this repo's own specs — uses to know the section is
        ready.
      */}
      {loaded !== null && (
      <div className="runs-toolbar">
        {focused ? (
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
            type="button"
            className="btn btn-primary"
            onClick={addRun}
            disabled={adding || experimentVersion === null}
          >
            <Plus size={15} strokeWidth={2.2} aria-hidden="true" />
            {adding ? 'Adding Run…' : 'Add Run'}
          </button>
        )}
        {/*
          THE COUNTS, AND THE ONE ELEMENT THAT ANNOUNCES THEM.

          It is rendered in EVERY mode and at the same position, so the DOM node
          survives entering focus, leaving focus, searching and paging — a live
          region that is unmounted and remounted with its new text is not reliably
          announced, which would make the announcement present in the markup and
          absent in practice.

          `aria-live` rather than `role="status"` deliberately: this is a label for
          the list below it, not a transient status message, and the record screen
          already carries several `status` regions (one per run card) that an
          unnamed extra one would sit among.
        */}
        <p className="runs-count" aria-live="polite" aria-atomic="true">
          {countLine(loaded, filtering, focused)}
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

      {addNote !== null && (
        <p className="runs-note" role="status">
          {addNote}
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
            runs={loaded.runs}
            cardFocusId={cardFocusId}
            onCardFocused={() => setCardFocusId(null)}
            expanded={expanded[focusRunId] ?? true}
            onToggle={() =>
              setExpanded((prev) => ({ ...prev, [focusRunId]: !(prev[focusRunId] ?? true) }))
            }
            onRun={replaceRun}
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
                />
              ))}
            </div>

            {moreError !== null && (
              <p className="runs-error" role="alert">
                {moreError} The {loaded.runs.length} runs already loaded are unchanged.
              </p>
            )}

            {loaded.runs.length < loaded.matched && (
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
 */
function countLine(loaded: Loaded | null, filtering: boolean, focused: boolean): string {
  if (loaded === null) return '';
  const runWord = loaded.total === 1 ? 'run' : 'runs';
  if (focused) {
    return `Viewing one run · ${loaded.total} ${runWord} in this record`;
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
  runs,
  cardFocusId,
  onCardFocused,
  expanded,
  onToggle,
  onRun,
  onLeave,
}: {
  experimentId: string;
  focusRunId: string;
  focus: FocusState;
  runs: ApiRunView[];
  cardFocusId: string | null;
  onCardFocused: () => void;
  expanded: boolean;
  onToggle: () => void;
  onRun: (run: ApiRunView) => void;
  onLeave: () => void;
}) {
  const fromPage = runs.find((r) => r.id === focusRunId);
  const run = focus.status === 'fetched' ? focus.run : fromPage;

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
      />
    </div>
  );
}

function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

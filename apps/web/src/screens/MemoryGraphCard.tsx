/*
 * Project Memory → Graph (P36.2, redesigned in P36R Slice 3 + 6).
 *
 * ONE fetch (`api.getMemoryGraph()`), ONE index (`buildGraphIndex`), ONE state
 * model (`lib/graphModel.ts`). Every search, filter, selection, neighbourhood,
 * path and viewport change is a `GraphAction` applied by `applyGraphAction` —
 * no second code path exists, which is what lets the Slice-4 command bar and
 * the Slice-5 Assistant intents drive this surface without reimplementing it.
 *
 * Two permanent modes over the same data:
 *   Explore — a bounded dark canvas (the app's only dark surface).
 *   Browse  — the textual, keyboard-first list. Not a fallback.
 *
 * What this surface is: a served-file REFERENCE projection. What it is not:
 * the full source graph (`meta.underlying_graph` discloses the real, larger,
 * un-embedded figures), a scientific relationship map, or a validation verdict.
 */
import './graph/graph.css';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { CircleHelp, LayoutList, Network, Search } from '../components/icons';
import { api, type ApiError } from '../lib/api';
import { relationDisplayLabel } from '../lib/displayLabels';
import { useFetch } from '../lib/useFetch';
import {
  GRAPH_URL_PARAMS,
  MAX_HISTORY,
  MAX_QUERY_LENGTH,
  decodeGraphActions,
  defaultGraphMode,
  describeCommandOutcome,
  encodeGraphParams,
  graphParamKey,
  parseGraphCommand,
  suggestedGraphCommands,
  type GraphCommandHistoryEntry,
  type GraphSurfaceContext,
  type GraphUrlParam,
} from '../lib/graphCommands';
import {
  PALETTE_SLOTS,
  applyGraphAction,
  graphLodLevel,
  buildGraphIndex,
  communityColorIndex,
  communityLabelAmong,
  connectedNodes,
  filteredNodeIds,
  initialGraphViewState,
  visibleEdges,
  visibleNodeIds,
  type GraphAction,
  type GraphCommunityEntry,
  type GraphIndex,
  type GraphViewState,
} from '../lib/graphModel';
import { decodeDeepGraph, type DeepIndex } from '../lib/graphDeep';
import type { ApiMemoryGraphResponse } from '../lib/types';
import { GraphBrowse, type BrowseGrouping } from './graph/GraphBrowse';
import { GraphCanvas, type DeepLayerState } from './graph/GraphCanvas';
import { GraphCommandBar } from './graph/GraphCommandBar';
import { GraphDeepDetail, GraphDetail, GraphPathResult } from './graph/GraphDetail';
import {
  GraphActiveFilters,
  GraphFiltersPanel,
  GraphFiltersToggle,
  activeFilterChips,
  hiddenFilterCount,
  noRelationshipsShown,
} from './graph/GraphFilters';
import { GraphHelp, type GraphHelpExpand } from './graph/GraphHelp';
import { GraphPathFinder, GraphPathToggle } from './graph/GraphPathFinder';

// --- top-level card ---------------------------------------------------------

interface MemoryGraphCardProps {
  /**
   * P36R S5 — publishes the mounted surface (index, provenance, a state reader
   * and an external `apply`) to the owning screen, so an Assistant proposal the
   * user EXPLICITLY applies reaches this same reducer instead of a second copy
   * of the graph logic. Called with `null` on unmount. Optional: without it the
   * surface behaves exactly as before.
   */
  onReady?: (ctx: GraphSurfaceContext | null) => void;
}

export function MemoryGraphCard({ onReady }: MemoryGraphCardProps = {}) {
  const graph = useFetch(() => api.getMemoryGraph(), []);
  const [helpOpen, setHelpOpen] = useState(false);
  // P36V.1 G — which disclosure the dialog opens expanded. The "Syntax" control
  // and a typed `help` asked for the grammar; the "View Technical Details"
  // suggestion asked for the reference data; the plain trigger asked for
  // neither, so nothing is pre-expanded for it.
  const [helpExpand, setHelpExpand] = useState<GraphHelpExpand | null>(null);
  const helpTriggerRef = useRef<HTMLButtonElement | null>(null);
  // The help drawer has FOUR openers: the "About This Graph" trigger, the
  // command bar's "Syntax" button, typing `help`, and the "View Technical
  // Details" suggestion. Focus must return to whichever one the user actually
  // used — returning it to the trigger after a typed `help` dropped the user out
  // of the command input they were in.
  const helpReturnRef = useRef<HTMLElement | null>(null);
  const openHelp = useCallback((expand?: GraphHelpExpand) => {
    const active = typeof document === 'undefined' ? null : document.activeElement;
    helpReturnRef.current =
      active instanceof HTMLElement && active !== document.body ? active : null;
    setHelpExpand(expand ?? null);
    setHelpOpen(true);
  }, []);
  const closeHelp = useCallback(() => {
    setHelpOpen(false);
    const invoker = helpReturnRef.current;
    helpReturnRef.current = null;
    if (invoker && invoker.isConnected) invoker.focus();
    else helpTriggerRef.current?.focus();
  }, []);

  const helpAvailable = graph.status === 'data' && graph.data.available && graph.data.nodes.length > 0;

  return (
    <div className="card placeholder-card memory-graph-card">
      <div className="memory-graph-titlerow">
        <h2 className="memory-graph-heading">Graph</h2>
        {helpAvailable && (
          <button
            ref={helpTriggerRef}
            type="button"
            className="memory-graph-help-trigger"
            aria-haspopup="dialog"
            aria-expanded={helpOpen}
            /* An arrow, not the bare callback: React would pass the MouseEvent
               as the `expand` argument. */
            onClick={() => openHelp()}
          >
            <CircleHelp size={13} strokeWidth={2} aria-hidden="true" />
            About This Graph
          </button>
        )}
      </div>
      {/* P36V PR2 slice B — ONE visible boundary statement. The longer
          disclosures that used to stack up here (the un-embedded source graph's
          figures, the four-layer projection chain, the snapshot provenance line,
          the full cluster caveat) were RELOCATED into About This Graph, not
          dropped: Graph Data carries the layer chain and the un-embedded
          figures, Cluster Colors carries the cluster caveat, and Technical
          Details carries the provenance fingerprint. */}
      <p className="memory-graph-subtitle">
        This graph shows project-file relationships and navigation leads. It does not represent
        scientific truth or causality.
      </p>
      {graph.status === 'loading' && <LoadingPanel label="Loading graph…" />}
      {graph.status === 'error' && <MemoryGraphError error={graph.error} onRetry={graph.reload} />}
      {graph.status === 'data' && (
        <MemoryGraphBody data={graph.data} onReady={onReady} onOpenHelp={openHelp} />
      )}
      {helpOpen && graph.status === 'data' && graph.data.available && (
        <GraphHelp
          meta={graph.data.meta}
          relationTypes={[...new Set(graph.data.edges.flatMap((e) => e.relations))].sort()}
          paletteSlots={PALETTE_SLOTS}
          communityCount={graph.data.communities.length}
          singletonCount={graph.data.communities.filter((c) => c.file_count <= 1).length}
          expand={helpExpand}
          onClose={closeHelp}
        />
      )}
    </div>
  );
}

function MemoryGraphError({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  return <BackendDown error={error} onRetry={onRetry} />;
}

function MemoryGraphBody({
  data,
  onReady,
  onOpenHelp,
}: {
  data: ApiMemoryGraphResponse;
  onReady?: (ctx: GraphSurfaceContext | null) => void;
  onOpenHelp: (expand?: GraphHelpExpand) => void;
}) {
  if (!data.available) {
    return (
      <div className="memory-graph-unavailable">
        <p className="memory-graph-unavailable-title">
          The Graph tab is unavailable — no memory graph is loaded in this deployment (see Project
          memory status on the Overview tab).
        </p>
        <p className="memory-graph-unavailable-text">
          This is a quiet, advisory state, not an error — no nodes are shown while memory is
          unavailable; this tab never fabricates a graph.
        </p>
      </div>
    );
  }
  if (data.nodes.length === 0) {
    return (
      <p className="memory-graph-empty-note">
        No files or concepts are indexed in the served-file graph yet.
      </p>
    );
  }
  return <MemoryGraphAvailable data={data} onReady={onReady} onOpenHelp={onOpenHelp} />;
}

// --- available state ---------------------------------------------------------

function MemoryGraphAvailable({
  data,
  onReady,
  onOpenHelp,
}: {
  data: ApiMemoryGraphResponse;
  onReady?: (ctx: GraphSurfaceContext | null) => void;
  onOpenHelp: (expand?: GraphHelpExpand) => void;
}) {
  const navigate = useNavigate();
  const index = useMemo<GraphIndex>(() => buildGraphIndex(data), [data]);

  // --- URL state (P36R S4) ---------------------------------------------------
  // A BOUNDED, enumerable set of parameters (GRAPH_URL_PARAMS) — mode, filters,
  // search, and one selection or focus. Never a serialized blob: every value is
  // length-checked and, where the grammar is closed, checked against its set at
  // `decodeGraphActions`; node and cluster tokens then go through the reducer's
  // own `resolveNode` / `resolveCommunity`, so a hostile link can only ever
  // produce an honest "no node matches" — never a guessed identity, and never a
  // raw action object reaching the reducer.
  const [params, setParams] = useSearchParams();
  const paramsRef = useRef(params);
  paramsRef.current = params;

  const [state, setState] = useState<GraphViewState>(() => {
    let s = initialGraphViewState(defaultGraphMode());
    for (const action of decodeGraphActions((k) => params.get(k))) {
      s = applyGraphAction(s, action, index);
    }
    return s;
  });
  const stateRef = useRef(state);
  stateRef.current = state;

  // A command's syntax error has no reducer notice to carry it, so it lives
  // here — and is rendered inside the SAME single polite live region, never a
  // second one.
  const [commandError, setCommandError] = useState<string | null>(null);
  // Nor does a SUCCESSFUL command that the reducer left no notice on: `find`,
  // `select`, `community`, `type`, `relation`, `fit` and `clear` are seven of
  // the eleven verbs, and every one of them used to announce absolutely nothing.
  // This is the same string the history line shows, in the same single region.
  const [commandOutcome, setCommandOutcome] = useState<string | null>(null);
  const [history, setHistory] = useState<GraphCommandHistoryEntry[]>([]);
  const historySeq = useRef(0);

  const dispatch = useCallback(
    (action: GraphAction) => {
      setCommandError(null);
      // A control-driven change is not the command's outcome any more; leaving
      // the old announcement mounted would let a stale line describe a view it
      // no longer matches.
      setCommandOutcome(null);
      setState((s) => applyGraphAction(s, action, index));
    },
    [index],
  );

  // The URL is written by EXPLICIT navigational acts only — a typed command or
  // an applied Assistant proposal. Pointer drags, zooming and per-keystroke
  // filtering deliberately do not push history entries.
  const urlKeyRef = useRef(graphParamKey((k) => params.get(k)));
  const writeUrl = useCallback(
    (next: GraphViewState) => {
      const sp = new URLSearchParams(paramsRef.current);
      for (const key of GRAPH_URL_PARAMS) sp.delete(key);
      for (const [key, value] of Object.entries(encodeGraphParams(next))) sp.set(key, value);
      // The Graph tab must be part of the link, or a reload lands on Overview.
      sp.set('tab', 'graph');
      urlKeyRef.current = graphParamKey((k: GraphUrlParam) => sp.get(k));
      setParams(sp);
    },
    [setParams],
  );

  // An EXTERNAL parameter change — browser back/forward, or a pasted link —
  // rebuilds the view from the link. Our own writes are recognised by
  // `urlKeyRef` and skipped, so this never fights the surface.
  const urlKey = graphParamKey((k) => params.get(k));
  useEffect(() => {
    if (urlKey === urlKeyRef.current) return;
    urlKeyRef.current = urlKey;
    let s = initialGraphViewState(defaultGraphMode());
    for (const action of decodeGraphActions((k) => paramsRef.current.get(k))) {
      s = applyGraphAction(s, action, index);
    }
    setState(s);
    setCommandError(null);
    setCommandOutcome(null);
  }, [urlKey, index]);

  // ONE application path for both text front-ends. The actions were produced by
  // the parser or the intent classifier; applying them is the same reducer a
  // click uses, and the outcome recorded here is the reducer's own notice.
  const runActions = useCallback(
    (command: string, actions: GraphAction[], origin: 'command' | 'assistant') => {
      // A new command's outcome REPLACES the previous one. Without dropping the
      // stale notice first, `fit` or `reset` after a `neighbors` left the old
      // neighbourhood notice standing in the live region — announcing the
      // previous command as if it were what just happened, and masking the
      // command that actually ran.
      let next = applyGraphAction(stateRef.current, { kind: 'dismissNotice' }, index);
      for (const action of actions) next = applyGraphAction(next, action, index);
      stateRef.current = next;
      setState(next);
      setCommandError(null);
      // ONE outcome string, used for BOTH the spoken announcement and the
      // written history line — they cannot describe the same command
      // differently. When the reducer attached a notice, the live region renders
      // that notice richly instead, so the plain line would be a duplicate.
      const outcome = describeCommandOutcome(command, next, index);
      setCommandOutcome(next.notice ? null : outcome);
      writeUrl(next);
      historySeq.current += 1;
      const id = historySeq.current;
      setHistory((h) =>
        [...h, { id, command, origin, status: 'ok' as const, outcome }].slice(-MAX_HISTORY),
      );
    },
    [index, writeUrl],
  );

  const pushHistory = useCallback((entry: Omit<GraphCommandHistoryEntry, 'id'>) => {
    historySeq.current += 1;
    const id = historySeq.current;
    setHistory((h) => [...h, { ...entry, id }].slice(-MAX_HISTORY));
  }, []);

  const runCommand = useCallback(
    (raw: string) => {
      const parsed = parseGraphCommand(raw);
      if (parsed.status === 'empty') return;
      if (parsed.status === 'help') {
        // "About This Graph" verbatim — the trigger's label and the dialog's own
        // title. A lowercase paraphrase reads as a different thing than the
        // control the user is being pointed at.
        const outcome = 'Opened the command syntax in About This Graph.';
        setCommandError(null);
        // A previous command's notice would otherwise outrank this in the live
        // region and `help` would still announce nothing.
        setState((s) => applyGraphAction(s, { kind: 'dismissNotice' }, index));
        setCommandOutcome(outcome);
        onOpenHelp('commands');
        pushHistory({ command: 'help', origin: 'command', status: 'help', outcome });
        return;
      }
      if (parsed.status === 'error') {
        // Nothing is applied: the graph state is untouched and the error is
        // announced honestly.
        setCommandError(parsed.message);
        setCommandOutcome(null);
        pushHistory({
          command: raw.trim().slice(0, 120),
          origin: 'command',
          status: 'error',
          outcome: parsed.message,
        });
        return;
      }
      runActions(parsed.echo, parsed.actions, 'command');
    },
    [index, onOpenHelp, pushHistory, runActions],
  );

  // The external (Assistant) entry point — identical machinery, no extra
  // actions. An earlier draft prepended `setMode: explore` on wide viewports;
  // that silently pulled a user out of Browse, which is not what the proposal
  // card says Apply will do. Browse is driven by the same state, so an applied
  // filter or focus is just as visible there — the mode stays the user's choice.
  const applyExternal = useCallback(
    (command: string | null, actions: GraphAction[]) => {
      runActions(command ?? 'applied from the Assistant', actions, 'assistant');
    },
    [runActions],
  );

  useEffect(() => {
    if (!onReady) return;
    onReady({
      index,
      meta: data.meta,
      peek: () => stateRef.current,
      apply: applyExternal,
    });
    return () => onReady(null);
  }, [onReady, index, data.meta, applyExternal]);

  // --- the DEEP (symbol-level) layer, P36V.1 Unit F -------------------------
  //
  // LAZY on purpose. The artifact is ~500 kB of columnar rows; a visit to
  // Project Memory that never zooms past the first level-of-detail threshold
  // never requests it, so the tab stays ONE fetch for every reader who does not
  // ask for detail. Requested at most once per mount, and any failure degrades
  // to an honest `unavailable` — the canvas then keeps the file projection and
  // says so rather than aggregating something in its place.
  const [deep, setDeep] = useState<DeepLayerState>({ status: 'idle' });
  const [deepSelectedId, setDeepSelectedId] = useState<string | null>(null);
  const deepRequested = useRef(false);
  const alive = useRef(true);
  useEffect(() => () => {
    alive.current = false;
  }, []);
  // Requested when the layer would actually be DRAWN on the canvas: past the
  // first threshold, in Explore, and with no neighbourhood/path focus active (a
  // focus keeps the canvas on the base projection it was computed over, so
  // fetching 500 kB there would buy nothing).
  const deepDrawnOnCanvas =
    graphLodLevel(state.view.scale) !== 'file' && state.mode === 'explore' && state.focus === null;
  /*
   * …OR when the reader asks for it in Browse.
   *
   * Requiring `mode === 'explore'` was the reviewed defect: Browse has no
   * viewport, so it can never cross a zoom threshold, so a reader who entered
   * Browse directly could never obtain the deep layer at all — which made the
   * whole symbol level, and `GraphDeepDetail` with it, reachable only by a pointer
   * gesture on the canvas. Browse now has its own explicit control; the fetch
   * stays opt-in rather than becoming eager.
   */
  const [deepAskedInBrowse, setDeepAskedInBrowse] = useState(false);
  const deepNeeded = deepDrawnOnCanvas || deepAskedInBrowse;
  useEffect(() => {
    if (!deepNeeded || deepRequested.current) return;
    deepRequested.current = true;
    setDeep({ status: 'loading' });
    api
      .getMemoryGraphDetail()
      .then((res) => {
        if (!alive.current) return;
        const decoded = decodeDeepGraph(res);
        if (decoded) {
          setDeep({ status: 'ready', index: decoded });
          return;
        }
        setDeep({
          status: 'unavailable',
          reason: res.reason ?? (res.available ? 'detail_schema_unrecognised' : 'detail_absent'),
        });
      })
      .catch(() => {
        if (alive.current) setDeep({ status: 'unavailable', reason: 'request_failed' });
      });
  }, [deepNeeded]);
  const deepIndex: DeepIndex | null = deep.status === 'ready' ? deep.index : null;
  /** Whether the canvas is actually drawing a deeper layer right now — the same
   *  three conditions GraphCanvas uses to build a plan. Deliberately NOT
   *  `deepNeeded`: a Browse-initiated fetch must never make the count line above
   *  the canvas claim the canvas is zoomed inside the files. */
  const deepShowing = deepIndex !== null && deepDrawnOnCanvas;

  /*
   * DEEP-ONLY UI MUST NOT OUTLIVE THE DEEP LAYER (orchestrator decision, P36V.1).
   *
   * `deepSelectedId` was never cleared when the canvas zoomed back out, so the
   * pinned-symbol panel — and Unit G's deep suggested commands, which read this
   * same value — kept describing a mark that is not drawn at 100 % zoom. The value
   * is CLEARED rather than the surfaces being special-cased, so every consumer of
   * it (this panel, the suggestions, the canvas's `aria-pressed`) agrees without
   * any of them needing to know the rule. The prop Unit G reads is unchanged.
   *
   * Explore only. In Browse nothing is drawn at any zoom, and the deep detail
   * panel is Browse's textual route into the layer — clearing there would remove
   * the keyboard path, not a stale claim.
   */
  useEffect(() => {
    if (state.mode !== 'explore') return;
    if (deepShowing) return;
    setDeepSelectedId((current) => (current === null ? current : null));
  }, [state.mode, deepShowing]);

  /*
   * P36V.1 G — the Suggested Commands set.
   *
   * Derived from the SAME live state and the SAME index the bar runs against,
   * and — deliberately — from Unit F's `deepSelectedId` rather than a second
   * selection mechanism of its own. Every entry is verified inside
   * `suggestedGraphCommands` by folding its own command through the real parser
   * and the real reducer, so nothing offered here can fail to resolve.
   */
  const suggestions = useMemo(
    () => suggestedGraphCommands(index, { state, deep: deepIndex, deepSelectedId }),
    [index, state, deepIndex, deepSelectedId],
  );

  const [communityQuery, setCommunityQuery] = useState('');
  const [grouping, setGrouping] = useState<BrowseGrouping>('type');
  const [pathFrom, setPathFrom] = useState('');
  const [pathTo, setPathTo] = useState('');

  // P36V PR2 slice B — progressive disclosure. Both regions start closed; NO
  // control was removed, and the active-filter chips below keep a collapsed
  // Filters panel from hiding the fact that the view is narrowed.
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [pathOpen, setPathOpen] = useState(false);
  const filtersId = useId();
  const pathId = useId();
  // "Use as path start" in the detail panel writes into the path tool. With the
  // tool collapsed that was a click with no visible effect at all, so it opens
  // the tool it is filling in.
  const usePathStart = useCallback((id: string) => {
    setPathFrom(id);
    setPathOpen(true);
  }, []);

  const listIds = useMemo(() => filteredNodeIds(state, index), [state, index]);
  const canvasIds = useMemo(() => visibleNodeIds(state, index), [state, index]);
  const canvasEdges = useMemo(
    () => visibleEdges(state, index, new Set(canvasIds)),
    [state, index, canvasIds],
  );

  const selectedNode = state.selectedId ? (index.byId.get(state.selectedId) ?? null) : null;
  const selectedConnected = useMemo(
    () => (state.selectedId ? connectedNodes(state.selectedId, state, index) : []),
    [state, index],
  );

  const shownCount = state.mode === 'explore' ? canvasIds.length : listIds.length;

  const chips = useMemo(() => activeFilterChips(state, index), [state, index]);
  const filterCount = hiddenFilterCount(state, index);
  // The chip row's controls remove themselves; focus must go somewhere real.
  const filtersToggleRef = useRef<HTMLButtonElement | null>(null);
  const focusFiltersToggle = useCallback(() => filtersToggleRef.current?.focus(), []);
  // The old "Clear filters" button's behaviour, verbatim: the reducer's
  // `clearFilters` (search, node type, cluster, relationship, focus) plus the
  // two local text boxes it also emptied.
  const clearAllFilters = useCallback(() => {
    setPathFrom('');
    setPathTo('');
    setCommunityQuery('');
    dispatch({ kind: 'clearFilters' });
  }, [dispatch]);

  const navigateToFile = useCallback(
    (path: string) => navigate(`/memory?file=${encodeURIComponent(path)}`),
    [navigate],
  );
  const navigateToConcept = useCallback(
    (id: string) => navigate(`/memory?concept=${encodeURIComponent(id)}`),
    [navigate],
  );

  const meta = data.meta;

  return (
    <div className="memory-graph-available">
      {/* P36V PR2 slice B — the header is now ONE data line. The counts keep
          their scope qualifier so the surface never reads as the whole graph;
          the figures for the un-embedded source graph, the four-layer projection
          chain and the provenance fingerprint all moved into About This Graph
          (Graph Data / Technical Details). Nothing was dropped. */}
      <div className="memory-graph-header">
        <p className="memory-graph-counts">
          {meta.counts.files} files · {meta.counts.concepts} concepts ·{' '}
          {meta.counts.reference_edges} reference{meta.counts.reference_edges === 1 ? '' : 's'} ·{' '}
          {meta.counts.communities_rendered} communit
          {meta.counts.communities_rendered === 1 ? 'y' : 'ies'} shown — an advisory served-file
          projection, never the full source graph.
        </p>
        {data.truncated && (
          <p className="memory-graph-truncated-note">
            Showing a capped subset of the served-file graph — the node or reference count reached
            its display limit, so not everything indexed is listed here.
          </p>
        )}
      </div>

      {/* PRIMARY TOOLBAR — mode, search, and the two disclosures. Everything
          else that used to live on this row (node type, cluster search, cluster
          select, relationship checkboxes, grouping, the path form) is behind
          Filters or Find a Path; the canvas viewport controls (Fit to View,
          Reset View, zoom) are on the canvas toolbar they act on. */}
      <div className="memory-graph-controls">
        <div className="memory-graph-modeswitch" role="radiogroup" aria-label="Graph view mode">
          <button
            type="button"
            role="radio"
            aria-checked={state.mode === 'explore'}
            className="memory-graph-modebtn"
            onClick={() => dispatch({ kind: 'setMode', mode: 'explore' })}
          >
            <Network size={13} strokeWidth={2} aria-hidden="true" />
            Explore
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={state.mode === 'browse'}
            className="memory-graph-modebtn"
            onClick={() => dispatch({ kind: 'setMode', mode: 'browse' })}
          >
            <LayoutList size={13} strokeWidth={2} aria-hidden="true" />
            Browse
          </button>
        </div>
        <label className="memory-graph-search-wrap">
          <Search size={14} strokeWidth={2} aria-hidden="true" className="memory-graph-search-icon" />
          <span className="memory-graph-visually-hidden">Search graph nodes</span>
          <input
            type="search"
            className="memory-graph-search-input"
            placeholder="Search files and concepts…"
            /* The SAME bound `find` and the `gq` parameter enforce. Unbounded,
               a long query became a link the encoder had to drop — and a link
               with no search shows its recipient MORE nodes than its author. */
            maxLength={MAX_QUERY_LENGTH}
            value={state.search}
            onChange={(e) => dispatch({ kind: 'search', query: e.target.value })}
          />
        </label>
        <GraphFiltersToggle
          id={filtersId}
          open={filtersOpen}
          count={filterCount}
          onToggle={() => setFiltersOpen((o) => !o)}
          buttonRef={filtersToggleRef}
        />
        <GraphPathToggle id={pathId} open={pathOpen} onToggle={() => setPathOpen((o) => !o)} />
      </div>

      {filtersOpen && (
        <GraphFiltersPanel
          id={filtersId}
          index={index}
          state={state}
          dispatch={dispatch}
          communityQuery={communityQuery}
          onCommunityQuery={setCommunityQuery}
          grouping={grouping}
          onGrouping={setGrouping}
        />
      )}

      {/* Active filters stay visible whether or not the panel is open — a
          collapsed disclosure must never be able to hide a narrowed view. */}
      <GraphActiveFilters
        chips={chips}
        dispatch={dispatch}
        onClearAll={clearAllFilters}
        onFocusFiltersToggle={focusFiltersToggle}
        noRelationships={noRelationshipsShown(state, index)}
      />

      {pathOpen && (
        <GraphPathFinder
          id={pathId}
          state={state}
          dispatch={dispatch}
          from={pathFrom}
          to={pathTo}
          onFrom={setPathFrom}
          onTo={setPathTo}
        />
      )}

      {/* P36R S4 — the deterministic command bar. A bounded grammar over the
          SAME actions the controls above dispatch; it adds no capability the
          controls lack, only a keyboard-first way to reach them. */}
      <GraphCommandBar
        index={index}
        history={history}
        suggestions={suggestions}
        onRun={runCommand}
        onClearHistory={() => setHistory([])}
        onOpenHelp={onOpenHelp}
      />

      {/* The count line is deliberately NOT in the live region: it changes on
          every search keystroke, which announced "3 of 5 … 2 of 5 … 1 of 5"
          six times while typing one word. It stays a visible, readable status
          line; the live region carries the RESULTS — notices, path outcomes,
          neighbourhood outcomes, refusals. */}
      <div className="memory-graph-status">
        <p className="memory-graph-list-summary">
          {shownCount} of {index.counts.total} nodes shown
          {state.mode === 'explore' && listIds.length !== canvasIds.length
            ? ` on the canvas · ${listIds.length} match in Browse`
            : ''}
          {/* P36V.1 F — this count is about the FILE projection. Once the canvas
              has zoomed into the deeper layers it is drawing something else, and
              a count line sitting directly above it must not read as a
              description of what is on screen. The canvas states its own counts
              underneath itself. */}
          {deepShowing
            ? ' — the canvas is zoomed inside them, drawing symbol-level detail with its own counts below'
            : ''}
        </p>
        {state.focus && (
          <span className="memory-graph-focuschip">
            {state.focus.kind === 'neighbors'
              ? `${state.focus.depth}-hop neighbourhood of ${state.focus.nodeId}`
              : `path ${state.focus.from} → ${state.focus.to}`}
            <button type="button" onClick={() => dispatch({ kind: 'clearFocus' })}>
              Clear
            </button>
          </span>
        )}
      </div>
      {/* Exactly ONE polite live region on this surface. Always mounted (an
          empty container announces reliably; one created on demand does not).
          It carries a command syntax error, OR a reducer notice, OR the terse
          outcome of a command the reducer left no notice on — in that order of
          precedence. The command bar adds no second region. */}
      <div className="memory-graph-live" aria-live="polite">
        {commandError ? (
          <p className="memory-graph-notice advisory">{commandError}</p>
        ) : state.notice ? (
          <GraphNoticeView notice={state.notice} dispatch={dispatch} index={index} />
        ) : commandOutcome ? (
          <p className="memory-graph-notice">{commandOutcome}</p>
        ) : null}
      </div>

      <div className="memory-graph-body">
        <div className="memory-graph-primary">
          {state.mode === 'explore' ? (
            <GraphCanvas
              index={index}
              state={state}
              dispatch={dispatch}
              visibleIds={canvasIds}
              edges={canvasEdges}
              deep={deep}
              deepSelectedId={deepSelectedId}
              onDeepSelect={setDeepSelectedId}
            />
          ) : (
            <GraphBrowse
              index={index}
              state={state}
              dispatch={dispatch}
              ids={listIds}
              grouping={grouping}
              deep={deepIndex}
              deepStatus={deep.status}
              deepReason={deep.status === 'unavailable' ? deep.reason : null}
              onRequestDeep={() => setDeepAskedInBrowse(true)}
              deepSelectedId={deepSelectedId}
              onSelectDeep={setDeepSelectedId}
            />
          )}
          {/* Explore only: the legend explains CANVAS marks (shape, colour,
              lines). Browse has no marks — it names every cluster in the rows
              themselves — so showing it there would explain nothing. */}
          {state.mode === 'explore' && <GraphLegend index={index} />}
        </div>

        <div className="memory-graph-side">
          {/* The pinned DEEP mark's detail — rendered in BOTH modes, exactly as
              GraphDetail is, so what a pointer discovers by clicking a symbol on
              the canvas is readable as text from the keyboard too. */}
          {deepIndex && deepSelectedId && (
            <GraphDeepDetail
              deep={deepIndex}
              selectedId={deepSelectedId}
              relationFilter={state.relationFilter}
              onSelectDeep={setDeepSelectedId}
              onNavigateFile={navigateToFile}
              onClear={() => setDeepSelectedId(null)}
              /* The canvas states the structural staleness whenever it is
                 drawing a deep layer; this panel states it otherwise. One
                 screen, one statement. */
              showProvenance={!deepShowing}
            />
          )}
          {state.focus?.kind === 'path' && (
            <GraphPathResult
              focus={state.focus}
              index={index}
              onSelect={(id) => dispatch({ kind: 'select', nodeId: id })}
              onClear={() => dispatch({ kind: 'clearFocus' })}
            />
          )}
          <GraphDetail
            node={selectedNode}
            index={index}
            connected={selectedConnected}
            relationFiltered={state.relationFilter !== null}
            onSelect={(id) => dispatch({ kind: 'select', nodeId: id })}
            onNeighbors={(id, depth) => dispatch({ kind: 'neighbors', nodeId: id, depth })}
            onPathFrom={usePathStart}
            onNavigateFile={navigateToFile}
            onNavigateConcept={navigateToConcept}
          />
        </div>
      </div>
    </div>
  );
}

// --- notices -----------------------------------------------------------------

/** A cluster's own label for a candidate button, falling back to its id when the
 *  payload carries no entry for it. Never invents a name. */
function communityLabelFor(id: string, index: GraphIndex): string {
  const entry = index.communityById.get(id);
  return entry ? communityLabelAmong(entry, index.communitiesBySize) : `cluster ${id}`;
}

function GraphNoticeView({
  notice,
  dispatch,
  index,
}: {
  notice: NonNullable<GraphViewState['notice']>;
  dispatch: (action: GraphAction) => void;
  index: GraphIndex;
}) {
  if (notice.kind === 'not_found') {
    return (
      <p className="memory-graph-notice advisory">
        No node in this projection matches <span className="mono">{notice.token}</span>. Nothing was
        selected — an approximate match is never substituted for the one you asked for.
      </p>
    );
  }
  if (notice.kind === 'ambiguous') {
    return (
      <div className="memory-graph-notice advisory">
        <span className="mono">{notice.token}</span> matches {notice.candidates.length} nodes, so no
        identity was assumed. Pick one:
        <ul className="memory-graph-notice-candidates">
          {notice.candidates.map((id) => (
            <li key={id}>
              <button
                type="button"
                className="memory-graph-candidate-btn"
                onClick={() => dispatch({ kind: 'select', nodeId: id })}
              >
                {id}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (notice.kind === 'community_not_found') {
    return (
      <p className="memory-graph-notice advisory">
        No cluster in this projection matches <span className="mono">{notice.token}</span>. The
        cluster filter was left as it was — an approximate cluster is never substituted.
      </p>
    );
  }
  if (notice.kind === 'community_ambiguous') {
    return (
      <div className="memory-graph-notice advisory">
        <span className="mono">{notice.token}</span> matches {notice.candidates.length} clusters, so
        none was assumed. Pick one:
        <ul className="memory-graph-notice-candidates">
          {notice.candidates.map((id) => (
            <li key={id}>
              <button
                type="button"
                className="memory-graph-candidate-btn"
                onClick={() => dispatch({ kind: 'filterCommunity', id })}
              >
                {/* The cluster's own label, not the bare numeric id: a row of
                    `41 55 48` is unreadable, and a `community <name>` command
                    can now surface eight of them at once. The id is still what
                    is dispatched — only the LABEL is friendlier. */}
                {communityLabelFor(id, index)}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (notice.kind === 'relation_unknown') {
    return (
      <p className="memory-graph-notice advisory">
        {notice.tokens.length === 1 ? 'Relationship type' : 'Relationship types'}{' '}
        <span className="mono">{notice.tokens.join(', ')}</span>{' '}
        {notice.tokens.length === 1 ? 'is' : 'are'} not present in this projection, so{' '}
        {notice.tokens.length === 1 ? 'it was' : 'they were'} not applied — the filter can only name
        values the payload actually contains.
      </p>
    );
  }
  if (notice.kind === 'no_path') {
    return (
      <p className="memory-graph-notice advisory">
        No path connects <span className="mono">{notice.from}</span> and{' '}
        <span className="mono">{notice.to}</span> in this projection — under the current relationship
        filter they are in separate components. That is the honest answer, not a rendering limit.
      </p>
    );
  }
  if (notice.kind === 'path_found') {
    return (
      <p className="memory-graph-notice">
        Found a {notice.hops}-step route from <span className="mono">{notice.from}</span> to{' '}
        <span className="mono">{notice.to}</span>. A route means these files reference one another
        in the project source — it is a navigational lead, not a scientific relationship.
      </p>
    );
  }
  // `notice.count` is what the canvas actually draws — the neighbourhood after
  // the active type / cluster / search filters. Announcing the neighbourhood's
  // own size here read "14 nodes" over a count line saying "0 of 220 nodes
  // shown"; both figures are stated now, and only when they differ.
  const filteredOut = notice.count < notice.neighborhoodSize;
  return (
    <p className="memory-graph-notice">
      Showing the {notice.depth}-hop neighbourhood of <span className="mono">{notice.nodeId}</span> —{' '}
      {notice.count} node{notice.count === 1 ? '' : 's'} shown.
      {filteredOut
        ? ` The neighbourhood holds ${notice.neighborhoodSize} node${
            notice.neighborhoodSize === 1 ? '' : 's'
          }; the rest are hidden by the filters that are on, not missing from the projection.`
        : ''}
      {notice.truncated
        ? ' The neighbourhood hit its display bound, so some connected nodes are not shown here.'
        : ''}
    </p>
  );
}

// --- legend -------------------------------------------------------------------

/*
 * P36V PR2 slice B — the legend now READS as a legend.
 *
 * Before: three run-on text fragments ("circle = file", "diamond = concept",
 * "lines = references … (calls, imports, imports_from, references)") followed by
 * a row of `name · N files` strings. The relation values were joined raw, the
 * count was welded onto the cluster title, and the primary label for a node type
 * was code-style text.
 *
 * Now: named groups, the ACTUAL mark beside a readable Title-Case type name, and
 * the cluster's file count in its own element next to (not inside) its title.
 *
 * WHAT IS NOT RENAMED: cluster names. They are arbitrary upstream data and render
 * verbatim, with the raw cluster id available on `title`. Only the closed
 * five-value relationship vocabulary is relabelled.
 *
 * The coloured-cluster derivation below is UNCHANGED, deliberately: it is the
 * same `communityColorIndex` the canvas paints with. Re-deriving it here (by
 * rank, or by dropping singletons) is exactly how P36R once ended up with a
 * coloured node that had no legend entry while the neutral swatch silently
 * claimed it.
 */
function GraphLegend({ index }: { index: GraphIndex }) {
  const coloured = index.communitiesBySize
    .map((entry) => ({ entry, slot: communityColorIndex(entry.id, index) }))
    .filter((c): c is { entry: GraphCommunityEntry; slot: number } => c.slot !== null);
  const colouredEntries = coloured.map((c) => c.entry);
  const neutralExists =
    coloured.length < index.communitiesBySize.length ||
    index.nodes.some((n) => !n.community_id);
  return (
    <div className="graph-legend">
      {/* <h3>, not <h4>: the card's own heading is the <h2> above, and the
          detail pane beside this legend opens at <h3>. An <h4> here both skipped
          a level and put a deeper heading BEFORE a shallower one in document
          order, which is exactly what a screen-reader outline cannot recover
          from. */}
      <h3 className="graph-legend-heading">Legend</h3>

      <div className="graph-legend-group">
        <p className="graph-legend-group-title">Node Types</p>
        <div className="graph-legend-row">
          <span className="graph-legend-item">
            <span className="graph-legend-swatch shape-file-outline" aria-hidden="true" />
            <span className="graph-legend-name">Files</span>
          </span>
          <span className="graph-legend-item">
            <span className="graph-legend-swatch shape-concept shape-file-outline" aria-hidden="true" />
            <span className="graph-legend-name">Concepts</span>
          </span>
        </div>
      </div>

      {coloured.length > 0 && (
        <div className="graph-legend-group">
          <p className="graph-legend-group-title">Clusters</p>
          <div className="graph-legend-row">
            {coloured.map(({ entry, slot }) => {
              // `communityLabelAmong` is still the authority on WHICH text
              // identifies this cluster (it appends `cluster <id>` when two
              // clusters share a name) — but the file count is rendered as its
              // own element rather than welded into the title.
              const label = communityLabelAmong(entry, colouredEntries);
              const suffix = ` · ${entry.file_count} file${entry.file_count === 1 ? '' : 's'}`;
              const title = label.endsWith(suffix) ? label.slice(0, -suffix.length) : label;
              return (
                <span className="graph-legend-item" key={entry.id} title={`cluster ${entry.id}`}>
                  <span className={`graph-legend-swatch c${slot}`} aria-hidden="true" />
                  <span className="graph-legend-name">{title}</span>
                  <span className="graph-legend-count">
                    {entry.file_count} file{entry.file_count === 1 ? '' : 's'}
                  </span>
                </span>
              );
            })}
            {neutralExists && (
              <span className="graph-legend-item">
                <span className="graph-legend-swatch" aria-hidden="true" />
                <span className="graph-legend-name">Every Other Cluster, and Nodes in No Cluster</span>
              </span>
            )}
          </div>
        </div>
      )}

      <div className="graph-legend-group">
        <p className="graph-legend-group-title">References</p>
        <div className="graph-legend-row">
          <span className="graph-legend-item">
            <span className="graph-legend-swatch graph-legend-line" aria-hidden="true" />
            {/* Each relation is its OWN element carrying the backend's exact
                value on `title`, exactly as a cluster entry carries
                `cluster <id>`. This replaced a second visible copy of the whole
                vocabulary — a `.graph-legend-raw` mono line printing
                `calls · imports · imports_from · references · shares_data_with`
                directly beneath the group that had just listed them in Title
                Case. The raw token is already reachable at the three places
                closer to the action (the filter checkbox's `title`,
                GraphDetail's `title`, and About This Graph → Relationship
                Types, which pairs each label with its value and says which of
                the two the filter matches); an unlabelled row of context-free
                mono tokens on the primary surface was the duplication this
                slice exists to remove. */}
            <span className="graph-legend-name">
              {index.relationTypes.length > 0
                ? index.relationTypes.map((rel, i) => (
                    <span key={rel}>
                      {i > 0 ? ' · ' : ''}
                      <span className="graph-legend-relation" title={rel}>
                        {relationDisplayLabel(rel)}
                      </span>
                    </span>
                  ))
                : 'No relationship values are present in this projection'}
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}

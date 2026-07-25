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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { CircleHelp, LayoutList, Network, Search } from '../components/icons';
import { api, type ApiError } from '../lib/api';
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
  type GraphCommandHistoryEntry,
  type GraphSurfaceContext,
  type GraphUrlParam,
} from '../lib/graphCommands';
import {
  PALETTE_SLOTS,
  applyGraphAction,
  buildGraphIndex,
  communityColorIndex,
  communityLabelAmong,
  communityOptionLabel,
  connectedNodes,
  filteredNodeIds,
  initialGraphViewState,
  visibleEdges,
  visibleNodeIds,
  type GraphAction,
  type GraphCommunityEntry,
  type GraphIndex,
  type GraphTypeFilter,
  type GraphViewState,
} from '../lib/graphModel';
import type { ApiMemoryGraphResponse } from '../lib/types';
import { shortSha } from './ProjectMemory';
import { GraphBrowse, type BrowseGrouping } from './graph/GraphBrowse';
import { GraphCanvas } from './graph/GraphCanvas';
import { GraphCommandBar } from './graph/GraphCommandBar';
import { GraphDetail, GraphPathResult } from './graph/GraphDetail';
import { GraphHelp } from './graph/GraphHelp';

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
  const helpTriggerRef = useRef<HTMLButtonElement | null>(null);
  // The help drawer has THREE openers: the "About this graph" trigger, the
  // command bar's "Syntax" button, and typing `help`. Focus must return to
  // whichever one the user actually used — returning it to the trigger after a
  // typed `help` dropped the user out of the command input they were in.
  const helpReturnRef = useRef<HTMLElement | null>(null);
  const openHelp = useCallback(() => {
    const active = typeof document === 'undefined' ? null : document.activeElement;
    helpReturnRef.current =
      active instanceof HTMLElement && active !== document.body ? active : null;
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
            onClick={openHelp}
          >
            <CircleHelp size={13} strokeWidth={2} aria-hidden="true" />
            About this graph
          </button>
        )}
      </div>
      <p className="memory-graph-subtitle">
        A served-file reference graph derived from Project Memory — leads to verify, never a
        validation verdict.
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
  onOpenHelp: () => void;
}) {
  if (!data.available) {
    return (
      <div className="memory-graph-unavailable">
        <p className="memory-graph-unavailable-title">
          The Graph tab is unavailable — the memory graph is not present on this backend (see
          Project memory status on the Overview tab).
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
  onOpenHelp: () => void;
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
        const outcome = 'Opened the command syntax in About this graph.';
        setCommandError(null);
        // A previous command's notice would otherwise outrank this in the live
        // region and `help` would still announce nothing.
        setState((s) => applyGraphAction(s, { kind: 'dismissNotice' }, index));
        setCommandOutcome(outcome);
        onOpenHelp();
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

  const [communityQuery, setCommunityQuery] = useState('');
  const [grouping, setGrouping] = useState<BrowseGrouping>('type');
  const [pathFrom, setPathFrom] = useState('');
  const [pathTo, setPathTo] = useState('');

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

  const communityOptions = useMemo(() => {
    const needle = communityQuery.trim().toLowerCase();
    const match = (c: (typeof index.communitiesBySize)[number]) =>
      needle === '' ||
      (c.name ?? '').toLowerCase().includes(needle) ||
      c.id.toLowerCase().includes(needle);
    return {
      multi: index.communitiesBySize.filter((c) => !c.isSingleton && match(c)),
      single: index.communitiesBySize.filter((c) => c.isSingleton && match(c)),
    };
  }, [index.communitiesBySize, communityQuery]);

  const navigateToFile = useCallback(
    (path: string) => navigate(`/memory?file=${encodeURIComponent(path)}`),
    [navigate],
  );
  const navigateToConcept = useCallback(
    (id: string) => navigate(`/memory?concept=${encodeURIComponent(id)}`),
    [navigate],
  );

  const meta = data.meta;
  const u = meta.underlying_graph;
  const underlyingKnown = u.node_count != null && u.edge_count != null && u.community_count != null;

  return (
    <div className="memory-graph-available">
      <div className="memory-graph-header">
        <div className="memory-graph-headline">
          <p className="memory-graph-counts">
            {meta.counts.files} files · {meta.counts.concepts} concepts ·{' '}
            {meta.counts.reference_edges} reference{meta.counts.reference_edges === 1 ? '' : 's'} ·{' '}
            {meta.counts.communities_rendered} communit
            {meta.counts.communities_rendered === 1 ? 'y' : 'ies'} shown
          </p>
          <p className="memory-graph-provenance mono">
            {meta.provenance.built_at_commit ? shortSha(meta.provenance.built_at_commit) : '—'} ·
            source{' '}
            {meta.provenance.source_graph_sha256 ? shortSha(meta.provenance.source_graph_sha256) : '—'}{' '}
            · v{meta.provenance.snapshot_schema_version ?? '—'} · {meta.provenance.provider}
          </p>
        </div>
        {/* The `{' '}` is load-bearing: JSX drops the newline between the
            expression and the em dash, which rendered "…here— this Graph tab". */}
        <p className="memory-graph-disclosure">
          {underlyingKnown
            ? `The underlying source graph (${u.node_count} nodes / ${u.edge_count} edges / ${u.community_count} communities) is not embedded here`
            : 'The underlying source graph is not embedded here'}{' '}
          — this Graph tab is a served-file reference projection only, never the full source graph.
        </p>
        {/* The full layer chain stays on the page (not buried in help), but
            collapsed: the one-line disclosure above is the honest headline and
            this is the detail behind it. */}
        <details className="memory-graph-layers-details">
          <summary>How this projection is built</summary>
          <ol className="memory-graph-layers">
            <li>
              Full Graphify source graph
              {underlyingKnown
                ? ` — ${u.node_count} nodes / ${u.edge_count} edges / ${u.community_count} clusters`
                : ''}
              , not embedded in this deployment.
            </li>
            <li>
              Served-file projection — {meta.counts.files} files and {meta.counts.reference_edges}{' '}
              references, the only part governance allows this deployment to serve.
            </li>
            <li>
              Concepts — {meta.counts.concepts} doc-anchored concepts, carrying no edges in this
              projection.
            </li>
            <li>
              Clusters — {meta.counts.communities_rendered} automatically-derived groupings, advisory
              only.
            </li>
          </ol>
        </details>
        {data.truncated && (
          <p className="memory-graph-truncated-note">
            Showing a capped subset of the served-file graph — the node or reference count reached
            its display limit, so not everything indexed is listed here.
          </p>
        )}
      </div>

      {/* mode switch + shared controls — the controls are identical in both
          modes, so they live on one wrapping row with the switch. */}
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
        <label className="memory-graph-filter">
          <span>Show</span>
          <select
            value={state.typeFilter}
            onChange={(e) => dispatch({ kind: 'filterType', value: e.target.value as GraphTypeFilter })}
          >
            <option value="all">Files &amp; concepts</option>
            <option value="file">Files only</option>
            <option value="concept">Concepts only</option>
          </select>
        </label>
        <label className="memory-graph-filter">
          <span>Find a cluster</span>
          <input
            type="text"
            value={communityQuery}
            placeholder="narrow the list…"
            onChange={(e) => setCommunityQuery(e.target.value)}
          />
        </label>
        <label className="memory-graph-filter">
          <span>Community</span>
          <select
            value={state.communityFilter}
            onChange={(e) => dispatch({ kind: 'filterCommunity', id: e.target.value })}
          >
            <option value="all">All clusters</option>
            {communityOptions.multi.length > 0 && (
              <optgroup label="Multi-file clusters">
                {communityOptions.multi.map((c) => (
                  <option key={c.id} value={c.id}>
                    {communityOptionLabel(c)}
                  </option>
                ))}
              </optgroup>
            )}
            {communityOptions.single.length > 0 && (
              <optgroup label="Single-file clusters (label is one file's name)">
                {communityOptions.single.map((c) => (
                  <option key={c.id} value={c.id}>
                    {communityOptionLabel(c)}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
        {state.mode === 'browse' && (
          <label className="memory-graph-filter">
            <span>Group by</span>
            <select value={grouping} onChange={(e) => setGrouping(e.target.value as BrowseGrouping)}>
              <option value="type">File type</option>
              <option value="community">Cluster</option>
            </select>
          </label>
        )}
      </div>
      <p className="memory-graph-community-note">
        Clusters are derived automatically by the upstream graph builder and named after one
        representative node — {index.counts.singletonCommunities} of {index.counts.communities} hold
        a single file. Advisory groupings, not as categories the schema recognises.
      </p>

      <fieldset className="memory-graph-relations">
        <legend>Relationships</legend>
        <div className="memory-graph-relations-row">
          {index.relationTypes.map((rel) => {
            const checked = state.relationFilter === null || state.relationFilter.includes(rel);
            return (
              <label className="memory-graph-relation-check" key={rel}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => {
                    const current = state.relationFilter ?? [...index.relationTypes];
                    const next = current.includes(rel)
                      ? current.filter((r) => r !== rel)
                      : [...current, rel];
                    // Everything ticked is "no filter" (null); anything less is
                    // the exact set — including none, which honestly draws none.
                    dispatch({
                      kind: 'filterRelation',
                      relations: next.length === index.relationTypes.length ? null : next,
                    });
                  }}
                />
                <span className="mono">{rel}</span>
              </label>
            );
          })}
          {index.relationTypes.length === 0 && (
            <span className="memory-graph-relations-note">
              No relationship values are present in this projection.
            </span>
          )}
          <span className="memory-graph-relations-note">
            the backend's own values · unticking one also stops paths travelling through it
          </span>
        </div>
      </fieldset>

      <form
        className="memory-graph-pathform"
        onSubmit={(e) => {
          e.preventDefault();
          dispatch({ kind: 'path', from: pathFrom, to: pathTo });
        }}
      >
        <label className="memory-graph-pathfield">
          <span>Path from</span>
          <input
            type="text"
            value={pathFrom}
            placeholder="file path or concept"
            onChange={(e) => setPathFrom(e.target.value)}
          />
        </label>
        <label className="memory-graph-pathfield">
          <span>Path to</span>
          <input
            type="text"
            value={pathTo}
            placeholder="file path or concept"
            onChange={(e) => setPathTo(e.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-secondary">
          Find path
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            setPathFrom('');
            setPathTo('');
            setCommunityQuery('');
            dispatch({ kind: 'clearFilters' });
          }}
        >
          Clear filters
        </button>
      </form>

      {/* P36R S4 — the deterministic command bar. A bounded grammar over the
          SAME actions the controls above dispatch; it adds no capability the
          controls lack, only a keyboard-first way to reach them. */}
      <GraphCommandBar
        index={index}
        history={history}
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
            />
          ) : (
            <GraphBrowse
              index={index}
              state={state}
              dispatch={dispatch}
              ids={listIds}
              grouping={grouping}
            />
          )}
          {/* Explore only: the legend explains CANVAS marks (shape, colour,
              lines). Browse has no marks — it names every cluster in the rows
              themselves — so showing it there would explain nothing. */}
          {state.mode === 'explore' && <GraphLegend index={index} />}
        </div>

        <div className="memory-graph-side">
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
            onPathFrom={(id) => setPathFrom(id)}
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

function GraphLegend({ index }: { index: GraphIndex }) {
  // ONE source of truth for "which clusters are coloured": the same function
  // the canvas paints with. Re-deriving it here (by rank, or by dropping
  // singletons) is exactly how a coloured node ends up with no legend entry
  // while the neutral swatch silently claims it.
  const coloured = index.communitiesBySize
    .map((entry) => ({ entry, slot: communityColorIndex(entry.id, index) }))
    .filter((c): c is { entry: GraphCommunityEntry; slot: number } => c.slot !== null);
  const colouredEntries = coloured.map((c) => c.entry);
  const neutralExists =
    coloured.length < index.communitiesBySize.length ||
    index.nodes.some((n) => !n.community_id);
  return (
    <div className="graph-legend">
      <p className="graph-legend-row">
        <span className="graph-legend-item">
          <span className="graph-legend-swatch shape-file-outline" aria-hidden="true" />
          circle = file
        </span>
        <span className="graph-legend-item">
          <span className="graph-legend-swatch shape-concept shape-file-outline" aria-hidden="true" />
          diamond = concept
        </span>
        <span className="graph-legend-item">
          lines = references recorded in the projection ({index.relationTypes.join(', ') || 'none'})
        </span>
      </p>
      {coloured.length > 0 && (
        <p className="graph-legend-row">
          {coloured.map(({ entry, slot }) => (
            <span className="graph-legend-item" key={entry.id}>
              <span className={`graph-legend-swatch c${slot}`} aria-hidden="true" />
              {/* `name · N files`, never `name (28) (13)`: upstream names carry
                  their own parenthetical, so a second one reads as the same
                  kind of number. Identical names get their cluster id too. */}
              {communityLabelAmong(entry, colouredEntries)}
            </span>
          ))}
          {neutralExists && (
            <span className="graph-legend-item">
              <span className="graph-legend-swatch" aria-hidden="true" />
              every other cluster, and nodes in no cluster
            </span>
          )}
        </p>
      )}
    </div>
  );
}

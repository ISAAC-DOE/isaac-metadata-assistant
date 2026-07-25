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
import { useCallback, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { CircleHelp, LayoutList, Network, Search } from '../components/icons';
import { api, type ApiError } from '../lib/api';
import { useFetch } from '../lib/useFetch';
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
  type GraphMode,
  type GraphTypeFilter,
  type GraphViewState,
} from '../lib/graphModel';
import type { ApiMemoryGraphResponse } from '../lib/types';
import { shortSha } from './ProjectMemory';
import { GraphBrowse, type BrowseGrouping } from './graph/GraphBrowse';
import { GraphCanvas } from './graph/GraphCanvas';
import { GraphDetail, GraphPathResult } from './graph/GraphDetail';
import { GraphHelp } from './graph/GraphHelp';

/** Narrow viewports open in Browse: a 220-node canvas is not a phone surface.
 *  Guarded for environments without matchMedia (jsdom) — they get Explore. */
function defaultMode(): GraphMode {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'explore';
  return window.matchMedia('(max-width: 860px)').matches ? 'browse' : 'explore';
}

// --- top-level card ---------------------------------------------------------

export function MemoryGraphCard() {
  const graph = useFetch(() => api.getMemoryGraph(), []);
  const [helpOpen, setHelpOpen] = useState(false);
  const helpTriggerRef = useRef<HTMLButtonElement | null>(null);
  const closeHelp = useCallback(() => {
    setHelpOpen(false);
    helpTriggerRef.current?.focus();
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
            onClick={() => setHelpOpen(true)}
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
      {graph.status === 'data' && <MemoryGraphBody data={graph.data} />}
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

function MemoryGraphBody({ data }: { data: ApiMemoryGraphResponse }) {
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
  return <MemoryGraphAvailable data={data} />;
}

// --- available state ---------------------------------------------------------

function MemoryGraphAvailable({ data }: { data: ApiMemoryGraphResponse }) {
  const navigate = useNavigate();
  const index = useMemo<GraphIndex>(() => buildGraphIndex(data), [data]);

  const [state, setState] = useState<GraphViewState>(() => initialGraphViewState(defaultMode()));
  const dispatch = useCallback(
    (action: GraphAction) => setState((s) => applyGraphAction(s, action, index)),
    [index],
  );

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
          empty container announces reliably; one created on demand does not). */}
      <div className="memory-graph-live" aria-live="polite">
        {state.notice && <GraphNoticeView notice={state.notice} dispatch={dispatch} />}
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

function GraphNoticeView({
  notice,
  dispatch,
}: {
  notice: NonNullable<GraphViewState['notice']>;
  dispatch: (action: GraphAction) => void;
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
                {id}
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
  return (
    <p className="memory-graph-notice">
      Showing the {notice.depth}-hop neighbourhood of <span className="mono">{notice.nodeId}</span> —{' '}
      {notice.count} node{notice.count === 1 ? '' : 's'}.
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

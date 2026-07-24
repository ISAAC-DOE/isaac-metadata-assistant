/*
 * P36.2 — Project Memory "Graph" tab. Renders the deterministic, capped,
 * served-file REFERENCE projection from `GET /api/memory/graph`
 * (apps/api/isaac_api/memory_graph.py). This is memory-plane advisory
 * material — leads to verify, never a validation verdict — and it is
 * explicitly NOT the full source graph: the underlying source graph
 * (node_count/edge_count/community_count on `meta.underlying_graph`) is not
 * embedded; this tab only ever renders the smaller served-file projection the
 * backend actually returns.
 *
 * ONE fetch (`api.getMemoryGraph()`); every search/filter/select interaction
 * below is pure client-side state over the single fetched payload — no
 * further network calls.
 *
 * Two coordinated views of the SAME node set:
 *  - A textual node list (search + file-type/community filters + rows) — the
 *    PRIMARY affordance. It alone makes every node reachable and selectable
 *    with no pointer and with the SVG entirely hidden (narrow screens).
 *  - A bounded SVG (secondary) showing ONLY the selected node's capped 1-hop
 *    neighborhood, or one community's nodes — never the full rendered graph
 *    at once. Node positions are deterministically precomputed (no physics,
 *    no randomness): the focal node (or nothing, in community mode) at the
 *    center, the rest on a sorted-by-id ring.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Search, ZoomIn, ZoomOut, Maximize2, RotateCcw } from '../components/icons';
import { api, type ApiError } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import type {
  ApiMemoryFileSummary,
  ApiMemoryGraphConceptNode,
  ApiMemoryGraphEdge,
  ApiMemoryGraphFileNode,
  ApiMemoryGraphNode,
  ApiMemoryGraphResponse,
} from '../lib/types';
import { communityLabel, domId, groupFilesByType, shortSha } from './ProjectMemory';

// -- deterministic layout constants (no physics, no Math.random) -----------
const MAX_RING_NODES = 25; // mirrors the backend's own per-file MAX_RELATED cap
const MAX_COMMUNITY_NODES = 26; // center + ring parity for the community view
const RING_RADIUS = 130;
const VIEWPORT = 340; // base square viewBox extent at scale=1
const MIN_SCALE = 0.4;
const MAX_SCALE = 4;
const PAN_STEP = 26;
const NODE_PADDING = 46;

type NodeTypeFilter = 'all' | 'file' | 'concept';

const isFileNode = (n: ApiMemoryGraphNode): n is ApiMemoryGraphFileNode => n.kind === 'file';
const isConceptNode = (n: ApiMemoryGraphNode): n is ApiMemoryGraphConceptNode => n.kind === 'concept';

// --- top-level card ---------------------------------------------------------

export function MemoryGraphCard() {
  const graph = useFetch(() => api.getMemoryGraph(), []);
  return (
    <div className="card placeholder-card memory-graph-card">
      <h2 className="memory-graph-heading">Graph</h2>
      <p className="memory-graph-subtitle">
        A served-file reference graph derived from Project Memory — leads to verify, never a
        validation verdict.
      </p>
      {graph.status === 'loading' && <LoadingPanel label="Loading graph…" />}
      {graph.status === 'error' && <MemoryGraphError error={graph.error} onRetry={graph.reload} />}
      {graph.status === 'data' && <MemoryGraphBody data={graph.data} />}
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

interface Positioned {
  x: number;
  y: number;
}

function buildIndex(nodes: ApiMemoryGraphNode[], edges: ApiMemoryGraphEdge[]) {
  const byId = new Map<string, ApiMemoryGraphNode>(nodes.map((n) => [n.id, n]));
  const adjacency = new Map<string, { id: string; relations: string[] }[]>();
  for (const e of edges) {
    if (!adjacency.has(e.source)) adjacency.set(e.source, []);
    if (!adjacency.has(e.target)) adjacency.set(e.target, []);
    adjacency.get(e.source)!.push({ id: e.target, relations: e.relations });
    adjacency.get(e.target)!.push({ id: e.source, relations: e.relations });
  }
  for (const list of adjacency.values()) list.sort((a, b) => a.id.localeCompare(b.id));
  return { byId, adjacency };
}

/** A basename for a file path, or the raw label for a concept — kept short for
 *  the SVG's inline text so long repo paths never overflow the canvas. */
function shortNodeLabel(node: ApiMemoryGraphNode): string {
  const raw = node.label ?? node.id;
  const base = node.kind === 'file' ? (raw.split('/').pop() ?? raw) : raw;
  return base.length > 22 ? `${base.slice(0, 21)}…` : base;
}

function MemoryGraphAvailable({ data }: { data: ApiMemoryGraphResponse }) {
  const navigate = useNavigate();
  const { byId, adjacency } = useMemo(() => buildIndex(data.nodes, data.edges), [data.nodes, data.edges]);

  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<NodeTypeFilter>('all');
  const [communityFilter, setCommunityFilter] = useState<string>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selectedNode = selectedId ? (byId.get(selectedId) ?? null) : null;

  const selectNode = useCallback((id: string) => {
    setSelectedId(id);
  }, []);

  const onCommunityFilterChange = useCallback((e: ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    setCommunityFilter(value);
    // Choosing a specific community switches the canvas to that community's
    // view; an active node selection would otherwise keep the canvas pinned
    // to the node's own neighborhood, hiding the very community just picked.
    if (value !== 'all') setSelectedId(null);
  }, []);

  // ---- textual list: search + type + community, all client-side ----------
  const normalizedSearch = search.trim().toLowerCase();
  const passesFilters = useCallback(
    (n: ApiMemoryGraphNode) => {
      if (typeFilter !== 'all' && n.kind !== typeFilter) return false;
      if (communityFilter !== 'all' && (n.community_id ?? '') !== communityFilter) return false;
      if (normalizedSearch) {
        const haystack = `${n.label ?? ''} ${n.id}`.toLowerCase();
        if (!haystack.includes(normalizedSearch)) return false;
      }
      return true;
    },
    [typeFilter, communityFilter, normalizedSearch],
  );

  const filteredFileNodes = useMemo(
    () => data.nodes.filter(isFileNode).filter(passesFilters),
    [data.nodes, passesFilters],
  );
  const filteredConceptNodes = useMemo(
    () => data.nodes.filter(isConceptNode).filter(passesFilters),
    [data.nodes, passesFilters],
  );
  const visibleCount = filteredFileNodes.length + filteredConceptNodes.length;

  // Reuse groupFilesByType (Source Index): the graph's file-node shape is
  // field-identical to ApiMemoryFileSummary except `id` where Source Index
  // uses `path` — a trivial rename lets the SAME grouping function drive both.
  const fileGroups = useMemo(() => {
    const asSummaries: ApiMemoryFileSummary[] = filteredFileNodes.map((n) => ({
      path: n.id,
      file_type: n.file_type,
      community_id: n.community_id,
      community_name: n.community_name,
      node_count: n.node_count,
      on_disk: n.on_disk,
    }));
    return groupFilesByType(asSummaries);
  }, [filteredFileNodes]);

  // ---- the selected node's capped neighbor set (used by BOTH the SVG ring
  // and the detail panel's textual connected-node list — one source) -------
  const neighborEntries = useMemo(() => {
    if (!selectedNode) return [];
    const raw = (adjacency.get(selectedNode.id) ?? []).slice(0, MAX_RING_NODES);
    const withNodes: { node: ApiMemoryGraphNode; relations: string[] }[] = [];
    for (const entry of raw) {
      const n = byId.get(entry.id);
      if (n) withNodes.push({ node: n, relations: entry.relations });
    }
    return withNodes;
  }, [selectedNode, adjacency, byId]);

  // ---- bounded SVG mode: selected node's ego network, OR one community ----
  const svgMode: 'node' | 'community' | 'none' = selectedNode
    ? 'node'
    : communityFilter !== 'all'
      ? 'community'
      : 'none';

  const svgOrder = useMemo<string[]>(() => {
    if (svgMode === 'node' && selectedNode) {
      return [selectedNode.id, ...neighborEntries.map((e) => e.node.id)];
    }
    if (svgMode === 'community') {
      return data.nodes
        .filter((n) => (n.community_id ?? '') === communityFilter)
        .map((n) => n.id)
        .sort((a, b) => a.localeCompare(b))
        .slice(0, MAX_COMMUNITY_NODES);
    }
    return [];
  }, [svgMode, selectedNode, neighborEntries, data.nodes, communityFilter]);

  const positions = useMemo<Map<string, Positioned>>(() => {
    const map = new Map<string, Positioned>();
    if (svgOrder.length === 0) return map;
    if (svgMode === 'node') {
      const [centerId, ...ring] = svgOrder;
      map.set(centerId, { x: 0, y: 0 });
      const k = ring.length;
      ring.forEach((id, i) => {
        const angle = ((-90 + (360 / Math.max(k, 1)) * i) * Math.PI) / 180;
        map.set(id, { x: RING_RADIUS * Math.cos(angle), y: RING_RADIUS * Math.sin(angle) });
      });
    } else {
      const k = svgOrder.length;
      if (k === 1) {
        map.set(svgOrder[0], { x: 0, y: 0 });
      } else {
        svgOrder.forEach((id, i) => {
          const angle = ((-90 + (360 / Math.max(k, 1)) * i) * Math.PI) / 180;
          map.set(id, { x: RING_RADIUS * Math.cos(angle), y: RING_RADIUS * Math.sin(angle) });
        });
      }
    }
    return map;
  }, [svgMode, svgOrder]);

  const svgEdges = useMemo(() => {
    if (positions.size === 0) return [];
    return data.edges.filter((e) => positions.has(e.source) && positions.has(e.target));
  }, [positions, data.edges]);

  // ---- roving tabindex among SVG nodes (mirrors SectionTabs) --------------
  const [rovingId, setRovingId] = useState<string | null>(svgOrder[0] ?? null);
  useEffect(() => {
    setRovingId(svgOrder[0] ?? null);
  }, [svgOrder]);

  function onNodeKeyDown(e: ReactKeyboardEvent<SVGGElement>, id: string) {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      e.stopPropagation();
      selectNode(id);
      return;
    }
    const navKeys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'];
    if (!navKeys.includes(e.key) || svgOrder.length === 0) return;
    e.preventDefault();
    e.stopPropagation();
    const idx = svgOrder.indexOf(id);
    let nextIndex = idx;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') nextIndex = (idx + 1) % svgOrder.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      nextIndex = (idx - 1 + svgOrder.length) % svgOrder.length;
    } else if (e.key === 'Home') nextIndex = 0;
    else if (e.key === 'End') nextIndex = svgOrder.length - 1;
    const nextId = svgOrder[nextIndex];
    setRovingId(nextId);
    (document.getElementById(domId('graph-node', nextId)) as SVGGElement | null)?.focus();
  }

  // ---- pan/zoom: pure viewBox math over the fixed, precomputed positions --
  const [view, setView] = useState({ cx: 0, cy: 0, scale: 1 });
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ startX: number; startY: number; cx: number; cy: number; unitsPerPx: number } | null>(
    null,
  );

  useEffect(() => {
    setView({ cx: 0, cy: 0, scale: 1 });
  }, [svgMode, selectedNode?.id, communityFilter]);

  const clampScale = (s: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));
  const zoomIn = useCallback(() => setView((v) => ({ ...v, scale: clampScale(v.scale * 1.25) })), []);
  const zoomOut = useCallback(() => setView((v) => ({ ...v, scale: clampScale(v.scale / 1.25) })), []);
  const resetView = useCallback(() => setView({ cx: 0, cy: 0, scale: 1 }), []);
  const fitView = useCallback(() => {
    const pts = Array.from(positions.values());
    if (pts.length === 0) {
      resetView();
      return;
    }
    const minX = Math.min(...pts.map((p) => p.x)) - NODE_PADDING;
    const maxX = Math.max(...pts.map((p) => p.x)) + NODE_PADDING;
    const minY = Math.min(...pts.map((p) => p.y)) - NODE_PADDING;
    const maxY = Math.max(...pts.map((p) => p.y)) + NODE_PADDING;
    const w = Math.max(maxX - minX, 60);
    const h = Math.max(maxY - minY, 60);
    setView({ cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, scale: clampScale(VIEWPORT / Math.max(w, h)) });
  }, [positions, resetView]);

  const onSvgPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    const unitsPerPx = VIEWPORT / view.scale / rect.width;
    dragRef.current = { startX: e.clientX, startY: e.clientY, cx: view.cx, cy: view.cy, unitsPerPx };
  };
  const onSvgPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const d = dragRef.current;
    if (!d) return;
    const dx = (e.clientX - d.startX) * d.unitsPerPx;
    const dy = (e.clientY - d.startY) * d.unitsPerPx;
    setView((v) => ({ ...v, cx: d.cx - dx, cy: d.cy - dy }));
  };
  const onSvgPointerUp = () => {
    dragRef.current = null;
  };
  const onSvgKeyDown = (e: ReactKeyboardEvent<SVGSVGElement>) => {
    if (e.target !== e.currentTarget) return; // node-level handlers own their own keys
    const step = PAN_STEP / view.scale;
    if (e.key === 'ArrowLeft') setView((v) => ({ ...v, cx: v.cx - step }));
    else if (e.key === 'ArrowRight') setView((v) => ({ ...v, cx: v.cx + step }));
    else if (e.key === 'ArrowUp') setView((v) => ({ ...v, cy: v.cy - step }));
    else if (e.key === 'ArrowDown') setView((v) => ({ ...v, cy: v.cy + step }));
    else return;
    e.preventDefault();
  };

  const vbExtent = VIEWPORT / view.scale;
  const viewBox = `${view.cx - vbExtent / 2} ${view.cy - vbExtent / 2} ${vbExtent} ${vbExtent}`;

  const meta = data.meta;
  const underlyingKnown =
    meta.underlying_graph.node_count != null &&
    meta.underlying_graph.edge_count != null &&
    meta.underlying_graph.community_count != null;

  const navigateToFile = useCallback(
    (path: string) => navigate(`/memory?file=${encodeURIComponent(path)}`),
    [navigate],
  );
  const navigateToConcept = useCallback(
    (id: string) => navigate(`/memory?concept=${encodeURIComponent(id)}`),
    [navigate],
  );

  const svgAriaLabel =
    svgMode === 'node' && selectedNode
      ? `Neighborhood of ${selectedNode.label ?? selectedNode.id}, ${svgOrder.length} node${svgOrder.length === 1 ? '' : 's'} shown`
      : svgMode === 'community'
        ? `Community ${communityFilter}, ${svgOrder.length} node${svgOrder.length === 1 ? '' : 's'} shown`
        : 'Graph canvas — select a node to see its neighborhood';

  return (
    <div className="memory-graph-available">
      <div className="memory-graph-header">
        <p className="memory-graph-counts">
          {meta.counts.files} files · {meta.counts.concepts} concepts · {meta.counts.reference_edges}{' '}
          reference{meta.counts.reference_edges === 1 ? '' : 's'} · {meta.counts.communities_rendered}{' '}
          communit{meta.counts.communities_rendered === 1 ? 'y' : 'ies'} shown
        </p>
        <p className="memory-graph-disclosure">
          {underlyingKnown
            ? `The underlying source graph (${meta.underlying_graph.node_count} nodes / ${meta.underlying_graph.edge_count} edges / ${meta.underlying_graph.community_count} communities) is not embedded here`
            : 'The underlying source graph is not embedded here'}
          — this Graph tab is a served-file reference projection only, never the full source graph.
        </p>
        {data.truncated && (
          <p className="memory-graph-truncated-note">
            Showing a capped subset of the served-file graph — the node or reference count reached
            its display limit, so not everything indexed is listed here.
          </p>
        )}
        <MemoryGraphLegend />
        <p className="memory-graph-provenance mono">
          {meta.provenance.built_at_commit ? shortSha(meta.provenance.built_at_commit) : '—'} · source{' '}
          {meta.provenance.source_graph_sha256 ? shortSha(meta.provenance.source_graph_sha256) : '—'} · v
          {meta.provenance.snapshot_schema_version ?? '—'} · {meta.provenance.provider}
        </p>
      </div>

      <div className="memory-graph-controls">
        <label className="memory-graph-search-wrap">
          <Search size={14} strokeWidth={2} aria-hidden="true" className="memory-graph-search-icon" />
          <span className="memory-graph-visually-hidden">Search graph nodes</span>
          <input
            type="search"
            className="memory-graph-search-input"
            placeholder="Search files and concepts…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label className="memory-graph-filter">
          <span>Show</span>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as NodeTypeFilter)}>
            <option value="all">Files &amp; concepts</option>
            <option value="file">Files only</option>
            <option value="concept">Concepts only</option>
          </select>
        </label>
        <label className="memory-graph-filter">
          <span>Community</span>
          <select value={communityFilter} onChange={onCommunityFilterChange}>
            <option value="all">All communities</option>
            {data.communities.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name ?? `Community ${c.id}`} ({c.file_count})
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="memory-graph-list-summary" aria-live="polite">
        {visibleCount} of {data.nodes.length} nodes shown
      </p>

      <div className="memory-graph-body">
        <div className="memory-graph-list-pane">
          <div className="memory-graph-list" role="group" aria-label="Graph nodes">
            {visibleCount === 0 && (
              <p className="memory-graph-list-empty">No nodes match the current search or filters.</p>
            )}
            {typeFilter !== 'concept' &&
              fileGroups.map((group) => (
                <div className="memory-graph-list-group" key={group.key}>
                  <h3 className="memory-graph-list-group-heading">
                    {group.label}
                    <span className="memory-graph-list-group-count">{group.files.length}</span>
                  </h3>
                  <ul className="memory-graph-list-rows">
                    {group.files.map((f) => (
                      <MemoryGraphListRow
                        key={f.path}
                        label={f.path}
                        kind="file"
                        community={communityLabel(f)}
                        selected={selectedId === f.path}
                        onSelect={() => selectNode(f.path)}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            {typeFilter !== 'file' && filteredConceptNodes.length > 0 && (
              <div className="memory-graph-list-group">
                <h3 className="memory-graph-list-group-heading">
                  Concepts
                  <span className="memory-graph-list-group-count">{filteredConceptNodes.length}</span>
                </h3>
                <ul className="memory-graph-list-rows">
                  {filteredConceptNodes.map((c) => (
                    <MemoryGraphListRow
                      key={c.id}
                      label={c.label ?? c.id}
                      kind="concept"
                      community={communityLabel(c)}
                      selected={selectedId === c.id}
                      onSelect={() => selectNode(c.id)}
                    />
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        <div className="memory-graph-canvas-pane">
          <div className="memory-graph-canvas-controls">
            <button type="button" className="btn btn-secondary" onClick={fitView} aria-label="Fit graph to view">
              <Maximize2 size={14} strokeWidth={2} aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-secondary" onClick={zoomIn} aria-label="Zoom in">
              <ZoomIn size={14} strokeWidth={2} aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-secondary" onClick={zoomOut} aria-label="Zoom out">
              <ZoomOut size={14} strokeWidth={2} aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-secondary" onClick={resetView} aria-label="Reset view">
              <RotateCcw size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          </div>
          <div className="memory-graph-canvas-scroll">
            {svgMode === 'none' ? (
              <p className="memory-graph-canvas-empty">
                Select a file or concept from the list, or pick a community above, to see its
                bounded neighborhood here.
              </p>
            ) : (
              <svg
                ref={svgRef}
                className="memory-graph-svg"
                viewBox={viewBox}
                role="group"
                aria-label={svgAriaLabel}
                tabIndex={0}
                onKeyDown={onSvgKeyDown}
                onPointerDown={onSvgPointerDown}
                onPointerMove={onSvgPointerMove}
                onPointerUp={onSvgPointerUp}
                onPointerLeave={onSvgPointerUp}
              >
                <g className="memory-graph-edges">
                  {svgEdges.map((e) => {
                    const p1 = positions.get(e.source);
                    const p2 = positions.get(e.target);
                    if (!p1 || !p2) return null;
                    return (
                      <line
                        key={`${e.source}|${e.target}`}
                        className="memory-graph-edge"
                        x1={p1.x}
                        y1={p1.y}
                        x2={p2.x}
                        y2={p2.y}
                      />
                    );
                  })}
                </g>
                <g className="memory-graph-nodes">
                  {svgOrder.map((id) => {
                    const node = byId.get(id);
                    const pos = positions.get(id);
                    if (!node || !pos) return null;
                    return (
                      <GraphNodeShape
                        key={id}
                        node={node}
                        x={pos.x}
                        y={pos.y}
                        isRoving={rovingId === id}
                        isSelected={selectedId === id}
                        onSelect={() => selectNode(id)}
                        onKeyDown={(e) => onNodeKeyDown(e, id)}
                      />
                    );
                  })}
                </g>
              </svg>
            )}
          </div>
        </div>
      </div>

      {selectedNode && (
        <MemoryGraphDetailPanel
          node={selectedNode}
          neighborEntries={neighborEntries}
          onSelect={selectNode}
          onNavigateFile={navigateToFile}
          onNavigateConcept={navigateToConcept}
        />
      )}
    </div>
  );
}

// --- legend -----------------------------------------------------------------

function MemoryGraphLegend() {
  return (
    <p className="memory-graph-legend">
      <span className="memory-graph-legend-item">
        <span className="memory-graph-legend-shape memory-graph-legend-circle" aria-hidden="true" />
        file
      </span>
      <span className="memory-graph-legend-item">
        <span className="memory-graph-legend-shape memory-graph-legend-diamond" aria-hidden="true" />
        concept
      </span>
      <span className="memory-graph-legend-item">
        reference-type edges: imports, calls, references, imports_from, shares_data_with
      </span>
    </p>
  );
}

// --- textual list row ---------------------------------------------------------

function MemoryGraphListRow({
  label,
  kind,
  community,
  selected,
  onSelect,
}: {
  label: string;
  kind: 'file' | 'concept';
  community: string | null;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li className="memory-graph-list-row">
      <button
        type="button"
        className={`memory-graph-list-row-btn${selected ? ' selected' : ''}`}
        aria-pressed={selected}
        onClick={onSelect}
      >
        <span
          className={`memory-graph-list-shape memory-graph-list-shape-${kind}`}
          aria-hidden="true"
        />
        <span className="memory-graph-list-label mono">{label}</span>
        {community && <span className="memory-graph-list-community">{community}</span>}
      </button>
    </li>
  );
}

// --- SVG node shape -----------------------------------------------------------

function GraphNodeShape({
  node,
  x,
  y,
  isRoving,
  isSelected,
  onSelect,
  onKeyDown,
}: {
  node: ApiMemoryGraphNode;
  x: number;
  y: number;
  isRoving: boolean;
  isSelected: boolean;
  onSelect: () => void;
  onKeyDown: (e: ReactKeyboardEvent<SVGGElement>) => void;
}) {
  const label = node.label ?? node.id;
  const community = communityLabel(node);
  const ariaLabel = `${label}, ${node.kind}${community ? `, ${community}` : ''}${isSelected ? ', selected' : ''}`;
  return (
    <g
      id={domId('graph-node', node.id)}
      role="button"
      tabIndex={isRoving ? 0 : -1}
      aria-label={ariaLabel}
      aria-pressed={isSelected}
      className={`memory-graph-node memory-graph-node-${node.kind}${isSelected ? ' selected' : ''}`}
      transform={`translate(${x} ${y})`}
      onClick={onSelect}
      onKeyDown={onKeyDown}
    >
      {node.kind === 'file' ? (
        <circle className="memory-graph-node-shape" r={14} />
      ) : (
        <polygon className="memory-graph-node-shape" points="0,-16 16,0 0,16 -16,0" />
      )}
      <text className="memory-graph-node-label" y={30} textAnchor="middle">
        {shortNodeLabel(node)}
      </text>
    </g>
  );
}

// --- detail panel ---------------------------------------------------------

function MemoryGraphDetailPanel({
  node,
  neighborEntries,
  onSelect,
  onNavigateFile,
  onNavigateConcept,
}: {
  node: ApiMemoryGraphNode;
  neighborEntries: { node: ApiMemoryGraphNode; relations: string[] }[];
  onSelect: (id: string) => void;
  onNavigateFile: (path: string) => void;
  onNavigateConcept: (id: string) => void;
}) {
  const community = communityLabel(node);
  return (
    <div className="memory-graph-detail" aria-live="polite">
      <h3 className="memory-graph-detail-title mono">{node.label ?? node.id}</h3>
      <dl className="memory-graph-detail-figures">
        <div className="memory-graph-detail-figure">
          <dt>Kind</dt>
          <dd>{node.kind === 'file' ? 'File' : 'Concept'}</dd>
        </div>
        <div className="memory-graph-detail-figure">
          <dt>Community</dt>
          <dd>{community ?? '—'}</dd>
        </div>
        <div className="memory-graph-detail-figure">
          <dt>Community ID</dt>
          <dd className="mono">{node.community_id ?? '—'}</dd>
        </div>
        {node.kind === 'file' && (
          <div className="memory-graph-detail-figure">
            <dt>Nodes</dt>
            <dd className="mono">{node.node_count}</dd>
          </div>
        )}
      </dl>

      {node.on_disk ? (
        <p className="memory-graph-detail-ondisk">present locally on this backend (not opened here)</p>
      ) : (
        <p className="memory-graph-detail-ondisk-missing">not present on this backend — cannot open</p>
      )}

      {node.kind === 'file' ? (
        <button type="button" className="btn btn-secondary" onClick={() => onNavigateFile(node.id)}>
          View in Sources
        </button>
      ) : (
        <button type="button" className="btn btn-secondary" onClick={() => onNavigateConcept(node.id)}>
          View in Concepts
        </button>
      )}

      <div className="memory-graph-detail-section">
        <h4 className="memory-graph-detail-section-heading">Connected nodes</h4>
        {neighborEntries.length > 0 ? (
          <ul className="memory-graph-detail-connected-list">
            {neighborEntries.map(({ node: n, relations }) => (
              <li key={n.id}>
                <button
                  type="button"
                  className="memory-graph-detail-connected-link"
                  onClick={() => onSelect(n.id)}
                >
                  <span className="mono">{n.label ?? n.id}</span>
                  {relations.length > 0 && (
                    <span className="memory-graph-detail-relation">{relations.join(', ')}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="memory-graph-detail-empty-note">
            no recorded connections for this node in the rendered graph
          </p>
        )}
      </div>

      <details className="memory-graph-detail-raw">
        <summary>Raw node data</summary>
        <pre className="mono">{JSON.stringify(node, null, 2)}</pre>
      </details>
    </div>
  );
}

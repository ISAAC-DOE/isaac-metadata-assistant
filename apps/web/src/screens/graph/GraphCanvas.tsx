/*
 * Explore mode — a bounded DARK canvas inside the light ISAAC shell.
 *
 * Determinism: this component draws coordinates; it never computes them from
 * anything time- or frame-dependent. Every position comes from
 * `index.layout` (a pure, fixed-iteration function of the payload) or from an
 * explicit user drag stored in `state.moved`. There is no physics loop, no
 * requestAnimationFrame settling and no Math.random anywhere in the path.
 *
 * Honesty: the ONLY edges drawn are objects taken from `index.edges`, which is
 * built from the payload's own `edges[]`. `visibleEdges` can filter that list;
 * nothing in this file can add to it.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { Maximize2, RotateCcw, ZoomIn, ZoomOut } from '../../components/icons';
import type { ApiMemoryGraphEdge, ApiMemoryGraphNode } from '../../lib/types';
import {
  HUB_LABEL_COUNT,
  LABEL_LIMIT,
  VIEW_EXTENT,
  canvasNodeLabel,
  communityColorIndex,
  edgeKey,
  nodePosition,
  placedLabelIds,
  viewBoxOf,
  type GraphAction,
  type GraphIndex,
  type GraphViewState,
} from '../../lib/graphModel';
import { domId } from '../ProjectMemory';
import { communityText } from './GraphDetail';

const CLICK_SLOP_PX = 4;
const FILE_RADIUS = 9;
/** Also the label baseline offset mirrored by graphModel's LABEL_BASELINE_UNITS. */
const CONCEPT_RADIUS = 11;

/**
 * Zoom / fit / reset keys, resolved to an action.
 *
 * Shared by the canvas handler and the node handler: GraphHelp documents these
 * keys alongside the node-navigation keys, so they have to work while a node
 * holds focus too — otherwise the help over-promises.
 */
function viewportAction(key: string): GraphAction | null {
  if (key === '+' || key === '=') return { kind: 'zoom', factor: 1.25 };
  if (key === '-' || key === '_') return { kind: 'zoom', factor: 1 / 1.25 };
  if (key === '0') return { kind: 'reset' };
  if (key === 'f' || key === 'F') return { kind: 'fit' };
  return null;
}

interface GraphCanvasProps {
  index: GraphIndex;
  state: GraphViewState;
  dispatch: (action: GraphAction) => void;
  visibleIds: string[];
  edges: ApiMemoryGraphEdge[];
}

export function GraphCanvas({ index, state, dispatch, visibleIds, edges }: GraphCanvasProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);

  // Roving tabindex over the visible node set (mirrors SectionTabs).
  const [rovingId, setRovingId] = useState<string | null>(visibleIds[0] ?? null);
  useEffect(() => {
    setRovingId((current) => (current && visibleIds.includes(current) ? current : (visibleIds[0] ?? null)));
  }, [visibleIds]);

  const visibleSet = useMemo(() => new Set(visibleIds), [visibleIds]);

  const connectedToSelected = useMemo(() => {
    if (!state.selectedId) return new Set<string>();
    return new Set((index.adjacency.get(state.selectedId) ?? []).map((n) => n.id));
  }, [state.selectedId, index.adjacency]);

  const pathEdgeKeys = useMemo(() => {
    if (state.focus?.kind !== 'path') return new Set<string>();
    const keys = new Set<string>();
    const route = state.focus.ordered;
    for (let i = 0; i + 1 < route.length; i += 1) keys.add(edgeKey(route[i], route[i + 1]));
    return keys;
  }, [state.focus]);

  // Labelling. Below LABEL_LIMIT every visible node is labelled. ABOVE it the
  // canvas is not left mute — a 220-node overview with no text is a picture of
  // dots with nothing to orient by — so up to HUB_LABEL_COUNT landmarks stay
  // labelled: most-connected first, collision-filtered so they read as
  // landmarks rather than a smear (see placedLabelIds).
  const showAllLabels = visibleIds.length <= LABEL_LIMIT;
  const hubLabels = useMemo(
    () => (showAllLabels ? null : new Set(placedLabelIds(visibleIds, index, state.moved))),
    [showAllLabels, visibleIds, index, state.moved],
  );

  /** Visible nodes with no recorded reference at all — the outer-ring belt. */
  const isolatedVisible = useMemo(
    () => visibleIds.filter((id) => (index.adjacency.get(id)?.length ?? 0) === 0).length,
    [visibleIds, index.adjacency],
  );

  /** User units per CSS pixel, for the square viewBox under xMidYMid meet. */
  const unitsPerPx = useCallback(() => {
    const rect = svgRef.current?.getBoundingClientRect();
    const extent = VIEW_EXTENT / state.view.scale;
    if (!rect || rect.width === 0 || rect.height === 0) return extent / 600;
    return extent / Math.min(rect.width, rect.height);
  }, [state.view.scale]);

  // One pointer gesture at a time: either panning the background or dragging a
  // node. Kept in a ref so a move event never depends on a re-render landing.
  const gesture = useRef<
    | { kind: 'pan'; lastX: number; lastY: number; moved: number }
    | { kind: 'node'; id: string; lastX: number; lastY: number; moved: number; x: number; y: number }
    | null
  >(null);

  const onCanvasPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    gesture.current = { kind: 'pan', lastX: e.clientX, lastY: e.clientY, moved: 0 };
  };

  const onNodePointerDown = (e: ReactPointerEvent<SVGGElement>, id: string) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const pos = nodePosition(id, state, index);
    if (!pos) return;
    gesture.current = { kind: 'node', id, lastX: e.clientX, lastY: e.clientY, moved: 0, x: pos.x, y: pos.y };
  };

  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const g = gesture.current;
    if (!g) return;
    const upp = unitsPerPx();
    const dxPx = e.clientX - g.lastX;
    const dyPx = e.clientY - g.lastY;
    g.lastX = e.clientX;
    g.lastY = e.clientY;
    g.moved += Math.abs(dxPx) + Math.abs(dyPx);
    if (g.kind === 'pan') {
      // Dragging the background right moves the CONTENT right, so the viewport
      // centre moves left.
      dispatch({ kind: 'pan', dx: -dxPx * upp, dy: -dyPx * upp });
    } else {
      g.x += dxPx * upp;
      g.y += dyPx * upp;
      dispatch({ kind: 'moveNode', nodeId: g.id, x: g.x, y: g.y });
    }
  };

  const onPointerUp = () => {
    const g = gesture.current;
    gesture.current = null;
    // A press that never really moved is a click, not a drag.
    if (g && g.kind === 'node' && g.moved < CLICK_SLOP_PX) {
      dispatch({ kind: 'select', nodeId: g.id });
    }
  };

  const onCanvasKeyDown = (e: ReactKeyboardEvent<SVGSVGElement>) => {
    if (e.target !== e.currentTarget) return; // node handlers own their own keys
    const step = (VIEW_EXTENT / state.view.scale) * 0.08;
    const viewport = viewportAction(e.key);
    if (viewport) dispatch(viewport);
    else if (e.key === 'ArrowLeft') dispatch({ kind: 'pan', dx: -step, dy: 0 });
    else if (e.key === 'ArrowRight') dispatch({ kind: 'pan', dx: step, dy: 0 });
    else if (e.key === 'ArrowUp') dispatch({ kind: 'pan', dx: 0, dy: -step });
    else if (e.key === 'ArrowDown') dispatch({ kind: 'pan', dx: 0, dy: step });
    else return;
    e.preventDefault();
  };

  const onNodeKeyDown = (e: ReactKeyboardEvent<SVGGElement>, id: string) => {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      e.stopPropagation();
      dispatch({ kind: 'select', nodeId: id });
      return;
    }
    // Zoom/fit/reset while a NODE holds focus. The canvas handler ignores
    // bubbled node events (arrow keys mean "move between nodes" there), so
    // these are forwarded explicitly rather than left silently dead.
    const viewport = viewportAction(e.key);
    if (viewport) {
      e.preventDefault();
      e.stopPropagation();
      dispatch(viewport);
      return;
    }
    const navKeys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'];
    if (!navKeys.includes(e.key) || visibleIds.length === 0) return;
    e.preventDefault();
    e.stopPropagation();
    const idx = visibleIds.indexOf(id);
    let next = idx;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % visibleIds.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      next = (idx - 1 + visibleIds.length) % visibleIds.length;
    } else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = visibleIds.length - 1;
    const nextId = visibleIds[next];
    setRovingId(nextId);
    (document.getElementById(domId('graph-node', nextId)) as SVGGElement | null)?.focus();
  };

  const hoverNode = hoverId ? index.byId.get(hoverId) : null;
  const canvasLabel = `Graph canvas — ${visibleIds.length} node${visibleIds.length === 1 ? '' : 's'} and ${edges.length} reference${edges.length === 1 ? '' : 's'} drawn. Arrow keys pan; Tab reaches the nodes.`;

  return (
    <div className="graph-explore">
      <div className="graph-explore-toolbar">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => dispatch({ kind: 'fit' })}
          aria-label="Fit graph to view"
        >
          <Maximize2 size={14} strokeWidth={2} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => dispatch({ kind: 'zoom', factor: 1.25 })}
          aria-label="Zoom in"
        >
          <ZoomIn size={14} strokeWidth={2} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => dispatch({ kind: 'zoom', factor: 1 / 1.25 })}
          aria-label="Zoom out"
        >
          <ZoomOut size={14} strokeWidth={2} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => dispatch({ kind: 'reset' })}
          aria-label="Reset view"
        >
          <RotateCcw size={14} strokeWidth={2} aria-hidden="true" />
        </button>
        <span className="graph-explore-toolbar-sep" aria-hidden="true" />
        <span className="memory-graph-modenote">
          zoom {Math.round(state.view.scale * 100)}%
        </span>
      </div>

      <div className="graph-canvas">
        {visibleIds.length === 0 ? (
          <p className="graph-canvas-empty">
            No nodes match the current search, filters or focus — nothing is drawn rather than
            something approximate.
          </p>
        ) : (
          <svg
            ref={svgRef}
            className="memory-graph-svg"
            viewBox={viewBoxOf(state.view)}
            preserveAspectRatio="xMidYMid meet"
            role="group"
            aria-label={canvasLabel}
            tabIndex={0}
            onKeyDown={onCanvasKeyDown}
            onPointerDown={onCanvasPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerUp}
          >
            <g className="memory-graph-edges">
              {edges.map((e) => {
                const p1 = nodePosition(e.source, state, index);
                const p2 = nodePosition(e.target, state, index);
                if (!p1 || !p2) return null;
                const key = edgeKey(e.source, e.target);
                const lit =
                  pathEdgeKeys.has(key) ||
                  (state.selectedId !== null &&
                    (e.source === state.selectedId || e.target === state.selectedId));
                return (
                  <line
                    key={key}
                    /* The canonical payload key, exposed so a test can prove
                       every DRAWN edge exists in the fetched payload. */
                    data-edge={key}
                    className={`memory-graph-edge${lit ? ' lit' : ''}`}
                    x1={p1.x}
                    y1={p1.y}
                    x2={p2.x}
                    y2={p2.y}
                  />
                );
              })}
            </g>
            <g className="memory-graph-nodes">
              {visibleIds.map((id) => {
                const node = index.byId.get(id);
                const pos = nodePosition(id, state, index);
                if (!node || !pos) return null;
                return (
                  <CanvasNode
                    key={id}
                    node={node}
                    x={pos.x}
                    y={pos.y}
                    index={index}
                    isSelected={state.selectedId === id}
                    isConnected={connectedToSelected.has(id)}
                    /* Dim the rest only when the selected node is actually ON
                       this canvas. Otherwise a selection made before a filter
                       greys out every node with nothing left highlighted. */
                    isDim={
                      state.selectedId !== null &&
                      visibleSet.has(state.selectedId) &&
                      state.selectedId !== id &&
                      !connectedToSelected.has(id)
                    }
                    showLabel={
                      showAllLabels ||
                      (hubLabels?.has(id) ?? false) ||
                      state.selectedId === id ||
                      hoverId === id ||
                      connectedToSelected.has(id)
                    }
                    isRoving={rovingId === id}
                    onPointerDown={(e) => onNodePointerDown(e, id)}
                    onKeyDown={(e) => onNodeKeyDown(e, id)}
                    onHover={() => setHoverId(id)}
                    onLeave={() => setHoverId((h) => (h === id ? null : h))}
                  />
                );
              })}
            </g>
          </svg>
        )}

        {hoverNode && (
          <div className="graph-canvas-overlay graph-canvas-hover">
            <span className="mono">{hoverNode.label ?? hoverNode.id}</span>
            <br />
            <span className="graph-canvas-hover-meta">
              {hoverNode.kind === 'file' ? 'file' : 'concept'}
              {communityText(hoverNode) ? ` · ${communityText(hoverNode)}` : ''}
            </span>
          </div>
        )}
      </div>

      {visibleSet.size > 0 && index.renderTruncated && (
        <p className="memory-graph-truncated-note">
          The canvas draws at most {index.renderIds.length} of {index.counts.total} nodes at once.
          The rest are reachable in Browse and through search — they are not silently discarded.
        </p>
      )}

      <p className="graph-canvas-caption">
        Drag the background to pan, drag a node to move it. Every visible node is labelled once{' '}
        {LABEL_LIMIT} or fewer are shown; above that up to {HUB_LABEL_COUNT} of the most-connected
        nodes stay labelled as landmarks, along with the selected node and its connections.
        {isolatedVisible > 0 && (
          <>
            {' '}
            {isolatedVisible} of the nodes drawn here have no recorded reference at all and sit on
            the outer rings — the ring is where they are parked, not a relationship between them.
          </>
        )}
      </p>
    </div>
  );
}

function CanvasNode({
  node,
  x,
  y,
  index,
  isSelected,
  isConnected,
  isDim,
  showLabel,
  isRoving,
  onPointerDown,
  onKeyDown,
  onHover,
  onLeave,
}: {
  node: ApiMemoryGraphNode;
  x: number;
  y: number;
  index: GraphIndex;
  isSelected: boolean;
  isConnected: boolean;
  isDim: boolean;
  showLabel: boolean;
  isRoving: boolean;
  onPointerDown: (e: ReactPointerEvent<SVGGElement>) => void;
  onKeyDown: (e: ReactKeyboardEvent<SVGGElement>) => void;
  onHover: () => void;
  onLeave: () => void;
}) {
  const slot = communityColorIndex(node.community_id, index);
  const community = communityText(node);
  const label = node.label ?? node.id;
  const ariaLabel = `${label}, ${node.kind}${community ? `, ${community}` : ''}${isSelected ? ', selected' : ''}`;
  const classes = [
    'memory-graph-node',
    `memory-graph-node-${node.kind}`,
    slot !== null ? `memory-graph-node-c${slot}` : '',
    isSelected ? 'selected' : '',
    isConnected ? 'connected' : '',
    isDim ? 'dim' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <g
      id={domId('graph-node', node.id)}
      role="button"
      tabIndex={isRoving ? 0 : -1}
      aria-label={ariaLabel}
      aria-pressed={isSelected}
      className={classes}
      transform={`translate(${x} ${y})`}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      onPointerEnter={onHover}
      onPointerLeave={onLeave}
      onFocus={onHover}
      onBlur={onLeave}
    >
      {node.kind === 'file' ? (
        <circle className="memory-graph-node-shape" r={FILE_RADIUS} />
      ) : (
        <polygon
          className="memory-graph-node-shape"
          points={`0,${-CONCEPT_RADIUS} ${CONCEPT_RADIUS},0 0,${CONCEPT_RADIUS} ${-CONCEPT_RADIUS},0`}
        />
      )}
      {showLabel && (
        <text className="memory-graph-node-label" y={CONCEPT_RADIUS + 13} textAnchor="middle">
          {canvasNodeLabel(node)}
        </text>
      )}
    </g>
  );
}

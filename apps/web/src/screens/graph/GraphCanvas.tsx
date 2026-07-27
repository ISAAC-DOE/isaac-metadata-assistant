/*
 * Explore mode — a bounded DARK canvas inside the light ISAAC shell, with
 * SEMANTIC ZOOM (P36V.1 Unit F).
 *
 * Three levels of detail, each driven by a real field of the data (see
 * `lib/graphDeep.ts` for the measurements that establish the hierarchy):
 *   `file`    — the served-file projection from `GET /api/memory/graph`.
 *   `cluster` — (source_file, community_id) groups from the deep payload.
 *   `symbol`  — individual deep nodes and the payload's own edges, with
 *               direction preserved.
 * Zooming past a threshold reveals the next level; there is no mode switch, and
 * the deeper layers are LAZILY fetched — a visit that never zooms never pays for
 * them.
 *
 * Determinism: this component draws coordinates; it never computes them from
 * anything time- or frame-dependent. Every base position comes from
 * `index.layout` (a pure, fixed-iteration function of the payload) or from an
 * explicit user drag stored in `state.moved`; every deep position is that base
 * position plus a pure golden-angle offset from `graphDeep`. There is no physics
 * loop, no requestAnimationFrame settling and no Math.random anywhere in the path.
 *
 * Honesty: the ONLY edges drawn are objects taken from `index.edges` (base) or
 * reductions over the deep payload's own `edges[]` (deep). A deep line carries
 * `data-edge-index`, the payload row it stands for, and `data-edge-backing`, how
 * many real payload edges it folds — so a test can prove nothing was invented.
 * Neither layer can ADD an edge.
 *
 * Screen-space sizing: marks, labels and strokes are declared in user units AT
 * SCALE 1 and divided by the live scale, so their RENDERED size is invariant
 * under zoom (`screenBoundedUnits`). Before this, `FILE_RADIUS`, the stroke
 * widths and the 11px label font were constants in user units — which is why
 * zooming to 477% magnified everything instead of revealing anything.
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
import { Maximize2, Network, RotateCcw, ZoomIn, ZoomOut } from '../../components/icons';
import { relationDisplayLabel } from '../../lib/displayLabels';
import type { ApiMemoryGraphEdge, ApiMemoryGraphNode } from '../../lib/types';
import {
  HUB_LABEL_COUNT,
  LABEL_LIMIT,
  LABEL_UNITS,
  LOD_CLUSTER_SCALE,
  MARK_UNITS,
  SELECTED_MARK_FACTOR,
  VIEW_EXTENT,
  canvasNodeLabel,
  communityColorIndex,
  edgeKey,
  graphLodLevel,
  nextLodScale,
  nodePosition,
  placedLabelIds,
  screenBoundedUnits,
  viewBoxOf,
  type GraphAction,
  type GraphIndex,
  type GraphLodLevel,
  type GraphViewState,
} from '../../lib/graphModel';
import {
  deepRelationSummary,
  deepRenderPlan,
  stalenessSentence,
  deepStaleness,
  type DeepIndex,
  type DeepRenderNode,
  type DeepRenderPlan,
} from '../../lib/graphDeep';
import { domId } from '../ProjectMemory';
import { communityText } from './GraphDetail';

const CLICK_SLOP_PX = 4;

/**
 * The lazily fetched deep layer, as the canvas sees it. `idle` means the reader
 * has never zoomed past the first threshold, so nothing was fetched at all.
 */
export type DeepLayerState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'unavailable'; reason: string | null }
  | { status: 'ready'; index: DeepIndex };

/** Label font reference for a file REGION outline (user units at scale 1). */
const REGION_LABEL_UNITS = 12;
/** Arrowhead length reference (user units at scale 1). Deep edges only: the
 *  base projection's edges are de-duplicated and undirected, so drawing an
 *  arrow there would assert a direction the base payload does not carry. */
const ARROW_UNITS = 7;
/** Above this many deep marks, only landmarks / hover / selection are labelled. */
const DEEP_LABEL_LIMIT = 24;
/** Label halo width reference (user units at scale 1) — mirrors the P36R
 *  `stroke-width: 3px` rule that used to live in graph.css. */
const LABEL_HALO_UNITS = 3;

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

/** What the pointer or the keyboard is currently on. */
type HoverTarget = { layer: 'base' | 'deep'; id: string } | null;

interface TooltipContent {
  title: string;
  kind: string;
  cluster: string | null;
  connections: string;
  source: string | null;
  relationships: string | null;
}

interface GraphCanvasProps {
  index: GraphIndex;
  state: GraphViewState;
  dispatch: (action: GraphAction) => void;
  visibleIds: string[];
  edges: ApiMemoryGraphEdge[];
  /** P36V.1 F — the deep layer. Omitted ⇒ the surface behaves exactly as before. */
  deep?: DeepLayerState;
  /** The pinned deep mark, owned by MemoryGraphCard so the detail pane (and a
   *  later suggestions unit) can read it without reaching into the canvas. */
  deepSelectedId?: string | null;
  onDeepSelect?: (id: string | null) => void;
}

export function GraphCanvas({
  index,
  state,
  dispatch,
  visibleIds,
  edges,
  deep = { status: 'idle' },
  deepSelectedId = null,
  onDeepSelect,
}: GraphCanvasProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hover, setHover] = useState<HoverTarget>(null);

  const scale = state.view.scale;
  const level: GraphLodLevel = graphLodLevel(scale);
  const deepIndex = deep.status === 'ready' ? deep.index : null;

  /**
   * The deeper levels are suspended while a NEIGHBOURHOOD or PATH focus is
   * active. That focus was computed over the base projection, so drawing
   * symbol-level marks instead would show a set the focus never selected — the
   * canvas would contradict the focus chip above it. Stated on screen, not
   * silently.
   */
  const focusSuspends = state.focus !== null;
  const deepLevel: 'cluster' | 'symbol' | null =
    level === 'file' || focusSuspends || !deepIndex ? null : level;

  const plan: DeepRenderPlan | null = useMemo(
    () =>
      deepIndex && deepLevel
        ? deepRenderPlan(deepIndex, index, state, visibleIds, deepLevel, deepSelectedId)
        : null,
    [deepIndex, deepLevel, index, state, visibleIds, deepSelectedId],
  );

  // --- focus ring over whatever is actually rendered -------------------------
  // ONE roving tabindex, over the marks on screen: base ids at the file level,
  // deep keys below it. This is the accessibility contract the SVG model exists
  // for — every mark is a real focusable <g role="button">, so the keyboard
  // reaches the deep layer exactly as the pointer does.
  const focusIds = useMemo(
    () => (plan ? plan.nodes.map((n) => n.id) : visibleIds),
    [plan, visibleIds],
  );
  const domPrefix = plan ? 'graph-deep-node' : 'graph-node';
  const [rovingId, setRovingId] = useState<string | null>(focusIds[0] ?? null);
  useEffect(() => {
    setRovingId((current) => (current && focusIds.includes(current) ? current : (focusIds[0] ?? null)));
  }, [focusIds]);

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

  /** Deep marks that keep a standing label: all of them while few are drawn,
   *  otherwise the largest groups / most-connected symbols (the plan is already
   *  in that order), bounded. Hover, focus and selection add their own. */
  const deepLabelIds = useMemo(() => {
    if (!plan) return new Set<string>();
    if (plan.nodes.length <= DEEP_LABEL_LIMIT) return new Set(plan.nodes.map((n) => n.id));
    if (plan.level === 'symbol') return new Set<string>();
    return new Set(plan.nodes.slice(0, HUB_LABEL_COUNT).map((n) => n.id));
  }, [plan]);

  /** Visible nodes with no recorded reference at all — the outer-ring belt. */
  const isolatedVisible = useMemo(
    () => visibleIds.filter((id) => (index.adjacency.get(id)?.length ?? 0) === 0).length,
    [visibleIds, index.adjacency],
  );

  /** User units per CSS pixel, for the square viewBox under xMidYMid meet. */
  const unitsPerPx = useCallback(() => {
    const rect = svgRef.current?.getBoundingClientRect();
    const extent = VIEW_EXTENT / scale;
    if (!rect || rect.width === 0 || rect.height === 0) return extent / 600;
    return extent / Math.min(rect.width, rect.height);
  }, [scale]);

  // One pointer gesture at a time: either panning the background or dragging a
  // node. Kept in a ref so a move event never depends on a re-render landing.
  const gesture = useRef<
    | { kind: 'pan'; lastX: number; lastY: number; moved: number }
    | { kind: 'node'; id: string; lastX: number; lastY: number; moved: number; x: number; y: number }
    /** A deep mark is not draggable: its position is derived from its FILE's
     *  position, so moving it alone would misrepresent containment. A press is
     *  therefore only ever a click. */
    | { kind: 'deep'; id: string; moved: number }
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

  const onDeepPointerDown = (e: ReactPointerEvent<SVGGElement>, id: string) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    gesture.current = { kind: 'deep', id, moved: 0 };
  };

  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const g = gesture.current;
    if (!g) return;
    if (g.kind === 'deep') return;
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
    if (g && g.kind === 'deep') selectDeep(g.id);
  };

  /** Pin / unpin a deep mark. Selection is a TOGGLE so the keyboard can undo it
   *  without hunting for a Clear control. */
  const selectDeep = useCallback(
    (id: string) => {
      onDeepSelect?.(deepSelectedId === id ? null : id);
    },
    [onDeepSelect, deepSelectedId],
  );

  const onCanvasKeyDown = (e: ReactKeyboardEvent<SVGSVGElement>) => {
    if (e.target !== e.currentTarget) return; // node handlers own their own keys
    const step = (VIEW_EXTENT / scale) * 0.08;
    const viewport = viewportAction(e.key);
    if (viewport) dispatch(viewport);
    else if (e.key === 'ArrowLeft') dispatch({ kind: 'pan', dx: -step, dy: 0 });
    else if (e.key === 'ArrowRight') dispatch({ kind: 'pan', dx: step, dy: 0 });
    else if (e.key === 'ArrowUp') dispatch({ kind: 'pan', dx: 0, dy: -step });
    else if (e.key === 'ArrowDown') dispatch({ kind: 'pan', dx: 0, dy: step });
    else return;
    e.preventDefault();
  };

  /** Arrow / Home / End movement over the rendered marks, shared by both layers. */
  const moveRoving = (key: string, id: string): boolean => {
    const navKeys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'];
    if (!navKeys.includes(key) || focusIds.length === 0) return false;
    const idx = focusIds.indexOf(id);
    let next = idx;
    if (key === 'ArrowRight' || key === 'ArrowDown') next = (idx + 1) % focusIds.length;
    else if (key === 'ArrowLeft' || key === 'ArrowUp') {
      next = (idx - 1 + focusIds.length) % focusIds.length;
    } else if (key === 'Home') next = 0;
    else if (key === 'End') next = focusIds.length - 1;
    const nextId = focusIds[next];
    setRovingId(nextId);
    (document.getElementById(domId(domPrefix, nextId)) as SVGGElement | null)?.focus();
    return true;
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
    if (moveRoving(e.key, id)) {
      e.preventDefault();
      e.stopPropagation();
    }
  };

  const onDeepKeyDown = (e: ReactKeyboardEvent<SVGGElement>, id: string) => {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      e.stopPropagation();
      selectDeep(id);
      return;
    }
    const viewport = viewportAction(e.key);
    if (viewport) {
      e.preventDefault();
      e.stopPropagation();
      dispatch(viewport);
      return;
    }
    if (moveRoving(e.key, id)) {
      e.preventDefault();
      e.stopPropagation();
    }
  };

  // --- the hover / focus tooltip --------------------------------------------
  // ONE description, reached by pointer hover OR keyboard focus (the marks fire
  // `onFocus`/`onBlur` into the same setter), so the two are equivalent by
  // construction rather than by promise.
  const tooltip = useMemo<TooltipContent | null>(() => {
    if (!hover) return null;
    if (hover.layer === 'base') {
      const node = index.byId.get(hover.id);
      if (!node) return null;
      return baseTooltip(node, index, state);
    }
    const mark = plan?.nodes.find((n) => n.id === hover.id);
    if (!mark || !deepIndex) return null;
    return deepTooltip(mark, deepIndex, state);
  }, [hover, index, state, plan, deepIndex]);

  const canvasLabel = plan
    ? `Graph canvas, ${plan.level === 'symbol' ? 'symbol' : 'cluster'} detail — ${plan.nodes.length} mark${plan.nodes.length === 1 ? '' : 's'} and ${plan.edges.length} relationship${plan.edges.length === 1 ? '' : 's'} drawn inside ${plan.openFiles} file${plan.openFiles === 1 ? '' : 's'}. Arrow keys pan; Tab reaches the marks.`
    : `Graph canvas — ${visibleIds.length} node${visibleIds.length === 1 ? '' : 's'} and ${edges.length} reference${edges.length === 1 ? '' : 's'} drawn. Arrow keys pan; Tab reaches the nodes.`;

  const nextScale = nextLodScale(scale);
  /**
   * Step exactly onto the next level-of-detail threshold, CENTRED on something
   * real: the current selection, else the nearest visible node to the current
   * centre. Without that step the viewport keeps (0,0), which on this layout is
   * empty space between the clusters — so "Reveal Detail" would zoom in and show
   * nothing, which is the very complaint this slice exists to fix. Deterministic
   * (nearest, ties by id) and built from two pure reducer actions, so it adds no
   * mutation surface of its own.
   */
  const revealDetail = useCallback(() => {
    const target = nextLodScale(state.view.scale);
    if (target === null) return;
    let anchor = state.selectedId ? nodePosition(state.selectedId, state, index) : null;
    if (!anchor) {
      let best: { id: string; d: number } | null = null;
      for (const id of visibleIds) {
        const pos = nodePosition(id, state, index);
        if (!pos) continue;
        const d = Math.hypot(pos.x - state.view.cx, pos.y - state.view.cy);
        if (!best || d < best.d) best = { id, d };
      }
      anchor = best ? (nodePosition(best.id, state, index) ?? null) : null;
    }
    if (anchor) {
      dispatch({ kind: 'pan', dx: anchor.x - state.view.cx, dy: anchor.y - state.view.cy });
    }
    dispatch({ kind: 'zoom', factor: target / state.view.scale });
  }, [dispatch, index, state, visibleIds]);
  const staleness = deepIndex ? deepStaleness(deepIndex.provenance) : null;
  const arrowUnits = screenBoundedUnits(ARROW_UNITS, scale, 2, 12);

  return (
    <div className="graph-explore">
      {/* P36V PR2 slice B — Fit and Reset already existed here as ICON-ONLY
          buttons whose only name was an aria-label. They are now labelled in
          Title Case, so the two viewport controls the redesign wants
          "immediately visible" are legible rather than glyph-only. They are NOT
          duplicated into the primary toolbar: one action, one control, and they
          belong beside the viewport they act on (Browse has no viewport). Zoom
          stays icon-only — a magnifier ± is unambiguous and the row must not
          outgrow the canvas. */}
      <div className="graph-explore-toolbar">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => dispatch({ kind: 'fit' })}
        >
          <Maximize2 size={14} strokeWidth={2} aria-hidden="true" />
          Fit to View
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
        >
          <RotateCcw size={14} strokeWidth={2} aria-hidden="true" />
          Reset View
        </button>
        {/* P36V.1 F — one press lands exactly ON the next level-of-detail
            threshold. Semantic zoom is otherwise six 1.25× presses away from
            being discovered at all. Disabled (not hidden) at the deepest
            level, so the control never disappears under the pointer. */}
        <button
          type="button"
          className="btn btn-secondary"
          disabled={nextScale === null}
          onClick={revealDetail}
        >
          <Network size={14} strokeWidth={2} aria-hidden="true" />
          Reveal Detail
        </button>
        <span className="graph-explore-toolbar-sep" aria-hidden="true" />
        <span className="memory-graph-modenote">zoom {Math.round(scale * 100)}%</span>
        <span className="memory-graph-modenote graph-lod-indicator">
          {levelSummary(level, plan, focusSuspends, deep)}
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
            {plan && (
              <defs>
                {/* `userSpaceOnUse` so the arrowhead is sized in the same
                    screen-bounded units as everything else, instead of tracking
                    the stroke width. */}
                <marker
                  id="graph-deep-arrow"
                  markerUnits="userSpaceOnUse"
                  markerWidth={arrowUnits}
                  markerHeight={arrowUnits}
                  refX={arrowUnits}
                  refY={arrowUnits / 2}
                  orient="auto"
                >
                  <path
                    className="memory-graph-deep-arrowhead"
                    d={`M0,0 L${arrowUnits},${arrowUnits / 2} L0,${arrowUnits} Z`}
                  />
                </marker>
              </defs>
            )}

            {plan ? (
              <>
                {/* File REGIONS — the container each deep mark sits in. Derived
                    from real containment (`source_file`), drawn as inert
                    geometry: not a node, not an edge, never focusable. */}
                <g className="memory-graph-deep-regions" aria-hidden="true">
                  {plan.regions.map((region) => (
                    <g
                      key={region.sourceFile}
                      className="memory-graph-deep-region"
                      data-region={region.sourceFile}
                    >
                      <circle
                        className="memory-graph-deep-region-shape"
                        cx={region.x}
                        cy={region.y}
                        r={region.radius + screenBoundedUnits(4, scale, 1, 10)}
                        vectorEffect="non-scaling-stroke"
                      />
                      <text
                        className="memory-graph-deep-region-label"
                        x={region.x}
                        y={region.y - region.radius - screenBoundedUnits(8, scale, 2, 16)}
                        textAnchor="middle"
                        fontSize={screenBoundedUnits(REGION_LABEL_UNITS, scale, 6, 18)}
                        strokeWidth={screenBoundedUnits(LABEL_HALO_UNITS, scale, 0.5, 4)}
                      >
                        {region.label}
                      </text>
                    </g>
                  ))}
                </g>
                <g className="memory-graph-deep-edges">
                  {plan.edges.map((e) => {
                    const shorten = screenBoundedUnits(MARK_UNITS.symbol + ARROW_UNITS, scale, 3, 22);
                    const dx = e.x2 - e.x1;
                    const dy = e.y2 - e.y1;
                    const len = Math.hypot(dx, dy);
                    const t = len > shorten ? (len - shorten) / len : 1;
                    return (
                      <line
                        key={e.key}
                        className="memory-graph-edge memory-graph-deep-edge"
                        /* PROOF ATTRIBUTES: the payload row this line stands
                           for, how many real rows it folds, and their real
                           relation values. A test reads these back against the
                           fetched payload. */
                        data-edge-index={e.payloadIndex}
                        data-edge-backing={e.backing}
                        data-edge-relations={e.relations.join(',')}
                        data-edge-from={e.from}
                        data-edge-to={e.to}
                        x1={e.x1}
                        y1={e.y1}
                        x2={e.x1 + dx * t}
                        y2={e.y1 + dy * t}
                        vectorEffect="non-scaling-stroke"
                        markerEnd="url(#graph-deep-arrow)"
                      />
                    );
                  })}
                </g>
                <g className="memory-graph-deep-nodes">
                  {plan.nodes.map((mark) => (
                    <DeepMark
                      key={mark.key}
                      mark={mark}
                      index={index}
                      scale={scale}
                      isSelected={deepSelectedId === mark.id}
                      showLabel={
                        deepLabelIds.has(mark.id) ||
                        deepSelectedId === mark.id ||
                        (hover?.layer === 'deep' && hover.id === mark.id)
                      }
                      isRoving={rovingId === mark.id}
                      onPointerDown={(e) => onDeepPointerDown(e, mark.id)}
                      onKeyDown={(e) => onDeepKeyDown(e, mark.id)}
                      onHover={() => setHover({ layer: 'deep', id: mark.id })}
                      onLeave={() =>
                        setHover((h) => (h && h.layer === 'deep' && h.id === mark.id ? null : h))
                      }
                    />
                  ))}
                </g>
              </>
            ) : (
              <>
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
                        /* Keeps the line legible at every zoom instead of
                           thickening with the viewBox. */
                        vectorEffect="non-scaling-stroke"
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
                        scale={scale}
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
                          (hover?.layer === 'base' && hover.id === id) ||
                          connectedToSelected.has(id)
                        }
                        isRoving={rovingId === id}
                        onPointerDown={(e) => onNodePointerDown(e, id)}
                        onKeyDown={(e) => onNodeKeyDown(e, id)}
                        onHover={() => setHover({ layer: 'base', id })}
                        onLeave={() =>
                          setHover((h) => (h && h.layer === 'base' && h.id === id ? null : h))
                        }
                      />
                    );
                  })}
                </g>
              </>
            )}
          </svg>
        )}

        {tooltip && <CanvasTooltip content={tooltip} />}
      </div>

      {/* STRUCTURAL STALENESS — on the surface, not buried in a dialog. The
          symbol layer reads as a map of the current code and it is not one: its
          structure is pinned to the snapshot's `built_at_commit`. Rendered from
          the payload's own provenance fields, and never softened. */}
      {staleness && (
        <p className="graph-deep-staleness" data-staleness-commit={staleness.builtAtCommit ?? ''}>
          {stalenessSentence(staleness)}
          {staleness.servedSetConsistency === 'stale'
            ? ' The served file set has also changed since then, so some files here may no longer be served.'
            : ''}
        </p>
      )}

      {deep.status === 'loading' && (
        <p className="graph-deep-note" role="status">
          Loading the symbol-level structure…
        </p>
      )}
      {deep.status === 'unavailable' && (
        <p className="graph-deep-note advisory">
          Symbol-level detail is unavailable in this deployment
          {deep.reason ? ` — ${describeDeepReason(deep.reason)}` : ''}. The canvas stays on the file
          projection; nothing was aggregated, estimated or stood in for the missing structure.
        </p>
      )}
      {deepIndex && focusSuspends && level !== 'file' && (
        <p className="graph-deep-note advisory">
          A neighbourhood or path focus is active, so the canvas keeps the file projection the focus
          was computed over. Clear the focus to open the symbol-level layers at this zoom.
        </p>
      )}
      {plan && plan.nodes.length === 0 && (
        <p className="graph-deep-note advisory">
          No file with symbol-level structure is inside the viewport at this zoom, so nothing is
          drawn — pan, press Fit to View, or zoom out to the file projection. An empty view here is
          a statement about the viewport, not about the graph.
        </p>
      )}
      {plan && plan.nodes.length > 0 && (
        <p className="graph-deep-note">
          {plan.level === 'symbol'
            ? `${plan.nodes.length} symbol${plan.nodes.length === 1 ? '' : 's'}`
            : `${plan.nodes.length} cluster${plan.nodes.length === 1 ? '' : 's'}`}{' '}
          and {plan.edges.length} relationship{plan.edges.length === 1 ? '' : 's'} drawn inside{' '}
          {plan.openFiles} of {plan.candidateFiles} file
          {plan.candidateFiles === 1 ? '' : 's'} in view
          {plan.nodesTruncated
            ? `, capped from ${plan.nodesConsidered} — pan or zoom to reach the rest`
            : ''}
          {plan.edgesTruncated ? `; ${plan.edgesConsidered} relationships matched the view` : ''}.
          {plan.filesWithoutDeepStructure > 0
            ? ` ${plan.filesWithoutDeepStructure} file${
                plan.filesWithoutDeepStructure === 1 ? ' has' : 's have'
              } no symbol-level structure in this graph at all.`
            : ''}
          {plan.unplacedFiles > 0
            ? ` ${plan.unplacedFiles} file${
                plan.unplacedFiles === 1 ? '' : 's'
              } could not be placed and ${plan.unplacedFiles === 1 ? 'is' : 'are'} not drawn.`
            : ''}
          {deepIndex?.truncated
            ? ' The served payload itself is capped, so the layer is not the whole source graph.'
            : ''}
        </p>
      )}

      {visibleSet.size > 0 && index.renderTruncated && !plan && (
        <p className="memory-graph-truncated-note">
          The canvas draws at most {index.renderIds.length} of {index.counts.total} nodes at once.
          The rest are reachable in Browse and through search — they are not silently discarded.
        </p>
      )}

      <p className="graph-canvas-caption">
        {plan ? (
          <>
            Drag the background to pan. Hover or focus a mark for its detail; Enter pins it. Zoom out
            to return to the file projection. Positions inside a file are a deterministic layout, not
            a claim about the code's structure — only the marks and the arrows come from the graph.
          </>
        ) : (
          <>
            Drag the background to pan, drag a node to move it. Every visible node is labelled once{' '}
            {LABEL_LIMIT} or fewer are shown; above that up to {HUB_LABEL_COUNT} of the
            most-connected nodes stay labelled as landmarks, along with the selected node and its
            connections. Zoom in past {Math.round(LOD_CLUSTER_SCALE * 100)}% to open the clusters
            and symbols inside these files.
            {isolatedVisible > 0 && (
              <>
                {' '}
                {isolatedVisible} of the nodes drawn here have no recorded reference at all and sit
                on the outer rings — the ring is where they are parked, not a relationship between
                them.
              </>
            )}
          </>
        )}
      </p>
    </div>
  );
}

/**
 * The honest, readable form of a backend `reason` token. An unknown token is
 * shown VERBATIM rather than smoothed into a friendly guess about what failed.
 */
function describeDeepReason(reason: string): string {
  if (reason === 'detail_absent') return 'the deployment ships no symbol-level artifact';
  if (reason === 'detail_unreadable') return 'the symbol-level artifact could not be read';
  if (reason === 'detail_unsupported') return 'the artifact uses an unsupported schema version';
  if (reason === 'graph_absent' || reason === 'graph_unreadable') {
    return 'no memory graph is loaded here';
  }
  if (reason === 'request_failed') return 'the request for it did not complete';
  if (reason === 'detail_schema_unrecognised') {
    return 'its column contract was not recognised, so nothing was decoded';
  }
  return reason;
}

/** The level line in the toolbar — what is on screen, and what the next zoom
 *  step would open. Never claims a level the canvas is not actually drawing. */
function levelSummary(
  level: GraphLodLevel,
  plan: DeepRenderPlan | null,
  focusSuspends: boolean,
  deep: DeepLayerState,
): string {
  if (plan) return plan.level === 'symbol' ? 'showing symbols' : 'showing clusters';
  if (level !== 'file' && focusSuspends) return 'showing files (focus active)';
  if (level !== 'file' && deep.status === 'unavailable') return 'showing files (no deeper layer)';
  if (level !== 'file' && deep.status === 'loading') return 'showing files (opening detail…)';
  return 'showing files';
}

// --- tooltips -----------------------------------------------------------------

/** The base (file / concept) description. Human-readable, never a raw dump —
 *  the raw entry stays in the detail pane's "Raw node data". */
function baseTooltip(
  node: ApiMemoryGraphNode,
  index: GraphIndex,
  state: GraphViewState,
): TooltipContent {
  const neighbours = index.adjacency.get(node.id) ?? [];
  const counts = new Map<string, number>();
  for (const nb of neighbours) {
    for (const relation of nb.relations) {
      if (state.relationFilter !== null && !state.relationFilter.includes(relation)) continue;
      counts.set(relation, (counts.get(relation) ?? 0) + 1);
    }
  }
  const summary = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    .map(([relation, count]) => `${relationDisplayLabel(relation)} ${count}`)
    .join(' · ');
  return {
    title: node.label ?? node.id,
    kind: node.kind === 'file' ? 'File' : 'Concept',
    cluster: communityText(node),
    connections: `${neighbours.length} connection${neighbours.length === 1 ? '' : 's'}`,
    source: node.kind === 'file' ? node.id : (node.source_file ?? null),
    relationships: summary === '' ? null : summary,
  };
}

/** The deep (cluster / symbol) description. Same six fields as the base
 *  tooltip, so hover reads the same way at every level. */
function deepTooltip(
  mark: DeepRenderNode,
  deepIndex: DeepIndex,
  state: GraphViewState,
): TooltipContent {
  const summary = deepRelationSummary(deepIndex, mark, state.relationFilter)
    .map((r) => `${relationDisplayLabel(r.relation)} ${r.count}`)
    .join(' · ');
  const kind =
    mark.kind === 'cluster'
      ? `Cluster of ${mark.memberCount} node${mark.memberCount === 1 ? '' : 's'}`
      : `${mark.fileType ? `${mark.fileType} ` : ''}node`;
  return {
    title: mark.label,
    kind,
    cluster:
      mark.communityName ?? (mark.communityId ? `cluster ${mark.communityId}` : null),
    connections: `${mark.connections} recorded relationship${mark.connections === 1 ? '' : 's'}`,
    source: mark.sourceLocation ? `${mark.sourceFile} ${mark.sourceLocation}` : mark.sourceFile,
    relationships: summary === '' ? null : summary,
  };
}

/** The screen-aligned tooltip. An HTML overlay, NOT SVG text: it therefore never
 *  scales with the viewBox and stays readable at every zoom. */
function CanvasTooltip({ content }: { content: TooltipContent }) {
  return (
    <div className="graph-canvas-overlay graph-canvas-hover" data-canvas-tooltip="">
      <span className="graph-canvas-hover-title mono">{content.title}</span>
      <span className="graph-canvas-hover-meta">
        {content.kind}
        {content.cluster ? ` · ${content.cluster}` : ''} · {content.connections}
      </span>
      {content.relationships && (
        <span className="graph-canvas-hover-meta">{content.relationships}</span>
      )}
      {content.source && <span className="graph-canvas-hover-source mono">{content.source}</span>}
    </div>
  );
}

// --- marks --------------------------------------------------------------------

function CanvasNode({
  node,
  x,
  y,
  index,
  scale,
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
  scale: number;
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

  // Screen-bounded geometry: identical to the P36R constants at scale 1, and
  // constant on screen above it.
  const base = node.kind === 'file' ? MARK_UNITS.file : MARK_UNITS.concept;
  const radius = screenBoundedUnits(base * (isSelected ? SELECTED_MARK_FACTOR : 1), scale);
  const fontUnits = screenBoundedUnits(LABEL_UNITS, scale, 6, 18);
  const labelOffset = screenBoundedUnits(MARK_UNITS.concept + 13, scale, 8, 34);

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
        <circle className="memory-graph-node-shape" r={radius} vectorEffect="non-scaling-stroke" />
      ) : (
        <polygon
          className="memory-graph-node-shape"
          points={`0,${-radius} ${radius},0 0,${radius} ${-radius},0`}
          vectorEffect="non-scaling-stroke"
        />
      )}
      {showLabel && (
        <text
          className="memory-graph-node-label"
          y={labelOffset}
          textAnchor="middle"
          fontSize={fontUnits}
          /* The label's background halo. In user units like the font, so it is
             screen-bounded the same way — a stylesheet value grew with the
             viewBox and swallowed the glyphs at deep zoom. */
          strokeWidth={screenBoundedUnits(LABEL_HALO_UNITS, scale, 0.5, 4)}
        >
          {canvasNodeLabel(node)}
        </text>
      )}
    </g>
  );
}

/** One deep mark — a (file, community) cluster, or one symbol. The SAME
 *  focusable `<g role="button">` model as a base node, so the keyboard reaches
 *  the deep layer without a second mechanism. */
function DeepMark({
  mark,
  index,
  scale,
  isSelected,
  showLabel,
  isRoving,
  onPointerDown,
  onKeyDown,
  onHover,
  onLeave,
}: {
  mark: DeepRenderNode;
  index: GraphIndex;
  scale: number;
  isSelected: boolean;
  showLabel: boolean;
  isRoving: boolean;
  onPointerDown: (e: ReactPointerEvent<SVGGElement>) => void;
  onKeyDown: (e: ReactKeyboardEvent<SVGGElement>) => void;
  onHover: () => void;
  onLeave: () => void;
}) {
  const slot = communityColorIndex(mark.communityId, index);
  const clusterName =
    mark.communityName ?? (mark.communityId ? `cluster ${mark.communityId}` : null);
  const ariaLabel = [
    mark.label,
    mark.kind === 'cluster'
      ? `cluster of ${mark.memberCount} node${mark.memberCount === 1 ? '' : 's'}`
      : (mark.fileType ?? 'node'),
    clusterName && mark.kind === 'symbol' ? clusterName : null,
    `in ${mark.sourceFile}${mark.sourceLocation ? ` ${mark.sourceLocation}` : ''}`,
    `${mark.connections} recorded relationship${mark.connections === 1 ? '' : 's'}`,
    isSelected ? 'pinned' : null,
  ]
    .filter(Boolean)
    .join(', ');

  const unitsAtScale1 =
    mark.kind === 'cluster'
      ? Math.min(MARK_UNITS.cluster + Math.log2(mark.memberCount + 1) * 1.6, 18)
      : MARK_UNITS.symbol;
  const radius = screenBoundedUnits(
    unitsAtScale1 * (isSelected ? SELECTED_MARK_FACTOR : 1),
    scale,
  );
  const fontUnits = screenBoundedUnits(LABEL_UNITS, scale, 6, 18);
  const labelOffset = radius + screenBoundedUnits(11, scale, 6, 20);

  const classes = [
    'memory-graph-node',
    'memory-graph-deep-node',
    `memory-graph-deep-${mark.kind}`,
    slot !== null ? `memory-graph-node-c${slot}` : '',
    isSelected ? 'selected' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <g
      id={domId('graph-deep-node', mark.id)}
      role="button"
      tabIndex={isRoving ? 0 : -1}
      aria-label={ariaLabel}
      aria-pressed={isSelected}
      className={classes}
      data-deep-kind={mark.kind}
      data-deep-file={mark.sourceFile}
      data-deep-community={mark.communityId ?? ''}
      transform={`translate(${mark.x} ${mark.y})`}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      onPointerEnter={onHover}
      onPointerLeave={onLeave}
      onFocus={onHover}
      onBlur={onLeave}
    >
      {mark.kind === 'cluster' ? (
        <circle className="memory-graph-node-shape" r={radius} vectorEffect="non-scaling-stroke" />
      ) : (
        <rect
          className="memory-graph-node-shape"
          x={-radius}
          y={-radius}
          width={radius * 2}
          height={radius * 2}
          rx={radius / 2.5}
          vectorEffect="non-scaling-stroke"
        />
      )}
      {showLabel && (
        <text
          className="memory-graph-node-label"
          y={labelOffset}
          textAnchor="middle"
          fontSize={fontUnits}
          /* The label's background halo. In user units like the font, so it is
             screen-bounded the same way — a stylesheet value grew with the
             viewBox and swallowed the glyphs at deep zoom. */
          strokeWidth={screenBoundedUnits(LABEL_HALO_UNITS, scale, 0.5, 4)}
        >
          {deepMarkLabel(mark)}
        </text>
      )}
    </g>
  );
}

/** Longest deep label painted before eliding — the same bound the base canvas
 *  uses (`CANVAS_LABEL_MAX_CHARS`), applied to the deep label. */
const DEEP_LABEL_MAX_CHARS = 26;

export function deepMarkLabel(mark: DeepRenderNode): string {
  const raw = mark.label;
  return raw.length > DEEP_LABEL_MAX_CHARS ? `${raw.slice(0, DEEP_LABEL_MAX_CHARS - 1)}…` : raw;
}

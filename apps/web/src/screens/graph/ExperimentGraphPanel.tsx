import './experiment-graph.css';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  DEFAULT_VIEWPORT_BOX,
  EXPERIMENT_NODE_KINDS,
  EDGE_KIND_LABELS,
  MAX_VISIBLE_NODES,
  NODE_KIND_LABELS,
  applyExperimentGraphAction,
  buildExperimentGraph,
  expandableNodeIds,
  fitExperimentViewport,
  initialExperimentGraphState,
  searchExperimentGraph,
  shortLabel,
  viewBoxFor,
  visibleEdges,
  visibleNodeIds,
  visibleTruncated,
  type ExperimentGraph,
  type ExperimentGraphAction,
  type ExperimentGraphNode,
  type ExperimentGraphViewState,
  type ExperimentNodeKind,
  type ViewportBox,
} from '../../lib/experimentGraph';
import { screenBoundedUnits, type GraphPoint } from '../../lib/graphModel';
import type { ExperimentGraphBundle } from '../../lib/types';

/**
 * The EXPERIMENT-SCOPED graph — a picture of ONE experiment's science, not of
 * the repository.
 *
 * Mounted inside the Review Record screen (`?view=graph`), because that is where
 * a scientist working on a record already is. It reads NOTHING new from the
 * server that the record screens do not already read, and it holds no cache: the
 * graph is rebuilt from the bundle on every render, so a stale experiment graph
 * is structurally impossible rather than merely unlikely.
 *
 * Progressive by construction: the first paint is the anchor and its immediate
 * neighbourhood. Everything else is opened by an explicit expand.
 */

const KIND_SHAPES: Readonly<Record<ExperimentNodeKind, 'circle' | 'square' | 'diamond'>> =
  Object.freeze({
    experiment: 'circle',
    record: 'circle',
    section: 'square',
    field: 'circle',
    block_object: 'circle',
    implicit: 'diamond',
    evidence: 'square',
    source_file: 'square',
    workflow_step: 'circle',
    issue: 'diamond',
    warning: 'diamond',
    linked_record: 'circle',
    rule: 'square',
    confirmation: 'square',
    evidence_class: 'circle',
  });

/**
 * Mark radii in CSS PIXELS — the size each mark renders at, at every zoom and
 * every viewport. `screenBoundedUnits` converts a pixel size into the user
 * units the live scale needs, which is what stops zoom from being pure
 * magnification.
 */
const KIND_RADII: Readonly<Record<ExperimentNodeKind, number>> = Object.freeze({
  experiment: 13,
  record: 12,
  section: 10,
  field: 7.5,
  block_object: 8,
  implicit: 7.5,
  evidence: 6,
  source_file: 7.5,
  workflow_step: 7,
  issue: 7.5,
  warning: 7.5,
  linked_record: 9,
  rule: 6,
  confirmation: 6,
  evidence_class: 6.5,
});

/** Canvas label size, in CSS pixels. */
const LABEL_PX = 11.5;
const LABEL_PX_MIN = 9;
const LABEL_PX_MAX = 20;

/** Kinds offered as visibility toggles, in a stable reading order. */
const FILTERABLE_KINDS: readonly ExperimentNodeKind[] = [
  'section',
  'field',
  'block_object',
  'implicit',
  'evidence',
  'source_file',
  'rule',
  'confirmation',
  'evidence_class',
  'workflow_step',
  'issue',
  'warning',
  'linked_record',
];

function domId(prefix: string, id: string): string {
  return `${prefix}-${id.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
}

const CANVAS_LABEL_MAX_CHARS = 26;

interface LabelBox {
  x1: number;
  x2: number;
  y1: number;
  y2: number;
}

const boxesOverlap = (a: LabelBox, b: LabelBox): boolean =>
  a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;

/**
 * Which nodes keep a visible label.
 *
 * A canvas that draws every label at every zoom does not produce more
 * information, it produces a pile of overlapping glyphs — measured at 1440px
 * with eleven nodes, where the anchor's title and a linked record's id sat on
 * top of each other. So labels are placed greedily in a DETERMINISTIC priority
 * order (selected, then anchor, then the visible order, which is sorted by id)
 * and one that would collide with an already-placed label is dropped. The node
 * itself is never dropped, and the detail pane always names it in full.
 */
function placedLabelIds(
  visible: readonly string[],
  layout: Map<string, GraphPoint>,
  kindOf: (id: string) => ExperimentNodeKind | undefined,
  labelOf: (id: string) => string,
  scale: number,
  selectedId: string | null,
  anchorId: string,
): Set<string> {
  const order = [
    ...(selectedId && visible.includes(selectedId) ? [selectedId] : []),
    ...(visible.includes(anchorId) ? [anchorId] : []),
    ...visible,
  ];
  const seen = new Set<string>();
  const boxes: LabelBox[] = [];
  const placed = new Set<string>();
  const font = screenBoundedUnits(LABEL_PX, scale, LABEL_PX_MIN, LABEL_PX_MAX);
  for (const id of order) {
    if (seen.has(id)) continue;
    seen.add(id);
    const p = layout.get(id);
    const kind = kindOf(id);
    if (!p || !kind) continue;
    const text = shortLabel(labelOf(id), CANVAS_LABEL_MAX_CHARS);
    const halfWidth = (text.length * font * 0.55) / 2;
    const radius = screenBoundedUnits(KIND_RADII[kind], scale);
    const baseline = p.y + radius + font * 1.35;
    const box: LabelBox = {
      x1: p.x - halfWidth,
      x2: p.x + halfWidth,
      y1: baseline - font,
      y2: baseline + font * 0.3,
    };
    if (boxes.some((b) => boxesOverlap(b, box))) continue;
    boxes.push(box);
    placed.add(id);
  }
  return placed;
}

export interface ExperimentGraphPanelProps {
  bundle: ExperimentGraphBundle;
  /** The workspace scope the bundle was READ in (null = ordinary workspace). */
  readInScope: string | null;
  /** The workspace scope the surface is addressing NOW. */
  currentScope: string | null;
}

export function ExperimentGraphPanel({
  bundle,
  readInScope,
  currentScope,
}: ExperimentGraphPanelProps) {
  // Rebuilt from the live bundle on every render — no memo across records, no
  // persisted projection, no index. `useMemo` is keyed on the bundle IDENTITY,
  // so a refetch (which produces a new object) always rebuilds.
  const result = useMemo(
    () => buildExperimentGraph(bundle, { readIn: readInScope, current: currentScope }),
    [bundle, readInScope, currentScope],
  );

  if (!result.ok) {
    return (
      <section className="expgraph" aria-labelledby="expgraph-heading">
        <h2 id="expgraph-heading" className="expgraph-title">
          Experiment Graph
        </h2>
        <p className="expgraph-refusal" role="note">
          {result.message}
        </p>
      </section>
    );
  }

  return <LoadedExperimentGraph graph={result.graph} />;
}

function LoadedExperimentGraph({ graph }: { graph: ExperimentGraph }) {
  const navigate = useNavigate();
  const [state, setState] = useState<ExperimentGraphViewState>(() => {
    const initial = initialExperimentGraphState(graph);
    return { ...initial, view: fitExperimentViewport(visibleNodeIds(initial, graph), graph) };
  });

  /*
   * The canvas's MEASURED size.
   *
   * Deliberately the only place in this feature that reads layout: the model
   * stays free of the DOM, and the one thing the model genuinely cannot know —
   * how many pixels it is being drawn into — is passed in. jsdom reports 0x0
   * (it performs no layout) and has no ResizeObserver, so both are guarded and
   * the default box applies; that is why the vitest suite is unaffected by
   * this and why the responsive behaviour was measured in real Chromium
   * instead.
   */
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [box, setBox] = useState<ViewportBox>(DEFAULT_VIEWPORT_BOX);
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const read = () => {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setBox((prev) =>
          prev.width === rect.width && prev.height === rect.height
            ? prev
            : { width: rect.width, height: rect.height },
        );
      }
    };
    read();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(read);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Frame the first paint against the REAL box once it is known. Runs when the
  // box changes, and only while the reader is still on the untouched initial
  // view — a re-fit after they have panned or expanded would undo their work.
  const framedFor = useRef<string | null>(null);
  useEffect(() => {
    const key = `${box.width}x${box.height}`;
    if (framedFor.current === key) return;
    framedFor.current = key;
    setState((prev) =>
      prev.expanded.length === 1 && prev.expanded[0] === graph.anchorId
        ? { ...prev, view: fitExperimentViewport(visibleNodeIds(prev, graph), graph, box) }
        : prev,
    );
  }, [box, graph]);

  const dispatch = useCallback(
    (action: ExperimentGraphAction) => {
      setState((prev) => applyExperimentGraphAction(prev, action, graph));
    },
    [graph],
  );

  const visible = useMemo(() => visibleNodeIds(state, graph), [state, graph]);
  const edges = useMemo(() => visibleEdges(visible, graph), [visible, graph]);
  const expandable = useMemo(() => expandableNodeIds(state, graph), [state, graph]);
  const truncated = useMemo(() => visibleTruncated(state, graph), [state, graph]);
  const results = useMemo(
    () => searchExperimentGraph(state.search, graph),
    [state.search, graph],
  );

  const selected = state.selectedId ? (graph.byId.get(state.selectedId) ?? null) : null;
  const visibleSet = useMemo(() => new Set(visible), [visible]);
  const labelled = useMemo(
    () =>
      placedLabelIds(
        visible,
        graph.layout,
        (id) => graph.byId.get(id)?.kind,
        (id) => graph.byId.get(id)?.label ?? id,
        state.view.scale,
        state.selectedId,
        graph.anchorId,
      ),
    [visible, graph, state.view.scale, state.selectedId],
  );

  // --- drag to pan ---------------------------------------------------------
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  const onSurfacePointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (e.target !== e.currentTarget) return; // a node handles its own press
    dragRef.current = { x: e.clientX, y: e.clientY };
  };
  const onSurfacePointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const from = dragRef.current;
    if (!from) return;
    const dx = e.clientX - from.x;
    const dy = e.clientY - from.y;
    if (Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
    dragRef.current = { x: e.clientX, y: e.clientY };
    dispatch({ kind: 'pan', dx: -dx / 60, dy: -dy / 60 });
  };
  const endDrag = () => {
    dragRef.current = null;
  };

  // --- keyboard: one roving tab stop over the drawn nodes ------------------
  const rovingId = selected && visibleSet.has(selected.id) ? selected.id : visible[0];

  const onNodeKeyDown = (e: ReactKeyboardEvent<SVGGElement>, id: string) => {
    const index = visible.indexOf(id);
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') nextIndex = (index + 1) % visible.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp')
      nextIndex = (index - 1 + visible.length) % visible.length;
    else if (e.key === 'Home') nextIndex = 0;
    else if (e.key === 'End') nextIndex = visible.length - 1;
    else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      dispatch({ kind: 'expand', nodeId: id });
      return;
    }
    if (nextIndex === null) return;
    e.preventDefault();
    const next = visible[nextIndex];
    dispatch({ kind: 'select', nodeId: next });
    document.getElementById(domId('expgraph-node', next))?.focus();
  };

  const onNodeActivate = (id: string) => {
    // A click selects. A click on the ALREADY-selected node opens it — so the
    // most common gesture (look, then look deeper) needs no second control,
    // while the Expand button in the detail pane remains the explicit path.
    if (state.selectedId === id) dispatch({ kind: 'expand', nodeId: id });
    else dispatch({ kind: 'select', nodeId: id });
  };

  const counts = graph.counts;
  const drawnLabel = `${visible.length} of ${graph.nodes.length} nodes drawn · ${edges.length} of ${graph.edges.length} relationships`;

  return (
    <section className="expgraph" aria-labelledby="expgraph-heading">
      <header className="expgraph-head">
        <h2 id="expgraph-heading" className="expgraph-title">
          Experiment Graph
        </h2>
        <p className="expgraph-intro">
          Everything this experiment is made of and where each part came from — sections,
          fields, the evidence under them, the files that evidence cites, and the workflow
          it sits in. Every line is drawn from a recorded fact; nothing is inferred from
          resemblance.
        </p>
        <p className="expgraph-counts" data-testid="expgraph-counts">
          {drawnLabel}
        </p>
      </header>

      {graph.notes.length > 0 && (
        <ul className="expgraph-notes">
          {graph.notes.map((note) => (
            <li key={note.kind} className="expgraph-note" role="note" data-note={note.kind}>
              {note.text}
            </li>
          ))}
        </ul>
      )}
      {truncated && (
        <p className="expgraph-note" role="note" data-note="visible_cap">
          More than {MAX_VISIBLE_NODES} nodes would be drawn at once, so the view is bounded.
          Collapse something, or hide a category, to see the rest.
        </p>
      )}

      <div className="expgraph-controls">
        <div className="expgraph-search">
          <label className="expgraph-search-label" htmlFor="expgraph-search-input">
            Search within this experiment
          </label>
          <input
            id="expgraph-search-input"
            className="expgraph-search-input"
            type="search"
            value={state.search}
            placeholder="Field, file, rule, value…"
            onChange={(e) => dispatch({ kind: 'search', query: e.target.value })}
          />
          {state.search.trim() !== '' && (
            <div className="expgraph-results" role="listbox" aria-label="Search results">
              {results.length === 0 ? (
                <p className="expgraph-results-empty">
                  Nothing in this experiment matches “{state.search.trim()}”. No near match is
                  offered — a guess would not be an answer.
                </p>
              ) : (
                results.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    role="option"
                    aria-selected={state.selectedId === r.id}
                    className="expgraph-result"
                    onClick={() => dispatch({ kind: 'reveal', nodeId: r.id })}
                  >
                    <span className="expgraph-result-label">{r.label}</span>
                    <span className="expgraph-result-kind">{NODE_KIND_LABELS[r.kind]}</span>
                    <span className="expgraph-result-match">{shortLabel(r.matchedOn, 64)}</span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        <div className="expgraph-buttons" role="group" aria-label="Graph view controls">
          <button type="button" className="expgraph-btn" onClick={() => dispatch({ kind: 'zoom', factor: 1.25 })}>
            Zoom In
          </button>
          <button type="button" className="expgraph-btn" onClick={() => dispatch({ kind: 'zoom', factor: 1 / 1.25 })}>
            Zoom Out
          </button>
          <button
            type="button"
            className="expgraph-btn"
            onClick={() => dispatch({ kind: 'fit', box })}
          >
            Fit View
          </button>
          <button
            type="button"
            className="expgraph-btn"
            onClick={() => dispatch({ kind: 'reset', box })}
          >
            Reset View
          </button>
        </div>

        <fieldset className="expgraph-kinds">
          <legend className="expgraph-kinds-legend">Show</legend>
          <div className="expgraph-kinds-row">
            {FILTERABLE_KINDS.filter((k) => counts[k] > 0).map((k) => {
              const on = !state.hiddenKinds.includes(k);
              return (
                <button
                  key={k}
                  type="button"
                  className={`expgraph-kind-chip${on ? ' on' : ''}`}
                  data-kind={k}
                  aria-pressed={on}
                  onClick={() => dispatch({ kind: 'toggleKind', nodeKind: k })}
                >
                  <span className="expgraph-kind-swatch" data-kind={k} aria-hidden="true" />
                  {NODE_KIND_LABELS[k]}
                  <span className="expgraph-kind-count">{counts[k]}</span>
                </button>
              );
            })}
          </div>
        </fieldset>
      </div>

      <div className="expgraph-body">
        <div className="expgraph-canvas-wrap">
          <svg
            ref={svgRef}
            className="expgraph-canvas"
            viewBox={viewBoxFor(state.view, box)}
            preserveAspectRatio="xMidYMid meet"
            role="application"
            aria-label={`Experiment graph. ${drawnLabel}. Use arrow keys to move between nodes and Enter to open one.`}
            onPointerDown={onSurfacePointerDown}
            onPointerMove={onSurfacePointerMove}
            onPointerUp={endDrag}
            onPointerLeave={endDrag}
          >
            <g className="expgraph-edges">
              {edges.map((e) => {
                const a = graph.layout.get(e.source);
                const b = graph.layout.get(e.target);
                if (!a || !b) return null;
                const touchesSelected =
                  state.selectedId === e.source || state.selectedId === e.target;
                return (
                  <line
                    key={`${e.kind}|${e.source}|${e.target}`}
                    className={`expgraph-edge${touchesSelected ? ' active' : ''}`}
                    data-edge-kind={e.kind}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    vectorEffect="non-scaling-stroke"
                  >
                    <title>{`${EDGE_KIND_LABELS[e.kind]} — ${e.why}`}</title>
                  </line>
                );
              })}
            </g>
            <g className="expgraph-nodes">
              {visible.map((id) => {
                const node = graph.byId.get(id);
                const p = graph.layout.get(id);
                if (!node || !p) return null;
                return (
                  <CanvasNode
                    key={id}
                    node={node}
                    x={p.x}
                    y={p.y}
                    scale={state.view.scale}
                    isAnchor={id === graph.anchorId}
                    isSelected={state.selectedId === id}
                    isExpanded={state.expanded.includes(id)}
                    canExpand={expandable.has(id)}
                    showLabel={labelled.has(id)}
                    isRoving={rovingId === id}
                    onActivate={() => onNodeActivate(id)}
                    onKeyDown={(e) => onNodeKeyDown(e, id)}
                  />
                );
              })}
            </g>
          </svg>
        </div>

        <aside className="expgraph-detail" aria-label="Selected node">
          {selected ? (
            <NodeDetail
              node={selected}
              graph={graph}
              expanded={state.expanded.includes(selected.id)}
              isAnchor={selected.id === graph.anchorId}
              visibleSet={visibleSet}
              onSelect={(id) => dispatch({ kind: 'select', nodeId: id })}
              onReveal={(id) => dispatch({ kind: 'reveal', nodeId: id })}
              onExpand={(id) => dispatch({ kind: 'expand', nodeId: id })}
              onCollapse={(id) => dispatch({ kind: 'collapse', nodeId: id })}
              onJump={(to) => navigate(to)}
            />
          ) : (
            <p className="expgraph-detail-empty">
              Select a node to see what it is, where it came from, and why each line touching
              it exists.
            </p>
          )}
        </aside>
      </div>
    </section>
  );
}

function CanvasNode({
  node,
  x,
  y,
  scale,
  isAnchor,
  isSelected,
  isExpanded,
  canExpand,
  showLabel,
  isRoving,
  onActivate,
  onKeyDown,
}: {
  node: ExperimentGraphNode;
  x: number;
  y: number;
  scale: number;
  isAnchor: boolean;
  isSelected: boolean;
  isExpanded: boolean;
  canExpand: boolean;
  showLabel: boolean;
  isRoving: boolean;
  onActivate: () => void;
  onKeyDown: (e: ReactKeyboardEvent<SVGGElement>) => void;
}) {
  // Screen-bounded geometry, borrowed from the memory canvas rather than
  // reinvented: the viewBox scales with zoom, so a fixed user-unit radius grows
  // with it and zooming in reveals nothing — the same marks, larger. Bounding
  // the mark in SCREEN units is what makes zoom mean "see more", not "see
  // bigger".
  const r = screenBoundedUnits(KIND_RADII[node.kind], scale);
  const font = screenBoundedUnits(LABEL_PX, scale, LABEL_PX_MIN, LABEL_PX_MAX);
  const shape = KIND_SHAPES[node.kind];
  const classes = [
    'expgraph-node',
    isAnchor ? 'anchor' : '',
    isSelected ? 'selected' : '',
    isExpanded ? 'expanded' : '',
    node.fromStaleArtifact ? 'stale' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const aria = [
    node.label,
    NODE_KIND_LABELS[node.kind],
    isSelected ? 'selected' : '',
    canExpand ? 'has more to show' : '',
    node.fromStaleArtifact ? 'read from a stale exported artifact' : '',
  ]
    .filter(Boolean)
    .join(', ');

  return (
    <g
      id={domId('expgraph-node', node.id)}
      className={classes}
      data-kind={node.kind}
      data-node-id={node.id}
      role="button"
      tabIndex={isRoving ? 0 : -1}
      aria-label={aria}
      aria-pressed={isSelected}
      transform={`translate(${x} ${y})`}
      onPointerDown={(e) => {
        e.stopPropagation();
        onActivate();
      }}
      onKeyDown={onKeyDown}
    >
      {shape === 'circle' && (
        <circle className="expgraph-node-shape" r={r} vectorEffect="non-scaling-stroke" />
      )}
      {shape === 'square' && (
        <rect
          className="expgraph-node-shape"
          x={-r}
          y={-r}
          width={r * 2}
          height={r * 2}
          rx={3}
          vectorEffect="non-scaling-stroke"
        />
      )}
      {shape === 'diamond' && (
        <polygon
          className="expgraph-node-shape"
          points={`0,${-r} ${r},0 0,${r} ${-r},0`}
          vectorEffect="non-scaling-stroke"
        />
      )}
      {canExpand && (
        <circle
          className="expgraph-node-more"
          r={Math.max(2.4, r * 0.22)}
          cx={r + r * 0.35}
          cy={-r - r * 0.12}
          aria-hidden="true"
        />
      )}
      {showLabel && (
        <text
          className="expgraph-node-label"
          y={r + font * 1.35}
          fontSize={font}
          strokeWidth={Math.max(1, font * 0.27)}
          textAnchor="middle"
        >
          {shortLabel(node.label, CANVAS_LABEL_MAX_CHARS)}
        </text>
      )}
    </g>
  );
}

function NodeDetail({
  node,
  graph,
  expanded,
  isAnchor,
  visibleSet,
  onSelect,
  onReveal,
  onExpand,
  onCollapse,
  onJump,
}: {
  node: ExperimentGraphNode;
  graph: ExperimentGraph;
  expanded: boolean;
  isAnchor: boolean;
  visibleSet: Set<string>;
  onSelect: (id: string) => void;
  onReveal: (id: string) => void;
  onExpand: (id: string) => void;
  onCollapse: (id: string) => void;
  onJump: (to: string) => void;
}) {
  const neighbours = graph.adjacency.get(node.id) ?? [];

  return (
    <div className="expgraph-detail-body">
      <p className="expgraph-detail-kind" data-kind={node.kind}>
        <span className="expgraph-kind-swatch" data-kind={node.kind} aria-hidden="true" />
        {NODE_KIND_LABELS[node.kind]}
      </p>
      <h3 className="expgraph-detail-title">{node.label}</h3>

      {node.fromStaleArtifact && (
        <p className="expgraph-detail-stale" role="note">
          Read from an exported artifact whose state is <strong>stale</strong> — the record
          changed after export, so this does not describe the current draft.
        </p>
      )}

      <p className="expgraph-detail-producer">
        <span className="expgraph-detail-producer-term">Where this came from</span>
        <span className="expgraph-detail-producer-value">{node.producer}</span>
      </p>

      {node.detail.length > 0 && (
        <dl className="expgraph-detail-list">
          {node.detail.map((line, i) => (
            <div className="expgraph-detail-row" key={`${line.term}-${i}`}>
              <dt>{line.term}</dt>
              <dd>{line.value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="expgraph-detail-actions">
        {expanded ? (
          <button
            type="button"
            className="expgraph-btn"
            disabled={isAnchor}
            onClick={() => onCollapse(node.id)}
          >
            {isAnchor ? 'Anchor — always open' : 'Collapse'}
          </button>
        ) : (
          <button type="button" className="expgraph-btn" onClick={() => onExpand(node.id)}>
            Expand
          </button>
        )}
        {node.jump && (
          <button
            type="button"
            className="expgraph-btn primary"
            onClick={() => onJump(node.jump!.to)}
          >
            {node.jump.label}
          </button>
        )}
      </div>

      <h4 className="expgraph-detail-subhead">
        Connections <span className="expgraph-detail-count">{neighbours.length}</span>
      </h4>
      {neighbours.length === 0 ? (
        <p className="expgraph-detail-empty">This node has no recorded relationships.</p>
      ) : (
        <ul className="expgraph-conn-list">
          {neighbours.map((adj, i) => {
            const other = graph.byId.get(adj.id);
            if (!other) return null;
            const drawn = visibleSet.has(adj.id);
            return (
              <li className="expgraph-conn" key={`${adj.edge.kind}-${adj.id}-${i}`}>
                <p className="expgraph-conn-head">
                  <span className="expgraph-conn-rel">
                    {adj.incoming ? '←' : '→'} {EDGE_KIND_LABELS[adj.edge.kind]}
                  </span>
                  {adj.edge.label && (
                    <span className="expgraph-conn-tag">{adj.edge.label}</span>
                  )}
                </p>
                <button
                  type="button"
                  className="expgraph-conn-target"
                  onClick={() => (drawn ? onSelect(adj.id) : onReveal(adj.id))}
                >
                  {other.label}
                  <span className="expgraph-conn-kind">{NODE_KIND_LABELS[other.kind]}</span>
                </button>
                <p className="expgraph-conn-why">{adj.edge.why}</p>
              </li>
            );
          })}
        </ul>
      )}

      <details className="expgraph-legend">
        <summary>What this graph will not draw</summary>
        <p>
          No relationship is inferred from resemblance. Two records that share a formula, a
          sample id, a beamline, a proposal or a contributor name are <strong>not</strong>{' '}
          joined here — a matching string is not an entity, and a link is an author’s
          assertion, read only from the record’s own <code>links[]</code>. No similarity, no
          timestamp-derived causality, and no scientific interpretation is drawn: nothing in
          this application computes any of them.
        </p>
        <p className="expgraph-legend-kinds">
          {EXPERIMENT_NODE_KINDS.map((k) => NODE_KIND_LABELS[k]).join(' · ')}
        </p>
      </details>
    </div>
  );
}

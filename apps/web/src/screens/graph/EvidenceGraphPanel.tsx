import './evidence-graph.css';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import {
  DEFAULT_VIEWPORT_BOX,
  EDGE_KIND_LABELS,
  EVIDENCE_GRAPH_DISCLOSURE,
  EVIDENCE_NODE_KINDS,
  MAX_VISIBLE_EVIDENCE_NODES,
  NODE_KIND_LABELS,
  ancestorsOf,
  applyEvidenceGraphAction,
  buildEvidenceGraph,
  checksFromStore,
  crossLinksOf,
  emptyRunCheckStore,
  evidenceGraphFreshnessKey,
  evidenceTreeRows,
  fitEvidenceViewport,
  initialEvidenceGraphState,
  nodeIds,
  readRunCheck,
  rekeyRunCheckStore,
  searchEvidenceGraph,
  shortLabel,
  viewBoxFor,
  visibleEvidenceEdges,
  visibleEvidenceNodeIds,
  visibleEvidenceTruncated,
  writeRunCheck,
  type EvidenceGraph,
  type EvidenceGraphAction,
  type EvidenceGraphNode,
  type EvidenceGraphRunsMeta,
  type EvidenceGraphViewState,
  type EvidenceNodeKind,
  type RunCheckStore,
  type ViewportBox,
} from '../../lib/evidenceGraph';
import { screenBoundedUnits, type GraphPoint } from '../../lib/graphModel';
import type {
  ApiEvidenceClassification,
  ApiEvidenceEntry,
  ApiExperimentDetail,
  ApiRunCheckResponse,
  ApiRunView,
} from '../../lib/types';

/**
 * The EVIDENCE GRAPH — one experiment, shaped around its RUNS, for the
 * scientist who ran them.
 *
 * It answers the five questions the Evidence List cannot answer in one look:
 * what belongs to Run 2, what supports this measurement, which asset is
 * referenced, where did this descriptor come from, and which validation issue
 * belongs to which run.
 *
 * ── What this component is NOT ──────────────────────────────────────────────
 *
 * It is not the Project Memory graph. Nothing here reads `graphify-out/`, the
 * committed memory snapshot, or any repository artifact; no file path, module
 * name or codebase concept can appear, because the model it renders
 * (`lib/evidenceGraph.ts`) never reads one. The only "file" it ever names is a
 * source file the scientist's OWN evidence cites.
 *
 * ── Accessibility, stated rather than implied ───────────────────────────────
 *
 * There are TWO representations of one model, and only ONE of them is in the
 * accessibility tree:
 *
 *   · the SVG canvas is `aria-hidden` and takes no tab stop. It is a picture.
 *     A second focusable representation of the same nodes would give a keyboard
 *     user two parallel tab sequences through identical content.
 *   · the STRUCTURE TREE (`role="tree"`) is the real control: every drawn node
 *     is a `treeitem` with an accessible name, its kind, `aria-level`,
 *     `aria-expanded` where it has children, and a roving tab stop with the
 *     WAI-ARIA tree keys (Up/Down, Right to open or descend, Left to close or
 *     ascend, Home/End, Enter to open).
 *
 * Relationships that are NOT containment — `conflicts_with`, and a run value's
 * `derived_from` link up to the experiment — cannot be edges of a tree, so they
 * are reachable in the details pane as buttons that move the selection. That is
 * the whole non-visual equivalent: every node and every edge is reachable
 * without seeing the layout.
 *
 * ── Freshness ───────────────────────────────────────────────────────────────
 *
 * The graph is rebuilt from props on every render — no projection, no index, no
 * memo across records. The ONE cache (a run's validation check, which costs a
 * request) is keyed on {@link evidenceGraphFreshnessKey} and re-keyed DURING
 * RENDER, so a moved version token evicts before the builder can be handed a
 * stale verdict rather than one frame after.
 */

const KIND_SHAPES: Readonly<Record<EvidenceNodeKind, 'circle' | 'square' | 'diamond'>> =
  Object.freeze({
    experiment: 'circle',
    run: 'circle',
    sample: 'circle',
    context: 'square',
    measurement: 'circle',
    asset: 'square',
    descriptor: 'diamond',
    evidence_entry: 'square',
    evidence_source: 'square',
    validation_finding: 'diamond',
  });

/** Mark radii in CSS PIXELS — see `screenBoundedUnits`: zoom means "see more". */
const KIND_RADII: Readonly<Record<EvidenceNodeKind, number>> = Object.freeze({
  experiment: 14,
  run: 12,
  sample: 9,
  context: 8.5,
  measurement: 9,
  asset: 8.5,
  descriptor: 8.5,
  evidence_entry: 6.5,
  evidence_source: 6,
  validation_finding: 7.5,
});

const LABEL_PX = 11.5;
const LABEL_PX_MIN = 9;
const LABEL_PX_MAX = 20;
const CANVAS_LABEL_MAX_CHARS = 26;

/** Kinds offered as visibility toggles, in a stable reading order. Experiment and
 *  Run are absent on purpose: filtering away the spine is not a filter. */
const FILTERABLE_KINDS: readonly EvidenceNodeKind[] = [
  'sample',
  'context',
  'measurement',
  'asset',
  'descriptor',
  'evidence_entry',
  'evidence_source',
  'validation_finding',
];

function domId(prefix: string, id: string): string {
  return `${prefix}-${id.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
}

interface LabelBox {
  x1: number;
  x2: number;
  y1: number;
  y2: number;
}

const boxesOverlap = (a: LabelBox, b: LabelBox): boolean =>
  a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;

/**
 * Which nodes keep a visible canvas label — greedy, in a deterministic priority
 * order, dropping any label that would collide with one already placed. The node
 * is never dropped, and the tree always names it in full.
 */
function placedLabelIds(
  visible: readonly string[],
  layout: Map<string, GraphPoint>,
  kindOf: (id: string) => EvidenceNodeKind | undefined,
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

export interface EvidenceGraphPanelProps {
  experimentId: string;
  detail: ApiExperimentDetail;
  evidence: ApiEvidenceEntry[];
  classification: ApiEvidenceClassification;
  /** The runs actually LOADED — a bounded page, never "all runs". */
  runs: ApiRunView[];
  runsMeta: EvidenceGraphRunsMeta;
  /** The workspace scope the data was READ in (null = ordinary workspace). */
  readInScope: string | null;
  /** The workspace scope the surface is addressing NOW. */
  currentScope: string | null;
  /** The `?run=` focus, or null for the whole experiment. */
  focusRunId: string | null;
  onFocusRun: (runId: string | null) => void;
  /**
   * Fetch ONE run's validation check.
   *
   * Injected rather than called here so the panel performs no I/O of its own —
   * which is what lets a test assert exactly how many checks an expansion
   * triggers, and which run each one was for.
   */
  onRequestRunCheck: (runId: string) => Promise<ApiRunCheckResponse>;
}

export function EvidenceGraphPanel({
  experimentId,
  detail,
  evidence,
  classification,
  runs,
  runsMeta,
  readInScope,
  currentScope,
  focusRunId,
  onFocusRun,
  onRequestRunCheck,
}: EvidenceGraphPanelProps) {
  const freshnessKey = evidenceGraphFreshnessKey(currentScope, detail.version);

  // The one cache on this surface. Re-keyed DURING RENDER (`rekeyRunCheckStore`
  // returns the same object when the key matches, a fresh empty one when it does
  // not), so a moved version token can never be served to the builder — not even
  // for the single frame an effect-based eviction would leave open.
  const [rawStore, setRawStore] = useState<RunCheckStore>(() =>
    emptyRunCheckStore(freshnessKey),
  );
  const store = rekeyRunCheckStore(rawStore, freshnessKey);

  const checks = useMemo(() => checksFromStore(store, runs), [store, runs]);

  const result = useMemo(
    () =>
      buildEvidenceGraph(
        { detail, runs, runsMeta, evidence, classification, checks, focusRunId },
        { readIn: readInScope, current: currentScope },
      ),
    [
      detail,
      runs,
      runsMeta,
      evidence,
      classification,
      checks,
      focusRunId,
      readInScope,
      currentScope,
    ],
  );

  const recordCheck = useCallback(
    (runId: string, runVersion: string, check: ApiRunCheckResponse) => {
      setRawStore((prev) =>
        writeRunCheck(rekeyRunCheckStore(prev, freshnessKey), runId, runVersion, check),
      );
    },
    [freshnessKey],
  );

  if (!result.ok) {
    return (
      <section className="evgraph" aria-labelledby="evgraph-heading">
        <h2 id="evgraph-heading" className="evgraph-title">
          Evidence Graph
        </h2>
        <p className="evgraph-refusal" role="note">
          {result.message}
        </p>
      </section>
    );
  }

  return (
    <LoadedEvidenceGraph
      key={freshnessKey}
      experimentId={experimentId}
      graph={result.graph}
      runs={runs}
      store={store}
      focusRunId={focusRunId}
      onFocusRun={onFocusRun}
      onRequestRunCheck={onRequestRunCheck}
      onCheckLoaded={recordCheck}
    />
  );
}

function LoadedEvidenceGraph({
  experimentId,
  graph,
  runs,
  store,
  focusRunId,
  onFocusRun,
  onRequestRunCheck,
  onCheckLoaded,
}: {
  experimentId: string;
  graph: EvidenceGraph;
  runs: ApiRunView[];
  store: RunCheckStore;
  focusRunId: string | null;
  onFocusRun: (runId: string | null) => void;
  onRequestRunCheck: (runId: string) => Promise<ApiRunCheckResponse>;
  onCheckLoaded: (runId: string, runVersion: string, check: ApiRunCheckResponse) => void;
}) {
  const [state, setState] = useState<EvidenceGraphViewState>(() => {
    const initial = initialEvidenceGraphState(graph);
    return {
      ...initial,
      view: fitEvidenceViewport(visibleEvidenceNodeIds(initial, graph), graph),
    };
  });

  /** What the live region says. Expansion and selection both announce. */
  const [announcement, setAnnouncement] = useState('');
  /** Runs whose check is in flight, and runs whose check failed. */
  const [pendingChecks, setPendingChecks] = useState<readonly string[]>([]);
  const [checkErrors, setCheckErrors] = useState<Readonly<Record<string, string>>>({});

  /*
   * The canvas's MEASURED size — the only place this feature reads layout. jsdom
   * performs no layout and has no ResizeObserver, so both are guarded and the
   * default box applies there.
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

  // Frame the first paint against the REAL box once known — only while the
  // reader is still on the untouched initial view.
  const framedFor = useRef<string | null>(null);
  useEffect(() => {
    const key = `${box.width}x${box.height}`;
    if (framedFor.current === key) return;
    framedFor.current = key;
    setState((prev) =>
      prev.expanded.length === 1 && prev.expanded[0] === graph.anchorId
        ? { ...prev, view: fitEvidenceViewport(visibleEvidenceNodeIds(prev, graph), graph, box) }
        : prev,
    );
  }, [box, graph]);

  /**
   * Fetch the check for ONE run, and only when a reader actually opened it.
   *
   * This is the whole of "progressive expansion does not fetch everything":
   * opening a run asks for that run's findings and nobody else's, a run already
   * cached at its CURRENT version asks for nothing, and a run that is merely
   * drawn (collapsed, in the run list under the experiment) asks for nothing.
   */
  const requestCheckFor = useCallback(
    (nodeId: string) => {
      const node = graph.byId.get(nodeId);
      if (!node || node.kind !== 'run' || !node.runId) return;
      const run = runs.find((r) => r.id === node.runId);
      if (!run) return;
      if (readRunCheck(store, run.id, run.version)) return;
      setPendingChecks((prev) => (prev.includes(run.id) ? prev : [...prev, run.id]));
      void onRequestRunCheck(run.id)
        .then((check) => {
          onCheckLoaded(run.id, run.version, check);
          setCheckErrors((prev) => {
            if (!(run.id in prev)) return prev;
            const next = { ...prev };
            delete next[run.id];
            return next;
          });
        })
        .catch((err: unknown) => {
          // A failed check is SAID, never rendered as "no findings" — an absent
          // verdict and a clean verdict are different facts.
          setCheckErrors((prev) => ({
            ...prev,
            [run.id]: err instanceof Error ? err.message : 'the check could not be read',
          }));
        })
        .finally(() => {
          setPendingChecks((prev) => prev.filter((id) => id !== run.id));
        });
    },
    [graph, runs, store, onRequestRunCheck, onCheckLoaded],
  );

  const dispatch = useCallback(
    (action: EvidenceGraphAction) => {
      setState((prev) => {
        const next = applyEvidenceGraphAction(prev, action, graph);
        const label = (id: string) => graph.byId.get(id)?.label ?? id;

        if (action.kind === 'expand' || action.kind === 'toggle') {
          const opened =
            !prev.expanded.includes(action.nodeId) && next.expanded.includes(action.nodeId);
          if (opened) {
            const n = (graph.childrenOf.get(action.nodeId) ?? []).length;
            setAnnouncement(
              `${label(action.nodeId)} expanded. ${n} ${n === 1 ? 'item' : 'items'} revealed.`,
            );
          } else if (prev.expanded.includes(action.nodeId)) {
            setAnnouncement(`${label(action.nodeId)} collapsed.`);
          }
        } else if (action.kind === 'collapse' && prev.expanded.includes(action.nodeId)) {
          setAnnouncement(`${label(action.nodeId)} collapsed.`);
        } else if (action.kind === 'reveal') {
          setAnnouncement(`${label(action.nodeId)} revealed and selected.`);
        } else if (action.kind === 'select' && action.nodeId && action.nodeId !== prev.selectedId) {
          const node = graph.byId.get(action.nodeId);
          if (node) setAnnouncement(`${node.label} selected. ${NODE_KIND_LABELS[node.kind]}.`);
        }
        return next;
      });

      // Opening a run is what asks for its findings.
      if (action.kind === 'expand' || action.kind === 'toggle' || action.kind === 'reveal') {
        requestCheckFor(action.nodeId);
      }
    },
    [graph, requestCheckFor],
  );

  const visible = useMemo(() => visibleEvidenceNodeIds(state, graph), [state, graph]);
  const rows = useMemo(() => evidenceTreeRows(state, graph), [state, graph]);
  const edges = useMemo(() => visibleEvidenceEdges(visible, graph), [visible, graph]);
  const truncated = useMemo(() => visibleEvidenceTruncated(state, graph), [state, graph]);
  const results = useMemo(() => searchEvidenceGraph(state.search, graph), [state.search, graph]);

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

  // --- drag to pan (pointer only; the tree is the keyboard interface) -------
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  const onSurfacePointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (e.target !== e.currentTarget) return;
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

  // --- the tree: one roving tab stop, WAI-ARIA tree keys --------------------
  const rowIds = useMemo(() => rows.map((r) => r.id), [rows]);
  const rovingId =
    state.selectedId && rowIds.includes(state.selectedId) ? state.selectedId : rowIds[0];

  const focusRow = (id: string) => {
    dispatch({ kind: 'select', nodeId: id });
    window.requestAnimationFrame(() => {
      document.getElementById(domId('evgraph-row', id))?.focus();
    });
  };

  const onRowKeyDown = (e: ReactKeyboardEvent<HTMLLIElement>, id: string) => {
    const index = rowIds.indexOf(id);
    const node = graph.byId.get(id);
    const children = graph.childrenOf.get(id) ?? [];
    const isOpen = state.expanded.includes(id);

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (index < rowIds.length - 1) focusRow(rowIds[index + 1]);
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (index > 0) focusRow(rowIds[index - 1]);
      return;
    }
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      if (children.length === 0) return;
      if (!isOpen) dispatch({ kind: 'expand', nodeId: id });
      else focusRow(children[0]);
      return;
    }
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      if (isOpen && id !== graph.anchorId) dispatch({ kind: 'collapse', nodeId: id });
      else if (node?.parentId && rowIds.includes(node.parentId)) focusRow(node.parentId);
      return;
    }
    if (e.key === 'Home') {
      e.preventDefault();
      focusRow(rowIds[0]);
      return;
    }
    if (e.key === 'End') {
      e.preventDefault();
      focusRow(rowIds[rowIds.length - 1]);
      return;
    }
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (children.length > 0) dispatch({ kind: 'toggle', nodeId: id });
      else dispatch({ kind: 'select', nodeId: id });
    }
  };

  const onNodeActivate = (id: string) => {
    if (state.selectedId === id) dispatch({ kind: 'expand', nodeId: id });
    else dispatch({ kind: 'select', nodeId: id });
  };

  const counts = graph.counts;
  const drawnLabel = `${visible.length} of ${graph.nodes.length} nodes drawn · ${edges.length} of ${graph.edges.length} relationships`;

  const anchorNode = graph.byId.get(graph.anchorId);
  const breadcrumb =
    graph.anchorId === graph.rootId ? [] : ancestorsOf(graph.anchorId, graph).slice(0, -1);

  const selectedRun =
    selected?.runId ? runs.find((r) => r.id === selected.runId) : undefined;
  const selectedRunNodeId = selected?.runId ? nodeIds.run(selected.runId) : null;
  const selectedRunPending = selected?.runId
    ? pendingChecks.includes(selected.runId)
    : false;
  const selectedRunError = selected?.runId ? checkErrors[selected.runId] : undefined;
  const selectedRunChecked =
    selectedRun ? readRunCheck(store, selectedRun.id, selectedRun.version) !== null : false;

  return (
    <section className="evgraph" aria-labelledby="evgraph-heading">
      <header className="evgraph-head">
        <h2 id="evgraph-heading" className="evgraph-title">
          Evidence Graph
        </h2>
        <p className="evgraph-intro">
          This experiment and its runs, with the sample, context, measurement, assets and
          descriptors each run actually carries — and the evidence and validation findings
          recorded under them.
        </p>
        {/* The disclosure. Rendered from the exported constant so a paraphrase
            cannot satisfy the test that asserts it is on screen. */}
        <p className="evgraph-disclosure" role="note" data-testid="evgraph-disclosure">
          {EVIDENCE_GRAPH_DISCLOSURE}
        </p>
        <p className="evgraph-counts" data-testid="evgraph-counts">
          {drawnLabel}
        </p>
        <p className="evgraph-freshness" data-testid="evgraph-freshness">
          Built from this record at version <code>{graph.freshnessKey.split('|').pop()}</code>.
          Nothing here is cached across a version change.
        </p>
      </header>

      {graph.notes.length > 0 && (
        <ul className="evgraph-notes">
          {graph.notes.map((note) => (
            <li key={note.kind} className="evgraph-note" role="note" data-note={note.kind}>
              {note.text}
            </li>
          ))}
        </ul>
      )}
      {truncated && (
        <p className="evgraph-note" role="note" data-note="visible_cap">
          More than {MAX_VISIBLE_EVIDENCE_NODES} nodes would be drawn at once, so the view is
          bounded. Collapse something, or hide a category, to see the rest.
        </p>
      )}

      <div className="evgraph-controls">
        <div className="evgraph-search">
          <label className="evgraph-search-label" htmlFor="evgraph-search-input">
            Search this experiment
          </label>
          <input
            id="evgraph-search-input"
            className="evgraph-search-input"
            type="search"
            value={state.search}
            placeholder="Run, sample, file, finding, value…"
            onChange={(e) => dispatch({ kind: 'search', query: e.target.value })}
          />
          {state.search.trim() !== '' && (
            <div className="evgraph-results" role="listbox" aria-label="Search results">
              {results.length === 0 ? (
                <p className="evgraph-results-empty">
                  Nothing loaded here matches “{state.search.trim()}”. No near match is
                  offered — a guess would not be an answer.
                </p>
              ) : (
                results.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    role="option"
                    aria-selected={state.selectedId === r.id}
                    className="evgraph-result"
                    onClick={() => dispatch({ kind: 'reveal', nodeId: r.id })}
                  >
                    <span className="evgraph-result-label">{r.label}</span>
                    <span className="evgraph-result-kind">{NODE_KIND_LABELS[r.kind]}</span>
                    {r.runLabel && <span className="evgraph-result-run">in {r.runLabel}</span>}
                    <span className="evgraph-result-match">{shortLabel(r.matchedOn, 64)}</span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        <div className="evgraph-focus">
          <label className="evgraph-focus-label" htmlFor="evgraph-focus-select">
            Focus on run
          </label>
          <select
            id="evgraph-focus-select"
            className="evgraph-focus-select"
            value={focusRunId ?? ''}
            onChange={(e) => onFocusRun(e.target.value === '' ? null : e.target.value)}
          >
            <option value="">Whole experiment</option>
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.label || `Run ${run.ordinal}`}
              </option>
            ))}
          </select>
        </div>

        <div className="evgraph-buttons" role="group" aria-label="Graph view controls">
          <button
            type="button"
            className="evgraph-btn"
            onClick={() => dispatch({ kind: 'zoom', factor: 1.25 })}
          >
            Zoom In
          </button>
          <button
            type="button"
            className="evgraph-btn"
            onClick={() => dispatch({ kind: 'zoom', factor: 1 / 1.25 })}
          >
            Zoom Out
          </button>
          <button type="button" className="evgraph-btn" onClick={() => dispatch({ kind: 'fit', box })}>
            Fit to View
          </button>
          <button
            type="button"
            className="evgraph-btn"
            onClick={() => dispatch({ kind: 'reset', box })}
          >
            Reset
          </button>
        </div>

        <fieldset className="evgraph-kinds">
          <legend className="evgraph-kinds-legend">Show</legend>
          <div className="evgraph-kinds-row">
            {FILTERABLE_KINDS.filter((k) => counts[k] > 0).map((k) => {
              const on = !state.hiddenKinds.includes(k);
              return (
                <button
                  key={k}
                  type="button"
                  className={`evgraph-kind-chip${on ? ' on' : ''}`}
                  data-kind={k}
                  aria-pressed={on}
                  onClick={() => dispatch({ kind: 'toggleKind', nodeKind: k })}
                >
                  <span className="evgraph-kind-swatch" data-kind={k} aria-hidden="true" />
                  {NODE_KIND_LABELS[k]}
                  <span className="evgraph-kind-count">{counts[k]}</span>
                </button>
              );
            })}
          </div>
        </fieldset>
      </div>

      {/* Expansion and selection both announce here. Polite, so it never
          interrupts a reader mid-sentence. */}
      <p className="sr-only" role="status" aria-live="polite" data-testid="evgraph-live">
        {announcement}
      </p>

      <div className="evgraph-body">
        <div className="evgraph-structure">
          <h3 className="evgraph-structure-title" id="evgraph-tree-label">
            Structure
          </h3>
          {breadcrumb.length > 0 && (
            <p className="evgraph-breadcrumb">
              Focused on <strong>{anchorNode?.label}</strong>, inside{' '}
              {breadcrumb.map((id, i) => (
                <span key={id}>
                  {i > 0 && ' › '}
                  <button
                    type="button"
                    className="evgraph-breadcrumb-link"
                    onClick={() => onFocusRun(null)}
                  >
                    {graph.byId.get(id)?.label ?? id}
                  </button>
                </span>
              ))}
              .
            </p>
          )}
          <p className="evgraph-structure-help">
            The same nodes and relationships as the diagram, as a tree. Arrow keys move; Right
            opens, Left closes; Enter opens or selects.
          </p>
          <ul className="evgraph-tree" role="tree" aria-labelledby="evgraph-tree-label">
            {rows.map((row) => {
              const node = graph.byId.get(row.id);
              if (!node) return null;
              const children = graph.childrenOf.get(row.id) ?? [];
              const isOpen = state.expanded.includes(row.id);
              const isSelected = state.selectedId === row.id;
              return (
                <li
                  key={row.id}
                  id={domId('evgraph-row', row.id)}
                  className={`evgraph-row${isSelected ? ' selected' : ''}`}
                  role="treeitem"
                  aria-level={row.level}
                  aria-selected={isSelected}
                  aria-expanded={children.length > 0 ? isOpen : undefined}
                  tabIndex={rovingId === row.id ? 0 : -1}
                  data-kind={node.kind}
                  data-node-id={row.id}
                  style={{ paddingInlineStart: `${(row.level - 1) * 14 + 8}px` }}
                  onClick={(e) => {
                    e.stopPropagation();
                    dispatch({ kind: 'select', nodeId: row.id });
                  }}
                  onKeyDown={(e) => onRowKeyDown(e, row.id)}
                >
                  <span className="evgraph-row-swatch" data-kind={node.kind} aria-hidden="true" />
                  <span className="evgraph-row-label">{node.label}</span>
                  <span className="evgraph-row-kind">{NODE_KIND_LABELS[node.kind]}</span>
                  {children.length > 0 && (
                    <span className="evgraph-row-count">{children.length}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>

        <div className="evgraph-canvas-wrap">
          {/*
            aria-hidden, and deliberately so: this is a second rendering of the
            tree beside it. Exposing both would give a screen-reader user two
            copies of every node. The tree is the accessible interface.
          */}
          <svg
            ref={svgRef}
            className="evgraph-canvas"
            viewBox={viewBoxFor(state.view, box)}
            preserveAspectRatio="xMidYMid meet"
            aria-hidden="true"
            focusable="false"
            onPointerDown={onSurfacePointerDown}
            onPointerMove={onSurfacePointerMove}
            onPointerUp={endDrag}
            onPointerLeave={endDrag}
          >
            <g className="evgraph-edges">
              {edges.map((e) => {
                const a = graph.layout.get(e.source);
                const b = graph.layout.get(e.target);
                if (!a || !b) return null;
                const touchesSelected =
                  state.selectedId === e.source || state.selectedId === e.target;
                return (
                  <line
                    key={`${e.kind}|${e.source}|${e.target}`}
                    className={`evgraph-edge${touchesSelected ? ' active' : ''}${
                      e.containment ? '' : ' crosslink'
                    }`}
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
            <g className="evgraph-nodes">
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
                    canExpand={(graph.childrenOf.get(id) ?? []).length > 0}
                    showLabel={labelled.has(id)}
                    onActivate={() => onNodeActivate(id)}
                  />
                );
              })}
            </g>
          </svg>
        </div>

        <aside className="evgraph-detail" aria-label="Selected node">
          {selected ? (
            <NodeDetail
              node={selected}
              graph={graph}
              expanded={state.expanded.includes(selected.id)}
              isAnchor={selected.id === graph.anchorId}
              visibleSet={visibleSet}
              runCheck={{
                runNodeId: selectedRunNodeId,
                pending: selectedRunPending,
                error: selectedRunError,
                checked: selectedRunChecked,
                onCheck: () => selectedRunNodeId && requestCheckFor(selectedRunNodeId),
              }}
              onSelect={(id) => dispatch({ kind: 'select', nodeId: id })}
              onReveal={(id) => dispatch({ kind: 'reveal', nodeId: id })}
              onExpand={(id) => dispatch({ kind: 'expand', nodeId: id })}
              onCollapse={(id) => dispatch({ kind: 'collapse', nodeId: id })}
            />
          ) : (
            <p className="evgraph-detail-empty">
              Select a node to see what it is, where it came from, and why each relationship
              touching it exists.
            </p>
          )}
        </aside>
      </div>

      <p className="evgraph-experiment-id sr-only">
        Evidence graph for experiment {experimentId}.
      </p>
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
  onActivate,
}: {
  node: EvidenceGraphNode;
  x: number;
  y: number;
  scale: number;
  isAnchor: boolean;
  isSelected: boolean;
  isExpanded: boolean;
  canExpand: boolean;
  showLabel: boolean;
  onActivate: () => void;
}) {
  const r = screenBoundedUnits(KIND_RADII[node.kind], scale);
  const font = screenBoundedUnits(LABEL_PX, scale, LABEL_PX_MIN, LABEL_PX_MAX);
  const shape = KIND_SHAPES[node.kind];
  const classes = ['evgraph-node', isAnchor ? 'anchor' : '', isSelected ? 'selected' : '', isExpanded ? 'expanded' : '']
    .filter(Boolean)
    .join(' ');

  return (
    <g
      className={classes}
      data-kind={node.kind}
      data-node-id={node.id}
      transform={`translate(${x} ${y})`}
      onPointerDown={(e) => {
        e.stopPropagation();
        onActivate();
      }}
    >
      {shape === 'circle' && (
        <circle className="evgraph-node-shape" r={r} vectorEffect="non-scaling-stroke" />
      )}
      {shape === 'square' && (
        <rect
          className="evgraph-node-shape"
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
          className="evgraph-node-shape"
          points={`0,${-r} ${r},0 0,${r} ${-r},0`}
          vectorEffect="non-scaling-stroke"
        />
      )}
      {canExpand && !isExpanded && (
        <circle
          className="evgraph-node-more"
          r={Math.max(2.4, r * 0.22)}
          cx={r + r * 0.35}
          cy={-r - r * 0.12}
        />
      )}
      {showLabel && (
        <text
          className="evgraph-node-label"
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
  runCheck,
  onSelect,
  onReveal,
  onExpand,
  onCollapse,
}: {
  node: EvidenceGraphNode;
  graph: EvidenceGraph;
  expanded: boolean;
  isAnchor: boolean;
  visibleSet: Set<string>;
  runCheck: {
    runNodeId: string | null;
    pending: boolean;
    error: string | undefined;
    checked: boolean;
    onCheck: () => void;
  };
  onSelect: (id: string) => void;
  onReveal: (id: string) => void;
  onExpand: (id: string) => void;
  onCollapse: (id: string) => void;
}) {
  const neighbours = graph.adjacency.get(node.id) ?? [];
  const crossLinks = crossLinksOf(node.id, graph);
  const children = graph.childrenOf.get(node.id) ?? [];

  return (
    <div className="evgraph-detail-body">
      <p className="evgraph-detail-kind" data-kind={node.kind}>
        <span className="evgraph-kind-swatch" data-kind={node.kind} aria-hidden="true" />
        {NODE_KIND_LABELS[node.kind]}
      </p>
      <h3 className="evgraph-detail-title">{node.label}</h3>

      <p className="evgraph-detail-producer">
        <span className="evgraph-detail-producer-term">Where this came from</span>
        <span className="evgraph-detail-producer-value">{node.producer}</span>
      </p>

      {node.detail.length > 0 && (
        <dl className="evgraph-detail-list">
          {node.detail.map((line, i) => (
            <div className="evgraph-detail-row" key={`${line.term}-${i}`}>
              <dt>{line.term}</dt>
              <dd>{line.value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="evgraph-detail-actions">
        {children.length > 0 &&
          (expanded ? (
            <button
              type="button"
              className="evgraph-btn"
              disabled={isAnchor}
              onClick={() => onCollapse(node.id)}
            >
              {isAnchor ? 'Anchor — always open' : 'Collapse'}
            </button>
          ) : (
            <button type="button" className="evgraph-btn" onClick={() => onExpand(node.id)}>
              Expand
            </button>
          ))}
      </div>

      {/* Validation findings are read PER RUN, on demand. The three states —
          not read, reading, failed — are distinct, because "no findings" and
          "no verdict" are different facts. */}
      {node.kind === 'run' && runCheck.runNodeId && (
        <div className="evgraph-detail-check">
          {runCheck.pending ? (
            <p className="evgraph-detail-check-state" role="status">
              Reading this run’s validation findings…
            </p>
          ) : runCheck.error ? (
            <p className="evgraph-detail-check-state error" role="note">
              This run’s validation findings could not be read: {runCheck.error}. No findings
              are shown, which is not the same as this run having none.
            </p>
          ) : runCheck.checked ? (
            <p className="evgraph-detail-check-state" role="note">
              Validation findings for this run have been read at its current version.
            </p>
          ) : (
            <button type="button" className="evgraph-btn" onClick={runCheck.onCheck}>
              Read this run’s validation findings
            </button>
          )}
        </div>
      )}

      <h4 className="evgraph-detail-subhead">
        Relationships <span className="evgraph-detail-count">{neighbours.length}</span>
      </h4>
      {/* One list, not two. The cross-links are IN it, each tagged "not in the
          tree" — a separate heading above the list promised a second list that
          was never rendered. The count is stated here because it is the
          reason the tag exists: these are exactly the relationships a reader
          navigating the tree alone would otherwise never meet. */}
      {crossLinks.length > 0 && (
        <p className="evgraph-detail-hint">
          {crossLinks.length} of these {crossLinks.length === 1 ? 'is' : 'are'} not part of the
          tree, and {crossLinks.length === 1 ? 'is' : 'are'} reachable only here — not by
          expanding.
        </p>
      )}
      {neighbours.length === 0 ? (
        <p className="evgraph-detail-empty">This node has no recorded relationships.</p>
      ) : (
        <ul className="evgraph-conn-list">
          {neighbours.map((adj, i) => {
            const other = graph.byId.get(adj.id);
            if (!other) return null;
            const drawn = visibleSet.has(adj.id);
            return (
              <li className="evgraph-conn" key={`${adj.edge.kind}-${adj.id}-${i}`}>
                <p className="evgraph-conn-head">
                  <span className="evgraph-conn-rel" data-edge-kind={adj.edge.kind}>
                    {adj.incoming ? '←' : '→'} {EDGE_KIND_LABELS[adj.edge.kind]}
                  </span>
                  {adj.edge.label && <span className="evgraph-conn-tag">{adj.edge.label}</span>}
                  {!adj.edge.containment && (
                    <span className="evgraph-conn-cross">not in the tree</span>
                  )}
                </p>
                <button
                  type="button"
                  className="evgraph-conn-target"
                  onClick={() => (drawn ? onSelect(adj.id) : onReveal(adj.id))}
                >
                  {other.label}
                  <span className="evgraph-conn-kind">{NODE_KIND_LABELS[other.kind]}</span>
                </button>
                <p className="evgraph-conn-why">{adj.edge.why}</p>
              </li>
            );
          })}
        </ul>
      )}

      <details className="evgraph-legend">
        <summary>What this graph will not draw</summary>
        <p>{EVIDENCE_GRAPH_DISCLOSURE}</p>
        <p>
          No relationship is inferred from resemblance or from time. Two runs are{' '}
          <strong>not</strong> joined because they share a formula, a sample id, a beamline or a
          proposal — a matching string is not an entity. Nothing is ordered into cause and
          effect: <code>created_utc</code> orders records in time, which is not causation. No
          similarity is computed, and no scientific interpretation of any value is drawn,
          because nothing in this application computes one.
        </p>
        <p className="evgraph-legend-kinds">
          {EVIDENCE_NODE_KINDS.map((k) => NODE_KIND_LABELS[k]).join(' · ')}
        </p>
      </details>
    </div>
  );
}

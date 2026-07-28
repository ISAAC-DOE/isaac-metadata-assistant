/*
 * Browse mode — the textual, keyboard-first view of the SAME graph.
 *
 * Permanent, not a fallback. Every capability Explore offers with a pointer is
 * reachable here as text: search and filters are the shared controls above,
 * selection is a button, connections/neighbourhood/path/source-navigation and
 * the raw node JSON all live in the shared GraphDetail panel. What Browse does
 * not have is a viewport — pan/zoom/fit/reset are affordances OF a canvas, not
 * capabilities of the graph.
 */
import { useMemo, useState } from 'react';
import type { ApiMemoryFileSummary, ApiMemoryGraphNode } from '../../lib/types';
import type { GraphAction, GraphIndex, GraphViewState } from '../../lib/graphModel';
import { describeDeepReason, type DeepIndex } from '../../lib/graphDeep';
import { groupFilesByType, domId } from '../ProjectMemory';
import { communityText } from './GraphDetail';

export type BrowseGrouping = 'type' | 'community';

/** Symbols listed per expanded file. Bounded and DISCLOSED, like every other
 *  bound on this surface — one file in the real artifact carries 462. */
const BROWSE_SYMBOL_MAX = 40;

interface GraphBrowseProps {
  index: GraphIndex;
  state: GraphViewState;
  dispatch: (action: GraphAction) => void;
  /** filtered node ids — the textual list is NOT capped by the canvas bound */
  ids: string[];
  grouping: BrowseGrouping;
  /**
   * P36V.1 Unit F — the deep layer. Browse does not gain a viewport (pan/zoom are
   * affordances OF a canvas), but it is the accessible COMPLEMENT of Explore, not
   * a lesser fallback, so every capability of the deeper layers has to be reachable
   * here as text and from the keyboard.
   *
   * The reviewed defect: the deep payload was fetched only when the CANVAS crossed
   * a zoom threshold, so a reader who entered Browse directly never fetched it —
   * no per-row counts, no deep notes — and even once populated Browse offered
   * counts only, with no way to reach a symbol. `GraphDeepDetail` was therefore
   * reachable ONLY by a pointer gesture on the canvas, which contradicts both "no
   * pointer-only graph access" and "Browse remains the exact accessible textual
   * complement to Explore".
   */
  deep?: DeepIndex | null;
  /** the deep layer's fetch state, so Browse can offer to load it itself */
  deepStatus?: 'idle' | 'loading' | 'unavailable' | 'ready';
  /** why it is unavailable, verbatim from the backend */
  deepReason?: string | null;
  /** ask the owner to fetch the deep layer — Browse's own entry point to it */
  onRequestDeep?: () => void;
  /** the pinned symbol, shared with Explore so both modes agree */
  deepSelectedId?: string | null;
  onSelectDeep?: (id: string | null) => void;
}

interface BrowseGroup {
  key: string;
  label: string;
  nodes: ApiMemoryGraphNode[];
}

export function GraphBrowse({
  index,
  state,
  dispatch,
  ids,
  grouping,
  deep = null,
  deepStatus = 'idle',
  deepReason = null,
  onRequestDeep,
  deepSelectedId = null,
  onSelectDeep,
}: GraphBrowseProps) {
  /** Which file rows have their symbol list open. Local: an expansion is a
   *  reading aid, not shared graph state, so it does not belong in the reducer. */
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const nodes = useMemo(
    () => ids.map((id) => index.byId.get(id)).filter((n): n is ApiMemoryGraphNode => n !== undefined),
    [ids, index.byId],
  );

  const groups = useMemo<BrowseGroup[]>(() => {
    if (grouping === 'community') {
      const buckets = new Map<string, ApiMemoryGraphNode[]>();
      for (const n of nodes) {
        const key = n.community_id ?? '';
        if (!buckets.has(key)) buckets.set(key, []);
        buckets.get(key)!.push(n);
      }
      return [...buckets.entries()]
        .sort((a, b) => {
          // Unclustered last; otherwise largest cluster first, ties by id.
          if (a[0] === '') return 1;
          if (b[0] === '') return -1;
          const ra = index.communityById.get(a[0])?.rank ?? Number.MAX_SAFE_INTEGER;
          const rb = index.communityById.get(b[0])?.rank ?? Number.MAX_SAFE_INTEGER;
          return ra - rb || (a[0] < b[0] ? -1 : 1);
        })
        .map(([key, members]) => {
          const entry = key ? index.communityById.get(key) : undefined;
          const label = key === '' ? 'No cluster' : (entry?.name ?? `cluster ${key}`);
          return { key: key || 'none', label, nodes: members };
        });
    }

    // Grouped by file type, reusing the Source Index grouping verbatim so the
    // two surfaces can never disagree about what a "code" or "document" file is.
    const files = nodes.filter((n) => n.kind === 'file');
    const concepts = nodes.filter((n) => n.kind === 'concept');
    const summaries: ApiMemoryFileSummary[] = files.map((n) => ({
      path: n.id,
      file_type: n.kind === 'file' ? n.file_type : null,
      community_id: n.community_id,
      community_name: n.community_name,
      node_count: n.kind === 'file' ? n.node_count : 0,
      on_disk: n.on_disk,
    }));
    const out: BrowseGroup[] = groupFilesByType(summaries).map((g) => ({
      key: g.key,
      label: g.label,
      nodes: g.files
        .map((f) => index.byId.get(f.path))
        .filter((n): n is ApiMemoryGraphNode => n !== undefined),
    }));
    if (concepts.length > 0) out.push({ key: 'concepts', label: 'Concepts', nodes: concepts });
    return out;
  }, [nodes, grouping, index.byId, index.communityById]);

  /** Files in THIS list that carry symbol-level structure, and how much. Derived
   *  only from the deep payload's own `source_file` groups — never estimated. */
  const deepSummary = useMemo(() => {
    if (!deep) return null;
    let withStructure = 0;
    let symbols = 0;
    for (const node of nodes) {
      const members = deep.byFile.get(node.id);
      if (!members || members.length === 0) continue;
      withStructure += 1;
      symbols += members.length;
    }
    return { withStructure, symbols, files: nodes.length };
  }, [deep, nodes]);

  return (
    <div className="memory-graph-list" role="group" aria-label="Graph nodes">
      {/* Browse's OWN entry point to the deeper layer. Without this the payload
          was fetched only when the canvas crossed a zoom threshold, so entering
          Browse directly left the whole symbol level unreachable — a
          pointer-only capability. The fetch stays opt-in and says what it costs;
          it is not made eager just because Browse is open. */}
      {deep === null && deepStatus === 'idle' && onRequestDeep && (
        <div className="memory-graph-list-deepload">
          <p className="memory-graph-list-deepnote">
            Each file here may also contain symbol-level structure — the functions, classes,
            document sections and rationales recorded inside it. It is a separate, larger artifact,
            so it is fetched only when asked for.
          </p>
          <button type="button" className="btn btn-secondary" onClick={onRequestDeep}>
            Load Symbol-Level Detail
          </button>
        </div>
      )}
      {deep === null && deepStatus === 'loading' && (
        <p className="memory-graph-list-deepnote">Loading the symbol-level structure…</p>
      )}
      {deep === null && deepStatus === 'unavailable' && (
        <p className="memory-graph-list-deepnote advisory">
          Symbol-level detail is unavailable in this deployment
          {deepReason ? ` — ${describeDeepReason(deepReason)}` : ''}. The rows below stay at file
          level; nothing was aggregated, estimated or stood in for the missing structure.
        </p>
      )}
      {deepSummary && deepSummary.withStructure > 0 && (
        <p className="memory-graph-list-deepnote">
          {deepSummary.symbols} symbol-level node{deepSummary.symbols === 1 ? '' : 's'} are recorded
          inside {deepSummary.withStructure} of the {deepSummary.files} listed here. Open a row's
          symbol list to read them and pick one — its full detail, including its recorded
          relationships in both directions, appears in the panel beside this list. Explore draws the
          same nodes when zoomed in.
        </p>
      )}
      {nodes.length === 0 && (
        <p className="memory-graph-list-empty">
          No nodes match the current search, filters or focus.
        </p>
      )}
      {groups
        .filter((g) => g.nodes.length > 0)
        .map((group) => (
          <div className="memory-graph-list-group" key={group.key}>
            <h3 className="memory-graph-list-group-heading">
              {group.label}
              <span className="memory-graph-list-group-count">{group.nodes.length}</span>
            </h3>
            <ul className="memory-graph-list-rows">
              {group.nodes.map((node) => {
                const members = deep?.byFile.get(node.id) ?? [];
                const clusters = deep?.clustersByFile.get(node.id)?.length ?? 0;
                const open = expanded[node.id] === true;
                const listId = domId('graph-browse-symbols', node.id);
                return (
                  <li className="memory-graph-list-row" key={node.id}>
                    <button
                      type="button"
                      className={`memory-graph-list-row-btn${state.selectedId === node.id ? ' selected' : ''}`}
                      aria-pressed={state.selectedId === node.id}
                      onClick={() => dispatch({ kind: 'select', nodeId: node.id })}
                    >
                      <span
                        className={`memory-graph-list-shape memory-graph-list-shape-${node.kind}`}
                        aria-hidden="true"
                      />
                      <span className="memory-graph-list-label mono">{node.label ?? node.id}</span>
                      {grouping !== 'community' && communityText(node) && (
                        <span className="memory-graph-list-community">{communityText(node)}</span>
                      )}
                    </button>
                    {/* The symbol list is a SIBLING disclosure, not nested inside
                        the select button (a button cannot contain a button). The
                        counts stay on its label, so the row still reads its real
                        figures whether or not it is expanded. */}
                    {deep && members.length > 0 && (
                      <>
                        <button
                          type="button"
                          className="memory-graph-list-deepcount"
                          aria-expanded={open}
                          aria-controls={listId}
                          onClick={() =>
                            setExpanded((e) => ({ ...e, [node.id]: !(e[node.id] === true) }))
                          }
                        >
                          {members.length} symbol{members.length === 1 ? '' : 's'} · {clusters}{' '}
                          cluster{clusters === 1 ? '' : 's'}
                        </button>
                        {open && (
                          <ul className="memory-graph-list-symbols" id={listId}>
                            {members.slice(0, BROWSE_SYMBOL_MAX).map((memberIndex) => {
                              const symbol = deep.byIndex.get(memberIndex);
                              if (!symbol) return null;
                              const cluster = deep.clusterByKey.get(symbol.clusterKey);
                              return (
                                <li key={symbol.id}>
                                  <button
                                    type="button"
                                    className={`memory-graph-list-symbol-btn${
                                      deepSelectedId === symbol.id ? ' selected' : ''
                                    }`}
                                    aria-pressed={deepSelectedId === symbol.id}
                                    onClick={() =>
                                      onSelectDeep?.(
                                        deepSelectedId === symbol.id ? null : symbol.id,
                                      )
                                    }
                                  >
                                    <span className="memory-graph-list-label mono">
                                      {symbol.label}
                                    </span>
                                    <span className="memory-graph-list-symbol-meta">
                                      {symbol.fileType ?? 'node'}
                                      {cluster?.name
                                        ? ` · ${cluster.name}`
                                        : symbol.communityId
                                          ? ` · cluster ${symbol.communityId}`
                                          : ''}
                                      {symbol.sourceLocation ? ` · ${symbol.sourceLocation}` : ''}
                                      {` · ${symbol.degree} recorded relationship${
                                        symbol.degree === 1 ? '' : 's'
                                      }`}
                                    </span>
                                  </button>
                                </li>
                              );
                            })}
                            {members.length > BROWSE_SYMBOL_MAX && (
                              <li className="memory-graph-list-symbols-note">
                                Showing {BROWSE_SYMBOL_MAX} of {members.length} — the rest are
                                reachable from a listed symbol&apos;s own relationships and on the
                                canvas at symbol zoom, not discarded.
                              </li>
                            )}
                          </ul>
                        )}
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
    </div>
  );
}

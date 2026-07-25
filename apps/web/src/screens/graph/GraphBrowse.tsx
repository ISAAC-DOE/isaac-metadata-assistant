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
import { useMemo } from 'react';
import type { ApiMemoryFileSummary, ApiMemoryGraphNode } from '../../lib/types';
import type { GraphAction, GraphIndex, GraphViewState } from '../../lib/graphModel';
import { groupFilesByType } from '../ProjectMemory';
import { communityText } from './GraphDetail';

export type BrowseGrouping = 'type' | 'community';

interface GraphBrowseProps {
  index: GraphIndex;
  state: GraphViewState;
  dispatch: (action: GraphAction) => void;
  /** filtered node ids — the textual list is NOT capped by the canvas bound */
  ids: string[];
  grouping: BrowseGrouping;
}

interface BrowseGroup {
  key: string;
  label: string;
  nodes: ApiMemoryGraphNode[];
}

export function GraphBrowse({ index, state, dispatch, ids, grouping }: GraphBrowseProps) {
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

  return (
    <div className="memory-graph-list" role="group" aria-label="Graph nodes">
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
              {group.nodes.map((node) => (
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
                </li>
              ))}
            </ul>
          </div>
        ))}
    </div>
  );
}

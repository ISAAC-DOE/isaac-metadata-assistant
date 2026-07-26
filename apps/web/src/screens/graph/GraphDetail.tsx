/*
 * The selected-node detail panel — rendered IDENTICALLY in Explore and Browse.
 *
 * This is the core of the equivalent-access argument: whatever a pointer can
 * discover by clicking a node on the canvas is discoverable here, as text, from
 * the keyboard — kind, cluster, on-disk state, connected nodes with their
 * relation values, neighbourhood expansion, source navigation, and the raw node
 * JSON. The canvas adds spatial insight; it adds no capability.
 */
import type { ApiMemoryGraphNode } from '../../lib/types';
import type { GraphFocus, GraphIndex, GraphNeighbor } from '../../lib/graphModel';
import { communityLabel } from '../ProjectMemory';

/**
 * A node's cluster, for display. Deliberately the SAME helper the Source Index
 * and Concept Lookup use — `community_name` verbatim, else the honest
 * "community <id>", else nothing. A name is never invented here, and the
 * cluster's size is shown as its own figure rather than smuggled into the name.
 */
export function communityText(node: ApiMemoryGraphNode): string | null {
  return communityLabel(node);
}

interface GraphDetailProps {
  node: ApiMemoryGraphNode | null;
  index: GraphIndex;
  connected: GraphNeighbor[];
  /** true when a relation filter is hiding some of this node's connections */
  relationFiltered: boolean;
  onSelect: (id: string) => void;
  onNeighbors: (id: string, depth: 1 | 2) => void;
  onPathFrom: (id: string) => void;
  onNavigateFile: (path: string) => void;
  onNavigateConcept: (id: string) => void;
}

export function GraphDetail({
  node,
  index,
  connected,
  relationFiltered,
  onSelect,
  onNeighbors,
  onPathFrom,
  onNavigateFile,
  onNavigateConcept,
}: GraphDetailProps) {
  if (!node) {
    return (
      <p className="memory-graph-detail-empty">
        No node is selected. Choose a file or concept — from the canvas, the list, or the search box
        — to see its cluster, its recorded connections and its raw entry.
      </p>
    );
  }

  const community = communityText(node);
  const clusterEntry = node.community_id ? index.communityById.get(node.community_id) : undefined;
  const totalConnections = index.adjacency.get(node.id)?.length ?? 0;
  // A file node IS the file; a concept node's `on_disk` describes its anchor
  // source. Naming the referent keeps one sentence honest for both kinds.
  const fileSubject = node.kind === 'file' ? 'the file itself' : 'its source file';

  return (
    <div className="memory-graph-detail">
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
        <div className="memory-graph-detail-figure">
          <dt>Connections</dt>
          <dd className="mono">{totalConnections}</dd>
        </div>
        {clusterEntry && (
          <div className="memory-graph-detail-figure">
            <dt>Cluster size</dt>
            <dd className="mono">
              {clusterEntry.file_count} file{clusterEntry.file_count === 1 ? '' : 's'}
            </dd>
          </div>
        )}
      </dl>

      {/* P36R S10 — ONE sentence for `on_disk`, shared with the Source Index and
          Concepts. `on_disk` is a filesystem existence check under the repo root
          (`memory.py::_on_disk`, which never opens the file), so the copy speaks
          only about the deployment carrying the file — never about snapshot
          membership, which is a different fact and is true of these files.
          The subject differs by node kind because the referent differs: a file
          node IS the file; a concept node's `on_disk` is computed from its
          anchor source (`memory.py:755`). A concept with no served anchor gets
          `on_disk:false` from `_on_disk(None)` with no file behind it at all, so
          claiming a file is missing there would assert one exists. */}
      {node.kind === 'concept' && !node.source_file ? (
        <p className="memory-graph-detail-ondisk-missing">no linked source</p>
      ) : node.on_disk ? (
        <p className="memory-graph-detail-ondisk">
          This deployment carries {fileSubject} — it is not opened or read here.
        </p>
      ) : (
        <p className="memory-graph-detail-ondisk-missing">
          This deployment does not carry {fileSubject} — open it in the project to read it.
        </p>
      )}

      <div className="memory-graph-detail-actions">
        {node.kind === 'file' ? (
          <button type="button" className="btn btn-secondary" onClick={() => onNavigateFile(node.id)}>
            View in Sources
          </button>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={() => onNavigateConcept(node.id)}>
            View in Concepts
          </button>
        )}
        <button type="button" className="btn btn-secondary" onClick={() => onNeighbors(node.id, 1)}>
          Show 1-hop neighbourhood
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => onNeighbors(node.id, 2)}>
          Show 2-hop neighbourhood
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => onPathFrom(node.id)}>
          Use as path start
        </button>
      </div>

      <div className="memory-graph-detail-section">
        <h4 className="memory-graph-detail-section-heading">Connected nodes</h4>
        {connected.length > 0 ? (
          <ul className="memory-graph-detail-connected-list">
            {connected.map((nb) => {
              const n = index.byId.get(nb.id);
              return (
                <li key={nb.id}>
                  <button
                    type="button"
                    className="memory-graph-detail-connected-link"
                    onClick={() => onSelect(nb.id)}
                  >
                    <span className="mono">{n?.label ?? nb.id}</span>
                    {nb.relations.length > 0 && (
                      <span className="memory-graph-detail-relation">{nb.relations.join(', ')}</span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="memory-graph-detail-empty-note">
            {relationFiltered
              ? 'no connections of the selected relationship types for this node'
              : 'no recorded connections for this node in the rendered graph'}
          </p>
        )}
        {relationFiltered && connected.length > 0 && connected.length < totalConnections && (
          <p className="memory-graph-detail-empty-note">
            {totalConnections - connected.length} further connection
            {totalConnections - connected.length === 1 ? ' is' : 's are'} hidden by the relationship
            filter.
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

/**
 * A found path, rendered as ordered text in BOTH modes. The caveat is not
 * decoration: a route through file references is a navigational lead, and
 * saying so where the route is displayed is the honest place to say it.
 */
export function GraphPathResult({
  focus,
  index,
  onSelect,
  onClear,
}: {
  focus: Extract<GraphFocus, { kind: 'path' }>;
  index: GraphIndex;
  onSelect: (id: string) => void;
  onClear: () => void;
}) {
  // focus.ids is the sorted VISIBILITY set; focus.ordered is the route itself,
  // so the steps below read start → end rather than alphabetically.
  const ordered = focus.ordered;
  return (
    <div className="memory-graph-detail">
      <h3 className="memory-graph-detail-title">Path</h3>
      <ol className="memory-graph-path-list">
        {ordered.map((id) => (
          <li key={id}>
            <button type="button" className="memory-graph-detail-connected-link" onClick={() => onSelect(id)}>
              <span className="mono">{index.byId.get(id)?.label ?? id}</span>
            </button>
          </li>
        ))}
      </ol>
      <p className="memory-graph-path-caveat">
        {ordered.length - 1} step{ordered.length - 1 === 1 ? '' : 's'}. A path is a navigational
        lead — it means these files reference one another in the project source. It is not a
        semantic or scientific connection, and it is not evidence for anything in a record.
      </p>
      <div className="memory-graph-detail-actions">
        <button type="button" className="btn btn-secondary" onClick={onClear}>
          Clear path
        </button>
      </div>
    </div>
  );
}

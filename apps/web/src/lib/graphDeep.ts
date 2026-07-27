/*
 * graphDeep — the DEEP (symbol-level) layer behind the Explore canvas's
 * semantic zoom. P36V.1 Unit F owns it.
 *
 * WHAT IT IS: a decoder, a deterministic nested layout, and a level-of-detail
 * render PLAN over the committed artifact served by
 * `GET /api/memory/graph/detail` (2,612 nodes · 4,067 edges · 221 communities,
 * restricted to the snapshot's served-content manifest).
 *
 * WHAT IT IS NOT: a second source of truth, a graph builder, or a place where
 * structure is inferred. Three invariants are encoded here, not just described:
 *
 *  1. NO INVENTED NODES. Every node this module can ever produce is either a row
 *     of the payload's `nodes[]` or a GROUP of such rows keyed by one of their
 *     own fields (`source_file`, `community_id`). No node is synthesised.
 *
 *  2. NO INVENTED EDGES. Every line the canvas can draw is derived by REDUCTION
 *     over the payload's own `edges[]`: at the symbol level one line is one
 *     payload edge (`payloadIndex`); at the cluster level one line is a fold of
 *     ≥1 payload edges between two groups, carrying its backing count and the
 *     index of a real backing edge. A group pair with zero payload edges between
 *     it can therefore never appear — the aggregate set is the IMAGE of the real
 *     edge set, so it cannot be larger than it.
 *
 *  3. NO INVENTED HIERARCHY. The levels come from measurement of this exact
 *     artifact, not from a guess:
 *       · all 2,161 `contains` edges are within-file (0 cross-file), so
 *         file→symbol containment is real;
 *       · every node carries a non-null `source_file` (0 of 2,612 missing) and a
 *         non-null `community_id`;
 *       · 188 of the 221 communities lie entirely inside ONE file, and 75 files
 *         span more than one community (one spans 58) — so `community` is a
 *         grouping INSIDE a file, NOT a container of files. The mid level is
 *         therefore (file, community) groups, and the coarse level is the file
 *         projection the base endpoint already serves.
 *
 * Determinism: no Math.random, no clock, no rAF, no DOM measurement. Every
 * offset is a pure function of the payload (a golden-angle spiral over an
 * explicitly sorted member list); every cap and every ordering is an explicit
 * sort. Same payload + same viewport ⇒ byte-identical plan.
 */
import {
  VIEW_EXTENT,
  nodePosition,
  type GraphIndex,
  type GraphPoint,
  type GraphViewState,
} from './graphModel';

// --------------------------------------------------------------- wire contract

/** One positional node row. Column meaning comes from `node_keys`, never from a
 *  hardcoded position — the decoder resolves the columns by name. */
export type DeepNodeRow = readonly (string | null)[];
/** One positional edge row: two 0-based indices into `nodes[]` plus a relation. */
export type DeepEdgeRow = readonly (number | string | null)[];

export interface ApiGraphDetailCounts {
  nodes: number | null;
  edges: number | null;
  communities: number | null;
  file_types: Record<string, number>;
  relations: Record<string, number>;
}

export interface ApiGraphDetailProvenance {
  built_at_commit: string | null;
  source_graph_sha256: string | null;
  detail_schema_version: number | string | null;
  generator: string | null;
  policy_fingerprint: string | null;
  /** the two honesty flags a consumer can branch on without parsing prose */
  is_point_in_time: boolean;
  describes_current_head: boolean;
  structural_scope: string | null;
  structural_basis: string | null;
  served_content_scope: string | null;
  served_content_basis: string | null;
  served_file_count: number | null;
  /**
   * Names which set `served_file_count` counts, because two counts differ by
   * one and were being conflated: the served PATH SET is 201
   * (`snapshot["served"]`, what this field counts), while the served CONTENT
   * MANIFEST is 200 — the manifest builder self-excludes any
   * `*memory-snapshot.json` it would otherwise hash, since embedding a
   * snapshot digest inside a snapshot is circular. Additive backend field; no
   * rendering depends on it.
   */
  served_file_count_scope?: string | null;
  served_path_set_fingerprint: string | null;
  /** 'current' | 'stale' | 'unknown' — a PATH-SET check, not a content check */
  served_set_consistency: string;
  snapshot_provider?: string | null;
  snapshot_built_at_commit?: string | null;
  note: string;
}

export interface ApiGraphDetailResponse {
  plane: 'memory';
  note: string;
  available: boolean;
  reason?: string | null;
  integrity?: string | null;
  truncated: boolean;
  node_keys: string[];
  edge_keys: string[];
  nodes: DeepNodeRow[];
  edges: DeepEdgeRow[];
  community_names: Record<string, string>;
  encoding: Record<string, string>;
  meta: {
    counts: ApiGraphDetailCounts;
    provenance: ApiGraphDetailProvenance;
  };
}

// ------------------------------------------------------------- decoded shapes

export interface DeepNode {
  /** row position in the payload — the identity `edges[]` refers to */
  index: number;
  id: string;
  label: string;
  fileType: string | null;
  sourceFile: string;
  /** e.g. 'L50', or null (29 of 2,612 rows carry none) */
  sourceLocation: string | null;
  communityId: string | null;
  /** payload edges incident on this node, either direction */
  degree: number;
  /** offset from its file's canvas position, in layout units */
  dx: number;
  dy: number;
  clusterKey: string;
}

export interface DeepEdge {
  /** row position in the payload's `edges[]` — what `data-edge-index` cites */
  index: number;
  source: number;
  target: number;
  /** the source graph's own value, never normalised or invented */
  relation: string;
}

export interface DeepCluster {
  key: string;
  sourceFile: string;
  communityId: string | null;
  /** `community_names[communityId]`, verbatim; null when the payload names none */
  name: string | null;
  /** payload node indices, in spiral order */
  members: number[];
  dx: number;
  dy: number;
  /** payload edges with BOTH endpoints inside this group */
  internalEdges: number;
  /** payload edges with exactly one endpoint inside this group */
  externalEdges: number;
}

export interface DeepIndex {
  nodes: DeepNode[];
  byId: Map<string, DeepNode>;
  /** payload row index → node. Dropped rows leave a HOLE here rather than
   *  shifting their neighbours, which is what keeps `edges[]`'s indices valid. */
  byIndex: Map<number, DeepNode>;
  edges: DeepEdge[];
  /** node index → incident payload edge indices, ascending */
  incident: Map<number, number[]>;
  /** source_file → node indices in spiral order */
  byFile: Map<string, number[]>;
  fileRadius: Map<string, number>;
  clustersByFile: Map<string, DeepCluster[]>;
  clusterByKey: Map<string, DeepCluster>;
  communityNames: Map<string, string>;
  /** relation value → count, from the decoded edges (not from meta) */
  relationCounts: Map<string, number>;
  /** every source_file present, sorted */
  files: string[];
  counts: ApiGraphDetailCounts;
  provenance: ApiGraphDetailProvenance;
  /** the backend already capped the artifact */
  truncated: boolean;
  note: string;
  /** rows that could not be decoded — DROPPED, never repaired */
  droppedNodeRows: number;
  droppedEdgeRows: number;
}

// ---------------------------------------------------------------- the decoder

const NODE_COLUMNS = ['id', 'label', 'file_type', 'source_file', 'source_location', 'community_id'] as const;
const EDGE_COLUMNS = ['source_index', 'target_index', 'relation'] as const;

const asString = (v: unknown): string | null => (typeof v === 'string' && v !== '' ? v : null);

const byAsc = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

/** Numeric-aware compare for ids/locations that are numbers in string clothing
 *  ('116' vs '98', 'L50' vs 'L100'), falling back to a plain compare. */
function numericAware(a: string | null, b: string | null): number {
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  const na = Number(a.replace(/^L/, ''));
  const nb = Number(b.replace(/^L/, ''));
  if (Number.isFinite(na) && Number.isFinite(nb) && na !== nb) return na - nb;
  return byAsc(a, b);
}

/** Golden angle — a CONSTANT, not a seed. The "randomness" of the spiral is the
 *  member's own position in an explicitly sorted list. */
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

/** Spiral radius per sqrt(member count), so symbol DENSITY inside a file is
 *  roughly constant instead of a 1-symbol file occupying a 462-symbol footprint. */
export const FILE_SPIRAL_UNIT = 1.6;
export const FILE_RADIUS_MIN = 4;
/** Capped so a huge file's symbol cloud stays inside its own neighbourhood in
 *  the base layout (measured mean nearest-neighbour spacing ≈ 44 units). */
export const FILE_RADIUS_MAX = 16;

export function deepFileRadius(memberCount: number): number {
  return Math.min(
    FILE_RADIUS_MAX,
    Math.max(FILE_RADIUS_MIN, FILE_SPIRAL_UNIT * Math.sqrt(Math.max(1, memberCount))),
  );
}

/**
 * Decode the columnar payload into the deep index, or return `null` when the
 * payload cannot be decoded (unavailable, missing columns, no rows). Nothing is
 * repaired: a row with no id or no `source_file`, and an edge row whose endpoint
 * index is out of range, is DROPPED and counted.
 */
export function decodeDeepGraph(res: ApiGraphDetailResponse | null | undefined): DeepIndex | null {
  if (!res || !res.available) return null;
  if (!Array.isArray(res.nodes) || !Array.isArray(res.edges)) return null;

  const nodeCol = new Map<string, number>();
  for (const name of NODE_COLUMNS) {
    const at = (res.node_keys ?? []).indexOf(name);
    if (at < 0) return null; // unrecognised schema — never guessed at
    nodeCol.set(name, at);
  }
  const edgeCol = new Map<string, number>();
  for (const name of EDGE_COLUMNS) {
    const at = (res.edge_keys ?? []).indexOf(name);
    if (at < 0) return null;
    edgeCol.set(name, at);
  }

  const col = (row: DeepNodeRow, name: (typeof NODE_COLUMNS)[number]): string | null =>
    asString(row[nodeCol.get(name)!]);

  // --- nodes ---------------------------------------------------------------
  // Row position is the identity `edges[]` uses, so rows are kept in payload
  // order and a dropped row leaves a hole rather than shifting its neighbours.
  const nodes: (DeepNode | null)[] = [];
  let droppedNodeRows = 0;
  res.nodes.forEach((row, index) => {
    const id = col(row, 'id');
    const sourceFile = col(row, 'source_file');
    if (!id || !sourceFile) {
      droppedNodeRows += 1;
      nodes.push(null);
      return;
    }
    const communityId = col(row, 'community_id');
    nodes.push({
      index,
      id,
      label: col(row, 'label') ?? id,
      fileType: col(row, 'file_type'),
      sourceFile,
      sourceLocation: col(row, 'source_location'),
      communityId,
      degree: 0,
      dx: 0,
      dy: 0,
      clusterKey: clusterKeyOf(sourceFile, communityId),
    });
  });

  // --- edges ---------------------------------------------------------------
  const edges: DeepEdge[] = [];
  const incident = new Map<number, number[]>();
  const relationCounts = new Map<string, number>();
  let droppedEdgeRows = 0;
  res.edges.forEach((row, index) => {
    const s = row[edgeCol.get('source_index')!];
    const t = row[edgeCol.get('target_index')!];
    const relation = asString(row[edgeCol.get('relation')!]);
    if (typeof s !== 'number' || typeof t !== 'number' || !relation) {
      droppedEdgeRows += 1;
      return;
    }
    if (!Number.isInteger(s) || !Number.isInteger(t) || s === t) {
      droppedEdgeRows += 1;
      return;
    }
    if (!nodes[s] || !nodes[t]) {
      // An endpoint that is not a decodable node: dropped, never repaired.
      droppedEdgeRows += 1;
      return;
    }
    const edgeIndex = edges.length;
    edges.push({ index, source: s, target: t, relation });
    relationCounts.set(relation, (relationCounts.get(relation) ?? 0) + 1);
    for (const end of [s, t]) {
      const list = incident.get(end);
      if (list) list.push(edgeIndex);
      else incident.set(end, [edgeIndex]);
    }
    nodes[s]!.degree += 1;
    nodes[t]!.degree += 1;
  });

  const kept = nodes.filter((n): n is DeepNode => n !== null);
  if (kept.length === 0) return null;

  // --- per-file spiral layout ---------------------------------------------
  const byFile = new Map<string, number[]>();
  for (const node of kept) {
    const list = byFile.get(node.sourceFile);
    if (list) list.push(node.index);
    else byFile.set(node.sourceFile, [node.index]);
  }
  const fileRadius = new Map<string, number>();
  const clustersByFile = new Map<string, DeepCluster[]>();
  const clusterByKey = new Map<string, DeepCluster>();
  const communityNames = new Map<string, string>(Object.entries(res.community_names ?? {}));

  const files = [...byFile.keys()].sort(byAsc);
  for (const file of files) {
    const members = byFile.get(file)!;
    // Members are ordered so that same-community symbols are CONTIGUOUS on the
    // spiral: that is what makes a (file, community) group a compact blob whose
    // centroid is a meaningful mid-level position rather than a smear.
    members.sort((a, b) => {
      const na = nodes[a]!;
      const nb = nodes[b]!;
      return (
        numericAware(na.communityId, nb.communityId) ||
        numericAware(na.sourceLocation, nb.sourceLocation) ||
        byAsc(na.id, nb.id)
      );
    });
    const n = members.length;
    const radius = deepFileRadius(n);
    fileRadius.set(file, radius);
    members.forEach((nodeIndex, i) => {
      const node = nodes[nodeIndex]!;
      if (n === 1) {
        node.dx = 0;
        node.dy = 0;
        return;
      }
      const r = radius * Math.sqrt((i + 0.5) / n);
      const a = GOLDEN_ANGLE * i;
      node.dx = r * Math.cos(a);
      node.dy = r * Math.sin(a);
    });

    // (file, community) groups — the mid level. Order: largest first, then by
    // community id, so the palette and any cap keep the informative groups.
    const groups = new Map<string, number[]>();
    for (const nodeIndex of members) {
      const key = nodes[nodeIndex]!.clusterKey;
      const list = groups.get(key);
      if (list) list.push(nodeIndex);
      else groups.set(key, [nodeIndex]);
    }
    const clusters: DeepCluster[] = [...groups.entries()]
      .map(([key, groupMembers]) => {
        let sx = 0;
        let sy = 0;
        for (const m of groupMembers) {
          sx += nodes[m]!.dx;
          sy += nodes[m]!.dy;
        }
        const cid = nodes[groupMembers[0]]!.communityId;
        return {
          key,
          sourceFile: file,
          communityId: cid,
          name: cid !== null ? (communityNames.get(cid) ?? null) : null,
          members: groupMembers,
          dx: sx / groupMembers.length,
          dy: sy / groupMembers.length,
          internalEdges: 0,
          externalEdges: 0,
        } satisfies DeepCluster;
      })
      .sort(
        (a, b) =>
          b.members.length - a.members.length || numericAware(a.communityId, b.communityId),
      );
    clustersByFile.set(file, clusters);
    for (const cluster of clusters) clusterByKey.set(cluster.key, cluster);
  }

  // Group edge tallies — a real count of real payload edges, used by the mid
  // level's tooltip and never as a substitute for drawing them.
  for (const edge of edges) {
    const a = nodes[edge.source]!.clusterKey;
    const b = nodes[edge.target]!.clusterKey;
    if (a === b) {
      const cluster = clusterByKey.get(a);
      if (cluster) cluster.internalEdges += 1;
    } else {
      const ca = clusterByKey.get(a);
      const cb = clusterByKey.get(b);
      if (ca) ca.externalEdges += 1;
      if (cb) cb.externalEdges += 1;
    }
  }

  const byId = new Map(kept.map((n) => [n.id, n] as const));
  const byIndex = new Map(kept.map((n) => [n.index, n] as const));

  return {
    nodes: kept,
    byId,
    byIndex,
    edges,
    incident,
    byFile,
    fileRadius,
    clustersByFile,
    clusterByKey,
    communityNames,
    relationCounts,
    files,
    counts: res.meta?.counts ?? {
      nodes: null,
      edges: null,
      communities: null,
      file_types: {},
      relations: {},
    },
    provenance: res.meta.provenance,
    truncated: Boolean(res.truncated),
    note: res.note,
    droppedNodeRows,
    droppedEdgeRows,
  };
}

/** The group key for a (file, community) pair. ` ` cannot occur in either
 *  value, so the key is unambiguous. */
export function clusterKeyOf(sourceFile: string, communityId: string | null): string {
  return `${sourceFile} ${communityId ?? ''}`;
}

// --------------------------------------------------- structural staleness

export interface DeepStaleness {
  builtAtCommit: string | null;
  shortCommit: string | null;
  isPointInTime: boolean;
  describesCurrentHead: boolean;
  /** the SERVED PATH SET axis — 'current' | 'stale' | 'unknown' */
  servedSetConsistency: string;
}

export function deepStaleness(provenance: ApiGraphDetailProvenance): DeepStaleness {
  const commit = asString(provenance?.built_at_commit);
  return {
    builtAtCommit: commit,
    shortCommit: commit ? commit.slice(0, 7) : null,
    isPointInTime: provenance?.is_point_in_time !== false,
    describesCurrentHead: provenance?.describes_current_head === true,
    servedSetConsistency: asString(provenance?.served_set_consistency) ?? 'unknown',
  };
}

/**
 * The structural-staleness sentence rendered ON the graph surface.
 *
 * Deliberately unsoftened. The layer's structure is pinned to
 * `built_at_commit`; at the time of writing that is 213 commits behind HEAD, so
 * everything built in Phases 25–36V — including the Assistant, Settings and this
 * graph surface itself — is absent from it. A 2,612-node symbol map READS as a
 * current code map, and it is not one. "May be slightly out of date" would be a
 * lie of degree, so the wording states the fact and its consequence.
 */
export function stalenessSentence(staleness: DeepStaleness): string {
  const commit = staleness.shortCommit
    ? `commit ${staleness.shortCommit}`
    : 'a commit the payload does not name';
  if (staleness.describesCurrentHead && !staleness.isPointInTime) {
    // Not reachable with today's artifact; handled rather than assumed away.
    return `Symbol-level structure was indexed at ${commit}, which the payload reports as the current repository HEAD.`;
  }
  return (
    `Symbol-level structure is a point-in-time index of ${commit} — it does NOT describe the ` +
    'current repository HEAD. Anything added, renamed or removed since that commit is absent ' +
    'from this layer, including work that exists in the running app.'
  );
}

// ------------------------------------------------------------- LOD render plan

/** Open-file bounds per level. A "few hundred" rendered elements is the target;
 *  these are the first line of defence, before the node/edge caps. */
export const MAX_OPEN_FILES: Record<'cluster' | 'symbol', number> = { cluster: 48, symbol: 32 };
/** Hard cap on deep marks in one frame — deliberately the SAME bound the base
 *  layer uses (`MAX_RENDER_NODES`), so the deep layer can never put more marks
 *  on screen than the file projection ever does. Measured against the real
 *  artifact: the symbol level considers 281 marks at 400% zoom, so this cap does
 *  bite, and it is reported on screen when it does. */
export const MAX_DEEP_NODES = 260;
/** Hard cap on deep lines in one frame. With ≤260 marks and ≤400 lines the
 *  rendered element count stays in the low hundreds of marks / ~1.3k SVG
 *  elements — never the thousands a full 4,067-edge draw would need. */
export const MAX_DEEP_EDGES = 400;
/** Bound on the local neighbourhood pinned around a selected deep node. */
export const MAX_DEEP_NEIGHBORS = 40;
/** Cull window = the viewBox square, expanded by this factor. */
export const CULL_MARGIN = 1.12;

export interface DeepRegion {
  sourceFile: string;
  x: number;
  y: number;
  radius: number;
  label: string;
  memberCount: number;
  clusterCount: number;
}

export interface DeepRenderNode {
  key: string;
  kind: 'cluster' | 'symbol';
  /** cluster key, or the deep node's own id */
  id: string;
  label: string;
  x: number;
  y: number;
  sourceFile: string;
  communityId: string | null;
  communityName: string | null;
  fileType: string | null;
  sourceLocation: string | null;
  /** 1 for a symbol; the group size for a cluster */
  memberCount: number;
  /** real payload edges touching this mark */
  connections: number;
  /** kept regardless of the cap: the selection and its local neighbourhood */
  pinned: boolean;
}

export interface DeepRenderEdge {
  key: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** real relation values, sorted and de-duplicated — never relabelled here */
  relations: string[];
  /** payload `edges[]` index of a REAL edge this line stands for */
  payloadIndex: number;
  /** how many real payload edges this line folds (1 at the symbol level) */
  backing: number;
  from: string;
  to: string;
}

export interface DeepRenderPlan {
  level: 'cluster' | 'symbol';
  regions: DeepRegion[];
  nodes: DeepRenderNode[];
  edges: DeepRenderEdge[];
  /** base-visible files that carry deep structure and fall in the cull window */
  openFiles: number;
  /** …before the open-file cap */
  candidateFiles: number;
  nodesConsidered: number;
  nodesTruncated: boolean;
  edgesConsidered: number;
  edgesTruncated: boolean;
  /** base-visible files with NO symbol-level structure in this artifact */
  filesWithoutDeepStructure: number;
  /** files the base layout has no position for — never drawn at a guessed spot */
  unplacedFiles: number;
}

interface CullWindow {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

function cullWindow(state: GraphViewState): CullWindow {
  const half = ((VIEW_EXTENT / state.view.scale) / 2) * CULL_MARGIN;
  return {
    x0: state.view.cx - half,
    x1: state.view.cx + half,
    y0: state.view.cy - half,
    y1: state.view.cy + half,
  };
}

const inWindow = (w: CullWindow, p: GraphPoint, pad = 0): boolean =>
  p.x >= w.x0 - pad && p.x <= w.x1 + pad && p.y >= w.y0 - pad && p.y <= w.y1 + pad;

/**
 * Build the deep render plan for the current viewport.
 *
 * `visibleBaseIds` is what the BASE layer would draw, so every active filter
 * (search, node type, cluster) is inherited: the deeper layers only ever open
 * files the current filters leave on the canvas. `state.relationFilter` is
 * applied to the deep edges by their own real relation values.
 */
export function deepRenderPlan(
  deep: DeepIndex,
  base: GraphIndex,
  state: GraphViewState,
  visibleBaseIds: readonly string[],
  level: 'cluster' | 'symbol',
  selectedDeepId: string | null,
): DeepRenderPlan {
  const cull = cullWindow(state);
  const relationFilter = state.relationFilter;
  const relationAllowed = (relation: string): boolean =>
    relationFilter === null || relationFilter.includes(relation);

  // --- 1. which files are open ---------------------------------------------
  let filesWithoutDeepStructure = 0;
  let unplacedFiles = 0;
  const candidates: { file: string; pos: GraphPoint; radius: number; distance: number }[] = [];
  for (const id of [...visibleBaseIds].sort(byAsc)) {
    const members = deep.byFile.get(id);
    if (!members || members.length === 0) {
      // A served file with no symbol-level structure in this artifact. Stated,
      // never padded out with a placeholder symbol.
      if (base.byId.get(id)?.kind === 'file') filesWithoutDeepStructure += 1;
      continue;
    }
    const pos = nodePosition(id, state, base);
    if (!pos) {
      unplacedFiles += 1;
      continue;
    }
    const radius = deep.fileRadius.get(id) ?? FILE_RADIUS_MIN;
    if (!inWindow(cull, pos, radius)) continue;
    const dx = pos.x - state.view.cx;
    const dy = pos.y - state.view.cy;
    candidates.push({ file: id, pos, radius, distance: Math.hypot(dx, dy) });
  }
  const candidateFiles = candidates.length;
  // Nearest to the viewport centre first — the files the reader is looking at.
  candidates.sort((a, b) => a.distance - b.distance || byAsc(a.file, b.file));
  const open = candidates.slice(0, MAX_OPEN_FILES[level]);
  const openByFile = new Map(open.map((o) => [o.file, o] as const));

  const regions: DeepRegion[] = open
    .map((o) => ({
      sourceFile: o.file,
      x: o.pos.x,
      y: o.pos.y,
      radius: o.radius,
      label: o.file.slice(o.file.lastIndexOf('/') + 1) || o.file,
      memberCount: deep.byFile.get(o.file)?.length ?? 0,
      clusterCount: deep.clustersByFile.get(o.file)?.length ?? 0,
    }))
    .sort((a, b) => byAsc(a.sourceFile, b.sourceFile));

  // --- 2. the marks --------------------------------------------------------
  const nodes: DeepRenderNode[] = [];
  let nodesConsidered = 0;
  let nodesTruncated = false;

  if (level === 'cluster') {
    const all: DeepRenderNode[] = [];
    for (const o of open) {
      for (const cluster of deep.clustersByFile.get(o.file) ?? []) {
        all.push({
          key: cluster.key,
          kind: 'cluster',
          id: cluster.key,
          label: cluster.name ?? (cluster.communityId ? `cluster ${cluster.communityId}` : 'no cluster'),
          x: o.pos.x + cluster.dx,
          y: o.pos.y + cluster.dy,
          sourceFile: cluster.sourceFile,
          communityId: cluster.communityId,
          communityName: cluster.name,
          fileType: deep.byIndex.get(cluster.members[0])?.fileType ?? null,
          sourceLocation: null,
          memberCount: cluster.members.length,
          connections: cluster.internalEdges + cluster.externalEdges,
          pinned: selectedDeepId === cluster.key,
        });
      }
    }
    nodesConsidered = all.length;
    // Largest group first, ties by key: a cap keeps the structurally
    // informative groups and drops the singletons, deterministically.
    all.sort(
      (a, b) => Number(b.pinned) - Number(a.pinned) || b.memberCount - a.memberCount || byAsc(a.key, b.key),
    );
    nodesTruncated = all.length > MAX_DEEP_NODES;
    nodes.push(...all.slice(0, MAX_DEEP_NODES));
  } else {
    // Symbol level. The selection and a BOUNDED local neighbourhood are pinned
    // first, so a selected node's real neighbours appear without a mode switch
    // even when they live in a file that is off to the side.
    const pinned = new Set<number>();
    const selected = selectedDeepId ? deep.byId.get(selectedDeepId) : undefined;
    if (selected) {
      pinned.add(selected.index);
      const neighbours: number[] = [];
      for (const edgeIndex of deep.incident.get(selected.index) ?? []) {
        const edge = deep.edges[edgeIndex];
        if (!relationAllowed(edge.relation)) continue;
        const other = edge.source === selected.index ? edge.target : edge.source;
        if (!neighbours.includes(other)) neighbours.push(other);
      }
      neighbours
        .sort((a, b) => byAsc(idOf(deep, a), idOf(deep, b)))
        .slice(0, MAX_DEEP_NEIGHBORS)
        .forEach((n) => pinned.add(n));
    }

    const candidateIndices: number[] = [];
    for (const o of open) {
      for (const nodeIndex of deep.byFile.get(o.file) ?? []) candidateIndices.push(nodeIndex);
    }
    for (const nodeIndex of pinned) {
      if (!candidateIndices.includes(nodeIndex)) candidateIndices.push(nodeIndex);
    }
    nodesConsidered = candidateIndices.length;

    const placed: { node: DeepNode; x: number; y: number; pinned: boolean }[] = [];
    for (const nodeIndex of candidateIndices) {
      const node = nodeAt(deep, nodeIndex);
      if (!node) continue;
      const filePos =
        openByFile.get(node.sourceFile)?.pos ?? nodePosition(node.sourceFile, state, base);
      if (!filePos) continue; // no position for its file — never drawn at a guess
      const x = filePos.x + node.dx;
      const y = filePos.y + node.dy;
      const isPinned = pinned.has(nodeIndex);
      if (!isPinned && !inWindow(cull, { x, y })) continue;
      placed.push({ node, x, y, pinned: isPinned });
    }
    // Pinned first, then most-connected, ties by id: the same ranking rule the
    // base render cap uses, so "what survives the cap" is never a surprise.
    placed.sort(
      (a, b) =>
        Number(b.pinned) - Number(a.pinned) ||
        b.node.degree - a.node.degree ||
        byAsc(a.node.id, b.node.id),
    );
    nodesTruncated = placed.length > MAX_DEEP_NODES;
    for (const p of placed.slice(0, MAX_DEEP_NODES)) {
      const cluster = deep.clusterByKey.get(p.node.clusterKey);
      nodes.push({
        key: p.node.id,
        kind: 'symbol',
        id: p.node.id,
        label: p.node.label,
        x: p.x,
        y: p.y,
        sourceFile: p.node.sourceFile,
        communityId: p.node.communityId,
        communityName: cluster?.name ?? null,
        fileType: p.node.fileType,
        sourceLocation: p.node.sourceLocation,
        memberCount: 1,
        connections: p.node.degree,
        pinned: p.pinned,
      });
    }
  }

  // --- 3. the lines --------------------------------------------------------
  // Both branches are a REDUCTION over `deep.edges` — the only edge source.
  const drawnById = new Map(nodes.map((n) => [n.id, n] as const));
  const edges: DeepRenderEdge[] = [];
  let edgesConsidered = 0;
  let edgesTruncated = false;

  if (level === 'symbol') {
    const rendered: DeepRenderEdge[] = [];
    for (const edge of deep.edges) {
      if (!relationAllowed(edge.relation)) continue;
      const from = nodeAt(deep, edge.source);
      const to = nodeAt(deep, edge.target);
      if (!from || !to) continue;
      const a = drawnById.get(from.id);
      const b = drawnById.get(to.id);
      if (!a || !b) continue;
      rendered.push({
        key: `${edge.index}`,
        x1: a.x,
        y1: a.y,
        x2: b.x,
        y2: b.y,
        relations: [edge.relation],
        payloadIndex: edge.index,
        backing: 1,
        from: from.id,
        to: to.id,
      });
    }
    edgesConsidered = rendered.length;
    edgesTruncated = rendered.length > MAX_DEEP_EDGES;
    edges.push(...rendered.slice(0, MAX_DEEP_EDGES));
  } else {
    // Cluster level: fold real edges onto the ORDERED group pair, preserving
    // direction. The aggregate set is the image of the real edge set under the
    // grouping function, so it can never contain a pair with no real edge.
    const folded = new Map<
      string,
      { from: string; to: string; relations: Set<string>; backing: number; payloadIndex: number }
    >();
    for (const edge of deep.edges) {
      if (!relationAllowed(edge.relation)) continue;
      const from = nodeAt(deep, edge.source);
      const to = nodeAt(deep, edge.target);
      if (!from || !to) continue;
      if (from.clusterKey === to.clusterKey) continue; // inside one group: counted, not drawn
      const a = drawnById.get(from.clusterKey);
      const b = drawnById.get(to.clusterKey);
      if (!a || !b) continue;
      const key = `${from.clusterKey}${to.clusterKey}`;
      const entry = folded.get(key);
      if (entry) {
        entry.relations.add(edge.relation);
        entry.backing += 1;
      } else {
        folded.set(key, {
          from: from.clusterKey,
          to: to.clusterKey,
          relations: new Set([edge.relation]),
          backing: 1,
          payloadIndex: edge.index,
        });
      }
    }
    const aggregated = [...folded.entries()]
      .sort((a, b) => byAsc(a[0], b[0]))
      .map(([key, entry]) => {
        const a = drawnById.get(entry.from)!;
        const b = drawnById.get(entry.to)!;
        return {
          key,
          x1: a.x,
          y1: a.y,
          x2: b.x,
          y2: b.y,
          relations: [...entry.relations].sort(byAsc),
          payloadIndex: entry.payloadIndex,
          backing: entry.backing,
          from: entry.from,
          to: entry.to,
        } satisfies DeepRenderEdge;
      });
    edgesConsidered = aggregated.length;
    edgesTruncated = aggregated.length > MAX_DEEP_EDGES;
    edges.push(...aggregated.slice(0, MAX_DEEP_EDGES));
  }

  return {
    level,
    regions,
    nodes,
    edges,
    openFiles: open.length,
    candidateFiles,
    nodesConsidered,
    nodesTruncated,
    edgesConsidered,
    edgesTruncated,
    filesWithoutDeepStructure,
    unplacedFiles,
  };
}

/** The decoded node at a payload row index, or undefined when that row was
 *  dropped. O(1) — a dropped row must never shift its neighbours. */
function nodeAt(deep: DeepIndex, payloadIndex: number): DeepNode | undefined {
  return deep.byIndex.get(payloadIndex);
}

const idOf = (deep: DeepIndex, payloadIndex: number): string =>
  nodeAt(deep, payloadIndex)?.id ?? String(payloadIndex);

// ------------------------------------------------------------------- tooltips

export interface DeepTooltip {
  title: string;
  kind: string;
  cluster: string | null;
  connections: string;
  source: string;
  relationships: string | null;
}

/** Human-readable relationship summary for a mark: real relation values with
 *  their counts, most frequent first. Never a guess, never a total that includes
 *  a relation the payload did not record. */
export function deepRelationSummary(
  deep: DeepIndex,
  node: DeepRenderNode,
  relationFilter: readonly string[] | null,
): { relation: string; count: number }[] {
  const counts = new Map<string, number>();
  const memberIndices =
    node.kind === 'symbol'
      ? (() => {
          const found = deep.byId.get(node.id);
          return found ? [found.index] : [];
        })()
      : (deep.clusterByKey.get(node.id)?.members ?? []);
  const seen = new Set<number>();
  for (const memberIndex of memberIndices) {
    for (const edgeIndex of deep.incident.get(memberIndex) ?? []) {
      if (seen.has(edgeIndex)) continue;
      seen.add(edgeIndex);
      const edge = deep.edges[edgeIndex];
      if (relationFilter !== null && !relationFilter.includes(edge.relation)) continue;
      counts.set(edge.relation, (counts.get(edge.relation) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([relation, count]) => ({ relation, count }))
    .sort((a, b) => b.count - a.count || byAsc(a.relation, b.relation));
}

/*
 * Synthetic fixtures for the DEEP (symbol-level) graph layer — P36V.1 Unit F.
 *
 * Shape-faithful to `GET /api/memory/graph/detail` (columnar rows, 0-based edge
 * endpoint indices, real relation vocabulary) and unmistakably FAKE: the files
 * are the same `src/fake_mod.py` / `src/other_mod.py` / `docs/fake-note.md`
 * placeholders the base graph fixture uses, and the build commit is
 * `f00dface…`.
 *
 * The rows are deliberately arranged so that every level-of-detail behaviour is
 * exercisable with a handful of nodes:
 *   · `src/fake_mod.py` holds TWO communities (131, 77), so its mid level has
 *     more than one mark and a real cross-cluster edge inside one file;
 *   · community `55` is deliberately ABSENT from `community_names`, so the
 *     "cluster <id>" fallback is exercised rather than assumed;
 *   · edges 4 and 7 share the same (cluster → cluster) pair, so the mid level
 *     must FOLD them into one line with `backing: 2`;
 *   · `docs/fake-note.md` sits on the base layout's unconnected belt, far from
 *     the origin, so viewport culling has something to cull.
 */
import type { ApiGraphDetailResponse } from '../lib/graphDeep';

export const DEEP_BUILT_AT_COMMIT = 'f00dfacef00dfacef00dfacef00dfacef00dface';

const NOTE =
  'Project memory returns leads to verify — never a validation verdict. This is the ' +
  'symbol-level structure of the source graph as indexed at built_at_commit; it is a ' +
  'point-in-time snapshot, not a map of the current repository HEAD.';

const PROVENANCE_NOTE =
  'structure describes built_at_commit (point-in-time Graphify index), while the served-file ' +
  'content manifest is CI-current; the two are separate axes';

/** node rows: [id, label, file_type, source_file, source_location, community_id] */
export const DEEP_NODE_ROWS: (string | null)[][] = [
  /* 0 */ ['fake/mod_root', 'fake_mod.py', 'code', 'src/fake_mod.py', 'L1', '131'],
  /* 1 */ ['fake/export_fn', 'export_record', 'code', 'src/fake_mod.py', 'L20', '131'],
  /* 2 */ ['fake/validate_fn', 'validate_draft', 'code', 'src/fake_mod.py', 'L58', '77'],
  /* 3 */ ['fake/helper_fn', 'sha256_of', 'code', 'src/fake_mod.py', 'L96', '77'],
  /* 4 */ ['other/mod_root', 'other_mod.py', 'code', 'src/other_mod.py', 'L1', '55'],
  /* 5 */ ['other/load_fn', 'load_snapshot', 'code', 'src/other_mod.py', 'L12', '55'],
  /* 6 */ ['note/section', 'Fake Note', 'document', 'docs/fake-note.md', 'L1', '208'],
  /* 7 */ ['note/rationale', 'why memory cites this', 'rationale', 'docs/fake-note.md', null, '208'],
];

/** edge rows: [source_index, target_index, relation] — direction as recorded. */
export const DEEP_EDGE_ROWS: [number, number, string][] = [
  /* 0 */ [0, 1, 'contains'],
  /* 1 */ [0, 2, 'contains'],
  /* 2 */ [2, 3, 'calls'],
  /* 3 */ [1, 2, 'calls'],
  /* 4 */ [1, 5, 'imports'],
  /* 5 */ [4, 5, 'contains'],
  /* 6 */ [7, 6, 'rationale_for'],
  /* 7 */ [1, 4, 'imports_from'],
];

export const memoryGraphDetailAvailable: ApiGraphDetailResponse = {
  plane: 'memory',
  note: NOTE,
  available: true,
  reason: null,
  integrity: 'verified',
  truncated: false,
  node_keys: ['id', 'label', 'file_type', 'source_file', 'source_location', 'community_id'],
  edge_keys: ['source_index', 'target_index', 'relation'],
  nodes: DEEP_NODE_ROWS,
  edges: DEEP_EDGE_ROWS,
  community_names: {
    '131': 'Export Pipeline',
    '77': 'Draft Validator',
    '208': 'Fake Notes',
    // '55' is intentionally unnamed.
  },
  encoding: {
    nodes: 'Positional rows matching node_keys.',
    edges: 'Positional rows matching edge_keys; indices are 0-based into nodes[].',
    community_names: 'Mapping of community_id -> curated community name.',
  },
  meta: {
    counts: {
      nodes: 8,
      edges: 8,
      communities: 4,
      file_types: { code: 6, document: 1, rationale: 1 },
      relations: { calls: 2, contains: 3, imports: 1, imports_from: 1, rationale_for: 1 },
    },
    provenance: {
      built_at_commit: DEEP_BUILT_AT_COMMIT,
      source_graph_sha256: 'f00dface00000000000000000000000000000000000000000000000000000000',
      detail_schema_version: 1,
      generator: 'scripts/build_memory_snapshot.py (synthetic fixture)',
      policy_fingerprint: 'fake-policy-fingerprint',
      is_point_in_time: true,
      describes_current_head: false,
      structural_scope: 'served_files_only',
      structural_basis: 'point_in_time_graph_index',
      served_content_scope: 'served_files_only',
      served_content_basis: 'ci_content_manifest',
      served_file_count: 3,
      served_path_set_fingerprint: 'fake-path-set-fingerprint',
      served_set_consistency: 'current',
      snapshot_provider: 'snapshot',
      snapshot_built_at_commit: DEEP_BUILT_AT_COMMIT,
      note: PROVENANCE_NOTE,
    },
  },
};

/** The honest degraded envelope: HTTP 200, `available:false`, zero rows. */
export const memoryGraphDetailUnavailable: ApiGraphDetailResponse = {
  plane: 'memory',
  note: NOTE,
  available: false,
  reason: 'detail_absent',
  integrity: 'unknown',
  truncated: false,
  node_keys: [],
  edge_keys: [],
  nodes: [],
  edges: [],
  community_names: {},
  encoding: {},
  meta: {
    counts: { nodes: 0, edges: 0, communities: 0, file_types: {}, relations: {} },
    provenance: {
      built_at_commit: null,
      source_graph_sha256: null,
      detail_schema_version: null,
      generator: null,
      policy_fingerprint: null,
      is_point_in_time: true,
      describes_current_head: false,
      structural_scope: null,
      structural_basis: null,
      served_content_scope: 'served_files_only',
      served_content_basis: 'ci_content_manifest',
      served_file_count: null,
      served_path_set_fingerprint: null,
      served_set_consistency: 'unknown',
      snapshot_provider: null,
      snapshot_built_at_commit: null,
      note: PROVENANCE_NOTE,
    },
  },
};

/** A payload whose column contract is not the one this client decodes. */
export const memoryGraphDetailUnknownSchema: ApiGraphDetailResponse = {
  ...memoryGraphDetailAvailable,
  node_keys: ['id', 'label', 'kind', 'path'],
  edge_keys: ['from', 'to', 'kind'],
};

/** A large synthetic payload for the performance bounds: `files` files ×
 *  `perFile` symbols, chained by real `contains` + `calls` rows. Every row is
 *  synthetic and self-evidently so. */
export function bigDeepPayload(files: number, perFile: number): ApiGraphDetailResponse {
  const nodes: (string | null)[][] = [];
  const edges: [number, number, string][] = [];
  const communityNames: Record<string, string> = {};
  for (let f = 0; f < files; f += 1) {
    const path = `synthetic/chain-${String(f).padStart(4, '0')}.py`;
    const rootIndex = nodes.length;
    for (let i = 0; i < perFile; i += 1) {
      // Two communities per file, so the mid level has real groups to fold.
      const community = `${f * 2 + (i % 2)}`;
      communityNames[community] = `synthetic cluster ${community}`;
      nodes.push([`${path}#sym-${i}`, `sym_${i}`, 'code', path, `L${i * 4 + 1}`, community]);
      if (i > 0) edges.push([rootIndex, rootIndex + i, 'contains']);
      if (i > 1) edges.push([rootIndex + i - 1, rootIndex + i, 'calls']);
    }
    if (f > 0) edges.push([rootIndex, rootIndex - perFile, 'imports']);
  }
  return {
    ...memoryGraphDetailAvailable,
    nodes,
    edges,
    community_names: communityNames,
    meta: {
      ...memoryGraphDetailAvailable.meta,
      counts: {
        nodes: nodes.length,
        edges: edges.length,
        communities: Object.keys(communityNames).length,
        file_types: { code: nodes.length },
        relations: {},
      },
    },
  };
}
